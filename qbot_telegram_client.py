"""Qbot Telegram client — safe API interface, no token leaks."""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from typing import Any

_MAX_MSG = 4096
_TIMEOUT = 10


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def _enabled() -> bool:
    return os.getenv("TELEGRAM_ENABLED", "").lower() == "true" and bool(_token())


def _api(method: str, data: dict | None = None) -> dict[str, Any]:
    token = _token()
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not set"}
    url = f"https://api.telegram.org/bot[REDACTED]/{method}".replace("[REDACTED]", "")
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        if data:
            req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.code}", "description": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def send_message(chat_id: int | str, text: str) -> dict[str, Any]:
    if not _enabled():
        return {"ok": False, "error": "Telegram not enabled"}
    messages = [text[i:i + _MAX_MSG] for i in range(0, len(text), _MAX_MSG)]
    results = []
    for msg in messages:
        results.append(_api("sendMessage", {"chat_id": str(chat_id), "text": msg, "parse_mode": "HTML"}))
    return results[0] if len(results) == 1 else results[-1]


def get_webhook_info() -> dict[str, Any]:
    token = _token()
    if not token:
        return {"ok": False, "error": "token missing"}
    return _api("getWebhookInfo")


def set_webhook(url: str, secret_token: str | None = None) -> dict[str, Any]:
    if not url.startswith("https://"):
        return {"ok": False, "error": "webhook URL must be https://"}
    data: dict[str, Any] = {"url": url}
    if secret_token:
        data["secret_token"] = secret_token
    return _api("setWebhook", data)


def delete_webhook() -> dict[str, Any]:
    return _api("deleteWebhook")


def validate_update(update: dict) -> tuple[bool, str | None]:
    if not isinstance(update, dict):
        return False, "invalid update format"
    if "message" not in update:
        return False, "no message field"
    msg = update.get("message", {})
    if "text" not in msg:
        return False, "no text in message"
    return True, None


def extract_chat_id(update: dict) -> int | None:
    return update.get("message", {}).get("chat", {}).get("id")


def extract_message_text(update: dict) -> str:
    return update.get("message", {}).get("text", "")


def is_allowed_chat(chat_id: int) -> bool:
    if os.getenv("TELEGRAM_ALLOW_ALL_CHATS", "").lower() == "true":
        return True
    allowed = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
    if not allowed:
        return False
    return str(chat_id) in allowed.split(",")
