#!/usr/bin/env python3
"""DeepSeek LLM provider — cheaper dev/test alternative.

Selected by ALBERT_LLM_PROVIDER=deepseek.
Model: DEEPSEEK_MODEL env var, default deepseek-chat.
API: DEEPSEEK_API_KEY env var, endpoint https://api.deepseek.com/v1.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from qbot3.llm.base import LLMProvider, PlanResult, AnswerResult

_PLAN_PROMPT = """\
You are Albert — QBot3 planning LLM. Output ONLY valid JSON for the plan.
Rules:
- Use ONLY tools from available_tools list.
- For read: mode="read_only", tools_to_call=[tool_names].
- For write: mode="write", write_action="writer_name", write_payload={params}.
- Do not invent tool names.
- confidence 0.0-1.0, <0.6 means needs_clarification=true.
- Includes db_schema_list, db_table_describe, db_sample_rows, db_select_readonly tools.
- If a domain reader might fail (e.g. missing column), add db_table_describe as fallback.
Output JSON: {{"intent":"...","mode":"read_only|write","tools_to_call":[],"parameters":{{}},"write_action":null,"write_payload":{{}},"requires_confirm":false,"confidence":0.0,"needs_clarification":false,"clarification_question":"","needed_context":[]}}
"""

_ANSWER_PROMPT = """\
You are Albert — QBot3 answer generator. Output ONLY valid JSON.
Rules:
- For writes: NEVER say "dodano", "zapisano", "wykonano". Say "Przygotowałem draft".
- If tool returned no data: "brak danych w DB", not "nie mam dostępu".
- For calendar: show events, reminders, meals.
- Do not describe planning process.
- If any tool result has status "SCHEMA_MISMATCH" or "READER_ERROR", check for
  db_introspection_fallback results. If available, use them as data source.
- If fallback not available, explain the reader error and suggest DB introspection.
Output JSON: {{"answer":"...","status":"ok|partial|no_data|draft|clarify|error","confidence":"low|medium|high","missing_fields":[],"limitations":[]}}
"""


class DeepSeekProvider(LLMProvider):
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.model = os.getenv("ALBERT_LLM_MODEL", "deepseek-chat")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

    def _call(self, system: str, user: str, max_tokens: int = 500) -> Any:
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY not configured")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0,
        }
        r = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not text:
            raise RuntimeError(f"Empty DeepSeek response: {data}")
        import re
        clean = text.strip()
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.MULTILINE).strip()
        return json.loads(clean)

    def plan(self, context: dict[str, Any], tools_desc: list[dict[str, Any]], user_message: str) -> PlanResult:
        tools_text = "\n".join(f"- {t['name']} ({t['category']}): {t['description'][:100]}" for t in tools_desc)
        system = _PLAN_PROMPT + "\n\nAvailable tools:\n" + tools_text
        user = f"User: {user_message}\nContext: {json.dumps(context, ensure_ascii=False, default=str)[:500]}"
        result = self._call(system, user, max_tokens=500)
        if not isinstance(result, dict):
            result = {}
        return PlanResult(
            intent=str(result.get("intent", "")).strip(),
            mode=str(result.get("mode", "read_only")).strip().lower(),
            tools_to_call=result.get("tools_to_call", []),
            parameters=result.get("parameters", {}),
            write_action=result.get("write_action"),
            write_payload=result.get("write_payload", {}),
            requires_confirm=bool(result.get("requires_confirm", False)),
            confidence=max(0.0, min(1.0, float(result.get("confidence", 0.0)))),
            needs_clarification=bool(result.get("needs_clarification", False)) or not result.get("intent"),
            clarification_question=str(result.get("clarification_question", "")),
            needed_context=result.get("needed_context", []),
            raw=dict(result),
        )

    def answer(self, context: dict[str, Any], plan: dict[str, Any], tool_results: list[dict[str, Any]]) -> AnswerResult:
        user = json.dumps({"question": context.get("question", ""), "plan": plan, "tool_results": tool_results}, ensure_ascii=False, default=str)[:3000]
        result = self._call(_ANSWER_PROMPT, user, max_tokens=700)
        if not isinstance(result, dict):
            return AnswerResult(answer="Error processing response.", status="error")
        return AnswerResult(
            answer=str(result.get("answer", "")).strip() or "Error.",
            status=str(result.get("status", "error")).strip().lower(),
            confidence=str(result.get("confidence", "medium")).strip().lower(),
            missing_fields=result.get("missing_fields", []),
            limitations=result.get("limitations", []),
            raw=result,
        )
