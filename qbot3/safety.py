#!/usr/bin/env python3
"""QBot3 Safety — write idempotency, audit logging, allowlist validation.

Zero legacy router imports. No hidden tool selection. All writes go through here.
Action draft standard per P4 contract.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

_DOC_ALLOWLIST = frozenset({
    "QBOT_BIBLE.md",
    "QBOT_KNOWHOW.md",
    "QBOT_PROJECT_INSTRUCTION_LOCAL.md",
})
_DOC_BASE_DIR = "/opt/qbot/docs"

_ACTION_ALLOWLIST = frozenset({
    "nutrition_log_add",
    "calendar_event_add",
    "reminder_add",
    "planning_fact_add",
    "memory_confirmed_fact_add",
})


def _db() -> Any:
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
    )


def validate(action_type: str, payload: dict[str, Any], idem_key: str, dry_run: bool = False) -> dict[str, Any]:
    if action_type not in _ACTION_ALLOWLIST:
        return {"status": "BLOCKED", "error": f"action_type '{action_type}' not in allowlist: {sorted(_ACTION_ALLOWLIST)}"}
    if not isinstance(payload, dict):
        return {"status": "BLOCKED", "error": "payload must be an object"}
    if not idem_key:
        return {"status": "BLOCKED", "error": "idempotency_key required"}
    if dry_run:
        return {"status": "OK", "dry_run": True, "action_type": action_type, "idempotency_key": idem_key,
                "note": "dry_run — no actual write performed"}
    dup = _check_duplicate(action_type, idem_key)
    if dup:
        return dup
    return {"status": "OK"}


def validate_action_draft(draft: dict[str, Any]) -> dict[str, Any]:
    """Validate a standardized action_draft per P4 contract."""
    required = ["action_type", "payload", "requires_confirm", "idempotency_key_suggestion"]
    for field in required:
        if field not in draft:
            return {"status": "BLOCKED", "error": f"action_draft missing required field: {field}"}
    if not draft.get("requires_confirm"):
        return {"status": "BLOCKED", "error": "action_draft requires_confirm must be true"}
    if not isinstance(draft.get("payload"), dict):
        return {"status": "BLOCKED", "error": "payload must be an object"}
    return validate(
        draft["action_type"],
        draft["payload"],
        draft.get("idempotency_key_suggestion", ""),
    )


def _check_duplicate(action_type: str, idem_key: str) -> dict[str, Any] | None:
    try:
        with _db() as c:
            cur = c.cursor()
            cur.execute(
                "SELECT id FROM qbot_doc_write_audit WHERE idempotency_key=%s AND status='OK' LIMIT 1",
                (idem_key,),
            )
            if cur.fetchone():
                return {"status": "DUPLICATE", "action_type": action_type, "idempotency_key": idem_key, "note": "already processed"}
            cur.execute(
                "SELECT id FROM nutrition_write_audit WHERE idempotency_key=%s LIMIT 1",
                (idem_key,),
            )
            if cur.fetchone():
                return {"status": "DUPLICATE", "action_type": action_type, "idempotency_key": idem_key, "note": "already processed"}
            cur.execute(
                "SELECT id FROM qcal_write_audit WHERE idempotency_key=%s LIMIT 1",
                (idem_key,),
            )
            if cur.fetchone():
                return {"status": "DUPLICATE", "action_type": action_type, "idempotency_key": idem_key, "note": "already processed"}
    except Exception:
        pass
    return None


def _save_audit(table: str, data: dict[str, Any]) -> None:
    try:
        cols = ", ".join(data.keys())
        vals = ", ".join(["%s"] * len(data))
        with _db() as c:
            c.execute(f"INSERT INTO {table} ({cols}) VALUES ({vals})", tuple(data.values()))
    except Exception:
        pass


def exec_doc_append(action_type: str, payload: dict[str, Any], idem_key: str, source: str = "qbot3") -> dict[str, Any]:
    target = str(payload.get("target_document", "")).strip()
    if target not in _DOC_ALLOWLIST:
        return {"status": "BLOCKED", "error": f"invalid target_document: {target}"}
    content_md = str(payload.get("content_markdown", "")).strip()
    resolved = os.path.join(_DOC_BASE_DIR, target)
    if not os.path.isfile(resolved):
        return {"status": "NOT_FOUND", "error": f"file not found: {resolved}"}
    with open(resolved, "r", encoding="utf-8") as f:
        current = f.read()
    heading = str(payload.get("heading", "")).strip()
    new_section = f"\n\n{heading}\n\n{content_md}\n"
    new_content = current + new_section
    backup_path = f"{resolved}.{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.bak"
    try:
        import shutil
        shutil.copy2(resolved, backup_path)
    except Exception:
        pass
    with open(resolved, "w", encoding="utf-8") as f:
        f.write(new_content)
    _save_audit("qbot_doc_write_audit", {
        "action_type": action_type,
        "target_document": target,
        "idempotency_key": idem_key,
        "status": "OK",
        "backup_path": backup_path,
        "payload_hash": hashlib_hex(payload),
        "result_json": json.dumps({"new_size": len(new_content)}, default=str),
        "source": source,
    })
    return {"status": "OK", "action_type": action_type, "target_document": target, "idempotency_key": idem_key, "backup_path": backup_path, "changed": True}


def hashlib_hex(data: dict) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:16]
