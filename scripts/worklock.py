#!/usr/bin/env python3
"""worklock -- mini tablica robocza dla sesji QBota.

Cel: sesje OGLASZAJA, ktore pliki EDYTUJA, zeby dwie sesje nie pisaly do tego
samego pliku naraz. To OSTRZEZENIE, nie fizyczny zamek -- dziala, bo sesje
sprawdzaja tablice przed edycja (regula w CLAUDE.md / CONTEXT). Czytanie i
analiza sa zawsze bezpieczne -- zajmuje sie TYLKO to, co sie edytuje.

Uzycie:
  python3 scripts/worklock.py status
  python3 scripts/worklock.py claim --who NAZWA --task "opis" --files a.py b.py
  python3 scripts/worklock.py release --who NAZWA
  python3 scripts/worklock.py release --who NAZWA --files a.py

claim konczy sie kodem 2, gdy ktorys plik jest juz zajety przez INNA sesje.
Zajecia starsze niz 30 min sa ignorowane (sesja pewnie padla).
Stan: /opt/qbot/app/.worklock.json (poza repo).
"""
import argparse, json, os, sys, time, fcntl

STATE = "/opt/qbot/app/.worklock.json"
STALE_SEC = 30 * 60


def _load(fh):
    fh.seek(0)
    data = fh.read()
    if not data.strip():
        return []
    try:
        return json.loads(data)
    except Exception:
        return []


def _prune(claims):
    now = time.time()
    return [c for c in claims if now - c.get("ts", 0) < STALE_SEC]


def _save(fh, claims):
    fh.seek(0)
    fh.truncate()
    fh.write(json.dumps(claims, ensure_ascii=False, indent=2))
    fh.flush()
    os.fsync(fh.fileno())


def _age(ts):
    m = int((time.time() - ts) // 60)
    return f"{m} min temu" if m else "przed chwila"


def _open():
    fd = open(STATE, "a+")
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def cmd_status(a):
    fh = _open()
    try:
        claims = _prune(_load(fh))
        _save(fh, claims)
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()
    if not claims:
        print("TABLICA PUSTA -- nikt nic nie edytuje.")
        return 0
    print("W ROBOCIE:")
    for c in claims:
        files = ", ".join(c.get("files", []))
        print(f"  [{c['who']}] {files}  -- {c.get('task','')}  ({_age(c['ts'])})")
    return 0


def cmd_claim(a):
    who, files = a.who, a.files
    fh = _open()
    try:
        claims = _prune(_load(fh))
        conflicts = []
        for c in claims:
            if c["who"] == who:
                continue
            for f in files:
                if f in c.get("files", []):
                    conflicts.append((f, c))
        if conflicts:
            print("ZAJETE -- nie zajmuje. Poczekaj albo uzgodnij:")
            seen = set()
            for f, c in conflicts:
                key = (f, c["who"])
                if key in seen:
                    continue
                seen.add(key)
                print(f"  {f} -> trzyma [{c['who']}] ({c.get('task','')}, {_age(c['ts'])})")
            return 2
        mine = next((c for c in claims if c["who"] == who), None)
        if mine is None:
            mine = {"who": who, "files": [], "task": a.task or "", "ts": time.time()}
            claims.append(mine)
        mine["files"] = list(dict.fromkeys(mine.get("files", []) + files))
        if a.task:
            mine["task"] = a.task
        mine["ts"] = time.time()
        _save(fh, claims)
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()
    print(f"OK -- zajete przez [{who}]: {', '.join(files)}")
    return 0


def cmd_release(a):
    who = a.who
    fh = _open()
    try:
        claims = _prune(_load(fh))
        if a.files:
            for c in claims:
                if c["who"] == who:
                    c["files"] = [f for f in c.get("files", []) if f not in a.files]
            claims = [c for c in claims if c.get("files")]
            msg = f"zwolniono {', '.join(a.files)} dla [{who}]"
        else:
            claims = [c for c in claims if c["who"] != who]
            msg = f"zwolniono wszystko dla [{who}]"
        _save(fh, claims)
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()
    print("OK -- " + msg)
    return 0


def main():
    p = argparse.ArgumentParser(description="Mini tablica robocza sesji QBota")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status)
    c = sub.add_parser("claim"); c.set_defaults(fn=cmd_claim)
    c.add_argument("--who", required=True)
    c.add_argument("--task", default="")
    c.add_argument("--files", nargs="+", required=True)
    r = sub.add_parser("release"); r.set_defaults(fn=cmd_release)
    r.add_argument("--who", required=True)
    r.add_argument("--files", nargs="*")
    a = p.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
