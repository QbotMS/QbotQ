"""QBot3 DB Introspection — transparent read-only DB access for Albert.

Albert can:
- list schemas/tables
- describe table columns
- sample rows
- execute safe SELECT with guard

Albert cannot:
- INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE
- read secrets
- write data

All reads are logged in audit.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
    _HAS_PSYCOPG = True
except ImportError:
    psycopg = None
    _HAS_PSYCOPG = False

_MAX_ROWS = int(os.getenv("QBOT3_DB_INTROSPECTION_MAX_ROWS", "50"))
_MAX_SAMPLE_ROWS = int(os.getenv("QBOT3_DB_INTROSPECTION_SAMPLE_ROWS", "5"))
_TIMEOUT_SEC = int(os.getenv("QBOT3_DB_INTROSPECTION_TIMEOUT", "10"))
_SECRET_TABLES = frozenset({
    "_secrets", "secrets", "credentials", "passwords", "tokens", "keys", "auth",
})

_SELECT_ONLY_RE = re.compile(r'^\s*SELECT\b', re.I)
_FORBIDDEN_KEYWORDS_RE = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|COPY|EXECUTE|CALL|MERGE|GRANT|REVOKE)\b',
    re.I,
)


def _db() -> Any:
    if not _HAS_PSYCOPG:
        raise RuntimeError("psycopg not available")
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
    )


def _check_secrets(table: str) -> None:
    parts = table.lower().replace('"', '').split('.')
    for part in parts:
        if part in _SECRET_TABLES:
            raise PermissionError(f"ACCESS_DENIED: table '{table}' is in secret denylist")


def _safe_select(sql: str, params: tuple | None = None) -> dict[str, Any]:
    """Execute a read-only SELECT with safety guards."""
    sql_stripped = sql.strip()
    if not _SELECT_ONLY_RE.match(sql_stripped):
        return {"status": "BLOCKED", "error": "Only SELECT statements are allowed"}
    if _FORBIDDEN_KEYWORDS_RE.search(sql_stripped):
        return {"status": "BLOCKED", "error": "Write/modify statements are not allowed"}

    # Enforce LIMIT
    if not re.search(r'\bLIMIT\s+\d+', sql_stripped, re.I):
        sql_stripped = sql_stripped.rstrip(';') + f" LIMIT {_MAX_ROWS}"

    # Enforce timeout
    import signal
    from contextlib import contextmanager

    class TimeoutError_(Exception):
        pass

    @contextmanager
    def timeout(seconds: int):
        def handler(signum, frame):
            raise TimeoutError_("query timeout")
        signal.signal(signal.SIGALRM, handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)

    try:
        with _db() as conn:
            with timeout(_TIMEOUT_SEC):
                cur = conn.execute(sql_stripped, params or ())
                rows = cur.fetchall()
        return {
            "status": "OK",
            "rows": [dict(r) for r in rows],
            "row_count": len(rows),
            "sql_audit": sql_stripped[:200],
        }
    except TimeoutError_:
        return {"status": "TIMEOUT", "error": f"query exceeded {_TIMEOUT_SEC}s timeout"}
    except Exception as exc:
        return {"status": "SQL_ERROR", "error": str(exc)[:500], "sql_audit": sql_stripped[:200]}


# ── Public tools (registered in tool_registry, NOT public MCP) ────────


def db_schema_list(_args: dict | None = None) -> dict[str, Any]:
    """List all schemas and their tables in the database."""
    try:
        with _db() as conn:
            schemas = conn.execute("""
                SELECT schema_name FROM information_schema.schemata
                WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                ORDER BY schema_name
            """).fetchall()

            result = {}
            for s in schemas:
                schema = s["schema_name"]
                tables = conn.execute("""
                    SELECT table_name, table_type FROM information_schema.tables
                    WHERE table_schema = %s ORDER BY table_name
                """, (schema,)).fetchall()
                if tables:
                    result[schema] = [t["table_name"] for t in tables]

            return {"status": "OK", "schemas": result, "schema_count": len(result)}
    except Exception as exc:
        return {"status": "DB_ERROR", "error": str(exc)[:300]}


def db_table_describe(args: dict | None = None) -> dict[str, Any]:
    """Describe columns of a table: name, type, nullable, default."""
    if not args:
        args = {}
    table = str(args.get("table", "")).strip()
    schema = str(args.get("schema", "public")).strip()
    if not table:
        return {"status": "BLOCKED", "error": "table required"}
    _check_secrets(f"{schema}.{table}")
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

            # Legacy table hint for body_composition
            hint = None
            if schema == "public" and table == "body_composition":
                hint = "⚠️ LEGACY — nie używać. Body composition znajduje się w qbot_v2.body_measurements (kanoniczna tabela Garmin)."

            return {
                "status": "OK",
                "schema": schema,
                "table": table,
                "columns": columns,
                "column_count": len(columns),
                "hint": hint,
            }
    except PermissionError:
        return {"status": "BLOCKED", "error": f"table '{table}' is in secret denylist"}
    except Exception as exc:
        return {"status": "DB_ERROR", "error": str(exc)[:300]}


def db_sample_rows(args: dict | None = None) -> dict[str, Any]:
    """Sample up to N rows from a table (safe SELECT with LIMIT)."""
    if not args:
        args = {}
    table = str(args.get("table", "")).strip()
    schema = str(args.get("schema", "public")).strip()
    limit = min(int(args.get("limit", _MAX_SAMPLE_ROWS)), _MAX_SAMPLE_ROWS)
    if not table:
        return {"status": "BLOCKED", "error": "table required"}
    _check_secrets(f"{schema}.{table}")
    full_table = f'"{schema}"."{table}"' if schema != "public" else f'"{table}"'
    return _safe_select(f"SELECT * FROM {full_table} LIMIT {limit}")


def db_select_readonly(args: dict | None = None) -> dict[str, Any]:
    """Execute a read-only SELECT query. Only SELECT allowed, LIMIT enforced."""
    if not args:
        args = {}
    sql = str(args.get("sql", "")).strip()
    if not sql:
        return {"status": "BLOCKED", "error": "sql required"}

    # Extract table names for secret check
    table_refs = re.findall(r'(?:FROM|JOIN)\s+["\']?(\w+)["\']?', sql, re.I)
    for t in table_refs:
        try:
            _check_secrets(t)
        except PermissionError:
            return {"status": "BLOCKED", "error": f"query references secret table '{t}'"}

    return _safe_select(sql)
