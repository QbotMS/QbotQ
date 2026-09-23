"""[G1] Zaproszenia gosci na jazde: osobny token na osobe + widok danych z BIALEJ LISTY.

Token (secrets.token_urlsafe(24) = 32 znaki) otwiera JEDNA trase + JEDEN dzien z planem
organizatora (godzina startu + przerwy zapisane przy zaproszeniu). Waznosc: do konca dnia
po jezdzie (Europe/Warsaw). Uniewaznienie = revoked_at. Licznik otwarc + ostatnie otwarcie.
Widok gosciem liczony warstwa planu BEZ AI (qbot_web._build_report_data ai=False, day_table=True);
komentarze odcinkow ryzyka z pakietu dnia, jesli jest. Zadne pole spoza guest_view() nie wychodzi.
"""
from __future__ import annotations

import datetime as _dt
import re
import secrets
import time
import threading

STATUSY = ("czeka", "tak", "nie")
_RL: dict = {}
_RL_LOCK = threading.Lock()
RL_MAX, RL_WIN_S = 120, 600          # max zapytan na token w oknie 10 min


def ensure(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS qbot_v2.ride_invite ("
                 "token text PRIMARY KEY, route_id text NOT NULL, ride_date date NOT NULL, "
                 "start_time text NOT NULL, long_stops int NOT NULL DEFAULT 0, long_stop_min int NOT NULL DEFAULT 0, "
                 "email text NOT NULL, status text NOT NULL DEFAULT 'czeka', "
                 "created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL, "
                 "revoked_at timestamptz, responded_at timestamptz, "
                 "open_count int NOT NULL DEFAULT 0, last_opened_at timestamptz)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ride_invite_uq ON qbot_v2.ride_invite (route_id, ride_date, lower(email))")


def _row(r):
    return dict(r) if isinstance(r, dict) else r


def rate_ok(token: str) -> bool:
    now = time.time()
    with _RL_LOCK:
        q = [t for t in _RL.get(token, []) if now - t < RL_WIN_S]
        if len(q) >= RL_MAX:
            _RL[token] = q
            return False
        q.append(now)
        _RL[token] = q
        return True


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def create_invites(conn, route_id: str, ride_date: str, start_time: str, long_stops: int,
                   long_stop_min: int, emails: list) -> list:
    """Jedno zaproszenie na adres. Istniejace (ta sama trasa+dzien+email) - aktualizuje plan,
    przywraca waznosc (zdejmuje uniewaznienie), TOKEN ZOSTAJE (wyslany link dalej dziala)."""
    ensure(conn)
    out = []
    for e in emails or []:
        e = str(e or "").strip()
        if not _EMAIL.match(e):
            out.append({"email": e, "ok": False, "blad": "zly adres"})
            continue
        tok = secrets.token_urlsafe(24)
        r = conn.execute(
            "INSERT INTO qbot_v2.ride_invite (token, route_id, ride_date, start_time, long_stops, long_stop_min, email, expires_at) "
            "VALUES (%s, %s, %s::date, %s, %s, %s, %s, "
            "  ((%s::date + 2)::timestamp AT TIME ZONE 'Europe/Warsaw') - interval '1 second') "
            "ON CONFLICT (route_id, ride_date, (lower(email))) DO UPDATE SET start_time=EXCLUDED.start_time, "
            "  long_stops=EXCLUDED.long_stops, long_stop_min=EXCLUDED.long_stop_min, "
            "  expires_at=EXCLUDED.expires_at, revoked_at=NULL "
            "RETURNING token, email, status, expires_at",
            (tok, route_id, ride_date, start_time, int(long_stops or 0), int(long_stop_min or 0), e, ride_date)).fetchone()
        r = _row(r)
        out.append({"email": r["email"], "ok": True, "token": r["token"], "status": r["status"],
                    "wazny_do": r["expires_at"].isoformat(timespec="minutes") if r["expires_at"] else None})
    conn.commit()
    return out


def get_valid(conn, token: str):
    """(zaproszenie, None) albo (None, powod). Nie zdradza, czy token w ogole istnial (ten sam komunikat)."""
    ensure(conn)
    if not token or len(token) < 20:
        return None, "nieprawidlowy link"
    r = conn.execute("SELECT *, (expires_at < now()) AS wygasl FROM qbot_v2.ride_invite WHERE token=%s", (token,)).fetchone()
    conn.commit()
    if not r:
        return None, "nieprawidlowy link"
    r = _row(r)
    if r.get("revoked_at"):
        return None, "link zostal wylaczony przez organizatora"
    if r.get("wygasl"):
        return None, "link wygasl"
    return r, None


def touch(conn, token: str):
    conn.execute("UPDATE qbot_v2.ride_invite SET open_count=open_count+1, last_opened_at=now() WHERE token=%s", (token,))
    conn.commit()


def set_rsvp(conn, token: str, status: str) -> bool:
    if status not in ("tak", "nie"):
        return False
    conn.execute("UPDATE qbot_v2.ride_invite SET status=%s, responded_at=now() WHERE token=%s", (status, token))
    conn.commit()
    return True


def revoke(conn, token: str) -> bool:
    ensure(conn)
    r = conn.execute("UPDATE qbot_v2.ride_invite SET revoked_at=now() WHERE token=%s AND revoked_at IS NULL RETURNING token",
                     (token,)).fetchone()
    conn.commit()
    return bool(r)


def list_invites(conn, route_id: str, ride_date: str | None = None) -> list:
    ensure(conn)
    q = ("SELECT token, email, ride_date, start_time, long_stops, long_stop_min, status, created_at, expires_at, "
         "revoked_at, responded_at, open_count, last_opened_at FROM qbot_v2.ride_invite WHERE route_id=%s")
    args = [route_id]
    if ride_date:
        q += " AND ride_date=%s"
        args.append(ride_date)
    rows = conn.execute(q + " ORDER BY ride_date, lower(email)", args).fetchall()
    conn.commit()
    out = []
    for r in rows:
        r = _row(r)
        out.append({k: (v.isoformat(timespec="minutes") if isinstance(v, _dt.datetime)
                        else v.isoformat() if isinstance(v, _dt.date) else v)
                    for k, v in r.items()})
    return out


# ---------- BIALA LISTA ----------
def _pick(d: dict, keys) -> dict:
    return {k: d.get(k) for k in keys if isinstance(d, dict) and k in d}


def _clean_name(n: str) -> str:
    return str(n or "Trasa").split(" \u00b7 ")[0].strip()[:160]


def guest_view(data: dict, invite: dict, geometry: list | None, pack: dict | None) -> dict:
    det = data.get("details") or {}
    rt, st, tm = data.get("route") or {}, data.get("start") or {}, data.get("time") or {}
    total_h = tm.get("total_h")
    meta = None
    try:
        h, m = [int(x) for x in str(invite["start_time"]).split(":")]
        mm = h * 60 + m + int(round(float(total_h) * 60))
        meta = "%02d:%02d" % ((mm // 60) % 24, mm % 60)
    except Exception:
        pass
    by = {}
    for r in ((pack or {}).get("dzien") or {}).get("ryzyka") or []:
        by[r.get("id")] = r
    risks = []
    for i, r in enumerate(((det.get("surface") or {}).get("risk") or [])):
        p = by.get("r%d" % (i + 1)) or {}
        risks.append({"a": r.get("a"), "b": r.get("b"), "km": r.get("km"), "k": r.get("k"),
                      "komentarz": p.get("komentarz"), "piach": p.get("piach"), "po_opadach": p.get("po_opadach")})
    ch = data.get("chart") or {}
    chart = {k: ch.get(k) for k in ("km_total", "ele", "ele_min", "ele_max", "weather", "eta", "wind")}
    chart["surface_cat"] = [_pick(x, ("a", "b", "k", "label")) for x in (ch.get("surface_cat") or [])]
    w = det.get("weather") or {}
    poi = det.get("poi") or {}
    return {
        "typ": "gosc", "wersja": 1,
        "trasa": {"nazwa": _clean_name(rt.get("name")), "dystans_km": rt.get("distance_km"), "przewyzszenie_m": rt.get("ascent_m"),
                  "geometria": geometry or []},
        "plan": {"data": str(invite["ride_date"]), "start": invite["start_time"],
                 "przerwy": {"liczba": invite["long_stops"], "min": invite["long_stop_min"]},
                 "meta": meta, "miejsce_startu": _pick(st, ("miejscowosc", "gmina", "powiat", "wojewodztwo")),
                 "czas": _pick(tm, ("moving_h", "total_h", "speed_gross_kmh", "speed_net_kmh", "stops_count", "stops_auto_min", "long_stops_min")),
                 "uwaga": "Plan organizatora - czasy liczone z jego tempa."},
        "wykres": chart,
        "pogoda": {"naglowek": data.get("weather_head"), "okna": w.get("windows"), "szczyt": w.get("peak"),
                   "slonce": w.get("slonce"), "ogolne": w.get("ogolne"), "etapy": w.get("etapy"), "uwagi": w.get("caveats"),
                   "prognoza_z": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="minutes")},
        "alerty": data.get("alerts") or [],
        "nawierzchnia": {"total_km": (det.get("surface") or {}).get("total_km"),
                         "udzial": (det.get("surface") or {}).get("by_cat"), "ryzyka": risks},
        "podjazdy": {"suma_w_gore_m": (det.get("climbs") or {}).get("ascent_m"),
                     "lista": [_pick(c, ("i", "a_km", "b_km", "length_m", "gain_m", "avg_pct", "max_pct", "severity", "segments"))
                               for c in ((det.get("climbs") or {}).get("list") or [])]},
        "zaopatrzenie": [{"rejon": x.get("area"), "km": x.get("q_km"),
                          "punkty": [_pick(p, ("km", "name", "cat", "miejscowosc", "hours", "open_status", "lat", "lon", "dist_m"))
                                     for p in (x.get("picks") or [])]} for x in (poi.get("resupply") or [])],
        "atrakcje": [_pick(a, ("km", "name", "desc", "miejscowosc", "lat", "lon", "dist_m"))
                     for a in ((poi.get("attractions") or {}).get("items") or [])],
        "gosc": {"email": invite["email"], "rsvp": invite["status"],
                 "wazny_do": invite["expires_at"].isoformat(timespec="minutes") if hasattr(invite.get("expires_at"), "isoformat") else invite.get("expires_at")},
    }
