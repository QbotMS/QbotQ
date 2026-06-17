#!/usr/bin/env python3
"""Fix: garażu w garage_status matchuje 'szukaj kasków w garażu'. 
Fix: get_route używa właściwego env dla RWGPS."""
import ast

QH = '/opt/qbot/app/qbot_query_handler.py'
lines = open(QH, encoding='utf-8').readlines()

# Linia 238 (0-indexed 237): garage_status — usuń "gara\u017cu" (garażu), zostaw tylko "gara\u017c"
old_gs = '    (["gara\u017c", "garage", "sprz\u0119t", "sprzet", "rower", "rowery", "wyposa\u017cenie", "status gara\u017cu", "co mam w gara\u017cu"], "garage_status"),\n'
new_gs = '    (["gara\u017c", "garage", "sprz\u0119t", "sprzet", "rower", "rowery", "wyposa\u017cenie"], "garage_status"),\n'

if lines[237] == old_gs:
    lines[237] = new_gs
    print("OK: removed garażu from garage_status")
else:
    print("MISS gs:", repr(lines[237][:80]))

content = ''.join(lines)
ast.parse(content)
open(QH, 'w', encoding='utf-8').write(content)
print("syntax OK")

# Fix feasibility get_route — użyj zmiennych środowiskowych zamiast .env.local
FEAS = '/opt/qbot/app/tools/feasibility.py'
fc = open(FEAS, encoding='utf-8').read()

old_rwgps_env = '''def _rwgps_env() -> dict:
    """Załaduj credentials RWGPS z .env.local lub zmiennych środowiskowych."""
    env = {}
    try:
        for line in open("/opt/qbot/app/.env.local"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    except Exception:
        pass
    env.setdefault("RWGPS_API_KEY", os.environ.get("RWGPS_API_KEY", ""))
    env.setdefault("RWGPS_AUTH_TOKEN", os.environ.get("RWGPS_AUTH_TOKEN", ""))
    return env'''

new_rwgps_env = '''def _rwgps_env() -> dict:
    """Załaduj credentials RWGPS ze zmiennych środowiskowych lub .env."""
    env = {
        "RWGPS_API_KEY": os.environ.get("RWGPS_API_KEY", ""),
        "RWGPS_AUTH_TOKEN": os.environ.get("RWGPS_AUTH_TOKEN", ""),
    }
    # Fallback: próbuj różne pliki .env
    for env_file in ["/opt/qbot/app/.env", "/opt/qbot/app/.env.local", "/etc/qbot/qbot-api.env"]:
        try:
            for line in open(env_file):
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    k = k.strip(); v = v.strip().strip('"').strip("'")
                    if k in ("RWGPS_API_KEY", "RWGPS_AUTH_TOKEN") and not env[k]:
                        env[k] = v
        except Exception:
            pass
    return env'''

if old_rwgps_env in fc:
    fc = fc.replace(old_rwgps_env, new_rwgps_env, 1)
    ast.parse(fc)
    open(FEAS, 'w', encoding='utf-8').write(fc)
    print("OK: _rwgps_env reads multiple env files")
else:
    print("FAIL: _rwgps_env block not found")
