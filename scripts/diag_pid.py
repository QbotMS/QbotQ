#!/usr/bin/env python3
"""Czy proces o danym PID zyje i od kiedy dziala (bez ps).
  .venv/bin/python3 scripts/diag_pid.py <pid>"""
import os
import sys

pid = sys.argv[1]
base = f"/proc/{pid}"
if not os.path.exists(base):
    print("proces NIE zyje")
    raise SystemExit(0)
st = dict(line.split(":", 1) for line in open(f"{base}/status") if ":" in line)
fields = open(f"{base}/stat").read().rsplit(")", 1)[1].split()
hz = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
start_ticks = int(fields[19])
utime, stime = int(fields[11]), int(fields[12])
uptime = float(open("/proc/uptime").read().split()[0])
print("stan:", st.get("State", "").strip(), "| RAM:", st.get("VmRSS", "").strip())
print(f"dziala od {uptime - start_ticks / hz:.0f} s, czas CPU {(utime + stime) / hz:.0f} s")
print("cmd:", open(f"{base}/cmdline").read().replace("\x00", " ")[:200])
