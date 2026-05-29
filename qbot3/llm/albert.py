#!/usr/bin/env python3
"""Albert — natywny agent loop z OpenAI-compatible tool/function calling.

Zastępuje dwuetapowe plan()+answer() z openai_provider.py.
Jeden przepływ: pytanie → tool_calls loop → odpowiedź tekstem.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from qbot_config import (
    ANTHROPIC_API_KEY,
    QGPT_API_KEY,
    QGPT_BASE_URL,
    QGPT_MODEL,
)

_log = logging.getLogger("qbot3.albert")

# Limit iteracji — zapobiega nieskończonej pętli
_MAX_STEPS = int(os.getenv("ALBERT_MAX_STEPS", "5"))

# Model i transport — przez qbot_config (ładuje .env)
_BASE_URL = (QGPT_BASE_URL or "https://api.openai.com/v1").rstrip("/")
_MODEL    = QGPT_MODEL or os.getenv("ALBERT_LLM_MODEL", "gpt-4o-mini")
_API_KEY  = QGPT_API_KEY or os.getenv("OPENAI_API_KEY") or ANTHROPIC_API_KEY or ""

def _needs_forced_final_answer(answer_text: str, tool_results_log: list[dict]) -> bool:
    """Sprawdza czy model zakończył z pustą odpowiedzią mimo że ma dane z narzędzi.

    Wymusza final-answer call gdy model zwrócił 'Brak danych' lub pusty string,
    a w tool_results są rzeczywiste dane (nie błędy).
    """
    if not tool_results_log:
        return False
    # Pusta odpowiedź lub fraza "brak danych"
    if answer_text and "brak danych" not in answer_text.lower():
        return False
    # Sprawdź czy któryś tool_result ma rzeczywiste dane (nie błąd)
    for tr in tool_results_log:
        status = tr.get("status", "")
        if status in ("error", "ERROR", "BLOCKED", "SCHEMA_MISMATCH", "READER_ERROR", "DATA_MISSING"):
            continue
        data = tr.get("data", {})
        if isinstance(data, dict):
            # Ma klucze poza standardowymi meta-polami
            meaningful = {k for k in data if k not in ("status", "tool", "safety_class", "reader", "category")}
            if meaningful:
                return True
    return False


def _flatten_tool_result(tool_name: str, result: Any) -> dict:
    """Wypłaszcza wynik toola do formatu czytelnego dla modelu.

    Modele OpenAI-compatible oczekują że content w role=tool to
    bezpośredni wynik narzędzia — nie wrapper {reader, status, data}.
    """
    if not isinstance(result, dict):
        return {"tool": tool_name, "result": str(result)}

    status = result.get("status", "OK")

    # Przypadek błędu — zachowaj komunikat
    if status not in ("OK", "ok", "READY_WITH_WARNINGS"):
        error_msg = (
            result.get("error")
            or result.get("message")
            or (result.get("data", {}).get("error", "") if isinstance(result.get("data"), dict) else "")
            or str(status)
        )
        return {
            "tool": tool_name,
            "status": status,
            "error": error_msg,
        }

    # Przypadek sukcesu — wypłaszcz data na poziom główny
    data = result.get("data", {})
    if isinstance(data, dict):
        flat: dict[str, Any] = {"tool": tool_name, "status": "OK"}
        skip = {"status", "tool", "safety_class", "_rows_truncated", "_events_truncated",
                "_documents_truncated", "reader", "category", "args_schema", "mode", "notes"}
        for k, v in data.items():
            if k not in skip:
                flat[k] = v
        return flat

    # Fallback — zwróć oryginalny result bez wrappera reader/category
    flat = {"tool": tool_name, "status": "OK"}
    for k, v in result.items():
        if k not in ("reader", "category", "safety_class"):
            flat[k] = v
    return flat


_SYSTEM = """\
Jesteś Albert — asystent osobisty Michała (Warszawa, rowerzysta, gravel).
Odpowiadasz po polsku, zwięźle i konkretnie.

Masz dostęp do narzędzi. Używaj ich samodzielnie aby zebrać potrzebne dane.
Nie opisuj planu działania. Nie pytaj o potwierdzenie przy odczycie danych.
Przy zapisie danych zawsze twórz draft i informuj że wymaga qbot.action_execute.

Reguły bezpieczeństwa:
- Operacje destrukcyjne (usuń, skasuj, wyczyść) są zablokowane — nie próbuj ich wykonywać.
- Zapis danych (dodaj, wpisz, zapisz) → zwróć action_draft z action_type i payload.
- Odczyt danych → wywołaj narzędzia i odpowiedz na podstawie wyników.
- Jeśli nie masz danych, powiedz wprost "brak danych" zamiast "nie mam dostępu".
- Po otrzymaniu wyniku narzędzia użyj go do odpowiedzi. Jeśli tool zwrócił dane, NIE mów "brak danych".
- Przy DB: jeśli nie znasz schematu, najpierw wywołaj db_schema_list, potem db_table_describe,
  potem db_select_readonly z konkretnym SQL.
- Nie dodawaj narzędzi "na próbę" — każde narzędzie musi mieć kompletne argumenty.
- Jeśli nie potrzebujesz więcej danych, zakończ odpowiedzią bez wywoływania narzędzi.
"""


def run(question: str, tools_spec: list[dict], execute_tool_fn, context: dict) -> dict[str, Any]:
    """Główna pętla Alberta.

    Args:
        question: pytanie użytkownika
        tools_spec: lista narzędzi w formacie OpenAI tools[]
        execute_tool_fn: callable(tool_name: str, args: dict) -> dict
        context: dict z date, timezone, user itp.

    Returns:
        dict: answer, status, tool_results, steps, action_draft
    """
    try:
        import openai
    except ImportError:
        return {
            "answer": "Brak biblioteki openai. Zainstaluj: pip install openai",
            "status": "error",
            "tool_results": [],
            "steps": 0,
            "action_draft": None,
        }

    client = openai.OpenAI(api_key=_API_KEY, base_url=_BASE_URL)

    ctx_str = ""
    if context:
        ctx_str = f"\n\nKontekst: {json.dumps(context, ensure_ascii=False, default=str)}"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM + ctx_str},
        {"role": "user",   "content": question},
    ]

    tool_results_log: list[dict] = []
    action_draft = None
    steps = 0

    _log.info(f"Albert start: model={_MODEL} base_url={_BASE_URL} tools={len(tools_spec)} question={question[:80]}")

    for step in range(_MAX_STEPS):
        steps = step + 1

        try:
            kwargs: dict[str, Any] = {
                "model": _MODEL,
                "messages": messages,
                "temperature": 0,
                "max_tokens": 1200,
            }
            if tools_spec:
                kwargs["tools"] = tools_spec
                kwargs["tool_choice"] = "auto"

            response = client.chat.completions.create(**kwargs)
        except Exception as exc:
            _log.error(f"Albert LLM error step={step}: {exc}")
            return {
                "answer": f"Błąd komunikacji z LLM: {exc}",
                "status": "error",
                "tool_results": tool_results_log,
                "steps": steps,
                "action_draft": None,
            }

        msg = response.choices[0].message
        finish = response.choices[0].finish_reason
        answer_text = (msg.content or "").strip()
        empty_answer = not answer_text

        _log.info(
            f"Albert step={step}: finish={finish} empty_content={empty_answer} "
            f"tool_calls={len(msg.tool_calls) if msg.tool_calls else 0} "
            f"tool_results={len(tool_results_log)}"
        )

        # Albert zakończył — zwróć odpowiedź tekstem
        if finish == "stop" or not msg.tool_calls:
            if not answer_text:
                answer_text = "Brak danych do odpowiedzi."

            # Jeśli model skończył z pustą odpowiedzią mimo danych → wymuś final answer
            if _needs_forced_final_answer(answer_text, tool_results_log):
                _log.info("Albert forcing final answer without tools")
                messages.append({
                    "role": "user",
                    "content": (
                        "Masz powyżej wyniki narzędzi. "
                        "Odpowiedz użytkownikowi po polsku na podstawie tych danych. "
                        "Jeśli wynik narzędzia zawiera dane, NIE mów 'brak danych'."
                    ),
                })
                try:
                    final_response = client.chat.completions.create(
                        model=_MODEL,
                        messages=messages,
                        temperature=0,
                        max_tokens=1200,
                    )
                    forced_answer = (final_response.choices[0].message.content or "").strip()
                    if forced_answer:
                        answer_text = forced_answer
                        _log.info(f"Albert forced answer obtained: len={len(answer_text)}")
                except Exception as exc:
                    _log.error(f"Albert forced final answer error: {exc}")

            status = "draft" if action_draft else "ok"
            _log.info(f"Albert done: steps={steps} status={status} answer_len={len(answer_text)}")
            return {
                "answer": answer_text,
                "status": status,
                "tool_results": tool_results_log,
                "steps": steps,
                "action_draft": action_draft,
            }

        # Albert chce wywołać narzędzia — dodaj jego odpowiedź do historii
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_msg)

        # Wykonaj każde tool_call
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            _log.info(f"Albert tool_call: {tool_name} args={json.dumps(args, ensure_ascii=False)[:120]}")

            try:
                result = execute_tool_fn(tool_name, args)
            except Exception as exc:
                result = {"status": "error", "error": str(exc)[:300]}

            tool_results_log.append({
                "reader": tool_name,
                "status": result.get("status", "OK") if isinstance(result, dict) else "OK",
                "data": result,
            })

            # Wykryj write draft — zapisz action_draft do zwrotu
            if isinstance(result, dict) and result.get("status") == "WRITE_DRAFT":
                action_draft = {
                    "action_type": result.get("action_type", tool_name),
                    "payload_json": result.get("payload_json", args),
                    "requires_confirm": True,
                    "idempotency_key": None,
                }

            # Dodaj wypłaszczony wynik tool do historii
            tool_content = _flatten_tool_result(tool_name, result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(tool_content, ensure_ascii=False, default=str)[:4000],
            })

    # Przekroczono limit kroków
    _log.warning(f"Albert max_steps={_MAX_STEPS} reached")
    return {
        "answer": (
            f"Przekroczono limit {_MAX_STEPS} kroków. "
            f"Ostatnie narzędzia: {[r['reader'] for r in tool_results_log[-3:]]}"
        ),
        "status": "partial",
        "tool_results": tool_results_log,
        "steps": steps,
        "action_draft": action_draft,
    }


def build_tools_spec(tools_desc: list[dict]) -> list[dict]:
    """Konwertuje tool_descriptions() do formatu OpenAI tools[].

    Wejście (tool_descriptions):
      [{"name": "...", "description": "...", "args_schema": {...}}]

    Wyjście (OpenAI tools[]):
      [{"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}]
    """
    result = []
    for t in tools_desc:
        name = t.get("name", "")
        if not name:
            continue
        if t.get("status") == "error":
            continue

        args_schema = t.get("args_schema") or {}
        if not isinstance(args_schema, dict):
            args_schema = {}
        if "type" not in args_schema:
            args_schema = {"type": "object", "properties": args_schema}
        if "properties" not in args_schema:
            args_schema["properties"] = {}

        result.append({
            "type": "function",
            "function": {
                "name": name,
                "description": (t.get("description") or "")[:500],
                "parameters": args_schema,
            },
        })
    return result
