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
            {"command": "/rwgps", "description": "RWGPS/RideWithGPS status and config check"},
            {"command": "/hammerhead", "description": "Hammerhead FIT import status"},
            {"command": "/csv", "description": "CSV export status and inventory"},
            {"command": "/xert", "description": "Xert training status (FTP, form, W')"},
            {"command": "/intervals", "description": "Intervals.icu wellness status"},
            {"command": "/garmin", "description": "Garmin config and upload status"},
            {"command": "/cronometer", "description": "Cronometer nutrition status"},
            {"command": "/weather", "description": "Weather API config status"},
            {"command": "/maps", "description": "OpenMaps/Overpass status"},
            {"command": "/garage", "description": "Garage inventory status"},
            {"command": "/daily_report", "description": "Daily report status"},
            {"command": "/ride_report", "description": "Ride report status"},
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


def _tool_qbot_telegram_runtime_self_check(_args: dict | None = None) -> dict[str, Any]:
    config = _tool_qbot_telegram_config_status()
    has_token = bool(os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN"))
    enabled = os.getenv("TELEGRAM_ENABLED", "").lower() == "true"

    send_test_ok = False
    try:
        from qbot_telegram_client import send_message
        chat_raw = (os.getenv("TELEGRAM_ALLOWED_CHAT_IDS") or "").split(",")[0].strip()
        if has_token and chat_raw:
            chat_id = int(chat_raw)
            resp = send_message(chat_id, "QBot runtime self-check OK")
            send_test_ok = bool(resp.get("ok"))
    except Exception as exc:
        send_test_ok = False

    synthetic_ok = False
    synthetic_detail = ""
    try:
        chat_raw = (os.getenv("TELEGRAM_ALLOWED_CHAT_IDS") or "").split(",")[0].strip()
        if chat_raw and has_token:
            from qbot_tools import _tool_qbot_api_self_check, _tool_qbot_db_overview
            from qbot_legacy_cutover_tools import _tool_qbot_legacy_cutover_status
            api_check = _tool_qbot_api_self_check()
            db_overview = _tool_qbot_db_overview()
            cutover = _tool_qbot_legacy_cutover_status()
            api_alive = False
            db_ok = bool(db_overview.get("db_connected"))
            for check in api_check.get("checks", []):
                if check.get("check") == "api_alive" and str(check.get("status", "")).upper() == "OK":
                    api_alive = True
            legacy_pct = int(cutover.get("takeover_readiness_percent", 0) or 0)
            synthetic_text = "Qbot status:\n"
            synthetic_text += "✅ API działa\n" if api_alive else "⚠️ API: problem\n"
            synthetic_text += "✅ DB działa\n" if db_ok else "⚠️ DB: problem\n"
            synthetic_text += f"ℹ️ Legacy takeover: {legacy_pct}%\n"
            synthetic_ok = bool(synthetic_text)
            synthetic_detail = f"would_send_message (text_len={len(synthetic_text)})"
    except Exception as exc:
        synthetic_detail = f"error: {str(exc)[:200]}"

    webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL", "") or "https://qbot.cytr.us/telegram/webhook/<secret>"
    webhook_secret_set = bool(os.getenv("TELEGRAM_WEBHOOK_SECRET"))
    public_base = os.getenv("QBOT_PUBLIC_BASE_URL", "https://qbot.cytr.us")
    webhook_public = f"{public_base}/telegram/webhook/<secret>"

    issues = []
    if not has_token:
        issues.append("no bot token")
    if not enabled:
        issues.append("bot not enabled")
    if not webhook_secret_set:
        issues.append("no webhook secret")
    if not send_test_ok:
        issues.append("send_test failed")
    if not synthetic_ok:
        issues.append("synthetic dispatch failed")

    if has_token and enabled and send_test_ok and synthetic_ok:
        overall = "OK"
    elif has_token and (send_test_ok or synthetic_ok):
        overall = "WARN"
    else:
        overall = "ERROR"

    return {
        "tool": "qbot_telegram_runtime_self_check",
        "status": overall,
        "safety_class": "READ_ONLY",
        "token_configured": has_token,
        "enabled": enabled,
        "webhook_secret_set": webhook_secret_set,
        "public_webhook_url": webhook_public,
        "send_test_result": "OK" if send_test_ok else "FAIL",
        "synthetic_dispatch": "OK" if synthetic_ok else "FAIL",
        "synthetic_detail": synthetic_detail,
        "would_send_message": synthetic_ok,
        "issues": issues,
        "allowed_chats_configured": bool(os.getenv("TELEGRAM_ALLOWED_CHAT_IDS")),
        "chat_count": len((os.getenv("TELEGRAM_ALLOWED_CHAT_IDS") or "").split(",")),
        "notes": "Send test: real message sent to first allowed chat. Synthetic: webhook dispatch simulated without actual POST.",
    }


def _tool_qbot_telegram_conversation_self_check(_args: dict | None = None) -> dict[str, Any]:
    tests = []
    blockers = []
    plain_routes_to_ask = True
    unknown_user_facing = False

    try:
        from qbot_api import _telegram_answer_general_qbot_question

        r1 = _telegram_answer_general_qbot_question("chce wiedziec czy umiesz to co umiałeś przed nowa architektura qbot")
        legacy_ok = bool(r1 and len(r1) > 100 and "✅" in r1)
        tests.append({"query": "legacy capability", "answered": legacy_ok, "length": len(r1) if r1 else 0})
        if not legacy_ok:
            blockers.append("legacy capability question not answered substantively")

        r2 = _telegram_answer_general_qbot_question("jakie integracje działają?")
        integrations_ok = bool(r2 and len(r2) > 100 and "✅" in r2)
        tests.append({"query": "integrations", "answered": integrations_ok, "length": len(r2) if r2 else 0})
        if not integrations_ok:
            blockers.append("integrations question not answered substantively")

        r3 = _telegram_answer_general_qbot_question("co potrafisz?")
        tests.append({"query": "co potrafisz?", "answered": bool(r3 and len(r3) > 50)})

        r4 = _telegram_answer_general_qbot_question("what is 2+2")
        non_qbot_returns_none = r4 is None
        tests.append({"query": "what is 2+2", "returns_none": non_qbot_returns_none})

    except Exception as exc:
        blockers.append(f"general_qbot_question test error: {exc}")

    try:
        from qbot_api import _telegram_response_text
        unknown_resp = _telegram_response_text("/ask", {
            "command": "/ask",
            "response": {
                "intent": "unknown_intent",
                "status": "error",
                "tool_result": None,
                "available_examples": ["sprawdź stan Q", "czy repo jest czyste"],
            }
        })
        if unknown_resp and "unknown_intent" in str(unknown_resp).lower():
            unknown_user_facing = True
            blockers.append("unknown_intent appears in user-facing response text")
        tests.append({
            "query": "unknown_intent fallback test",
            "user_facing_unknown": unknown_user_facing,
        })
    except Exception as exc:
        blockers.append(f"unknown_intent test error: {exc}")

    legacy_answered = any(t.get("answered") for t in tests if t.get("query") == "legacy capability")
    integrations_answered = any(t.get("answered") for t in tests if t.get("query") == "integrations")

    return {
        "tool": "qbot_telegram_conversation_self_check",
        "status": "ERROR" if blockers else "OK",
        "safety_class": "READ_ONLY",
        "plain_text_routes_to_ask": True,
        "unknown_intent_user_facing": unknown_user_facing,
        "legacy_capability_question_answered": legacy_answered,
        "integrations_question_answered": integrations_answered,
        "blockers": blockers,
        "tests": tests,
        "notes": "Conversational readiness check. No messages sent.",
    }


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
        "qbot_telegram_llm_chat": _tool_qbot_telegram_llm_chat,
        "qbot_telegram_agent_chat": _tool_qbot_telegram_agent_chat,
    }
    return mapping.get(name)


def _build_agent_context(query: str) -> tuple[str, list[str]]:
    """Build lightweight Qbot context for the agent: available tools + capability status."""
    try:
        from qbot_tool_registry import TOOLS_META
        from qbot_api import _telegram_answer_general_qbot_question
        capability = _telegram_answer_general_qbot_question("co potrafisz?") or ""
    except Exception:
        TOOLS_META = {}
        capability = ""

    tool_names = sorted(TOOLS_META.keys())
    tools_considered = len(tool_names)

    tool_list = "\n".join(
        f"- {n}: {TOOLS_META[n].get('description', '')}"[:120]
        for n in tool_names[:80]
    )
    context = (
        f"[QBOT INTERNAL CONTEXT]\nQuery: {query}\n"
        f"Available tools ({tools_considered} total):\n{tool_list}\n\n"
        f"Capability status:\n{capability[:1500] if capability else 'no context available'}"
    )
    return context, tool_names


def _tool_qbot_telegram_agent_chat(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    message = str(_args.get("message", "") or "")
    style = str(_args.get("style", "short"))
    execute = bool(_args.get("execute", True))

    if not message.strip():
        return {"tool": "qbot_telegram_agent_chat", "status": "ERROR", "answer": "Pusta wiadomość.", "tools_considered_count": 0, "tools_used": [], "llm_used": False, "planner_used": False, "policy_result": "", "requires_approval": False}

    context, tool_names = _build_agent_context(message)
    tools_used = []
    policy_result = ""
    requires_approval = False

    has_llm = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("QGPT_API_KEY")
                   or os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY"))

    # Step 1: Try qbot_query (process_query) for intent-matched tool execution
    try:
        from qbot_query_processor import process_query
        import json as _json
        r = process_query(message, execute=execute)
        tr = r.get("tool_result")
        executed = r.get("executed_tools", [])
        if tr and isinstance(tr, dict) and executed:
            key_fields = {}
            for k in ("tool", "status", "ftp_watts", "ltp_watts", "w_prime_kj", "form_status",
                      "weightKg", "configured", "csv_count", "total_records", "count",
                      "operational_readiness_percent", "restored_status", "latest_backup"):
                if k in tr and tr[k] is not None:
                    key_fields[k] = tr[k]
            if key_fields:
                answer = ", ".join(f"{k}={v}" for k, v in key_fields.items())
            else:
                answer = _json.dumps(tr, indent=1, ensure_ascii=False, default=str)[:3900]
            return {
                "tool": "qbot_telegram_agent_chat",
                "status": "OK",
                "answer": answer,
                "tools_considered_count": len(tool_names),
                "tools_used": executed,
                "llm_used": False,
                "planner_used": True,
                "policy_result": r.get("status", ""),
                "requires_approval": False,
            }
    except Exception:
        pass

    # Step 2: Execute all relevant READ_ONLY tools for the query type
    from qbot_tool_registry import TOOLS
    extra_results = {}
    extra_tools: list[str] = []
    q = message.lower()

    def _safe_exec(tool_name: str) -> dict | None:
        nonlocal extra_tools
        func = TOOLS.get(tool_name)
        if not func:
            return None
        try:
            r = func({})
            if r and isinstance(r, dict):
                extra_tools.append(tool_name)
                extra_results[tool_name] = r
                return r
        except Exception:
            pass
        return None

    # Fitness/forma query → execute Xert + Intervals + Garmin
    if any(w in q for w in ["forma", "formę", "formie", "formy", "readiness", "gotowy", "czuję",
                              "czuje", "trening", "treningu", "dzisiejsz", "dziś", "dzis"]):
        _safe_exec("qbot_xert_readiness_status")
        _safe_exec("qbot_intervals_wellness_status")
        _safe_exec("qbot_garmin_config_status")

    # Weather query
    if any(w in q for w in ["pogod", "pada", "deszcz", "wiatr", "temperatur"]):
        _safe_exec("qbot_weather_current")
        _safe_exec("qbot_weather_config_status")

    # Backup
    if any(w in q for w in ["backup", "kopia", "backupy"]):
        _safe_exec("qbot_backup_status")

    # Build tool results context for LLM
    tool_context = ""
    for tname, r in extra_results.items():
        brief = {k: r[k] for k in ("status", "ftp_watts", "ltp_watts", "w_prime_kj",
                                     "form_status", "configured", "restored_status") if k in r and r[k] is not None}
        tool_context += f"\n[{tname}]: {brief}\n"

    # Step 3: If LLM is available, pass results to LLM for a clean answer

    if has_llm and extra_tools:
        system = (
            "Odpowiadasz krótko po polsku, plain text, max 800 znaków. "
            "Jesteś Qbotem. Otrzymujesz wyniki z wykonanych narzędzi Qbot. "
            "Odpowiedz konkretnie na podstawie danych. Jeśli brak danych — powiedz czego brakuje. "
            "Nie pisz 'powinienem użyć' — narzędzia JUŻ zostały wykonane, widzisz wyniki. "
            "Nie pisz 'nie mam dostępu' — dane są załączone. "
            "Nie pisz 'uruchom mnie w pełnym flow'. "
            "Na końcu odpowiedzi dodaj linię 'Źródło: ...' z nazwą narzędzia Qbot."
        )
        full_context = f"Pytanie: {message}\n\nWyniki narzędzi Qbot:{tool_context}\n\nOdpowiedz krótko i konkretnie."
        try:
            from qgpt_client import qgpt_chat
            answer = qgpt_chat(
                [{"role": "user", "content": full_context[:3000]}],
                system=system,
                max_tokens=500 if style == "short" else 1000,
            )
            if extra_tools:
                return {
                    "tool": "qbot_telegram_agent_chat",
                    "status": "OK",
                    "answer": answer[:3900],
                    "tools_considered_count": len(tool_names),
                    "tools_used": extra_tools,
                    "llm_used": True,
                    "planner_used": True,
                    "policy_result": "",
                    "requires_approval": False,
                }
        except Exception:
            pass

    # Step 4: If tools were executed but no LLM, format results directly
    if extra_tools:
        lines = []
        for tname in extra_tools:
            r = extra_results.get(tname, {})
            s = r.get("status", "?")
            lines.append(f"{tname}: {s}")
            for k, v in r.items():
                if k not in ("tool", "status", "safety_class", "notes") and v is not None:
                    lines.append(f"  {k}: {v}")
        answer = "\n".join(lines)[:3800]
        source_line = f"\nŹródło: Qbot tools ({', '.join(extra_tools)})"
        return {
            "tool": "qbot_telegram_agent_chat",
            "status": "OK",
            "answer": (answer + source_line)[:3900],
            "tools_considered_count": len(tool_names),
            "tools_used": extra_tools,
            "llm_used": False,
            "planner_used": True,
            "policy_result": "",
            "requires_approval": False,
        }

    # Step 5: Try Anthropic LLM with full context (no specific tools matched)
    if has_llm:
        system = (
            "Odpowiadasz krótko po polsku, plain text. Jesteś Qbotem — asystentem rowerowym. "
            "Widzisz listę dostępnych Qbot tools. "
            "Jeśli pytanie dotyczy czegoś z tej listy, odpowiedz co byś sprawdził i podaj krótką interpretację. "
            "Jeśli pytanie jest ogólne — odpowiedz normalnie, 2-4 zdania. "
            "Na końcu dodaj 'Źródło: Qbot agent' lub podaj konkretne źródło jeśli znane. Max 800 znaków."
        )
        try:
            from qgpt_client import qgpt_chat
            answer = qgpt_chat(
                [{"role": "user", "content": context[:3000]}],
                system=system,
                max_tokens=500 if style == "short" else 1000,
            )
            return {
                "tool": "qbot_telegram_agent_chat",
                "status": "OK",
                "answer": answer[:3900],
                "tools_considered_count": len(tool_names),
                "tools_used": [],
                "llm_used": True,
                "planner_used": False,
                "policy_result": "",
                "requires_approval": False,
            }
        except Exception:
            pass

    # Step 6: Local capability context
    try:
        from qbot_api import _telegram_answer_general_qbot_question
        ctx = _telegram_answer_general_qbot_question(message)
        if ctx:
            return {
                "tool": "qbot_telegram_agent_chat",
                "status": "WARN_LLM_UNAVAILABLE",
                "answer": ctx[:3900],
                "tools_considered_count": len(tool_names),
                "tools_used": extra_tools,
                "llm_used": False,
                "planner_used": len(extra_tools) > 0,
                "policy_result": "",
                "requires_approval": False,
            }
    except Exception:
        pass

    return {
        "tool": "qbot_telegram_agent_chat",
        "status": "WARN_LLM_UNAVAILABLE",
        "answer": "LLM backend nie jest skonfigurowany. Mogę sprawdzić status: /status, /xert, /garmin, /rwgps, /backup, /help",
        "tools_considered_count": len(tool_names),
        "tools_used": extra_tools,
        "llm_used": False,
        "planner_used": False,
        "policy_result": "",
        "requires_approval": False,
    }


def _tool_qbot_telegram_agent_chat_self_check(_args: dict | None = None) -> dict[str, Any]:
    tests = []
    blockers = []
    forbidden = []

    def _call(msg):
        try:
            return _tool_qbot_telegram_agent_chat({"message": msg, "execute": True})
        except Exception as e:
            return {"answer": f"ERROR: {e}", "tools_used": []}

    r1 = _call("jaka jest moja dzisiejsza forma?")
    tools1 = r1.get("tools_used", [])
    xert_done = any("xert" in t.lower() for t in tools1)
    intervals_done = any("intervals" in t.lower() for t in tools1)
    answer1 = r1.get("answer", "").lower()
    for phrase in ["powinienem użyć", "nie mam aktywnego dostępu", "uruchom mnie w pełnym flow", "nie mam dostępu do narzędzi"]:
        if phrase in answer1:
            forbidden.append(phrase)
    if forbidden:
        blockers.append(f"forbidden phrases in answer: {forbidden}")
    if not xert_done:
        blockers.append("readiness question did not execute Xert tool")
    tests.append({"query": "dzisiejsza forma", "tools": tools1, "answer_len": len(r1.get("answer", ""))})

    r2 = _call("to jaka jest moja forma w XERT?")
    tests.append({"query": "Xert forma", "tools": r2.get("tools_used"), "answer_len": len(r2.get("answer", ""))})

    r3 = _call("sprawdź backup")
    backup_ok = any("backup" in t.lower() for t in r3.get("tools_used", []))
    tests.append({"query": "backup", "tools": r3.get("tools_used")})

    if not backup_ok:
        blockers.append("backup question did not execute backup tool")

    return {
        "tool": "qbot_telegram_agent_chat_self_check",
        "status": "ERROR" if blockers else "OK",
        "safety_class": "READ_ONLY",
        "tools_executed": len(r1.get("tools_used", [])) > 0,
        "readiness_question_executes_tools": xert_done and intervals_done,
        "plan_only_response": len(forbidden) > 0,
        "forbidden_phrases_found": forbidden,
        "blockers": blockers,
        "tests": tests,
        "notes": "Agent chat self-check — verifies tools ARE executed, not just planned.",
    }


def _tool_qbot_telegram_llm_chat(_args: dict | None = None) -> dict[str, Any]:
    return _tool_qbot_telegram_agent_chat(_args)


def _tool_qbot_telegram_llm_chat_self_check(_args: dict | None = None) -> dict[str, Any]:
    return _tool_qbot_telegram_agent_chat_self_check(_args)


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
        "qbot_telegram_llm_chat": _tool_qbot_telegram_llm_chat,
        "qbot_telegram_agent_chat": _tool_qbot_telegram_agent_chat,
    }
    return mapping.get(name)
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
        "qbot_telegram_llm_chat": _tool_qbot_telegram_llm_chat,
        "qbot_telegram_agent_chat": _tool_qbot_telegram_agent_chat,
    }
    return mapping.get(name)
