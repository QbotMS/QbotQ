#!/usr/bin/env python3
"""QBot3 MCP Adapter — exactly 2 public tools.

No hidden tool selection, no procedural orchestration.
qbot.query → agent_runtime.orchestrate_query()
qbot.action_execute → safety.validate() + exec
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from qbot3.agent_runtime import orchestrate_query
from qbot3.fallback_policy import (
    is_route_domain_query,
    planner_unavailable_response,
    should_use_albert_fallback,
)
from qbot3.safety import validate, exec_doc_append

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.INFO)


def _log_query_vnext_metrics(
    engine: str,
    intent: str | None,
    status: str | None,
    fallback_reason: str | None,
    query_len: int,
    sources_count: int,
    missing_sources_count: int,
    duration_ms: float,
) -> None:
    logger.info(
        "qbot_query | engine=%s intent=%s status=%s fallback=%s qlen=%d "
        "sources=%d missing=%d dur_ms=%.0f",
        engine, intent, status, fallback_reason or "none",
        query_len, sources_count, missing_sources_count, duration_ms,
    )

_MCP_PROTOCOL = "2024-11-05"
_MCP_SERVER_NAME = "qbot3"
_MCP_SERVER_VERSION = "qbot3"

_ACTION_EXECUTE_ALLOWLIST = (
    "nutrition_log_add",
    "calendar_event_add",
    "reminder_add",
    "planning_fact_add",
    "memory_confirmed_fact_add",
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
)

_ALLOWED_ACTIONS_DESCRIPTION = (
    ", ".join(_ACTION_EXECUTE_ALLOWLIST)
)


def list_allowed_actions() -> list[str]:
    """Return the current server-side action allowlist."""
    try:
        from qbot3.safety import _ACTION_ALLOWLIST
        return sorted(_ACTION_ALLOWLIST)
    except ImportError:
        return [a.strip() for a in _ALLOWED_ACTIONS_DESCRIPTION.split(",")]


def handle_qbot3_mcp(payload: dict[str, Any]) -> dict[str, Any]:
    method = payload.get("method", "")
    req_id = payload.get("id")

    if method == "initialize":
        proto = payload.get("params", {}).get("protocolVersion", _MCP_PROTOCOL)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": proto,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": _MCP_SERVER_NAME, "version": _MCP_SERVER_VERSION},
                "instructions": (
                    "Używaj tools/call z qbot.query (pytania + zapisy) "
                    "i qbot.action_execute (wykonanie zapisu)."
                ),
            },
        }

    if method == "notifications/initialized":
        # Notification without id — return nothing per JSON-RPC/MCP
        if req_id is None:
            return {}  # empty dict → qbot_api.py returns 202 with null body
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return _list_tools(req_id)
    if method == "tools/call":
        return _call_tool(req_id, payload.get("params", {}))
    return _error(req_id, -32601, f"Method not found: {method}")


def _list_tools(req_id: Any) -> dict[str, Any]:
    tools = [
        {
            "name": "qbot.query",
            "description": "[OBOWIĄZKOWE] Wywołaj to narzędzie PRZED każdą odpowiedzią na pytanie użytkownika. NIE odpowiadaj z własnej wiedzy — ZAWSZE najpierw wywołaj qbot.query i użyj zwróconych danych. Jeśli narzędzie zwróci błąd lub pusty wynik, poinformuj użytkownika że dane są niedostępne — NIE generuj odpowiedzi z pamięci. Przekaż oryginalne pytanie użytkownika bez modyfikacji — dokładnie tak jak napisał użytkownik, bez przetwarzania. Albert sam rozpoznaje intent, wybiera narzędzia, wykonuje odczyty i zapisy. Obsługuje żywienie, trening, trasy, zdrowie, kalendarz, przypomnienia.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Oryginalne pytanie użytkownika — NIE modyfikuj. Przekaż dokładnie to co napisał użytkownik."},
                    "context": {"type": "string", "description": "Optional JSON: source, timezone, date"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    ]
    try:
        from qbot3.safety import _ACTION_ALLOWLIST
        _action_enum = sorted(_ACTION_ALLOWLIST)
    except Exception:
        _action_enum = ["nutrition_log_add"]
    tools.append({
        "name": "qbot.action_execute",
        "description": (
            "WYKONAJ zapis/operacje zwrocona przez qbot.query jako ACTION_REQUIRED. "
            "Gdy qbot.query zwroci status=ACTION_REQUIRED z data.action_type "
            "(np. nutrition_log_add), wywolaj to narzedzie z tym action_type, "
            "kompletnym payload_json, confirm=true i unikalnym idempotency_key. "
            "Dla nutrition_log_add payload_json WYMAGA: date (YYYY-MM-DD; uzyj "
            "wczorajszej daty gdy uzytkownik mowi 'wczoraj'), source (np. "
            "'chatgpt_mcp'), meal_name (nazwa produktu/posilku), kcal_total; "
            "opcjonalnie protein_g, carbs_g, fat_g. WYMAGA confirm=true."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action_type": {"type": "string", "enum": _action_enum},
                "payload_json": {"type": "object", "description": "Kompletny payload (jak w data/action_draft z qbot.query)."},
                "idempotency_key": {"type": "string", "description": "Unikalny klucz - zapobiega duplikatom."},
                "confirm": {"type": "boolean", "description": "MUSI byc true, zeby zapisac."},
                "dry_run": {"type": "boolean", "default": False, "description": "Tylko walidacja, bez zapisu."},
                "source": {"type": "string", "default": "chatgpt_mcp"},
            },
            "required": ["action_type", "payload_json", "idempotency_key", "confirm"],
            "additionalProperties": False,
        },
    })
    return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}


def _call_tool(req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name", "")
    args = params.get("arguments", {})

    if name == "qbot.query":
        query = str(args.get("query", "")).strip()
        qlen = len(query)
        if not query:
            return _result(req_id, {"error": "empty query"})
        t0 = perf_counter()
        if os.getenv("QBOT_QUERY_VNEXT_ENABLED") == "1":
            try:
                from qbot_query_handler import handle_query
                vnext_result = handle_query(question=query, context=args.get("context"))
                if vnext_result.get("status") == "UNRECOGNIZED":
                    if is_route_domain_query(query):
                        from core.planner import plan_routes
                        try:
                            result = plan_routes(query)
                        except Exception as exc:
                            result = planner_unavailable_response(
                                query,
                                intent="planner_routes",
                                source="qbot.query",
                                fallback_reason=f"planner_error: {exc}",
                            )
                    elif should_use_albert_fallback(query):
                        result = orchestrate_query(query, context=args.get("context", ""))
                        from qbot3.response_normalizer import normalize_response
                        result = normalize_response(result)
                        result["fallback_reason"] = "query_vnext UNRECOGNIZED — fell back to Albert"
                    else:
                        result = planner_unavailable_response(
                            query,
                            intent="unrecognized",
                            source="qbot.query",
                            fallback_reason="QBOT_DISABLE_ALBERT_FALLBACK=1",
                        )
                else:
                    result = vnext_result
            except Exception as exc:
                if is_route_domain_query(query):
                    from core.planner import plan_routes
                    try:
                        result = plan_routes(query)
                    except Exception as planner_exc:
                        result = planner_unavailable_response(
                            query,
                            intent="planner_routes",
                            source="qbot.query",
                            fallback_reason=f"query_vnext error: {exc}; planner_error: {planner_exc}",
                        )
                elif should_use_albert_fallback(query):
                    result = orchestrate_query(query, context=args.get("context", ""))
                    from qbot3.response_normalizer import normalize_response
                    result = normalize_response(result)
                    result["fallback_reason"] = f"query_vnext error: {exc} — fell back to Albert"
                else:
                    result = planner_unavailable_response(
                        query,
                        intent="unrecognized",
                        source="qbot.query",
                        fallback_reason=f"query_vnext error: {exc}",
                    )
        else:
            if is_route_domain_query(query):
                from core.planner import plan_routes
                try:
                    result = plan_routes(query)
                except Exception as exc:
                    result = planner_unavailable_response(
                        query,
                        intent="planner_routes",
                        source="qbot.query",
                        fallback_reason=f"planner_error: {exc}",
                    )
            elif should_use_albert_fallback(query):
                result = orchestrate_query(query, context=args.get("context", ""))
                from qbot3.response_normalizer import normalize_response
                result = normalize_response(result)
            else:
                result = planner_unavailable_response(
                    query,
                    intent="unrecognized",
                    source="qbot.query",
                    fallback_reason="QBOT_DISABLE_ALBERT_FALLBACK=1",
                )
            result["fallback_reason"] = "query_vnext disabled"
        dur_ms = (perf_counter() - t0) * 1000
        _log_query_vnext_metrics(
            engine=str(result.get("engine", "")),
            intent=str(result.get("intent", "") or result.get("tool", "")),
            status=str(result.get("status", "")),
            fallback_reason=result.get("fallback_reason"),
            query_len=qlen,
            sources_count=len(result.get("sources_used", []) or []),
            missing_sources_count=len(result.get("missing_sources", []) or []),
            duration_ms=dur_ms,
        )
        return _result(req_id, result)

    if name == "qbot.action_execute":
        return _handle_action_execute(req_id, args)

    return _error(req_id, -32602, f"Tool not found: {name}")


def _handle_action_execute(req_id: Any, args: dict[str, Any]) -> dict[str, Any]:
    action_type = str(args.get("action_type", "")).strip()
    payload = args.get("payload_json", {})
    idem_key = str(args.get("idempotency_key", "")).strip()
    confirm = args.get("confirm", False)
    dry_run = args.get("dry_run", False)

    if not confirm:
        return _result(req_id, {"tool": "qbot.action_execute", "status": "BLOCKED", "error": "confirm must be true"})

    validation = validate(action_type, payload, idem_key, dry_run=dry_run)
    if validation["status"] != "OK":
        return _result(req_id, {"tool": "qbot.action_execute", **validation})

    if validation.get("dry_run"):
        return _result(req_id, {
            "tool": "qbot.action_execute", "status": "DRY_RUN_OK",
            "execution_mode": "dry_run", "write_committed": False,
            "action_type": action_type, "idempotency_key": idem_key,
            "note": "dry_run — walidacja OK, żaden zapis nie został wykonany",
        })

    # ── Real execute ──────────────────────────────────────────────────
    if action_type == "qbot_doc_append":
        result = exec_doc_append(action_type, payload, idem_key)
        real_write = result.get("status") == "OK"
        return _result(req_id, {
            "tool": "qbot.action_execute",
            "status": "OK" if real_write else result.get("status", "ERROR"),
            "execution_mode": "real_write" if real_write else "error",
            "write_committed": real_write,
            **result,
        })

    # Non-doc write actions — try real writer
    if action_type == "nutrition_log_add":
        write_result = _execute_nutrition_write(action_type, payload, idem_key)
        return _result(req_id, write_result)

    if action_type in ("calendar_event_add", "reminder_add", "memory_confirmed_fact_add"):
        return _result(req_id, {
            "tool": "qbot.action_execute", "status": "WRITE_NOT_AVAILABLE",
            "execution_mode": "mock", "write_committed": False,
            "action_type": action_type, "idempotency_key": idem_key,
            "note": f"{action_type} nie ma jeszcze realnego writera w QBot3. "
                     "Draft został przygotowany, ale wykonanie wymaga implementacji backendu.",
        })

    if action_type == "planning_fact_add":
        return _result(req_id, _execute_planning_fact_add(action_type, payload, idem_key))

    if action_type == "rwgps_route_import_gpx":
        return _result(req_id, _execute_rwgps_import(action_type, payload, idem_key))

    if action_type == "rwgps_route_export_gpx":
        return _result(req_id, _execute_rwgps_route_export_gpx(action_type, payload, idem_key))

    if action_type == "rwgps_route_profile_export_csv":
        return _result(req_id, _execute_rwgps_route_profile_export_csv(action_type, payload, idem_key))

    if action_type == "rwgps_route_surface_analyze":
        return _result(req_id, _execute_rwgps_route_surface_analyze(action_type, payload, idem_key))

    if action_type == "route_poi_analyze":
        return _result(req_id, _execute_route_poi_analyze(action_type, payload, idem_key))

    if action_type == "fit_file_analyze":
        return _result(req_id, _execute_fit_file_analyze(action_type, payload, idem_key))

    if action_type == "qbot_artifact_put":
        return _result(req_id, _execute_qbot_artifact_put(action_type, payload, idem_key))

    if action_type == "qbot_artifact_get":
        return _result(req_id, _execute_qbot_artifact_get(action_type, payload, idem_key))

    return _result(req_id, {
        "tool": "qbot.action_execute", "status": "BLOCKED",
        "execution_mode": "unknown", "write_committed": False,
        "action_type": action_type, "error": f"Unknown action_type: {action_type}",
    })


def _execute_nutrition_write(action_type: str, payload: dict[str, Any], idem_key: str) -> dict[str, Any]:
    """Execute nutrition log write — writes directly to qbot_v2 intake tables."""
    try:
        from qbot_nutrition_db import (
            _conn,
            daily_summary_compute,
            daily_summary_get,
            intake_log_create,
            meal_log_list,
        )
        from datetime import date as dt_date

        meal_name = str(payload.get("meal_name", "")).strip()
        if not meal_name:
            return {"tool": "qbot.action_execute", "status": "BLOCKED",
                    "execution_mode": "error", "write_committed": False,
                    "commit_executed": False,
                    "error": "meal_name is required", "action_type": action_type, "idempotency_key": idem_key}

        target_date = str(payload.get("date", dt_date.today().isoformat()))[:10]
        source = str(payload.get("source", "qbot3")).strip() or "qbot3"
        smoke_test = source == "smoke_test" or bool(payload.get("is_test"))
        quality_status = str(payload.get("quality_status", "manual")).strip() or "manual"
        eaten_at = payload.get("eaten_at") or f"{target_date}T12:00:00+02:00"
        context = json.dumps({
            "origin": "qbot3",
            "action_type": action_type,
            "idempotency_key": idem_key,
            "source": source,
        }, ensure_ascii=False)

        raw_items = payload.get("items", [])
        if raw_items:
            items = []
            for it in raw_items:
                items.append({
                    "food": it.get("meal_name") or it.get("food_name") or meal_name,
                    "food_name": it.get("meal_name") or it.get("food_name") or meal_name,
                    "amount": it.get("amount", 0) or payload.get("amount", 0) or 1,
                    "unit": it.get("unit", "szt"),
                    "kcal": it.get("kcal_total") or it.get("kcal") or payload.get("kcal_total"),
                    "carbs_g": it.get("carbs_g") or payload.get("carbs_g"),
                    "protein_g": it.get("protein_g") or payload.get("protein_g"),
                    "fat_g": it.get("fat_g") or payload.get("fat_g"),
                    "fiber_g": it.get("fiber_g") or payload.get("fiber_g"),
                    "sodium_mg": it.get("salt_g") or payload.get("salt_g"),
                })
        else:
            items = [{
                "food": meal_name,
                "food_name": meal_name,
                "amount": payload.get("amount", 0) or payload.get("quantity", 0) or 1,
                "unit": payload.get("unit", "szt"),
                "kcal": payload.get("kcal_total"),
                "carbs_g": payload.get("carbs_g"),
                "protein_g": payload.get("protein_g"),
                "fat_g": payload.get("fat_g"),
                "fiber_g": payload.get("fiber_g"),
                "sodium_mg": payload.get("salt_g"),
            }]

        before_summary = daily_summary_get(target_date)
        before_kcal = float((before_summary or {}).get("kcal_total", 0) or 0)
        expected_kcal = float(payload.get("kcal_total", 0) or 0)

        result = intake_log_create(
            meal_type="meal",
            note=payload.get("description", ""),
            context=context,
            eaten_at=eaten_at,
            items=items,
            source=source,
            quality_status=quality_status,
        )
        meal_id = result.get("id")
        commit_executed = bool(meal_id)
        if not meal_id:
            return {
                "tool": "qbot.action_execute", "status": "WRITE_ERROR",
                "execution_mode": "error", "write_committed": False,
                "commit_executed": False,
                "action_type": action_type, "idempotency_key": idem_key,
                "error": f"intake_log_create returned: {result}",
            }

        verification_error = None
        after_summary = None
        public_v1_count = 0
        try:
            meals_today = meal_log_list(date_str=target_date, limit=200)
            if not any(m.get("id") == meal_id for m in meals_today):
                verification_error = "nutrition_meal_list did not return the inserted intake row"

            after_summary = daily_summary_compute(target_date)
            after_kcal = float((after_summary or {}).get("kcal_total", 0) or 0)
            if after_kcal < before_kcal + expected_kcal - 0.1:
                verification_error = (
                    f"daily_summary missing inserted kcal: before={before_kcal}, "
                    f"expected_delta={expected_kcal}, after={after_kcal}"
                )

            with _conn() as conn:
                cur = conn.cursor()
                for table in ("meal_logs", "meal_log_items"):
                    cur.execute(
                        "SELECT to_regclass(%s) AS exists_flag",
                        (f"public.{table}",),
                    )
                    exists_flag = cur.fetchone()["exists_flag"]
                    if not exists_flag:
                        continue
                    if table == "meal_logs":
                        cur.execute(
                            """SELECT COUNT(*) AS n
                               FROM public.meal_logs
                               WHERE eaten_at::date = %s
                                 AND COALESCE(context::text, '') ILIKE %s""",
                            (target_date, f"%{idem_key}%"),
                        )
                        public_v1_count += cur.fetchone()["n"]
                    else:
                        cur.execute(
                            """SELECT COUNT(*) AS n
                               FROM public.meal_log_items mli
                               JOIN public.meal_logs ml ON ml.id = mli.meal_log_id
                               WHERE ml.eaten_at::date = %s
                                 AND COALESCE(ml.context::text, '') ILIKE %s""",
                            (target_date, f"%{idem_key}%"),
                        )
                        public_v1_count += cur.fetchone()["n"]
        except Exception as verify_exc:
            verification_error = str(verify_exc)

        cleanup_performed = False
        if smoke_test or verification_error:
            try:
                with _conn() as conn:
                    conn.execute("DELETE FROM qbot_v2.intake_items WHERE intake_log_id=%s", (meal_id,))
                    conn.execute("DELETE FROM qbot_v2.intake_logs WHERE id=%s", (meal_id,))
                    conn.commit()
                daily_summary_compute(target_date)
                cleanup_performed = True
            except Exception as cleanup_exc:
                return {
                    "tool": "qbot.action_execute", "status": "WRITE_ERROR",
                    "execution_mode": "error", "write_committed": False,
                    "commit_executed": commit_executed,
                    "cleanup_performed": cleanup_performed,
                    "action_type": action_type, "idempotency_key": idem_key,
                    "error": f"cleanup failed after write: {cleanup_exc}",
                }

        if verification_error or public_v1_count:
            return {
                "tool": "qbot.action_execute", "status": "WRITE_INCONSISTENT",
                "execution_mode": "smoke_test" if smoke_test else "real_write",
                "write_committed": False,
                "commit_executed": commit_executed,
                "cleanup_performed": cleanup_performed,
                "db_inserted": True,
                "inserted_id": meal_id,
                "action_type": action_type, "idempotency_key": idem_key,
                "meal_log_id": meal_id,
                "storage_backend": "qbot_v2.intake_logs via qbot_nutrition_db.intake_log_create",
                "before_summary": before_summary,
                "after_summary": after_summary,
                "error": verification_error or "public/V1 received a nutrition row",
            }

        return {
            "tool": "qbot.action_execute",
            "status": "OK",
            "execution_mode": "smoke_test" if smoke_test else "real_write",
            "write_committed": not smoke_test,
            "commit_executed": commit_executed,
            "cleanup_performed": cleanup_performed,
            "db_inserted": True,
            "inserted_id": meal_id,
            "action_type": action_type, "idempotency_key": idem_key,
            "meal_log_id": meal_id,
            "storage_backend": "qbot_v2.intake_logs via qbot_nutrition_db.intake_log_create",
            "note": "Posiłek zapisany w qbot_v2.intake_logs",
            "before_summary": before_summary,
            "after_summary": after_summary,
        }

    except Exception as exc:
        return {
            "tool": "qbot.action_execute", "status": "WRITE_ERROR",
            "execution_mode": "error", "write_committed": False,
            "commit_executed": False,
            "action_type": action_type, "idempotency_key": idem_key,
            "error": str(exc)[:500],
        }


def _result(req_id: Any, data: dict) -> dict[str, Any]:
    normalized = json.loads(json.dumps(data, ensure_ascii=False, default=str))
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "content": [{"type": "text", "text": json.dumps(normalized, ensure_ascii=False)}],
            "structuredContent": normalized,
        },
    }


def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _execute_rwgps_import(action_type: str, payload: dict, idem_key: str) -> dict:
    """Import Tuscany 2026 stage do RWGPS jako przycięta kopia kanonicznej trasy.

    Pipeline:
      1. COPY kanonicznej trasy 55256628 → nowa trasa z pełną geometrią
      2. FETCH track_points źródła GET /api/v1/routes/{id}.json?track_points=1
      3. TRIM i NORMALIZUJ d (przelicz cumulative distance, żeby etap zaczynał się od 0)
      4. UPDATE kopii PUT /routes/{id}.json {"route": {"name": ..., "track_points": [...]}}
      5. WALIDUJ: re-fetch i sprawdź distance > 0, track_points > 0

    Uwaga: /api/v1/routes/{id}.json dla PUT/PATCH zwraca 404.
    Działa tylko legacy /routes/{id}.json.
    """
    import logging
    _log = logging.getLogger("rwgps_import")

    try:
        import httpx
        from tools.rwgps.client import (
            import_stage_from_canonical, RWGPSError,
        )
        from qbot3.artifacts.gpx_splitter import DEFAULT_STAGE_SPECS
        route_name_hint = str(
            payload.get("route_name_hint")
            or payload.get("name_hint")
            or payload.get("route_name")
            or ""
        ).strip()
        find_latest = bool(payload.get("find_latest", False))
        publish = bool(payload.get("publish", False))
        project_id = str(payload.get("project_id", "tuscany_2026"))
        source_route_id_raw = payload.get("source_route_id", payload.get("route_id"))
        source_route_id: int | None = None
        resolved_route_name = ""
        resolved_candidates: list[dict[str, Any]] = []

        if source_route_id_raw is not None:
            source_route_id_text = str(source_route_id_raw).strip()
            if source_route_id_text.isdigit():
                source_route_id = int(source_route_id_text)

        if source_route_id is None and route_name_hint:
            from tools.rwgps.route_find import find_routes

            candidates = find_routes(route_name_hint, limit=10)
            resolved_candidates = [item for item in candidates if isinstance(item, dict)]
            if find_latest and resolved_candidates:
                def _updated_ts(item: dict[str, Any]) -> float:
                    raw = str(item.get("updated_at") or "").strip()
                    if not raw:
                        return 0.0
                    try:
                        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt.astimezone(timezone.utc).timestamp()
                    except Exception:
                        return 0.0

                resolved_candidates = sorted(
                    resolved_candidates,
                    key=lambda item: (
                        -int(item.get("score", 0) or 0),
                        -_updated_ts(item),
                        str(item.get("name") or "").lower(),
                    ),
                )
            numeric_candidate = next(
                (
                    item
                    for item in resolved_candidates
                    if str(item.get("route_id") or "").strip().isdigit()
                ),
                None,
            )
            if numeric_candidate:
                source_route_id = int(str(numeric_candidate.get("route_id")).strip())
                resolved_route_name = str(numeric_candidate.get("name") or "").strip()
            else:
                return {
                    "tool": "qbot.action_execute",
                    "status": "PARTIAL",
                    "error": "Nie udało się rozwiązać route_id z route_name_hint.",
                    "resolved_route_id": None,
                    "route_name": None,
                    "route_name_hint": route_name_hint,
                    "candidates": resolved_candidates[:5],
                    "write_committed": False,
                }

        stage_raw = payload.get("stage")
        stage: int | None = None
        if stage_raw not in (None, ""):
            try:
                stage = int(stage_raw)
            except (TypeError, ValueError):
                stage = None

        if source_route_id is not None and stage_raw is None:
            try:
                import hashlib
                import requests

                from qbot3.artifacts.store import register_existing_file, search_artifacts

                route_id_text = str(source_route_id)
                gpx_path = f"/opt/qbot/artifacts/exports/rwgps/rwgps_{route_id_text}.gpx"
                if not os.path.exists(gpx_path) or bool(payload.get("force", False)):
                    api_key = os.getenv("RWGPS_API_KEY", "").strip()
                    auth_token = os.getenv("RWGPS_AUTH_TOKEN", "").strip()
                    r = requests.get(
                        f"https://ridewithgps.com/routes/{route_id_text}.gpx",
                        params={"apikey": api_key, "auth_token": auth_token, "version": "2"},
                        timeout=30,
                    )
                    r.raise_for_status()
                    os.makedirs(os.path.dirname(gpx_path), exist_ok=True)
                    with open(gpx_path, "wb") as fh:
                        fh.write(r.content)

                with open(gpx_path, "rb") as fh:
                    gpx_bytes = fh.read()
                gpx_sha256 = hashlib.sha256(gpx_bytes).hexdigest()
                artifact_filename = f"rwgps_{route_id_text}.gpx"
                artifact_title = resolved_route_name or route_name_hint or f"rwgps_{route_id_text}"

                if bool(payload.get("import_to_artifacts", False)) and not publish:
                    existing = search_artifacts(
                        query=artifact_filename,
                        project_id=project_id,
                        artifact_type="route",
                        status="active",
                        limit=20,
                    )
                    for item in existing:
                        if str(item.get("sha256") or "").strip() == gpx_sha256:
                            item_metadata = item.get("metadata") or item.get("metadata_json") or {}
                            if isinstance(item_metadata, dict):
                                item_metadata = dict(item_metadata)
                                item_metadata.setdefault("stage", None)
                            else:
                                item_metadata = {"stage": None}
                            return {
                                "tool": "qbot.action_execute",
                                "status": "OK",
                                "action_type": action_type,
                                "idempotency_key": idem_key,
                                "execution_mode": "real_write",
                                "write_committed": False,
                                "reused": True,
                                "resolved_route_id": route_id_text,
                                "route_name": artifact_title,
                                "filename": artifact_filename,
                                "source_gpx_path": gpx_path,
                                "artifact_id": item.get("artifact_id"),
                                "artifact_path": item.get("file_path") or item.get("artifact_path"),
                                "artifact_status": item.get("status") or "active",
                                "metadata": item_metadata,
                                "note": "Route resolved by name hint and reused existing RWGPS GPX artifact.",
                            }

                    artifact_abs = f"/opt/qbot/artifacts/exports/rwgps/{artifact_filename}"
                    if not os.path.exists(artifact_abs):
                        os.makedirs(os.path.dirname(artifact_abs), exist_ok=True)
                        with open(artifact_abs, "wb") as fh:
                            fh.write(gpx_bytes)
                    artifact_result = register_existing_file(
                        f"exports/rwgps/{artifact_filename}",
                        artifact_type="route",
                        title=artifact_title,
                        project_id=project_id,
                        mutation_type="import",
                        source="rwgps",
                        idempotency_key=f"rwgps_import:{route_id_text}:{gpx_sha256}",
                        metadata={
                            "rwgps_route_id": int(route_id_text),
                            "route_name": artifact_title,
                            "source_route_id": int(route_id_text),
                            "stage": stage,
                        },
                    )
                    return {
                        "tool": "qbot.action_execute",
                        "status": "OK",
                        "action_type": action_type,
                        "idempotency_key": idem_key,
                        "execution_mode": "real_write",
                        "write_committed": True,
                        "reused": False,
                        "resolved_route_id": route_id_text,
                        "route_name": artifact_title,
                        "filename": artifact_filename,
                        "source_gpx_path": gpx_path,
                        "artifact_id": artifact_result.get("artifact_id"),
                        "artifact_path": artifact_result.get("file_path") or artifact_result.get("artifact_path"),
                        "artifact_status": artifact_result.get("status") or "active",
                        "metadata": artifact_result.get("metadata_json") or {"stage": stage},
                        "note": "Route resolved by name hint and imported as RWGPS GPX artifact.",
                    }

                if not publish:
                    return {
                        "tool": "qbot.action_execute",
                        "status": "PARTIAL",
                        "error": "publish=true jest wymagane do publikacji nowej trasy na RWGPS.",
                        "resolved_route_id": route_id_text,
                        "route_name": artifact_title,
                        "route_name_hint": route_name_hint or None,
                        "source_gpx_path": gpx_path,
                        "write_committed": False,
                    }

                from tools.rwgps.client import create_route_from_gpx as rwgps_create_route

                create_result = rwgps_create_route(
                    gpx_path=gpx_path,
                    name=artifact_title,
                    description=str(payload.get("description", "")).strip(),
                    privacy=str(payload.get("privacy", "private")).strip().lower(),
                )
                if not create_result.get("ok"):
                    return {
                        "tool": "qbot.action_execute",
                        "status": "CREATE_FAILED",
                        "error": create_result.get("error", "Unknown error"),
                        "resolved_route_id": route_id_text,
                        "route_name": artifact_title,
                        "route_name_hint": route_name_hint or None,
                        "write_committed": False,
                    }

                artifact_result = None
                if bool(payload.get("import_to_artifacts", False)) and create_result.get("route_id"):
                    try:
                        from tools.rwgps.client import export_route_to_artifact

                        artifact_result = export_route_to_artifact(create_result.get("route_id"), fmt="gpx")
                    except Exception as exc:
                        artifact_result = {"ok": False, "error": str(exc)}
                    if not isinstance(artifact_result, dict) or not artifact_result.get("artifact_store_id"):
                        try:
                            from qbot3.artifacts.store import register_existing_file

                            artifact_rel = f"exports/rwgps/rwgps_{create_result.get('route_id')}.gpx"
                            artifact_abs = os.path.join("/opt/qbot/artifacts", artifact_rel)
                            os.makedirs(os.path.dirname(artifact_abs), exist_ok=True)
                            if not os.path.exists(artifact_abs):
                                shutil.copyfile(gpx_path, artifact_abs)

                            artifact_result = register_existing_file(
                                artifact_rel,
                                artifact_type="route",
                                title=artifact_title,
                                project_id=project_id,
                                mutation_type="import",
                                source="rwgps",
                                metadata={
                                    "rwgps_route_id": int(route_id_text),
                                    "rwgps_new_route_id": int(str(create_result.get("route_id") or route_id_text)),
                                    "route_name": artifact_title,
                                    "stage": stage,
                                },
                            )
                        except Exception as exc:
                            artifact_result = {"ok": False, "error": str(exc)}

                return {
                    "tool": "qbot.action_execute",
                    "status": "OK",
                    "action_type": action_type,
                    "idempotency_key": idem_key,
                    "execution_mode": "real_write",
                    "write_committed": True,
                    "resolved_route_id": route_id_text,
                    "route_name": artifact_title,
                    "filename": artifact_filename,
                    "new_route_id": create_result.get("route_id"),
                    "html_url": create_result.get("html_url"),
                    "api_url": create_result.get("api_url"),
                    "source_gpx_path": gpx_path,
                    "artifact_id": (artifact_result or {}).get("artifact_store_id") or (artifact_result or {}).get("artifact_id") if isinstance(artifact_result, dict) else None,
                    "artifact_path": (artifact_result or {}).get("artifact_path") if isinstance(artifact_result, dict) else None,
                    "artifact_status": (artifact_result or {}).get("status") if isinstance(artifact_result, dict) else None,
                    "metadata": (artifact_result or {}).get("metadata_json") if isinstance(artifact_result, dict) else None,
                    "note": "Route resolved by name hint and imported from RWGPS GPX.",
                }
            except Exception as exc:
                return {
                    "tool": "qbot.action_execute",
                    "status": "ERROR",
                    "error": str(exc)[:500],
                    "resolved_route_id": route_id_text if 'route_id_text' in locals() else None,
                    "route_name": resolved_route_name or route_name_hint or None,
                    "write_committed": False,
                }

        specs = DEFAULT_STAGE_SPECS.get((project_id, source_route_id), [])
        spec = next((s for s in specs if s.stage == stage), None)
        if not spec:
            return {
                "tool": "qbot.action_execute", "status": "ERROR",
                "error": f"Nie znaleziono StageSpec dla project={project_id}, route={source_route_id}, stage={stage}",
                "write_committed": False,
            }

        gpx_name = payload.get("name") or f"Toskania 2026 7D-B Etap {stage:02d} - {spec.title}"

        result = import_stage_from_canonical(
            str(source_route_id),
            start_km=spec.start_km,
            end_km=spec.end_km,
            name=gpx_name,
        )

        html_url = result["html_url"]
        new_route_id = result["route_id"]
        diagnostics = result.get("diagnostics", [])

        # Logowanie diagnostyczne
        for entry in diagnostics:
            _log.info("STEP %s: %s", entry["step"], entry)

        _log.info("FINAL: route_id=%s distance=%.1fkm track_points=%d html_url=%s",
                  new_route_id, result.get("distance_km") or 0, result.get("track_points_count") or 0, html_url)

        if not result.get("ok") or not result.get("distance_m"):
            return {
                "tool": "qbot.action_execute",
                "status": "IMPORT_FAILED_VALIDATION",
                "error": f"Trasa {new_route_id} ma pustą geometrię (distance={result.get('distance_m')})",
                "new_route_id": new_route_id,
                "html_url": html_url,
                "write_committed": False,
            }

        return {
            "tool": "qbot.action_execute",
            "status": "OK",
            "execution_mode": "real_write",
            "write_committed": True,
            "action_type": action_type,
            "idempotency_key": idem_key,
            "stage": stage,
            "new_route_id": new_route_id,
            "html_url": html_url,
            "name": gpx_name,
            "distance_km": result.get("distance_km"),
            "track_points_count": result.get("track_points_count"),
            "track_points_total": result.get("track_points_total"),
            "track_points_trimmed": result.get("track_points_trimmed"),
            "diagnostics": diagnostics,
        }

    except Exception as exc:
        return {
            "tool": "qbot.action_execute", "status": "ERROR",
            "error": str(exc)[:300], "write_committed": False,
        }


def _execute_rwgps_route_export_gpx(action_type: str, payload: dict, idem_key: str) -> dict:
    """Export an existing RWGPS route as a GPX artifact.

    Uses export_route_to_artifact() which fetches route data from RWGPS,
    builds GPX content, saves to artifacts/exports/rwgps/, and registers
    in qbot_v2.artifacts.  Does NOT mutate the route on RWGPS.
    """
    import logging
    _log = logging.getLogger("rwgps_route_export_gpx")

    try:
        route_id_raw = payload.get("route_id")
        if route_id_raw is None:
            return {"tool": "qbot.action_execute", "status": "ERROR",
                    "write_committed": False,
                    "error": "route_id is required"}
        if isinstance(route_id_raw, str) and not route_id_raw.strip():
            return {"tool": "qbot.action_execute", "status": "ERROR",
                    "write_committed": False,
                    "error": "route_id must not be empty"}

        fmt = str(payload.get("format", "gpx")).strip().lower() or "gpx"
        if fmt != "gpx":
            return {"tool": "qbot.action_execute", "status": "ERROR",
                    "write_committed": False,
                    "error": f"Unsupported format: '{fmt}'. Only 'gpx' is supported."}

        from tools.rwgps.client import export_route_to_artifact

        result = export_route_to_artifact(route_id_raw, fmt="gpx")

        if not isinstance(result, dict):
            return {"tool": "qbot.action_execute", "status": "ERROR",
                    "write_committed": False,
                    "error": f"export_route_to_artifact returned unexpected type: {type(result).__name__}"}

        if result.get("ok") and result.get("status") == "OK":
            return {
                "tool": "qbot.action_execute",
                "status": "OK",
                "write_committed": False,
                "action_type": action_type,
                "idempotency_key": idem_key,
                **result,
            }

        error_msg = result.get("error") or result.get("status", "UNKNOWN")
        return {
            "tool": "qbot.action_execute", "status": "RWGPS_EXPORT_FAILED",
            "write_committed": False,
            "error": error_msg,
            "action_type": action_type,
            "idempotency_key": idem_key,
            **{k: v for k, v in result.items() if k in (
                "route_id", "format", "artifact_path", "filename",
                "point_count", "distance_km", "elevation_gain_m",
            )},
        }

    except Exception as exc:
        _log.error("export_gpx exception: %s", exc)
        return {
            "tool": "qbot.action_execute", "status": "ERROR",
            "error": str(exc)[:500],
            "write_committed": False,
        }


def _execute_rwgps_route_profile_export_csv(action_type: str, payload: dict, idem_key: str) -> dict:
    """Export route elevation profile to CSV/Markdown artifacts."""
    import logging
    _log = logging.getLogger("rwgps_route_profile_export_csv")

    try:
        from tools.rwgps.route_profile_export import export_route_profile_csv

        class _ArtifactStoreAdapter:
            def register(
                self,
                *,
                project_id: str,
                artifact_type: str,
                title: str,
                filename: str,
                file_path: str,
                mime_type: str,
            ) -> dict[str, Any]:
                from qbot3.artifacts.store import register_existing_file

                try:
                    result = register_existing_file(
                        file_path,
                        artifact_type=artifact_type,
                        title=title,
                        project_id=project_id,
                    )
                    if not result or not isinstance(result, dict):
                        _log.error(
                            "artifact register returned empty result for file_path=%s project_id=%s artifact_type=%s",
                            file_path,
                            project_id,
                            artifact_type,
                        )
                        return ""
                    artifact_id = str(result.get("artifact_id", "")).strip()
                    if not artifact_id:
                        _log.error(
                            "artifact register returned no artifact_id for file_path=%s project_id=%s artifact_type=%s result=%r",
                            file_path,
                            project_id,
                            artifact_type,
                            result,
                        )
                    return artifact_id
                except Exception:
                    _log.exception(
                        "artifact register failed for file_path=%s project_id=%s artifact_type=%s",
                        file_path,
                        project_id,
                        artifact_type,
                    )
                    return ""

        meta = export_route_profile_csv(
            route_id=payload["route_id"],
            project_id=payload.get("project_id", "tuscany_2026"),
            km_from=float(payload.get("km_from", 0)),
            km_to=(float(payload["km_to"]) if payload.get("km_to") not in (None, "") else None),
            sample_m=float(payload.get("sample_m", 100)),
            gpx_path=payload.get("artifact_path"),
            artifact_store=_ArtifactStoreAdapter(),
        )

        return {
            "tool": "qbot.action_execute",
            "status": "OK",
            "execution_mode": "real_write",
            "write_committed": True,
            "action_type": action_type,
            "idempotency_key": idem_key,
            **meta,
        }
    except Exception as exc:
        _log.error("route_profile_export_csv exception: %s", exc)
        return {
            "tool": "qbot.action_execute",
            "status": "ERROR",
            "error": str(exc)[:500],
            "write_committed": False,
        }


def _execute_rwgps_route_surface_analyze(action_type: str, payload: dict, idem_key: str) -> dict:
    """Run surface analysis for an RWGPS route via the GI-1A CLI analyzer.

    Deterministic read-only analysis — no PUT to RWGPS, no route mutation.
    """
    import logging
    _log = logging.getLogger("rwgps_route_surface_analyze")

    try:
        route_id_raw = payload.get("route_id")
        if route_id_raw is None:
            return {"tool": "qbot.action_execute", "status": "ERROR",
                    "write_committed": False,
                    "error": "route_id is required"}
        route_id = str(route_id_raw).strip()
        if not route_id:
            return {"tool": "qbot.action_execute", "status": "ERROR",
                    "write_committed": False,
                    "error": "route_id must not be empty"}

        project_id = str(payload.get("project_id", "tuscany_2026")).strip() or "tuscany_2026"

        force_export = bool(payload.get("force_export", False))
        refresh_overpass = bool(payload.get("refresh_overpass", False))

        seg_km_raw = payload.get("segment_km", 10.0)
        try:
            seg_km = max(2.0, min(20.0, float(seg_km_raw)))
        except (TypeError, ValueError):
            seg_km = 10.0

        from scripts.analyze_rwgps_surface import analyze_rwgps_surface_route

        result = analyze_rwgps_surface_route(
            route_id=route_id,
            project_id=project_id,
            force_export=force_export,
            refresh_overpass=refresh_overpass,
            segment_km=seg_km,
        )

        if result.get("ok"):
            return {
                "tool": "qbot.action_execute",
                "status": "OK",
                "action_type": action_type,
                "idempotency_key": idem_key,
                "write_committed": False,
                "route_id": result.get("route_id"),
                "route_name": result.get("route_name"),
                "project_id": result.get("project_id"),
                "gpx_path": result.get("gpx_path"),
                "point_count": result.get("geometry", {}).get("point_count"),
                "distance_km": result.get("geometry", {}).get("distance_km"),
                "elevation_gain_m": result.get("geometry", {}).get("elevation_gain_m"),
                "surface_breakdown": result.get("surface_breakdown"),
                "highway_breakdown": result.get("highway_breakdown"),
                "unknown_percent": result.get("unknown_percent"),
                "json_path": result.get("json_path"),
                "md_path": result.get("md_path"),
                "warnings": result.get("warnings"),
                "duration_s": result.get("duration_s"),
                "recommendation": result.get("recommendation"),
            }

        return {
            "tool": "qbot.action_execute", "status": "SURFACE_ANALYSIS_FAILED",
            "write_committed": False,
            "error": result.get("error", "Unknown error"),
            "action_type": action_type,
            "idempotency_key": idem_key,
            "route_id": route_id,
        }

    except Exception as exc:
        _log.error("surface_analyze exception: %s", exc)
        return {
            "tool": "qbot.action_execute", "status": "ERROR",
            "write_committed": False,
            "error": str(exc)[:500],
        }


def _execute_route_poi_analyze(action_type: str, payload: dict, idem_key: str) -> dict:
    """Run deterministic route POI analysis and persist a report artifact."""
    import logging
    _log = logging.getLogger("route_poi_analyze")

    try:
        from qbot_route_tools import _tool_qbot_route_poi_analyze
        result = _tool_qbot_route_poi_analyze({
            "route_id": payload.get("route_id"),
            "artifact_id": payload.get("artifact_id"),
            "project_id": payload.get("project_id"),
            "path": payload.get("path"),
            "km_from": payload.get("km_from"),
            "km_to": payload.get("km_to"),
            "buffers": payload.get("buffers"),
            "focus": payload.get("focus"),
            "retry_chunk_id": payload.get("retry_chunk_id"),
            "retry_mode": payload.get("retry_mode"),
            "merge_artifact_ids": payload.get("merge_artifact_ids"),
            "timeout_sec": payload.get("timeout_sec"),
            "output_format": payload.get("output_format", "md"),
            "confirm": True,
        })
    except Exception as exc:
        _log.error("route_poi_analyze exception: %s", exc)
        return {
            "tool": "qbot.action_execute",
            "status": "ERROR",
            "write_committed": False,
            "error": str(exc)[:500],
        }

    if result.get("status") in {"OK", "PARTIAL"} and result.get("ok", True):
        return {
            "tool": "qbot.action_execute",
            "status": result.get("status", "OK"),
            "write_committed": True,
            "execution_mode": "partial_write" if result.get("status") == "PARTIAL" else "real_write",
            "action_type": action_type,
            "idempotency_key": idem_key,
            "route_id": result.get("route_id"),
            "artifact_id": result.get("artifact_id"),
            "source_path": result.get("source_path"),
            "report_path": result.get("report_path"),
            "report_artifact_id": result.get("report_artifact_id"),
            "analysis": result.get("analysis"),
            "analysis_status": result.get("status"),
            "warnings": result.get("analysis", {}).get("warnings"),
        }

    return {
        "tool": "qbot.action_execute",
        "status": result.get("status", "ERROR"),
        "write_committed": False,
        "execution_mode": "error",
        "action_type": action_type,
        "idempotency_key": idem_key,
        "error": result.get("error", "route_poi_analyze failed"),
        "payload": payload,
    }


def _execute_fit_file_analyze(action_type: str, payload: dict, idem_key: str) -> dict:
    """Run read-only FIT file analysis through the query handler helper."""
    import logging
    _log = logging.getLogger("fit_file_analyze")

    try:
        from qbot_query_handler import _handle_fit_file_analyze

        query = str(payload.get("query") or payload.get("text") or "").strip()
        params = payload.get("params") if isinstance(payload.get("params"), dict) else None
        result = _handle_fit_file_analyze(query, params)
        return {
            "tool": "qbot.action_execute",
            "status": result.get("status", "OK"),
            "action_type": action_type,
            "idempotency_key": idem_key,
            "execution_mode": "read_only",
            "write_committed": False,
            "answer": result.get("answer"),
            "data": result.get("data"),
            "sources_used": result.get("sources_used", []),
            "warnings": result.get("warnings", []),
        }
    except Exception as exc:
        _log.error("fit_file_analyze exception: %s", exc)
        return {
            "tool": "qbot.action_execute",
            "status": "ERROR",
            "write_committed": False,
            "error": str(exc)[:500],
        }


def _execute_qbot_artifact_put(action_type: str, payload: dict, idem_key: str) -> dict:
    """Save a binary/text artefact file from a ChatGPT session into the project tree.

    Pipeline: validate payload → decode base64 → verify sha256/size →
    atomic write (tmp+rename) → register in qbot_v2.artifacts via
    register_existing_file (avoids double-write / versioning of save_file).
    """
    import base64
    import hashlib
    import json
    import logging
    import os
    import shutil
    import tempfile
    from pathlib import Path

    _log = logging.getLogger("qbot_artifact_put")

    project_id = str(payload.get("project_id", "")).strip()
    # Normalize project aliases
    _pid_lower = project_id.lower().replace(" ", "_").replace("-", "_")
    _PROJECT_ALIASES = {"toskania_2026": "tuscany_2026", "toskania": "tuscany_2026", "toscana": "tuscany_2026"}
    project_id = _PROJECT_ALIASES.get(_pid_lower, project_id)
    _log.info("ENTER filename=%s project=%s subdir=%s b64_len=%s idem=%s",
              payload.get("filename"), project_id,
              payload.get("subdir"), len(str(payload.get("content_base64", ""))),
              idem_key)
    filename = str(payload.get("filename", "")).strip()
    mime_type = str(payload.get("mime_type", "")).strip()
    # Akceptuj content (plain text) i sam koduj do base64
    content_b64 = payload.get("content_base64", "")
    if not content_b64 and payload.get("content"):
        import base64 as _b64
        content_b64 = _b64.b64encode(str(payload["content"]).encode("utf-8")).decode("ascii")
        if not mime_type:
            mime_type = "text/markdown"
    sha256_expected = str(payload.get("sha256", "")).strip()
    overwrite = bool(payload.get("overwrite", False))
    subdir_raw = str(payload.get("subdir", "")).strip()
    description = str(payload.get("description", "")).strip()
    source = str(payload.get("source", "chatgpt_session")).strip()
    artifact_type = str(payload.get("artifact_type", "document")).strip()
    mutation_type = str(payload.get("mutation_type", "generated")).strip()

    # Map to known DB enum values to avoid PG "invalid input value" errors
    _VALID_ARTIFACT_TYPES = frozenset({"route", "poi", "plan", "report", "export", "database", "import", "document"})
    if artifact_type not in _VALID_ARTIFACT_TYPES:
        artifact_type = "document"
    _VALID_MUTATION_TYPES = frozenset({"source", "copy", "split", "merge", "edit", "export", "analysis", "generated", "import"})
    if mutation_type not in _VALID_MUTATION_TYPES:
        mutation_type = "generated"

    # Sanity checks (in addition to safety.validate)
    # Zgadnij mime_type z rozszerzenia jeśli nie podany
    if not mime_type:
        _ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        mime_type = {"md": "text/markdown", "txt": "text/plain",
                     "json": "application/json", "gpx": "application/gpx+xml",
                     "html": "text/html"}.get(_ext, "text/plain")
    if not project_id or not filename or not content_b64:

        return {
            "tool": "qbot.action_execute", "status": "BLOCKED",
            "error": "Missing required fields in payload",
            "write_committed": False,
        }
    if any(c in filename for c in ("/", "\\", "..", "\x00")):
        return {
            "tool": "qbot.action_execute", "status": "BLOCKED",
            "error": f"Path traversal detected in filename: {filename}",
            "write_committed": False,
        }

    # Decode
    try:
        raw = base64.b64decode(content_b64, validate=True)
    except Exception as e:
        return {
            "tool": "qbot.action_execute", "status": "BLOCKED",
            "error": f"base64 decode failed: {e}", "write_committed": False,
        }

    # sha256 verify (if provided)
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if sha256_expected and actual_sha256 != sha256_expected:
        return {
            "tool": "qbot.action_execute", "status": "BLOCKED",
            "error": f"sha256 mismatch: got {actual_sha256[:16]}... expected {sha256_expected[:16]}...",
            "write_committed": False,
        }

    # size_bytes verify (if provided)
    size_provided = payload.get("size_bytes")
    if size_provided is not None and int(size_provided) != len(raw):
        return {
            "tool": "qbot.action_execute", "status": "BLOCKED",
            "error": f"size_bytes mismatch: got {len(raw)}, expected {int(size_provided)}",
            "write_committed": False,
        }

    # Build path — shelf routing
    artifacts_root = Path("/opt/qbot/artifacts")
    VALID_SHELVES = {"wip", "export", "canonical"}
    shelf_raw = str(payload.get("shelf", "")).strip().lower()
    shelf = shelf_raw if shelf_raw in VALID_SHELVES else "wip"

    # canonical i export wymagaja confirm=true
    if shelf in ("canonical", "export") and not bool(payload.get("confirm", False)):
        return {
            "tool": "qbot.action_execute", "status": "BLOCKED",
            "error": (
                f"Zapis do shelf='{shelf}' wymaga jawnego confirm=true w payloadzie. "
                "Dodaj confirm: true i ponow."
            ),
            "write_committed": False,
            "shelf": shelf,
        }

    subdir = subdir_raw.strip("/") if subdir_raw else "files"
    if any(c in subdir for c in ("/", "\\", "..", "\x00")):
        subdir = "files"
    _eff_sub = subdir if (subdir and subdir != shelf) else "files"
    rel_dir = f"{shelf}/{project_id}/{_eff_sub}"
    abs_dir = (artifacts_root / rel_dir).resolve()
    root = artifacts_root.resolve()
    if not str(abs_dir).startswith(str(root)):
        return {
            "tool": "qbot.action_execute", "status": "BLOCKED",
            "error": f"path traversal: {abs_dir}", "write_committed": False,
        }
    abs_dir.mkdir(parents=True, exist_ok=True)
    abs_path = abs_dir / filename
    relative_path = f"{rel_dir}/{filename}"

    # Overwrite check
    if abs_path.exists() and not overwrite:
        return {
            "tool": "qbot.action_execute", "status": "CONFLICT",
            "error": f"File already exists: {abs_path}",
            "artifact_path": str(abs_path), "write_committed": False,
        }

    # Atomic write: tmp + rename
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(abs_dir), suffix=".tmp")
        os.write(fd, raw)
        os.close(fd)
        shutil.move(tmp_path, str(abs_path))
        tmp_path = None
    except Exception as e:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        return {
            "tool": "qbot.action_execute", "status": "WRITE_ERROR",
            "error": f"write failed: {e}", "write_committed": False,
        }

    size_bytes = len(raw)

    # ── Register in qbot_v2.artifacts via register_existing_file ──
    # We use register_existing_file (not save_file) because the file is
    # already written atomically above.  save_file would try to re-write
    # with a versioned path and cause a double-write.
    artifact_id = None
    db_ok = False
    db_error = None
    try:
        from qbot3.artifacts.store import register_existing_file
        meta = {"description": description, "source": source, "subdir": subdir}
        db_result = register_existing_file(
            relative_path,
            artifact_type=artifact_type,
            title=description or filename,
            project_id=project_id,
            mutation_type=mutation_type,
            source=source,
            idempotency_key=idem_key,
            metadata=meta,
        )
        if db_result:
            artifact_id = str(db_result.get("artifact_id", ""))
            db_ok = True
    except Exception as e:
        db_error = str(e)[:300]
        _log.warning("DB register failed for %s: %s", relative_path, db_error)

    result = {
        "tool": "qbot.action_execute",
        "status": "OK",
        "write_committed": True,
        "action_type": action_type,
        "idempotency_key": idem_key,
        "artifact_id": artifact_id or "",
        "project_id": project_id,
        "filename": filename,
        "artifact_path": str(abs_path),
        "relative_path": relative_path,
        "shelf": shelf,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "sha256": actual_sha256,
        "db_registered": db_ok,
    }
    if db_error:
        result["db_warning"] = db_error

    _log.info("OK file=%s path=%s size=%d sha256=%s db=%s err=%s",
              filename, relative_path, size_bytes, actual_sha256, db_ok, db_error or "")
    return result


def _execute_qbot_artifact_get(action_type: str, payload: dict, idem_key: str) -> dict:
    """Read-only artifact content retrieval.

    Resolves identifier (artifact_id UUID, filename, title, or full path)
    against qbot_v2.artifacts, then reads file content from the allowlisted
    filesystem.  No DB writes, no side effects.
    """
    identifier = str(payload.get("identifier") or payload.get("path") or payload.get("artifact_id", "")).strip()
    if not identifier:
        return {
            "tool": "qbot.action_execute", "status": "BLOCKED",
            "write_committed": False,
            "error": "identifier is required",
        }

    start_line = int(payload.get("start_line", 1))
    max_lines = int(payload.get("max_lines", 200))

    try:
        from qbot3.artifacts.store import read_artifact_content
        result = read_artifact_content(
            identifier=identifier,
            start_line=start_line,
            max_lines=max_lines,
            max_bytes=65536,
        )
    except ImportError:
        return {
            "tool": "qbot.action_execute", "status": "ERROR",
            "write_committed": False,
            "error": "artifact store module not available",
        }
    except Exception as exc:
        return {
            "tool": "qbot.action_execute", "status": "ERROR",
            "write_committed": False,
            "error": str(exc)[:500],
        }

    if not result.get("ok"):
        return {
            "tool": "qbot.action_execute",
            "status": result.get("status", "ERROR"),
            "write_committed": False,
            "identifier": identifier,
            "error": result.get("error", "unknown error"),
            **({k: result[k] for k in ("artifact_id", "path", "size_bytes") if k in result}),
        }

    truncated = result.get("truncated", False)
    note = None
    if truncated:
        note = "Tre\u015b\u0107 przyci\u0119ta do 65536 bajt\u00f3w / 200 linii."

    return {
        "tool": "qbot.action_execute",
        "status": "OK",
        "write_committed": False,
        "action_type": action_type,
        "artifact_id": result.get("artifact_id"),
        "filename": result.get("filename"),
        "title": result.get("title"),
        "artifact_type": result.get("artifact_type"),
        "project_id": result.get("project_id"),
        "path": result.get("path"),
        "size_bytes": result.get("size_bytes"),
        "line_count": result.get("line_count"),
        "start_line": result.get("start_line"),
        "end_line": result.get("end_line"),
        "content": result.get("content"),
        "truncated": truncated,
        "note": note,
    }


def _execute_planning_fact_add(action_type: str, payload: dict, idem_key: str) -> dict:
    """Save a planning fact via qbot_planning_memory.save_planning_fact.

    Przekazuje payload jako draft, ustawia confirm=True.
    """
    import logging
    _log = logging.getLogger("planning_fact_add")
    _log.info("ENTER title=%s fact_type=%s date=%s idem=%s",
              payload.get("title"), payload.get("fact_type"), payload.get("date"), idem_key)

    try:
        from qbot_planning_memory import save_planning_fact
        source = str(payload.get("source", "qbot3")).strip() or "qbot3"
        result = save_planning_fact(draft=payload, channel=source, confirm=True)

        if result.get("status") == "OK":
            _log.info("OK id=%s title=%s", result.get("planning_fact_id"), payload.get("title"))
            return {
                "tool": "qbot.action_execute",
                "status": "OK",
                "write_committed": True,
                "action_type": action_type,
                "idempotency_key": idem_key,
                "planning_fact_id": result.get("planning_fact_id"),
            }
        error = result.get("error", "save_planning_fact failed")
        _log.warning("FAIL: %s", error)
        return {
            "tool": "qbot.action_execute", "status": "ERROR",
            "write_committed": False, "error": error,
        }
    except ImportError:
        _log.warning("qbot_planning_memory not available")
        return {
            "tool": "qbot.action_execute", "status": "MISSING_CAPABILITY",
            "write_committed": False,
            "missing_capability": "planning_fact_add",
            "note": "save_planning_fact not available.",
        }
    except Exception as exc:
        _log.error("EXCEPTION: %s", exc)
        return {
            "tool": "qbot.action_execute", "status": "ERROR",
            "write_committed": False,
            "error": str(exc)[:300],
        }
