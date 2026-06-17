"""core/incidents.py — automatyczne tickety incydentow (PRZEBUDOWA sekcja 4).

change_log = pelny audit trail. incident_tickets = wyselekcjonowany podzbior:
problemy wymagajace dzialania (ERROR, zlamany niezmiennik). Kazdy ticket
pakuje kontekst do diagnozy: zapytanie, intent, error, traceback, ostatnie
linie logow, env. Komenda /incydenty buduje gotowy-do-wklejenia prompt.

ZASADA: open_incident nigdy nie podnosi wyjatku do callera (best-effort).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

_log = logging.getLogger("qbot.incidents")


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


def _capture_log_tail(lines: int = 40) -> str:
    """Ostatnie linie logu serwisu qbot-api (best-effort)."""
    try:
        out = subprocess.run(
            ["journalctl", "-u", "qbot-api", "-n", str(lines), "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=8,
        )
        return (out.stdout or "")[-8000:]
    except Exception:
        return ""


def _env_snapshot() -> dict[str, Any]:
    """Wybrane zmienne env istotne dla diagnozy (bez sekretow)."""
    keys = (
        "QBOT_DISABLE_ALBERT_FALLBACK", "QBOT_QUERY_VNEXT_ENABLED",
        "QGPT_MODEL", "QBOT_PLANNER_ENABLED", "PGDATABASE",
    )
    return {k: os.getenv(k) for k in keys if os.getenv(k) is not None}


def _recent_duplicate_exists(summary: str) -> bool:
    """Czy istnieje otwarty ticket z tym samym summary w ostatnich 6h.

    Zapobiega zalewaniu tabeli identycznymi incydentami.
    """
    try:
        c = _conn()
        cur = c.cursor()
        cur.execute(
            """SELECT 1 FROM qbot_v2.incident_tickets
               WHERE summary = %s AND status = 'open'
                 AND created_at > now() - interval '6 hours' LIMIT 1""",
            (summary,),
        )
        row = cur.fetchone()
        c.close()
        return row is not None
    except Exception:
        return False


def open_incident(
    summary: str,
    *,
    severity: str = "medium",
    source: str | None = None,
    action_type: str | None = None,
    intent: str | None = None,
    query_text: str | None = None,
    error_text: str | None = None,
    traceback: str | None = None,
    detail: dict[str, Any] | None = None,
    change_log_id: int | None = None,
    capture_logs: bool = True,
    dedup: bool = True,
) -> int | None:
    """Utworz ticket incydentu. Zwraca id lub None. Best-effort.

    dedup=True: pomija jesli identyczny otwarty ticket powstal w ostatnich 6h.
    """
    try:
        if dedup and _recent_duplicate_exists(summary):
            return None
        log_tail = _capture_log_tail() if capture_logs else ""
        c = _conn()
        cur = c.cursor()
        cur.execute(
            """INSERT INTO qbot_v2.incident_tickets
               (severity, source, action_type, intent, query_text, summary,
                error_text, traceback, log_tail, env_snapshot, detail_json,
                change_log_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (
                severity, source, action_type, intent, query_text, summary,
                error_text, traceback, log_tail,
                json.dumps(_env_snapshot(), default=str),
                json.dumps(detail or {}, default=str)[:50000],
                change_log_id,
            ),
        )
        new_id = cur.fetchone()["id"]
        c.commit()
        c.close()
        return new_id
    except Exception as e:  # noqa: BLE001 — best-effort
        _log.warning("open_incident failed: %s", e)
        return None


def list_open_incidents(limit: int = 20) -> list[dict[str, Any]]:
    try:
        c = _conn()
        cur = c.cursor()
        cur.execute(
            """SELECT id, created_at, severity, source, action_type, intent,
                      query_text, summary, error_text
               FROM qbot_v2.incident_tickets
               WHERE status = 'open'
               ORDER BY created_at DESC LIMIT %s""",
            (limit,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        c.close()
        return rows
    except Exception as e:
        _log.warning("list_open_incidents failed: %s", e)
        return []


def get_incident(incident_id: int) -> dict[str, Any] | None:
    try:
        c = _conn()
        cur = c.cursor()
        cur.execute("SELECT * FROM qbot_v2.incident_tickets WHERE id = %s", (int(incident_id),))
        row = cur.fetchone()
        c.close()
        return dict(row) if row else None
    except Exception:
        return None


def resolve_incident(incident_id: int, resolution: str, status: str = "resolved") -> bool:
    try:
        c = _conn()
        cur = c.cursor()
        cur.execute(
            """UPDATE qbot_v2.incident_tickets
               SET status = %s, resolution = %s, updated_at = now()
               WHERE id = %s""",
            (status, resolution, int(incident_id)),
        )
        c.commit()
        c.close()
        return True
    except Exception as e:
        _log.warning("resolve_incident failed: %s", e)
        return False


def build_incident_prompt(incident_id: int | None = None) -> str:
    """Zbuduj gotowy-do-wklejenia prompt diagnostyczny dla Terminus.

    Bez incident_id: bierze najnowszy otwarty. Z incident_id: konkretny.
    """
    inc = None
    if incident_id is not None:
        inc = get_incident(incident_id)
    else:
        opened = list_open_incidents(limit=1)
        if opened:
            inc = get_incident(opened[0]["id"])
    if not inc:
        return "Brak otwartych incydentow."

    env = inc.get("env_snapshot") or {}
    env_lines = "\n".join(f"  {k}={v}" for k, v in env.items()) or "  (brak)"

    parts = [
        f"# INCYDENT QBot #{inc['id']} ({inc.get('severity', 'medium')})",
        f"Utworzony: {inc.get('created_at')}",
        f"Zrodlo: {inc.get('source')} | action_type: {inc.get('action_type')} | intent: {inc.get('intent')}",
        "",
        f"## Podsumowanie\n{inc.get('summary')}",
    ]
    if inc.get("query_text"):
        parts.append(f"\n## Zapytanie\n{inc['query_text']}")
    if inc.get("error_text"):
        parts.append(f"\n## Blad\n{inc['error_text']}")
    if inc.get("traceback"):
        parts.append(f"\n## Traceback\n```\n{inc['traceback'][:3000]}\n```")
    parts.append(f"\n## Env\n{env_lines}")
    if inc.get("log_tail"):
        parts.append(f"\n## Ostatnie linie logu (qbot-api)\n```\n{inc['log_tail'][-3000:]}\n```")
    parts.append(
        "\n## Zadanie\n"
        "Zdiagnozuj przyczyne. Przygotuj patch + test na backupie. NIE wdrazaj "
        "bez potwierdzenia. Trzymaj sie zasad: czytaj plik przed edycja, "
        "ast.parse przed zapisem, backup, smoke test po restarcie."
    )
    return "\n".join(parts)
