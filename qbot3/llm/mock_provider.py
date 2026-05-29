#!/usr/bin/env python3
"""Mock LLM provider — deterministic responses for testing.

Selected by ALBERT_LLM_PROVIDER=mock.
Returns predefined JSON patterns regardless of input.
"""

from __future__ import annotations

from typing import Any

from qbot3.llm.base import LLMProvider, PlanResult, AnswerResult


class MockProvider(LLMProvider):
    def plan(self, context: dict[str, Any], tools_desc: list[dict[str, Any]], user_message: str) -> PlanResult:
        ql = user_message.lower()
        intent = "status"
        tools = []
        mode = "read_only"

        if any(k in ql for k in ("readiness", "gotowoś")):
            intent = "readiness"
            tools = ["readiness"]
        elif "status" in ql:
            intent = "status"
            tools = ["status"]
        elif any(k in ql for k in ("kalendarz", "calendar", "wydarzeń", "wydarzen")):
            intent = "calendar"
            tools = ["calendar_snapshot"]
        elif any(k in ql for k in ("pogoda", "weather", "temperatur")):
            intent = "weather"
            tools = ["weather_forecast"]
        elif any(k in ql for k in ("posiłk", "jadłem", "jadłam", "zjadł", "meal", "jedzeni")):
            intent = "nutrition_day"
            tools = ["nutrition_day_summary", "nutrition_meal_list"]
        elif any(k in ql for k in ("bilans", "kalor")):
            intent = "nutrition_day"
            tools = ["nutrition_day_summary", "nutrition_meal_list"]
        elif any(k in ql for k in ("knowhow", "know-how", "know_how", "bible", "dokument")):
            intent = "docs"
            tools = ["canonical_docs"]
        elif any(k in ql for k in ("rwgps", "tras")):
            intent = "routes"
            tools = ["rwgps_route_list"]
        elif any(k in ql for k in ("wellness", "sen", "spa", "sleep")):
            intent = "wellness"
            tools = ["wellness_day", "sleep_day"]
        elif any(k in ql for k in ("dodaj", "zapisz", "przypomnij")):
            intent = "reminder_add" if "przypomnij" in ql else "calendar_event_add" if "wydarzenie" in ql else "nutrition_log_add"
            mode = "write"

        return PlanResult(
            intent=intent,
            mode=mode,
            tools_to_call=tools,
            parameters={},
            write_action=None if mode == "read_only" else intent,
            write_payload={"title": user_message[:50]} if mode == "write" else {},
            requires_confirm=mode == "write",
            confidence=0.95,
            needs_clarification=False,
            needed_context=[],
            raw={"intent": intent, "mode": mode},
        )

    def answer(self, context: dict[str, Any], plan: dict[str, Any], tool_results: list[dict[str, Any]]) -> AnswerResult:
        mode = plan.get("mode", "read_only")
        if mode == "write":
            return AnswerResult(
                answer="Przygotowałem draft. Zapis wymaga potwierdzenia przez qbot.action_execute.",
                status="draft",
                confidence="high",
            )
        return AnswerResult(
            answer="Mock provider response.",
            status="ok",
            confidence="high",
        )
