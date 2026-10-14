#!/usr/bin/env python3
"""debug_garmin_training_raw.py -- [GARMIN-DANE] Etap 6b: co Garmin zwraca o gotowosci i statusie treningu.
Tylko odczyt z Garmina, nic nie zapisuje do bazy. JSON -> /opt/qbot/artifacts/garmin_training_raw_<data>.json
  .venv/bin/python3 scripts/debug_garmin_training_raw.py [--dates 2026-10-14,2026-06-10]"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
OUT_DIR = Path("/opt/qbot/artifacts")
INTEREST = re.compile(r"(score|level|status|feedback|recovery|acute|load|balance|vo2|chronic|ratio|factor|percent)", re.I)


def _client():
    from garminconnect import Garmin
    profile = json.loads((APP_DIR / ".garmin_profile.json").read_text())
    g = Garmin("", "")
    g.client.load(str(APP_DIR / ".garmin_tokens"))
    g.display_name = profile["display_name"]
    return g


def _walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        if obj and isinstance(obj[0], (dict, list)):
            yield from _walk(obj[0], f"{path}[0]")
        else:
            yield path, f"<lista {len(obj)}>"
    else:
        yield path, obj


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dates", default=date.today().isoformat())
    a = p.parse_args()
    g = _client()
    calls = [("training_readiness", "get_training_readiness"), ("training_status", "get_training_status"),
             ("max_metrics", "get_max_metrics"), ("hill_score", "get_hill_score"), ("endurance_score", "get_endurance_score")]
    for d in [x.strip() for x in a.dates.split(",") if x.strip()]:
        out = {"date": d}
        for name, fn in calls:
            f = getattr(g, fn, None)
            if f is None:
                out[name] = {"_error": "brak metody w bibliotece"}
                continue
            try:
                out[name] = f(d) if name not in ("hill_score", "endurance_score") else f(d, d)
            except TypeError:
                try:
                    out[name] = f(d)
                except Exception as e:  # noqa: BLE001
                    out[name] = {"_error": str(e)[:200]}
            except Exception as e:  # noqa: BLE001
                out[name] = {"_error": str(e)[:200]}
        path = OUT_DIR / f"garmin_training_raw_{d}.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        print("=" * 70, f"\n{d} -> {path}")
        for name, _ in calls:
            data = out[name]
            print(f"\n[{name}] typ: {type(data).__name__}")
            hits = [(k, v) for k, v in _walk(data) if INTEREST.search(k)]
            for k, v in hits[:40]:
                print(f"   {k} = {v}")
            if not hits:
                print("   ", str(data)[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
