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
        tools = ["status"]
        mode = "read_only"
        write_action = None
        write_payload = {}
        requires_confirm = False

        # Write patterns must be checked FIRST to avoid matching "event" etc.
        if any(k in ql for k in ("dodaj", "zapisz", "przypomnij")):
            mode = "write"
            tools = []
            if "przypomnij" in ql:
                intent = "reminder_add"
            elif "wydarzenie" in ql or "event" in ql or "kalendarz" in ql or "bikepack" in ql:
                intent = "calendar_event_add"
            else:
                intent = "nutrition_log_add"
            write_action = intent
            write_payload = {"title": user_message[:80]}
            requires_confirm = True
        elif any(k in ql for k in ("readiness", "gotowoś")):
            intent = "readiness"
            tools = ["readiness"]
        elif any(k in ql for k in ("kalendarz", "calendar", "wydarzeń", "wydarzen", "event", "eventy", "zaplanowane", "spotkan")):
            intent = "calendar"
            tools = ["qcal_events_range"]
        elif any(k in ql for k in ("pogoda", "weather", "temperatur")):
            intent = "weather"
            tools = ["weather_forecast"]
        elif any(k in ql for k in ("posiłk", "jadłem", "jadłam", "zjadł", "meal", "jedzeni")):
            intent = "nutrition_day"
            tools = ["nutrition_day_summary", "nutrition_meal_list"]
        elif any(k in ql for k in ("bilans", "kalor", "kcal", "energy")):
            intent = "nutrition_balance"
            tools = ["nutrition_balance_today", "nutrition_day_summary"]
        elif any(k in ql for k in ("knowhow", "know-how", "know_how", "bible", "dokument", "kanoniczn")):
            intent = "docs"
            tools = ["canonical_docs"]
        elif any(k in ql for k in ("rwgps", "tras", "route")):
            intent = "routes"
            tools = ["rwgps_route_list"]
        elif any(k in ql for k in ("wellness", "sen", "spa", "sleep", "hrv")):
            intent = "wellness"
            tools = ["wellness_day", "sleep_day"]
        elif any(k in ql for k in ("garmin", "diagnost", "dane", "sync", "import")):
            intent = "garmin_diagnostics"
            tools = ["garmin_diagnostics", "garmin_sync_status"]
        elif any(k in ql for k in ("narzędzi", "tool", "mcp", "dostępny", "capabilit")):
            intent = "mcp_tools"
            tools = ["mcp_tools_list"]
        elif any(k in ql for k in ("garage", "samochód", "rower")):
            intent = "garage"
            tools = ["garage_status"]
        elif any(k in ql for k in ("furtk", "gate", "hikconnect", "otwórz bram", "gate_status")):
            intent = "gate_status"
            tools = ["gate_status"]
        elif any(k in ql for k in ("hammerhead", "garmin sync", "transfer", "karoo", "activity transfer")):
            intent = "hammerhead_sync_status"
            tools = ["hammerhead_sync_status"]
        elif any(k in ql for k in ("raport dzienny", "daily report", "report status", "pipeline", "dlaczego email", "raport nie przeszedł")):
            intent = "daily_report_status"
            tools = ["daily_report_status"]

        return PlanResult(
            intent=intent,
            mode=mode,
            tools_to_call=tools,
            parameters={},
            write_action=write_action,
            write_payload=write_payload,
            requires_confirm=requires_confirm,
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
