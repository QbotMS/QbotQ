#!/usr/bin/env python3
"""Write machine-readable QBot operational state."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/opt/qbot/app")

import qbot_config as cfg
from qbot_mcp_client import mcp_call


OUT_FILE = cfg.DATA_DIR / "qbot_operational_state.json"


def run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=8).strip()
    except Exception as exc:
        return f"ERROR: {exc}"


def read_daily_sent():
    path = cfg.DATA_DIR / "daily_report_sent.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text()).get("date")
    except Exception:
        return "unreadable"


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def tail(path: Path, lines: int = 20) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(errors="replace").splitlines()[-lines:]


def has_recent_error(lines: list[str]) -> bool:
    markers = ("traceback", "error", "❌", "failed rc=", "błąd")
    return any(any(m in line.lower() for m in markers) for line in lines)


def health_summary(state: dict) -> dict:
    issues = []
    services = state.get("services", {})
    for name, status in services.items():
        if status != "active":
            issues.append(f"service {name}: {status}")
    if not state.get("reports", {}).get("ride_report_cron_enabled"):
        issues.append("ride_report cron disabled")
    failed_tg = state.get("messages", {}).get("telegram_failed_count", 0)
    if failed_tg:
        issues.append(f"telegram failed messages: {failed_tg}")
    failed_email = state.get("messages", {}).get("email_failed_count", 0)
    if failed_email:
        issues.append(f"email failed replies: {failed_email}")
    logs = state.get("recent_logs", {})
    for name, lines in logs.items():
        if has_recent_error(lines):
            issues.append(f"recent {name} log has errors")
    if issues:
        level = "FAIL" if any(i.startswith("service ") for i in issues) else "WARN"
    else:
        level = "OK"
    return {"level": level, "issues": issues}


def collect_state() -> dict:
    xert = mcp_call("get_xert_status", logger=lambda msg: None) or {}
    weather = mcp_call("get_weather", {"location": cfg.LOCATION_NAME, "days": 1}, logger=lambda msg: None) or {}
    services = run(["systemctl", "--no-pager", "--plain", "is-active", "q-bot.service", "ngrok-qbot.service", "qbot-qlab-server.service"]).splitlines()
    qbot_cron = run(["crontab", "-u", "qbot", "-l"])
    root_cron = run(["crontab", "-l"])
    failed_messages = read_json(cfg.DATA_DIR / "telegram_failed_messages.json", [])
    failed_emails = read_json(cfg.DATA_DIR / "email_failed_replies.json", [])
    state = {
        "generated_at": datetime.now().isoformat(),
        "llm": {
            "provider": cfg.llm_provider(),
            "qgpt_model": cfg.QGPT_MODEL,
            "anthropic_model": cfg.ANTHROPIC_MODEL,
        },
        "mcp": {
            "url": cfg.MCP_URL,
            "xert_tp": xert.get("tp_ftp_watts"),
            "xert_status": (xert.get("forma") or {}).get("status") if isinstance(xert, dict) else None,
            "weather_keys": sorted(weather.keys()) if isinstance(weather, dict) else [],
        },
        "reports": {
            "daily_sent_date": read_daily_sent(),
            "ride_report_cron_enabled": "ride_report.py" in qbot_cron,
        },
        "messages": {
            "telegram_failed_count": len(failed_messages) if isinstance(failed_messages, list) else 0,
            "email_failed_count": len(failed_emails) if isinstance(failed_emails, list) else 0,
        },
        "services": {
            "q-bot.service": services[0] if len(services) > 0 else "unknown",
            "ngrok-qbot.service": services[1] if len(services) > 1 else "unknown",
            "qbot-qlab-server.service": services[2] if len(services) > 2 else "unknown",
        },
        "cron": {
            "qbot": qbot_cron.splitlines(),
            "root": root_cron.splitlines(),
        },
        "recent_logs": {
            "daily_report": tail(Path("/opt/qbot/logs/daily_report.log"), 10),
            "ride_report": tail(Path("/opt/qbot/logs/ride_report.log"), 10),
            "qbot_err": tail(Path("/opt/qbot/logs/q-bot.err.log"), 10),
        },
    }
    state["health"] = health_summary(state)
    return state


def main() -> int:
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = collect_state()
    OUT_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT_FILE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
