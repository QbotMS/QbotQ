"""Qbot LLM Planner — rule-fallback planner, policy engine, plan executor."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


# ──────────── Safety metadata per tool ───────────────────────────────────

def _tool_safety(tool_name: str) -> dict[str, Any]:
    from qbot_tool_registry import TOOLS_META
    meta = TOOLS_META.get(tool_name, {})
    default = {
        "safety_class": "READ_ONLY",
        "requires_approval": False,
        "allowed_auto_execute": True,
        "allowed_in_llm_plan": True,
        "description_for_planner": meta.get("description", ""),
        "args_schema": meta.get("args_schema", {}),
        "risk_notes": None,
    }
    # Override for known WRITE_SAFE tools
    write_safe = {"qbot_artifact_create"}
    controlled = set()
    if tool_name in write_safe:
        default["safety_class"] = "WRITE_SAFE"
        default["allowed_auto_execute"] = True
        default["allowed_in_llm_plan"] = True
    if tool_name in controlled:
        default["safety_class"] = "CONTROLLED_ACTION"
        default["requires_approval"] = True
        default["allowed_auto_execute"] = False
    return default


# ──────────── qbot_tool_policy_list ─────────────────────────────────────

def _tool_qbot_tool_policy_list(_args: dict | None = None) -> dict[str, Any]:
    from qbot_tool_registry import TOOLS_META
    items = []
    for name, meta in sorted(TOOLS_META.items()):
        safety = _tool_safety(name)
        items.append({
            "name": name,
            "safety_class": safety["safety_class"],
            "allowed_auto_execute": safety["allowed_auto_execute"],
            "requires_approval": safety["requires_approval"],
            "allowed_in_llm_plan": safety["allowed_in_llm_plan"],
            "args_schema": safety["args_schema"],
            "description_for_planner": safety["description_for_planner"],
        })
    return {"tool": "qbot_tool_policy_list", "tools": items, "count": len(items)}


# ──────────── qbot_llm_plan_query ───────────────────────────────────────

def _fallback_planner(query: str) -> dict[str, Any]:
    """Rule-based fallback planner — uses existing qbot_query logic."""
    from qbot_query_processor import process_query
    result = process_query(query, execute=False)
    tools = []
    for t in result.get("planned_tools", []):
        safety = _tool_safety(t)
        if safety["allowed_in_llm_plan"]:
            tools.append({
                "tool": t,
                "args": safety["args_schema"],
                "reason": f"matched keyword intent: {result.get('intent', 'unknown')}",
                "expected_output": safety["description_for_planner"],
            })
    if not tools and result.get("selected_tool"):
        t = result["selected_tool"]
        safety = _tool_safety(t)
        tools.append({
            "tool": t,
            "args": safety["args_schema"],
            "reason": f"matched keyword intent: {result.get('intent', 'unknown')}",
            "expected_output": safety["description_for_planner"],
        })
    return {
        "intent": f"fallback:{result.get('intent', 'unknown')}",
        "steps": tools,
        "answer_goal": f"Provide diagnostic information about: {query}",
        "risk_assessment": "low",
    }


def _tool_qbot_llm_plan_query(args: dict | None = None) -> dict[str, Any]:
    query = (args or {}).get("query", "")
    if not query or not query.strip():
        return {"tool": "qbot_llm_plan_query", "status": "error", "error": "empty query"}

    # Fallback planner — no real LLM
    plan = _fallback_planner(query)
    validation = _validate_plan_internal(plan)

    plan_id = None
    try:
        import api_db
        import psycopg
        from psycopg.rows import dict_row
        import os
        conn = psycopg.connect(
            host=os.getenv("PGHOST", "localhost"), port=os.getenv("PGPORT", "5432"),
            dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
            password=os.getenv("PGPASSWORD", ""), row_factory=dict_row,
        )
        row = conn.execute(
            """INSERT INTO qbot_plans (user_query, planner_source, proposed_plan, validated_plan,
               policy_status, requires_approval, blocked_reasons)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (query, "rule_fallback", json.dumps(plan), json.dumps(validation),
             validation["policy_status"], validation.get("requires_approval", False),
             json.dumps(validation.get("blocked_reasons", []))),
        ).fetchone()
        conn.commit()
        conn.close()
        plan_id = row["id"] if row else None
    except Exception:
        pass

    return {
        "tool": "qbot_llm_plan_query",
        "user_query": query,
        "planner_used": "rule_fallback",
        "proposed_plan": plan,
        "validation": validation,
        "policy_status": validation["policy_status"],
        "requires_approval": validation.get("requires_approval", False),
        "blocked_reasons": validation.get("blocked_reasons", []),
        "plan_id": plan_id,
    }


# ──────────── Internal validation ───────────────────────────────────────

def _validate_plan_internal(plan: dict[str, Any]) -> dict[str, Any]:
    from qbot_tool_registry import TOOLS
    approved: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    require_approval: list[dict[str, Any]] = []
    reasons: list[str] = []
    has_approval_step = False

    for step in plan.get("steps", []):
        tool = step.get("tool", "")
        if not tool or tool not in TOOLS:
            blocked.append({**step, "reason": f"unknown tool: {tool}"})
            reasons.append(f"Blocked: unknown tool {tool}")
            continue
        safety = _tool_safety(tool)
        if safety["safety_class"] == "CONTROLLED_ACTION":
            require_approval.append({**step, "reason": "CONTROLLED_ACTION requires approval"})
            has_approval_step = True
        elif safety["safety_class"] in ("READ_ONLY", "WRITE_SAFE") and safety["allowed_in_llm_plan"]:
            approved.append({**step, "safety_class": safety["safety_class"]})
        else:
            blocked.append({**step, "reason": f"safety class {safety['safety_class']} not allowed"})
            reasons.append(f"Blocked: {tool} safety class {safety['safety_class']}")

    if blocked:
        policy = "BLOCKED"
    elif has_approval_step:
        policy = "REQUIRES_APPROVAL"
    else:
        policy = "APPROVED_READ_ONLY"

    return {
        "approved_steps": [s["tool"] for s in approved],
        "blocked_steps": [s["tool"] for s in blocked],
        "requires_approval_steps": [s["tool"] for s in require_approval],
        "policy_status": policy,
        "requires_approval": has_approval_step or False,
        "reasons": reasons,
    }


# ──────────── qbot_policy_validate_plan ─────────────────────────────────

def _tool_qbot_policy_validate_plan(args: dict | None = None) -> dict[str, Any]:
    plan = (args or {}).get("plan", {})
    if not plan or not isinstance(plan, dict):
        return {"tool": "qbot_policy_validate_plan", "status": "error", "error": "invalid plan format"}
    validation = _validate_plan_internal(plan)
    validation["tool"] = "qbot_policy_validate_plan"
    return validation


# ──────────── qbot_execute_validated_plan ────────────────────────────────

def _tool_qbot_execute_validated_plan(args: dict | None = None) -> dict[str, Any]:
    from qbot_tool_registry import TOOLS
    plan_id_raw = (args or {}).get("plan_id", 0)
    execute = (args or {}).get("execute", False) is True
    approval = (args or {}).get("approval", False) is True

    try:
        plan_id = int(plan_id_raw)
    except (ValueError, TypeError):
        return {"tool": "qbot_execute_validated_plan", "status": "error", "error": f"invalid plan_id: {plan_id_raw}"}

    plan_data = None
    try:
        import psycopg
        from psycopg.rows import dict_row
        import os
        conn = psycopg.connect(
            host=os.getenv("PGHOST", "localhost"), port=os.getenv("PGPORT", "5432"),
            dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
            password=os.getenv("PGPASSWORD", ""), row_factory=dict_row,
        )
        row = conn.execute("SELECT * FROM qbot_plans WHERE id = %s", (plan_id,)).fetchone()
        conn.close()
        if row:
            plan_data = dict(row)
            if isinstance(plan_data.get("proposed_plan"), str):
                plan_data["proposed_plan"] = json.loads(plan_data["proposed_plan"])
            if isinstance(plan_data.get("validated_plan"), str):
                plan_data["validated_plan"] = json.loads(plan_data["validated_plan"])
    except Exception as exc:
        return {"tool": "qbot_execute_validated_plan", "status": "error", "error": f"plan fetch failed: {exc}"}

    if not plan_data:
        return {"tool": "qbot_execute_validated_plan", "status": "error", "error": f"plan {plan_id} not found"}

    policy = plan_data.get("policy_status", "BLOCKED")
    if policy == "BLOCKED":
        return {"tool": "qbot_execute_validated_plan", "plan_id": plan_id, "execution_status": "BLOCKED",
                "executed_steps": [], "skipped_steps": [], "blocked_steps": [],
                "tool_results": {}, "reason": "Plan is BLOCKED by policy"}

    proposed = plan_data.get("proposed_plan", {})
    if isinstance(proposed, str):
        try:
            proposed = json.loads(proposed)
        except Exception:
            proposed = {}
    steps = proposed.get("steps", [])

    if not execute:
        return {
            "tool": "qbot_execute_validated_plan",
            "plan_id": plan_id,
            "execution_status": "PREVIEW",
            "planned_steps": [s.get("tool") for s in steps],
            "executed_steps": [],
            "skipped_steps": [],
            "blocked_steps": [],
            "tool_results": {},
        }

    executed: list[str] = []
    skipped: list[str] = []
    blocked_steps: list[str] = []
    results: dict[str, Any] = {}

    for step in steps:
        tool = step.get("tool", "")
        safety = _tool_safety(tool)
        if safety["safety_class"] == "CONTROLLED_ACTION" and not approval:
            skipped.append(tool)
            continue
        if tool not in TOOLS:
            blocked_steps.append(tool)
            continue
        try:
            step_args = step.get("args", {}) if isinstance(step.get("args"), dict) else {}
            results[tool] = TOOLS[tool](step_args)
            executed.append(tool)
        except Exception as exc:
            results[tool] = {"error": str(exc)}
            executed.append(tool)

    exec_status = "COMPLETED" if not blocked_steps else "PARTIAL"

    # Update plan in DB
    try:
        import psycopg
        from psycopg.rows import dict_row
        import os
        conn = psycopg.connect(
            host=os.getenv("PGHOST", "localhost"), port=os.getenv("PGPORT", "5432"),
            dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
            password=os.getenv("PGPASSWORD", ""), row_factory=dict_row,
        )
        conn.execute(
            "UPDATE qbot_plans SET execution_status=%s, executed_at=now(), tool_results=%s WHERE id=%s",
            (exec_status, json.dumps(results), plan_id),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    return {
        "tool": "qbot_execute_validated_plan",
        "plan_id": plan_id,
        "execution_status": exec_status,
        "executed_steps": executed,
        "skipped_steps": skipped,
        "blocked_steps": blocked_steps,
        "tool_results": results,
    }


# ──────────── qbot_llm_provider_status ──────────────────────────────────

def _tool_qbot_llm_provider_status(_args: dict | None = None) -> dict[str, Any]:
    has_key = False
    provider = "none"
    try:
        import os
        has_key = bool(os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
        if os.getenv("DEEPSEEK_API_KEY"):
            provider = "deepseek"
        elif os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        elif os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"
    except Exception:
        pass
    return {
        "tool": "qbot_llm_provider_status",
        "provider_detected": provider if has_key else "none",
        "real_llm_available": has_key,
        "current_planner_mode": "rule_fallback",
        "synthesizer_available": has_key,
        "status": "WARN" if not has_key else "OK",
        "note": "No API keys exposed. Planner uses rule fallback. Add DEEPSEEK_API_KEY env for real LLM planning." if not has_key else f"Provider {provider} detected",
    }


# ──────────── LLM run query (full pipeline) ────────────────────────────

def _tool_qbot_llm_run_query(args: dict | None = None) -> dict[str, Any]:
    query = (args or {}).get("query", "")
    execute = (args or {}).get("execute", False) is True
    if not query.strip():
        return {"tool": "qbot_llm_run_query", "status": "error", "error": "empty query"}

    plan_result = _tool_qbot_llm_plan_query({"query": query})
    plan_id = plan_result.get("plan_id")
    policy_status = plan_result.get("policy_status", "UNKNOWN")
    proposed = plan_result.get("proposed_plan", {})
    steps = proposed.get("steps", [])

    if not execute:
        return {
            "tool": "qbot_llm_run_query",
            "query": query,
            "plan_id": plan_id,
            "planner_used": "rule_fallback",
            "policy_status": policy_status,
            "execution_status": "PREVIEW",
            "planned_steps": [s["tool"] for s in steps],
            "answer": None,
            "tool_results_summary": None,
            "safety_boundary": "LLM proposes, Qbot validates. No auto-execution.",
        }

    if policy_status == "BLOCKED":
        return {
            "tool": "qbot_llm_run_query",
            "query": query, "plan_id": plan_id,
            "planner_used": "rule_fallback",
            "policy_status": policy_status,
            "execution_status": "BLOCKED",
            "answer": None,
            "tool_results_summary": {"reason": plan_result.get("blocked_reasons", [])},
            "safety_boundary": "Plan blocked by policy validation",
        }

    if plan_id:
        exec_result = _tool_qbot_execute_validated_plan({"plan_id": plan_id, "execute": True})
    else:
        exec_result = {"executed_steps": [], "tool_results": {}, "execution_status": "SKIPPED"}

    tool_results = exec_result.get("tool_results", {})
    summary = {}
    for k, v in tool_results.items():
        if isinstance(v, dict):
            summary[k] = v.get("status", "N/A")

    return {
        "tool": "qbot_llm_run_query",
        "query": query,
        "plan_id": plan_id,
        "planner_used": "rule_fallback",
        "policy_status": policy_status,
        "execution_status": exec_result.get("execution_status", "UNKNOWN"),
        "answer": f"Fallback summary: executed {len(exec_result.get('executed_steps', []))} tools. Results: {json.dumps(summary)}",
        "tool_results_summary": summary,
        "safety_boundary": "LLM proposes, Qbot validates. Rule fallback planner used (no LLM API key configured).",
    }
