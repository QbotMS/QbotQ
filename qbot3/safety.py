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

try:
    import psycopg
    from psycopg.rows import dict_row
    _HAS_PSYCOPG = True
except ImportError:
    psycopg = None
    _HAS_PSYCOPG = False

_DOC_ALLOWLIST = frozenset({
    "QBOT_BIBLE.md",
    "QBOT_KNOWHOW.md",
    "QBOT_PROJECT_INSTRUCTION_LOCAL.md",
})
_DOC_BASE_DIR = "/opt/qbot/docs"

# Akcje dozwolone w qbot3, ktore na 2026-06-14 nie maja jeszcze wpisu w
# modules/*/manifest.py["write_actions"]. Migrowac do manifestow w kolejnej
# sesji; do tego czasu utrzymywane tu jawnie, zeby nie zrobic regresji.
_LEGACY_EXTRA_ACTIONS = frozenset({
    "calendar_event_add",
    "reminder_add",
    "memory_confirmed_fact_add",
    "rwgps_route_export_gpx",
    "rwgps_route_surface_analyze",
    "fit_file_analyze",
})

# Allowlist generowana z manifestow modulow (core/registry.py) + legacy
# extra. Jedyne zrodlo prawdy dla write_actions to modules/*/manifest.py -
# nowa akcja dodana tam automatycznie dziala tutaj, bez recznej edycji.
try:
    from core.registry import get_allowlist as _registry_get_allowlist
    _ACTION_ALLOWLIST = frozenset(_registry_get_allowlist()) | _LEGACY_EXTRA_ACTIONS
except Exception:
    # fallback hard-coded na wypadek bledu importu registry
    _ACTION_ALLOWLIST = frozenset({
        "nutrition_log_add",
        "calendar_event_add",
        "reminder_add",
        "planning_fact_add",
        "memory_confirmed_fact_add",
        "garmin_workout_create",
        "qbot_doc_append",
        "rwgps_gpx_import",
        "rwgps_route_import_gpx",
        "rwgps_route_export_gpx",
        "rwgps_route_profile_export_csv",
        "rwgps_route_surface_analyze",
        "rwgps_poi_push",
        "route_poi_analyze",
        "fit_file_analyze",
        "qbot_artifact_put",
        "qbot_artifact_get",
    })


def _db() -> Any:
    if not _HAS_PSYCOPG:
        raise RuntimeError("psycopg not available — cannot connect to DB")
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
    if action_type == "nutrition_log_add":
        required = ("date", "source", "meal_name", "kcal_total")
        missing = [field for field in required if payload.get(field) in (None, "")]
        if missing:
            return {"status": "BLOCKED", "error": f"nutrition payload missing required fields: {', '.join(missing)}"}
        date_raw = str(payload.get("date", "")).strip()
        try:
            from datetime import date as dt_date
            dt_date.fromisoformat(date_raw[:10])
        except Exception:
            return {"status": "BLOCKED", "error": f"invalid nutrition date: {date_raw}"}
        if not str(payload.get("source", "")).strip():
            return {"status": "BLOCKED", "error": "nutrition source required"}
        macros = [payload.get("protein_g"), payload.get("carbs_g"), payload.get("fat_g")]
        if any(v is not None for v in macros) and any(v in (None, "") for v in macros):
            return {"status": "BLOCKED", "error": "protein_g, carbs_g and fat_g must be provided together when known"}

    if action_type == "qbot_artifact_put":
        required = ("project_id", "filename", "content_base64", "mime_type")
        missing = [f for f in required if not payload.get(f)]
        if missing:
            return {"status": "BLOCKED", "error": f"artifact_put payload missing required fields: {', '.join(missing)}"}

        filename = str(payload["filename"])
        if any(c in filename for c in ("/", "\\", "..", "\x00")):
            return {"status": "BLOCKED", "error": f"path traversal detected in filename: {filename}"}

        allowed_exts = frozenset({".xlsx", ".csv", ".md", ".json", ".gpx", ".txt", ".pdf"})
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in allowed_exts:
            return {"status": "BLOCKED", "error": f"extension '{ext}' not allowed; allowed: {sorted(allowed_exts)}"}

        import base64
        try:
            raw = base64.b64decode(payload["content_base64"], validate=True)
        except Exception:
            return {"status": "BLOCKED", "error": "content_base64 is not valid base64"}

        if len(raw) > 25 * 1024 * 1024:
            return {"status": "BLOCKED", "error": f"decoded content exceeds 25 MB ({len(raw)} bytes)"}

        import hashlib
        actual_sha256 = hashlib.sha256(raw).hexdigest()
        sha256_provided = str(payload.get("sha256", "")).strip()
        if sha256_provided and actual_sha256 != sha256_provided:
            return {"status": "BLOCKED", "error": f"sha256 mismatch: got {actual_sha256[:16]}... expected {sha256_provided[:16]}..."}

        size_provided = payload.get("size_bytes")
        if size_provided is not None and int(size_provided) != len(raw):
            return {"status": "BLOCKED", "error": f"size_bytes mismatch: got {len(raw)}, expected {int(size_provided)}"}

    if action_type == "garmin_workout_create":
        has_name = bool(str(payload.get("workoutName", "")).strip() or str(payload.get("name", "")).strip())
        has_segments = isinstance(payload.get("workoutSegments"), list) and bool(payload.get("workoutSegments"))
        has_steps = isinstance(payload.get("steps"), list) and bool(payload.get("steps"))
        if not has_name:
            return {"status": "BLOCKED", "error": "garmin_workout_create requires workoutName or name"}
        if not (has_segments or has_steps):
            return {"status": "BLOCKED", "error": "garmin_workout_create requires workoutSegments or steps"}

    if action_type == "route_poi_analyze":
        merge_artifacts = payload.get("merge_artifact_ids")
        has_source = any(str(payload.get(field, "")).strip() for field in ("route_id", "artifact_id", "path"))
        if not has_source and not merge_artifacts:
            return {"status": "BLOCKED", "error": "route_id, artifact_id, path or merge_artifact_ids required"}
        if not merge_artifacts:
            required = ("km_from", "km_to")
            missing = [field for field in required if payload.get(field) in (None, "")]
            if missing:
                return {"status": "BLOCKED", "error": f"route_poi_analyze payload missing required fields: {', '.join(missing)}"}
            try:
                km_from = float(payload.get("km_from"))
                km_to = float(payload.get("km_to"))
            except (TypeError, ValueError):
                return {"status": "BLOCKED", "error": "km_from and km_to must be numeric"}
            if km_to < km_from:
                return {"status": "BLOCKED", "error": "km_to must be >= km_from"}
        buffers = payload.get("buffers") or {}
        if buffers and not isinstance(buffers, dict):
            return {"status": "BLOCKED", "error": "buffers must be an object if provided"}
        for key in ("attractions_m", "hard_resupply_m", "soft_food_m", "water_m", "food_m", "chunk_km", "chunk_overlap_km", "min_chunk_km", "analysis_timeout_sec", "overpass_timeout_sec", "overpass_retries", "retry_backoff_sec"):
            value = buffers.get(key) if isinstance(buffers, dict) else None
            if value in (None, ""):
                continue
            try:
                float(value)
            except (TypeError, ValueError):
                return {"status": "BLOCKED", "error": f"buffers.{key} must be numeric"}
            if float(value) < 0:
                return {"status": "BLOCKED", "error": f"buffers.{key} must be >= 0"}
        focus = str(payload.get("focus", "")).strip()
        if focus and focus.lower() not in {"all", "logistics", "hard_resupply", "food_only"}:
            return {"status": "BLOCKED", "error": "focus must be one of: all, logistics, hard_resupply, food_only"}
        timeout_sec = payload.get("timeout_sec")
        if timeout_sec not in (None, ""):
            try:
                if float(timeout_sec) <= 0:
                    return {"status": "BLOCKED", "error": "timeout_sec must be > 0"}
            except (TypeError, ValueError):
                return {"status": "BLOCKED", "error": "timeout_sec must be numeric"}

    if action_type == "rwgps_route_profile_export_csv":
        route_id = payload.get("route_id")
        if route_id in (None, ""):
            return {"status": "BLOCKED", "error": "route_id required"}

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
            cur.execute(
                "SELECT id FROM garmin_workout_write_audit WHERE idempotency_key=%s LIMIT 1",
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
