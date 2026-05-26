"""Qbot External LLM mode — ChatGPT Plus external session integration."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from qgpt_client import qgpt_json
from qbot_config import QGPT_API_KEY, QGPT_BASE_URL

_SENSITIVE: set[str] = {"password", "secret", "token", "apikey", "api_key", "pgpassword", "env", "credential", "auth"}
_ALLOWED_TOPICS: set[str] = {"operational_status", "legacy_takeover", "llm_planner", "backup_restore", "project_status", "error_review", "full_status"}
_ALLOWED_STYLES: set[str] = {"concise", "detailed", "operator", "decision_memo"}


def _sanitize(obj: Any, depth: int = 0) -> Any:
    if depth > 3:
        return "<truncated>"
    if isinstance(obj, dict):
        r: dict[str, Any] = {}
        for k, v in obj.items():
            if any(s in str(k).lower() for s in _SENSITIVE):
                r[k] = "<redacted>"
            elif isinstance(v, (dict, list)):
                r[k] = _sanitize(v, depth + 1)
            elif isinstance(v, str) and len(v) > 2000:
                r[k] = v[:2000] + "...<truncated>"
            else:
                r[k] = v
        return r
    if isinstance(obj, list):
        return [_sanitize(v, depth + 1) if isinstance(v, (dict, list)) else v[:500] + "...<truncated>" if isinstance(v, str) and len(v) > 500 else v for v in obj[:50]]
    return obj[:2000] + "...<truncated>" if isinstance(obj, str) and len(obj) > 2000 else obj


def _tool_policy_index() -> list[dict[str, Any]]:
    from qbot_llm_planner import _tool_qbot_tool_policy_list

    result = _tool_qbot_tool_policy_list({})
    items = result.get("tools", []) if isinstance(result, dict) else []
    return [item for item in items if isinstance(item, dict) and item.get("allowed_in_llm_plan", True)]


def _tool_specs_for_query(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    query_l = (query or "").lower()
    tokens = [tok for tok in re.findall(r"[a-z0-9_ąćęłńóśźż-]+", query_l) if len(tok) >= 3]
    tokens = list(dict.fromkeys(tokens))[:12]
    policy = _tool_policy_index()

    def score(item: dict[str, Any]) -> int:
        hay = " ".join(
            str(item.get(k, "")) for k in (
                "name",
                "description_for_planner",
                "safety_class",
            )
        ).lower()
        total = 0
        for token in tokens:
            if token in hay:
                total += max(1, len(token))
        return total

    ranked = sorted(policy, key=score, reverse=True)
    picked = [item for item in ranked if score(item) > 0][:limit]
    if not picked:
        picked = ranked[:limit]
    return picked


def _openai_compatible_planning_enabled() -> bool:
    return bool(QGPT_API_KEY) or QGPT_BASE_URL.startswith(("http://localhost", "http://127.0.0.1"))


def _fallback_tool_plan(query: str, *, max_tools: int = 3) -> dict[str, Any]:
    from qbot_query_processor import process_query

    preview = process_query(query, execute=False)
    planned = preview.get("planned_tools", []) if isinstance(preview, dict) else []
    selected = preview.get("selected_tool") if isinstance(preview, dict) else None
    tool_names: list[str] = []
    if isinstance(selected, str) and selected:
        tool_names.append(selected)
    for tool_name in planned:
        if isinstance(tool_name, str) and tool_name not in tool_names:
            tool_names.append(tool_name)
    tool_names = tool_names[:max_tools]

    policy = {item.get("name"): item for item in _tool_policy_index()}
    recommended = []
    for tool_name in tool_names:
        meta = policy.get(tool_name)
        if not meta:
            continue
        recommended.append({
            "tool": tool_name,
            "args": meta.get("args_schema", {}) or {},
            "reason": f"rule fallback matched intent: {preview.get('intent', 'unknown')}",
            "confidence": preview.get("confidence", "medium"),
        })

    return {
        "planner_source": "rule_fallback",
        "query": query,
        "recommended_tools": recommended,
        "ask_for_more_context": preview.get("intent") == "unknown_intent",
        "context_questions": preview.get("available_examples", [])[:3] if preview.get("intent") == "unknown_intent" else [],
        "notes": "Fallback planner used because no API-backed LLM plan was available.",
        "preview": preview,
    }


# ──────────── qbot_external_llm_status ──────────────────────────────────

def _tool_qbot_external_llm_status(_args: dict | None = None) -> dict[str, Any]:
    import os
    has_key = bool(os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
    return {
        "tool": "qbot_external_llm_status",
        "external_llm_mode_enabled": True,
        "primary_model_mode": "ChatGPT Plus external, no API",
        "api_llm_enabled": has_key,
        "api_llm_default": "disabled_by_default",
        "deepseek_primary": False,
        "opencode_deepseek_role": "code executor/dev assistant",
        "qbot_policy_engine_active": True,
        "status": "OK",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ──────────── qbot_external_llm_policy ──────────────────────────────────

def _tool_qbot_external_llm_policy(_args: dict | None = None) -> dict[str, Any]:
    return {
        "tool": "qbot_external_llm_policy",
        "primary_reasoning_model": "OpenAI ChatGPT Plus external session",
        "api_llm_provider": "disabled_by_default",
        "dev_code_model": "DeepSeek via OpenCode Go",
        "qbot_role": [
            "source_of_truth",
            "policy_engine",
            "tool_executor",
            "audit_log",
            "artifact_store",
        ],
        "chatgpt_role": [
            "main_reasoning",
            "answer_synthesis",
            "planning_assistance",
            "prompt_authoring",
        ],
        "deepseek_role": [
            "code_implementation",
            "tests",
            "static_analysis",
            "refactor_assistance",
        ],
        "forbidden": [
            "secrets in prompts",
            "direct API key exposure",
            "LLM executing tools without Qbot policy",
            "arbitrary shell",
            "arbitrary SQL",
        ],
        "status": "OK",
    }


# ──────────── qbot_external_context_bundle ──────────────────────────────

_TOPIC_TOOLS: dict[str, list[str]] = {
    "operational_status": ["qbot_operator_final_smoke_test", "qbot_readiness_report", "qbot_maintenance_report"],
    "legacy_takeover": ["qbot_legacy_takeover_status", "qbot_legacy_cutover_status"],
    "llm_planner": ["qbot_tool_policy_list", "qbot_llm_boundary_policy"],
    "backup_restore": ["qbot_backup_status", "qbot_backup_timer_status", "qbot_restore_drill_status"],
    "project_status": ["qbot_git_status", "qbot_project_guard_check", "qbot_project_diff_summary"],
    "error_review": ["qbot_error_summary", "qbot_test_error_classification", "qbot_recent_tool_calls"],
    "full_status": ["qbot_operator_final_smoke_test", "qbot_readiness_report", "qbot_backup_status", "qbot_git_status"],
}


def _tool_qbot_external_context_bundle(args: dict | None = None) -> dict[str, Any]:
    topic = str((args or {}).get("topic", "operational_status"))
    include_recent = bool((args or {}).get("include_recent_calls", True))
    include_policy = bool((args or {}).get("include_policy", True))
    include_artifacts = bool((args or {}).get("include_artifacts", False))
    max_chars = int((args or {}).get("max_chars", 12000))
    max_chars = max(2000, min(50000, max_chars))

    if topic not in _ALLOWED_TOPICS:
        return {
            "tool": "qbot_external_context_bundle", "status": "error",
            "error": f"unknown topic: {topic!r}", "allowed": sorted(_ALLOWED_TOPICS),
        }

    from qbot_tool_registry import TOOLS
    tools_to_call = _TOPIC_TOOLS.get(topic, [])
    if include_recent and "qbot_recent_tool_calls" not in tools_to_call:
        tools_to_call.append("qbot_recent_tool_calls")
    if include_policy:
        tools_to_call.extend(["qbot_external_llm_policy", "qbot_llm_boundary_policy"])

    results: dict[str, Any] = {}
    sources: list[str] = []
    for t in tools_to_call:
        func = TOOLS.get(t)
        if not func:
            continue
        try:
            results[t] = func({})
            sources.append(t)
        except Exception as exc:
            results[t] = {"error": str(exc)}

    sanitized = _sanitize(results)
    context_str = json.dumps(sanitized, ensure_ascii=False)
    omitted: list[str] = []
    if len(context_str) > max_chars:
        context_str = context_str[:max_chars] + "...<truncated>"
        omitted.append(f"truncated from {len(json.dumps(sanitized, ensure_ascii=False))} to {max_chars} chars")

    return {
        "tool": "qbot_external_context_bundle",
        "topic": topic,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "safe_for_chatgpt": True,
        "context": json.loads(context_str) if context_str else {},
        "included_sources": sources,
        "omitted_due_to_size": omitted,
        "max_chars": max_chars,
        "status": "OK",
    }


# ──────────── qbot_external_tool_plan ──────────────────────────────────

def _tool_qbot_external_tool_plan(args: dict | None = None) -> dict[str, Any]:
    query = str((args or {}).get("query", "")).strip()
    style = str((args or {}).get("style", "concise"))
    max_tools = int((args or {}).get("max_tools", 3))
    max_tools = max(1, min(5, max_tools))
    include_prompt = bool((args or {}).get("include_prompt", True))
    if style not in _ALLOWED_STYLES:
        return {
            "tool": "qbot_external_tool_plan",
            "status": "error",
            "error": f"unknown style: {style!r}",
            "allowed": sorted(_ALLOWED_STYLES),
        }
    if not query:
        return {
            "tool": "qbot_external_tool_plan",
            "status": "error",
            "error": "query required",
        }
    if not _openai_compatible_planning_enabled():
        return {
            "tool": "qbot_external_tool_plan",
            "status": "error",
            "error": "OpenAI-compatible planning is required for this path",
            "planner_source": "unavailable",
            "note": "Set QGPT_API_KEY or use a local OpenAI-compatible base URL before using this path.",
        }

    candidates = _tool_specs_for_query(query, limit=10)
    policy_index = {item.get("name"): item for item in _tool_policy_index()}
    candidate_names = [str(item.get("name")) for item in candidates if item.get("name")]

    style_notes = {
        "concise": "Prefer the smallest sufficient tool plan. Return at most 3 tools.",
        "detailed": "You may return a multi-step plan, but keep it minimal and ordered.",
        "operator": "Focus on concrete next actions. Prefer diagnostics before reports.",
        "decision_memo": "Explain the recommendation as if preparing a decision memo.",
    }

    system = (
        "You are QBot's internal tool planner. "
        "Your job is to choose the best QBot tools for the given user query. "
        "Only select tools that appear in the provided policy list. "
        "Return strict JSON only."
    )
    prompt = {
        "query": query,
        "style": style,
        "style_instruction": style_notes.get(style, style_notes["concise"]),
        "max_tools": max_tools,
        "candidate_tools": candidates,
        "allowed_output_schema": {
            "planner_source": "qgpt|rule_fallback",
            "recommended_tools": [
                {
                    "tool": "qbot_tool_name",
                    "args": {"example": "value"},
                    "reason": "why this tool fits the query",
                    "confidence": "high|medium|low",
                }
            ],
            "ask_for_more_context": False,
            "context_questions": ["..."],
            "external_llm_instruction": "Short instruction for the external LLM",
        },
    }

    plan: dict[str, Any]
    planner_source = "openai_compatible"
    try:
        raw = qgpt_json(json.dumps(prompt, ensure_ascii=False), system=system, max_tokens=1200, temperature=0)
        if not isinstance(raw, dict):
            raise ValueError("planner response is not a JSON object")
        plan = raw
    except Exception as exc:
        return {
            "tool": "qbot_external_tool_plan",
            "status": "error",
            "error": f"OpenAI-compatible planner failed: {exc}",
            "planner_source": planner_source,
            "query": query,
            "style": style,
            "max_tools": max_tools,
            "candidate_tools": candidates,
            "candidate_tool_names": candidate_names,
            "note": "No alternate-provider fallback is used in this path by design.",
        }

    recommended_tools = []
    seen: set[str] = set()
    for item in plan.get("recommended_tools", []) if isinstance(plan.get("recommended_tools", []), list) else []:
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("tool", "")).strip()
        if not tool_name or tool_name not in policy_index or tool_name in seen:
            continue
        seen.add(tool_name)
        meta = policy_index[tool_name]
        recommended_tools.append({
            "tool": tool_name,
            "args": item.get("args") if isinstance(item.get("args"), dict) else meta.get("args_schema", {}) or {},
            "reason": str(item.get("reason", meta.get("description_for_planner", "")))[:1000],
            "confidence": str(item.get("confidence", "medium")),
        })
        if len(recommended_tools) >= max_tools:
            break

    if not recommended_tools:
        fallback = _fallback_tool_plan(query, max_tools=max_tools)
        recommended_tools = fallback.get("recommended_tools", [])
        planner_source = "openai_compatible+rule_fallback"
        plan.setdefault("ask_for_more_context", fallback.get("ask_for_more_context", False))
        plan.setdefault("context_questions", fallback.get("context_questions", []))
        plan.setdefault("notes", fallback.get("notes"))

    external_llm_instruction = str(plan.get("external_llm_instruction") or "").strip()
    if not external_llm_instruction:
        tool_list = ", ".join(t["tool"] for t in recommended_tools) if recommended_tools else "QBot tool policy"
        external_llm_instruction = (
            f"Use the recommended QBot tools in this order when needed: {tool_list}. "
            "If a tool already answers the query, stop. If context is missing, ask one clarifying question."
        )

    return {
        "tool": "qbot_external_tool_plan",
        "status": "OK",
        "planner_source": planner_source,
        "query": query,
        "style": style,
        "max_tools": max_tools,
        "candidate_tools": candidates,
        "candidate_tool_names": candidate_names,
        "recommended_tools": recommended_tools,
        "ask_for_more_context": bool(plan.get("ask_for_more_context", False)),
        "context_questions": plan.get("context_questions", []) if isinstance(plan.get("context_questions", []), list) else [],
        "external_llm_instruction": external_llm_instruction,
        "notes": plan.get("notes"),
        "planner_error": plan.get("planner_error"),
        "plan": _sanitize(plan),
        "status_details": {
            "planner_source": planner_source,
            "candidate_count": len(candidates),
            "recommended_count": len(recommended_tools),
        },
        "include_prompt": include_prompt,
    }


# ──────────── qbot_chatgpt_prompt_pack ──────────────────────────────────

def _tool_qbot_chatgpt_prompt_pack(args: dict | None = None) -> dict[str, Any]:
    topic = str((args or {}).get("topic", "operational_status"))
    task = str((args or {}).get("task", "Summarize current Qbot status and recommend next step"))
    style = str((args or {}).get("style", "concise"))
    max_chars = int((args or {}).get("max_chars", 12000))
    query = str((args or {}).get("query", "")).strip()
    max_tools = int((args or {}).get("max_tools", 3))
    max_tools = max(1, min(5, max_tools))

    if style not in _ALLOWED_STYLES:
        return {"tool": "qbot_chatgpt_prompt_pack", "status": "error",
                "error": f"unknown style: {style!r}", "allowed": sorted(_ALLOWED_STYLES)}

    bundle = _tool_qbot_external_context_bundle({"topic": topic, "max_chars": max_chars,
                                                 "include_recent_calls": True,
                                                 "include_policy": True})
    tool_plan = None
    if query:
        tool_plan = _tool_qbot_external_tool_plan({
            "query": query,
            "style": style,
            "max_tools": max_tools,
            "include_prompt": True,
        })

    style_notes = {
        "concise": "Keep response under 500 words. Bullet points preferred.",
        "detailed": "Provide thorough analysis with reasoning. Tables and sections encouraged.",
        "operator": "Focus on actionable items. Use operator checklist format.",
        "decision_memo": "Write a formal decision memo with recommendation, rationale, risks, and alternatives.",
    }

    prompt = (
        f"ROLE: You are the main reasoning model for Qbot. Qbot is the source of truth, policy engine, and tool executor. "
        f"You act as answer synthesizer and planning assistant.\n\n"
        f"TASK: {task}\n\n"
        f"CONSTRAINTS:\n"
        f"- You may suggest which Qbot tools to use next, but Qbot's policy engine validates all steps.\n"
        f"- Never suggest executing shell commands, modifying services, or accessing secrets.\n"
        f"- Stay factual. Use the provided sanitized Qbot context.\n\n"
        f"STYLE: {style_notes.get(style, style_notes['concise'])}\n\n"
        f"CONTEXT FROM QBOT:\n"
        f"{json.dumps(bundle.get('context', {}), ensure_ascii=False, indent=2)}\n\n"
        f"TOOL PLAN:\n"
        f"{json.dumps(tool_plan.get('recommended_tools', []) if isinstance(tool_plan, dict) else [], ensure_ascii=False, indent=2)}\n\n"
        f"TOOL PLAN INSTRUCTION:\n"
        f"{tool_plan.get('external_llm_instruction', '') if isinstance(tool_plan, dict) else ''}\n\n"
        f"CLARIFYING QUESTIONS:\n"
        f"{json.dumps(tool_plan.get('context_questions', []) if isinstance(tool_plan, dict) else [], ensure_ascii=False, indent=2)}\n\n"
        f"EXPECTED OUTPUT FORMAT:\n"
        f"1. Summary of current status\n"
        f"2. Key findings and warnings\n"
        f"3. Recommended next Qbot tool to run (name from policy list)\n"
        f"4. Additional context requests if needed"
    )

    return {
        "tool": "qbot_chatgpt_prompt_pack",
        "topic": topic,
        "style": style,
        "query": query or None,
        "prompt": prompt[:max_chars],
        "context_bundle_summary": f"{len(bundle.get('included_sources', []))} sources: {', '.join(bundle.get('included_sources', [])[:5])}",
        "tool_plan": tool_plan,
        "safe_for_chatgpt": True,
        "status": "OK",
    }


# ──────────── qbot_chatgpt_decision_record_create ───────────────────────

def _tool_qbot_chatgpt_decision_record_create(args: dict | None = None) -> dict[str, Any]:
    title = str((args or {}).get("title", ""))[:200]
    decision = str((args or {}).get("decision", ""))[:20000]
    rationale = str((args or {}).get("rationale", ""))[:20000]
    source_topic = str((args or {}).get("source_context_topic", ""))
    tags = (args or {}).get("tags", []) or []
    if isinstance(tags, str):
        tags = [tags]
    tags = tags[:10]

    if not title or not decision:
        return {"tool": "qbot_chatgpt_decision_record_create", "status": "error", "error": "title and decision required"}

    cl = (title + decision + rationale).lower()
    if any(s.lower() in cl for s in _SENSITIVE):
        return {"tool": "qbot_chatgpt_decision_record_create", "status": "error",
                "error": "content contains sensitive words — rejected"}

    try:
        import psycopg
        from psycopg.rows import dict_row
        import os
        conn = psycopg.connect(
            host=os.getenv("PGHOST", "localhost"), port=os.getenv("PGPORT", "5432"),
            dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
            password=os.getenv("PGPASSWORD", ""), row_factory=dict_row,
        )
        metadata = json.dumps({"decision": decision, "rationale": rationale, "source_topic": source_topic})
        row = conn.execute(
            """INSERT INTO qbot_artifacts (artifact_type, title, content, tags, metadata)
               VALUES (%s, %s, %s, %s, %s) RETURNING id, created_at""",
            ("decision_record", title, decision, json.dumps(tags), metadata),
        ).fetchone()
        conn.commit()
        conn.close()
        return {
            "tool": "qbot_chatgpt_decision_record_create",
            "status": "ok",
            "artifact_id": row["id"],
            "created_at": row["created_at"].isoformat(),
            "title": title,
        }
    except Exception as exc:
        return {"tool": "qbot_chatgpt_decision_record_create", "status": "error", "error": str(exc)}


# ──────────── qbot_external_llm_workflow_guide ──────────────────────────

def _tool_qbot_external_llm_workflow_guide(_args: dict | None = None) -> dict[str, Any]:
    return {
        "tool": "qbot_external_llm_workflow_guide",
        "steps": [
            {
                "step": 1, "action": "Generate tool plan",
                "tool": "qbot_external_tool_plan",
                "description": "Ask QBot which tools fit the query and get a structured recommendation",
                "curl_example": 'curl -s -X POST http://127.0.0.1:8001/q -H "Content-Type: application/json" -d \'{"tool":"qbot_external_tool_plan","args":{"query":"sprawdź status qbot","style":"concise"}}\'',
            },
            {
                "step": 2, "action": "Generate context bundle",
                "tool": "qbot_external_context_bundle",
                "description": "Collect sanitized Qbot data for a topic (operational_status, etc.)",
                "curl_example": 'curl -s -X POST http://127.0.0.1:8001/q -H "Content-Type: application/json" -d \'{"tool":"qbot_external_context_bundle","args":{"topic":"operational_status"}}\'',
            },
            {
                "step": 3, "action": "Generate prompt pack",
                "tool": "qbot_chatgpt_prompt_pack",
                "description": "Create a ready-to-paste prompt for ChatGPT Plus with context, constraints, and a recommended tool plan",
                "curl_example": 'curl -s -X POST http://127.0.0.1:8001/q -H "Content-Type: application/json" -d \'{"tool":"qbot_chatgpt_prompt_pack","args":{"topic":"operational_status","task":"Summarize status","style":"concise","query":"sprawdź status qbot"}}\'',
            },
            {
                "step": 4, "action": "Paste into ChatGPT Plus session",
                "description": "Copy the prompt field from the response and paste into your ChatGPT Plus conversation",
            },
            {
                "step": 5, "action": "ChatGPT suggests Qbot actions",
                "description": "ChatGPT may suggest which Qbot tools to run next. Qbot's policy engine validates all steps.",
            },
            {
                "step": 6, "action": "Return decision to Qbot",
                "tool": "qbot_chatgpt_decision_record_create",
                "description": "Record the ChatGPT decision/rationale as a decision_record artifact in PostgreSQL",
                "curl_example": 'curl -s -X POST http://127.0.0.1:8001/q -H "Content-Type: application/json" -d \'{"tool":"qbot_chatgpt_decision_record_create","args":{"title":"Decision","decision":"...","rationale":"...","tags":["decision"]}}\'',
            },
        ],
        "what_not_to_do": [
            "NEVER paste secrets, passwords, or API keys into ChatGPT",
            "NEVER paste .env.local content",
            "NEVER paste full database dumps or user data",
            "NEVER let ChatGPT execute shell commands directly",
            "NEVER let ChatGPT bypass Qbot policy engine",
            "NEVER paste more than 20KB of context per message",
        ],
        "notes": [
            "qbot_external_tool_plan requires an OpenAI-compatible runtime in this path",
            "If the runtime is unavailable, the tool returns a hard error instead of falling back to another provider",
        ],
        "status": "OK",
    }


def _get_external_llm_tool(name: str):
    mapping = {
        "qbot_external_llm_status": _tool_qbot_external_llm_status,
        "qbot_external_llm_policy": _tool_qbot_external_llm_policy,
        "qbot_external_context_bundle": _tool_qbot_external_context_bundle,
        "qbot_external_tool_plan": _tool_qbot_external_tool_plan,
        "qbot_chatgpt_prompt_pack": _tool_qbot_chatgpt_prompt_pack,
        "qbot_chatgpt_decision_record_create": _tool_qbot_chatgpt_decision_record_create,
        "qbot_external_llm_workflow_guide": _tool_qbot_external_llm_workflow_guide,
    }
    return mapping.get(name)
