#!/usr/bin/env python3
"""Dodaj intent rwgps_recent_routes — lista tras z ostatnich N dni."""
import ast, shutil, datetime

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
QH = '/opt/qbot/app/qbot_query_handler.py'
with open(QH, encoding='utf-8') as f:
    qh = f.read()
shutil.copy(QH, f'{QH}.bak.rwgps.{ts}')

# 1. Dodaj keyword intent
old_kw = '    (["podjazdy", "climb", "podjazd", "wzniesienia", "przewyższenia na trasie"], "route_climbs"),'
new_kw = (
    '    (["trasy rwgps", "moje trasy", "ostatnie trasy", "nowe trasy", "trasy z ostatniego",\n'
    '      "trasy zbudowane", "trasy ułożone", "trasy w rwgps", "historia tras",\n'
    '      "co układałem", "co tworzyłem w rwgps"], "rwgps_recent_routes"),\n'
    '    (["podjazdy", "climb", "podjazd", "wzniesienia", "przewyższenia na trasie"], "route_climbs"),\n'
)
if old_kw in qh:
    qh = qh.replace(old_kw, new_kw, 1)
    print("OK: rwgps_recent_routes keyword added")
else:
    print("FAIL kw: not found")

# 2. Dodaj handler
old_climbs_def = 'def _handle_route_climbs(question: str) -> dict:'
new_handler = (
    'def _handle_rwgps_recent_routes(question: str) -> dict:\n'
    '    """Lista tras RWGPS z ostatnich N dni (domyślnie 7)."""\n'
    '    import re, httpx, os\n'
    '    from datetime import datetime, timezone, timedelta\n'
    '    ql = question.lower()\n'
    '    days = 30\n'
    '    m = re.search(r"(\\d+)\\s*(?:dni|d\\b|tygod)", ql)\n'
    '    if m:\n'
    '        n = int(m.group(1))\n'
    '        days = n * 7 if "tygod" in ql[m.start():m.start()+20] else n\n'
    '    elif "tydzie" in ql or "tydzien" in ql:\n'
    '        days = 7\n'
    '    cutoff = datetime.now(timezone.utc) - timedelta(days=days)\n'
    '    try:\n'
    '        env = {}\n'
    '        for ef in ["/opt/qbot/app/.env", "/etc/qbot/qbot-api.env"]:\n'
    '            try:\n'
    '                for line in open(ef):\n'
    '                    if "=" in line and not line.startswith("#"):\n'
    '                        k, _, v = line.strip().partition("=")\n'
    '                        env[k] = v\n'
    '            except Exception:\n'
    '                pass\n'
    '        api_key = env.get("RWGPS_API_KEY", os.getenv("RWGPS_API_KEY", ""))\n'
    '        auth_token = env.get("RWGPS_AUTH_TOKEN", os.getenv("RWGPS_AUTH_TOKEN", ""))\n'
    '        user_id = env.get("RWGPS_USER_ID", os.getenv("RWGPS_USER_ID", "1040578"))\n'
    '        # Pobierz ostatnie 50 tras (RWGPS nie sortuje po dacie — skanujemy od końca)\n'
    '        recent = []\n'
    '        for offset in range(0, 500, 50):\n'
    '            url = (f"https://ridewithgps.com/users/{user_id}/routes.json"\n'
    '                   f"?apikey={api_key}&auth_token={auth_token}&version=2&limit=50&offset={offset}")\n'
    '            resp = httpx.get(url, timeout=15.0)\n'
    '            routes = resp.json().get("results", [])\n'
    '            if not routes:\n'
    '                break\n'
    '            for r in routes:\n'
    '                upd = r.get("updated_at", "")\n'
    '                if upd:\n'
    '                    try:\n'
    '                        dt = datetime.fromisoformat(upd.replace("Z", "+00:00"))\n'
    '                        if dt > cutoff:\n'
    '                            recent.append(r)\n'
    '                    except Exception:\n'
    '                        pass\n'
    '            # Jeśli wszystkie trasy w batchu są starsze niż cutoff — stop\n'
    '            oldest = routes[-1].get("updated_at", "")\n'
    '            if oldest:\n'
    '                try:\n'
    '                    if datetime.fromisoformat(oldest.replace("Z", "+00:00")) < cutoff - timedelta(days=365):\n'
    '                        break\n'
    '                except Exception:\n'
    '                    pass\n'
    '        if not recent:\n'
    '            return _envelope("rwgps_recent_routes",\n'
    '                f"Brak tras RWGPS zaktualizowanych w ostatnich {days} dniach.",\n'
    '                data={"days": days, "count": 0})\n'
    '        parts = [f"\\U0001f5fa\\ufe0f Trasy RWGPS z ostatnich {days} dni ({len(recent)} tras):"]\n'
    '        for r in sorted(recent, key=lambda x: x.get("updated_at",""), reverse=True):\n'
    '            km = round(r.get("distance", 0) / 1000, 1)\n'
    '            elev = r.get("elevation_gain", 0)\n'
    '            upd = r.get("updated_at", "")[:10]\n'
    '            rid = r.get("id")\n'
    '            name = r.get("name", "?")\n'
    '            parts.append(f"  • [{upd}] {name} — {km} km, +{elev}m | ID: {rid}")\n'
    '            parts.append(f"    https://ridewithgps.com/routes/{rid}")\n'
    '        return _envelope("rwgps_recent_routes", "\\n".join(parts),\n'
    '            data={"days": days, "count": len(recent),\n'
    '                  "routes": [{"id": r.get("id"), "name": r.get("name"),\n'
    '                              "km": round(r.get("distance",0)/1000,1),\n'
    '                              "updated_at": r.get("updated_at","")} for r in recent]},\n'
    '            sources_used=["rwgps"])\n'
    '    except Exception as exc:\n'
    '        return _envelope("rwgps_recent_routes", f"Błąd RWGPS API: {exc}", status_override="ERROR")\n'
    '\n'
    '\n'
    'def _handle_route_climbs(question: str) -> dict:\n'
)
if old_climbs_def in qh:
    qh = qh.replace(old_climbs_def, new_handler, 1)
    print("OK: _handle_rwgps_recent_routes added")
else:
    print("FAIL handler: not found")

# 3. Dispatch
old_dispatch = '    elif intent == "route_climbs":'
new_dispatch = (
    '    elif intent == "rwgps_recent_routes":\n'
    '        return _handle_rwgps_recent_routes(question)\n'
    '    elif intent == "route_climbs":\n'
)
if old_dispatch in qh:
    qh = qh.replace(old_dispatch, new_dispatch, 1)
    print("OK: dispatch added")
else:
    print("FAIL dispatch")

ast.parse(qh)
with open(QH, 'w', encoding='utf-8') as f:
    f.write(qh)
print("syntax OK")
