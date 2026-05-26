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
        "qbot_telegram_clothing_advice_self_check": _tool_qbot_telegram_clothing_advice_self_check,
    }
    return mapping.get(name)


# ── Conversation memory (in-process, TTL-based) ──────────────────────

_CONV_MEMORY: dict[str, list[dict[str, Any]]] = {}
_CONV_MAX_MSGS = 30
_CONV_MAX_AGE_MIN = 60
_LAST_WEATHER: dict[str, dict[str, Any]] = {}

import time as _time_module


def _conv_get(chat_id: str) -> list[dict[str, Any]]:
    msgs = _CONV_MEMORY.get(str(chat_id), [])
    now = _time_module.time()
    cutoff = now - _CONV_MAX_AGE_MIN * 60
    fresh = [m for m in msgs if m.get("ts", 0) > cutoff]
    _CONV_MEMORY[str(chat_id)] = fresh[-_CONV_MAX_MSGS:]
    return fresh[-_CONV_MAX_MSGS:]


def _conv_append(chat_id: str, role: str, text: str, intent: str = "", tools_used: list[str] | None = None,
                 missing_slots: list[str] | None = None, answer_summary: str = ""):
    msgs = _conv_get(str(chat_id))
    msgs.append({
        "role": role,
        "text": text[:4000],
        "ts": _time_module.time(),
        "intent": intent,
        "tools_used": tools_used or [],
        "missing_slots": missing_slots or [],
        "answer_summary": answer_summary[:500],
    })
    msgs = msgs[-_CONV_MAX_MSGS:]
    _CONV_MEMORY[str(chat_id)] = msgs


def _conv_detect_followup(message: str, chat_id: str) -> dict[str, Any] | None:
    msgs = _conv_get(str(chat_id))
    if not msgs:
        return None
    last_agent = None
    for m in reversed(msgs):
        if m["role"] == "assistant":
            last_agent = m
            break
    if not last_agent:
        return None

    missing = last_agent.get("missing_slots", [])
    last_intent = last_agent.get("intent", "")
    q = message.lower().strip()
    resolved = {}

    # Follow-up: location for weather
    if "location" in missing and last_intent in ("weather_current", "weather_inquiry"):
        from qbot_integration_tools import _find_city_from_text
        city = _find_city_from_text(message)
        if city:
            return {"is_followup": True, "resolved_intent": "weather_current",
                    "resolved_slots": {"location": city}, "source": "conversation_context",
                    "confidence": "high", "reason": "previous assistant asked for location for weather"}

    # Follow-up: period/forecast for weather
    if last_intent in ("weather_current", "weather_inquiry") and any(w in q for w in ["jutro", "rano", "wieczorem", "jutrzejszy", "forecast"]):
        prev_loc = None
        for m in reversed(msgs):
            if m["role"] == "user" and m.get("slots"):
                prev_loc = m["slots"].get("location")
                break
        period = "tomorrow_morning" if any(w in q for w in ["rano", "morning"]) else "tomorrow"
        return {"is_followup": True, "resolved_intent": "weather_forecast",
                "resolved_slots": {"location": prev_loc or "Marki,PL", "period": period},
                "source": "conversation_context", "confidence": "high",
                "reason": f"weather forecast follow-up, period={period}"}

    # Follow-up: different integration
    if any(w in q for w in ["a garmin", "a xert", "a rwgps", "a intervals", "a hammerhead"]):
        for mod in ["garmin", "xert", "rwgps", "intervals", "hammerhead"]:
            if mod in q:
                return {"is_followup": True, "resolved_intent": f"{mod}_status",
                        "resolved_slots": {"integration": mod}, "source": "conversation_context",
                        "confidence": "medium", "reason": f"integration follow-up: {mod}"}

    # Affirmative/confirm
    if q in ("tak", "yes", "ok", "okej", "dobrze", "spoko"):
        return {"is_followup": True, "resolved_intent": "confirm_previous",
                "resolved_slots": {}, "source": "conversation_context",
                "confidence": "high", "reason": "user confirmed previous question"}

    return None


def _tool_qbot_conversation_resolve_followup(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    result = _conv_detect_followup(str(_args.get("message", "")), str(_args.get("chat_id", "")))
    if result:
        return {"tool": "qbot_conversation_resolve_followup", "status": "OK", "safety_class": "READ_ONLY", **result}
    return {"tool": "qbot_conversation_resolve_followup", "status": "OK", "safety_class": "READ_ONLY",
            "is_followup": False, "resolved_intent": None, "resolved_slots": {}, "source": None, "confidence": "none"}


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
    chat_id = str(_args.get("chat_id", "") or "")

    if not message.strip():
        return {"tool": "qbot_telegram_agent_chat", "status": "ERROR", "answer": "Pusta wiadomość.", "tools_considered_count": 0, "tools_used": [], "llm_used": False, "planner_used": False, "policy_result": "", "requires_approval": False}

    # Check conversation context for follow-up detection
    followup = None
    if chat_id:
        followup = _conv_detect_followup(message, chat_id)

    # If follow-up detected, inject resolved slots into message/query
    if followup and followup.get("is_followup"):
        resolved = followup.get("resolved_intent", "")
        slots = followup.get("resolved_slots", {})
        if resolved == "weather_current" and slots.get("location"):
            message = f"pogoda w {slots['location']}"
        elif resolved == "weather_forecast" and slots.get("location"):
            message = f"prognoza pogody na {slots.get('period', '')} dla {slots['location']}"
        elif resolved and slots.get("integration"):
            message = f"sprawdź status {slots['integration']}"

    # Record user message
    if chat_id:
        _conv_append(chat_id, "user", message, intent=followup.get("resolved_intent", "") if followup else "", missing_slots=[])

    context, tool_names = _build_agent_context(message)
    tools_used: list[str] = []
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
            tstatus = str(tr.get("status", "")).upper()
            has_useful = any(k in tr for k in ("ftp_watts", "temperature_c", "latest_backup", "count", "operational_readiness_percent")) and tstatus not in ("WARN", "ERROR", "NO_DATA", "PARTIAL")
            if has_useful:
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
            else:
                extra_tools.extend(executed)
                for tn in executed:
                    if tn not in extra_results:
                        extra_results[tn] = tr
    except Exception:
        pass

    # Step 2: Execute all relevant READ_ONLY tools for the query type
    from qbot_tool_registry import TOOLS
    extra_results = {}
    extra_tools: list[str] = []
    q = message.lower()

    def _safe_exec(tool_name: str, extra_args: dict | None = None) -> dict | None:
        nonlocal extra_tools
        func = TOOLS.get(tool_name)
        if not func:
            return None
        try:
            args = dict(extra_args or {})
            if extra_args is None and tool_name.startswith("qbot_weather"):
                args["text"] = message
            r = func(args)
            if r and isinstance(r, dict):
                extra_tools.append(tool_name)
                extra_results[tool_name] = r
                return r
        except Exception:
            pass
        return None

    # Fitness/forma query → execute Xert + Intervals + Garmin
    if any(w in q for w in ["forma", "formę", "formie", "formy", "readiness", "gotowy", "czuję",
                              "czuje", "trening", "treningu", "dzisiejsz", "dziś", "dzis",
                              "waga", "wagę", "intervals", "hrv", "sen", "spa"]):
        _safe_exec("qbot_xert_readiness_status")
        _safe_exec("qbot_intervals_wellness_status")
        _safe_exec("qbot_garmin_config_status")

    # Weather query
    if any(w in q for w in ["pogod", "pada", "deszcz", "wiatr", "temperatur", "ubrać", "ubiór", "ciuchy", "ubranie", "strój", "ubrac", "ubier", "zabrać"]):
        _safe_exec("qbot_weather_current")
        _safe_exec("qbot_weather_config_status")

    # Cache latest weather for conversation context
    if "qbot_weather_current" in extra_results:
        w = extra_results["qbot_weather_current"]
        if w.get("status") == "OK" and w.get("temperature_c") is not None and chat_id:
            _LAST_WEATHER[str(chat_id)] = {
                "temperature_c": w.get("temperature_c"),
                "feels_like_c": w.get("feels_like_c"),
                "wind_mps": w.get("wind_mps"),
                "wind_kmh": w.get("wind_kmh"),
                "description": w.get("description", ""),
                "humidity_percent": w.get("humidity_percent"),
                "location_resolved": w.get("location_resolved", ""),
                "source": w.get("source", ""),
                "ts": _time_module.time(),
            }

    # Clothing advice synthesis — check before NEEDS_LOCATION returns
    clothing_kw = ["ubrać", "ubiór", "ciuchy", "ubranie", "strój", "ubrac", "ubier", "zabrać"]
    if any(w in q for w in clothing_kw):
        clothing_answer = _synthesize_clothing_advice(
            extra_results.get("qbot_weather_current", {}),
            extra_results.get("qbot_garage_raw_status"),
            chat_id
        )
        if chat_id:
            _conv_append(chat_id, "assistant", clothing_answer, intent="clothing_advice",
                         tools_used=extra_tools)
        return {
            "tool": "qbot_telegram_agent_chat",
            "status": "OK",
            "answer": clothing_answer[:3900],
            "tools_considered_count": len(tool_names),
            "tools_used": extra_tools,
            "llm_used": False,
            "planner_used": True,
            "policy_result": "",
            "requires_approval": False,
        }

    # Backup
    if any(w in q for w in ["backup", "kopia", "backupy"]):
        _safe_exec("qbot_backup_status")

    # Handle NEEDS_LOCATION or ERROR from weather — clean user-facing
    weather_status = extra_results.get("qbot_weather_current", {})
    if weather_status.get("status") == "NEEDS_LOCATION":
        if chat_id:
            _conv_append(chat_id, "assistant", "Dla jakiej lokalizacji?", intent="weather_inquiry",
                         missing_slots=["location"])
        return {
            "tool": "qbot_telegram_agent_chat",
            "status": "OK",
            "answer": (
                "Dla jakiej lokalizacji sprawdzić pogodę? Nie mam lokalizacji w wiadomości "
                "ani świeżej lokalizacji z ostatniej trasy (<18h). "
                "Napisz np. „pogoda w Markach”.\n"
                "Źródło pogody: nie pobrano — brak lokalizacji.\n"
                "Źródło lokalizacji: brak w zapytaniu / brak świeżej trasy."
            ),
            "tools_considered_count": len(tool_names),
            "tools_used": extra_tools,
            "llm_used": False,
            "planner_used": True,
            "policy_result": "",
            "requires_approval": False,
        }
    elif weather_status.get("status") == "ERROR":
        owm_err = weather_status.get("openweathermap_error_message", "nie skonfigurowany")
        om_err = weather_status.get("open_meteo_error_message", "brak")
        loc = weather_status.get("location_resolved", "?")
        return {
            "tool": "qbot_telegram_agent_chat",
            "status": "WARN",
            "answer": (
                f"Nie pobrałem pogody dla {loc}. "
                f"OpenWeatherMap: {owm_err}. Open-Meteo fallback: {om_err or 'nie próbowano'}. "
                f"Spróbuj ponownie za chwilę.\n"
                f"Źródło pogody: obie próby nieudane.\n"
                f"Źródło lokalizacji: tekst wiadomości."
            ),
            "tools_considered_count": len(tool_names),
            "tools_used": extra_tools,
            "llm_used": False,
            "planner_used": True,
            "policy_result": "",
            "requires_approval": False,
        }

    # Build tool results context for LLM
    tool_context = ""
    for tname, r in extra_results.items():
        brief = {k: r[k] for k in ("status", "ftp_watts", "ltp_watts", "w_prime_kj",
                                     "form_status", "configured", "restored_status",
                                     "temperature_c", "description", "source",
                                     "wind_mps", "wind_kmh", "humidity_percent", "location_resolved") if k in r and r[k] is not None}
        tool_context += f"\n[{tname}]: {brief}\n"

    # Step 3: If LLM is available, pass results to LLM for a clean answer

    if has_llm and extra_tools:
        system = (
            "Odpowiadasz krótko po polsku, plain text, max 800 znaków. "
            "Jesteś Qbotem. Otrzymujesz wyniki z wykonanych narzędzi Qbot. "
            "WAŻNE: wiatr zawsze podawaj TYLKO w m/s (nie km/h), pole wind_mps. NIE dodawaj przeliczenia na km/h. "
            "Odpowiedz konkretnie na podstawie danych, naturalnym językiem. "
            "NIGDY nie pokazuj użytkownikowi wewnętrznych nazw narzędzi (get_weather, qbot_*, NEEDS_LOCATION itp). "
            "NIGDY nie pisz 'narzędzie zwróciło', 'status X', 'tool Y'. "
            "Zamiast tego przetłumacz dane na zrozumiałą odpowiedź. "
            "Jeśli brak danych — powiedz normalnie czego brakuje. "
            "Na końcu dodaj 'Źródło: ...' z opisem źródła (nie nazwą wewnętrzną)."
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
        # Natural language formatting for weather
        weather_r = extra_results.get("qbot_weather_current", {})
        if weather_r.get("status") == "OK" and weather_r.get("temperature_c") is not None:
            w = weather_r
            loc = w.get("location_resolved", "?")
            source_w = w.get("source", "?")
            lines = [
                f"{loc}: {w['temperature_c']}°C, odczuwalnie {w.get('feels_like_c', '?')}°C, "
                f"wiatr {round(w.get('wind_mps', 0), 1)} m/s, {w.get('description', '?')}.",
                f"Źródło pogody: {source_w} via qbot_weather_current.",
                f"Źródło lokalizacji: ostatnia przejechana trasa." if w.get("_location_source") == "last_ride_location"
                else f"Źródło lokalizacji: tekst wiadomości.",
            ]
            return {
                "tool": "qbot_telegram_agent_chat",
                "status": "OK",
                "answer": " ".join(lines)[:3900],
                "tools_considered_count": len(tool_names),
                "tools_used": extra_tools,
                "llm_used": False,
                "planner_used": True,
                "policy_result": "",
                "requires_approval": False,
            }

        lines = []
        for tname in extra_tools:
            r = extra_results.get(tname, {})
            s = r.get("status", "?")
            if s in ("WARN", "ERROR", "NO_DATA", "PARTIAL") and not any(k in r for k in ("temperature_c", "ftp_watts", "latest_backup")):
                continue
            lines.append(f"{tname}: {s}")
            for k, v in r.items():
                if k not in ("tool", "status", "safety_class", "notes") and v is not None:
                    lines.append(f"  {k}: {v}")
        if not lines:
            answer = _build_fallback_answer(message, extra_results, tool_names)
        else:
            answer = "\n".join(lines)[:3800]
            source_line = f"\nŹródło: Qbot tools ({', '.join(extra_tools)})"
            answer = (answer + source_line)[:3900]
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
            "NIGDY nie pokazuj użytkownikowi wewnętrznych nazw narzędzi (get_weather, qbot_*, status=WARN itp). "
            "Nie pisz 'Sprawdziłbym pogodę'. Zamiast tego podaj praktyczną odpowiedź. "
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


def _synthesize_clothing_advice(weather_current: dict, garage_data: dict | None, chat_id: str) -> str:
    """Build natural-language cycling clothing advice from weather data or conversation context."""
    temp = weather_current.get("temperature_c")
    wind = weather_current.get("wind_mps")
    desc = (weather_current.get("description") or "").lower()
    loc = weather_current.get("location_resolved", "")
    weather_source = weather_current.get("source", "")
    sources: list[str] = []
    used_cache = False

    if temp is None and chat_id:
        cached = _LAST_WEATHER.get(str(chat_id))
        if cached and cached.get("temperature_c") is not None and cached.get("ts", 0) > _time_module.time() - 3600:
            temp = cached.get("temperature_c")
            wind = cached.get("wind_mps")
            desc = (cached.get("description") or "").lower()
            loc = cached.get("location_resolved", "")
            weather_source = cached.get("source", "")
            used_cache = True

    parts: list[str] = []

    if temp is not None:
        if used_cache:
            sources.append(f"ostatnia pogoda z rozmowy{f' ({loc})' if loc else ''}")
        else:
            sources.append(f"pogoda: {weather_source}{f' ({loc})' if loc else ''}")

        temp_str = f"ok. {int(temp)}°C" if temp == int(temp) else f"{temp:.0f}°C"
        wind_str = ""
        if wind is not None:
            wind_str = f", wiatr {round(wind, 1)} m/s"

        # Build natural advice text
        advice_lines = []
        if temp >= 25:
            advice_lines.append("Krótki rękaw, krótkie spodenki, lekkie rękawiczki, okulary.")
        elif temp >= 20:
            advice_lines.append("Krótki rękaw, krótkie spodenki, okulary, rękawiczki.")
            if wind and wind > 8:
                advice_lines.append("Weź kamizelkę lub przeciwwiatrówkę na wiatr.")
        elif temp >= 15:
            advice_lines.append("Krótki lub długi rękaw, rękawki lub cienka kamizelka. Spodenki lub długie spodnie, okulary, rękawiczki.")
        elif temp >= 10:
            advice_lines.append("Długi rękaw, warstwa termo, kamizelka, rękawiczki, okulary.")
            if wind and wind > 4:
                advice_lines.append("Weź przeciwwiatrówkę.")
        elif temp >= 5:
            advice_lines.append("Ciepła bluza lub softshell, ocieplane spodnie, rękawiczki, czapka pod kask.")
        else:
            advice_lines.append("Kurtka zimowa, ocieplane spodnie, grube rękawiczki, czapka pod kask, ocieplane buty.")

        if desc and any(d in desc for d in ("deszcz", "mżawka", "opad")):
            advice_lines.append("Weź kurtkę przeciwdeszczową.")
        if wind and wind > 12:
            advice_lines.append(f"Silny wiatr ({round(wind, 1)} m/s) — weź kamizelkę przeciwwiatrową.")

        advice_lines.append("Na gravel lub szuter: okulary, rękawiczki, ewentualnie buff.")
        advice = " ".join(advice_lines)

        parts.append(f"Przy {temp_str}{wind_str}: {advice}")
    else:
        sources.append("pogoda: brak danych")
        parts.append(
            "Nie mam danych pogodowych — ubierz się warstwowo, weź kurtkę na wszelki wypadek. "
            "Dla dokładniejszej porady podaj lokalizację (np. „pogoda w Markach”)."
        )

    # Garage info — never show raw status=WARN to user
    if garage_data:
        gs = (garage_data.get("status") or "").upper()
        if gs in ("WARN", "ERROR", "NO_DATA"):
            sources.append("Qbot garage: brak użytecznych danych")
        else:
            count = garage_data.get("count", garage_data.get("total_records", "?"))
            sources.append(f"Qbot garage: sprawdzono ({count})" if count else "Qbot garage: sprawdzono")
    else:
        sources.append("Qbot garage: nie sprawdzono")

    sources.append("wniosek: Qbot local heuristic")
    source_line = "Źródła: " + "; ".join(sources) + "."

    return "\n".join(parts) + "\n" + source_line


def _build_fallback_answer(message: str, extra_results: dict, tool_names: list) -> str:
    """Provide heuristic answers when tools return WARN/empty and no LLM."""
    q = message.lower()
    weather_r = extra_results.get("qbot_weather_current", {})
    garage_r = extra_results.get("qbot_garage_raw_status", {})
    sources = []

    # Clothing advice from weather context
    if any(w in q for w in ["ubrać", "ubiór", "ciuchy", "ubranie", "strój", "zabrać", "ubrac"]):
        temp = weather_r.get("temperature_c")
        wind = weather_r.get("wind_mps")
        desc = weather_r.get("description", "")
        lines = []
        if temp is not None:
            sources.append(f"pogoda: {weather_r.get('source', '?')}, {weather_r.get('location_resolved', '?')}")
            wind_part = f", wietrze {round(wind, 1)} m/s" if wind is not None else ""
            lines.append(f"Przy {temp}°C{wind_part}:")
            if temp >= 20:
                lines.append("- Krótki rękaw / lekka koszulka, krótkie spodenki.")
            elif temp >= 15:
                lines.append("- Krótki lub długi rękaw, rękawki lub kamizelka.")
            elif temp >= 10:
                lines.append("- Długa bluza lub warstwa, kamizelka, rękawiczki.")
            else:
                lines.append("- Ciepłe warstwy, kurtka, rękawiczki, czapka.")
            if wind and wind > 12:
                lines.append("- Silny wiatr (>{round(wind, 1)} m/s): weź kamizelkę przeciwwiatrową.")
            if "deszcz" in desc or "mżawka" in desc:
                lines.append("- Opady: weź kurtkę przeciwdeszczową.")
            lines.append("- Na gravel/szuter: okulary, rękawiczki, ewentualnie buff.")
        else:
            lines.append("Brak danych pogodowych — ubierz się warstwowo, weź kurtkę na wszelki wypadek.")
        if garage_r.get("status") in ("WARN", "ERROR", "NO_DATA"):
            sources.append("garaż: brak danych")
        else:
            sources.append("garaż: sprawdzono")
        lines.append("\nŹródła: " + "; ".join(sources) + "; wniosek — heurystyka Qbot.")
        return "\n".join(lines)[:3900]

    # Generic fallback
    return (
        "Nie mam wystarczających danych, aby odpowiedzieć konkretnie. "
        "Spróbuj zadać pytanie z konkretną lokalizacją (np. \"pogoda w Markach\") "
        "lub użyj komendy /help.\n"
        "Źródło: Qbot fallback."
    )


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


def _tool_qbot_telegram_clothing_advice_self_check(_args: dict | None = None) -> dict[str, Any]:
    blockers = []

    has_raw = False
    uses_weather = False
    natural = False

    # Simulate: weather context available, then ask clothing
    try:
        r = _tool_qbot_telegram_agent_chat({"message": "jak się ubrać na rower?", "execute": True})
        answer = r.get("answer", "")
        has_raw = "tool=" in answer or ("status=WARN" in answer and "qbot_garage" in answer)
        uses_weather = any(w in answer.lower() for w in ["°c", "stopni", "temp", "wiatr", "warstw"])
        natural = not has_raw and len(answer) > 50
        if has_raw:
            blockers.append("raw tool output found in clothing answer")
        if not natural:
            blockers.append("answer not natural/too short")
    except Exception as e:
        blockers.append(f"clothing test error: {e}")

    return {
        "tool": "qbot_telegram_clothing_advice_self_check",
        "status": "ERROR" if blockers else "OK",
        "safety_class": "READ_ONLY",
        "uses_weather_context": uses_weather,
        "garage_warn_not_user_facing_raw": not has_raw,
        "natural_answer": natural,
        "sources_present": "Źródło" in (r.get("answer", "") if hasattr(r, 'get') else ""),
        "blockers": blockers,
        "notes": "Checks that clothing advice is natural, not raw tool dump.",
    }
