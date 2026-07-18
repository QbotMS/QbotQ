"""
tools/trip_stages.py
Handler: etapy dowolnego wyjazdu z qbot_planning_facts (fact_type='route_stages').

qbot.query examples:
  "dzisiejszy etap"
  "etap 3 toskania"
  "plan toskania"
  "kiedy jadę i co mam dziś"
"""
from __future__ import annotations
import json, os, re
from datetime import date, timedelta
from typing import Optional

# ---------------------------------------------------------------------------
# DB helper (reuse env z qbot_query_handler)
# ---------------------------------------------------------------------------
def _pg():
    import psycopg
    return psycopg.connect(
        host=os.getenv("PGHOST","127.0.0.1"),
        port=os.getenv("PGPORT","5432"),
        dbname=os.getenv("PGDATABASE","qbot"),
        user=os.getenv("PGUSER","qbot"),
        password=os.getenv("PGPASSWORD",""),
        connect_timeout=5,
        options="-c search_path=qbot_v2",
    )

# ---------------------------------------------------------------------------
# Pobierz plan etapów z bazy
# ---------------------------------------------------------------------------
def _fetch_route_stages(trip_hint: str = None) -> list[dict]:
    """
    Zwraca listę planów etapów z qbot_planning_facts.
    trip_hint: filtr po tytule (np. 'toskania').
    Każdy plan to dict z polami: id, title, stages (list), status, date.
    """
    conn = _pg()
    try:
        cur = conn.cursor()
        if trip_hint:
            cur.execute(
                "SELECT id, date, title, fact_json, status FROM qbot_planning_facts "
                "WHERE fact_type='route_stages' AND LOWER(title) LIKE %s ORDER BY date DESC",
                (f"%{trip_hint.lower()}%",)
            )
        else:
            cur.execute(
                "SELECT id, date, title, fact_json, status FROM qbot_planning_facts "
                "WHERE fact_type='route_stages' ORDER BY date DESC LIMIT 10"
            )
        rows = cur.fetchall()
    finally:
        conn.close()

    results = []
    for row in rows:
        fj = row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}")
        results.append({
            "id": row[0],
            "date": row[1],
            "title": row[2],
            "stages": fj.get("stages", []),
            "status": row[4],
            "variant": fj.get("variant",""),
            "project": fj.get("project",""),
        })
    return results

def _fetch_active_event(ref_date: date = None) -> Optional[dict]:
    """Zwraca aktywny event dla danej daty z qbot_planning_facts (route_stages).

    Stary calendar_events usuniety 2026-07-16 (DECISIONS.md) — okno eventu
    wyprowadzamy z planu etapow: date_start/date_end = min/max daty etapow.
    """
    if ref_date is None:
        ref_date = date.today()
    for plan in _fetch_route_stages():
        stage_dates = [s.get("date") for s in plan.get("stages", []) if s.get("date")]
        if not stage_dates:
            continue
        try:
            ds = date.fromisoformat(min(stage_dates))
            de = date.fromisoformat(max(stage_dates))
        except Exception:
            continue
        if ds <= ref_date <= de:
            return {"id": plan.get("id"), "date_start": ds, "date_end": de,
                    "title": plan.get("title"), "event_type": "bikepacking",
                    "status": plan.get("status")}
    return None

# ---------------------------------------------------------------------------
# Logika etapów
# ---------------------------------------------------------------------------
def _match_stage_by_date(stages: list, ref_date: date) -> Optional[dict]:
    """Znajdź etap pasujący do daty (pole 'date' w stages[])."""
    date_str = ref_date.isoformat()
    for s in stages:
        if s.get("date") == date_str:
            return s
    return None

def _match_stage_by_number(stages: list, n: int) -> Optional[dict]:
    """Znajdź etap wg numeru."""
    for s in stages:
        if s.get("stage") == n:
            return s
    return None

def _format_stage(stage: dict, plan_title: str) -> str:
    n       = stage.get("stage","?")
    seg     = stage.get("segment","?")
    dist    = stage.get("distance_km")
    elev    = stage.get("elevation_gain_m") or stage.get("elev_gain")
    rwgps   = stage.get("route_id") or stage.get("rwgps_id")
    nocleg  = stage.get("nocleg") or stage.get("accommodation")
    notes   = stage.get("notes","")
    d       = stage.get("date","")

    lines = [f"Etap {n}: {seg}"]
    if d: lines.append(f"  Data: {d}")
    if dist: lines.append(f"  Dystans: {dist} km")
    if elev: lines.append(f"  Przewyzszenie: +{elev} m")
    if rwgps: lines.append(f"  RWGPS: {rwgps}")
    if nocleg: lines.append(f"  Nocleg: {nocleg}")
    if notes: lines.append(f"  {notes}")
    lines.append(f"  [{plan_title}]")
    return "\n".join(lines)

def _format_all_stages(plan: dict) -> str:
    lines = [f"## {plan['title']}"]
    if plan.get("variant"): lines.append(f"Wariant: {plan['variant']}")
    lines.append("")
    for s in sorted(plan["stages"], key=lambda x: x.get("stage",0)):
        n    = s.get("stage","?")
        seg  = s.get("segment","?")
        dist = s.get("distance_km","?")
        d    = s.get("date","")
        rwgps = s.get("route_id") or s.get("rwgps_id","—")
        lines.append(f"  Etap {n} ({d}): {seg} | {dist} km | RWGPS: {rwgps}")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Główna funkcja — entry point dla handlera
# ---------------------------------------------------------------------------
def handle_trip_stages(question: str) -> dict:
    """
    Zwraca dict: {"answer": str, "data": dict, "sources": list}
    """
    ql = question.lower()

    # Wyodrębnij hint tripu (słowa kluczowe po 'etap', 'plan', 'wyjazd')
    trip_hint = None
    hint_m = re.search(r"(?:toskani\w*|tuscany|tour\w*|wyprawa\w*|wyjazd\s+(\w+))", ql)
    if hint_m:
        trip_hint = hint_m.group(0).split()[0]  # pierwsze słowo matcha

    # Pobierz plany
    plans = _fetch_route_stages(trip_hint)
    if not plans:
        plans = _fetch_route_stages()  # fallback — wszystkie
    if not plans:
        return {"answer":"Brak planów etapów w bazie.", "data":{}, "sources":["qbot_planning_facts"]}

    plan = plans[0]  # najnowszy / najlepiej pasujący

    # Wyodrębnij datę referencyjną
    ref_date = date.today()
    date_m = re.search(r"(\d{4}-\d{2}-\d{2})", question)
    if date_m:
        ref_date = date.fromisoformat(date_m.group(1))
    elif "jutro" in ql:
        ref_date = date.today() + timedelta(days=1)
    elif "wczoraj" in ql:
        ref_date = date.today() - timedelta(days=1)

    # Wyodrębnij numer etapu
    stage_num_m = re.search(r"etap\s+(\d+)", ql)
    stage_num = int(stage_num_m.group(1)) if stage_num_m else None

    # Tryb: pełny plan vs konkretny etap
    if any(w in ql for w in ["plan","wszystkie","lista etap","pelny","cały plan","caly plan"]):
        answer = _format_all_stages(plan)
        return {"answer": answer, "data": {"plan": plan}, "sources":["qbot_planning_facts"]}

    # Konkretny etap wg numeru
    if stage_num:
        stage = _match_stage_by_number(plan["stages"], stage_num)
        if not stage:
            return {"answer":f"Brak etapu {stage_num} w planie '{plan['title']}'.",
                    "data":{}, "sources":["qbot_planning_facts"]}
        return {"answer": _format_stage(stage, plan["title"]),
                "data": {"stage": stage, "plan_title": plan["title"]},
                "sources":["qbot_planning_facts"]}

    # Etap wg daty (dziś/jutro/data)
    stage = _match_stage_by_date(plan["stages"], ref_date)
    if stage:
        # Sprawdź aktywny event dla kontekstu
        event = _fetch_active_event(ref_date)
        event_info = f"\nEvent: {event['title']} ({event['date_start']} – {event['date_end']})" if event else ""
        answer = _format_stage(stage, plan["title"]) + event_info
        return {"answer": answer,
                "data": {"stage": stage, "plan_title": plan["title"], "event": event},
                "sources":["qbot_planning_facts"]}

    # Brak etapu na dziś — sprawdź czy event jest aktywny
    event = _fetch_active_event(ref_date)
    if event:
        days_in = (ref_date - event["date_start"]).days + 1
        days_left = (event["date_end"] - ref_date).days
        answer = (f"Event aktywny: {event['title']}\n"
                  f"Dzien {days_in} z {(event['date_end']-event['date_start']).days+1}\n"
                  f"Pozostalo: {days_left} dni\n\n"
                  f"Brak etapu przypisanego do daty {ref_date} w planie '{plan['title']}'.")
    else:
        # Znajdź następny etap
        upcoming = sorted(
            [s for s in plan["stages"] if s.get("date","") > ref_date.isoformat()],
            key=lambda x: x.get("date","")
        )
        if upcoming:
            next_s = upcoming[0]
            days_to = (date.fromisoformat(next_s["date"]) - ref_date).days
            answer = (f"Brak etapu na {ref_date}.\n"
                      f"Nastepny: Etap {next_s.get('stage','?')} za {days_to} dni "
                      f"({next_s.get('date','?')}): {next_s.get('segment','?')}")
        else:
            answer = f"Brak etapu na {ref_date} i brak nadchodzących etapów w planie '{plan['title']}'."

    return {"answer": answer, "data": {"ref_date": ref_date.isoformat(), "plan_title": plan["title"]},
            "sources":["qbot_planning_facts"]}


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "dzisiejszy etap toskania"
    r = handle_trip_stages(q)
    print(r["answer"])
