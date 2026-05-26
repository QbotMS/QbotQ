"""QBot task queue — MCP-driven task exchange for ChatGPT → CLI execution."""
from __future__ import annotations

import json
import os
import uuid
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_STATE_PATH = Path("/opt/qbot/app/state/qbot_task_queue.json")
_MAX_TASKS = 500


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict[str, Any]:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _STATE_PATH.exists():
        return {"tasks": [], "updated_at": None}
    try:
        data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"tasks": [], "updated_at": None}
        data.setdefault("tasks", [])
        data.setdefault("updated_at", None)
        return data
    except Exception:
        return {"tasks": [], "updated_at": None}


def _save(data: dict[str, Any]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = dict(data)
    data["updated_at"] = _utc_now()
    if len(data.get("tasks", [])) > _MAX_TASKS:
        data["tasks"] = data["tasks"][-_MAX_TASKS:]
    _STATE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# TOOLS
# ═══════════════════════════════════════════════════════════════════════════

def _tool_qbot_task_queue_add(args: dict | None = None) -> dict[str, Any]:
    """Add a task to the queue. source=chatgpt_mcp by default."""
    args = args or {}
    title = str(args.get("title", "") or "").strip()[:500]
    description = str(args.get("description", "") or "").strip()[:4000]
    source = str(args.get("source", "chatgpt_mcp")).strip()[:100]
    style = str(args.get("style", "short")).strip()[:20]
    tools_to_use = args.get("tools_to_use", [])
    if isinstance(tools_to_use, str):
        tools_to_use = [t.strip() for t in tools_to_use.split(",") if t.strip()]
    tools_to_use = (tools_to_use or [])[:20]

    if not title:
        return {"tool": "qbot_task_queue_add", "status": "ERROR",
                "safety_class": "WRITE_SAFE", "error": "title is required"}

    task_id = uuid.uuid4().hex[:12]
    task = {
        "id": task_id,
        "source": source,
        "title": title,
        "description": description[:4000],
        "tools_to_use": tools_to_use,
        "style": style,
        "status": "pending",
        "result_summary": None,
        "error": None,
        "created_at": _utc_now(),
        "run_at": None,
        "completed_at": None,
    }

    data = _load()
    data["tasks"].append(task)
    _save(data)

    return {
        "tool": "qbot_task_queue_add",
        "status": "OK",
        "safety_class": "WRITE_SAFE",
        "task_id": task_id,
        "title": title,
        "queue_length": len(data["tasks"]),
    }


def _tool_qbot_task_queue_list(args: dict | None = None) -> dict[str, Any]:
    """List tasks in queue, filtered by status."""
    args = args or {}
    status_filter = str(args.get("status", "") or "").strip().lower()
    limit = min(max(int(args.get("limit", 50) or 50), 1), 200)
    data = _load()
    tasks = data.get("tasks", [])
    if status_filter:
        tasks = [t for t in tasks if t.get("status", "").lower() == status_filter]
    tasks = tasks[-limit:]

    return {
        "tool": "qbot_task_queue_list",
        "status": "OK",
        "safety_class": "READ_ONLY",
        "tasks": tasks,
        "queue_total": len(data.get("tasks", [])),
        "filtered_count": len(tasks),
        "status_filter": status_filter or "all",
    }


def _tool_qbot_task_queue_next(args: dict | None = None) -> dict[str, Any]:
    """Get the next pending task (does not change state)."""
    data = _load()
    tasks = data.get("tasks", [])
    pending = [t for t in tasks if t.get("status") == "pending"]
    if not pending:
        return {
            "tool": "qbot_task_queue_next",
            "status": "OK",
            "safety_class": "READ_ONLY",
            "task": None,
            "pending_count": 0,
            "total_count": len(tasks),
            "note": "No pending tasks",
        }
    next_task = pending[0]
    return {
        "tool": "qbot_task_queue_next",
        "status": "OK",
        "safety_class": "READ_ONLY",
        "task": next_task,
        "pending_count": len(pending),
        "total_count": len(tasks),
    }


def _tool_qbot_task_queue_status(args: dict | None = None) -> dict[str, Any]:
    """Update task status: start / pass / blocked / fail. Safe write."""
    args = args or {}
    task_id = str(args.get("task_id", "") or "").strip()
    new_status = str(args.get("status", "") or "").strip().lower()
    result_summary = str(args.get("result_summary", "") or "").strip()[:2000]
    error_detail = str(args.get("error", "") or "").strip()[:1000]
    valid = {"pending", "in_progress", "pass", "blocked", "fail"}
    if new_status not in valid:
        return {"tool": "qbot_task_queue_status", "status": "ERROR",
                "safety_class": "WRITE_SAFE",
                "error": f"invalid status '{new_status}'. Use: {valid}"}
    if not task_id:
        return {"tool": "qbot_task_queue_status", "status": "ERROR",
                "safety_class": "WRITE_SAFE", "error": "task_id is required"}

    data = _load()
    found = None
    for t in data["tasks"]:
        if t.get("id") == task_id:
            found = t
            break
    if not found:
        return {"tool": "qbot_task_queue_status", "status": "ERROR",
                "safety_class": "WRITE_SAFE",
                "error": f"task_id {task_id} not found"}

    found["status"] = new_status
    if result_summary:
        found["result_summary"] = result_summary
    if error_detail:
        found["error"] = error_detail
    if new_status == "in_progress" and not found.get("run_at"):
        found["run_at"] = _utc_now()
    if new_status in ("pass", "blocked", "fail"):
        found["completed_at"] = _utc_now()

    _save(data)

    return {
        "tool": "qbot_task_queue_status",
        "status": "OK",
        "safety_class": "WRITE_SAFE",
        "task_id": task_id,
        "new_status": new_status,
        "queue_total": len(data["tasks"]),
    }
