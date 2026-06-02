"""
tools/trip_attractions.py
Handler: atrakcje/POI z qbot_planning_facts (fact_type LIKE 'poi_%').
"""
from __future__ import annotations
import json, os, re
from datetime import date
from typing import Optional

def _pg():
    import psycopg
    return psycopg.connect(
        host=os.getenv("PGHOST","127.0.0.1"), port=os.getenv("PGPORT","5432"),
        dbname=os.getenv("PGDATABASE","qbot"), user=os.getenv("PGUSER","qbot"),
        password=os.getenv("PGPASSWORD",""), connect_timeout=5,
        options="-c search_path=qbot_v2",
    )

def _fetch_poi_facts(trip_hint: str = None, stage_n: int = None) -> list[dict]:
    conn = _pg()
    try:
        cur = conn.cursor()
        where = ["fact_type LIKE 'poi_%%'"]
        params = []
        if trip_hint:
            where.append("LOWER(title) LIKE %s")
            params.append("%" + trip_hint.lower() + "%")
        if stage_n is not None:
            where.append("(LOWER(title) LIKE %s OR LOWER(title) LIKE %s)")
            params += ["%" + f"stage {stage_n:02d}" + "%", "%" + f"etap {stage_n}" + "%"]
        cur.execute(
            "SELECT id, date, title, fact_type, fact_json, status FROM qbot_planning_facts "
            "WHERE " + " AND ".join(where) + " ORDER BY date, id",
            params
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    results = []
    for row in rows:
        fj = row[4] if isinstance(row[4], dict) else json.loads(row[4] or "{}")
        results.append({
            "id": row[0], "date": row[1], "title": row[2],
            "fact_type": row[3], "data": fj, "status": row[5],
        })
    return results

def _format_poi_record(rec: dict) -> str:
    title = rec["title"]
    ftype = rec["fact_type"].replace("poi_","").replace("_"," ")
    data  = rec["data"]

    if not data:
        return f"[{ftype}] {title}\n  (brak danych — uzupelnij fact_json)"

    lines = [f"[{ftype}] {title}"]
    if isinstance(data, list):
        for item in data[:10]:
            name = item.get("name") or item.get("title","?")
            dist = item.get("distance_km") or item.get("detour_km","")
            km   = item.get("km") or item.get("km_approx","")
            note = item.get("note") or item.get("notes","")
            line = "  * " + str(name)
            if km: line += " (km~" + str(km) + ")"
            if dist: line += " +" + str(dist) + "km zjazd"
            if note: line += " — " + str(note)
            lines.append(line)
        if len(data) > 10:
            lines.append("  ... i " + str(len(data)-10) + " wiecej")
    elif isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, list):
                lines.append("  " + key + ":")
                for item in val[:5]:
                    if isinstance(item, dict):
                        lines.append("    * " + item.get("name","?"))
                    else:
                        lines.append("    * " + str(item))
            elif isinstance(val, (str,int,float)):
                lines.append("  " + str(key) + ": " + str(val))

    return "\n".join(lines)

def handle_trip_attractions(question: str) -> dict:
    ql = question.lower()

    trip_hint = None
    for kw in ["toskani","tuscany","tour","wyprawa","alps","dolomit"]:
        if kw in ql:
            trip_hint = kw
            break

    stage_m = re.search(r"etap\s+(\d+)", ql)
    stage_n = int(stage_m.group(1)) if stage_m else None

    km_m = re.search(r"km\s*(\d+)[-]\s*(\d+)", ql)

    records = _fetch_poi_facts(trip_hint, stage_n)
    if not records:
        records = _fetch_poi_facts()

    if not records:
        return {
            "answer": "Brak danych POI/atrakcji w bazie. Dodaj fakty fact_type='poi_*' przez qbot.action_execute.",
            "data": {}, "sources": ["qbot_planning_facts"]
        }

    if km_m:
        km_from, km_to = int(km_m.group(1)), int(km_m.group(2))
        filtered = []
        for rec in records:
            data = rec["data"]
            if isinstance(data, list):
                items_in_range = [
                    i for i in data
                    if km_from <= float(i.get("km") or i.get("km_approx") or 0) <= km_to
                ]
                if items_in_range:
                    filtered.append({**rec, "data": items_in_range})
            else:
                filtered.append(rec)
        records = filtered or records

    parts = [_format_poi_record(r) for r in records]
    answer = "\n\n".join(parts)
    return {
        "answer": answer,
        "data": {"count": len(records), "records": [r["id"] for r in records]},
        "sources": ["qbot_planning_facts"]
    }


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "atrakcje toskania"
    r = handle_trip_attractions(q)
    print(r["answer"])
