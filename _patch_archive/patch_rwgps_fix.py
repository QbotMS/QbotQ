#!/usr/bin/env python3
"""Fix _handle_rwgps_recent_routes — odpytaj known route_ids z planning_facts zamiast paginować całą listę."""
import ast
lines = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').readlines()

# Znajdź funkcję i zastąp całe ciało
start = None
for i, l in enumerate(lines):
    if 'def _handle_rwgps_recent_routes(question: str) -> dict:' in l:
        start = i
        break

if start is None:
    print("FAIL: function not found")
    exit(1)

# Znajdź koniec funkcji (następna def na poziomie 0)
end = start + 1
while end < len(lines):
    if lines[end].startswith('def ') and end > start + 2:
        break
    end += 1

new_fn = (
    'def _handle_rwgps_recent_routes(question: str) -> dict:\n'
    '    """Lista tras RWGPS z ostatnich N dni — z planning_facts + RWGPS API."""\n'
    '    import re, httpx, os, json\n'
    '    from datetime import datetime, timezone, timedelta\n'
    '    ql = question.lower()\n'
    '    days = 7\n'
    '    m = re.search(r"(\\d+)\\s*(?:dni|tygod)", ql)\n'
    '    if m:\n'
    '        n = int(m.group(1))\n'
    '        days = n * 7 if "tygod" in ql[m.start():m.start()+20] else n\n'
    '    elif "miesi" in ql:\n'
    '        days = 30\n'
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
    '\n'
    '        # Pobierz route_id z planning_facts\n'
    '        pg = _pg_conn()\n'
    '        rows = _safe_fetch(pg, """\n'
    '            SELECT fact_json->>\'stages\' as stages_json\n'
    '            FROM qbot_v2.qbot_planning_facts\n'
    '            WHERE fact_type=\'route_stages\'\n'
    '            ORDER BY date DESC LIMIT 1\n'
    '        """)\n'
    '        pg.close()\n'
    '        known_ids = []\n'
    '        if rows and rows[0].get("stages_json"):\n'
    '            stages = json.loads(rows[0]["stages_json"])\n'
    '            known_ids = [str(s.get("route_id")) for s in stages if s.get("route_id")]\n'
    '\n'
    '        # Sprawdź każdy known route_id w RWGPS\n'
    '        cutoff = datetime.now(timezone.utc) - timedelta(days=days)\n'
    '        recent = []\n'
    '        for rid in known_ids:\n'
    '            try:\n'
    '                url = (f"https://ridewithgps.com/routes/{rid}.json"\n'
    '                       f"?apikey={api_key}&auth_token={auth_token}&version=2")\n'
    '                resp = httpx.get(url, timeout=10.0)\n'
    '                if resp.status_code != 200:\n'
    '                    continue\n'
    '                r = resp.json().get("route", {})\n'
    '                upd = r.get("updated_at", "")\n'
    '                if upd:\n'
    '                    dt = datetime.fromisoformat(upd.replace("Z", "+00:00"))\n'
    '                    recent.append({\n'
    '                        "id": r.get("id"), "name": r.get("name", "?"),\n'
    '                        "distance_km": round(r.get("distance", 0) / 1000, 1),\n'
    '                        "elevation_gain": r.get("elevation_gain", 0),\n'
    '                        "updated_at": upd[:10],\n'
    '                        "url": f"https://ridewithgps.com/routes/{rid}",\n'
    '                        "recent": dt > cutoff,\n'
    '                    })\n'
    '            except Exception:\n'
    '                pass\n'
    '\n'
    '        if not recent:\n'
    '            return _envelope("rwgps_recent_routes",\n'
    '                f"Brak tras RWGPS w planning_facts. Znane ID: {known_ids}",\n'
    '                data={"days": days, "known_ids": known_ids})\n'
    '\n'
    '        recent.sort(key=lambda x: x["updated_at"], reverse=True)\n'
    '        recent_only = [r for r in recent if r["recent"]]\n'
    '        label = f"ostatnich {days} dni" if recent_only else "z planning_facts"\n'
    '        show = recent_only if recent_only else recent\n'
    '\n'
    '        parts = [f"\\U0001f5fa\\ufe0f Trasy RWGPS ({label}, {len(show)} tras):"]\n'
    '        for r in show:\n'
    '            flag = "" if r["recent"] else " (starszy ni\u017c 7 dni)"\n'
    '            parts.append(f"  \u2022 [{r[\'updated_at\']}] {r[\'name\']} "\n'
    '                        f"— {r[\'distance_km\']} km, +{r[\'elevation_gain\']}m{flag}")\n'
    '            parts.append(f"    ID: {r[\'id\']} | {r[\'url\']}")\n'
    '\n'
    '        return _envelope("rwgps_recent_routes", "\\n".join(parts),\n'
    '            data={"days": days, "count": len(show), "routes": show},\n'
    '            sources_used=["rwgps", "qbot_v2.qbot_planning_facts"])\n'
    '    except Exception as exc:\n'
    '        return _envelope("rwgps_recent_routes", f"B\u0142\u0105d RWGPS: {exc}", status_override="ERROR")\n'
    '\n'
    '\n'
)

lines[start:end] = [new_fn]
content = ''.join(lines)
ast.parse(content)
open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
print("OK: _handle_rwgps_recent_routes rewritten, syntax OK")
