"""Qbot External LLM mode — ChatGPT Plus external session integration."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

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


# ──────────── qbot_chatgpt_prompt_pack ──────────────────────────────────

def _tool_qbot_chatgpt_prompt_pack(args: dict | None = None) -> dict[str, Any]:
    topic = str((args or {}).get("topic", "operational_status"))
    task = str((args or {}).get("task", "Summarize current Qbot status and recommend next step"))
    style = str((args or {}).get("style", "concise"))
    max_chars = int((args or {}).get("max_chars", 12000))

    if style not in _ALLOWED_STYLES:
        return {"tool": "qbot_chatgpt_prompt_pack", "status": "error",
                "error": f"unknown style: {style!r}", "allowed": sorted(_ALLOWED_STYLES)}

    bundle = _tool_qbot_external_context_bundle({"topic": topic, "max_chars": max_chars,
                                                   "include_recent_calls": True,
                                                   "include_policy": True})

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
        "prompt": prompt[:max_chars],
        "context_bundle_summary": f"{len(bundle.get('included_sources', []))} sources: {', '.join(bundle.get('included_sources', [])[:5])}",
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
                "step": 1, "action": "Generate context bundle",
                "tool": "qbot_external_context_bundle",
                "description": "Collect sanitized Qbot data for a topic (operational_status, etc.)",
                "curl_example": 'curl -s -X POST http://127.0.0.1:8001/q -H "Content-Type: application/json" -d \'{"tool":"qbot_external_context_bundle","args":{"topic":"operational_status"}}\'',
            },
            {
                "step": 2, "action": "Generate prompt pack",
                "tool": "qbot_chatgpt_prompt_pack",
                "description": "Create a ready-to-paste prompt for ChatGPT Plus with context, constraints, and style",
                "curl_example": 'curl -s -X POST http://127.0.0.1:8001/q -H "Content-Type: application/json" -d \'{"tool":"qbot_chatgpt_prompt_pack","args":{"topic":"operational_status","task":"Summarize status","style":"concise"}}\'',
            },
            {
                "step": 3, "action": "Paste into ChatGPT Plus session",
                "description": "Copy the prompt field from the response and paste into your ChatGPT Plus conversation",
            },
            {
                "step": 4, "action": "ChatGPT suggests Qbot actions",
                "description": "ChatGPT may suggest which Qbot tools to run next. Qbot's policy engine validates all steps.",
            },
            {
                "step": 5, "action": "Return decision to Qbot",
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
        "status": "OK",
    }


def _get_external_llm_tool(name: str):
    mapping = {
        "qbot_external_llm_status": _tool_qbot_external_llm_status,
        "qbot_external_llm_policy": _tool_qbot_external_llm_policy,
        "qbot_external_context_bundle": _tool_qbot_external_context_bundle,
        "qbot_chatgpt_prompt_pack": _tool_qbot_chatgpt_prompt_pack,
        "qbot_chatgpt_decision_record_create": _tool_qbot_chatgpt_decision_record_create,
        "qbot_external_llm_workflow_guide": _tool_qbot_external_llm_workflow_guide,
    }
    return mapping.get(name)
