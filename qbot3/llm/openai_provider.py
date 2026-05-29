#!/usr/bin/env python3
"""OpenAI-compatible LLM provider — wraps qgpt_client which handles OpenAI + Anthropic fallback.

Selected by ALBERT_LLM_PROVIDER=openai (default).
Model selected by ALBERT_LLM_MODEL env var, or QGPT_MODEL / ANTHROPIC_MODEL.
"""

from __future__ import annotations

import json
import logging
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
- Dla zapisu (dodaj/usuń/zmień/zapisz): mode="write", tools_to_call=[], write_action="nazwa_writera", write_payload: {parametry do writera}, requires_confirm=true (ZAWSZE true dla write — patrz zasada poniżej).
- Nie pisz "dodano", "zapisano", "wykonano" w planie. To należy do final answer.
- requires_confirm: dla mode="read_only" ustaw false, dla mode="write" ZAWSZE true. "Bez zapisu", "nie zapisuj", "tylko przygotuj", "draft" oznaczają przygotowanie action_draft bez wykonania — NIE zmieniają requires_confirm na false. qbot.query nigdy nie wykonuje zapisu, więc każdy write draft wymaga potwierdzenia przez qbot.action_execute.
- parameters: tylko pola z args_schema narzędzia.
- confidence: 0.0-1.0. Jeśli <0.6, ustaw needs_clarification=true.
- needed_context: lista kontekstu który może być potrzebny (np. "bible", "knowhow").
- DOPASUJ narzędzie do DOMENY pytania. Nie używaj system_logs_recent jako domyślnego dla problemów domenowych.
  * daily report / email pipeline → daily_report_status
  * gate / furtka / unlock → gate_status
  * hammerhead / garmin sync / transfer → hammerhead_sync_status
  * docs / bible / knowhow → canonical_docs
- Jeśli narzędzie z available_tools pasuje do domeny, UŻYJ go. Nie wybieraj ogólnych narzędzi (system_logs_recent, system_env_status) gdy istnieje dedykowane narzędzie.

WIELOKROKOWE PLANOWANIE:
- Możesz planować w wielu krokach. Po wykonaniu narzędzi zobaczysz ich wyniki w `tool_results` i możesz zaplanować kolejny krok lub zakończyć odpowiedzią.
- Jeśli nie znasz schematu DB, najpierw użyj db_schema_list, potem db_table_describe, a dopiero potem db_select_readonly z konkretnym sql.
- Każde wybrane narzędzie musi mieć kompletne argumenty. Nie dodawaj narzędzi "na próbę".
- Aby zakończyć i wygenerować odpowiedź, zwróć tools_to_call=[] (pusta lista). Wtedy system przekaże wszystkie tool_results do final answer.

DB INTROSPECTION (transparent read-only):
- db_schema_list, db_table_describe, db_sample_rows, db_select_readonly to narzędzia do jawnego odczytu DB.
- DB read-only jest domyślnym źródłem prawdy dla zwykłych pytań o dane.
- Jeśli tabela nie jest znana, najpierw użyj db_schema_list, potem db_table_describe.
- Jeśli znasz lub możesz ustalić tabelę, użyj db_select_readonly z konkretnym sql do pobrania realnych rekordów. NIGDY nie planuj db_select_readonly bez parametru sql — zostanie odrzucony.
- db_sample_rows używaj tylko do orientacji w kształcie danych, nie jako zamiennik realnych rekordów.
- Snapshoty / dashboardy nie są domyślnym odczytem danych.
- calendar_snapshot używaj wyłącznie, gdy użytkownik pyta wprost o dzisiejszy dashboard, podsumowanie dnia, snapshot dnia albo status dnia.
- Przykład: dla "pokaż kalendarz" użyj db_schema_list lub db_table_describe(table="calendar_events"), a potem db_select_readonly z future rows z calendar_events (od dziś w przyszłość, limit 100).
- Przykład: dla "co dziś jadłem" użyj db_schema_list / db_table_describe dla tabel żywieniowych, a potem db_select_readonly z dzisiejszymi realnymi logami.
- Jeśli dane nie siedzą w DB, możesz użyć technicznego connector read-only, ale nadal bez snapshotu jako domyślnego zamiennika.
- Jeśli pytanie jest czysto testowe / konwersacyjne i nie wymaga danych, możesz zwrócić mode="read_only" z pustym tools_to_call.
- Dla ordinary calendar / food / training questions nie używaj calendar_snapshot ani gotowych summary readers jako domyślnego źródła.
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
- Dla snapshotów / dashboardów: pokazuj je tylko wtedy, gdy użytkownik pyta wprost o dzisiejszy dashboard, podsumowanie dnia, snapshot dnia albo status dnia.
- Dla zwykłych pytań o kalendarz, jedzenie, treningi czy trasy używaj realnych rekordów przez DB read-only albo low-level connector read-only.
- Jeśli plan ma puste tools_to_call, odpowiedz bezpośrednio i zwięźle zamiast zgłaszać brak narzędzi.
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
    def __init__(self) -> None:
        _log = logging.getLogger("qbot3.llm")
        _provider = os.getenv("ALBERT_LLM_PROVIDER", "openai")
        _model = os.getenv("ALBERT_LLM_MODEL") or os.getenv("QGPT_MODEL") or "(env not set)"
        _qgpt_key = bool(os.getenv("QGPT_API_KEY"))
        _openai_key = bool(os.getenv("OPENAI_API_KEY"))
        _anthropic_key = bool(os.getenv("ANTHROPIC_API_KEY"))
        _log.info(
            f"Albert LLM transport: provider={_provider} model={_model} "
            f"qgpt_key={_qgpt_key} openai_key={_openai_key} anthropic_key={_anthropic_key}"
        )

    def plan(self, context: dict[str, Any], tools_desc: list[dict[str, Any]], user_message: str,
             tool_results: list[dict[str, Any]] | None = None) -> PlanResult:
        system = _PLAN_SYSTEM + "\n\nDostępne narzędzia są przekazane w payload.available_tools. Nie powtarzaj ich listy w odpowiedzi."
        payload: dict[str, Any] = {
            "question": user_message,
            "available_tools": tools_desc,
            "context": context,
            "rules": ["Use ONLY tools from available_tools.", "For write: mode=write, tools_to_call=[], write_action=name.", "Do not invent tool names."],
        }
        if tool_results:
            payload["tool_results"] = tool_results
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
        payload = {"question": context.get("question", ""), "plan": plan, "tool_results": _compact_tool_results(tool_results)}
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


def _compact_tool_results(tool_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shrink tool results before final answer generation.

    Keeps the semantics and row-level evidence, but removes bulky repeated data
    that can cause model truncation or malformed JSON.
    """
    compacted: list[dict[str, Any]] = []
    for tr in tool_results:
        data = tr.get("data", {})
        if not isinstance(data, dict):
            compacted.append(tr)
            continue
        item = dict(tr)
        compact_data = dict(data)
        rows = compact_data.get("rows")
        if isinstance(rows, list):
            compact_data["rows"] = rows[:5]
            compact_data["row_count"] = compact_data.get("row_count", len(rows))
            compact_data["_rows_truncated"] = len(rows) > 5
        events = compact_data.get("events")
        if isinstance(events, list):
            compact_data["events"] = events[:5]
            compact_data["count"] = compact_data.get("count", len(events))
            compact_data["_events_truncated"] = len(events) > 5
        documents = compact_data.get("documents")
        if isinstance(documents, list):
            compact_data["documents"] = documents[:3]
            compact_data["count"] = compact_data.get("count", len(documents))
            compact_data["_documents_truncated"] = len(documents) > 3
        item["data"] = compact_data
        compacted.append(item)
    return compacted
