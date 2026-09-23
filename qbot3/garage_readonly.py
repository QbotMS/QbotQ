"""Odczyt bazy garazu (SQLite /opt/qbot/app/data/garage.db) — tylko do odczytu.

Zabezpieczenia:
- plik otwierany w trybie ro (URI mode=ro) + PRAGMA query_only,
- authorizer SQLite przepuszcza tylko odczyt (SELECT/READ/FUNCTION),
- limit czasu 5 s (progress handler), max 200 wierszy, dlugie pola ucinane.
Kazde wywolanie -> linia GARAGE_READ_AUDIT {...} w dzienniku.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from datetime import datetime
from typing import Any

GARAGE_DB = os.getenv("QBOT_GARAGE_DB", "/opt/qbot/app/data/garage.db")
_MAX_ROWS = int(os.getenv("QBOT_GARAGE_MAX_ROWS", "200"))
_TIMEOUT_S = float(os.getenv("QBOT_GARAGE_TIMEOUT_S", "5"))
_MAX_CELL_CHARS = 4000

_SELECT_RE = re.compile(r"^\s*(SELECT|WITH)\b", re.I)
_FORBIDDEN_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE\s+INTO|ATTACH|DETACH|VACUUM|REINDEX|PRAGMA)\b", re.I
)

_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
_RECURSIVE = getattr(sqlite3, "SQLITE_RECURSIVE", None)
if _RECURSIVE is not None:
    _ALLOWED_ACTIONS.add(_RECURSIVE)


def _authorizer(action, *_a):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{GARAGE_DB}?mode=ro", uri=True, timeout=3)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA query_only = ON")
    return c


def _audit(tool: str, **fields: Any) -> None:
    try:
        rec = {"ts": datetime.now().isoformat(timespec="seconds"), "tool": tool, **fields}
        print("GARAGE_READ_AUDIT " + json.dumps(rec, ensure_ascii=False, default=str)[:1500], flush=True)
    except Exception:
        pass


def _cell(v: Any) -> Any:
    if isinstance(v, (bytes, bytearray, memoryview)):
        return f"<binary {len(bytes(v))} B>"
    if isinstance(v, str) and len(v) > _MAX_CELL_CHARS:
        return v[:_MAX_CELL_CHARS] + f"... <ucieto, {len(v)} znakow>"
    return v


def garage_tables(_args: dict | None = None) -> dict[str, Any]:
    """Lista tabel garazu z kolumnami i liczba wierszy."""
    try:
        c = _conn()
        try:
            names = [r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view') "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            tables = []
            for n in names:
                cols = [{"name": r[1], "type": r[2] or ""} for r in c.execute(f'PRAGMA table_info("{n}")')]
                cnt = c.execute(f'SELECT count(*) FROM "{n}"').fetchone()[0]
                tables.append({"table": n, "rows": cnt, "columns": cols})
        finally:
            c.close()
        _audit("garage_tables", status="OK", tables=len(tables))
        return {
            "status": "OK",
            "database": "garage.db (SQLite)",
            "tables": tables,
            "table_count": len(tables),
            "hint": ("Glowne: bikes (rowery), components (czesci; bike_id -> bikes.id), tires (opony), "
                     "gear (odziez/sprzet osobisty), equipment (torby/akcesoria), fitting (ustawienia), "
                     "trips/packing_lists/packing_items (pakowanie). Rekordy aktywne: active=1."),
        }
    except Exception as exc:
        _audit("garage_tables", status="ERROR", error=str(exc)[:200])
        return {"status": "ERROR", "error": str(exc)[:300]}


def garage_select(args: dict | None = None) -> dict[str, Any]:
    """Zapytanie SELECT / WITH na bazie garazu (SQLite). Max 200 wierszy."""
    args = args or {}
    sql = str(args.get("sql", "")).strip().rstrip(";").strip()
    if not sql:
        return {"status": "BLOCKED", "error": "sql required"}
    if ";" in sql:
        return {"status": "BLOCKED", "error": "Tylko jedno zapytanie naraz (bez ';')"}
    if not _SELECT_RE.match(sql):
        return {"status": "BLOCKED", "error": "Only SELECT / WITH ... SELECT statements are allowed"}
    if _FORBIDDEN_RE.search(sql):
        return {"status": "BLOCKED", "error": "Write/modify statements are not allowed"}
    try:
        cap = max(1, min(int(args.get("max_rows") or _MAX_ROWS), _MAX_ROWS))
    except (TypeError, ValueError):
        cap = _MAX_ROWS

    t0 = time.monotonic()
    deadline = t0 + _TIMEOUT_S
    try:
        c = _conn()
        try:
            c.set_authorizer(_authorizer)
            c.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
            cur = c.execute(sql)
            rows = cur.fetchmany(cap + 1)
        finally:
            c.close()
        truncated = len(rows) > cap
        rows = rows[:cap]
        out = [{k: _cell(r[k]) for k in r.keys()} for r in rows]
        ms = int((time.monotonic() - t0) * 1000)
        _audit("garage_select", status="OK", rows=len(out), truncated=truncated, ms=ms, sql=sql[:400])
        res = {"status": "OK", "rows": out, "row_count": len(out), "truncated": truncated, "sql_audit": sql[:200]}
        if truncated:
            res["note"] = f"Pokazano pierwsze {cap} wierszy — zawez zapytanie."
        return res
    except sqlite3.OperationalError as exc:
        msg = str(exc)
        ms = int((time.monotonic() - t0) * 1000)
        if "interrupted" in msg.lower():
            _audit("garage_select", status="TIMEOUT", ms=ms, sql=sql[:400])
            return {"status": "TIMEOUT", "error": f"zapytanie przekroczylo {int(_TIMEOUT_S)} s", "sql_audit": sql[:200]}
        if "not authorized" in msg.lower():
            _audit("garage_select", status="BLOCKED", ms=ms, sql=sql[:400])
            return {"status": "BLOCKED", "error": "operacja niedozwolona (tylko odczyt)", "sql_audit": sql[:200]}
        _audit("garage_select", status="SQL_ERROR", ms=ms, sql=sql[:400], error=msg[:200])
        return {"status": "SQL_ERROR", "error": msg[:500], "sql_audit": sql[:200]}
    except Exception as exc:
        _audit("garage_select", status="ERROR", sql=sql[:400], error=str(exc)[:200])
        return {"status": "ERROR", "error": str(exc)[:500], "sql_audit": sql[:200]}
