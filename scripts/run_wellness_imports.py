#!/usr/bin/env python3
"""Run Garmin + Intervals wellness imports for cron or manual backfill."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))

from dotenv import load_dotenv

load_dotenv(APP_DIR / ".env.local")
load_dotenv(APP_DIR / ".env")

from qbot_wellness_store import (  # noqa: E402
    _tool_qbot_garmin_wellness_import_execute,
    _tool_qbot_intervals_wellness_import_execute,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--date-from", default=None)
    p.add_argument("--date-to", default=None)
    p.add_argument("--source", choices=["all", "garmin", "intervals"], default="all")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def _default_dates() -> tuple[str, str]:
    today = date.today()
    return ((today - timedelta(days=1)).isoformat(), today.isoformat())


def main() -> int:
    args = _parse_args()
    date_from, date_to = args.date_from, args.date_to
    if not date_from or not date_to:
        default_from, default_to = _default_dates()
        date_from = date_from or default_from
        date_to = date_to or default_to

    payload = {"date_from": date_from, "date_to": date_to, "dry_run": args.dry_run}
    results = []
    if args.source in ("all", "garmin"):
        results.append(_tool_qbot_garmin_wellness_import_execute(payload))
    if args.source in ("all", "intervals"):
        results.append(_tool_qbot_intervals_wellness_import_execute(payload))

    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
