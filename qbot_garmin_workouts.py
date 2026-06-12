#!/usr/bin/env python3
"""Garmin workout creation helpers for QBot."""

from __future__ import annotations

import json
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row

from garmin_auth import garmin_client


GARMIN_YOGA_SPORT = {"sportTypeId": 7, "sportTypeKey": "yoga", "displayOrder": 8}
GARMIN_INTERVAL_STEP = {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3}
GARMIN_TIME_END = {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True}

_AUDIT_TABLE = "garmin_workout_write_audit"


def _conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=5,
    )


def ensure_audit_table() -> None:
    with _conn() as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_AUDIT_TABLE} (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                idempotency_key TEXT NOT NULL UNIQUE,
                action_type TEXT NOT NULL,
                workout_name TEXT NOT NULL,
                workout_id TEXT,
                status TEXT NOT NULL,
                verified BOOLEAN NOT NULL DEFAULT FALSE,
                payload_json JSONB NOT NULL,
                result_json JSONB,
                source TEXT DEFAULT 'chatgpt_mcp'
            )
            """
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{_AUDIT_TABLE}_created_at ON {_AUDIT_TABLE} (created_at)"
        )
        conn.commit()


def _json_safe(value: Any) -> Any:
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value)


def _sport_type_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sport_type = payload.get("sportType")
    sport = str(payload.get("sport", "")).strip().lower()
    if isinstance(sport_type, dict) and sport_type.get("sportTypeKey"):
        return {
            "sportTypeId": int(sport_type.get("sportTypeId", GARMIN_YOGA_SPORT["sportTypeId"])),
            "sportTypeKey": str(sport_type.get("sportTypeKey", GARMIN_YOGA_SPORT["sportTypeKey"])),
            "displayOrder": int(sport_type.get("displayOrder", GARMIN_YOGA_SPORT["displayOrder"])),
        }
    if sport in ("", "yoga"):
        return dict(GARMIN_YOGA_SPORT)
    raise ValueError(f"Unsupported Garmin sport: {sport}")


def _normalize_step(step: dict[str, Any], order: int) -> dict[str, Any]:
    seconds = step.get("seconds", step.get("endConditionValue"))
    if seconds in (None, ""):
        raise ValueError(f"step {order} missing seconds/endConditionValue")
    exercise_name = str(step.get("exerciseName") or step.get("pose") or step.get("name") or "").strip()
    if not exercise_name:
        raise ValueError(f"step {order} missing exerciseName")
    description = step.get("description")
    category = str(step.get("category", "POSE")).strip() or "POSE"
    step_type = step.get("stepType")
    if not isinstance(step_type, dict):
        step_type = dict(GARMIN_INTERVAL_STEP)
    end_condition = step.get("endCondition")
    if not isinstance(end_condition, dict):
        end_condition = dict(GARMIN_TIME_END)
    normalized = {
        "type": "ExecutableStepDTO",
        "stepOrder": int(step.get("stepOrder", order)),
        "stepType": step_type,
        "endCondition": end_condition,
        "endConditionValue": float(seconds),
        "category": category,
        "exerciseName": exercise_name,
    }
    if description not in (None, ""):
        normalized["description"] = str(description)
    return normalized


def build_workout_dto(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")

    workout_name = str(payload.get("workoutName") or payload.get("name") or "").strip()
    if not workout_name:
        raise ValueError("workoutName or name is required")

    sport_type = _sport_type_from_payload(payload)
    workout_segments = payload.get("workoutSegments")

    if isinstance(workout_segments, list) and workout_segments:
        normalized_segments: list[dict[str, Any]] = []
        duration = 0.0
        for idx, segment in enumerate(workout_segments, start=1):
            if not isinstance(segment, dict):
                raise ValueError(f"workoutSegments[{idx - 1}] must be an object")
            seg_sport = segment.get("sportType")
            if not isinstance(seg_sport, dict):
                seg_sport = dict(sport_type)
            steps = segment.get("workoutSteps") or []
            if not isinstance(steps, list) or not steps:
                raise ValueError(f"workoutSegments[{idx - 1}] must contain workoutSteps")
            normalized_steps = [_normalize_step(step, step_order) for step_order, step in enumerate(steps, start=1)]
            duration += sum(float(step["endConditionValue"]) for step in normalized_steps)
            normalized_segments.append(
                {
                    "segmentOrder": int(segment.get("segmentOrder", idx)),
                    "sportType": {
                        "sportTypeId": int(seg_sport.get("sportTypeId", sport_type["sportTypeId"])),
                        "sportTypeKey": str(seg_sport.get("sportTypeKey", sport_type["sportTypeKey"])),
                        "displayOrder": int(seg_sport.get("displayOrder", sport_type["displayOrder"])),
                    },
                    "workoutSteps": normalized_steps,
                }
            )
        estimated = payload.get("estimatedDurationInSecs")
        estimated_duration = int(estimated if estimated not in (None, "") else duration)
        dto = {
            "workoutName": workout_name,
            "sportType": sport_type,
            "estimatedDurationInSecs": estimated_duration,
            "workoutSegments": normalized_segments,
        }
    else:
        steps = payload.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError("payload must include workoutSegments or steps")
        normalized_steps = [_normalize_step(step, order) for order, step in enumerate(steps, start=1)]
        duration = sum(float(step["endConditionValue"]) for step in normalized_steps)
        estimated = payload.get("estimatedDurationInSecs")
        estimated_duration = int(estimated if estimated not in (None, "") else duration)
        dto = {
            "workoutName": workout_name,
            "sportType": sport_type,
            "estimatedDurationInSecs": estimated_duration,
            "workoutSegments": [
                {
                    "segmentOrder": 1,
                    "sportType": sport_type,
                    "workoutSteps": normalized_steps,
                }
            ],
        }

    description = payload.get("description")
    if description not in (None, ""):
        dto["description"] = str(description)

    author = payload.get("author")
    if isinstance(author, dict) and author:
        dto["author"] = author

    return dto


def _extract_workout_id(result: Any) -> str | None:
    if isinstance(result, dict):
        for key in ("workoutId", "id", "workout_id"):
            value = result.get(key)
            if value not in (None, ""):
                return str(value)
        for value in result.values():
            found = _extract_workout_id(value)
            if found:
                return found
    elif isinstance(result, list):
        for item in result:
            found = _extract_workout_id(item)
            if found:
                return found
    return None


def _find_workout_by_name(client: Any, workout_name: str) -> str | None:
    workouts = client.get_workouts(start=0, limit=100)
    matches = [w for w in workouts if isinstance(w, dict) and w.get("workoutName") == workout_name]
    if not matches:
        return None

    def created_key(item: dict[str, Any]) -> str:
        return str(item.get("createdDate") or item.get("updateDate") or "")

    latest = max(matches, key=created_key)
    value = latest.get("workoutId")
    return str(value) if value not in (None, "") else None


def _verify_workout(client: Any, workout_id: str, workout_name: str) -> bool:
    try:
        workout = client.get_workout_by_id(workout_id)
    except Exception:
        return False
    if not isinstance(workout, dict):
        return False
    return str(workout.get("workoutName", "")).strip() == workout_name


def audit_lookup(idempotency_key: str) -> dict[str, Any] | None:
    ensure_audit_table()
    with _conn() as conn:
        row = conn.execute(
            f"""
            SELECT idempotency_key, action_type, workout_name, workout_id, status, verified, payload_json, result_json
            FROM {_AUDIT_TABLE}
            WHERE idempotency_key = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (idempotency_key,),
        ).fetchone()
    if not row:
        return None
    return {k: _json_safe(v) for k, v in dict(row).items()}


def audit_record(
    *,
    idempotency_key: str,
    action_type: str,
    workout_name: str,
    workout_id: str | None,
    status: str,
    verified: bool,
    payload: dict[str, Any],
    result: dict[str, Any] | None,
    source: str = "chatgpt_mcp",
) -> None:
    ensure_audit_table()
    with _conn() as conn:
        conn.execute(
            f"""
            INSERT INTO {_AUDIT_TABLE}
                (idempotency_key, action_type, workout_name, workout_id, status, verified, payload_json, result_json, source)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (idempotency_key) DO UPDATE SET
                action_type = EXCLUDED.action_type,
                workout_name = EXCLUDED.workout_name,
                workout_id = EXCLUDED.workout_id,
                status = EXCLUDED.status,
                verified = EXCLUDED.verified,
                payload_json = EXCLUDED.payload_json,
                result_json = EXCLUDED.result_json,
                source = EXCLUDED.source
            """,
            (
                idempotency_key,
                action_type,
                workout_name,
                workout_id,
                status,
                verified,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                source,
            ),
        )
        conn.commit()


def execute_garmin_workout_create(
    payload: dict[str, Any],
    *,
    idempotency_key: str,
    confirm: bool,
    dry_run: bool = False,
    source: str = "chatgpt_mcp",
) -> dict[str, Any]:
    dto = build_workout_dto(payload)
    workout_name = dto["workoutName"]

    if dry_run:
        return {
            "status": "DRY_RUN_OK",
            "workoutName": workout_name,
            "workoutId": None,
            "verified": False,
            "payload": dto,
            "confirm_required": True,
            "idempotency_key": idempotency_key,
            "write_committed": False,
        }

    existing = audit_lookup(idempotency_key)
    if existing:
        return {
            "status": "DUPLICATE",
            "workoutName": existing.get("workout_name") or workout_name,
            "workoutId": existing.get("workout_id"),
            "verified": bool(existing.get("verified")),
            "idempotency_key": idempotency_key,
            "write_committed": False,
            "note": f"idempotency_key already processed ({existing.get('status')})",
        }

    audit_record(
        idempotency_key=idempotency_key,
        action_type="garmin_workout_create",
        workout_name=workout_name,
        workout_id=None,
        status="PENDING",
        verified=False,
        payload=dto,
        result={"status": "pending"},
        source=source,
    )

    try:
        client = garmin_client()
        result = client.upload_workout(dto)
        workout_id = _extract_workout_id(result) or _find_workout_by_name(client, workout_name)
        if not workout_id:
            raise RuntimeError(f"Garmin upload succeeded but no workoutId was returned for {workout_name}")
        verified = _verify_workout(client, workout_id, workout_name)
        result_payload = _json_safe(result) if isinstance(result, (dict, list)) else {"raw": str(result)}
        audit_record(
            idempotency_key=idempotency_key,
            action_type="garmin_workout_create",
            workout_name=workout_name,
            workout_id=workout_id,
            status="SUCCESS",
            verified=verified,
            payload=dto,
            result=result_payload if isinstance(result_payload, dict) else {"raw": result_payload},
            source=source,
        )
        return {
            "status": "success",
            "workoutName": workout_name,
            "workoutId": workout_id,
            "verified": verified,
            "write_committed": True,
            "idempotency_key": idempotency_key,
        }
    except Exception as exc:
        error_text = str(exc)[:500]
        try:
            audit_record(
                idempotency_key=idempotency_key,
                action_type="garmin_workout_create",
                workout_name=workout_name,
                workout_id=None,
                status="ERROR",
                verified=False,
                payload=dto,
                result={"error": error_text},
                source=source,
            )
        except Exception:
            pass
        return {
            "status": "ERROR",
            "workoutName": workout_name,
            "workoutId": None,
            "verified": False,
            "error": error_text,
            "write_committed": False,
            "idempotency_key": idempotency_key,
        }
