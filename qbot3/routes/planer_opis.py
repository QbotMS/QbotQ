#!/usr/bin/env python3
"""Generator opisu-tla trasy dla Planera wyprawy (Etap 2).

Zrodla (wszystko po AKTYWNEJ wersji route_base_id, status='active'):
- POI:        qbot_v2.route_poi_layer  (miasta + wyselekcjonowane atrakcje)
- krajobraz:  qbot_v2.route_surface_context.dominant_pl  (las/uprawy/zabudowa/trawy)
- podjazdy:   qbot_v2.route_climb_events
- nawierzchnia %: plik spine_<route_id>.json (paved/unpaved/unknown, wazone 50 m)

Fakty (liczby, nazwy) pochodza WYLACZNIE z bazy. LLM tylko uklada je w prose i
grupuje po odcinkach - nie wolno mu dodawac wlasnych obiektow ani liczb.

Cache: qbot_v2.planer_route_opis, invalidacja po geometry_hash z route_base.
"""
import json
import os
import re
from pathlib import Path

_SPINE_DIR = Path("/opt/qbot/web/public/data")

# Atrakcje warte wzmianki (whitelist po nazwie)
_BIG = re.compile(
    r"zamek|pa\u0142ac|dw[o\u00f3]r|klasztor|opactwo|bazylika|kolegiata|katedra|"
    r"ratusz|rynek|muzeum|skansen|twierdza|forteca|arboretum|ogr[o\u00f3]d dendro|"
    r"sanktuarium|park krajobraz|zabytkow|wie\u017ca piastowska|kompleks parkowo|"
    r"zespó\u0142 pa\u0142ac|cytadela|kaplica zamkowa",
    re.I,
)
# Szum do odrzucenia nawet gdy zawiera slowo z whitelist
_NOISE = re.compile(
    r"\u0142owisko|zb[o\u00f3]r|\u015bwiadk|jehow|pamparampam|sala kr[o\u00f3]lestwa|"
    r"kreatywnie|si\u0142ownia|pizzeria|bar\b|fontann|taras|wozownia|oficyna|"
    r"brama|dawny budynek|budynek gospodarczy|budynek mieszkalny|wie\u017ca ci\u015bnie|"
    r"dworzec|kamienice|gospodarstwo|agrotury|stajnie|folwark",
    re.I,
)

_PL = {"las": "lasy", "uprawy": "pola uprawne", "zabudowa": "tereny zabudowane",
       "trawy": "\u0142\u0105ki i pastwiska"}


def _db():
    import sys
    sys.path.insert(0, "/opt/qbot/app")
    os.environ.setdefault("QBOT3_ENABLED", "1")
    from fitmodel.api import _db_connect
    return _db_connect()


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _resolve_base(conn, route_id):
    """Aktywna wersja trasy; fallback: najnowsza jesli brak 'active'."""
    row = conn.execute(
        "SELECT route_base_id, route_version_key, geometry_hash, distance_m, status "
        "FROM qbot_v2.route_base WHERE route_id=%s "
        "ORDER BY (status='active') DESC, route_updated_at DESC NULLS LAST LIMIT 1",
        (route_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "base_id": row[0], "version_key": row[1], "geometry_hash": row[2],
        "distance_km": round(_f(row[3]) / 1000.0, 1), "status": row[4],
    }


def _spine_surface(route_id):
    """% nawierzchni + ascent ze spine (paved/unpaved/unknown)."""
    p = _SPINE_DIR / ("spine_%s.json" % route_id)
    if not p.exists():
        return None
    try:
        sp = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    pts = sp if isinstance(sp, list) else (sp.get("points") or sp.get("spine") or [])
    if not pts:
        return None
    cnt = {}
    ascent = 0.0
    for pt in pts:
        s = (pt.get("s") or "unknown")
        cnt[s] = cnt.get(s, 0) + 1
        dg = pt.get("g") or 0
        if dg > 0:
            ascent += dg
    tot = sum(cnt.values()) or 1
    grp = {"asfalt": 0, "nieutwardzone": 0, "nieznane": 0}
    for k, v in cnt.items():
        kl = (k or "").lower()
        if kl in ("paved", "asphalt", "asfalt", "concrete", "paving_stones"):
            grp["asfalt"] += v
        elif kl in ("unknown", "nieznane", ""):
            grp["nieznane"] += v
        else:
            grp["nieutwardzone"] += v
    return {
        "asfalt_pct": round(100.0 * grp["asfalt"] / tot),
        "nieutwardzone_pct": round(100.0 * grp["nieutwardzone"] / tot),
        "nieznane_pct": round(100.0 * grp["nieznane"] / tot),
        "ascent_m": round(ascent),
    }


def _landscape(conn, base_id):
    rows = conn.execute(
        "SELECT dominant_pl, sum((km_to-km_from)) FROM qbot_v2.route_surface_context "
        "WHERE route_base_id=%s AND dominant_pl IS NOT NULL GROUP BY 1 ORDER BY 2 DESC",
        (base_id,),
    ).fetchall()
    tot = sum(_f(r[1]) for r in rows) or 1.0
    out = []
    for r in rows:
        out.append({"label": _PL.get(r[0], r[0]), "pct": round(100.0 * _f(r[1]) / tot)})
    return out


def _climbs(conn, base_id):
    agg = conn.execute(
        "SELECT count(*), coalesce(max(elevation_gain_m),0), coalesce(max(avg_gradient_pct),0) "
        "FROM qbot_v2.route_climb_events WHERE route_base_id=%s", (base_id,),
    ).fetchone()
    top = conn.execute(
        "SELECT round((start_m/1000.0)::numeric,1), round((end_m/1000.0)::numeric,1), "
        "round(elevation_gain_m::numeric), round(avg_gradient_pct::numeric,1) "
        "FROM qbot_v2.route_climb_events WHERE route_base_id=%s "
        "ORDER BY elevation_gain_m DESC LIMIT 5", (base_id,),
    ).fetchall()
    return {
        "n": int(agg[0]), "max_gain_m": round(_f(agg[1])), "max_grad_pct": round(_f(agg[2]), 1),
        "top": [{"km_from": _f(t[0]), "km_to": _f(t[1]), "gain_m": round(_f(t[2])),
                 "grad_pct": _f(t[3])} for t in top],
    }


def _pois(conn, base_id):
    rows = conn.execute(
        "SELECT name, category, km_on_route FROM qbot_v2.route_poi_layer "
        "WHERE route_base_id=%s AND category IN ('town','attraction') "
        "AND (category='town' OR distance_from_route_m IS NULL OR distance_from_route_m <= 2000) "
        "ORDER BY km_on_route", (base_id,),
    ).fetchall()
    big = []
    for r in rows:
        nm = r[0] or ""
        if r[1] == "attraction" and _BIG.search(nm) and not _NOISE.search(nm):
            big.append({"name": nm, "km": round(_f(r[2]), 1)})
    # deduplikacja po (nazwa) - te same obiekty potrafia sie powtarzac
    seen = set()
    uniq = []
    for b in big:
        key = b["name"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(b)
    return uniq


def _facts_block(base, surf, land, climb, pois):
    lines = [
        "DYSTANS: %.1f km" % base["distance_km"],
    ]
    if surf:
        lines.append("NAWIERZCHNIA: asfalt %d%%, nieutwardzone %d%%, nieokreslone %d%%"
                     % (surf["asfalt_pct"], surf["nieutwardzone_pct"], surf["nieznane_pct"]))
        lines.append("PRZEWYZSZENIE_CALKOWITE: %d m" % surf["ascent_m"])
    if climb and climb["n"]:
        lines.append("PODJAZDY: %d szt., najwiekszy +%d m przy nachyleniu do %.1f%%"
                     % (climb["n"], climb["max_gain_m"], climb["max_grad_pct"]))
        tp = "; ".join("%.0f-%.0f km (+%d m)" % (t["km_from"], t["km_to"], t["gain_m"])
                       for t in climb["top"][:3])
        lines.append("NAJWIEKSZE_PODJAZDY: " + tp)
    if land:
        lines.append("KRAJOBRAZ: " + ", ".join("%s %d%%" % (l["label"], l["pct"]) for l in land))
    lines.append("")
    lines.append("ZABYTKI I MIEJSCA (nazwa @ km od startu) - UZYWAJ WYLACZNIE TYCH NAZW:")
    for p in pois:
        lines.append("  - %s @ %.1f km" % (p["name"], p["km"]))
    return "\n".join(lines)


_SYS = (
    "Jestes przewodnikiem rowerowym. Piszesz po polsku, rzeczowo i barwnie, ale bez "
    "przesady. Opisujesz TLO krajoznawcze wielodniowej trasy gravelowej. "
    "ZELAZNE ZASADY: (1) uzywaj wylacznie nazw miejsc i obiektow podanych w danych - "
    "nie dodawaj zadnych wlasnych zabytkow, miast ani faktow historycznych, ktorych "
    "nie ma w danych; (2) liczby (km, %, metry) przepisuj z danych bez zmian; "
    "(3) jesli czegos nie ma w danych - nie wymyslaj. Zwracasz WYLACZNIE JSON."
)


def _prompt(facts):
    return (
        "Na podstawie ponizszych danych trasy napisz opis-tlo w formacie JSON.\n\n"
        + facts
        + "\n\nZWROC DOKLADNIE taki JSON (bez markdown, bez komentarzy):\n"
        "{\n"
        '  "intro": "jeden akapit (3-5 zdan) o regionie i charakterze calej wyprawy",\n'
        '  "charakterystyka": ["3-5 krotkich punktow: ukszatlowanie terenu, '
        'nawierzchnia, krajobraz, gorzysty fragment jesli jest"],\n'
        '  "top_atrakcje": ["dokladne nazwy do 10 najwazniejszych obiektow z listy"]\n'
        "}\n"
        "Do top_atrakcje wybierz DOKLADNIE do 10 najwazniejszych obiektow (perly: "
        "zamki, palace, klasztory, sanktuaria, rynki starych miast, wazne muzea). "
        "Przepisz ich nazwy DOKLADNIE tak jak w danych, w kolejnosci wg km. "
        "Nie dodawaj obiektow spoza listy, nie wymyslaj nazw. "
        "KLUCZOWE: rozloz wybor po CALEJ trasie - maksymalnie 1-2 obiekty z jednego miasta lub okolicy, tak aby 10 pozycji obejmowalo poczatek, srodek i koniec trasy (az do konca km), a nie tylko jej poczatek."
    )


def build_opis(route_id, rebuild=False, model_label="qgpt"):
    """Zwraca dict {intro, charakterystyka[], przebieg[], generated_at, geom_hash}.
    Uzywa cache (planer_route_opis) o ile geometry_hash sie zgadza i nie rebuild.
    """
    conn = _db()
    try:
        base = _resolve_base(conn, route_id)
        if not base:
            return {"error": "route_not_found", "route_id": route_id}
        gh = base["geometry_hash"]

        if not rebuild:
            cur = conn.execute(
                "SELECT opis_json, geometry_hash, generated_at::text "
                "FROM qbot_v2.planer_route_opis WHERE route_id=%s", (route_id,),
            ).fetchone()
            if cur and cur[1] == gh and cur[0]:
                data = cur[0] if isinstance(cur[0], dict) else json.loads(cur[0])
                data["cached"] = True
                data["generated_at"] = cur[2]
                data["geom_hash"] = gh
                return data

        surf = _spine_surface(route_id)
        land = _landscape(conn, base["base_id"])
        climb = _climbs(conn, base["base_id"])
        pois = _pois(conn, base["base_id"])
        facts = _facts_block(base, surf, land, climb, pois)

        from qgpt_client import qgpt_json
        data = qgpt_json(_prompt(facts), system=_SYS, max_tokens=3000, temperature=0.3)
        if not isinstance(data, dict) or "intro" not in data:
            return {"error": "llm_bad_output", "raw": str(data)[:400]}

        data.setdefault("charakterystyka", [])
        by_name = {}
        for _p in pois:
            by_name[_p["name"].strip().lower()] = _p["km"]
        picked, seen = [], set()
        for nm in (data.get("top_atrakcje") or []):
            key = str(nm).strip().lower()
            if key in by_name and key not in seen:
                seen.add(key)
                picked.append({"name": str(nm).strip(), "km": by_name[key]})
        picked.sort(key=lambda x: x["km"])
        data["top_atrakcje"] = picked[:10]
        data.pop("przebieg", None)
        conn.execute(
            "INSERT INTO qbot_v2.planer_route_opis "
            "(route_id, route_base_id, geometry_hash, opis_json, model) "
            "VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT (route_id) DO UPDATE SET "
            "route_base_id=EXCLUDED.route_base_id, geometry_hash=EXCLUDED.geometry_hash, "
            "opis_json=EXCLUDED.opis_json, model=EXCLUDED.model, generated_at=now()",
            (route_id, base["base_id"], gh, json.dumps(data, ensure_ascii=False), model_label),
        )
        conn.commit()
        data["cached"] = False
        data["geom_hash"] = gh
        return data
    finally:
        conn.close()


# =========================== OPIS WG PODZIALU NA DNI ===========================

def _towns(conn, base_id):
    rows = conn.execute(
        "SELECT name, km_on_route FROM qbot_v2.route_poi_layer "
        "WHERE route_base_id=%s AND category='town' ORDER BY km_on_route", (base_id,),
    ).fetchall()
    return [{"name": r[0], "km": round(_f(r[1]), 1)} for r in rows if r[0]]


def _nearest_town(towns, km):
    best, bd = None, 1e18
    for t in towns:
        d = abs(t["km"] - km)
        if d < bd:
            bd = d
            best = t
    return best["name"] if best else None


def _spine_range(route_id, a, b):
    """Nawierzchnia % + przewyzszenie dla zakresu km [a, b]."""
    p = _SPINE_DIR / ("spine_%s.json" % route_id)
    if not p.exists():
        return None
    try:
        sp = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    pts = sp if isinstance(sp, list) else (sp.get("spine") or sp.get("points") or [])
    cnt = {"asfalt": 0, "nieutwardzone": 0, "nieznane": 0}
    asc = 0.0
    n = 0
    for pt in pts:
        k = pt.get("k")
        if k is None or k < a or k > b:
            continue
        n += 1
        sv = (pt.get("s") or "").lower()
        if sv in ("paved", "asphalt", "concrete", "paving_stones"):
            cnt["asfalt"] += 1
        elif sv in ("", "unknown", "nieznane"):
            cnt["nieznane"] += 1
        else:
            cnt["nieutwardzone"] += 1
        g = pt.get("g") or 0
        if g > 0:
            asc += g
    tot = sum(cnt.values()) or 1
    return {
        "asfalt_pct": round(100.0 * cnt["asfalt"] / tot),
        "nieutwardzone_pct": round(100.0 * cnt["nieutwardzone"] / tot),
        "nieznane_pct": round(100.0 * cnt["nieznane"] / tot),
        "ascent_m": round(asc), "n": n,
    }


_SYS_DZIEN = (
    "Jestes przewodnikiem rowerowym. Opisujesz JEDEN dzien wielodniowej wyprawy "
    "gravelowej po polsku, zwiezle i rzeczowo. ZASADY: uzywaj wylacznie nazw "
    "obiektow podanych w danych (nie dodawaj wlasnych), liczby przepisuj bez zmian, "
    "nie wymyslaj. Zwracasz WYLACZNIE JSON."
)


def _prompt_dzien(idx, a, b, surf, seg_pois, nocleg, is_last):
    lines = ["DZIEN %d: km %.1f - %.1f (dystans %.1f km)" % (idx + 1, a, b, b - a)]
    if surf:
        lines.append("NAWIERZCHNIA: asfalt %d%%, nieutwardzone %d%%, nieokreslone %d%%"
                     % (surf["asfalt_pct"], surf["nieutwardzone_pct"], surf["nieznane_pct"]))
        lines.append("PRZEWYZSZENIE: %d m" % surf["ascent_m"])
    if nocleg:
        lines.append("NOCLEG na koniec dnia w okolicy: %s" % nocleg)
    elif is_last:
        lines.append("To ostatni dzien - meta trasy, bez noclegu.")
    lines.append("OBIEKTY NA TRASIE DNIA (nazwa @ km) - UZYWAJ TYLKO TYCH:")
    if seg_pois:
        for p in seg_pois:
            lines.append("  - %s @ %.1f km" % (p["name"], p["km"]))
    else:
        lines.append("  (brak wyroznionych obiektow na tym odcinku)")
    facts = "\n".join(lines)
    return (
        facts + "\n\nZWROC DOKLADNIE taki JSON (bez markdown):\n"
        "{\n"
        '  "intro": "2-3 zdania o charakterze tego dnia: teren, nawierzchnia, klimat odcinka",\n'
        '  "punkty": ["najwazniejsze miejsca dnia z listy, po jednym zwiezlym zdaniu; max 4"]\n'
        "}\n"
        "Jesli brak obiektow - daj pusta liste punktow, a intro oprzyj na terenie i nawierzchni."
    )


def build_opis_dni(route_id, cuts, rebuild=False, model_label="qgpt"):
    """Opis LLM per dzien wg granic 'cuts' (lista km cięć). Cache po (route_id, cuts_hash)."""
    import hashlib
    conn = _db()
    try:
        base = _resolve_base(conn, route_id)
        if not base:
            return {"error": "route_not_found", "route_id": route_id}
        total = base["distance_km"]
        cuts = sorted(_f(c) for c in (cuts or []) if c is not None)
        bounds = [0.0] + cuts + [total]
        days = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
        ch = hashlib.md5(("|".join("%.1f" % c for c in cuts)).encode()).hexdigest()[:16]

        if not rebuild:
            cur = conn.execute(
                "SELECT dni_json FROM qbot_v2.planer_route_opis_dni "
                "WHERE route_id=%s AND cuts_hash=%s", (route_id, ch)).fetchone()
            if cur and cur[0]:
                dni = cur[0] if isinstance(cur[0], list) else json.loads(cur[0])
                return {"status": "OK", "cached": True, "route_id": route_id,
                        "cuts": cuts, "dni": dni}

        pois = _pois(conn, base["base_id"])
        towns = _towns(conn, base["base_id"])
        from qgpt_client import qgpt_json
        out = []
        for i, (a, b) in enumerate(days):
            seg = [p for p in pois if a <= p["km"] < b]
            if not seg:
                seg = [p for p in pois if a <= p["km"] <= b]
            surf = _spine_range(route_id, a, b)
            is_last = (i == len(days) - 1)
            nocleg = None if is_last else _nearest_town(towns, b)
            try:
                opis = qgpt_json(_prompt_dzien(i, a, b, surf, seg, nocleg, is_last),
                                 system=_SYS_DZIEN, max_tokens=900, temperature=0.3)
            except Exception as e:
                opis = {"intro": "", "punkty": [], "error": str(e)[:120]}
            if not isinstance(opis, dict):
                opis = {"intro": "", "punkty": []}
            opis.setdefault("punkty", [])
            out.append({
                "dzien": i + 1, "km_from": round(a, 1), "km_to": round(b, 1),
                "dystans_km": round(b - a, 1), "nocleg": nocleg,
                "nawierzchnia": surf, "opis": opis,
            })

        conn.execute(
            "INSERT INTO qbot_v2.planer_route_opis_dni "
            "(route_id, cuts_hash, route_base_id, cuts_json, dni_json, model) "
            "VALUES (%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (route_id, cuts_hash) DO UPDATE SET "
            "route_base_id=EXCLUDED.route_base_id, cuts_json=EXCLUDED.cuts_json, "
            "dni_json=EXCLUDED.dni_json, model=EXCLUDED.model, generated_at=now()",
            (route_id, ch, base["base_id"], json.dumps(cuts),
             json.dumps(out, ensure_ascii=False), model_label))
        conn.commit()
        return {"status": "OK", "cached": False, "route_id": route_id, "cuts": cuts, "dni": out}
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    rid = sys.argv[1] if len(sys.argv) > 1 else "komoot-3088315688"
    rebuild = "--rebuild" in sys.argv
    dni_arg = None
    for a in sys.argv:
        if a.startswith("--dni="):
            dni_arg = [float(x) for x in a.split("=", 1)[1].split(",") if x.strip()]
    if dni_arg is not None:
        print(json.dumps(build_opis_dni(rid, dni_arg, rebuild=rebuild), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(build_opis(rid, rebuild=rebuild), ensure_ascii=False, indent=2))
