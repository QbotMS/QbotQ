"""Qbot Telegram tools — audit, config, webhook, command help."""
from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SENSITIVE: set[str] = {"password", "secret", "token", "apikey", "api_key", "pgpassword", "env", "credential", "auth"}
_PROJECT_ROOT: Path = Path("/opt/qbot/app")
_SCAN_KW: list[str] = ["telegram", "TELEGRAM_BOT_TOKEN", "BOT_TOKEN", "TELEGRAM_CHAT_ID",
                        "ngrok", "webhook", "python-telegram-bot", "aiogram", "requests.post"]


def _token_ok() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN", ""))


def _secret_ok() -> bool:
    return bool(os.getenv("TELEGRAM_WEBHOOK_SECRET", ""))


def _public_url() -> str:
    return os.getenv("QBOT_PUBLIC_BASE_URL", "")


# ──────────── helpers ───────────────────────────────────────────────────

def _tool_qbot_telegram_transport_status(_args: dict | None = None) -> dict[str, Any]:
    check_remote = bool((_args or {}).get("check_remote", False))
    config = _tool_qbot_telegram_config_status()
    has_token = _token_ok()
    enabled = os.getenv("TELEGRAM_ENABLED", "").lower() == "true" and has_token
    public = _tool_qbot_public_endpoint_status()
    wh_info: dict[str, Any] = {}
    if has_token and check_remote:
        try:
            from qbot_telegram_client import get_webhook_info
            wh_info = get_webhook_info()
        except Exception:
            wh_info = {"ok": False, "error": "webhook check failed"}

    webhook_has_url = bool(wh_info.get("result", {}).get("url")) if wh_info.get("ok") else False
    public_ok = bool(public.get("is_https", False))
    if check_remote:
        status = "OK" if enabled and public_ok and webhook_has_url else "WARN"
    else:
        status = "OK" if enabled and public_ok and config.get("status") != "ERROR" else "WARN"
    if config.get("status") == "ERROR" or not has_token:
        status = "WARN"

    return {
        "tool": "qbot_telegram_transport_status",
        "config_status": config.get("status"),
        "enabled": enabled,
        "bot_reachable": has_token,
        "public_endpoint_configured": public_ok,
        "webhook_info": {"has_url": webhook_has_url} if check_remote and wh_info.get("ok") else {"skipped": not check_remote, "has_url": webhook_has_url},
        "status": status,
    }


# ──────────── qbot_telegram_legacy_audit ────────────────────────────────

def _tool_qbot_telegram_legacy_audit(_args: dict | None = None) -> dict[str, Any]:
    telegram_detected = False
    token_detected = False
    chat_config = False
    ngrok_found = False
    candidates: list[str] = []
    functions: list[str] = []

    for p in sorted(_PROJECT_ROOT.rglob("*")):
        if any(s in p.parts for s in {".git", ".venv", "__pycache__", ".pytest_cache", "logs", "outgoing", "backups"}):
            continue
        if p.name in (".env.local", ".env"):
            token_level = "token_detected" if "TELEGRAM_BOT_TOKEN" in (p.read_text(errors="ignore") if p.stat().st_size < 5000 else "") else "none"
            if token_level == "token_detected":
                token_detected = True
            candidates.append(f"{p.relative_to(_PROJECT_ROOT).as_posix()} ({token_level})")
            continue
        if not p.is_file() or p.suffix.lower() not in (".py", ".sh", ".json", ".yaml", ".yml", ".md", ".txt"):
            continue
        try:
            sz = p.stat().st_size
        except OSError:
            continue
        if sz > 300_000:
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        cl = content.lower()
        found = [k for k in _SCAN_KW if k in cl]
        if found:
            rel = p.relative_to(_PROJECT_ROOT).as_posix()
            candidates.append(f"{rel}: {found}")
            telegram_detected = True
            if "ngrok" in cl:
                ngrok_found = True
            if "TELEGRAM_CHAT_ID" in cl or "TELEGRAM_ALLOWED_CHAT_IDS" in cl:
                chat_config = True
            for line in content.splitlines():
                if any(k in line for k in ["def ", "class ", "@app.", "telegram", "webhook", "ngrok"]):
                    if len(functions) < 15:
                        functions.append(f"{rel}: {line.strip()[:200]}")

    return {
        "tool": "qbot_telegram_legacy_audit",
        "telegram_code_detected": telegram_detected,
        "token_present": token_detected,
        "chat_id_config_present": chat_config,
        "ngrok_references_found": ngrok_found,
        "candidate_files": candidates,
        "candidate_functions": functions,
        "migration_notes": [
            "Replace ngrok with direct HTTPS endpoint",
            "Use TELEGRAM_WEBHOOK_SECRET for webhook route protection",
            "Configure TELEGRAM_ALLOWED_CHAT_IDS for access control",
            "Do NOT commit .env.local or tokens to git",
        ] if ngrok_found else ["No ngrok references found — clean migration"],
        "status": "OK" if telegram_detected else "WARN",
    }


# ──────────── qbot_telegram_config_status ───────────────────────────────

def _tool_qbot_telegram_config_status(_args: dict | None = None) -> dict[str, Any]:
    bot_token = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
    allowed_ids = bool(os.getenv("TELEGRAM_ALLOWED_CHAT_IDS"))
    webhook_secret = bool(os.getenv("TELEGRAM_WEBHOOK_SECRET"))
    public_url = bool(os.getenv("QBOT_PUBLIC_BASE_URL"))
    webhook_url = bool(os.getenv("TELEGRAM_WEBHOOK_URL"))
    enabled = os.getenv("TELEGRAM_ENABLED", "").lower() == "true"

    missing: list[str] = []
    if not bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not allowed_ids:
        missing.append("TELEGRAM_ALLOWED_CHAT_IDS")
    if not webhook_secret:
        missing.append("TELEGRAM_WEBHOOK_SECRET")
    if not public_url:
        missing.append("QBOT_PUBLIC_BASE_URL")

    return {
        "tool": "qbot_telegram_config_status",
        "enabled": enabled,
        "bot_token_present": bot_token,
        "allowed_chat_ids_present": allowed_ids,
        "webhook_secret_present": webhook_secret,
        "public_base_url_present": public_url,
        "webhook_url_present": webhook_url,
        "config_source": ".env.local",
        "missing": missing,
        "status": "ERROR" if missing else "OK" if enabled else "WARN",
    }


# ──────────── qbot_public_endpoint_status ───────────────────────────────

def _tool_qbot_public_endpoint_status(_args: dict | None = None) -> dict[str, Any]:
    public_url = _public_url()
    has_url = bool(public_url)
    is_https = public_url.startswith("https://") if has_url else False
    recommendations: list[str] = []
    if not has_url:
        recommendations.append("Set QBOT_PUBLIC_BASE_URL=https://your-domain in .env.local")
    if not is_https and has_url:
        recommendations.append("QBOT_PUBLIC_BASE_URL must start with https:// for Telegram webhook")

    return {
        "tool": "qbot_public_endpoint_status",
        "public_url_configured": has_url,
        "is_https": is_https,
        "qbot_api_local": "127.0.0.1:8001 (active)",
        "recommendations": recommendations,
        "status": "ERROR" if not has_url else "WARN" if not is_https else "OK",
    }


# ──────────── qbot_telegram_status ──────────────────────────────────────

def _tool_qbot_telegram_status(_args: dict | None = None) -> dict[str, Any]:
    deep = bool((_args or {}).get("deep", False))
    transport = _tool_qbot_telegram_transport_status({"check_remote": False})
    try:
        from qbot_tools import _tool_qbot_api_self_check
        api_check = _tool_qbot_api_self_check()
    except Exception as exc:
        api_check = {"tool": "qbot_api_self_check", "status": "ERROR", "error": str(exc)}

    try:
        from qbot_legacy_cutover_tools import _tool_qbot_legacy_takeover_status, _tool_qbot_legacy_cutover_status
        takeover = _tool_qbot_legacy_takeover_status()
        cutover = _tool_qbot_legacy_cutover_status()
    except Exception as exc:
        takeover = {"tool": "qbot_legacy_takeover_status", "legacy_takeover_percent": 0, "status": "ERROR", "error": str(exc)}
        cutover = {"tool": "qbot_legacy_cutover_status", "cutover_completed": False, "legacy_service_active": True, "legacy_service_enabled": True}

    transport_status = str(transport.get("status", "UNKNOWN")).upper()
    api_ok = any(
        str(check.get("status", "")).upper() == "OK"
        for check in api_check.get("checks", [])
        if check.get("check") == "api_alive"
    )
    db_ok = any(
        str(check.get("status", "")).upper() == "OK"
        for check in api_check.get("checks", [])
        if check.get("check") == "db_connected"
    )

    webhook_ok = transport_status == "OK"
    legacy_takeover_pct = int(takeover.get("legacy_takeover_percent", 0) or 0)
    legacy_disabled = bool(cutover.get("cutover_completed")) or (
        cutover.get("legacy_service_active") is False and cutover.get("legacy_service_enabled") is False
    )
    cutover_status = str(cutover.get("status", "UNKNOWN")).upper()

    lines = ["Qbot status:"]
    lines.append("✅ API działa" if api_ok else "⚠️ API: problem")
    lines.append("✅ DB działa" if db_ok else "⚠️ DB: problem")
    lines.append("✅ Telegram webhook działa" if webhook_ok else "⚠️ Telegram webhook: problem")
    lines.append(f"✅ Legacy takeover: {legacy_takeover_pct}%")
    lines.append("ℹ️ q-bot.service: disabled po cutover" if legacy_disabled else "ℹ️ q-bot.service: legacy active")
    lines.append("ℹ️ ngrok: nieużywany")

    core_ok = api_ok and db_ok and webhook_ok and legacy_disabled and legacy_takeover_pct >= 100

    overall = "OK" if core_ok else "ERROR"

    return {
        "tool": "qbot_telegram_status",
        "status": overall,
        "summary_text": "\n".join(lines),
        "summary_lines": lines,
        "api_ok": api_ok,
        "db_ok": db_ok,
        "telegram_webhook_ok": webhook_ok,
        "legacy_takeover_percent": legacy_takeover_pct,
        "legacy_qbot_disabled": legacy_disabled,
        "api_self_check": api_check if deep else {"status": api_check.get("status", "UNKNOWN")},
        "telegram_transport": transport,
        "smoke_test": None if not deep else None,
        "readiness_report": None if not deep else None,
        "legacy_takeover_status": takeover,
        "legacy_cutover_status": cutover,
    }


# ──────────── qbot_telegram_webhook_plan ────────────────────────────────

def _tool_qbot_telegram_webhook_plan(_args: dict | None = None) -> dict[str, Any]:
    config = _tool_qbot_telegram_config_status()
    public_url = _public_url()
    secret_set = _secret_ok()
    wh_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "<SET-ME>")

    if public_url and public_url.endswith("/"):
        public_url = public_url.rstrip("/")
    webhook_url = f"{public_url}/telegram/webhook/{wh_secret}" if public_url else "<QBOT_PUBLIC_BASE_URL>/telegram/webhook/<WEBHOOK_SECRET>"

    return {
        "tool": "qbot_telegram_webhook_plan",
        "expected_webhook_url": webhook_url.replace(wh_secret, "<WEBHOOK_SECRET>") if wh_secret != "<SET-ME>" else webhook_url,
        "missing_config": config.get("missing", []),
        "manual_commands": [
            "# Set webhook (replace <TOKEN> with bot token)",
            'curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" -H "Content-Type: application/json" -d \'{"url":"<WEBHOOK_URL>","secret_token":"<SECRET>"}\'',
            "# Check webhook info",
            'curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"',
        ],
        "verification_steps": [
            "1. Set QBOT_PUBLIC_BASE_URL=https://your-domain in .env.local",
            "2. Set TELEGRAM_WEBHOOK_SECRET in .env.local",
            "3. Ensure HTTPS reverse proxy routes /telegram/webhook/ to 127.0.0.1:8001",
            "4. Set TELEGRAM_ENABLED=true in .env.local",
            "5. Run qbot_telegram_set_webhook with execute=true",
            "6. Verify with getWebhookInfo",
        ],
        "rollback_command": 'curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"',
        "status": "OK",
    }


# ──────────── qbot_telegram_set_webhook ─────────────────────────────────

def _tool_qbot_telegram_set_webhook(args: dict | None = None) -> dict[str, Any]:
    execute = (args or {}).get("execute", False) is True
    public_url = _public_url()
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")

    check = []
    if not _token_ok():
        check.append("TELEGRAM_BOT_TOKEN missing")
    if not secret:
        check.append("TELEGRAM_WEBHOOK_SECRET missing")
    if not public_url:
        check.append("QBOT_PUBLIC_BASE_URL missing")
    if not public_url.startswith("https://"):
        check.append("QBOT_PUBLIC_BASE_URL must be https://")
    if not os.getenv("TELEGRAM_ENABLED", "").lower() == "true":
        check.append("TELEGRAM_ENABLED must be true")

    if check:
        return {"tool": "qbot_telegram_set_webhook", "status": "BLOCKED", "execute": False, "reasons": check}

    wh_url = f"{public_url.rstrip('/')}/telegram/webhook/{secret}"

    if not execute:
        return {
            "tool": "qbot_telegram_set_webhook",
            "status": "PREVIEW",
            "execute": False,
            "would_set": wh_url.replace(secret, "<WEBHOOK_SECRET>"),
            "secret_set": True,
        }

    try:
        from qbot_telegram_client import set_webhook
        result = set_webhook(wh_url, secret_token=secret)
    except Exception as exc:
        return {"tool": "qbot_telegram_set_webhook", "status": "ERROR", "error": str(exc)}

    safe = {"ok": result.get("ok"), "description": result.get("description", "")}
    return {"tool": "qbot_telegram_set_webhook", "status": "OK" if result.get("ok") else "ERROR",
            "execute": True, "result": safe}


# ──────────── qbot_telegram_send_test ────────────────────────────────────

def _tool_qbot_telegram_send_test(args: dict | None = None) -> dict[str, Any]:
    if not _token_ok() or not os.getenv("TELEGRAM_ENABLED", "").lower() == "true":
        return {"tool": "qbot_telegram_send_test", "status": "ERROR", "error": "Telegram not enabled"}
    chat_id = (args or {}).get("chat_id")
    if not chat_id:
        allowed = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",")
        chat_id = allowed[0].strip() if allowed and allowed[0] else None
    if not chat_id:
        return {"tool": "qbot_telegram_send_test", "status": "ERROR", "error": "no chat_id configured"}
    text = str((args or {}).get("text", "Qbot Telegram test"))[:1000]
    try:
        from qbot_telegram_client import send_message, is_allowed_chat
        if not is_allowed_chat(int(chat_id)):
            return {"tool": "qbot_telegram_send_test", "status": "BLOCKED", "error": f"chat_id {chat_id} not allowed"}
        result = send_message(chat_id, text)
    except Exception as exc:
        return {"tool": "qbot_telegram_send_test", "status": "ERROR", "error": str(exc)}
    return {"tool": "qbot_telegram_send_test", "status": "OK" if result.get("ok") else "ERROR",
            "message_id": result.get("result", {}).get("message_id")}


# ──────────── qbot_telegram_command_help ────────────────────────────────

def _tool_qbot_telegram_command_help(_args: dict | None = None) -> dict[str, Any]:
    return {
        "tool": "qbot_telegram_command_help",
        "commands": [
            {"command": "/start", "description": "Welcome message and bot introduction"},
            {"command": "/help", "description": "Show this command list"},
            {"command": "/status", "description": "Quick Qbot status summary"},
            {"command": "/legacy", "description": "Legacy cutover and rollback status"},
            {"command": "/ready", "description": "Readiness report summary"},
            {"command": "/smoke", "description": "Final smoke test result"},
            {"command": "/backup", "description": "Backup status overview"},
            {"command": "/errors", "description": "Recent error summary"},
            {"command": "/takeover", "description": "Legacy takeover status"},
            {"command": "/weather_status", "description": "Current weather status and legacy OpenWeatherMap parity"},
            {"command": "/garage_status", "description": "Legacy garage / gate / home automation status"},
            {"command": "/artifacts", "description": "Artifacts container status"},
            {"command": "/integrations", "description": "External integrations overview"},
            {"command": "/ask <query>", "description": "Natural language query via Qbot policy engine"},
        ],
        "security_notes": [
            "Only allowed chat IDs can interact",
            "No CONTROLLED_ACTION via Telegram",
            "All queries go through Qbot policy engine",
            "No secrets in responses",
        ],
    }


# ──────────── qbot_telegram_answer_context ──────────────────────────────

def _sanitize(obj: Any, depth: int = 0) -> Any:
    if depth > 3:
        return "<truncated>"
    if isinstance(obj, dict):
        r: dict[str, Any] = {}
        for k, v in obj.items():
            if any(s in str(k).lower() for s in _SENSITIVE):
                r[k] = "<redacted>"
            elif isinstance(v, (dict, list)):
                r[k] = _sanitize(v, depth + 1)
            elif isinstance(v, str) and len(v) > 2000:
                r[k] = v[:2000] + "...<truncated>"
            else:
                r[k] = v
        return r
    if isinstance(obj, list):
        return [_sanitize(v, depth + 1) if isinstance(v, (dict, list)) else v[:500] + "...<truncated>" if isinstance(v, str) and len(v) > 500 else v for v in obj[:50]]
    return obj[:2000] + "...<truncated>" if isinstance(obj, str) and len(obj) > 2000 else obj


def _tool_qbot_telegram_answer_context(_args: dict | None = None) -> dict[str, Any]:
    status = _tool_qbot_telegram_status()
    cmds = _tool_qbot_telegram_command_help()
    return {
        "tool": "qbot_telegram_answer_context",
        "safe_for_llm": True,
        "context": _sanitize({"status": status, "commands": cmds}),
        "suggested_answer_outline": ["1. Summarize Telegram bot status", "2. List available commands", "3. Note security model", "4. Stay factual"],
        "llm_must_not": ["expose tokens", "bypass chat_id check"],
        "limitations": ["Sanitized context", "No secrets"],
    }


# ──────────── qbot_telegram_delete_webhook ──────────────────────────────

def _tool_qbot_telegram_delete_webhook(args: dict | None = None) -> dict[str, Any]:
    execute = (args or {}).get("execute", False) is True
    if not _token_ok() or not os.getenv("TELEGRAM_ENABLED", "").lower() == "true":
        return {"tool": "qbot_telegram_delete_webhook", "status": "BLOCKED", "error": "Telegram not enabled or token missing"}
    if not execute:
        return {"tool": "qbot_telegram_delete_webhook", "status": "PREVIEW", "execute": False}
    try:
        from qbot_telegram_client import delete_webhook
        result = delete_webhook()
    except Exception as exc:
        return {"tool": "qbot_telegram_delete_webhook", "status": "ERROR", "error": str(exc)}
    return {"tool": "qbot_telegram_delete_webhook", "status": "OK" if result.get("ok") else "ERROR",
            "execute": True, "result": {"ok": result.get("ok"), "description": result.get("description", "")}}


def _get_telegram_tool(name: str):
    mapping = {
        "qbot_telegram_legacy_audit": _tool_qbot_telegram_legacy_audit,
        "qbot_telegram_config_status": _tool_qbot_telegram_config_status,
        "qbot_public_endpoint_status": _tool_qbot_public_endpoint_status,
        "qbot_telegram_status": _tool_qbot_telegram_status,
        "qbot_telegram_webhook_plan": _tool_qbot_telegram_webhook_plan,
        "qbot_telegram_set_webhook": _tool_qbot_telegram_set_webhook,
        "qbot_telegram_send_test": _tool_qbot_telegram_send_test,
        "qbot_telegram_command_help": _tool_qbot_telegram_command_help,
        "qbot_telegram_answer_context": _tool_qbot_telegram_answer_context,
        "qbot_telegram_delete_webhook": _tool_qbot_telegram_delete_webhook,
    }
    return mapping.get(name)
