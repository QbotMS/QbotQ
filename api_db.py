import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def _conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
    )


def init_db():
    sql_path = Path(__file__).parent / "sql" / "init_qbot.sql"
    ddl = sql_path.read_text(encoding="utf-8")
    with _conn() as conn:
        conn.execute(ddl)
        conn.commit()


def save_tool_call(tool: str, args: dict, result: dict) -> int:
    args_json = json.dumps(args or {}, ensure_ascii=False)
    result_json = json.dumps(result or {}, ensure_ascii=False)
    with _conn() as conn:
        row = conn.execute(
            "INSERT INTO tool_calls (tool, args, result) VALUES (%s, %s, %s) RETURNING id",
            (tool, args_json, result_json),
        ).fetchone()
        conn.commit()
        return row["id"]


def select_tool_calls(limit: int = 10) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, tool, args, result, created_at "
            "FROM tool_calls ORDER BY id DESC LIMIT %s",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def ping() -> bool:
    try:
        with _conn() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def db_overview() -> dict:
    with _conn() as conn:
        version_row = conn.execute("SELECT version()").fetchone()
        pg_ver = version_row["version"] if version_row else "unknown"
        count = conn.execute("SELECT COUNT(*) AS cnt FROM tool_calls").fetchone()["cnt"]
        last = conn.execute(
            "SELECT created_at FROM tool_calls ORDER BY id DESC LIMIT 1"
        ).fetchone()
        rows = conn.execute(
            "SELECT result FROM tool_calls ORDER BY id DESC LIMIT 1000"
        ).fetchall()
    ok_count = 0
    error_count = 0
    for r in rows:
        try:
            res = json.loads(r["result"]) if isinstance(r["result"], str) else (r["result"] or {})
            error_count += 1 if "error" in res else 0
            ok_count += 1 if "error" not in res else 0
        except Exception:
            ok_count += 1
    return {
        "postgres_version": pg_ver,
        "tool_calls_count": count,
        "last_tool_call_at": last["created_at"].isoformat() if last else None,
        "status_counts": {"ok": ok_count, "error": error_count},
    }
