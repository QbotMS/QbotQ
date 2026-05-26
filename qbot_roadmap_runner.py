"""Controlled roadmap runner with assistant inbox and Telegram notifications."""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from qbot_assistant_inbox import _tool_qbot_assistant_inbox_add, _tool_qbot_assistant_inbox_list, _tool_qbot_assistant_inbox_mark_read, _tool_qbot_assistant_inbox_status

ROADMAP_PATH = Path("/opt/qbot/app/docs/qbot_implementation_roadmap.md")
STATE_PATH = Path("/opt/qbot/app/state/qbot_roadmap_runner_state.json")
PROJECT_ROOT = Path("/opt/qbot/app")
STANDARD_TASK_STEPS: list[tuple[str, int]] = [
    ("preflight", 10),
    ("baseline checks", 20),
    ("applying changes", 35),
    ("running py_compile", 45),
    ("restarting qbot-api", 65),
    ("running self-check", 80),
    ("public endpoint check", 88),
    ("security grep", 95),
    ("git diff/status", 98),
    ("PASS / BLOCKED", 100),
]
ALLOWED_TASK_SAFETY = {"READ_ONLY", "LOCAL_WRITE", "DOCS_ONLY", "TEST_ONLY"}
DENYLIST_TOOL_PATTERNS = (
    "upload",
    "sync",
    "delete",
    "restore",
    "set_webhook",
    "send_test",
    "send_message",
    "execute_execute",
    "import_execute",
    "create_execute",
    "scheduler_activation",
)
_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state() -> dict[str, Any]:
    return {
        "runner_status": "IDLE",
        "current_block": None,
        "current_task_id": None,
        "last_task_id": None,
        "last_status": None,
        "last_commit": None,
        "last_error": None,
        "started_at": None,
        "updated_at": None,
        "tasks_completed": [],
        "tasks_blocked": [],
        "telegram_notifications": [],
        "last_telegram_notification_key": None,
        "task_progress_percent": 0,
        "block_progress_percent": 0,
        "current_step": 0,
        "total_steps": len(STANDARD_TASK_STEPS),
        "step_name": None,
        "last_task_summary": None,
        "last_task_tools": [],
        "preview_tasks_completed": [],
        "preview_tasks_blocked": [],
        "preview_block": None,
        "preview_total_tasks_in_block": 0,
        "preview_current_task_id": None,
        "preview_task_progress_percent": 0,
        "preview_block_progress_percent": 0,
        "preview_current_step": 0,
        "preview_total_steps": len(STANDARD_TASK_STEPS),
        "preview_step_name": None,
    }


def _ensure_parent() -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_state() -> dict[str, Any]:
    with _LOCK:
        if not STATE_PATH.exists():
            return _default_state()
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return _default_state()
        if not isinstance(data, dict):
            return _default_state()
        defaults = _default_state()
        for key, value in defaults.items():
            data.setdefault(key, copy.deepcopy(value))
        return data


def _save_state(state: dict[str, Any]) -> None:
    with _LOCK:
        _ensure_parent()
        payload = copy.deepcopy(state)
        payload["updated_at"] = _utc_now()
        tmp = STATE_PATH.with_suffix(STATE_PATH.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(STATE_PATH)


def _sanitize_text(value: Any, limit: int = 500) -> str:
    text = str(value or "")
    if len(text) > limit:
        return text[:limit] + "...<truncated>"
    return text


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _normalize_status(value: Any) -> str:
    status = str(value or "").strip().upper()
    allowed = {"PASS", "FAIL", "BLOCKED", "WARN", "APPROVAL_REQUIRED", "SECURITY_BLOCKED", "PAUSED", "DONE", "OK"}
    return status if status in allowed else "OK"


def _git(cmd: list[str], timeout: int = 8) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=timeout)


def _http_status(url: str, method: str = "GET", timeout_s: float = 5.0) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=timeout_s, trust_env=False, verify=False, follow_redirects=False) as client:
            resp = client.request(method, url)
            body = resp.text[:300] if resp.text else ""
            return {
                "ok": True,
                "status_code": resp.status_code,
                "content_type": resp.headers.get("content-type", ""),
                "body_preview": body,
            }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _baseline_checks() -> dict[str, Any]:
    from qbot_tools import _tool_qbot_api_self_check, _tool_qbot_git_status

    py_files = sorted(str(p) for p in PROJECT_ROOT.glob("qbot*.py"))
    py_compile = {"ok": False, "files": len(py_files), "stdout": "", "stderr": ""}
    if py_files:
        proc = _git(["python3", "-m", "py_compile", *py_files], timeout=60)
        py_compile = {
            "ok": proc.returncode == 0,
            "files": len(py_files),
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "returncode": proc.returncode,
        }
    try:
        api_self_check = _tool_qbot_api_self_check()
        local_health = {
            "ok": str(api_self_check.get("status", "")).upper() in {"OK", "WARN"},
            "status": api_self_check.get("status"),
            "checks": api_self_check.get("checks", []),
            "source": "qbot_api_self_check",
        }
    except Exception as exc:
        local_health = {"ok": False, "error": str(exc)}
    public_q = _http_status("https://qbot.cytr.us/q")
    public_health = _http_status("https://qbot.cytr.us/health")
    git_status = _tool_qbot_git_status()
    secret_hits = _scan_secret_patterns()
    return {
        "py_compile": py_compile,
        "local_health": local_health,
        "public_q": public_q,
        "public_health": public_health,
        "git_status": git_status,
        "secret_hits": secret_hits,
    }


def _scan_secret_patterns() -> dict[str, Any]:
    patterns = re.compile(r"\b(?:TOKEN|API_KEY|SECRET|PASSWORD|JWT)\s*=\s*([^\s#'\"`]+)")
    excludes = {".git", ".venv", "__pycache__", "outgoing", "logs", "backups"}
    skip_files = {".env.local", ".env.hammerhead-garmin-sync"}
    placeholder_markers = {"SET-ME", "WEBHOOK_SECRET", "PLACEHOLDER"}

    def _is_symbolic(value: str) -> bool:
        """True if value is a code reference (getenv, config access, etc.), not a real secret."""
        v = value.strip()
        if v.startswith("<") or v.endswith(">"):
            return True
        if v in ("***", "REDACTED"):
            return True
        # Code patterns: getenv, config access, env strings
        if any(sig in v for sig in (
            "env(", "os.getenv(", "os.environ", "cfg.",
            ".getenv(", ".environ", "getenv(",
        )):
            return True
        # Heuristic: symbolic references contain dots/parens from code, not raw values
        if "." in v or "(" in v or ")" in v:
            return True
        return False

    symbolic: list[dict[str, Any]] = []
    blocking: list[dict[str, Any]] = []
    changed_files: list[Path] = []
    env_local_in_git = False
    try:
        git = _git(["git", "status", "--short"], timeout=8)
        if git.returncode == 0:
            for line in git.stdout.splitlines():
                if not line.strip():
                    continue
                m = re.match(r"^[ MADRCU\?]{1,2}\s+(.*)$", line)
                rel = m.group(1).strip() if m else line.strip()
                if rel:
                    if rel.endswith(".env.local"):
                        env_local_in_git = True
                    changed_files.append(PROJECT_ROOT / rel)
    except Exception:
        changed_files = []
    if not changed_files:
        try:
            proc = _git(["git", "diff", "--name-only"], timeout=8)
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    rel = line.strip()
                    if rel:
                        changed_files.append(PROJECT_ROOT / rel)
        except Exception:
            changed_files = []
    if not changed_files:
        changed_files = [p for p in PROJECT_ROOT.rglob("*") if p.is_file()]

    for path in changed_files:
        if any(part in excludes for part in path.parts):
            continue
        if path.name in skip_files:
            continue
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for match in patterns.finditer(text):
            raw_value = match.group(1).strip()
            raw_value_upper = raw_value.upper()

            if raw_value.startswith("<") or raw_value.endswith(">"):
                continue
            if any(marker in raw_value_upper for marker in placeholder_markers):
                continue

            if _is_symbolic(raw_value):
                symbolic.append({
                    "file": path.relative_to(PROJECT_ROOT).as_posix(),
                    "sample": raw_value[:80],
                })
            else:
                blocking.append({
                    "file": path.relative_to(PROJECT_ROOT).as_posix(),
                    "sample": match.group(0)[:80],
                })
            if len(blocking) + len(symbolic) >= 50:
                break

    return {
        "blocking_hits_count": len(blocking),
        "symbolic_hits_count": len(symbolic),
        "blocking_samples": blocking[:10],
        "ignored_symbolic_samples": [s["sample"] for s in symbolic[:10]],
        "env_local_tracked": env_local_in_git,
        "status": "BLOCKED" if blocking else ("WARN" if symbolic else "OK"),
        "truncated": len(blocking) + len(symbolic) >= 50,
    }


def _step_plan_for_task(_task: dict[str, Any]) -> list[tuple[str, int]]:
    return STANDARD_TASK_STEPS


def _emit_progress(log_lines: list[str], task_id: str, step_idx: int, total_steps: int, step_name: str, pct: int) -> None:
    line = f"{task_id} [{pct}%] {step_name}"
    print(line, flush=True)
    log_lines.append(line)


def _load_roadmap_text() -> str:
    return ROADMAP_PATH.read_text(encoding="utf-8")


def _parse_yes_no(value: str) -> bool:
    return str(value).strip().lower() in {"yes", "true", "y", "1"}


def _infer_safety_class(task: dict[str, Any]) -> str:
    desc = " ".join([
        task.get("description", ""),
        task.get("files_likely_touched", ""),
        task.get("tools_tests", ""),
        task.get("done_criteria", ""),
    ]).lower()
    files = task.get("files_likely_touched", "").lower()
    approval = task.get("approval", False)
    if any(word in desc for word in ["upload", "sync", "delete", "restore", "activation", "mutating", "execute"]):
        return "CONTROLLED_ACTION" if approval else "LOCAL_WRITE"
    if files.startswith("docs/") or "docs/" in files:
        return "DOCS_ONLY"
    if any(word in desc for word in ["self-check", "test", "smoke", "preview"]):
        return "TEST_ONLY"
    if any(word in desc for word in ["status", "inventory", "read-only", "read only", "audit", "readiness", "summary"]):
        return "READ_ONLY"
    if approval:
        return "CONTROLLED_ACTION"
    return "LOCAL_WRITE"


def _parse_roadmap() -> list[dict[str, Any]]:
    text = _load_roadmap_text()
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_table = False
    for raw in text.splitlines():
        block_match = re.match(r"###\s+(P\d+)\.\s+(.+)", raw.strip())
        if block_match:
            if current:
                blocks.append(current)
            current = {
                "block_id": block_match.group(1),
                "block_title": block_match.group(2).strip(),
                "tasks": [],
            }
            in_table = False
            continue
        if raw.startswith("| Task ID |"):
            in_table = True
            continue
        if in_table and raw.startswith("|---"):
            continue
        if in_table and raw.startswith("|"):
            cells = [cell.strip() for cell in raw.strip().strip("|").split("|")]
            if len(cells) < 8 or cells[0] == "Task ID":
                continue
            if current is None:
                continue
            task = {
                "task_id": cells[0],
                "description": cells[1],
                "files_likely_touched": cells[2],
                "tools_tests": cells[3],
                "risk": cells[4],
                "done_criteria": cells[5],
                "autonomous": _parse_yes_no(cells[6]),
                "approval": _parse_yes_no(cells[7]),
            }
            task["safety_class"] = _infer_safety_class(task)
            task["requires_approval"] = bool(task["approval"]) or task["safety_class"] == "CONTROLLED_ACTION"
            task["eligible_for_auto"] = bool(task["autonomous"]) and not task["requires_approval"] and task["safety_class"] in ALLOWED_TASK_SAFETY
            task["status"] = "pending"
            current["tasks"].append(task)
            continue
        if in_table and not raw.strip():
            in_table = False
    if current:
        blocks.append(current)
    return blocks


def _roadmap_blocks() -> list[dict[str, Any]]:
    return _parse_roadmap()


def _flatten_tasks(block_filter: str | None = None) -> list[dict[str, Any]]:
    blocks = _roadmap_blocks()
    tasks: list[dict[str, Any]] = []
    for block in blocks:
        if block_filter and block["block_id"] != block_filter:
            continue
        for index, task in enumerate(block["tasks"], start=1):
            entry = copy.deepcopy(task)
            entry["block_id"] = block["block_id"]
            entry["block_title"] = block["block_title"]
            entry["block_order"] = blocks.index(block)
            entry["block_task_index"] = index
            tasks.append(entry)
    return tasks


def _get_policy_map() -> dict[str, dict[str, Any]]:
    try:
        from qbot_llm_planner import _tool_qbot_tool_policy_list
        result = _tool_qbot_tool_policy_list()
    except Exception:
        result = {"tools": []}
    policy_map: dict[str, dict[str, Any]] = {}
    for item in result.get("tools", []):
        if isinstance(item, dict) and item.get("name"):
            policy_map[str(item["name"])] = item
    return policy_map


def _safe_task_tools(task: dict[str, Any]) -> list[str]:
    tool_names = []
    for name in re.findall(r"qbot_[a-z0-9_]+", task.get("tools_tests", "")):
        lowered = name.lower()
        if any(pat in lowered for pat in DENYLIST_TOOL_PATTERNS):
            continue
        tool_names.append(name)
    return list(dict.fromkeys(tool_names))


def _task_execution_preview(task: dict[str, Any]) -> dict[str, Any]:
    tools = _safe_task_tools(task)
    policy_map = _get_policy_map()
    approved_tools: list[dict[str, Any]] = []
    blocked_tools: list[dict[str, Any]] = []
    for tool_name in tools:
        policy = policy_map.get(tool_name, {})
        if policy and policy.get("requires_approval"):
            blocked_tools.append({
                "tool": tool_name,
                "reason": "requires approval",
            })
            continue
        if policy and policy.get("allowed_auto_execute", True) is False:
            blocked_tools.append({
                "tool": tool_name,
                "reason": "not allowed for auto execution",
            })
            continue
        approved_tools.append({
            "tool": tool_name,
            "status": "would_run",
            "safety_class": policy.get("safety_class", "READ_ONLY"),
            "args_preview": policy.get("args_schema", {}),
        })
    return {
        "task_tools_detected": tools,
        "approved_tools": approved_tools,
        "blocked_tools": blocked_tools,
    }


def _invoke_tool(tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    from qbot_tool_registry import TOOLS
    func = TOOLS.get(tool_name)
    if func is None:
        return {"tool": tool_name, "status": "error", "error": "tool not found"}
    try:
        result = func(args or {})
        if isinstance(result, dict):
            return result
        return {"tool": tool_name, "status": "error", "error": "unexpected tool payload"}
    except Exception as exc:
        return {"tool": tool_name, "status": "error", "error": str(exc)}


def _classify_tool_result(result: dict[str, Any]) -> str:
    status = str(result.get("status", "")).upper()
    if status in {"PASS", "OK", "READY"}:
        return "PASS"
    if status in {"FAIL", "ERROR"}:
        return "FAIL"
    if status in {"BLOCKED", "APPROVAL_REQUIRED", "SECURITY_BLOCKED"}:
        return status
    if status in {"WARN", "PAUSED", "DONE"}:
        return "WARN" if status == "WARN" else status
    if result.get("error"):
        return "FAIL"
    return "PASS"


def _task_lookup(task_id: str | None = None, block: str | None = None) -> dict[str, Any] | None:
    tasks = _flatten_tasks(block)
    if task_id:
        for task in tasks:
            if task["task_id"] == task_id:
                return task
        return None
    state = _load_state()
    completed = set(state.get("tasks_completed", []))
    blocked = set(state.get("tasks_blocked", []))
    for task in tasks:
        if task["task_id"] not in completed and task["task_id"] not in blocked:
            return task
    return None


def _current_block_summary(block: str) -> tuple[int, int]:
    tasks = _flatten_tasks(block)
    completed = set(_load_state().get("tasks_completed", []))
    return len([t for t in tasks if t["task_id"] in completed]), len(tasks)


def _compute_percent(current: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(100, int(round(current / total * 100))))


def _update_state_progress(
    *,
    runner_status: str | None = None,
    current_block: str | None = None,
    current_task_id: str | None = None,
    last_task_id: str | None = None,
    last_status: str | None = None,
    last_commit: str | None = None,
    last_error: str | None = None,
    started_at: str | None = None,
    task_progress_percent: int | None = None,
    block_progress_percent: int | None = None,
    current_step: int | None = None,
    total_steps: int | None = None,
    step_name: str | None = None,
    last_task_summary: str | None = None,
    last_task_tools: list[str] | None = None,
    preview_tasks_completed: list[str] | None = None,
    preview_tasks_blocked: list[str] | None = None,
    tasks_completed: list[str] | None = None,
    tasks_blocked: list[str] | None = None,
    preview_block: str | None = None,
    preview_total_tasks_in_block: int | None = None,
    preview_current_task_id: str | None = None,
    preview_task_progress_percent: int | None = None,
    preview_block_progress_percent: int | None = None,
    preview_current_step: int | None = None,
    preview_total_steps: int | None = None,
    preview_step_name: str | None = None,
    dry_run_persist: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    state = _load_state()
    # Preview fields always update
    updates: dict[str, Any] = {
        "preview_tasks_completed": preview_tasks_completed,
        "preview_tasks_blocked": preview_tasks_blocked,
        "preview_block": preview_block,
        "preview_total_tasks_in_block": preview_total_tasks_in_block,
        "preview_current_task_id": preview_current_task_id,
        "preview_task_progress_percent": preview_task_progress_percent,
        "preview_block_progress_percent": preview_block_progress_percent,
        "preview_current_step": preview_current_step,
        "preview_total_steps": preview_total_steps,
        "preview_step_name": preview_step_name,
    }
    # Real fields only for non-dry-run or explicit persist
    if not dry_run or dry_run_persist:
        real_updates = {
            "runner_status": runner_status,
            "current_block": current_block,
            "current_task_id": current_task_id,
            "last_task_id": last_task_id,
            "last_status": last_status,
            "last_commit": last_commit,
            "last_error": last_error,
            "started_at": started_at,
            "task_progress_percent": task_progress_percent,
            "block_progress_percent": block_progress_percent,
            "current_step": current_step,
            "total_steps": total_steps,
            "step_name": step_name,
            "last_task_summary": last_task_summary,
            "last_task_tools": last_task_tools,
            "tasks_completed": tasks_completed,
            "tasks_blocked": tasks_blocked,
        }
        updates.update(real_updates)
    for key, value in updates.items():
        if value is not None:
            state[key] = value
    _save_state(state)
    return state


def _append_telegram_notification(payload: dict[str, Any]) -> None:
    state = _load_state()
    notifications = list(state.get("telegram_notifications", []))
    notifications.append(payload)
    if len(notifications) > 100:
        notifications = notifications[-100:]
    state["telegram_notifications"] = notifications
    _save_state(state)


def _notify_telegram_message(text: str, allow_no_notify: bool = False) -> dict[str, Any]:
    allowed_chat = None
    allowed_raw = (os.getenv("TELEGRAM_ALLOWED_CHAT_IDS") or "").split(",")
    for candidate in allowed_raw:
        candidate = candidate.strip()
        if candidate:
            allowed_chat = candidate
            break
    if not allowed_chat:
        result = {"ok": False, "error": "no allowed chat configured"}
        if allow_no_notify:
            return result
        return result
    try:
        from qbot_telegram_client import is_allowed_chat, send_message
        if not is_allowed_chat(int(allowed_chat)):
            return {"ok": False, "error": f"chat_id {allowed_chat} not allowed"}
        return send_message(allowed_chat, text)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _build_notification_text(
    *,
    result_status: str,
    block_id: str,
    block_title: str,
    task_id: str,
    task_description: str,
    commit: str | None = None,
    next_task: dict[str, Any] | None = None,
    dry_run: bool = False,
    reason: str | None = None,
    progress: int = 0,
) -> str:
    if dry_run:
        lines = [f"Qbot dry-run {result_status}"]
    elif result_status == "PASS":
        lines = ["Qbot task PASS"]
    else:
        lines = [f"Qbot runner {result_status}"]
    lines.append(f"Block: {block_id}")
    lines.append(f"Task: {task_id}")
    if reason:
        lines.append(f"Reason: {reason}")
    lines.append(f"Progress: {progress}%")
    if commit:
        lines.append(f"Commit: {commit}")
    if next_task:
        lines.append(f"Next: {next_task['task_id']}")
    return "\n".join(lines)


def _record_inbox(
    *,
    status: str,
    block_id: str,
    task_id: str,
    summary: str,
    commit: str | None,
    next_action: str,
    requires_user_decision: bool,
    dry_run: bool,
    task_progress_percent: int,
    block_progress_percent: int,
    current_step: int,
    total_steps: int,
    step_name: str,
) -> dict[str, Any]:
    return _tool_qbot_assistant_inbox_add({
        "source": "roadmap_runner",
        "block": block_id,
        "task_id": task_id,
        "status": status,
        "summary": summary,
        "commit": commit or "",
        "next_action": next_action,
        "requires_user_decision": requires_user_decision,
        "dry_run": dry_run,
        "task_progress_percent": task_progress_percent,
        "block_progress_percent": block_progress_percent,
        "current_step": current_step,
        "total_steps": total_steps,
        "step_name": step_name,
    })


def _roadmap_task_state(task: dict[str, Any]) -> str:
    state = _load_state()
    if task["task_id"] in state.get("tasks_blocked", []):
        return "blocked"
    if task["task_id"] in state.get("tasks_completed", []):
        return "completed"
    return "pending"


def _list_tasks(block: str | None = None) -> list[dict[str, Any]]:
    tasks = _flatten_tasks(block)
    output = []
    for task in tasks:
        item = copy.deepcopy(task)
        item["status"] = _roadmap_task_state(task)
        item["can_auto_execute_now"] = bool(
            item["autonomous"] and not item["approval"] and item["safety_class"] in ALLOWED_TASK_SAFETY
        )
        output.append(item)
    return output


def _next_task(block: str | None = None) -> dict[str, Any] | None:
    tasks = _list_tasks(block)
    for task in tasks:
        if task["status"] == "pending":
            return task
    return None


def _next_task_in_session(
    *,
    block: str | None = None,
    completed: set[str] | None = None,
    blocked: set[str] | None = None,
) -> dict[str, Any] | None:
    completed = completed or set()
    blocked = blocked or set()
    for task in _flatten_tasks(block):
        if task["task_id"] in completed or task["task_id"] in blocked:
            continue
        return task
    return None


def _status_payload() -> dict[str, Any]:
    state = _load_state()
    current_block = state.get("current_block") or state.get("preview_block")
    current_task_id = state.get("current_task_id") or state.get("preview_current_task_id")
    block_progress = state.get("block_progress_percent")
    task_progress = state.get("task_progress_percent")
    current_step = state.get("current_step")
    total_steps = state.get("total_steps") or len(STANDARD_TASK_STEPS)
    step_name = state.get("step_name")
    if not current_block and state.get("preview_block"):
        current_block = state.get("preview_block")
    if not current_task_id and state.get("preview_current_task_id"):
        current_task_id = state.get("preview_current_task_id")
    inbox = _tool_qbot_assistant_inbox_status()
    next_task = _next_task(current_block if current_block else None)
    return {
        "runner_status": state.get("runner_status", "IDLE"),
        "current_block": current_block,
        "current_task_id": current_task_id,
        "task_progress_percent": int(task_progress or state.get("preview_task_progress_percent", 0) or 0),
        "block_progress_percent": int(block_progress or state.get("preview_block_progress_percent", 0) or 0),
        "current_step": int(current_step or state.get("preview_current_step", 0) or 0),
        "total_steps": int(total_steps or state.get("preview_total_steps", len(STANDARD_TASK_STEPS))),
        "step_name": step_name or state.get("preview_step_name"),
        "updated_at": state.get("updated_at"),
        "last_task_id": state.get("last_task_id"),
        "last_status": state.get("last_status"),
        "last_commit": state.get("last_commit"),
        "last_error": state.get("last_error"),
        "tasks_completed": list(state.get("tasks_completed", [])),
        "tasks_blocked": list(state.get("tasks_blocked", [])),
        "telegram_notifications": list(state.get("telegram_notifications", [])),
        "assistant_inbox": {
            "total_messages": inbox.get("total_messages", 0),
            "unread_messages": inbox.get("unread_messages", 0),
            "latest_message": inbox.get("latest_message"),
        },
        "next_task": next_task,
    }


def _tool_qbot_roadmap_runner_status(_args: dict | None = None) -> dict[str, Any]:
    payload = _status_payload()
    return {
        "tool": "qbot_roadmap_runner_status",
        "status": "OK" if payload["runner_status"] in {"IDLE", "PAUSED", "DONE"} else "WARN",
        **payload,
    }


def _tool_qbot_roadmap_runner_list_tasks(args: dict | None = None) -> dict[str, Any]:
    block = str((args or {}).get("block", "") or "").strip()
    tasks = _list_tasks(block or None)
    blocks = {}
    for task in tasks:
        blocks.setdefault(task["block_id"], 0)
        blocks[task["block_id"]] += 1
    return {
        "tool": "qbot_roadmap_runner_list_tasks",
        "status": "OK",
        "block_filter": block or None,
        "count": len(tasks),
        "blocks": blocks,
        "tasks": tasks,
    }


def _tool_qbot_roadmap_runner_next_task(args: dict | None = None) -> dict[str, Any]:
    block = str((args or {}).get("block", "") or "").strip()
    task_id = str((args or {}).get("task_id", "") or "").strip()
    task = _task_lookup(task_id or None, block or None)
    if task is None:
        return {
            "tool": "qbot_roadmap_runner_next_task",
            "status": "DONE",
            "block": block or None,
            "task": None,
            "reason": "no pending task found",
        }
    return {
        "tool": "qbot_roadmap_runner_next_task",
        "status": "OK",
        "block": block or task["block_id"],
        "task": task,
        "reason": "next pending task in roadmap order",
    }


def _hash_reason(reason: str | None) -> str:
    if not reason:
        return "none"
    return str(hash(reason[:200]))

def _should_send_telegram_notification(
    *,
    block: str,
    task_id: str,
    status: str,
    reason: str | None = None,
    dry_run: bool = False,
    notify_requested: bool = False,
) -> tuple[bool, str]:
    """Returns (send, key). Deduplicates by block+task+status+reason_hash+dry_run."""
    if status.upper() in ("RUNNING", "OK"):
        return False, "progress"
    if dry_run and not notify_requested:
        return False, "dry_run_no_notify"
    state = _load_state()
    key = f"{block}:{task_id}:{status.upper()}:{_hash_reason(reason)}:{dry_run}"
    last_key = state.get("last_telegram_notification_key")
    if last_key == key:
        return False, "duplicate"
    state["last_telegram_notification_key"] = key
    _save_state(state)
    return True, key


def _task_progress_result(
    task: dict[str, Any],
    *,
    status: str,
    dry_run: bool,
    current_step: int,
    total_steps: int,
    step_name: str,
    task_progress_percent: int,
    block_progress_percent: int,
    commit: str | None = None,
    last_error: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    block_id = task["block_id"]
    block_title = task["block_title"]
    next_task = _next_task(block_id)
    payload = {
        "tool": "qbot_roadmap_runner_execute_next",
        "status": status,
        "dry_run": dry_run,
        "block": block_id,
        "block_title": block_title,
        "task": task,
        "current_step": current_step,
        "total_steps": total_steps,
        "step_name": step_name,
        "task_progress_percent": task_progress_percent,
        "block_progress_percent": block_progress_percent,
        "inbox_entry": None,
        "next_task": next_task,
        "progress_log": [],
        "notifications": [],
        "last_error": last_error,
        "reason": reason,
    }
    return payload


def _task_session(
    task: dict[str, Any],
    *,
    dry_run: bool,
    allow_no_notify: bool = False,
    notify_requested: bool = False,
    max_steps: int | None = None,
    session_completed_before: int = 0,
    session_completed_ids: list[str] | None = None,
    session_blocked_ids: list[str] | None = None,
) -> dict[str, Any]:
    state = _load_state()
    block_id = task["block_id"]
    block_title = task["block_title"]
    task_id = task["task_id"]
    steps = _step_plan_for_task(task)
    total_steps = len(steps) if steps else len(STANDARD_TASK_STEPS)
    if max_steps is not None:
        total_steps = min(total_steps, max_steps)
    log_lines: list[str] = []
    progress_events: list[dict[str, Any]] = []
    selected_tools = _task_execution_preview(task)
    task_tests = selected_tools["approved_tools"]
    blocked_tools = selected_tools["blocked_tools"]
    task_progress_percent = 0
    block_completed = len(state.get("tasks_completed", []))
    block_total = len(_flatten_tasks(block_id))
    preview_completed_ids = list(session_completed_ids or state.get("preview_tasks_completed", []))
    preview_blocked_ids = list(session_blocked_ids or state.get("preview_tasks_blocked", []))
    started_at = state.get("started_at") or _utc_now()
    final_status = "PASS"
    reason = None
    commit = None
    last_error = None
    current_step = 0
    step_name = ""

    def _update(step_idx: int, name: str, percent: int) -> None:
        nonlocal current_step, step_name, task_progress_percent
        current_step = step_idx
        step_name = name
        task_progress_percent = percent
        _emit_progress(log_lines, task_id, step_idx, total_steps, name, percent)
        progress_events.append({
            "step": step_idx,
            "step_name": name,
            "progress_percent": percent,
            "updated_at": _utc_now(),
        })
        _update_state_progress(
            runner_status="RUNNING",
            current_block=block_id,
            current_task_id=task_id,
            started_at=started_at,
            task_progress_percent=task_progress_percent,
            block_progress_percent=_compute_percent(session_completed_before, block_total or 1),
            current_step=current_step,
            total_steps=total_steps,
            step_name=step_name,
            preview_block=block_id,
            preview_total_tasks_in_block=block_total,
            preview_current_task_id=task_id,
            preview_task_progress_percent=task_progress_percent,
            preview_block_progress_percent=_compute_percent(session_completed_before, block_total or 1),
            preview_current_step=current_step,
            preview_total_steps=total_steps,
            preview_step_name=step_name,
            preview_tasks_completed=preview_completed_ids,
            preview_tasks_blocked=preview_blocked_ids,
            dry_run=dry_run,
        )

    # 1. preflight
    _update(1, steps[0][0] if steps else "preflight", steps[0][1] if steps else 10)
    baseline = _baseline_checks()
    baseline_ok = True
    if not baseline["py_compile"]["ok"]:
        baseline_ok = False
        final_status = "FAIL"
        last_error = "py_compile failed"
        reason = "py_compile failed"
    elif not baseline["local_health"].get("ok"):
        baseline_ok = False
        final_status = "BLOCKED"
        last_error = "local health check failed"
        reason = "qbot-api local health failed"
    elif baseline["public_q"].get("status_code") != 404:
        baseline_ok = False
        final_status = "BLOCKED"
        last_error = f"public /q returned {baseline['public_q'].get('status_code')}"
        reason = "public /q is not blocked"
    elif baseline["public_health"].get("status_code") != 404:
        baseline_ok = False
        final_status = "BLOCKED"
        last_error = f"public /health returned {baseline['public_health'].get('status_code')}"
        reason = "public /health is not blocked"
    elif not baseline["git_status"].get("clean", False) and (dry_run or not task.get("eligible_for_auto")):
        baseline_ok = False
        final_status = "BLOCKED"
        last_error = "repository dirty before runner start"
        reason = "repository is dirty"
    elif baseline["secret_hits"].get("blocking_hits_count", baseline["secret_hits"].get("count", 0)) > 0 or baseline["secret_hits"].get("env_local_tracked"):
        baseline_ok = False
        final_status = "SECURITY_BLOCKED"
        last_error = "secret-like pattern detected"
        reason = "possible secret in repo/output"

    if not baseline_ok:
        _update_state_progress(
            runner_status="BLOCKED" if final_status != "FAIL" else "PAUSED",
            current_block=block_id,
            current_task_id=task_id,
            last_task_id=task_id,
            last_status=final_status,
            last_error=last_error,
            started_at=started_at,
            task_progress_percent=task_progress_percent,
            block_progress_percent=_compute_percent(session_completed_before, block_total or 1),
            current_step=current_step,
            total_steps=total_steps,
            step_name=step_name,
            last_task_summary=f"{task_id} {final_status} during baseline",
            preview_block=block_id,
            preview_total_tasks_in_block=block_total,
            preview_current_task_id=task_id,
            preview_task_progress_percent=task_progress_percent,
            preview_block_progress_percent=_compute_percent(session_completed_before, block_total or 1),
            preview_current_step=current_step,
            preview_total_steps=total_steps,
            preview_step_name=step_name,
            preview_tasks_completed=preview_completed_ids,
            preview_tasks_blocked=preview_blocked_ids,
            dry_run=dry_run,
        )
        message = _build_notification_text(
            result_status=final_status,
            block_id=block_id,
            block_title=block_title,
            task_id=task_id,
            task_description=task["description"],
            commit=commit,
            next_task=_next_task(block_id),
            dry_run=dry_run,
            reason=reason,
            progress=task_progress_percent,
        )
        should_send, notif_key = _should_send_telegram_notification(
            block=block_id, task_id=task_id, status=final_status,
            reason=reason, dry_run=dry_run, notify_requested=notify_requested,
        )
        notif = {"ok": False, "skipped": f"notification suppressed ({notif_key})"}
        if should_send:
            notif = _notify_telegram_message(message, allow_no_notify=allow_no_notify)
        _append_telegram_notification({
            "created_at": _utc_now(),
            "task_id": task_id,
            "block": block_id,
            "status": final_status,
            "dry_run": dry_run,
            "message": message[:1000],
            "ok": bool(notif.get("ok")),
            "error": _sanitize_text(notif.get("error"), 200),
            "notif_key": notif_key,
        })
        _record_inbox(
            status=final_status,
            block_id=block_id,
            task_id=task_id,
            summary=f"{task_id} {final_status} — {reason or 'baseline failed'}",
            commit=commit,
            next_action="Fix baseline blockers before retrying",
            requires_user_decision=True,
            dry_run=dry_run,
            task_progress_percent=task_progress_percent,
            block_progress_percent=_compute_percent(session_completed_before, block_total or 1),
            current_step=current_step,
            total_steps=total_steps,
            step_name=step_name,
        )
        if not notif.get("ok") and not allow_no_notify:
            final_status = "PAUSED"
        return _task_progress_result(
            task,
            status=final_status,
            dry_run=dry_run,
            current_step=current_step,
            total_steps=total_steps,
            step_name=step_name,
            task_progress_percent=task_progress_percent,
            block_progress_percent=_compute_percent(session_completed_before, block_total or 1),
            commit=commit,
            last_error=last_error,
            reason=reason,
        ) | {
            "baseline": baseline,
            "progress_log": log_lines,
            "progress_events": progress_events,
            "notification": notif,
        }

    # 2. execute / preview
    _update(2, steps[1][0] if len(steps) > 1 else "applying changes", steps[1][1] if len(steps) > 1 else 25)
    if dry_run:
        reason = reason or "dry-run preview only"
    elif not task.get("eligible_for_auto"):
        final_status = "APPROVAL_REQUIRED"
        reason = "task is not eligible for auto-execution"
        last_error = "task requires approval or has unsafe safety_class"
    else:
        reason = reason or "autonomous task — executing non-dry-run"

    # 3. py_compile
    _update(3, steps[2][0] if len(steps) > 2 else "running py_compile", steps[2][1] if len(steps) > 2 else 45)
    if baseline_ok:
        compile_result = baseline["py_compile"]
    else:
        compile_result = baseline["py_compile"]
    if not compile_result.get("ok"):
        final_status = "FAIL"
        last_error = "py_compile failed"

    # 4. restart/health
    _update(4, steps[3][0] if len(steps) > 3 else "restarting qbot-api", steps[3][1] if len(steps) > 3 else 65)
    health_result = baseline["local_health"]
    if not health_result.get("ok"):
        final_status = "BLOCKED"
        last_error = "local health failed"

    # 5. task self-check
    _update(5, steps[4][0] if len(steps) > 4 else "running self-check", steps[4][1] if len(steps) > 4 else 80)
    tool_results: list[dict[str, Any]] = []
    for tool_info in task_tests:
        tool_name = tool_info["tool"]
        tool_result = _invoke_tool(tool_name, copy.deepcopy(tool_info.get("args_preview", {})))
        tool_results.append({"tool": tool_name, "result": tool_result})
        normalized = _classify_tool_result(tool_result)
        if normalized == "FAIL":
            final_status = "FAIL"
            last_error = f"{tool_name} returned error"
            break
        if normalized in {"WARN", "BLOCKED", "APPROVAL_REQUIRED", "SECURITY_BLOCKED"}:
            final_status = normalized
            last_error = f"{tool_name} returned {normalized.lower()}"
            break
    if blocked_tools and final_status == "PASS":
        final_status = "APPROVAL_REQUIRED"
        reason = "some task tools require approval or are not auto-executable"

    # 6. public endpoint check
    _update(6, steps[5][0] if len(steps) > 5 else "public endpoint check", steps[5][1] if len(steps) > 5 else 88)
    public_q = baseline["public_q"]
    public_health = baseline["public_health"]
    if public_q.get("status_code") != 404 or public_health.get("status_code") != 404:
        final_status = "BLOCKED"
        last_error = "public endpoint hardening failed"

    # 7. security grep
    _update(7, steps[6][0] if len(steps) > 6 else "security grep", steps[6][1] if len(steps) > 6 else 95)
    secret_hits = baseline["secret_hits"]
    if secret_hits.get("blocking_hits_count", secret_hits.get("count", 0)) > 0:
        final_status = "SECURITY_BLOCKED"
        last_error = "secret-like pattern detected"

    # 8. git diff/status
    _update(8, steps[7][0] if len(steps) > 7 else "git diff/status", steps[7][1] if len(steps) > 7 else 98)
    git_status = baseline["git_status"]
    if not git_status.get("clean", False) and (dry_run or not task.get("eligible_for_auto")):
        final_status = "BLOCKED"
        last_error = "repository dirty"

    # 9. commit
    _update(9, steps[8][0] if len(steps) > 8 else "commit", steps[8][1] if len(steps) > 8 else 99)
    commit = None
    if dry_run:
        reason = reason or "dry-run completed"
    elif final_status != "PASS":
        reason = reason or f"task {final_status.lower()} — not committing"
    else:
        # Non-dry-run PASS → auto-commit
        files_raw = task.get("files_likely_touched", "")
        files_to_add = [f.strip().strip("`") for f in files_raw.replace(",", " ").split() if f.strip() and not f.strip().startswith("docs/")]

        if not files_to_add:
            reason = reason or "PASS — no code files to commit"
        else:
            # Record HEAD before commit attempt
            head_before = None
            try:
                head_proc = _git(["git", "rev-parse", "HEAD"], timeout=5)
                if head_proc.returncode == 0:
                    head_before = head_proc.stdout.strip()
            except Exception:
                pass

            try:
                add_proc = _git(["git", "add"] + files_to_add, timeout=15)
                if add_proc.returncode != 0:
                    final_status = "BLOCKED"
                    last_error = f"git add failed: {add_proc.stderr.strip()[:200]}"
                    reason = f"git add error on {files_to_add}"
                else:
                    commit_msg = f"{task.get('task_id', '')} {task.get('description', '')[:80]}".strip()
                    commit_proc = _git(["git", "commit", "-m", commit_msg], timeout=15)

                    # Verify if commit was actually created (may succeed despite non-zero exit)
                    head_after = None
                    try:
                        head2 = _git(["git", "rev-parse", "HEAD"], timeout=5)
                        if head2.returncode == 0:
                            head_after = head2.stdout.strip()
                    except Exception:
                        pass

                    if head_after and head_after != head_before:
                        # Commit was created despite non-zero exit from git commit
                        commit = head_after[:12]
                        reason = reason or f"committed {commit}"
                        if commit_proc.returncode != 0:
                            reason = f"PASS — verified commit {commit} (git commit returned non-zero but HEAD moved)"
                    elif commit_proc.returncode != 0:
                        stderr_lower = (commit_proc.stderr or "").lower()
                        if "nothing to commit" in stderr_lower or "nothing added to commit" in stderr_lower:
                            reason = reason or "PASS — no changes to commit"
                        else:
                            final_status = "BLOCKED"
                            last_error = f"git commit failed: {commit_proc.stderr.strip()[:200]}"
                            reason = "git commit error"
                    else:
                        commit = commit_proc.stdout.strip().split()[-1][:40] if commit_proc.stdout.strip() else "ok"
                        reason = reason or f"committed {commit}"
            except Exception as exc:
                final_status = "BLOCKED"
                last_error = f"git operation failed: {str(exc)[:200]}"
                reason = "git operation exception"

    # 10. notify/inbox
    _update(10, steps[9][0] if len(steps) > 9 else "PASS / BLOCKED", steps[9][1] if len(steps) > 9 else 100)
    block_progress_percent = _compute_percent(session_completed_before + (1 if final_status == "PASS" else 0), block_total or 1)
    if final_status == "PASS":
        preview_completed_ids.append(task_id)
    elif final_status in {"BLOCKED", "FAIL", "WARN", "APPROVAL_REQUIRED", "SECURITY_BLOCKED"}:
        preview_blocked_ids.append(task_id)

    _update_state_progress(
        runner_status="IDLE" if final_status == "PASS" else "PAUSED" if final_status in {"WARN", "APPROVAL_REQUIRED"} else "BLOCKED" if final_status in {"BLOCKED", "SECURITY_BLOCKED"} else "PAUSED",
        current_block=block_id,
        current_task_id=task_id,
        last_task_id=task_id,
        last_status=final_status,
        last_commit=commit,
        last_error=last_error,
        started_at=started_at,
        task_progress_percent=task_progress_percent,
        block_progress_percent=block_progress_percent,
        current_step=current_step,
        total_steps=total_steps,
        step_name=step_name,
        last_task_summary=f"{task_id} {final_status}",
        last_task_tools=[t["tool"] for t in tool_results],
        preview_block=block_id,
        preview_total_tasks_in_block=block_total,
        preview_current_task_id=task_id,
        preview_task_progress_percent=task_progress_percent,
        preview_block_progress_percent=block_progress_percent,
        preview_current_step=current_step,
        preview_total_steps=total_steps,
        preview_step_name=step_name,
        preview_tasks_completed=preview_completed_ids,
        preview_tasks_blocked=preview_blocked_ids,
    )
    message = _build_notification_text(
        result_status=final_status,
        block_id=block_id,
        block_title=block_title,
        task_id=task_id,
        task_description=task["description"],
        commit=commit,
        next_task=_next_task(block_id),
        dry_run=dry_run,
        reason=reason if final_status != "PASS" else None,
        progress=task_progress_percent,
    )
    should_send, notif_key = _should_send_telegram_notification(
        block=block_id, task_id=task_id, status=final_status,
        reason=reason if final_status != "PASS" else None,
        dry_run=dry_run, notify_requested=notify_requested,
    )
    notif = {"ok": False, "skipped": f"notification suppressed ({notif_key})"}
    if should_send:
        notif = _notify_telegram_message(message, allow_no_notify=allow_no_notify)
    _append_telegram_notification({
        "created_at": _utc_now(),
        "task_id": task_id,
        "block": block_id,
        "status": final_status,
        "dry_run": dry_run,
        "message": message[:1000],
        "ok": bool(notif.get("ok")),
        "error": _sanitize_text(notif.get("error"), 200),
        "notif_key": notif_key,
    })
    if not notif.get("ok") and not allow_no_notify and "skipped" not in notif:
        final_status = "PAUSED"
        last_error = f"telegram notify failed: {notif.get('error')}"
        _update_state_progress(
            runner_status="PAUSED",
            current_block=block_id,
            current_task_id=task_id,
            last_task_id=task_id,
            last_status=final_status,
            last_error=last_error,
            started_at=started_at,
            task_progress_percent=task_progress_percent,
            block_progress_percent=block_progress_percent,
            current_step=current_step,
            total_steps=total_steps,
            step_name=step_name,
            last_task_summary=f"{task_id} {final_status}",
            preview_block=block_id,
            preview_total_tasks_in_block=block_total,
            preview_current_task_id=task_id,
            preview_task_progress_percent=task_progress_percent,
            preview_block_progress_percent=block_progress_percent,
            preview_current_step=current_step,
            preview_total_steps=total_steps,
            preview_step_name=step_name,
            preview_tasks_completed=preview_completed_ids,
            preview_tasks_blocked=preview_blocked_ids,
            dry_run=dry_run,
        )
    _record_inbox(
        status=final_status,
        block_id=block_id,
        task_id=task_id,
        summary=f"{task_id} {final_status} ({'dry-run' if dry_run else 'real'})",
        commit=commit,
        next_action=(
            f"Proceed to {(_next_task(block_id) or task)['task_id']} " +
            f"{(_next_task(block_id) or task)['description'][:120]}"
        ) if final_status == "PASS" and _next_task(block_id) else "Review runner status and decide whether to continue",
        requires_user_decision=final_status != "PASS",
        dry_run=dry_run,
        task_progress_percent=task_progress_percent,
        block_progress_percent=block_progress_percent,
        current_step=current_step,
        total_steps=total_steps,
        step_name=step_name,
    )
    result = _task_progress_result(
        task,
        status=final_status,
        dry_run=dry_run,
        current_step=current_step,
        total_steps=total_steps,
        step_name=step_name,
        task_progress_percent=task_progress_percent,
        block_progress_percent=block_progress_percent,
        commit=commit,
        last_error=last_error,
        reason=reason,
    )
    result["baseline"] = baseline
    result["progress_log"] = log_lines
    result["progress_events"] = progress_events
    result["notification"] = notif
    result["task_specific_tool_results"] = tool_results
    result["task_specific_preview"] = selected_tools
    result["block_progress_percent"] = block_progress_percent
    result["completed_tasks"] = preview_completed_ids
    result["blocked_tasks"] = preview_blocked_ids
    result["total_tasks_in_block"] = block_total
    result["current_task_id"] = task_id
    result["current_step"] = current_step
    result["total_steps"] = total_steps
    result["step_name"] = step_name
    result["task_progress_percent"] = task_progress_percent
    return result


def _tool_qbot_roadmap_runner_execute_next(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    dry_run = _normalize_bool(args.get("dry_run", True))
    allow_no_notify = _normalize_bool(args.get("allow_no_notify", False))
    block = str(args.get("block", "") or "").strip() or None
    task_id = str(args.get("task_id", "") or "").strip() or None
    task = _task_lookup(task_id, block)
    if task is None:
        _update_state_progress(
            runner_status="DONE",
            current_block=block,
            current_task_id=None,
            last_status="DONE",
            last_error=None,
            step_name="PASS / BLOCKED",
            current_step=len(STANDARD_TASK_STEPS),
            total_steps=len(STANDARD_TASK_STEPS),
            task_progress_percent=100,
            block_progress_percent=100,
            preview_block=block,
            preview_total_tasks_in_block=0,
            preview_current_task_id=None,
            preview_task_progress_percent=100,
            preview_block_progress_percent=100,
            preview_current_step=len(STANDARD_TASK_STEPS),
            preview_total_steps=len(STANDARD_TASK_STEPS),
            preview_step_name="PASS / BLOCKED",
            preview_tasks_completed=[],
            preview_tasks_blocked=[],
        )
        return {
            "tool": "qbot_roadmap_runner_execute_next",
            "status": "DONE",
            "dry_run": dry_run,
            "block": block,
            "task": None,
            "reason": "no pending task found",
            "current_step": len(STANDARD_TASK_STEPS),
            "total_steps": len(STANDARD_TASK_STEPS),
            "step_name": "PASS / BLOCKED",
            "task_progress_percent": 100,
            "block_progress_percent": 100,
            "progress_log": [],
            "progress_events": [],
        }
    # If non-dry-run is requested we keep the path explicit and safe.
    if not dry_run:
        _update_state_progress(
            runner_status="PAUSED",
            current_block=task["block_id"],
            current_task_id=task["task_id"],
            last_task_id=task["task_id"],
            last_status="APPROVAL_REQUIRED",
            last_error="real execution is not yet automated in this runner",
            step_name="preflight",
            current_step=1,
            total_steps=len(STANDARD_TASK_STEPS),
            task_progress_percent=0,
            block_progress_percent=0,
            preview_block=task["block_id"],
            preview_total_tasks_in_block=len(_flatten_tasks(task["block_id"])),
            preview_current_task_id=task["task_id"],
            preview_task_progress_percent=0,
            preview_block_progress_percent=0,
            preview_current_step=1,
            preview_total_steps=len(STANDARD_TASK_STEPS),
            preview_step_name="preflight",
            preview_tasks_completed=list(_load_state().get("tasks_completed", [])),
            preview_tasks_blocked=list(_load_state().get("tasks_blocked", [])),
        )
        return {
            "tool": "qbot_roadmap_runner_execute_next",
            "status": "APPROVAL_REQUIRED",
            "dry_run": False,
            "block": task["block_id"],
            "task": task,
            "reason": "real execution is not yet automated in this runner",
            "current_step": 1,
            "total_steps": len(STANDARD_TASK_STEPS),
            "step_name": "preflight",
            "task_progress_percent": 0,
            "block_progress_percent": 0,
        }
    result = _task_session(task, dry_run=True, allow_no_notify=allow_no_notify, notify_requested=False)
    return result


def _tool_qbot_roadmap_runner_run_until_blocked(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    block = str(args.get("block", "") or "").strip() or None
    dry_run = _normalize_bool(args.get("dry_run", True))
    allow_no_notify = _normalize_bool(args.get("allow_no_notify", False))
    notify_requested = _normalize_bool(args.get("notify", False))
    max_tasks_raw = args.get("max_tasks", 5)
    max_minutes_raw = args.get("max_minutes", 60)
    try:
        max_tasks = max(1, int(max_tasks_raw))
    except (TypeError, ValueError):
        max_tasks = 5
    try:
        max_minutes = max(1, int(max_minutes_raw))
    except (TypeError, ValueError):
        max_minutes = 60

    started = datetime.now(timezone.utc)
    session_completed: list[str] = []
    session_blocked: list[str] = []
    task_results: list[dict[str, Any]] = []
    progress_log: list[str] = []
    status = "PAUSED"
    reason = "max_tasks reached"
    total_tasks_in_block = len(_flatten_tasks(block)) if block else len(_flatten_tasks())
    current_task = _next_task_in_session(block=block, completed=set(), blocked=set())

    while current_task and len(session_completed) < max_tasks:
        elapsed_minutes = (datetime.now(timezone.utc) - started).total_seconds() / 60
        if elapsed_minutes > max_minutes:
            status = "PAUSED"
            reason = "max_minutes reached"
            break

        result = _task_session(
            current_task,
            dry_run=dry_run,
            allow_no_notify=allow_no_notify,
            notify_requested=notify_requested,
            session_completed_before=len(session_completed),
            session_completed_ids=list(session_completed),
            session_blocked_ids=list(session_blocked),
        )
        task_results.append(result)
        progress_log.extend(result.get("progress_log", []))

        task_status = str(result.get("status", "")).upper()
        if task_status == "PASS":
            session_completed.append(current_task["task_id"])
            state = _load_state()
            real_completed = list(state.get("tasks_completed", []))
            real_blocked = list(state.get("tasks_blocked", []))
            if not dry_run and current_task["task_id"] not in real_completed:
                real_completed.append(current_task["task_id"])
            preview_completed = list(session_completed)
            _update_state_progress(
                runner_status="RUNNING",
                current_block=current_task["block_id"],
                current_task_id=current_task["task_id"],
                last_task_id=current_task["task_id"],
                last_status="PASS",
                last_error=None,
                task_progress_percent=result.get("task_progress_percent", 100),
                block_progress_percent=_compute_percent(len(session_completed), total_tasks_in_block or 1),
                current_step=result.get("current_step", 10),
                total_steps=result.get("total_steps", len(STANDARD_TASK_STEPS)),
                step_name=result.get("step_name", "PASS / BLOCKED"),
                tasks_completed=real_completed if not dry_run else None,
                tasks_blocked=real_blocked if not dry_run else None,
                preview_block=current_task["block_id"],
                preview_total_tasks_in_block=total_tasks_in_block,
                preview_current_task_id=current_task["task_id"],
                preview_task_progress_percent=result.get("task_progress_percent", 100),
                preview_block_progress_percent=_compute_percent(len(session_completed), total_tasks_in_block or 1),
                preview_current_step=result.get("current_step", 10),
                preview_total_steps=result.get("total_steps", len(STANDARD_TASK_STEPS)),
                preview_step_name=result.get("step_name", "PASS / BLOCKED"),
                preview_tasks_completed=preview_completed,
                preview_tasks_blocked=list(session_blocked),
            )
            current_task = _next_task_in_session(
                block=block,
                completed=set(session_completed),
                blocked=set(session_blocked),
            )
            if not current_task:
                status = "DONE"
                reason = "block completed"
                break
            continue

        session_blocked.append(current_task["task_id"])
        if not dry_run:
            state = _load_state()
            real_blocked = list(state.get("tasks_blocked", []))
            if current_task["task_id"] not in real_blocked:
                real_blocked.append(current_task["task_id"])
            _update_state_progress(
                runner_status="BLOCKED",
                current_block=current_task["block_id"],
                current_task_id=current_task["task_id"],
                last_task_id=current_task["task_id"],
                last_status=task_status,
                last_error=result.get("last_error") or result.get("reason") or "task blocked",
                tasks_completed=list(state.get("tasks_completed", [])),
                tasks_blocked=real_blocked,
                preview_block=current_task["block_id"],
                preview_total_tasks_in_block=total_tasks_in_block,
                preview_current_task_id=current_task["task_id"],
                preview_task_progress_percent=result.get("task_progress_percent", 0),
                preview_block_progress_percent=_compute_percent(len(session_completed), total_tasks_in_block or 1),
                preview_current_step=result.get("current_step", 0),
                preview_total_steps=result.get("total_steps", len(STANDARD_TASK_STEPS)),
                preview_step_name=result.get("step_name", None),
                preview_tasks_completed=list(session_completed),
                preview_tasks_blocked=list(session_blocked),
            )
        status = task_status
        reason = result.get("reason") or result.get("last_error") or "task paused"
        break

    if not task_results and current_task is None:
        status = "DONE"
        reason = "no pending task found"

    if len(session_completed) >= max_tasks and status not in {"DONE", "BLOCKED", "FAIL", "WARN", "APPROVAL_REQUIRED", "SECURITY_BLOCKED"}:
        status = "PAUSED"
        reason = "max_tasks reached"

    final_block_progress = _compute_percent(len(session_completed), total_tasks_in_block or 1)
    final_current_task_id = task_results[-1]["task"]["task_id"] if task_results else None
    final_current_step = task_results[-1].get("current_step", len(STANDARD_TASK_STEPS)) if task_results else len(STANDARD_TASK_STEPS)
    final_total_steps = task_results[-1].get("total_steps", len(STANDARD_TASK_STEPS)) if task_results else len(STANDARD_TASK_STEPS)
    final_step_name = task_results[-1].get("step_name", "PASS / BLOCKED") if task_results else "PASS / BLOCKED"
    final_state = _load_state()
    final_real_completed = list(final_state.get("tasks_completed", []))
    final_real_blocked = list(final_state.get("tasks_blocked", []))
    if dry_run:
        preview_completed_final = list(session_completed)
        preview_blocked_final = list(session_blocked)
    else:
        preview_completed_final = final_real_completed or list(session_completed)
        preview_blocked_final = final_real_blocked or list(session_blocked)

    runner_status = "DONE" if status == "DONE" else "BLOCKED" if status in {"BLOCKED", "SECURITY_BLOCKED"} else "PAUSED"
    _update_state_progress(
        runner_status=runner_status,
        current_block=block or (task_results[-1]["block"] if task_results else None),
        current_task_id=final_current_task_id,
        last_task_id=final_current_task_id,
        last_status=status,
        last_error=None if status in {"PASS", "DONE"} else reason,
        task_progress_percent=task_results[-1].get("task_progress_percent", 0) if task_results else 0,
        block_progress_percent=final_block_progress,
        current_step=final_current_step,
        total_steps=final_total_steps,
        step_name=final_step_name,
        tasks_completed=final_real_completed if not dry_run else None,
        tasks_blocked=final_real_blocked if not dry_run else None,
        preview_block=block or (task_results[-1]["block"] if task_results else None),
        preview_total_tasks_in_block=total_tasks_in_block,
        preview_current_task_id=final_current_task_id,
        preview_task_progress_percent=task_results[-1].get("task_progress_percent", 0) if task_results else 0,
        preview_block_progress_percent=final_block_progress,
        preview_current_step=final_current_step,
        preview_total_steps=final_total_steps,
        preview_step_name=final_step_name,
        preview_tasks_completed=preview_completed_final,
        preview_tasks_blocked=preview_blocked_final,
    )

    if task_results and status in {"PAUSED", "BLOCKED", "FAIL", "WARN", "APPROVAL_REQUIRED", "SECURITY_BLOCKED", "DONE"}:
        final_label = status.upper()
        final_text = (
            f"Qbot runner {'DONE' if dry_run else final_label}\n"
            f"Block: {block or (task_results[-1].get('block') if task_results else '?')}\n"
            f"Task: {final_current_task_id}\n"
            f"Status: {final_label}\n"
            f"Reason: {reason}\n"
            f"Progress: {task_results[-1].get('task_progress_percent', 0) if task_results else 0}%\n"
            f"Block progress: {final_block_progress}%"
        )
        should_send, notif_key = _should_send_telegram_notification(
            block=block or (task_results[-1].get("block", "") if task_results else ""),
            task_id=final_current_task_id,
            status=status.upper(),
            reason=reason,
            dry_run=dry_run,
            notify_requested=notify_requested,
        )
        final_notif = {"ok": False, "skipped": f"notification suppressed ({notif_key})"}
        if should_send:
            final_notif = _notify_telegram_message(final_text, allow_no_notify=allow_no_notify)
        _append_telegram_notification({
            "created_at": _utc_now(),
            "task_id": final_current_task_id,
            "block": block or task_results[-1]["block"],
            "status": final_label,
            "dry_run": dry_run,
            "message": final_text[:1000],
            "ok": bool(final_notif.get("ok")),
            "error": _sanitize_text(final_notif.get("error"), 200),
        })

    return {
        "tool": "qbot_roadmap_runner_run_until_blocked",
        "status": status,
        "dry_run": dry_run,
        "block": block,
        "reason": reason,
        "max_tasks": max_tasks,
        "max_minutes": max_minutes,
        "completed_tasks": sorted(set(session_completed)),
        "blocked_tasks": sorted(set(session_blocked)),
        "total_tasks_in_block": total_tasks_in_block,
        "current_task_id": final_current_task_id,
        "block_progress_percent": final_block_progress,
        "task_results": task_results,
        "progress_log": progress_log,
        "updated_at": _utc_now(),
    }


def _tool_qbot_roadmap_runner_pause(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    reason = _sanitize_text(args.get("reason", "manual pause"), 200)
    state = _update_state_progress(
        runner_status="PAUSED",
        last_status="PAUSED",
        last_error=reason,
    )
    return {"tool": "qbot_roadmap_runner_pause", "status": "OK", "state": state, "reason": reason}


def _tool_qbot_roadmap_runner_reconcile_state(args: dict | None = None) -> dict[str, Any]:
    """Reconcile runner state with git log commits. Discovers completed tasks from commit subjects."""
    args = args or {}
    block = str(args.get("block", "") or "").strip() or None
    state = _load_state()

    # Get task IDs from git log commit subjects
    git_completed: list[str] = []
    try:
        import re as _regex
        log_proc = _git(["git", "log", "--oneline", "-100"], timeout=10)
        if log_proc.returncode == 0:
            for line in log_proc.stdout.splitlines():
                # Search entire line (commit hash + subject) for task IDs
                matches = _regex.findall(r'\b(P\d+-\d+)\b', line)
                for m in matches:
                    if m not in git_completed:
                        git_completed.append(m)
    except Exception:
        pass

    # Merge with existing completed tasks
    existing_completed = list(state.get("tasks_completed", []))
    existing_blocked = list(state.get("tasks_blocked", []))

    for tid in git_completed:
        if tid not in existing_completed:
            existing_completed.append(tid)
        if tid in existing_blocked:
            existing_blocked.remove(tid)

    # Update state
    state["tasks_completed"] = existing_completed
    state["tasks_blocked"] = existing_blocked
    if existing_completed and not existing_blocked:
        state["runner_status"] = "PAUSED"
        state["last_status"] = "PASS"
        state["last_error"] = None
    state["last_commit"] = git_completed[0] if git_completed else state.get("last_commit")

    _save_state(state)

    # Determine next task
    tasks = _flatten_tasks(block) if block else _flatten_tasks()
    completed = set(existing_completed)
    blocked = set(existing_blocked)
    next_task = None
    for t in tasks:
        if t["task_id"] not in completed and t["task_id"] not in blocked:
            next_task = t
            break

    return {
        "tool": "qbot_roadmap_runner_reconcile_state",
        "status": "OK",
        "safety_class": "WRITE_SAFE",
        "block": block,
        "completed_from_git": git_completed,
        "completed_current": existing_completed,
        "blocked_current": existing_blocked,
        "next_task_id": next_task["task_id"] if next_task else None,
        "next_task_description": next_task["description"][:120] if next_task else None,
        "notes": f"Reconciled {len(git_completed)} tasks from git log",
    }


def _tool_qbot_roadmap_runner_resume(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    reason = _sanitize_text(args.get("reason", "manual resume"), 200)
    state = _update_state_progress(
        runner_status="IDLE",
        last_error=None,
    )
    return {"tool": "qbot_roadmap_runner_resume", "status": "OK", "state": state, "reason": reason}


def _tool_qbot_roadmap_runner_notify_test(_args: dict | None = None) -> dict[str, Any]:
    text = f"Qbot roadmap runner notify test\nTimestamp: {_utc_now()}"
    result = _notify_telegram_message(text, allow_no_notify=False)
    if result.get("ok"):
        _append_telegram_notification({
            "created_at": _utc_now(),
            "task_id": "notify_test",
            "block": "meta",
            "status": "PASS",
            "dry_run": False,
            "message": text,
            "ok": True,
            "error": None,
        })
    return {
        "tool": "qbot_roadmap_runner_notify_test",
        "status": "OK" if result.get("ok") else "ERROR",
        "notification": {
            "ok": bool(result.get("ok")),
            "error": result.get("error"),
        },
    }
