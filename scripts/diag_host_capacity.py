#!/usr/bin/env python3
"""Szybki stan: miejsce na dysku, RAM, osmium + jednorazowy test overpass-api.de (IPv4/IPv6)."""
import shutil
import socket
import subprocess

for p in ("/", "/opt/qbot"):
    t, u, f = shutil.disk_usage(p)
    print(f"dysk {p}: razem {t/1e9:.1f} GB, zajete {u/1e9:.1f} GB, wolne {f/1e9:.1f} GB")
try:
    mem = dict(l.split(":", 1) for l in open("/proc/meminfo"))
    print("RAM razem", mem["MemTotal"].strip(), "| dostepne", mem["MemAvailable"].strip())
except Exception as exc:
    print("RAM ?", exc)
print("osmium:", shutil.which("osmium"), "| ogr2ogr:", shutil.which("ogr2ogr"))
try:
    import osmium  # noqa: F401
    print("pyosmium: jest")
except Exception:
    print("pyosmium: brak")
for fam, name in ((socket.AF_INET, "IPv4"), (socket.AF_INET6, "IPv6")):
    for ip in ("162.55.144.139", "2a01:4f8:261:3c4f::2") if fam == socket.AF_INET6 else ("162.55.144.139", "65.109.112.52"):
        if (fam == socket.AF_INET6) != (":" in ip):
            continue
        s = socket.socket(fam, socket.SOCK_STREAM)
        s.settimeout(5)
        try:
            s.connect((ip, 443))
            print(f"overpass-api.de {name} {ip}:443 -> POLACZONO")
        except Exception as exc:
            print(f"overpass-api.de {name} {ip}:443 -> {type(exc).__name__}: {exc}")
        finally:
            s.close()
try:
    out = subprocess.run(["curl", "-s", "-m", "5", "-4", "https://ifconfig.me"], capture_output=True, text=True, timeout=8).stdout
    print("nasze IPv4 na zewnatrz:", out.strip())
except Exception as exc:
    print("IPv4 zewn. ?", exc)
