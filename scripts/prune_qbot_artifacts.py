#!/usr/bin/env python3
"""Prune generated QBot artifacts while keeping recent debugging context."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


APP_DIR = Path("/opt/qbot/app")


@dataclass(frozen=True)
class RetentionRule:
    path: Path
    patterns: tuple[str, ...]
    keep: int
    label: str


RULES = (
    RetentionRule(
        APP_DIR / "outgoing" / "hammerhead_originals",
        ("*.fit",),
        60,
        "hammerhead originals",
    ),
    RetentionRule(
        APP_DIR / "outgoing" / "garmin_proxy",
        ("*.fit", "*.csv"),
        60,
        "garmin proxy files",
    ),
    RetentionRule(
        APP_DIR / "outgoing" / "reports",
        ("*.json",),
        120,
        "hammerhead reports",
    ),
    RetentionRule(
        APP_DIR / "qlab_exports",
        ("*.qbot_replay_log.json", "*.validation_report.json"),
        20,
        "qlab detailed exports",
    ),
    RetentionRule(
        APP_DIR / "qlab_exports",
        ("*.qbot_replay_summary.json",),
        60,
        "qlab summaries",
    ),
)


def candidates(rule: RetentionRule) -> list[Path]:
    files: list[Path] = []
    if not rule.path.exists():
        return files
    for pattern in rule.patterns:
        files.extend(p for p in rule.path.glob(pattern) if p.is_file())
    return sorted(set(files), key=lambda p: p.stat().st_mtime, reverse=True)


def prune_rule(rule: RetentionRule, dry_run: bool) -> tuple[int, int]:
    files = candidates(rule)
    stale = files[rule.keep :]
    for path in stale:
        if dry_run:
            print(f"would remove: {path}")
        else:
            print(f"remove: {path}")
            path.unlink()
    return len(files), len(stale)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    for rule in RULES:
        total, removed = prune_rule(rule, args.dry_run)
        action = "would remove" if args.dry_run else "removed"
        print(f"{rule.label}: total={total}, keep={rule.keep}, {action}={removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
