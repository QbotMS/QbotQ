"""TRENER - weryfikacja planu tygodnia przez AI ("silnik liczy, AI sprawdza, uzytkownik decyduje").

review_week(c, user, week_start) -> {summary, issues[], rule_issues[], model, cached}. NIC nie zapisuje w planie.
AI dostaje zwarty kontekst (dni: typ, zajetosci, pogoda, notatki Kalendarza, sesje z planu i zrobione; faza, cel h,
gotowosc, nadchodzace cele, kluczowe progi) + wyniki regul. Ma zwrocic tylko JSON z uwagami opartymi na podanych danych.
Walidacja odpowiedzi: dzien musi nalezec do tygodnia, severity z listy, teksty przyciete. Cache w pamieci 30 min
per (uzytkownik, tydzien, skrot danych) - kolejne otwarcia nie kosztuja.
Testy: tests/test_trener_review.py (walidacja i budowa wejscia, bez LLM).
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import date, timedelta

import qbot_trener_engine as E

DN = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"]
SEV = {"wysoka", "średnia", "niska"}
_CACHE: dict = {}

SYSTEM = """Jesteś weryfikatorem planu treningowego (kolarstwo gravel/bikepacking + siła obwodowa + wioślarz + joga).
Dostajesz plan tygodnia ułożony przez silnik reguł i pełny kontekst. Twoje zadanie: znaleźć rzeczy BEZ SENSU albo RYZYKOWNE,
których reguły mogły nie złapać, np.: dwie ciężkie jazdy obok siebie, siła przy długiej jeździe, trening w dniu z ważnym
wydarzeniem albo notatką w Kalendarzu, jazda na zewnątrz przy złej pogodzie, brak odpoczynku po ciężkim dniu, plan niezgodny
z gotowością, dzień bez sensu (np. tylko joga, gdy budżet pozwala na więcej), konflikt z wyprawą/celem, dubel jazdy.
SESJE "reczna": true / "usunieta_przez_uzytkownika": true / "wyciszone_uwagi" to DECYZJE UŻYTKOWNIKA — szanuj je: nie proponuj ich
cofania ani przenoszenia; skomentuj tylko, gdy grozi to zdrowiu (np. choroba, bardzo ciężkie dni pod rząd) albo bezpieczeństwu (burza).
GODZINY: używaj WYŁĄCZNIE pól "suma_godzin" (nie licz sam). Gdy suma mieści się w "widelki_godzin" — nie komentuj godzin w ogóle;
poza widełkami najwyżej jedna spokojna uwaga, bez nakazu skracania.
ZASADY: opieraj się WYŁĄCZNIE na podanych danych (cytuj dzień, godzinę, liczbę z danych); nie wymyślaj wartości;
nie powtarzaj bez potrzeby uwag z "reguly" (możesz je doprecyzować); maks. 6 uwag, najważniejsze pierwsze;
pisz po polsku, prosto, krótko, bez żargonu. Jeśli plan jest sensowny — pusta lista i jedno zdanie podsumowania.
Odpowiedz WYŁĄCZNIE JSON: {"summary": "1–2 zdania", "issues": [{"day": "RRRR-MM-DD", "severity": "wysoka|średnia|niska",
"problem": "co jest nie tak", "why": "fakt z danych", "suggestion": "co zrobić (konkretnie)"}]}"""


def build_input(ctx: dict, sessions: list, activities: list, rule_issues: list, plan_meta: dict) -> dict:
    ws = ctx["week_start"]
    days = []
    for i in range(7):
        d = ws + timedelta(days=i)
        info = E.day_info(ctx, d)
        ds = d.isoformat()
        wx = (ctx.get("weather") or {}).get(ds)
        cal = [{"tytul": c.get("title") or c.get("event_type") or c.get("kind"), "godz": (str(c.get("at_time"))[:5] if c.get("at_time") else None),
                "notatka": (c.get("note") or "")[:200] or None}
               for c in ctx.get("calendar", []) if (E._d(c["day"]) <= d <= (E._d(c.get("end_day")) or E._d(c["day"])))]
        days.append({
            "data": ds, "dzien": DN[i], "minal": d < ctx["today"], "dzis": d == ctx["today"], "typ": info["type"],
            "zajetosci": [f"{E.t2(a)}–{E.t2(b)} {l.strip()}" for a, b, l in info["busy"] if a is not None],
            "pogoda": ({"wiatr_ms": wx.get("wind"), "porywy_ms": wx.get("gust"), "odczuwalna_min": wx.get("feel_min"), "odczuwalna_max": wx.get("feel_max"),
                        "opad_mmh": wx.get("rain_mmh"), "szansa_opadu": wx.get("rain_prob"), "burza": wx.get("storm")} if wx else None),
            "kalendarz": cal,
            "plan": [{"godz": (str(s.get("start_time"))[:5] if s.get("start_time") else None), "sport": s["sport"], "nazwa": s["name"],
                      "min": s["dur_min"], "status": s["status"], "reczna": s.get("source") == "manual", "dluga": bool(s.get("is_long")),
                      "usunieta_przez_uzytkownika": s["status"] == "skip" and "usunięte przez Ciebie" in (s.get("note") or ""),
                      "wyciszone_uwagi": s.get("acks") or [],
                      "xss": s.get("xss"), "uwaga": (s.get("note") or "")[:160] or None} for s in sessions if str(s["day"])[:10] == ds],
            "zrobione_z_garmina": [{"sport": a.get("sport_type"), "nazwa": a.get("activity_name"), "km": round((a.get("distance_m") or 0) / 1000, 1),
                                    "h": round((a.get("duration_s") or 0) / 3600, 1)} for a in activities if str(a.get("date"))[:10] == ds],
        })
    ov = ctx.get("ov") or {}
    goals = [{"nazwa": g["name"], "rodzaj": g["kind"], "priorytet": g.get("priority"), "od": str(g.get("date_from") or ""), "do": str(g.get("date_to") or ""),
              "cel": g.get("target")} for g in ctx.get("goals", [])
             if g.get("status") == "active" and g.get("date_from") and E._d(g["date_from"]) <= ws + timedelta(days=90) and (E._d(g.get("date_to")) or E._d(g["date_from"])) >= ws]
    linked = {s.get("training_session_id") for s in sessions if s.get("training_session_id")}
    done_h = sum(s["dur_min"] for s in sessions if s["status"] == "done") / 60
    extra_h = sum((a.get("duration_s") or 0) for a in activities if a.get("id") not in linked) / 3600
    left_h = sum(s["dur_min"] for s in sessions if s["status"] == "plan" and E._d(s["day"]) >= ctx["today"]) / 60
    tgt = float(plan_meta.get("target_h") or 0)
    return {"tydzien_od": ws.isoformat(), "dzis": ctx["today"].isoformat(), "okres_sezonu": plan_meta.get("phase_name"),
            "sezon": plan_meta.get("season"), "cel_godzin": plan_meta.get("target_h"),
            "suma_godzin": {"zrobione_w_planie": round(done_h, 1), "zrobione_poza_planem": round(extra_h, 1), "pozostaly_plan": round(left_h, 1),
                            "razem_tydzien": round(done_h + extra_h + left_h, 1)},
            "widelki_godzin": [round(tgt * 0.75, 1), round(tgt * 1.25, 1)],
            "gotowosc_dzis": ctx.get("readiness_today"), "prog_wersji_minimum": ctx.get("readiness_threshold"),
            "progi": {"min_dni_wolnych": E.P(ov, "load.min_rest_days"), "przerwa_po_ciezkiej_h": E.P(ov, "regen.heavy_gap_h"),
                      "ciezka_jazda_xss": E.P(ov, "yoga.hard_xss"), "dluga_jazda_h": E.P(ov, "yoga.long_h"),
                      "wiatr_max_ms": E.P(ov, "wx.wind_ms"), "deszcz_max_mmh": E.P(ov, "wx.rain_mmh")},
            "nadchodzace_cele": goals, "reguly": rule_issues, "dni": days}


def validate(resp, ws: date) -> dict:
    if not isinstance(resp, dict):
        return {"summary": "Nie udało się odczytać odpowiedzi AI.", "issues": []}
    days = {(ws + timedelta(days=i)).isoformat() for i in range(7)}
    out = []
    for it in (resp.get("issues") or [])[:6]:
        if not isinstance(it, dict):
            continue
        d = str(it.get("day") or "")[:10]
        if d not in days:
            continue
        sev = str(it.get("severity") or "średnia").lower()
        sev = sev if sev in SEV else "średnia"
        p = str(it.get("problem") or "").strip()
        if not p:
            continue
        out.append({"day": d, "severity": sev, "problem": p[:220], "why": str(it.get("why") or "")[:260], "suggestion": str(it.get("suggestion") or "")[:260]})
    order = {"wysoka": 0, "średnia": 1, "niska": 2}
    out.sort(key=lambda x: (order[x["severity"]], x["day"]))
    return {"summary": str(resp.get("summary") or "")[:400], "issues": out}


def review_week(c, user: str, ws: date, force: bool = False, llm=None) -> dict:
    ctx = E.build_context(c, user, ws)
    res = E.plan_week(ctx)
    c.execute("SELECT * FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s ORDER BY day, start_time NULLS LAST", (user, ws, ws + timedelta(days=6)))
    sessions = [dict(x) for x in c.fetchall()]
    for s_ in sessions:
        if s_.get("start_time"):
            s_["start_time"] = s_["start_time"].strftime("%H:%M")
    c.execute("SELECT id, date, sport_type, activity_name, distance_m, duration_s FROM qbot_v2.training_sessions WHERE date BETWEEN %s AND %s", (ws, ws + timedelta(days=6)))
    acts = [dict(x) for x in c.fetchall()]
    days_meta = {d: {"type": v["type"], "busy": v["busy"]} for d, v in res["days"].items()}
    det = E.check_rules_detailed([dict(s_, day=str(s_["day"])) for s_ in sessions], ctx.get("ov") or {}, days_meta)
    rules = [w["text"] for w in det if not w["acked"]]
    inp = build_input(ctx, sessions, acts, rules, res)
    if not sessions:
        return {"summary": "Brak planu w tym tygodniu — najpierw „przelicz tydzień”.", "issues": [], "rule_issues": rules, "cached": False, "model": None}
    key = hashlib.sha1((user + json.dumps(inp, sort_keys=True, default=str)).encode()).hexdigest()
    hit = _CACHE.get(key)
    if hit and not force and hit[0] > time.time() - 1800:
        return dict(hit[1], cached=True)
    if llm is None:
        from qgpt_client import qgpt_json as llm
    try:
        raw = llm(json.dumps(inp, ensure_ascii=False, default=str), system=SYSTEM, max_tokens=1400)
        out = validate(raw, ws)
    except Exception as e:
        out = {"summary": f"Weryfikacja AI niedostępna ({str(e)[:120]}).", "issues": []}
    try:
        import os
        model = os.environ.get("QGPT_MODEL")
    except Exception:
        model = None
    out.update(rule_issues=rules, cached=False, model=model)
    _CACHE[key] = (time.time(), out)
    return out
