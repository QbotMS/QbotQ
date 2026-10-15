#!/usr/bin/env python3
"""Cotygodniowy audyt QBota (etap 5, 15.10.2026) -- bezpiecznik, zeby balagan nie wracal.

Co robi (noc pon, timer qbot-weekly-audit):
  1. sprzata kopie .bak / _tmp_ starsze niz 7 dni -> /opt/qbot/_archiwum/<data>/ (scripts/cleanup_bak.py; nic nie kasuje)
  2. puszcza caly zestaw testow (pytest, katalog tests/)
  3. liczy kandydatow na martwy kod (scripts/audit_deadcode.py)
  4. sprawdza status funkcji (qbot_status_checks.all_checks)
Wynik: state/weekly_audit.json (czyta go SETUP > Polaczenia > Status, pozycja "Audyt tygodniowy").
Telegram: JEDNA wiadomosc tylko gdy jest NOWY problem (nowe padniete testy albo funkcja 'nie dziala'); cisza, gdy wszystko OK.
Recznie: cd /opt/qbot/app && .venv/bin/python3 scripts/weekly_audit.py [--no-telegram]
Dok.: docs/STATUS.md
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime

APP = "/opt/qbot/app"
PY = APP + "/.venv/bin/python3"
STATE = APP + "/state/weekly_audit.json"
sys.path.insert(0, APP)
os.chdir(APP)


def run(cmd, timeout):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=APP)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return -1, f"BLAD: {e}"


def main() -> int:
    notify = "--no-telegram" not in sys.argv
    prev = {}
    try:
        prev = json.load(open(STATE, encoding="utf-8"))
    except Exception:
        pass
    res = {"at": datetime.now().isoformat(timespec="seconds")}

    rc, out = run([PY, "scripts/cleanup_bak.py", "--apply", "--keep-hours", "168"], 120)
    m = re.search(r"do archiwum: (\d+) plikow, ([\d.]+) MB", out)
    res["cleanup_files"], res["cleanup_mb"] = (int(m.group(1)), float(m.group(2))) if m else (None, None)

    rc, out = run([PY, "-m", "pytest", "-q", "-p", "no:warnings", "-rf"], 900)
    tail = out.strip().splitlines()[-1] if out.strip() else ""
    num = lambda w: int(re.search(r"(\d+) " + w, tail).group(1)) if re.search(r"(\d+) " + w, tail) else 0
    res["tests_passed"], res["tests_failed"], res["tests_errors"] = num("passed"), num("failed"), num("error")
    res["tests_failed_list"] = sorted(set(re.findall(r"^(?:FAILED|ERROR) (\S+)", out, re.M)))[:30]

    # 15.10.2026: testy i narzedzia dzialaja jako root -> pliki analiz w artifacts/analysis bywaja root-owned,
    # a serwis www (qbot) nie moze ich potem nadpisac (blad 500 przy przebudowie raportu z jazdy). Oddajemy je qbotowi.
    try:
        import pwd, grp
        uid, gid = pwd.getpwnam("qbot").pw_uid, grp.getgrnam("qbot").gr_gid
        n = 0
        for dp, dns, fns in os.walk("/opt/qbot/artifacts/analysis"):
            for x in [dp] + [os.path.join(dp, f) for f in fns]:
                if os.lstat(x).st_uid == 0:
                    os.chown(x, uid, gid); n += 1
        res["chown_fixed"] = n
    except Exception as e:
        res["chown_fixed"] = f"blad: {type(e).__name__}"

    rc, out = run([PY, "scripts/audit_deadcode.py"], 120)
    m = re.search(r"A: (\d+) \| B: (\d+)", out)
    res["dead_candidates"] = int(m.group(1)) if m else None

    try:
        from qbot_status_checks import all_checks
        st = all_checks()
        res["status_overall"] = st["overall"]
        res["status_problems"] = [f"{i['name']}: {i['text']}" for i in st["items"] if i["state"] in ("bad", "warn")]
    except Exception as e:
        res["status_overall"], res["status_problems"] = "warn", [f"status: {type(e).__name__}"]

    bad_now = set(res["tests_failed_list"])
    new_fail = sorted(bad_now - set(prev.get("tests_failed_list") or []))
    res["new_failures"] = new_fail
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(res, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    problems = []
    if new_fail:
        problems.append(f"Nowe padniete testy ({len(new_fail)}): " + ", ".join(t.split("::")[-1] for t in new_fail[:5]))
    if res["status_overall"] == "bad":
        problems += res["status_problems"][:3]
    if problems and notify:
        try:
            import requests
            import qbot_config as cfg
            txt = "🧹 Audyt tygodniowy QBota: " + " | ".join(problems) + " — szczegóły: SETUP › Połączenia › Status."
            requests.post(f"https://api.telegram.org/bot{cfg.TELEGRAM_TOKEN}/sendMessage",
                          json={"chat_id": cfg.TELEGRAM_CHAT_ID, "text": txt}, timeout=15)
        except Exception as e:
            print("telegram nieudany:", e)
    print(json.dumps({k: v for k, v in res.items() if k != "tests_failed_list"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
