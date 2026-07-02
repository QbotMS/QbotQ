#!/usr/bin/env python3
"""Detached trigger for canonical route precompute jobs.

Called from the RWGPS webhook as an internal worker. In normal mode it
refreshes the canonical route base, checks whether the current
route_version_key is already fully precomputed, and runs the route
precompute orchestrator only when needed. In await-confirmation mode it
only materializes the RWGPS import and creates a Telegram pending action.

Dok.: docs/TELEGRAM_ROUTE_CONFIRM.md
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Mapping

sys.path.insert(0, "/opt/qbot/app")

from qbot3.routes.route_precompute_orchestrator import ensure_route_precompute
from qbot3.routes.route_precompute_orchestrator import active_precompute_job_types
from qbot3.routes.route_base_store import ensure_route_base
import psycopg
from psycopg.rows import dict_row
import os
import hashlib
import time


def _db_conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "5")),
    )


def _telegram_allowed_chat_ids() -> list[str]:
    raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS") or os.getenv("TELEGRAM_ALLOWED_CHAT_ID") or ""
    return [s.strip() for s in raw.split(",") if s.strip()]


def _route_confirmation_chat_id(conn, *, route_id_text: str) -> str | None:
    env_chat = (os.getenv("QBOT_ROUTE_CONFIRMATION_CHAT_ID") or os.getenv("TELEGRAM_CONFIRMATION_CHAT_ID") or "").strip()
    if env_chat:
        return env_chat

    allowed = _telegram_allowed_chat_ids()
    if not allowed:
        return None
    if len(allowed) == 1:
        return allowed[0]

    row = conn.execute(
        """
        SELECT chat_id
        FROM telegram_conversations
        WHERE chat_id = ANY(%s::text[])
        ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
        LIMIT 1
        """,
        (allowed,),
    ).fetchone()
    if row and row.get("chat_id"):
        return str(row.get("chat_id"))
    return allowed[0]


def _route_confirmation_details(conn, route_id_text: str) -> dict[str, object] | None:
    row = conn.execute(
        """
        SELECT
            a.id AS route_artifact_id,
            a.sha256 AS route_artifact_sha256,
            a.metadata_json AS route_artifact_metadata,
            pr.id AS route_parse_result_id,
            pr.distance_m,
            pr.distance_km,
            pr.elevation_gain_m,
            rb.route_version_key
        FROM qbot_v2.route_artifacts a
        LEFT JOIN qbot_v2.route_parse_results pr
            ON pr.route_artifact_id = a.id
        LEFT JOIN qbot_v2.route_base rb
            ON rb.route_artifact_id = a.id
        WHERE a.route_id::text = %s
        ORDER BY a.updated_at DESC NULLS LAST, a.created_at DESC NULLS LAST, a.id DESC
        LIMIT 1
        """,
        (route_id_text,),
    ).fetchone()
    if not row:
        return None

    metadata = row.get("route_artifact_metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
    route_name = str(metadata.get("route_name") or metadata.get("name") or f"RWGPS {route_id_text}").strip()
    distance_m = row.get("distance_m")
    distance_km = row.get("distance_km")
    elevation_gain_m = row.get("elevation_gain_m")
    route_version_key = row.get("route_version_key")
    if not route_version_key:
        route_version_key = row.get("route_artifact_sha256") or f"route-{route_id_text}"
    return {
        "route_id": route_id_text,
        "route_artifact_id": row.get("route_artifact_id"),
        "route_artifact_sha256": row.get("route_artifact_sha256"),
        "route_parse_result_id": row.get("route_parse_result_id"),
        "route_name": route_name,
        "distance_m": distance_m,
        "distance_km": distance_km,
        "elevation_gain_m": elevation_gain_m,
        "route_version_key": str(route_version_key),
    }


def _route_confirmation_idempotency_key(details: dict[str, object]) -> str:
    raw = "|".join(
        str(details.get(key) or "")
        for key in ("route_id", "route_artifact_sha256", "route_version_key")
    )
    return "confirm_route_analysis:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _route_confirmation_preview(details: dict[str, object]) -> str:
    route_name = str(details.get("route_name") or "").strip() or f"RWGPS {details.get('route_id')}"
    distance_km = details.get("distance_km")
    if distance_km is None and details.get("distance_m") is not None:
        distance_km = float(details["distance_m"]) / 1000.0
    elevation_gain_m = details.get("elevation_gain_m")
    if isinstance(distance_km, (int, float)):
        distance_text = f"{float(distance_km):.1f} km"
    else:
        distance_text = "nieznany dystans"
    if isinstance(elevation_gain_m, (int, float)):
        elevation_text = f"+{int(round(float(elevation_gain_m)))} m"
    else:
        elevation_text = "nieznane przewyższenie"
    return (
        f"Znalazłem nową trasę RWGPS: {route_name}, {distance_text}, {elevation_text}.\n"
        "Uruchomić pełną analizę?"
    )


def _route_confirmation_prompt_text(action_id: int, preview: str) -> str:
    preview_text = str(preview).strip()
    return f"#{action_id} {preview_text}\n\nOdpowiedz: {action_id} TAK albo {action_id} NIE"


def _send_route_confirmation_prompt(route_id_text: str, *, trigger_source: str) -> dict[str, object]:
    import qbot_qcal_telegram

    with _db_conn() as conn:
        details = _route_confirmation_details(conn, route_id_text)
        if not details:
            return {"status": "error", "error": f"missing route details for route_id={route_id_text}", "route_id": route_id_text}
        chat_id = _route_confirmation_chat_id(conn, route_id_text=route_id_text)
        if not chat_id:
            return {"status": "error", "error": "no Telegram chat configured for route confirmation", "route_id": route_id_text, "route_details": details}

    preview = _route_confirmation_preview(details)
    payload = {
        "route_id": route_id_text,
        "route_name": details.get("route_name"),
        "route_artifact_id": details.get("route_artifact_id"),
        "route_parse_result_id": details.get("route_parse_result_id"),
        "route_artifact_sha256": details.get("route_artifact_sha256"),
        "route_version_key": details.get("route_version_key"),
        "distance_km": details.get("distance_km"),
        "distance_m": details.get("distance_m"),
        "elevation_gain_m": details.get("elevation_gain_m"),
        "trigger_source": trigger_source,
    }
    idem_key = _route_confirmation_idempotency_key(details)

    pending = qbot_qcal_telegram.upsert_pending_action(
        chat_id=str(chat_id),
        action_type="confirm_route_analysis",
        payload=payload,
        preview=preview,
        idem_key=idem_key,
    )
    if pending.get("status") == "error":
        return {"status": "error", "error": pending.get("error", "pending action creation failed"), "route_id": route_id_text, "route_details": details}

    pending_action_id = pending.get("pending_action_id")
    if pending_action_id:
        qbot_qcal_telegram._conv_upsert(str(chat_id), state="awaiting_confirmation", pending_action_id=int(pending_action_id))
    if pending.get("created"):
        prompt_text = _route_confirmation_prompt_text(int(pending_action_id), preview) if pending_action_id else preview
        refresh_result = qbot_qcal_telegram._refresh_pending_expires_at(str(chat_id), int(pending_action_id), expires_minutes=30) if pending_action_id else {"status": "not_found"}
        if refresh_result.get("status") != "ok":
            return {
                "status": "error",
                "route_id": route_id_text,
                "route_details": details,
                "pending_action_id": pending_action_id,
                "pending_status": pending.get("status"),
                "error": refresh_result.get("error") or "failed to refresh expires_at before Telegram send",
            }
        send_result = qbot_qcal_telegram.send_message(str(chat_id), prompt_text)
        qbot_qcal_telegram._turn_add(
            str(chat_id),
            "outbound",
            text=prompt_text,
            intent="route_confirmation_prompt_sent" if send_result.get("ok") else "route_confirmation_prompt_failed",
            response_json=send_result,
            action_id=int(pending_action_id) if pending_action_id else None,
        )
        if not send_result.get("ok"):
            return {
                "status": "error",
                "route_id": route_id_text,
                "route_details": details,
                "pending_action_id": pending_action_id,
                "pending_status": pending.get("status"),
                "telegram_send": send_result,
                "error": send_result.get("description") or send_result.get("error") or "telegram send failed",
            }
    else:
        send_result = {"ok": True, "skipped": True, "reason": "existing_pending_action"}

    return {
        "status": "OK",
        "route_id": route_id_text,
        "route_details": details,
        "pending_action_id": pending_action_id,
        "pending_status": pending.get("status"),
        "chat_id": str(chat_id),
        "telegram_send": send_result,
        "prompt_text": _route_confirmation_prompt_text(int(pending_action_id), preview) if pending_action_id else preview,
        "idempotency_key": idem_key,
    }


def _route_confirmation_launch_audit_row(conn, *, route_id_text: str, action_id: int | None = None) -> dict[str, object] | None:
    if action_id is None:
        row = conn.execute(
            """
            SELECT id, action_id, qbot_response_json
            FROM telegram_conversation_turns
            WHERE intent='route_precompute_launch_audit'
              AND qbot_response_json->>'route_id' = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (route_id_text,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT id, action_id, qbot_response_json
            FROM telegram_conversation_turns
            WHERE intent='route_precompute_launch_audit'
              AND action_id = %s
              AND qbot_response_json->>'route_id' = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (action_id, route_id_text),
        ).fetchone()
    return dict(row) if row else None


def _route_confirmation_final_notification_sent(conn, *, launch_audit_turn_id: int) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM telegram_conversation_turns
        WHERE intent IN ('route_confirmation_final_notification_sent', 'route_confirmation_final_notification_failed')
          AND qbot_response_json->>'launch_audit_turn_id' = %s
        LIMIT 1
        """,
        (str(launch_audit_turn_id),),
    ).fetchone()
    return bool(row)


def _format_duration_pl(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    total = int(round(seconds))
    if total < 0:
        return None
    if total < 60:
        return f"{total} s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes} min {secs} s" if secs else f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min"


def _route_precompute_compute_seconds(conn, route_version_key: str) -> float | None:
    from datetime import datetime
    rows = _route_precompute_rows(conn, route_version_key)
    starts = []
    ends = []
    for row in rows:
        lsj = row.get("layer_status_json")
        if isinstance(lsj, str):
            try:
                lsj = json.loads(lsj)
            except Exception:
                lsj = None
        if not isinstance(lsj, dict):
            continue
        started = lsj.get("started_at")
        finished = lsj.get("finished_at")
        if started:
            try:
                starts.append(datetime.fromisoformat(str(started)))
            except Exception:
                pass
        if finished:
            try:
                ends.append(datetime.fromisoformat(str(finished)))
            except Exception:
                pass
    if not starts or not ends:
        return None
    delta = (max(ends) - min(starts)).total_seconds()
    return delta if delta >= 0 else None


def _route_confirmation_final_text(details: dict[str, object], *, trigger_status: str, duration_seconds: float | None = None) -> str:
    route_name = str(details.get("route_name") or "").strip() or f"RWGPS {details.get('route_id')}"
    dur = _format_duration_pl(duration_seconds)
    dur_suffix = f" Czas liczenia: {dur}." if dur else ""
    if trigger_status == "skipped":
        return f"✅ Analiza trasy {route_name} była już kompletna.{dur_suffix} Dane zapisane w DB. Możesz poprosić o pełny raport."
    return f"✅ Analiza trasy {route_name} zakończona.{dur_suffix} Dane zapisane w DB. Możesz poprosić o pełny raport."


def _send_route_confirmation_final_notification(result: dict[str, object], *, trigger_source: str) -> dict[str, object]:
    if trigger_source != "telegram_confirm":
        return {"status": "skipped", "reason": "non_telegram_confirm_trigger"}

    route_id_text = str(result.get("route_id") or "").strip()
    if not route_id_text:
        return {"status": "error", "error": "missing route_id in trigger result"}

    route_details = {}
    route_import = result.get("route_import")
    confirmation = result.get("confirmation")
    pending_action_id = None

    if isinstance(route_import, dict):
        route_details = dict(route_import)
    if isinstance(confirmation, dict):
        pending_action_id = confirmation.get("pending_action_id")

    with _db_conn() as conn:
        launch_row = None
        for _ in range(20):
            launch_row = _route_confirmation_launch_audit_row(
                conn,
                route_id_text=route_id_text,
                action_id=int(pending_action_id) if pending_action_id is not None else None,
            )
            if launch_row:
                break
            time.sleep(0.25)
        if not launch_row:
            return {"status": "skipped", "reason": "missing_launch_audit"}
        launch_audit_turn_id = int(launch_row["id"])
        if pending_action_id is None:
            pending_action_id = launch_row.get("action_id")
        if _route_confirmation_final_notification_sent(conn, launch_audit_turn_id=launch_audit_turn_id):
            return {"status": "skipped", "reason": "already_notified", "launch_audit_turn_id": launch_audit_turn_id}
        details = _route_confirmation_details(conn, route_id_text) or route_details
        chat_id = _route_confirmation_chat_id(conn, route_id_text=route_id_text)
        rvk_for_dur = str(result.get("route_version_key") or "").strip()
        compute_seconds = _route_precompute_compute_seconds(conn, rvk_for_dur) if rvk_for_dur else None
        if not chat_id:
            return {"status": "error", "error": "no Telegram chat configured for final notification", "launch_audit_turn_id": launch_audit_turn_id}

    final_status = str(result.get("trigger_status") or "").strip().lower()
    result_status = str(result.get("status") or "").strip().upper()
    if result_status not in ("OK", "OK".lower().upper()) and final_status != "skipped":
        message_text = f"⚠️ Analiza trasy {route_id_text} zakończyła się błędem. Sprawdź logi i DB."
        intent = "route_confirmation_final_notification_failed"
    else:
        message_text = _route_confirmation_final_text(details, trigger_status=final_status or "ran", duration_seconds=compute_seconds)
        intent = "route_confirmation_final_notification_sent"

    import qbot_qcal_telegram

    send_result = qbot_qcal_telegram.send_message(str(chat_id), message_text)
    audit_payload = {
        "status": "OK" if send_result.get("ok") else "ERROR",
        "route_id": route_id_text,
        "trigger_status": result.get("trigger_status"),
        "result_status": result.get("status"),
        "launch_audit_turn_id": launch_audit_turn_id,
        "telegram_send": send_result,
        "message_text": message_text,
    }
    qbot_qcal_telegram._turn_add(
        str(chat_id),
        "outbound",
        text=message_text,
        intent=intent,
        response_json=audit_payload,
        action_id=int(pending_action_id) if pending_action_id is not None else None,
    )
    return {
        "status": "OK" if send_result.get("ok") else "ERROR",
        "launch_audit_turn_id": launch_audit_turn_id,
        "telegram_send": send_result,
        "message_text": message_text,
        "intent": intent,
    }


def _normalize_route_id(route_id: str | int) -> str:
    text = str(route_id).strip()
    if not text:
        raise ValueError("route_id required")
    return text


def _route_precompute_rows(conn, route_version_key: str) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT job_type, status, layer_status_json, idempotency_key
        FROM qbot_v2.route_precompute_jobs
        WHERE route_version_key = %s
        ORDER BY job_type
        """,
        (route_version_key,),
    ).fetchall()
    return [dict(row) for row in rows]


def _route_import_state(conn, route_id_text: str) -> dict[str, object]:
    row = conn.execute(
        """
        SELECT
            a.id AS route_artifact_id,
            pr.id AS route_parse_result_id
        FROM qbot_v2.route_artifacts a
        LEFT JOIN qbot_v2.route_parse_results pr
            ON pr.route_artifact_id = a.id
        WHERE a.route_id::text = %s
        ORDER BY a.updated_at DESC NULLS LAST, a.created_at DESC NULLS LAST, a.id DESC
        LIMIT 1
        """,
        (route_id_text,),
    ).fetchone()
    if not row:
        return {
            "has_artifact": False,
            "has_parse_result": False,
            "route_artifact_id": None,
            "route_parse_result_id": None,
        }
    return {
        "has_artifact": bool(row.get("route_artifact_id")),
        "has_parse_result": bool(row.get("route_parse_result_id")),
        "route_artifact_id": row.get("route_artifact_id"),
        "route_parse_result_id": row.get("route_parse_result_id"),
    }


def _route_surface_profile_state(conn, route_artifact_id: int | None) -> dict[str, object]:
    if route_artifact_id is None:
        return {
            "has_profile": False,
            "surface_profile_id": None,
        }
    row = conn.execute(
        """
        SELECT id AS surface_profile_id
        FROM qbot_v2.route_surface_profiles
        WHERE route_artifact_id = %s
        ORDER BY enriched_at DESC NULLS LAST, id DESC
        LIMIT 1
        """,
        (route_artifact_id,),
    ).fetchone()
    if not row:
        return {
            "has_profile": False,
            "surface_profile_id": None,
        }
    return {
        "has_profile": True,
        "surface_profile_id": row.get("surface_profile_id"),
    }


def _route_frames_state(conn, route_artifact_id: int | None) -> dict[str, object]:
    if route_artifact_id is None:
        return {
            "has_frames": False,
            "frame_count": 0,
        }
    row = conn.execute(
        """
        SELECT count(*)::int AS frame_count
        FROM qbot_v2.route_frames
        WHERE route_artifact_id = %s
          AND frame_size_m = 80
        """,
        (route_artifact_id,),
    ).fetchone()
    frame_count = int(row.get("frame_count") or 0) if row else 0
    return {
        "has_frames": frame_count > 0,
        "frame_count": frame_count,
    }


def _route_artifact_path(conn, route_artifact_id: int | None) -> str | None:
    if route_artifact_id is None:
        return None
    row = conn.execute(
        """
        SELECT artifact_path
        FROM qbot_v2.route_artifacts
        WHERE id = %s
        LIMIT 1
        """,
        (route_artifact_id,),
    ).fetchone()
    return str(row.get("artifact_path")) if row and row.get("artifact_path") else None


def _persist_surface_profile_from_enrich_result(
    *,
    route_artifact_id: int,
    artifact_path: str,
    enrich_result: dict[str, object],
) -> dict[str, object] | None:
    import api_db

    with _db_conn() as conn:
        route_artifact_row = conn.execute(
            """
            SELECT id, route_id::text AS route_id, sha256, source_artifact_sha256, created_at, updated_at
            FROM qbot_v2.route_artifacts
            WHERE id = %s
            LIMIT 1
            """,
            (route_artifact_id,),
        ).fetchone()
    if not route_artifact_row:
        return None

    surface_profile = enrich_result.get("surface_profile") if isinstance(enrich_result, dict) else {}
    if not isinstance(surface_profile, dict):
        surface_profile = {}
    surface_summary: dict[str, object] = dict(surface_profile)
    if isinstance(enrich_result, dict):
        surface_summary.update(enrich_result)

    segments = surface_summary.get("segments")
    if not isinstance(segments, list):
        segments = surface_profile.get("segments") if isinstance(surface_profile.get("segments"), list) else []

    record = {
        "route_artifact_id": int(route_artifact_id),
        "enrichment_version": str(surface_summary.get("enrichment_version") or "surface-profile-v1"),
        "source_artifact_sha256": str(route_artifact_row.get("sha256") or route_artifact_row.get("source_artifact_sha256") or "").strip(),
        "surface_source": surface_summary.get("surface_source") or "unknown",
        "sample_every_m": surface_summary.get("sample_every_m") or surface_summary.get("sample_distance_m") or 50,
        "confidence": surface_summary.get("confidence"),
        "coverage_pct": surface_summary.get("coverage_pct"),
        "sampled_points": surface_summary.get("sampled_points"),
        "matched_points": surface_summary.get("matched_points"),
        "unmatched_points": surface_summary.get("unmatched_points"),
        "dominant_surface": surface_summary.get("dominant_surface"),
        "status": surface_summary.get("status") or "ok",
        "surface_summary_json": surface_summary,
        "surface_segments_json": segments,
        "surface_segments_path": surface_summary.get("surface_segments_path"),
    }
    if not record["source_artifact_sha256"]:
        return None
    try:
        profile_row = api_db.upsert_route_surface_profile(record)
        if isinstance(segments, list):
            seg_rows = [seg for seg in segments if isinstance(seg, dict)]
            if seg_rows:
                api_db.replace_route_surface_segments(profile_row["id"], seg_rows)
        return profile_row
    except Exception:
        return None


def _ensure_rwgps_route_artifact(route_id_text: str, *, force: bool = False) -> dict[str, object]:
    with _db_conn() as conn:
        state = _route_import_state(conn, route_id_text)
    if state["has_artifact"] and state["has_parse_result"] and not force:
        return {
            "status": "OK",
            "import_status": "skipped",
            "route_id": route_id_text,
            "route_artifact_id": state["route_artifact_id"],
            "route_parse_result_id": state["route_parse_result_id"],
        }

    from tools.rwgps.client import export_route_to_artifact

    export_result = export_route_to_artifact(route_id_text, fmt="gpx", return_mode="metadata")
    if not export_result.get("ok"):
        raise RuntimeError(
            export_result.get("reason")
            or export_result.get("error")
            or f"RWGPS export failed for route_id={route_id_text}"
        )

    with _db_conn() as conn:
        refreshed = _route_import_state(conn, route_id_text)
    return {
        "status": "OK",
        "import_status": "imported",
        "route_id": route_id_text,
        "route_artifact_id": refreshed["route_artifact_id"],
        "route_parse_result_id": refreshed["route_parse_result_id"],
        "export_result": export_result,
    }


def _ensure_rwgps_surface_profile(
    route_id_text: str,
    *,
    route_artifact_id: int | None = None,
    force: bool = False,
) -> dict[str, object]:
    artifact_path: str | None = None
    with _db_conn() as conn:
        import_state = _route_import_state(conn, route_id_text)
        effective_route_artifact_id = route_artifact_id or import_state.get("route_artifact_id")
        surface_state = _route_surface_profile_state(conn, int(effective_route_artifact_id) if effective_route_artifact_id is not None else None)

    if surface_state["has_profile"] and not force:
        return {
            "status": "OK",
            "surface_status": "skipped",
            "route_id": route_id_text,
            "route_artifact_id": effective_route_artifact_id,
            "surface_profile_id": surface_state["surface_profile_id"],
        }

    if not artifact_path:
        with _db_conn() as conn:
            artifact_path = _route_artifact_path(conn, int(effective_route_artifact_id) if effective_route_artifact_id is not None else None)
    if not artifact_path:
        return {
            "status": "ERROR",
            "surface_status": "missing_artifact_path",
            "route_id": route_id_text,
            "route_artifact_id": effective_route_artifact_id,
            "surface_profile_id": None,
            "error": f"missing route artifact path for route_id={route_id_text}",
        }

    from qbot_route_tools import _tool_qbot_route_artifact_enrich

    enrich_result = _tool_qbot_route_artifact_enrich(
        {
            "artifact_path": artifact_path,
            "enrich": ["surface"],
            "surface_source": "auto",
            "sample_every_m": 50,
            "return_mode": "summary",
        }
    )
    if not enrich_result.get("ok"):
        return {
            "status": "ERROR",
            "surface_status": "failed",
            "route_id": route_id_text,
            "route_artifact_id": effective_route_artifact_id,
            "surface_profile_id": None,
            "error": enrich_result.get("reason") or enrich_result.get("error") or "surface enrichment failed",
            "enrich_result": enrich_result,
        }

    with _db_conn() as conn:
        refreshed = _route_surface_profile_state(conn, int(effective_route_artifact_id) if effective_route_artifact_id is not None else None)
    # force=True: nadpisz istniejacy profil swiezym enrichem (upsert). Bez tego
    # wymuszony re-enrich liczyl poprawne segmenty, ale nie zapisywal ich
    # (prowieniencja nie trafiala do route_surface_profiles). Audyt 2026-07-02.
    if (force or not refreshed["has_profile"]) and effective_route_artifact_id is not None:
        with _db_conn() as conn:
            artifact_path = _route_artifact_path(conn, int(effective_route_artifact_id))
        if artifact_path:
            persisted = _persist_surface_profile_from_enrich_result(
                route_artifact_id=int(effective_route_artifact_id),
                artifact_path=artifact_path,
                enrich_result=enrich_result,
            )
            if persisted:
                with _db_conn() as conn:
                    refreshed = _route_surface_profile_state(conn, int(effective_route_artifact_id))
                try:
                    from tools.rwgps.route_frames import build as _build_route_frames

                    _build_route_frames(route_id=route_id_text, frame_size=80.0, dry_run=False, show=0)
                    frames_status = "built"
                except Exception as exc:
                    return {
                        "status": "ERROR",
                        "surface_status": "frames_failed",
                        "route_id": route_id_text,
                        "route_artifact_id": effective_route_artifact_id,
                        "surface_profile_id": refreshed["surface_profile_id"],
                        "error": f"route_frames build failed: {exc}",
                        "enrich_result": enrich_result,
                    }
    if not refreshed["has_profile"]:
        return {
            "status": "ERROR",
            "surface_status": "not_persisted",
            "route_id": route_id_text,
            "route_artifact_id": effective_route_artifact_id,
            "surface_profile_id": None,
            "error": "surface enrichment completed but no route_surface_profile was persisted",
            "enrich_result": enrich_result,
        }
    return {
        "status": "OK",
        "surface_status": "imported",
        "route_id": route_id_text,
        "route_artifact_id": effective_route_artifact_id,
        "surface_profile_id": refreshed["surface_profile_id"],
        "frames_status": "built" if refreshed["has_profile"] else "unknown",
        "enrich_result": enrich_result,
    }


def _ensure_rwgps_route_frames(
    route_id_text: str,
    *,
    route_artifact_id: int | None = None,
    force: bool = False,
) -> dict[str, object]:
    with _db_conn() as conn:
        import_state = _route_import_state(conn, route_id_text)
        effective_route_artifact_id = route_artifact_id or import_state.get("route_artifact_id")
        frames_state = _route_frames_state(conn, int(effective_route_artifact_id) if effective_route_artifact_id is not None else None)

    if frames_state["has_frames"] and not force:
        return {
            "status": "OK",
            "frames_status": "skipped",
            "route_id": route_id_text,
            "route_artifact_id": effective_route_artifact_id,
            "frame_count": frames_state["frame_count"],
        }

    if effective_route_artifact_id is None:
        return {
            "status": "ERROR",
            "frames_status": "missing_artifact_id",
            "route_id": route_id_text,
            "route_artifact_id": None,
            "frame_count": 0,
            "error": f"missing route artifact id for route_id={route_id_text}",
        }

    try:
        from tools.rwgps.route_frames import build as _build_route_frames

        rc = _build_route_frames(route_id=route_id_text, frame_size=80.0, dry_run=False, show=0)
    except Exception as exc:
        return {
            "status": "ERROR",
            "frames_status": "failed",
            "route_id": route_id_text,
            "route_artifact_id": effective_route_artifact_id,
            "frame_count": 0,
            "error": f"route_frames build failed: {exc}",
        }

    with _db_conn() as conn:
        refreshed = _route_frames_state(conn, int(effective_route_artifact_id))
    if not refreshed["has_frames"]:
        return {
            "status": "ERROR",
            "frames_status": "not_persisted",
            "route_id": route_id_text,
            "route_artifact_id": effective_route_artifact_id,
            "frame_count": 0,
            "error": "route_frames build completed but no frames were persisted",
            "build_result": rc,
        }
    return {
        "status": "OK",
        "frames_status": "built",
        "route_id": route_id_text,
        "route_artifact_id": effective_route_artifact_id,
        "frame_count": refreshed["frame_count"],
        "build_result": rc,
    }


def _precompute_complete(rows: list[dict[str, object]], env: Mapping[str, str] | None = None) -> bool:
    expected_job_types = active_precompute_job_types(env)
    if len(rows) != len(expected_job_types):
        return False
    present = {str(row.get("job_type") or "") for row in rows}
    if set(expected_job_types) != present:
        return False
    return all(str(row.get("status") or "").strip() == "complete" for row in rows)


def ensure_route_precompute_trigger(
    *,
    route_id: str | int,
    trigger_source: str = "rwgps_webhook",
    await_confirmation: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, object]:
    route_id_text = _normalize_route_id(route_id)
    import_result = _ensure_rwgps_route_artifact(route_id_text)
    if await_confirmation:
        prompt_result = _send_route_confirmation_prompt(route_id_text, trigger_source=trigger_source)
        if prompt_result.get("status") != "OK":
            return {
                "status": "ERROR",
                "trigger_status": "await_confirmation_failed",
                "route_id": route_id_text,
                "route_import": import_result,
                "confirmation": prompt_result,
            }
        return {
            "status": "OK",
            "trigger_status": "awaiting_confirmation",
            "route_id": route_id_text,
            "route_import": import_result,
            "confirmation": prompt_result,
        }

    surface_result = _ensure_rwgps_surface_profile(
        route_id_text,
        route_artifact_id=int(import_result.get("route_artifact_id")) if import_result.get("route_artifact_id") is not None else None,
    )
    if surface_result.get("status") != "OK":
        return {
            "status": "ERROR",
            "trigger_status": "failed",
            "route_id": route_id_text,
            "route_import": import_result,
            "route_surface": surface_result,
        }
    base_result = ensure_route_base(route_id_text)
    route_base = base_result["route_base"]
    route_base_id = int(route_base["route_base_id"])
    route_version_key = str(base_result["route_version_key"])
    route_artifact_id = base_result.get("route_artifact_id")
    frames_result = _ensure_rwgps_route_frames(
        route_id_text,
        route_artifact_id=int(route_artifact_id) if route_artifact_id is not None else None,
    )
    if frames_result.get("status") != "OK":
        return {
            "status": "ERROR",
            "trigger_status": "failed",
            "route_id": route_id_text,
            "route_import": import_result,
            "route_surface": surface_result,
            "route_frames": frames_result,
        }

    with _db_conn() as conn:
        rows = _route_precompute_rows(conn, route_version_key)
        already_complete = _precompute_complete(rows, env=env)
    if already_complete:
        skipped_result = {
            "status": "OK",
            "trigger_status": "skipped",
            "route_id": route_id_text,
            "route_base_id": route_base_id,
            "route_artifact_id": route_artifact_id,
            "route_version_key": route_version_key,
            "route_precompute_jobs_count": len(rows),
            "job_types": [row["job_type"] for row in rows],
            "route_import": import_result,
            "route_surface": surface_result,
            "route_frames": frames_result,
        }
        final_notification = _send_route_confirmation_final_notification(skipped_result, trigger_source=trigger_source)
        skipped_result["final_notification"] = final_notification
        return skipped_result

    result = ensure_route_precompute(route_id=route_id_text, trigger_source=trigger_source)
    final_notification = _send_route_confirmation_final_notification(result, trigger_source=trigger_source)
    return {
        "status": result.get("status", "OK"),
        "trigger_status": "ran",
        "route_id": route_id_text,
        "route_base_id": result.get("route_base_id", route_base_id),
        "route_artifact_id": result.get("route_artifact_id", route_artifact_id),
        "route_version_key": result.get("route_version_key", route_version_key),
        "route_precompute_jobs_count": len(result.get("job_rows") or []),
        "job_types": sorted((row.get("job_type") for row in result.get("job_rows") or [] if isinstance(row, dict))),
        "result": result,
        "route_import": import_result,
        "route_surface": surface_result,
        "route_frames": frames_result,
        "final_notification": final_notification,
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trigger canonical route precompute jobs for a route_id.")
    parser.add_argument("route_id", help="RWGPS route_id")
    parser.add_argument("--trigger-source", dest="trigger_source", default="rwgps_webhook")
    parser.add_argument("--await-confirmation", dest="await_confirmation", action="store_true")
    args = parser.parse_args(argv)
    result = ensure_route_precompute_trigger(
        route_id=args.route_id,
        trigger_source=args.trigger_source,
        await_confirmation=args.await_confirmation,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
