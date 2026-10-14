"""Pogoda dla Alberta: krotkie analizy tekstowe (po polsku, wiatr m/s, daty DD.MM) z modulow strony Pogoda.
Narzedzia w qbot3/tool_registry.py: weather_now, ride_window, ride_where, weather_skill (tylko odczyt). Dok.: docs/POGODA_RADAR.md"""
from __future__ import annotations

import datetime as dt
import os

STRONA = "albert.cytr.us/pogoda.html"


def _pl(x) -> str:
    return "–" if x is None else str(round(x, 1)).replace(".", ",")


def _ddmm(iso: str) -> str:
    return f"{iso[8:10]}.{iso[5:7]}"


def _cur():
    os.environ.setdefault("QBOT3_ENABLED", "1")
    from fitmodel.api import _db_connect
    from psycopg.rows import dict_row
    c = _db_connect()
    return c, c.cursor(row_factory=dict_row)


def _point(cur, lat, lon):
    if lat is not None and lon is not None:
        return float(lat), float(lon), "wskazany punkt"
    import qbot_pogoda as PG
    h = PG.home(cur)
    if not h:
        return 52.23, 21.01, "Warszawa (brak punktu domu)"
    return h["lat"], h["lon"], "dom"


def weather_now(lat=None, lon=None) -> dict:
    import qbot_pogoda as PG
    import qbot_radar as RAD
    conn, cur = _cur()
    try:
        la, lo, gdzie = _point(cur, lat, lon)
    finally:
        conn.close()
    lines = [f"Pogoda — {gdzie} ({_pl(la)}, {_pl(lo)})."]
    n = RAD.nowcast_point(la, lo, lead_max=60)
    if n.get("status") == "OK":
        r = n.get("ruch")
        lines.append(f"Radar ({n['najnowsza']}, {n['opoznienie_min']} min temu): {n['werdykt']}"
                     + (f" Opad przesuwa się z {r['skad']} na {r['dokad']}, ok. {round(r['kmh'])} km/h." if r else ""))
    m = PG.model_point(la, lo, hours=12)
    if m.get("status") == "OK":
        nxt = next((p for p in m["punkty"][1:] if p["mmh"] >= 0.5), None)
        lines.append(f"Dalej wg modelu ({m['model']}): " + (f"kolejny opad ok. {nxt['t']} ({_pl(nxt['mmh'])} mm/h)." if nxt else "sucho w najbliższych 12 h."))
    w = PG.conditions_point(la, lo, hours=12)
    if w.get("status") == "OK":
        fut = [h for h in w["godziny"] if not h["przeszlosc"]]
        if fut:
            h = fut[0]
            lines.append(f"Teraz: {_pl(h['temp'])}°C (odczuwalna {_pl(h['odcz'])}°C), wiatr {_pl(h['wiatr'])} m/s z {h['skad']}, porywy {_pl(h['porywy'])} m/s; "
                         f"nawierzchnia {['sucha', 'wilgotna', 'mokra/błoto'][h['nawierzchnia']]}"
                         + (", ryzyko oblodzenia" if h["lod"] >= 2 else "") + (", mgła" if h["mgla"] == 2 else "") + ".")
            t = [x["temp"] for x in fut if x["temp"] is not None]; g = [x["porywy"] for x in fut if x["porywy"] is not None]
            lines.append(f"Najbliższe 12 h: {_pl(min(t))}…{_pl(max(t))}°C, porywy do {_pl(max(g))} m/s, opad {_pl(sum((x['opad'] or 0) for x in fut))} mm.")
    lines.append(f"Mapa radaru i prognozy: {STRONA}")
    return {"status": "OK", "analysis": "\n".join(lines)}


def ride_window(ride_id=None, dzien=None, start=None, dur=None, lat=None, lon=None) -> dict:
    import qbot_pogoda_okno as PO
    conn, cur = _cur()
    try:
        la, lo, gdzie = _point(cur, lat, lon)
        jazdy = PO.rides(cur)
        r = next((x for x in jazdy if ride_id is not None and x["id"] == int(ride_id)), None)
        if r is None and dzien and start:
            day, st, d, rid, nazwa = dt.date.fromisoformat(dzien), start[:5], int(dur or 60), None, "jazda"
        else:
            r = r or (jazdy[0] if jazdy else None)
            if not r:
                return {"status": "OK", "analysis": "Brak zaplanowanych jazd rowerowych w Trenerze na 3 dni. Podaj dzień, godzinę startu i czas jazdy."}
            day, st, d, rid, nazwa = dt.date.fromisoformat(r["dzien"]), r["start"], r["czas_min"], r["id"], r["nazwa"]
        w = PO.window(cur, la, lo, day, st, d, ride_id=rid)
    finally:
        conn.close()
    p, best = w["plan"], w["najlepszy"]
    f = lambda x: f"{x['start']}–{x['koniec']}: {x['ocena']}/100 ({', '.join(x['uwagi'])}; porywy {_pl(x['poryw'])} m/s)"
    lines = [f"Okno jazdy — {nazwa}, {_ddmm(w['dzien'])} {st}, {d} min ({gdzie}). Okna na rower (Trener): "
             + ", ".join(f"{a}–{b}" for a, b in w["okna_rower"]) + (f"; słońce {w['slonce'][0]}–{w['slonce'][1]}." if w["slonce"] else ".")]
    if p:
        lines.append("Plan " + f(p) + ".")
    if p and best and best["ocena"] > p["ocena"] + 10:
        lines.append(f"Lepiej przesunąć na {best['start']} — " + f(best) + ".")
    elif p:
        lines.append("Plan jest dobry, nie ma po co przesuwać." if p["ocena"] >= 80 else "Żadna godzina w Twoich oknach nie jest wyraźnie lepsza.")
    for k, lab in (("najlepszy_wczesniej", "Wcześniej"), ("najlepszy_pozniej", "Później")):
        if w.get(k):
            lines.append(f"{lab}: " + f(w[k]) + ".")
    lines.append(f"Szczegóły i siatka startów: {STRONA} (◷). Źródła: {w['zrodla']}.")
    return {"status": "OK", "analysis": "\n".join(lines)}


def ride_where(dzien=None, km=100, lat=None, lon=None) -> dict:
    import qbot_pogoda_map as PM
    import qbot_trener_engine as E
    from zoneinfo import ZoneInfo
    m = PM.meta()
    if m.get("status") != "OK":
        return {"status": "OK", "analysis": "Mapa modelu jest w trakcie przeliczania — spróbuj za kilka minut."}
    tz = ZoneInfo("Europe/Warsaw"); today = dt.datetime.now(tz).date()
    conn, cur = _cur()
    try:
        la, lo, gdzie = _point(cur, lat, lon)
        if dzien:
            day = dt.date.fromisoformat(dzien)
        else:
            day = today + dt.timedelta(days=(5 - today.weekday()) % 7 or 0)
        ctx = E.build_context(cur, "admin", E.monday(day), today)
        win = E.day_info(ctx, day)["win"].get("rower") or [E.DEFAULT_WIN]
    finally:
        conn.close()
    a_h = max(0, (min(x[0] for x in win) + 59) // 60); b_h = min(24, max(x[1] for x in win) // 60)
    r = PM.ocena_dnia(day, a_h, b_h)
    if r.get("status") != "OK":
        return {"status": "OK", "analysis": f"{_ddmm(day.isoformat())}: {r.get('error') or r.get('status')} (prognoza mapy sięga ok. 5 dni)."}
    km = int(km) if km else None
    rej = PM.rejony(day, a_h, b_h, la, lo, km if km and km > 0 else None, n=5)
    lines = [f"Gdzie jechać {_ddmm(day.isoformat())} ({a_h:02d}–{b_h:02d}), " + (f"do {km} km od: {gdzie}." if km else f"bez limitu, od: {gdzie}.")
             + f" Polska średnio {r['polska']['srednia']}/100, dobre warunki na {round(r['polska']['udzial_dobrych'] * 100)}% obszaru."]
    for i, x in enumerate(rej, 1):
        lines.append(f"{i}. {x['nazwa']} ({x.get('km', '?')} km) — {x['ocena']}/100: opad {_pl(x['opad_mm'])} mm, wiatr {_pl(x['wiatr_ms'])} m/s, "
                     f"porywy {_pl(x['poryw_ms'])} m/s, {_pl(x['temp_sr'])}°C; podobnie w promieniu {'ponad 80' if x['zasieg_km'] >= 80 else x['zasieg_km']} km.")
    lines.append(f"Prognoza na 3–5 dni ma mniejszą trafność niż na jutro. Mapa ocen: {STRONA} (★). Model: {r['model']}, przebieg {r['run'][8:10]} UTC.")
    return {"status": "OK", "analysis": "\n".join(lines)}


def weather_skill() -> dict:
    import qbot_eps_verif as EV
    import qbot_pogoda_verif as PV
    import qbot_radar_verif as RV
    conn, cur = _cur()
    try:
        la, lo, _ = _point(cur, None, None)
        sc = PV.score_cached(cur, dni=60, lat=la, lon=lo)
        rv = RV.summary(cur, 14); ev = EV.summary(cur, 14)
    finally:
        conn.close()
    lines = ["Sprawdzalność prognoz (vs pomiary IMGW i radar):"]
    if sc.get("status") == "OK":
        d1 = sorted([w for w in sc["wyniki"] if w["wyprz_dni"] == 1 and w["temp_mae"] is not None], key=lambda w: w["temp_mae"])
        lines.append("Na jutro, u Ciebie (stacje do 100 km), błąd temperatury / wiatru: " + "; ".join(
            f"{w['opis']} {_pl(w['temp_mae'])}°C / {_pl(w['wiatr_mae'])} m/s" for w in d1) + ".")
        op = max((w for w in sc["wyniki"] if w["wyprz_dni"] == 1 and w["opad_trafnosc"] is not None), key=lambda w: w["opad_trafnosc"], default=None)
        if op:
            lines.append(f"Opad (okresy 6 h): najlepiej trafia {op['opis']} — {round(op['opad_trafnosc'] * 100)}%.")
    if rv.get("wyniki"):
        lines.append("Radar (przesunięcie obrazu), trafność: " + ", ".join(f"{w['lead_min']} min {round((w['csi'] or 0) * 100)}%" for w in rv["wyniki"])
                     + (f"; horyzont radaru {rv['horyzont_min']} min." if rv.get("horyzont_min") else "."))
    if ev.get("status") == "OK":
        lines.append("Szansa opadu z zespołu (BSS, >0 = lepsza od średniej): " + ", ".join(f"{g['wyprzedzenie_h']} h {g['bss']}" for g in ev["grupy"]) + ".")
    else:
        lines.append("Szansa opadu z zespołu: dane dopiero się zbierają.")
    lines.append(f"Modele do prognoz dobierane są automatycznie wg tych wyników. Tabele i wykresy: {STRONA} (✓).")
    return {"status": "OK", "analysis": "\n".join(lines)}
