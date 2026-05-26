"""Local assistant inbox for roadmap runner notifications."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_INBOX_PATH = Path("/opt/qbot/app/state/qbot_assistant_inbox.json")
_LOCK = threading.Lock()
_MAX_SUMMARY = 1000
_MAX_FIELD = 500


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state() -> dict[str, Any]:
    return {"messages": [], "updated_at": _utc_now()}


def _ensure_parent() -> None:
    _INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)


def _safe_text(value: Any, limit: int = _MAX_FIELD) -> str:
    text = str(value or "")
    if len(text) > limit:
        return text[:limit] + "...<truncated>"
    return text


def _load_state() -> dict[str, Any]:
    with _LOCK:
        if not _INBOX_PATH.exists():
            return _default_state()
        try:
            data = json.loads(_INBOX_PATH.read_text(encoding="utf-8"))
        except Exception:
            return _default_state()
        if not isinstance(data, dict):
            return _default_state()
        data.setdefault("messages", [])
        if not isinstance(data["messages"], list):
            data["messages"] = []
        return data


def _save_state(data: dict[str, Any]) -> None:
    with _LOCK:
        _ensure_parent()
        data = dict(data)
        data["updated_at"] = _utc_now()
        tmp = _INBOX_PATH.with_suffix(_INBOX_PATH.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(_INBOX_PATH)


def _normalize_status(value: Any) -> str:
    status = str(value or "").strip().upper()
    allowed = {
        "PASS",
        "BLOCKED",
        "FAIL",
        "WARN",
        "APPROVAL_REQUIRED",
        "SECURITY_BLOCKED",
        "DONE",
        "PAUSED",
    }
    return status if status in allowed else "PASS"


def _message_view(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": message.get("id"),
        "created_at": message.get("created_at"),
        "source": message.get("source"),
        "block": message.get("block"),
        "task_id": message.get("task_id"),
        "status": message.get("status"),
        "summary": message.get("summary"),
        "commit": message.get("commit"),
        "next_action": message.get("next_action"),
        "requires_user_decision": bool(message.get("requires_user_decision")),
        "read": bool(message.get("read")),
        "dry_run": bool(message.get("dry_run")),
        "task_progress_percent": message.get("task_progress_percent"),
        "block_progress_percent": message.get("block_progress_percent"),
        "step_name": message.get("step_name"),
    }


def _tool_qbot_assistant_inbox_add(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    state = _load_state()
    message = {
        "id": str(args.get("id") or uuid.uuid4()),
        "created_at": _utc_now(),
        "source": _safe_text(args.get("source", "roadmap_runner"), 120),
        "block": _safe_text(args.get("block", ""), 40),
        "task_id": _safe_text(args.get("task_id", ""), 80),
        "status": _normalize_status(args.get("status", "PASS")),
        "summary": _safe_text(args.get("summary", ""), _MAX_SUMMARY),
        "commit": _safe_text(args.get("commit", ""), 32),
        "next_action": _safe_text(args.get("next_action", ""), _MAX_SUMMARY),
        "requires_user_decision": bool(args.get("requires_user_decision", False)),
        "read": False,
        "dry_run": bool(args.get("dry_run", False)),
        "task_progress_percent": int(args.get("task_progress_percent", 0) or 0),
        "block_progress_percent": int(args.get("block_progress_percent", 0) or 0),
        "current_step": int(args.get("current_step", 0) or 0),
        "total_steps": int(args.get("total_steps", 0) or 0),
        "step_name": _safe_text(args.get("step_name", ""), 120),
    }
    state.setdefault("messages", [])
    state["messages"].append(message)
    _save_state(state)
    return {
        "tool": "qbot_assistant_inbox_add",
        "status": "OK",
        "message": _message_view(message),
        "count": len(state["messages"]),
        "unread_count": len([m for m in state["messages"] if not m.get("read")]),
    }


def _tool_qbot_assistant_inbox_list(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    limit_raw = args.get("limit", 20)
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        return {"tool": "qbot_assistant_inbox_list", "status": "error", "error": f"invalid limit: {limit_raw!r}"}
    limit = max(1, min(100, limit))
    unread_only = bool(args.get("unread_only", False))
    source_filter = str(args.get("source", "") or "").strip()
    block_filter = str(args.get("block", "") or "").strip()
    status_filter = str(args.get("status", "") or "").strip().upper()

    state = _load_state()
    messages = list(reversed(state.get("messages", [])))
    filtered: list[dict[str, Any]] = []
    for message in messages:
        if unread_only and message.get("read"):
            continue
        if source_filter and str(message.get("source", "")) != source_filter:
            continue
        if block_filter and str(message.get("block", "")) != block_filter:
            continue
        if status_filter and str(message.get("status", "")).upper() != status_filter:
            continue
        filtered.append(_message_view(message))
        if len(filtered) >= limit:
            break

    return {
        "tool": "qbot_assistant_inbox_list",
        "status": "OK",
        "count": len(filtered),
        "messages": filtered,
        "filters": {
            "limit": limit,
            "unread_only": unread_only,
            "source": source_filter or None,
            "block": block_filter or None,
            "status": status_filter or None,
        },
    }


def _tool_qbot_assistant_inbox_mark_read(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    message_id = str(args.get("id") or args.get("message_id") or "").strip()
    ids_raw = args.get("ids")
    ids = [message_id] if message_id else []
    if isinstance(ids_raw, list):
        ids.extend([str(i).strip() for i in ids_raw if str(i).strip()])
    ids = [i for i in ids if i]
    if not ids:
        return {"tool": "qbot_assistant_inbox_mark_read", "status": "error", "error": "message id missing"}

    state = _load_state()
    changed = 0
    for message in state.get("messages", []):
        if message.get("id") in ids and not message.get("read"):
            message["read"] = True
            changed += 1
    _save_state(state)

    return {
        "tool": "qbot_assistant_inbox_mark_read",
        "status": "OK",
        "changed": changed,
        "ids": ids,
        "unread_count": len([m for m in state.get("messages", []) if not m.get("read")]),
    }


def _tool_qbot_assistant_inbox_status(_args: dict | None = None) -> dict[str, Any]:
    state = _load_state()
    messages = state.get("messages", [])
    unread = [m for m in messages if not m.get("read")]
    latest = messages[-1] if messages else None
    statuses = {}
    for message in messages:
        statuses[str(message.get("status", "UNKNOWN")).upper()] = statuses.get(
            str(message.get("status", "UNKNOWN")).upper(), 0
        ) + 1
    return {
        "tool": "qbot_assistant_inbox_status",
        "status": "OK",
        "path": str(_INBOX_PATH),
        "total_messages": len(messages),
        "unread_messages": len(unread),
        "latest_message": _message_view(latest) if latest else None,
        "status_counts": statuses,
        "updated_at": state.get("updated_at"),
    }

