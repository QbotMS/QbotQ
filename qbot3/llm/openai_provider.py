#!/usr/bin/env python3
"""OpenAI-compatible LLM provider — wraps qgpt_client which handles OpenAI + Anthropic fallback.

Selected by ALBERT_LLM_PROVIDER=openai (default).
Model selected by ALBERT_LLM_MODEL env var, or QGPT_MODEL / ANTHROPIC_MODEL.
"""

from __future__ import annotations

import json
import os
from typing import Any

from qgpt_client import qgpt_json
from qbot3.llm.base import LLMProvider, PlanResult, AnswerResult


_PLAN_SYSTEM = """\
Jesteś Albert — jedyny mózg decyzyjny QBot3.

Masz wygenerować WYŁĄCZNIE JSON planu:
{
  "intent": "nazwa_intentu",
  "mode": "read_only|write",
  "tools_to_call": [],
  "parameters": {},
  "write_action": null,
  "write_payload": {},
  "requires_confirm": false,
  "confidence": 0.0,
  "needs_clarification": false,
  "clarification_question": "",
  "needed_context": []
}

TWARDE ZASADY:
- Nie odpowiadaj użytkownikowi. Zwracasz TYLKO JSON.
- Używaj TYLKO narzędzi z listy available_tools. NIE wymyślaj nazw.
- Dla odczytu: mode="read_only", tools_to_call = lista narzędzi, write_action=null.
- Dla zapisu (dodaj/usuń/zmień/zapisz): mode="write", tools_to_call=[], write_action="nazwa_writera", write_payload: {parametry do writera}.
- Nie pisz "dodano", "zapisano", "wykonano" w planie. To należy do final answer.
- parameters: tylko pola z args_schema narzędzia.
- confidence: 0.0-1.0. Jeśli <0.6, ustaw needs_clarification=true.
- needed_context: lista kontekstu który może być potrzebny (np. "bible", "knowhow").
- DOPASUJ narzędzie do DOMENY pytania. Nie używaj system_logs_recent jako domyślnego dla problemów domenowych.
  * daily report / email pipeline → daily_report_status
  * gate / furtka / unlock → gate_status
  * hammerhead / garmin sync / transfer → hammerhead_sync_status
  * docs / bible / knowhow → canonical_docs
- Jeśli narzędzie z available_tools pasuje do domeny, UŻYJ go. Nie wybieraj ogólnych narzędzi (system_logs_recent, system_env_status) gdy istnieje dedykowane narzędzie.

DB INTROSPECTION (transparent read-only):
- Są narzędzia db_schema_list, db_table_describe, db_sample_rows, db_select_readonly.
- Jeśli dedykowany reader (np. qcal_events_range) może nie działać z powodu braku kolumny,
  dodaj db_select_readonly jako fallback w tools_to_call.
- db_select_readonly przyjmuje parametr "sql" — tylko SELECT, LIMIT wymuszony.
- db_table_describe pokazuje rzeczywiste kolumny tabeli.
- Przykład: dla kalendarza → dodaj qcal_events_range ORAZ db_table_describe(table="calendar_events")
  jako fallback na wypadek błędu readera.
"""

_FINAL_SYSTEM = """\
Jesteś Albert — generujesz odpowiedź użytkownika.

Masz dostać:
- pytanie użytkownika
- plan (intent, mode, tools)
- wyniki narzędzi (tool_results)

TWARDE ZASADY:
- NIE wymyślaj nazw tooli, readerów, writerów.
- DLA ZAPISU (mode=write): NIGDY nie pisz "dodano", "zapisano", "wykonano". Zawsze mów "Przygotowałem draft" lub "wymaga potwierdzenia przez qbot.action_execute".
- Jeśli narzędzie nie zwróciło danych: "brak danych w DB", a nie "nie mam dostępu".
- Dla calendar_snapshot: przedstaw wydarzenia, remindery, posiłki — pełny obraz dnia.
- Dla bilansu: podaj kcal_in, kcal_out (jeśli dostępne), różnicę.
- Nie opisuj procesu planowania.
- Jeśli coś się nie udało, powiedz konkretnie co i na którym etapie.

DB INTROSPECTION FALLBACK:
- Jeśli któryś z wyników narzędzia ma status "SCHEMA_MISMATCH" lub "READER_ERROR",
  oznacza to, że dedykowany reader padł na schemacie DB (np. brakująca kolumna).
- W takich przypadkach system automatycznie uruchomił db_introspection_fallback —
  zobacz czy w tool_results są wyniki z czytnika "db_introspection_fallback.*".
- Jeśli istnieją, UŻYJ ich jako źródła danych. Poinformuj użytkownika, że reader miał błąd,
  ale dane zostały pobrane przez DB introspection.
- Jeśli nie ma fallbacka (status czytnika to wciąż błąd), poinformuj o błędzie readera
  i zaproponuj użycie db_schema_list / db_table_describe / db_select_readonly do diagnozy.

- Zwróć WYŁĄCZNIE JSON:
{
  "answer": "...",
  "status": "ok|partial|no_data|draft|clarify|error",
  "confidence": "low|medium|high",
  "missing_fields": [],
  "limitations": []
}
"""


class OpenAIProvider(LLMProvider):
    def plan(self, context: dict[str, Any], tools_desc: list[dict[str, Any]], user_message: str) -> PlanResult:
        model = os.getenv("ALBERT_LLM_MODEL", "") or None
        system = _PLAN_SYSTEM + "\n\nDostępne narzędzia:\n" + "\n".join(
            f"  {t.get('name', '?')} ({t.get('category', '?')}, safety={t.get('safety', '?')}) — {t.get('description', '')[:120]}"
            for t in tools_desc
        )
        payload = {
            "question": user_message,
            "available_tools": tools_desc,
            "context": context,
            "rules": ["Use ONLY tools from available_tools.", "For write: mode=write, tools_to_call=[], write_action=name.", "Do not invent tool names."],
        }
        result = qgpt_json(
            json.dumps(payload, ensure_ascii=False, default=str),
            system=system,
            max_tokens=500,
            temperature=0,
        )
        if not isinstance(result, dict):
            result = {}
        raw = dict(result)
        intent = str(result.get("intent", "")).strip()
        mode = str(result.get("mode", "read_only")).strip().lower()
        if mode not in ("read_only", "write"):
            mode = "read_only" if not result.get("write_action") else "write"
        return PlanResult(
            intent=intent,
            mode=mode,
            tools_to_call=result.get("tools_to_call", []),
            parameters=result.get("parameters", {}),
            write_action=result.get("write_action"),
            write_payload=result.get("write_payload", {}),
            requires_confirm=bool(result.get("requires_confirm", False)),
            confidence=max(0.0, min(1.0, float(result.get("confidence", 0.0)))),
            needs_clarification=bool(result.get("needs_clarification", False)) or not intent,
            clarification_question=str(result.get("clarification_question", "")),
            needed_context=result.get("needed_context", []),
            raw=raw,
        )

    def answer(self, context: dict[str, Any], plan: dict[str, Any], tool_results: list[dict[str, Any]]) -> AnswerResult:
        system = _FINAL_SYSTEM
        payload = {"question": context.get("question", ""), "plan": plan, "tool_results": tool_results}
        final = qgpt_json(
            json.dumps(payload, ensure_ascii=False, default=str),
            system=system,
            max_tokens=700,
            temperature=0,
        )
        if not isinstance(final, dict):
            return AnswerResult(answer="Nie mogę przetworzyć odpowiedzi.", status="error", confidence="low", limitations=["final_llm_non_dict"])
        answer = str(final.get("answer", "")).strip()
        if not answer:
            return AnswerResult(answer="Nie mogę przetworzyć odpowiedzi.", status="error", confidence="low", limitations=["empty_answer"])
        return AnswerResult(
            answer=answer,
            status=str(final.get("status", "ok")).strip().lower() or "ok",
            confidence=str(final.get("confidence", "medium")).strip().lower() or "medium",
            missing_fields=final.get("missing_fields", []),
            limitations=final.get("limitations", []),
            raw=final,
        )
