"""core/change_log.py — rejestr zmian QBot (PRZEBUDOWA sekcja 4).

Jedno miejsce zapisu "co sie zmienilo i dlaczego":
  - action_execute writes (z GPT/Planner) — kazdy write zostawia slad,
  - patche aplikowane przez agenta (kind='patch'),
  - incydenty (kind='incident').

ZASADA NADRZEDNA: log_change NIGDY nie podnosi wyjatku do callera.
Zapis do change_log nie moze zepsuc operacji ktora loguje. Wszystkie
bledy sa polykane (best-effort logging).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

_log = logging.getLogger("qbot.change_log")


def _conn():
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=5,
    )


def log_change(
    kind: str,
    *,
    action_type: str | None = None,
    status: str | None = None,
    idempotency_key: str | None = None,
    source: str | None = None,
    entity_ref: str | None = None,
    summary: str | None = None,
    detail: dict[str, Any] | None = None,
) -> int | None:
    """Zapisz wpis do qbot_v2.change_log. Zwraca id lub None przy bledzie.

    Best-effort: nigdy nie podnosi wyjatku. Bezpieczne do wolania z
    dowolnej sciezki write.
    """
    try:
        c = _conn()
        cur = c.cursor()
        cur.execute(
            """INSERT INTO qbot_v2.change_log
               (kind, action_type, status, idempotency_key, source,
                entity_ref, summary, detail_json)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (
                kind,
                action_type,
                status,
                idempotency_key,
                source,
                entity_ref,
                summary,
                json.dumps(detail or {}, default=str)[:50000],
            ),
        )
        new_id = cur.fetchone()["id"]
        c.commit()
        c.close()
        return new_id
    except Exception as e:  # noqa: BLE001 — best-effort, nigdy nie wybucha
        _log.warning("change_log insert failed (%s): %s", kind, e)
        return None


# Statusy ktore traktujemy jako "rzeczywisty write sie wydarzyl" (warto logowac
# z naciskiem). DRY_RUN/DUPLICATE/BLOCKED tez logujemy, ale jako nie-mutacje.
_WRITE_COMMITTED_STATUSES = {"OK", "PARTIAL"}


def _extract_entity_ref(action_type: str | None, result: dict[str, Any]) -> str | None:
    """Wyciagnij 'tabela:id' z wyniku action_execute, jesli sie da."""
    if not isinstance(result, dict):
        return None
    # Typowe pola id zwracane przez handlery
    candidates = (
        ("intake_logs", result.get("meal_id")),
        ("calendar_events", result.get("event_id")),
        ("reminders", result.get("reminder_id")),
        ("qbot_planning_facts", result.get("planning_fact_id")),
    )
    for table, val in candidates:
        if val:
            return f"{table}:{val}"
    return None


def log_action_execute(
    action_type: str | None,
    status: str | None,
    *,
    idempotency_key: str | None = None,
    source: str | None = None,
    payload: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> int | None:
    """Loguj wynik action_execute do change_log (best-effort).

    Loguje wszystkie nie-puste statusy. detail_json zawiera skrocony
    payload i wybrane pola wyniku (bez wielkich blobow).
    """
    try:
        result = result or {}
        entity_ref = _extract_entity_ref(action_type, result)
        committed = status in _WRITE_COMMITTED_STATUSES
        summary = f"{action_type} -> {status}"
        if entity_ref:
            summary += f" ({entity_ref})"
        detail = {
            "write_committed": committed,
            "payload": _shrink(payload),
            "result_excerpt": {
                k: result.get(k)
                for k in ("status", "error", "note", "title", "fact_type",
                          "json_changed", "meal_id", "event_id", "reminder_id",
                          "planning_fact_id", "warnings")
                if k in result
            },
        }
        return log_change(
            "action_execute",
            action_type=action_type,
            status=status,
            idempotency_key=idempotency_key,
            source=source,
            entity_ref=entity_ref,
            summary=summary,
            detail=detail,
        )
    except Exception as e:  # noqa: BLE001
        _log.warning("log_action_execute failed: %s", e)
        return None


def _shrink(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Przytnij payload do logu — usun duze pola (content_b64, content)."""
    if not isinstance(payload, dict):
        return payload
    out = {}
    for k, v in payload.items():
        if k in ("content_b64", "content", "content_markdown") and isinstance(v, str) and len(v) > 200:
            out[k] = f"<{len(v)} chars omitted>"
        else:
            out[k] = v
    return out
