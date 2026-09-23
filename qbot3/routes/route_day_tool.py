"""[E2e] Narzedzie Alberta: PLAN DNIA JAZDY z tego, co juz policzone - BEZ uruchamiania AI.

Sklada: warstwa planu (qbot_web._build_report_data ai=False, day_table=True) + pakiet dnia (route_day_pack)
+ prognoza formy (fitmodel.form_projection, w danych planu) + ostatni dobor ubioru (route_outfit)
+ opis trasy (route_intro) + zaproszenia (ride_invite). Domyslny wybor: najblizsza jazda z kalendarza
(wydarzenie z trasa, z godzina), potem najblizsza data z pakietem dnia.
"""
from __future__ import annotations

import datetime as _dt


def _pick_default(conn, route_id=None, date=None):
    """-> (route_id, date, time, zrodlo)"""
    today = _dt.date.today()
    q = ("SELECT r.route_id, r.day, e.at_time, e.title FROM qbot_v2.calendar_day_route r JOIN qbot_v2.calendar_entry e ON e.id=r.entry_id "
         "WHERE r.day >= %s" + (" AND r.route_id=%s" if route_id else "") + (" AND r.day=%s" if date else "") + " ORDER BY r.day LIMIT 1")
    args = [today] + ([route_id] if route_id else []) + ([date] if date else [])
    try:
        row = conn.execute(q, args).fetchone()
    except Exception:
        row = None
    if row:
        row = dict(row) if isinstance(row, dict) else dict(zip(("route_id", "day", "at_time", "title"), row))
        return row["route_id"], str(row["day"]), (str(row["at_time"])[:5] if row.get("at_time") else None), "kalendarz: " + str(row.get("title") or "")
    if route_id or not date:
        try:
            q2 = "SELECT route_id, pack_date FROM qbot_v2.route_day_pack WHERE pack_date >= %s" + (" AND route_id=%s" if route_id else "") + " ORDER BY pack_date LIMIT 1"
            r2 = conn.execute(q2, [today] + ([route_id] if route_id else [])).fetchone()
            if r2:
                r2 = list(r2.values()) if isinstance(r2, dict) else list(r2)
                return r2[0], str(r2[1]), None, "pakiet dnia"
        except Exception:
            pass
    return route_id, date, None, None


def day_plan(args: dict) -> dict:
    import qbot_web as W
    from qbot3.routes import route_day_pack as DP, outfit_advisor as OA, route_intro as RI, ride_invite as RV
    a = args or {}
    rid, day = (a.get("route_id") or None), (str(a.get("date"))[:10] if a.get("date") else None)
    conn = W._db_conn()
    try:
        rid2, day2, t_cal, src = _pick_default(conn, rid, day)
        conn.commit()
        if rid and day:
            src = "podane w pytaniu"
        rid, day = rid or rid2, day or day2
        if not rid or not day:
            return {"status": "NO_DATA", "error": "Brak trasy/daty: podaj route_id i date albo dodaj jazde do kalendarza."}
        start = str(a.get("time") or t_cal or "10:00")[:5]
        n, m = int(a.get("long_stops") or 0), int(a.get("long_stop_min") or 30)
        d = W._build_report_data(conn, rid, day, start, n, m, ai=False, day_table=True)
        conn.commit()
        det, tm = d.get("details") or {}, d.get("time") or {}
        st = start.split(":")
        meta = None
        try:
            mm = int(st[0]) * 60 + int(st[1]) + int(round(float(tm.get("total_h")) * 60))
            meta = "%02d:%02d" % ((mm // 60) % 24, mm % 60)
        except Exception:
            pass
        w = det.get("weather") or {}
        sl = w.get("slonce") or {}
        sun_warn = []
        if sl.get("wschod") and start < sl["wschod"]:
            sun_warn.append("start przed wschodem (%s)" % sl["wschod"])
        if meta and sl.get("zachod") and meta > sl["zachod"]:
            sun_warn.append("meta po zachodzie (%s) - oswietlenie" % sl["zachod"])
        out = {"status": "OK", "zrodlo_wyboru": src or "podane w pytaniu",
               "trasa": {"route_id": rid, "nazwa": RV._clean_name((d.get("route") or {}).get("name")),
                         "km": (d.get("route") or {}).get("distance_km"), "przewyzszenie_m": (d.get("route") or {}).get("ascent_m")},
               "plan": {"data": day, "start": start, "przerwy": "%d x %d min" % (n, m) if n else "brak", "meta": meta,
                        "czas_calk_h": tm.get("total_h"), "czas_ruchu_h": tm.get("moving_h"),
                        "miejsce_startu": (d.get("start") or {}).get("miejscowosc")},
               "slonce": {"wschod": sl.get("wschod"), "zachod": sl.get("zachod"), "ostrzezenia": sun_warn},
               "pogoda": {"ogolnie": w.get("ogolne"), "wbgt_max": (w.get("peak") or {}).get("wbgt"),
                          "okna": [{"godz": x.get("okno"), "km": [x.get("km_od"), x.get("km_do")], "odczuwalna": x.get("feels"),
                                    "deszcz_proc": x.get("opad_prob"), "wiatr_wzdluz_ms": x.get("wiatr_ms")} for x in (w.get("windows") or [])][::2]},
               "alerty": [{"typ": x.get("typ"), "km": [x.get("km_od"), x.get("km_do")], "opis": x.get("opis")} for x in (d.get("alerts") or [])],
               "forma_na_dzien": ((det.get("forma") or {}).get("prognoza_dnia") or {}).get("warianty")}
        pk = DP.load_pack(conn, rid, day)
        if pk:
            ap = DP.apply_pack(pk, d, start)
            v = (pk.get("warianty") or {}).get(ap.get("wariant")) or {}
            out["pakiet_dnia"] = {"wariant": ap.get("wariant"), "w_zakresie": ap.get("w_zakresie"), "ocena_okna": v.get("ocena_okna"),
                                  "reguly_aktywne": [r.get("zdanie") for r in ap.get("reguly_aktywne") or []],
                                  "etapy": [{"km": e.get("km"), "moc_w": e.get("moc_w"), "tryb": e.get("tryb"), "jedzenie_g_h": e.get("jedzenie_g_h"),
                                             "picie_l_h": e.get("picie_l_h"), "uwaga": e.get("uwaga")} for e in v.get("etapy") or []],
                                  "wykonalnosc": (pk.get("dzien") or {}).get("wykonalnosc"),
                                  "notatki": pk.get("notatki_alberta"), "wygenerowany": (pk.get("meta") or {}).get("created_at")}
        else:
            out["pakiet_dnia"] = "brak - mozna wygenerowac w Analizie trasy (Plan dnia -> Generuj pakiet dnia)"
        of = OA.load_last(conn, rid, day)
        if of:
            pl = of.get("plan") or {}
            same = pl.get("start") == start and int(pl.get("long_stops") or 0) == n
            out["ubior"] = {"dla_planu": pl, "ten_sam_plan": same, "warunki": of.get("warunki_krotko"),
                            "zestawy": [{"nazwa": z.get("nazwa"), "rzeczy": [x.get("nazwa") for x in z.get("rzeczy") or []],
                                         "do_kieszeni": [x.get("nazwa") for x in z.get("do_kieszeni") or []], "zdejmij": z.get("zdejmij")}
                                        for z in of.get("zestawy") or []]}
        else:
            out["ubior"] = "brak - mozna dobrac w Analizie trasy (Sprzet -> Dobierz ubior)"
        it = RI.load(conn, rid)
        if it:
            out["o_trasie"] = {"tytul": it.get("tytul"), "wprowadzenie": it.get("wprowadzenie"),
                               "warto_zobaczyc": [x.get("nazwa") for x in it.get("warto_zobaczyc") or []]}
        try:
            inv = RV.list_invites(conn, rid, day)
            act = [x for x in inv if not x.get("revoked_at")]
            if act:
                out["zaproszenia"] = {"zaproszonych": len(act), "jedzie": sum(1 for x in act if x.get("status") == "tak"),
                                      "nie_jedzie": sum(1 for x in act if x.get("status") == "nie")}
        except Exception:
            pass
        return out
    finally:
        conn.close()
