"""Jeden "dom" QBota (20.10.2026, sesja dom-2010; decyzja Michala: adres podawany w SETUP > Uzytkownik).

Kolejnosc zrodel:
  1. adres z SETUP > Uzytkownik (qbot_v2.app_settings, klucz 'user_home': address, lat, lon),
  2. wyliczony z jazd: komorka 0,01 st (~1 km) z najwieksza liczba startow 120 ostatnich jazd, mediana startow w niej
     (ta sama metoda co punkt bramy z 16.10; wczesniej Trener/Pogoda zaokraglaly do 0,1 st = ~5 km bledu).
Uzywaja: Trener (qbot_trener_engine.home_point -> pogoda planu, powiadomienia), Pogoda (/api/pogoda/dom, tarcza dnia),
Brama (zapis do /opt/qbot/artifacts/gate_home.json przy zmianie adresu). Dok.: docs/DOM.md
"""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

KEY = "user_home"
GATE_HOME_FILE = Path("/opt/qbot/artifacts/gate_home.json")
_CACHE: dict = {}


def _row(r, i, k):
    return r[k] if isinstance(r, dict) else r[i]


def saved(cur) -> dict | None:
    cur.execute("CREATE TABLE IF NOT EXISTS qbot_v2.app_settings (key TEXT PRIMARY KEY, value JSONB NOT NULL, "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())")
    cur.execute("SELECT value FROM qbot_v2.app_settings WHERE key=%s", (KEY,))
    r = cur.fetchone()
    v = _row(r, 0, "value") if r else None
    if isinstance(v, str):
        v = json.loads(v)
    if isinstance(v, dict) and v.get("lat") is not None and v.get("lon") is not None:
        return v
    return None


def computed(cur) -> tuple[float, float] | None:
    cur.execute("""WITH s AS (SELECT external_id FROM qbot_v2.training_sessions
                              WHERE sport_type IN ('cycling','gravel_cycling') ORDER BY date DESC LIMIT 120)
                   SELECT DISTINCT ON (r.external_id) r.lat, r.lon FROM qbot_v2.activity_record r JOIN s USING (external_id)
                   WHERE r.lat IS NOT NULL ORDER BY r.external_id, r.sec""")
    cells: dict = {}
    for r in cur.fetchall():
        la, lo = float(_row(r, 0, "lat")), float(_row(r, 1, "lon"))
        cells.setdefault((round(la, 2), round(lo, 2)), []).append((la, lo))
    if not cells:
        return None
    best = max(cells.values(), key=len)
    return (round(statistics.median(p[0] for p in best), 6), round(statistics.median(p[1] for p in best), 6))


def home(cur, fresh: bool = False) -> dict | None:
    """{lat, lon, address, zrodlo, z_jazd:{lat,lon}|None}; cache 10 min (zapis adresu czysci cache)."""
    if not fresh and _CACHE.get("t", 0) > time.time() - 600:
        return _CACHE.get("v")
    s = saved(cur)
    c = _CACHE.get("c") if _CACHE.get("ct", 0) > time.time() - 86400 else None
    if c is None:
        c = computed(cur)
        _CACHE.update(c=c, ct=time.time())
    if s:
        v = {"lat": float(s["lat"]), "lon": float(s["lon"]), "address": s.get("address") or "", "zrodlo": "adres z SETUP > Użytkownik"}
    elif c:
        v = {"lat": c[0], "lon": c[1], "address": "", "zrodlo": "wyliczony z jazd: najczęstszy start, dokładność ok. 100 m"}
    else:
        v = None
    if v is not None:
        v["z_jazd"] = {"lat": c[0], "lon": c[1]} if c else None
    _CACHE.update(t=time.time(), v=v)
    return v


def point(cur) -> tuple[float, float] | None:
    h = home(cur)
    return (h["lat"], h["lon"]) if h else None


def _write_gate(lat: float, lon: float, source: str) -> None:
    try:
        tmp = GATE_HOME_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"lat": lat, "lon": lon, "radius_m": 300, "source": source,
                                   "computed": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(GATE_HOME_FILE)
    except Exception:
        pass


def save(cur, address: str, lat: float, lon: float) -> dict:
    lat, lon = float(lat), float(lon)
    if not (49.0 <= lat <= 55.5 and 14.0 <= lon <= 24.5):
        raise ValueError("Punkt poza Polską — sprawdź adres.")
    v = {"address": (address or "").strip()[:200], "lat": round(lat, 6), "lon": round(lon, 6),
         "saved": time.strftime("%Y-%m-%dT%H:%M:%S")}
    saved(cur)
    cur.execute("INSERT INTO qbot_v2.app_settings (key, value) VALUES (%s, %s::jsonb) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()", (KEY, json.dumps(v, ensure_ascii=False)))
    _CACHE.pop("t", None)
    _write_gate(v["lat"], v["lon"], "adres z SETUP > Użytkownik")
    return home(cur, fresh=True)


def clear(cur) -> dict | None:
    cur.execute("DELETE FROM qbot_v2.app_settings WHERE key=%s", (KEY,))
    _CACHE.clear()
    h = home(cur, fresh=True)
    if h:
        _write_gate(h["lat"], h["lon"], "wyliczony z jazd (komórka 0,01°, mediana startów)")
    return h


def geocode(q: str) -> list[dict]:
    """Adres -> do 5 propozycji (Nominatim/OSM, Polska)."""
    import httpx
    q = (q or "").strip()
    if len(q) < 3:
        return []
    r = httpx.get("https://nominatim.openstreetmap.org/search",
                  params={"q": q, "format": "jsonv2", "countrycodes": "pl", "limit": 5, "addressdetails": 0, "accept-language": "pl"},
                  headers={"User-Agent": "QBot/1.0 (qbot.cytr.us; adres domowy uzytkownika)"}, timeout=10)
    r.raise_for_status()
    return [{"label": x.get("display_name", ""), "lat": float(x["lat"]), "lon": float(x["lon"]), "typ": x.get("type")} for x in r.json()]
