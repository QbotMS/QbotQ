"""QBot3 DB Introspection — przejrzysty odczyt bazy dla Alberta i publicznego MCP.

Mozliwe:
- lista schematow/tabel
- kolumny tabeli
- probka wierszy
- zapytanie SELECT / WITH ... SELECT

Niemozliwe (egzekwuje BAZA, nie tylko filtr tekstu):
- jakikolwiek zapis/zmiana — polaczenie idzie kontem qbot_ro
  (tylko GRANT SELECT, default_transaction_read_only=on, statement_timeout=5s,
  kolumny token w ride_invite/wyprawa_rsvp bez dostepu).
- brak danych logowania qbot_ro => blad (NIGDY fallback na konto wlasciciela qbot).

Kazde zapytanie trafia do dziennika (journal) jako linia DB_READ_AUDIT {...}.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import date, datetime, time as dtime
from decimal import Decimal
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
    _HAS_PSYCOPG = True
except ImportError:
    psycopg = None
    _HAS_PSYCOPG = False

_MAX_ROWS = int(os.getenv("QBOT3_DB_INTROSPECTION_MAX_ROWS", "200"))
_MAX_SAMPLE_ROWS = int(os.getenv("QBOT3_DB_INTROSPECTION_SAMPLE_ROWS", "20"))
_TIMEOUT_MS = int(os.getenv("QBOT3_DB_INTROSPECTION_TIMEOUT_MS", "5000"))
_MAX_CELL_CHARS = int(os.getenv("QBOT3_DB_INTROSPECTION_MAX_CELL", "4000"))
_ENV_LOCAL = "/opt/qbot/app/.env.local"

_SECRET_TABLES = frozenset({
    "_secrets", "secrets", "credentials", "passwords", "tokens", "keys", "auth",
})

_SELECT_ONLY_RE = re.compile(r'^\s*(SELECT|WITH)\b', re.I)
# Obrona w glebi (baza i tak odrzuci zapis). REPLACE usuniete — to tez zwykla funkcja tekstowa.
_FORBIDDEN_KEYWORDS_RE = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|COPY|EXECUTE|CALL|MERGE|GRANT|REVOKE|VACUUM|LOCK|NOTIFY|LISTEN)\b',
    re.I,
)


def _ro_creds() -> tuple[str, str]:
    user = os.getenv("PGRO_USER", "")
    pw = os.getenv("PGRO_PASSWORD", "")
    if user and pw:
        return user, pw
    try:
        vals: dict[str, str] = {}
        with open(_ENV_LOCAL, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("PGRO_") and "=" in line:
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip().strip('"').strip("'")
        user = vals.get("PGRO_USER", "")
        pw = vals.get("PGRO_PASSWORD", "")
    except OSError:
        pass
    if not (user and pw):
        raise RuntimeError("brak danych konta tylko-do-odczytu (PGRO_USER/PGRO_PASSWORD)")
    return user, pw


def _db() -> Any:
    if not _HAS_PSYCOPG:
        raise RuntimeError("psycopg not available")
    user, pw = _ro_creds()
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=user, password=pw,
        row_factory=dict_row, connect_timeout=5,
        options=f"-c statement_timeout={_TIMEOUT_MS} -c default_transaction_read_only=on",
    )


def _audit(tool: str, **fields: Any) -> None:
    try:
        rec = {"ts": datetime.now().isoformat(timespec="seconds"), "tool": tool, **fields}
        print("DB_READ_AUDIT " + json.dumps(rec, ensure_ascii=False, default=str)[:1500], flush=True)
    except Exception:
        pass


def _cell(v: Any) -> Any:
    if isinstance(v, (datetime, date, dtime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return f"<binary {len(bytes(v))} B>"
    if isinstance(v, str) and len(v) > _MAX_CELL_CHARS:
        return v[:_MAX_CELL_CHARS] + f"... <ucieto, {len(v)} znakow>"
    if isinstance(v, (dict, list)):
        s = json.dumps(v, ensure_ascii=False, default=str)
        if len(s) > _MAX_CELL_CHARS:
            return s[:_MAX_CELL_CHARS] + f"... <ucieto, {len(s)} znakow>"
    return v


def _check_secrets(table: str) -> None:
    parts = table.lower().replace('"', '').split('.')
    for part in parts:
        if part in _SECRET_TABLES:
            raise PermissionError(f"ACCESS_DENIED: table '{table}' is in secret denylist")


def _safe_select(sql: str, params: tuple | None = None, *, tool: str = "db_select_readonly",
                 max_rows: int | None = None) -> dict[str, Any]:
    """Odczyt SELECT/WITH kontem qbot_ro. Limit wierszy liczony po stronie Pythona (fetchmany)."""
    sql_stripped = sql.strip().rstrip(";").strip()
    if ";" in sql_stripped:
        return {"status": "BLOCKED", "error": "Tylko jedno zapytanie naraz (bez ';')"}
    if not _SELECT_ONLY_RE.match(sql_stripped):
        return {"status": "BLOCKED", "error": "Only SELECT / WITH ... SELECT statements are allowed"}
    if _FORBIDDEN_KEYWORDS_RE.search(sql_stripped):
        return {"status": "BLOCKED", "error": "Write/modify statements are not allowed"}

    cap = max(1, min(int(max_rows or _MAX_ROWS), _MAX_ROWS))
    t0 = time.monotonic()
    try:
        with _db() as conn:
            cur = conn.execute(sql_stripped, params or ())
            rows = cur.fetchmany(cap + 1) if cur.description else []
            conn.rollback()
        truncated = len(rows) > cap
        rows = rows[:cap]
        out_rows = [{k: _cell(v) for k, v in dict(r).items()} for r in rows]
        ms = int((time.monotonic() - t0) * 1000)
        _audit(tool, status="OK", rows=len(out_rows), truncated=truncated, ms=ms, sql=sql_stripped[:400])
        res = {
            "status": "OK",
            "rows": out_rows,
            "row_count": len(out_rows),
            "truncated": truncated,
            "sql_audit": sql_stripped[:200],
        }
        if truncated:
            res["note"] = f"Pokazano pierwsze {cap} wierszy — zawez zapytanie (WHERE/LIMIT/agregacja)."
        return res
    except Exception as exc:
        msg = str(exc)[:500]
        ms = int((time.monotonic() - t0) * 1000)
        status = "TIMEOUT" if "statement timeout" in msg.lower() or "canceling statement" in msg.lower() else "SQL_ERROR"
        if status == "TIMEOUT":
            msg = f"zapytanie przekroczylo {_TIMEOUT_MS // 1000} s — uprosc je lub zawez"
        _audit(tool, status=status, ms=ms, sql=sql_stripped[:400], error=msg[:200])
        return {"status": status, "error": msg, "sql_audit": sql_stripped[:200]}


# ── Public tools (Albert: tool_registry; publiczny MCP: qbot3/adapters/mcp_adapter.py) ──


def db_schema_list(_args: dict | None = None) -> dict[str, Any]:
    """Lista schematow i tabel widocznych dla konta qbot_ro."""
    try:
        with _db() as conn:
            rows = conn.execute("""
                SELECT table_schema, table_name FROM information_schema.tables
                WHERE table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                ORDER BY table_schema, table_name
            """).fetchall()
        result: dict[str, list[str]] = {}
        for r in rows:
            result.setdefault(r["table_schema"], []).append(r["table_name"])
        _audit("db_schema_list", status="OK", tables=len(rows))
        return {
            "status": "OK",
            "schemas": result,
            "schema_count": len(result),
            "hint": "Dane biezace sa w schemacie qbot_v2. public = czesciowo legacy, archive = archiwum.",
        }
    except Exception as exc:
        _audit("db_schema_list", status="DB_ERROR", error=str(exc)[:200])
        return {"status": "DB_ERROR", "error": str(exc)[:300]}


def db_table_describe(args: dict | None = None) -> dict[str, Any]:
    """Describe columns of a table: name, type, nullable, default."""
    if not args:
        args = {}
    table = str(args.get("table", "")).strip()
    schema = str(args.get("schema", "public")).strip()
    if "." in table and not args.get("schema"):
        schema, table = table.split(".", 1)
    if not table:
        return {"status": "BLOCKED", "error": "table required"}
    try:
        _check_secrets(f"{schema}.{table}")
    except PermissionError:
        return {"status": "BLOCKED", "error": f"table '{table}' is in secret denylist"}
    try:
        with _db() as conn:
            cols = conn.execute("""
                SELECT column_name, data_type, is_nullable, column_default, character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
            """, (schema, table)).fetchall()

            pk_cols = set()
            try:
                pk = conn.execute("""
                    SELECT kcu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                    WHERE tc.table_schema = %s AND tc.table_name = %s
                        AND tc.constraint_type = 'PRIMARY KEY'
                """, (schema, table)).fetchall()
                pk_cols = {r["column_name"] for r in pk}
            except Exception:
                pass

            approx_rows = None
            try:
                rr = conn.execute("""
                    SELECT c.reltuples::bigint AS n FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = %s AND c.relname = %s
                """, (schema, table)).fetchone()
                if rr and rr["n"] is not None and rr["n"] >= 0:
                    approx_rows = int(rr["n"])
            except Exception:
                pass

        columns = []
        for c in cols:
            columns.append({
                "name": c["column_name"],
                "type": c["data_type"],
                "nullable": c["is_nullable"] == "YES",
                "default": c["column_default"],
                "max_length": c["character_maximum_length"],
                "is_pk": c["column_name"] in pk_cols,
            })

        hint = None
        if schema == "public" and table == "body_composition":
            hint = "⚠️ LEGACY — nie używać. Body composition znajduje się w qbot_v2.body_measurements (kanoniczna tabela Garmin)."
        if not columns:
            hint = f"Brak tabeli {schema}.{table} albo brak do niej dostepu. Sprawdz db_schema_list (dane biezace: schema qbot_v2)."

        _audit("db_table_describe", status="OK", table=f"{schema}.{table}", columns=len(columns))
        return {
            "status": "OK",
            "schema": schema,
            "table": table,
            "columns": columns,
            "column_count": len(columns),
            "approx_rows": approx_rows,
            "hint": hint,
        }
    except Exception as exc:
        _audit("db_table_describe", status="DB_ERROR", table=f"{schema}.{table}", error=str(exc)[:200])
        return {"status": "DB_ERROR", "error": str(exc)[:300]}


def db_sample_rows(args: dict | None = None) -> dict[str, Any]:
    """Probka wierszy tabeli (SELECT * ... LIMIT n)."""
    if not args:
        args = {}
    table = str(args.get("table", "")).strip()
    schema = str(args.get("schema", "public")).strip()
    if "." in table and not args.get("schema"):
        schema, table = table.split(".", 1)
    try:
        limit = min(max(int(args.get("limit", 5)), 1), _MAX_SAMPLE_ROWS)
    except (TypeError, ValueError):
        limit = 5
    if not table:
        return {"status": "BLOCKED", "error": "table required"}
    if not re.fullmatch(r"\w+", table) or not re.fullmatch(r"\w+", schema):
        return {"status": "BLOCKED", "error": "invalid table/schema name"}
    try:
        _check_secrets(f"{schema}.{table}")
    except PermissionError:
        return {"status": "BLOCKED", "error": f"table '{table}' is in secret denylist"}
    return _safe_select(f'SELECT * FROM "{schema}"."{table}" LIMIT {limit}', tool="db_sample_rows")


def db_select_readonly(args: dict | None = None) -> dict[str, Any]:
    """Zapytanie tylko do odczytu (SELECT lub WITH ... SELECT). Max 200 wierszy."""
    if not args:
        args = {}
    sql = str(args.get("sql", "")).strip()
    if not sql:
        return {"status": "BLOCKED", "error": "sql required"}

    table_refs = re.findall(r'(?:FROM|JOIN)\s+["\']?([\w.]+)["\']?', sql, re.I)
    for t in table_refs:
        try:
            _check_secrets(t)
        except PermissionError:
            return {"status": "BLOCKED", "error": f"query references secret table '{t}'"}

    return _safe_select(sql, tool=str(args.get("_tool") or "db_select_readonly"), max_rows=args.get("max_rows"))
