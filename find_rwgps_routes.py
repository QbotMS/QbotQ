#!/usr/bin/env python3
import subprocess, json

api_key = subprocess.check_output(
    "source /etc/qbot/qbot-api.env && echo $RWGPS_API_KEY",
    shell=True, executable='/bin/bash').decode().strip()
auth_token = subprocess.check_output(
    "source /etc/qbot/qbot-api.env && echo $RWGPS_AUTH_TOKEN",
    shell=True, executable='/bin/bash').decode().strip()

import httpx
all_routes = []
for offset in range(0, 500, 50):
    url = f"https://ridewithgps.com/users/1040578/routes.json?apikey={api_key}&auth_token={auth_token}&version=2&limit=50&offset={offset}"
    r = httpx.get(url, timeout=15)
    routes = r.json().get('results', [])
    if not routes:
        print(f"offset {offset}: empty, stopping")
        break
    all_routes.extend(routes)
    print(f"offset {offset}: {len(routes)} routes, last_id={routes[-1].get('id')} last_updated={routes[-1].get('updated_at','')[:10]}")

print(f"\nTotal: {len(all_routes)} routes")
print("\nToskania routes:")
for r in all_routes:
    if 'Toskania' in r.get('name', '') or 'Etap 0' in r.get('name', ''):
        print(f"  {r.get('id')} | {r.get('name','?')[:60]} | {r.get('updated_at','')[:10]}")
