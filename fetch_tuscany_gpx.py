#!/usr/bin/env python3
"""Pobierz GPX etapów Toskanii z RWGPS i zapisz jako artefakty canonical."""
import subprocess, httpx, os, json
from datetime import datetime

# Env
api_key = subprocess.check_output(
    "source /etc/qbot/qbot-api.env && echo $RWGPS_API_KEY",
    shell=True, executable='/bin/bash').decode().strip()
auth_token = subprocess.check_output(
    "source /etc/qbot/qbot-api.env && echo $RWGPS_AUTH_TOKEN",
    shell=True, executable='/bin/bash').decode().strip()

# Etapy z planning_facts (zaktualizowane)
stages = [
    {"stage": 1, "route_id": "55395117", "segment": "Scandicci → Capannoli"},
    {"stage": 2, "route_id": "55444268", "segment": "Capannoli → Castagneto Carducci"},
    {"stage": 3, "route_id": "55444735", "segment": "Castagneto → Castiglione della Pescaia"},
    {"stage": 4, "route_id": "55395123", "segment": "Castiglione della Pescaia → Paganico"},
    {"stage": 5, "route_id": "55395124", "segment": "Paganico → Pienza"},
    {"stage": 6, "route_id": "55395125", "segment": "Pienza → Monteriggioni"},
    {"stage": 7, "route_id": "55395129", "segment": "Monteriggioni → Scandicci"},
]

canonical_dir = "/opt/qbot/artifacts/canonical/tuscany_2026/gpx"
os.makedirs(canonical_dir, exist_ok=True)

results = []
for s in stages:
    rid = s["route_id"]
    stage_n = s["stage"]
    segment = s["segment"]
    
    url = f"https://ridewithgps.com/routes/{rid}.gpx?apikey={api_key}&auth_token={auth_token}&version=2&sub_format=track"
    try:
        resp = httpx.get(url, timeout=20.0)
        if resp.status_code == 200 and resp.text.startswith("<?xml"):
            fname = f"tuscany_2026_stage_{stage_n:02d}_{rid}.gpx"
            fpath = os.path.join(canonical_dir, fname)
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(resp.text)
            size = len(resp.text)
            print(f"  OK: Stage {stage_n} ({rid}) → {fname} ({size//1024} KB)")
            results.append({"stage": stage_n, "route_id": rid, "segment": segment, 
                           "file": fpath, "status": "OK", "size_kb": size//1024})
        else:
            print(f"  FAIL: Stage {stage_n} ({rid}) → HTTP {resp.status_code}")
            results.append({"stage": stage_n, "route_id": rid, "segment": segment,
                           "status": f"HTTP_{resp.status_code}"})
    except Exception as e:
        print(f"  ERROR: Stage {stage_n} ({rid}) → {e}")
        results.append({"stage": stage_n, "route_id": rid, "segment": segment, "status": f"ERROR: {e}"})

# Zarejestruj w qbot_v2.artifacts
import psycopg
from psycopg.rows import dict_row
conn = psycopg.connect(
    host="127.0.0.1", port="5432", dbname="qbot", user="qbot",
    password=subprocess.check_output(
        "source /etc/qbot/qbot-api.env && echo $PGPASSWORD",
        shell=True, executable='/bin/bash').decode().strip(),
    row_factory=dict_row, options="-c search_path=qbot_v2"
)
import uuid, hashlib

registered = 0
for r in results:
    if r["status"] != "OK":
        continue
    rel_path = f"canonical/tuscany_2026/gpx/{os.path.basename(r['file'])}"
    title = f"Tuscany 2026 Stage {r['stage']:02d} GPX — {r['segment']}"
    artifact_id = str(uuid.uuid5(uuid.NAMESPACE_URL, rel_path))
    
    with conn:
        conn.execute("""
            INSERT INTO artifacts (artifact_id, project_id, artifact_type, title, file_path, status, created_at)
            VALUES (%s, %s, %s, %s, %s, 'active', NOW())
            ON CONFLICT (artifact_id) DO UPDATE SET
                title=EXCLUDED.title, file_path=EXCLUDED.file_path,
                status='active', created_at=NOW()
        """, (artifact_id, "tuscany_2026", "gpx", title, rel_path))
    registered += 1
    print(f"  DB: {title}")

conn.close()
print(f"\nGotowe: {len([r for r in results if r['status']=='OK'])}/7 GPX pobranych, {registered} zarejestrowanych w DB")
print(f"Ścieżka: {canonical_dir}")
