#!/usr/bin/env python3
"""Print a compact operational status for QBot."""
from __future__ import annotations

import sys
import json

sys.path.insert(0, "/opt/qbot/app")

from scripts.qbot_operational_state import OUT_FILE, collect_state


def print_lines(title: str, lines: list[str], limit: int = 8) -> None:
    print(f"\n{title}")
    if not lines:
        print("  —")
        return
    for line in lines[-limit:]:
        print(f"  {line}")


def main() -> int:
    state = collect_state()
    # Keep the machine-readable status fresh for other tools.
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    health = state.get("health", {})
    print(f"QBot status: {health.get('level', 'UNKNOWN')}")
    issues = health.get("issues") or []
    if issues:
        print("Issues:")
        for issue in issues:
            print(f"- {issue}")
    else:
        print("Issues: none")

    print("\nCore")
    print(f"- LLM: {state.get('llm', {}).get('provider')} | QGPT {state.get('llm', {}).get('qgpt_model')} | Anthropic {state.get('llm', {}).get('anthropic_model')}")
    print(f"- MCP: {state.get('mcp', {}).get('url')}")
    print(f"- Xert: TP {state.get('mcp', {}).get('xert_tp') or '—'} / {state.get('mcp', {}).get('xert_status') or '—'}")
    print(f"- Weather keys: {', '.join(state.get('mcp', {}).get('weather_keys') or []) or '—'}")

    print("\nReports")
    reports = state.get("reports", {})
    print(f"- Daily sent date: {reports.get('daily_sent_date') or 'none'}")
    print(f"- Ride report cron: {'enabled' if reports.get('ride_report_cron_enabled') else 'disabled'}")
    messages = state.get("messages", {})
    print(f"- Telegram failed messages: {messages.get('telegram_failed_count', 0)}")
    print(f"- Email failed replies: {messages.get('email_failed_count', 0)}")

    print("\nServices")
    for name, status in (state.get("services") or {}).items():
        print(f"- {name}: {status}")

    logs = state.get("recent_logs", {})
    print_lines("Recent daily_report.log", logs.get("daily_report", []))
    print_lines("Recent ride_report.log", logs.get("ride_report", []))
    print_lines("Recent q-bot.err.log", logs.get("qbot_err", []), limit=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
