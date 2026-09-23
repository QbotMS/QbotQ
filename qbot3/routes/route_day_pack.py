"""[E2c] Pakiet dnia - jeden szeroki przebieg AI dla trasy + daty.

Zasada: LICZBY daje silnik (warstwa planu, _build_report_data ai=False day_table=True),
AI pisze tylko interpretacje i reguly "jesli-to" z ZAMKNIETEJ listy warunkow, ktore
system sprawdza sam na rzeczywistym planie (godzina startu + przerwy uzytkownika).
Warianty startu: 08:00..12:00 co godzine. Ubior/opony: zaparkowane (pole null).

Schemat pakietu (wersja PACK_VERSION):
  meta{route_id,date,model,created_at,sloty,zakres,czas_s,bledy[]}
  dzien{pogoda_przebieg[], ryzyka[], wykonalnosc{}}
  warianty{"08:00":{ocena_okna{}, etapy[]}, ...}
  reguly[]  notatki_alberta[]  ubior_opony: null
"""
from __future__ import annotations

import datetime as _dt
import json
import time
from concurrent.futures import ThreadPoolExecutor

PACK_VERSION = 1
SLOTS = ["08:00", "09:00", "10:00", "11:00", "12:00"]
TAGI_ZJAWISK = {"upal", "zimno", "deszcz", "burza", "silny_wiatr", "mgla", "spokojnie"}
KLASY_OKNA = {"dobre", "akceptowalne", "slabe"}
TRYBY = {"atak", "tempo", "spokojnie"}
WERDYKTY = {"w_normie", "na_granicy", "ponad_forme"}
WARUNKI = {"wbgt_ponad", "wiatr_czolowy_ponad", "deszcz_prob_ponad", "burza",
           "meta_po", "zapas_wprime_ponizej", "start_przed", "start_po"}
SEKCJE = {"pogoda", "strategia", "ogolne"}
_WIATR = "Wiatr ZAWSZE w m/s. Bez markdown, bez emoji. NIE wymyslaj liczb - tylko z danych."


# ---------- wejscie z silnika ----------
def _f(x, d=1):
    try:
        return round(float(x), d)
    except Exception:
        return None


def _slot_summary(d: dict, start: str) -> dict:
    det = d.get("details") or {}
    w = det.get("weather") or {}
    t = d.get("time") or {}
    ch = (det.get("climbs") or {}).get("chain") or {}
    total_h = t.get("total_h")
    meta = None
    try:
        h, m = [int(x) for x in start.split(":")]
        mins = h * 60 + m + int(round(float(total_h) * 60))
        meta = "%02d:%02d" % ((mins // 60) % 24, mins % 60)
    except Exception:
        pass
    return {
        "start": start, "meta": meta, "czas_calk_h": total_h, "czas_ruchu_h": t.get("moving_h"),
        "okna": [{"godz": x.get("okno"), "km": [_f(x.get("km_od")), _f(x.get("km_do"))], "wbgt": x.get("wbgt"),
                  "odczuwalna": x.get("feels"), "deszcz_proc": x.get("opad_prob"), "opad_mm": x.get("opad_mm"),
                  "wiatr_wzdluz_ms": x.get("wiatr_ms")} for x in (w.get("windows") or [])],
        "alerty": [{"typ": a.get("typ"), "km": [a.get("km_od"), a.get("km_do")], "eta": [a.get("eta_od"), a.get("eta_do")],
                    "opis": a.get("opis")} for a in (d.get("alerts") or [])],
        "podjazdy_tryb": [{"i": c.get("i"), "km": [c.get("a_km"), c.get("b_km")], "tryb": c.get("chain_mode"),
                           "wbal_min": c.get("chain_wbal_min")} for c in ((det.get("climbs") or {}).get("list") or [])],
        "zapas_wprime_min_proc": ch.get("min_wbal_pct"),
    }


def collect(build_fn, conn, route_id: str, date_str: str, long_stops: int = 0, long_stop_min: int = 0) -> dict:
    """build_fn = qbot_web._build_report_data (wstrzykniete, bez importu cyklicznego)."""
    slots, base = {}, None
    for st in SLOTS:
        d = build_fn(conn, route_id, date_str, st, long_stops, long_stop_min, ai=False, day_table=True)
        if base is None:
            base = d
        slots[st] = _slot_summary(d, st)
    det = base.get("details") or {}
    fo = det.get("forma") or {}
    wd = fo.get("wykonalnosc_dane") or {}
    risks = []
    for i, r in enumerate((det.get("surface") or {}).get("risk") or []):
        risks.append({"id": "r%d" % (i + 1), "km": [_f(r.get("a")), _f(r.get("b"))], "kat": r.get("k"),
                      "teren": r.get("teren"), "osm": r.get("osm"), "sygnaly": (r.get("reason") or "")[:300]})
    day = {
        "trasa": {"route_id": route_id, "data": date_str, "dystans_km": (det.get("surface") or {}).get("total_km"),
                  "przewyzszenie_m": (det.get("climbs") or {}).get("ascent_m"),
                  "nawierzchnia_udzial": (det.get("surface") or {}).get("by_cat"),
                  "legenda_nawierzchni": {"1": "asfalt", "2": "dobry gravel", "3": "zwykly gravel/grunt",
                                          "4": "trudna/wolna", "5": "ryzyko/piach"}},
        "slonce": (det.get("weather") or {}).get("slonce"),
        "ryzyka": risks,
        "podjazdy": [{"i": c.get("i"), "km": [c.get("a_km"), c.get("b_km")], "dl_m": c.get("length_m"),
                      "sr_proc": c.get("avg_pct"), "max_proc": c.get("max_pct"), "ocena": c.get("score"),
                      "ocena_opis": c.get("score_label")} for c in ((det.get("climbs") or {}).get("list") or [])],
        "forma": {"ftp_w": _f(fo.get("ftp"), 0), "masa_kg": fo.get("mass"), "wprime_kj": _f(fo.get("w_prime_kj")),
                  "zapotrzebowanie": fo.get("vs_route"),
                  "prognoza_dnia": fo.get("prognoza_dnia")},
        "wykonalnosc": {"werdykt_silnika": wd.get("verdict"), "sciana": ((wd.get("walls") or [{}])[0]).get("label"),
                        "tsb_po": (wd.get("simulation") or {}).get("days") and wd["simulation"]["days"][0].get("tsb_morning"),
                        "sufity": wd.get("ceilings"), "forma": wd.get("form")},
        "zaopatrzenie": [{"rejon_km": p.get("q_km"), "punkty": [{"km": x.get("km"), "nazwa": x.get("name")}
                                                               for x in (p.get("picks") or [])][:4]}
                         for p in ((det.get("poi") or {}).get("resupply") or [])],
    }
    dx = build_fn(conn, route_id, date_str, SLOTS[-1], 2, 45, ai=False, day_table=True)
    extreme = _slot_summary(dx, SLOTS[-1])
    return {"day": day, "slots": slots, "extreme": extreme, "default_stops": [long_stops, long_stop_min]}


# ---------- prompty ----------
_HDR = "Jestes Albert - asystent kolarski QBot. Zwracasz WYLACZNIE JSON. " + _WIATR + "\n"

SYS_A = _HDR + (
    "Klucze: pogoda_przebieg, ryzyka, wykonalnosc, notatki_alberta.\n"
    "pogoda_przebieg: lista okresow dnia (lokalny czas) wg WSZYSTKICH wariantow startu z 'slots' "
    "[{\"od\":\"HH:MM\",\"do\":\"HH:MM\",\"zjawiska\":[tagi z: upal,zimno,deszcz,burza,silny_wiatr,mgla,spokojnie],"
    "\"opis\":<=12 slow}]. Opisuj przebieg DNIA, nie konkretnej jazdy.\n"
    "ryzyka: DOKLADNIE jeden wpis na kazdy element day.ryzyka, to samo id "
    "[{\"id\",\"pod_kolami\":krotki tag np. 'szuter','grunt','piach','bruk','sciezka_lesna',"
    "\"pewnosc\":\"niska|srednia|wysoka\",\"piach\":\"brak|mozliwy|pewny\",\"po_opadach\":\"sucho|normalnie|mokro\","
    "\"komentarz\":<=22 slow}]. Jawny tag surface=sand -> piach 'pewny'; sam region/ryzyko -> 'mozliwy'. "
    "NIE cytuj surowych kodow OSM - tlumacz na ludzki.\n"
    "wykonalnosc: {\"werdykt\":\"w_normie|na_granicy|ponad_forme\",\"komentarz\":<=25 slow} - na bazie liczb z day.wykonalnosc "
    "ORAZ day.forma.prognoza_dnia (forma PROGNOZOWANA rano w dniu jazdy: warianty 'jak_dotad' i 'odpoczynek'; "
    "TSB dodatni = swiezosc). Oceniaj na prognoze, nie na stan dzisiejszy.\n"
    "notatki_alberta: 4-10 najwazniejszych FAKTOW dnia (<=25 slow kazdy) do odpowiadania na pytania.")

SYS_B = _HDR + (
    "Klucz: warianty - obiekt, klucz = godzina startu z 'slots' (TYLKO podane). Dla kazdego:\n"
    "{\"ocena_okna\":{\"klasa\":\"dobre|akceptowalne|slabe\",\"powody\":[krotkie tagi],\"zdanie\":<=15 slow},"
    "\"etapy\":[{\"km\":[od,do],\"charakter\":[tagi],\"moc_w\":[lo,hi],\"moc_pct_ftp\":[lo,hi],"
    "\"tryb\":\"atak|tempo|spokojnie\",\"jedzenie_g_h\":liczba,\"picie_l_h\":liczba,\"uwaga\":<=15 slow}]}.\n"
    "3-6 etapow wg ZMIANY charakteru (nawierzchnia, podjazdy, pogoda/wiatr w oknach tego wariantu), km z danych, "
    "ciagle od 0 do konca trasy. Moc z forma.ftp_w: endurance ~56-75% FTP, nie na stale ponad FTP; "
    "podjazd z trybem 'tempo' -> nie zalecaj docisniecia. ROZNICUJ moc: pod wiatr czolowy >=3 m/s i na trudnej "
    "nawierzchni (kat 4-5) nizej, z wiatrem w plecy i na asfalcie mozna wyzej, w cieple (WBGT>=22) nizej - "
    "etapy i moc maja sie roznic miedzy wariantami, gdy roznia sie ich okna pogody. "
    "Jedzenie/picie z forma.zapotrzebowanie (cho_g_h, fluid_l) "
    "i ciepla. Uwagi odwoluj do zjawisk, NIE wpisuj godzin przejazdu (zmienia je plan).")

SYS_C = _HDR + (
    "Klucz: reguly - lista 5-12 regul 'jesli-to', ktore system sprawdzi SAM na rzeczywistym planie uzytkownika "
    "(jego godzina startu 08:00-12:00 i przerwy).\n"
    "[{\"id\":\"g1\",\"warunek\":{\"typ\":<jeden z: wbgt_ponad,wiatr_czolowy_ponad,deszcz_prob_ponad,burza,meta_po,"
    "zapas_wprime_ponizej,start_przed,start_po>,\"prog\":liczba albo \"HH:MM\" (dla meta_po/start_*; burza bez progu),"
    "\"km\":[od,do] opcjonalnie},\"sekcja\":\"pogoda|strategia|ogolne\",\"zdanie\":<=20 slow,"
    "\"korekta_mocy_pct\":liczba ujemna albo 0,\"priorytet\":1-3}].\n"
    "TWARDE ZASADY: (1) regula MUSI ROZROZNIAC plany - ma byc prawdziwa dla czesci wariantow w 'slots' i falszywa "
    "dla innych (sprawdz rozrzut wartosci miedzy wariantami; 'slots_skrajny' = start 12:00 z 2 przerwami po 45 min). "
    "Regula prawdziwa zawsze albo nigdy zostanie ODRZUCONA automatycznie. (2) Progi znaczace fizjologicznie: upal od "
    "WBGT ~23 C (mocno od ~26), istotny wiatr czolowy od ~4 m/s, deszcz od ~40%. Jesli dane dnia nie zblizaja sie do "
    "takich progow - nie tworz takiej reguly (lepiej mniej regul). (3) meta_po tylko gdy ma realny skutek (zmrok z "
    "day.slonce.zachod, burza, upal na koncu) - podaj powod w zdaniu. (4) NIE przecz symulacji: zapas_wprime_ponizej "
    "tylko z progiem wyraznie ponizej obecnego minimum i z sensowna rada. (5) wiatr_czolowy_ponad: wiatr czolowy = "
    "ujemny wiatr_wzdluz_ms, prog dodatni w m/s.")


def _ask(system: str, payload: dict, max_tokens: int):
    from qgpt_client import qgpt_json
    return qgpt_json(json.dumps(payload, ensure_ascii=False, default=str), system=system,
                     max_tokens=max_tokens, temperature=0.3)


# ---------- walidacja ----------
def _hhmm(x) -> bool:
    try:
        _dt.datetime.strptime(str(x), "%H:%M")
        return True
    except Exception:
        return False


def _valid_a(o, day):
    if not isinstance(o, dict):
        return "brak JSON"
    ids = {r["id"] for r in day["ryzyka"]}
    got = {r.get("id") for r in (o.get("ryzyka") or []) if isinstance(r, dict)}
    if ids != got:
        return "ryzyka: id niezgodne (%d/%d)" % (len(ids & got), len(ids))
    for p in o.get("pogoda_przebieg") or []:
        if not (_hhmm(p.get("od")) and _hhmm(p.get("do"))) or not set(p.get("zjawiska") or []) <= TAGI_ZJAWISK:
            return "pogoda_przebieg: zly okres/tag"
    if (o.get("wykonalnosc") or {}).get("werdykt") not in WERDYKTY:
        return "wykonalnosc: zly werdykt"
    if not isinstance(o.get("notatki_alberta"), list) or not o["notatki_alberta"]:
        return "brak notatek"
    return None


def _valid_b(o, slots, total_km, ftp):
    if not isinstance(o, dict) or not isinstance(o.get("warianty"), dict):
        return "brak warianty"
    for st in slots:
        v = o["warianty"].get(st)
        if not isinstance(v, dict):
            return "brak wariantu " + st
        if (v.get("ocena_okna") or {}).get("klasa") not in KLASY_OKNA:
            return st + ": zla klasa okna"
        et = v.get("etapy") or []
        if not (2 <= len(et) <= 7):
            return st + ": liczba etapow"
        for e in et:
            if e.get("tryb") not in TRYBY:
                return st + ": zly tryb"
            mw = e.get("moc_w") or []
            if len(mw) != 2 or not (0 < float(mw[0]) <= float(mw[1]) <= 1.1 * float(ftp or 400)):
                return st + ": moc poza zakresem"
        k0, k1 = float(et[0]["km"][0]), float(et[-1]["km"][1])
        if k0 > 1.0 or abs(k1 - float(total_km)) > max(2.0, 0.03 * float(total_km)):
            return st + ": etapy nie pokrywaja trasy"
    return None


def _valid_c(o):
    if not isinstance(o, dict) or not isinstance(o.get("reguly"), list) or not o["reguly"]:
        return "brak regul"
    for r in o["reguly"]:
        w = r.get("warunek") or {}
        if w.get("typ") not in WARUNKI or r.get("sekcja") not in SEKCJE:
            return "regula %s: zly typ/sekcja" % r.get("id")
        if w["typ"] in ("meta_po", "start_przed", "start_po") and not _hhmm(w.get("prog")):
            return "regula %s: prog HH:MM" % r.get("id")
        if w["typ"] not in ("burza", "meta_po", "start_przed", "start_po"):
            try:
                float(w.get("prog"))
            except Exception:
                return "regula %s: prog liczbowy" % r.get("id")
    return None


def _part(system, payload, max_tokens, validator):
    last_err = None
    for _ in range(2):
        try:
            o = _ask(system, payload, max_tokens)
        except Exception as e:  # noqa
            o, last_err = None, "wyjatek: " + str(e)[:120]
        try:
            err = validator(o)
        except Exception as e:  # noqa - zly ksztalt odpowiedzi = blad walidacji, nie awaria
            err = "walidacja: " + str(e)[:120]
        if err is None:
            return o, None
        last_err = err
    return None, last_err


def build_pack(inputs: dict, model_name: str = "") -> dict:
    t0 = time.perf_counter()
    day, slots = inputs["day"], inputs["slots"]
    total_km = day["trasa"]["dystans_km"] or 0
    ftp = (day.get("forma") or {}).get("ftp_w")
    pa = {"day": day, "slots": {k: {"start": v["start"], "meta": v["meta"], "okna": v["okna"], "alerty": v["alerty"]}
                               for k, v in slots.items()}}
    pb1 = {"day": day, "slots": {k: slots[k] for k in SLOTS[:3]}}
    pb2 = {"day": day, "slots": {k: slots[k] for k in SLOTS[3:]}}
    pc = {"day": {"trasa": day["trasa"], "podjazdy": day["podjazdy"], "forma": day["forma"], "slonce": day.get("slonce")},
          "slots": slots, "slots_skrajny": inputs.get("extreme")}
    contexts = [(slots[k], _mins(k)) for k in SLOTS] + ([(inputs["extreme"], _mins(SLOTS[-1]))] if inputs.get("extreme") else [])
    jobs = {
        "a": (SYS_A, pa, 6000, lambda o: _valid_a(o, day)),
        "b1": (SYS_B, pb1, 7000, lambda o: _valid_b(o, SLOTS[:3], total_km, ftp)),
        "b2": (SYS_B, pb2, 6000, lambda o: _valid_b(o, SLOTS[3:], total_km, ftp)),
        "c": (SYS_C, pc, 5000, _valid_c),
    }
    res, errs = {}, []
    with ThreadPoolExecutor(max_workers=4) as ex:
        fut = {k: ex.submit(_part, *v) for k, v in jobs.items()}
        for k, f in fut.items():
            o, e = f.result()
            res[k] = o
            if e:
                errs.append("%s: %s" % (k, e))
    reguly, odrzucone = screen_rules((res.get("c") or {}).get("reguly") or [], contexts)
    if len(reguly) < 3 and res.get("c"):
        pc2 = dict(pc)
        pc2["odrzucone_przez_test"] = odrzucone
        pc2["uwaga"] = "Poprzednie reguly odrzucono jako nierozrozniajace. Uloz nowe, ktore sa prawdziwe tylko dla czesci wariantow."
        o2, e2 = _part(SYS_C, pc2, 5000, _valid_c)
        if o2:
            g2, b2 = screen_rules(o2.get("reguly") or [], contexts)
            reguly, odrzucone = reguly + g2, odrzucone + b2
        elif e2:
            errs.append("c2: " + e2)
    # duplikaty (ten sam warunek) -> jedna regula; ID przenumerowane g1..gN
    _seen, _uniq = set(), []
    for r in reguly:
        k = json.dumps(r.get("warunek") or {}, sort_keys=True, ensure_ascii=False)
        if k in _seen:
            continue
        _seen.add(k)
        _uniq.append(r)
    for i, r in enumerate(_uniq, 1):
        r["id"] = "g%d" % i
    reguly = _uniq
    a = res.get("a") or {}
    warianty = {}
    for k in ("b1", "b2"):
        warianty.update((res.get(k) or {}).get("warianty") or {})
    return {
        "meta": {"wersja": PACK_VERSION, "route_id": day["trasa"]["route_id"], "date": day["trasa"]["data"],
                 "model": model_name, "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                 "sloty": SLOTS, "zakres": [SLOTS[0], SLOTS[-1]], "przerwy_zalozone": inputs.get("default_stops"),
                 "czas_s": round(time.perf_counter() - t0, 1), "bledy": errs},
        "dzien": {"pogoda_przebieg": a.get("pogoda_przebieg") or [], "ryzyka": a.get("ryzyka") or [],
                  "wykonalnosc": a.get("wykonalnosc")},
        "warianty": {k: warianty[k] for k in SLOTS if k in warianty},
        "reguly": reguly,
        "reguly_odrzucone": odrzucone,
        "notatki_alberta": a.get("notatki_alberta") or [],
        "ubior_opony": None,
    }


# ---------- zastosowanie na planie (bez AI) ----------
def _mins(hhmm):
    h, m = [int(x) for x in str(hhmm).split(":")]
    return h * 60 + m


def _in_km(win_km, rng):
    if not rng:
        return True
    try:
        a, b = float(rng[0]), float(rng[1])
        return float(win_km[1]) >= a and float(win_km[0]) <= b
    except Exception:
        return True


def eval_rule(r: dict, s: dict, sm: int) -> bool:
    """Czy regula jest prawdziwa dla podsumowania planu s (wynik _slot_summary), start w minutach sm."""
    w = r.get("warunek") or {}
    typ, prog, rng = w.get("typ"), w.get("prog"), w.get("km")
    try:
        okna = [o for o in s["okna"] if _in_km(o["km"], rng)]
        if typ == "wbgt_ponad":
            return any((o["wbgt"] if o["wbgt"] is not None else -99) > float(prog) for o in okna)
        if typ == "wiatr_czolowy_ponad":
            return any((o["wiatr_wzdluz_ms"] is not None) and (-float(o["wiatr_wzdluz_ms"]) > float(prog)) for o in okna)
        if typ == "deszcz_prob_ponad":
            return any((o["deszcz_proc"] or 0) > float(prog) for o in okna)
        if typ == "burza":
            return any((a.get("typ") or "").startswith("burz") for a in s["alerty"])
        if typ == "meta_po":
            return bool(s["meta"]) and _mins(s["meta"]) > _mins(prog)
        if typ == "zapas_wprime_ponizej":
            return s["zapas_wprime_min_proc"] is not None and float(s["zapas_wprime_min_proc"]) < float(prog)
        if typ == "start_przed":
            return sm < _mins(prog)
        if typ == "start_po":
            return sm > _mins(prog)
    except Exception:
        return False
    return False


def screen_rules(rules: list, contexts: list):
    """contexts = [(summary, start_min), ...]. Zwraca (dobre, odrzucone) - odrzucone = zawsze albo nigdy."""
    good, bad = [], []
    n = len(contexts)
    for r in rules or []:
        k = sum(1 for (sm_, st_) in contexts if eval_rule(r, sm_, st_))
        if k == 0 or k == n:
            bad.append({"id": r.get("id"), "warunek": r.get("warunek"),
                        "powod": "prawdziwa zawsze (%d/%d)" % (k, n) if k == n else "nigdy prawdziwa (0/%d)" % n})
        else:
            r = dict(r)
            r["test_aktywna"] = "%d/%d" % (k, n)
            good.append(r)
    return good, bad


def apply_pack(pack: dict, plan: dict, start: str) -> dict:
    """Wybiera najblizszy wariant startu i sprawdza reguly na rzeczywistym planie (plan = _build_report_data)."""
    if not pack:
        return {"jest": False}
    s = _slot_summary(plan, start)
    sm = _mins(start)
    _war = pack.get("warianty") or {}
    near = min(_war, key=lambda k: abs(_mins(k) - sm)) if _war else None
    in_range = _mins(pack["meta"]["zakres"][0]) <= sm <= _mins(pack["meta"]["zakres"][1])
    fired = [r for r in (pack.get("reguly") or []) if eval_rule(r, s, sm)]
    fired.sort(key=lambda r: int(r.get("priorytet") or 3))
    return {"jest": True, "wariant": near, "w_zakresie": in_range, "meta": s["meta"],
            "reguly_aktywne": fired, "pakiet_z": pack["meta"].get("created_at"),
            "przerwy_zalozone": pack["meta"].get("przerwy_zalozone")}



# ---------- zapis / odczyt (jeden pakiet na trase + date) ----------
def _ensure(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS qbot_v2.route_day_pack ("
                 "route_id text NOT NULL, pack_date date NOT NULL, "
                 "created_at timestamptz NOT NULL DEFAULT now(), model text, pack jsonb NOT NULL, "
                 "PRIMARY KEY (route_id, pack_date))")


def save_pack(conn, pack: dict) -> None:
    _ensure(conn)
    m = pack["meta"]
    conn.execute("INSERT INTO qbot_v2.route_day_pack (route_id, pack_date, created_at, model, pack) "
                 "VALUES (%s, %s, now(), %s, %s::jsonb) ON CONFLICT (route_id, pack_date) DO UPDATE "
                 "SET created_at=now(), model=EXCLUDED.model, pack=EXCLUDED.pack",
                 (m["route_id"], m["date"], m.get("model"), json.dumps(pack, ensure_ascii=False, default=str)))
    conn.commit()


def load_pack(conn, route_id: str, date_str: str):
    _ensure(conn)
    row = conn.execute("SELECT pack, extract(epoch from (now()-created_at))/3600.0 AS wiek_h "
                       "FROM qbot_v2.route_day_pack WHERE route_id=%s AND pack_date=%s",
                       (route_id, date_str)).fetchone()
    conn.commit()
    if not row:
        return None
    p = row["pack"] if isinstance(row, dict) else row[0]
    p = json.loads(p) if isinstance(p, str) else p
    p.setdefault("meta", {})["wiek_h"] = round(float(row["wiek_h"] if isinstance(row, dict) else row[1]), 2)
    return p



def list_packs(conn, route_id: str) -> list:
    """Daty z zapisanym pakietem dla trasy (rosnaco) + wiek i model. Bez tresci pakietu."""
    _ensure(conn)
    rows = conn.execute("SELECT pack_date, created_at, model FROM qbot_v2.route_day_pack "
                        "WHERE route_id=%s ORDER BY pack_date", (route_id,)).fetchall()
    conn.commit()
    out = []
    for r in rows:
        v = list(r.values()) if isinstance(r, dict) else list(r)
        out.append({"date": str(v[0]), "created_at": v[1].isoformat(timespec="seconds") if v[1] else None, "model": v[2]})
    return out
