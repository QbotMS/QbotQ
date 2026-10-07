"""Ubior na WYPRAWE bikepackingowa (Planer v3, 2026-10-07, v2).

Ten sam mechanizm co doradca ubioru z Analizy trasy (qbot3/routes/outfit_advisor.py): szafa z Garazu, audyt,
historia "W czym jechalem", zasady docs/OUTFIT_ADVISOR_RULES.md, 2 zestawy (spokojniejsza / szybsza) i WSZYSTKIE
kontrole i autokorekty doradcy (np. komplet marki, kieszen, kolory). Roznice dla wyprawy:
- warunki = cala wyprawa (prognoza dzien po dniu: najzimniejszy i najcieplejszy moment wszystkich dni),
- zasady nadrzedne: jeden zestaw na wszystkie dni; przy duzym rozrzucie tylko rzeczy MODULOWE; bagaz lekki,
- 'na_zmiane' (dokladane w kodzie): zapas rzeczy przy skorze (koszulka, spodenki, skarpety) - 1 komplet na 2 dni,
- zapis w qbot_v2.route_outfit (start_time='wyprawa'); Wyposazenie bierze z niego odziez (merge_packing).
"""
from __future__ import annotations

import datetime as _dt
import json
import time

from qbot3.routes import outfit_advisor as OA

MOD_SPREAD_C = 8.0

TRIP_RULES = """

## WYPRAWA BIKEPACKINGOWA (zasady nadrzedne dla tego doboru)
- Oba zestawy (spokojniejsza / szybsza) sa na CALA wyprawe (%(dni)d dni) - ta sama garderoba kazdego dnia.
  Kazda rzecz musi sie sprawdzic w CALYM zakresie warunkow: od %(tmin).0f do %(tmax).0f C (rozrzut %(rozrzut).0f C)%(deszcz)s%(wiatr)s.
- %(mod)s
- 'do_kieszeni' = to, co wozisz w torbie/kieszeni przez cala wyprawe: lekkie i pakowne, bez dublowania funkcji.
- Zapas rzeczy przy skorze na zmiane (koszulka, spodenki, skarpety) dolicza system - nie dodawaj ich do 'do_kieszeni'.
- W 'warunki_krotko' opisz warunki CALEJ wyprawy (zakres, deszcz, wiatr), nie jednej jazdy.
"""


def trip_war(days: list, hours=None, style: str = "lekko") -> dict:
    """Warunki calej wyprawy w ksztalcie 'warunki' doradcy (ten sam dobor kandydatow i kontrole)."""
    ok = [d for d in days if not d.get("brak")]
    tmins = [float(d["tmin"]) for d in ok if d.get("tmin") is not None]
    tmaxs = [float(d["tmax"]) for d in ok if d.get("tmax") is not None]
    if not tmins or not tmaxs:
        return {}
    lo, hi = min(tmins), max(tmaxs)
    rng = {"start": tmins[0], "koniec": tmaxs[-1], "min": lo, "max": hi, "srednia": round((lo + hi) / 2.0, 1)}
    rain = sum(float(d.get("precip_mm") or 0.0) for d in ok)
    wet = [d["date"] for d in ok if float(d.get("precip_mm") or 0.0) >= 0.5]
    wind = max([float(d.get("wind_max_ms") or 0.0) for d in ok] or [0.0])
    war = {"wyprawa": {"dni": len(days), "styl": style, "dzien_po_dniu": days},
           "czas_h": hours, "prognoza_powietrza": dict(rng), "na_trasie": dict(rng), "na_rowerze": dict(rng),
           "odczuwalna": {"start": tmins[0], "koniec": tmaxs[-1], "min": lo, "max": hi, "rozrzut": round(hi - lo, 1)},
           "deszcz": {"max_proc": (80 if any(float(d.get("precip_mm") or 0) >= 1.0 for d in ok) else (40 if wet else 0)),
                      "suma_mm": round(rain, 1), "okna_40proc": wet},
           "wiatr_ms": {"max": round(wind, 1), "czolowy_max": round(wind * 0.6, 1)}}
    if wind >= 5.0:
        war["wiatr_ochrona_pod_reka"] = {"okna": [d["date"] for d in ok if float(d.get("wind_max_ms") or 0) >= 5.0],
                                         "co": "kamizelka/wiatrowka pod reka"}
    return war


def advise_trip(conn, weather: dict, hours=None, style: str = "lekko", model_name: str = "") -> dict:
    """Pipeline jak OA.advise (2 zestawy + kontrole + autokorekty), warunki = cala wyprawa, zasady wyprawy w system."""
    from qgpt_client import qgpt_json
    t0 = time.perf_counter()
    days = weather.get("days_detail") or []
    war = trip_war(days, hours, style)
    if not war:
        return {"ok": False, "blad": "brak prognozy dla dni wyprawy"}
    hist = OA.historia_jazd(conn)
    sim = OA._similar_ok(hist, war)
    if sim:
        war["podobna_jazda_ok"] = {k: v for k, v in sim.items() if not k.startswith("_")}
    kand = OA.kandydaci(war, OA.recent_ids(conn), liked=OA._liked(hist), strong=sim["_ids"] if sim else None)
    if not kand:
        return {"ok": False, "blad": "brak pasujacych rzeczy w garazu"}
    sp = war["odczuwalna"]["rozrzut"]
    trip = TRIP_RULES % {
        "dni": len(days), "tmin": war["odczuwalna"]["min"], "tmax": war["odczuwalna"]["max"], "rozrzut": sp,
        "deszcz": (", opad lacznie %.1f mm" % war["deszcz"]["suma_mm"]) if war["deszcz"]["suma_mm"] > 0 else ", bez opadu w prognozie",
        "wiatr": ", wiatr do %.1f m/s" % war["wiatr_ms"]["max"],
        "mod": ("Rozrzut >= %.0f C: WYLACZNIE rzeczy modulowe (cienkie warstwy, rekawki, nogawki, kamizelka, cienka kurtka), "
                "NIE grube ocieplane rzeczy na caly dzien." % MOD_SPREAD_C) if sp >= MOD_SPREAD_C else
               "Rozrzut niewielki: zestaw moze byc prosty, ale bez rzeczy przydatnych tylko jednego dnia."}
    system = OA._rules_text() + trip + OA.SYS_FORMAT
    o, err, fix = None, None, ""
    for attempt in range(2):
        try:
            o = qgpt_json(OA._prompt(war, kand, hist, []) + fix, system=system, max_tokens=5000, temperature=0.5)
        except Exception as e:  # noqa
            o, err = None, "wyjatek: " + str(e)[:120]
        OA._dedupe(o, war)
        err = OA._valid(o, kand, war)
        if not err and attempt < 1:
            err = OA._style(o)
        if not err:
            ch = OA._checks(o, kand, war)
            if ch and attempt < 1:
                err = "; ".join(ch)
        if not err:
            break
        fix = "\n\nPOPRZEDNIA ODPOWIEDZ ODRZUCONA: " + err + ". Popraw i zwroc caly JSON."
    if err:
        return {"ok": False, "blad": err, "warunki": war}
    fx = OA._autofix(o, kand, war) + OA._pocket_trim(o, kand, war)
    if OA._valid(o, kand, war):
        return {"ok": False, "blad": "autokorekta zepsula zestaw", "warunki": war}
    o["_kontrola_uwagi"] = ["poprawione automatycznie: " + f for f in fx] + OA._checks(o, kand, war, final=True)
    if fx:
        note = OA._retext(o, kand, fx)
        if note:
            o["_kontrola_uwagi"].append(note)
    ids = {it["id"]: it for v in kand.values() for it in v}
    spare = max(1, len(days) // 2) if len(days) >= 2 else 0
    for z in o["zestawy"]:
        for key in ("rzeczy", "do_kieszeni"):
            for it in z.get(key) or []:
                c = ids[int(it["id"])]
                it.update({"id": c["id"], "nazwa": c["nazwa"], "kategoria": c["kategoria"], "warstwa": c["warstwa"], "kolor": c["kolor"]})
                zm = []
                for j in (it.get("zamienniki") if isinstance(it.get("zamienniki"), list) else [])[:2]:
                    try:
                        cj = ids.get(int(j))
                    except Exception:
                        cj = None
                    if cj and cj["warstwa"] == c["warstwa"] and cj["id"] != c["id"]:
                        zm.append({"id": cj["id"], "nazwa": cj["nazwa"], "kolor": cj["kolor"]})
                it["zamienniki"] = zm
        z["rzeczy"].sort(key=lambda x: OA.LAYER_KEYS.index(x["warstwa"]))
        z["kolory"] = OA._kolory(z["rzeczy"])
        z["na_zmiane"] = [{"id": it["id"], "nazwa": it["nazwa"], "ile": spare, "warstwa": it["warstwa"]}
                          for it in z["rzeczy"] if spare and it["warstwa"] in ("koszulka", "spodenki", "skarpety")]
    o["zestawy"].sort(key=lambda z: 0 if z.get("tempo") == "spokojniejsza" else 1)
    return {"ok": True, "wersja": 2, "model": model_name, "czas_s": round(time.perf_counter() - t0, 1),
            "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "warunki": war, "warunki_krotko": o.get("warunki_krotko"), "z_historii": o.get("z_historii"),
            "zestawy": o["zestawy"], "kandydatow": sum(len(v) for v in kand.values()), "jazd_w_historii": len(hist),
            "kontrola_uwagi": o.get("_kontrola_uwagi") or []}


def save(conn, route_id, start, prop):
    OA.ensure(conn)
    conn.execute("INSERT INTO qbot_v2.route_outfit (route_id, ride_date, start_time, long_stops, long_stop_min, model, proposal) "
                 "VALUES (%s, %s, 'wyprawa', 0, 0, %s, %s::jsonb)", (route_id, start, prop.get("model"), json.dumps(prop, ensure_ascii=False)))
    conn.commit()


def _prop(r):
    if not r:
        return None
    p = r["proposal"] if isinstance(r, dict) else r[0]
    return json.loads(p) if isinstance(p, str) else p


def load(conn, route_id, start):
    OA.ensure(conn)
    return _prop(conn.execute("SELECT proposal FROM qbot_v2.route_outfit WHERE route_id=%s AND ride_date=%s AND start_time='wyprawa' "
                              "ORDER BY created_at DESC LIMIT 1", (route_id, start)).fetchone())


def load_any(conn, route_id):
    """Najnowszy dobor ubioru wyprawy dla trasy (dowolna data) - dla Wyposazenia."""
    OA.ensure(conn)
    return _prop(conn.execute("SELECT proposal FROM qbot_v2.route_outfit WHERE route_id=%s AND start_time='wyprawa' "
                              "ORDER BY created_at DESC LIMIT 1", (route_id,)).fetchone())


def merge_packing(groups: list, prop: dict, which: int = 0) -> list:
    """Wyposazenie (decyzja Michala 2026-10-07): pozycje generatora ZOSTAJA (typ rzeczy), a rzeczy z Ubioru (zestaw A)
    ustawiaja wybor 'z garazu' (gear_id) przy pozycjach tej samej kategorii Garazu - pierwsza wolna pozycja danej
    kategorii dostaje rzecz z zestawu; reszte (np. zapas na zmiane) wybierasz sam."""
    zs = (prop or {}).get("zestawy") or []
    if not zs or (prop.get("wersja") or 1) < 2:
        return groups
    z = zs[min(which, len(zs) - 1)]
    pool = {}
    for it in (z.get("rzeczy") or []) + (z.get("do_kieszeni") or []):
        if it.get("kategoria") and it.get("id") is not None:
            pool.setdefault(str(it["kategoria"]).strip().lower(), []).append(it)
    out = []
    for g in groups or []:
        g2 = dict(g); items = []
        for it in g.get("items") or []:
            it2 = dict(it)
            cat = str(it2.get("garage_category") or "").strip().lower()
            if cat and pool.get(cat) and not it2.get("gear_id"):
                pick = pool[cat].pop(0)
                it2["gear_id"] = int(pick["id"])
                it2["reason"] = ((it2.get("reason") or "") + " · z Ubioru na wyprawę: " + str(pick.get("nazwa") or "")).strip(" ·")
            items.append(it2)
        g2["items"] = items
        out.append(g2)
    return out
