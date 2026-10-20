#!/usr/bin/env python3
"""Straznik MacOS-MCP - obserwator (LaunchAgent co 10 min, sesja devmcp-2010).
1) MacOS-MCP uruchomione z pominieciem straznika -> powiadomienie.
2) Po 21:00 raz dziennie: podsumowanie dnia z dziennika -> plik + powiadomienie.
"""
import json, os, subprocess
from collections import Counter
from datetime import datetime

HOME = os.path.expanduser("~")
LOGDIR = os.path.join(HOME, "Library", "Logs", "qbot-guard")
LOG = os.path.join(LOGDIR, "macos-mcp.jsonl")
STATE = os.path.join(HOME, ".qbot-guard", "watch_state.json")


def notify(text, title="Straznik MacOS-MCP"):
    q = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(["osascript", "-e", 'display notification "%s" with title "%s" sound name "Basso"'
                    % (q(text[:220]), q(title))], capture_output=True, timeout=10)


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def check_bypass(st):
    out = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True).stdout
    procs = {}
    for line in out.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3:
            procs[parts[0]] = (parts[1], parts[2])
    warned = set(st.get("warned", []))
    for pid, (ppid, cmd) in procs.items():
        if "macos-mcp serve" not in cmd or "uv " in cmd and "--directory" not in cmd:
            continue
        chain, cur, ok = 0, ppid, False
        while cur in procs and chain < 6:
            if "macos_mcp_guard.py" in procs[cur][1]:
                ok = True
                break
            cur = procs[cur][0]
            chain += 1
        if not ok and pid not in warned:
            notify("MacOS-MCP dziala Z POMINIECIEM straznika (pid %s). Sprawdz Ustawienia > Rozszerzenia w Claude." % pid)
            warned.add(pid)
    st["warned"] = sorted(warned)[-50:]


def summary(st):
    now = datetime.now()
    day = now.strftime("%Y-%m-%d")
    if now.hour < 21 or st.get("summary_day") == day:
        return
    calls, tools, apps, blocked, anomalies = 0, Counter(), Counter(), [], []
    try:
        for line in open(LOG, encoding="utf-8"):
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("ev") != "call" or not str(e.get("ts", "")).startswith(day):
                continue
            calls += 1
            tools[e.get("tool")] += 1
            if e.get("app"):
                apps[e.get("app")] += 1
            if e.get("decision") == "BLOK":
                blocked.append("%s %s (%s)" % (e["ts"][11:16], e.get("tool"), e.get("why")))
            for k in ("anomalia_nieobecnosc", "anomalia_haslo", "anomalia_nowa_domena"):
                if e.get(k):
                    anomalies.append("%s %s %s" % (e["ts"][11:16], k.replace("anomalia_", ""), e.get(k) if k.endswith("domena") else e.get("tool")))
    except FileNotFoundError:
        pass
    lines = ["Straznik MacOS-MCP - podsumowanie %s" % day, "Akcje: %d" % calls,
             "Narzedzia: " + ", ".join("%s %d" % kv for kv in tools.most_common()),
             "Aplikacje: " + ", ".join("%s %d" % kv for kv in apps.most_common(8)),
             "Zablokowane (%d):" % len(blocked)] + ["  " + b for b in blocked] + \
            ["Nietypowe (%d):" % len(anomalies)] + ["  " + a for a in anomalies]
    os.makedirs(LOGDIR, exist_ok=True)
    with open(os.path.join(LOGDIR, "podsumowanie-%s.txt" % day), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    if calls:
        notify("Dzis: %d akcji, %d zablokowanych, %d nietypowych. Szczegoly: ~/Library/Logs/qbot-guard/" % (
            calls, len(blocked), len(anomalies)), "Straznik - podsumowanie dnia")
    st["summary_day"] = day


def main():
    st = load_state()
    try:
        check_bypass(st)
    except Exception:
        pass
    try:
        summary(st)
    except Exception:
        pass
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w"))


if __name__ == "__main__":
    main()
