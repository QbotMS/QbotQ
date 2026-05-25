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
