#!/usr/bin/env python3
"""Worker raportu z jazdy: W1 -> W2 -> Telegram skrot + mail. Uzycie: ride_report_worker.py <ride_key> [--no-tg] [--no-mail]"""
import sys, json; sys.path.insert(0, "/opt/qbot/app")
from qbot3.rides.ride_report_notify import run_worker
if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args: print("brak ride_key"); sys.exit(2)
    r = run_worker(args[0], send_tg="--no-tg" not in sys.argv, send_mail="--no-mail" not in sys.argv)
    print(json.dumps(r, ensure_ascii=False)); sys.exit(0 if r.get("ok") else 1)
