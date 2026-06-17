#!/usr/bin/env python3
"""QBot3 Memory — minimal conversation memory layer.

Types:
  confirmed_fact — permanent user-confirmed facts (high trust)
  conversation_summary — working summaries (lower trust)

MVP: file-based storage. Future: PostgreSQL.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_MEMORY_DIR = Path("/opt/qbot/app/data/qbot3_memory")


def _ensure_dir():
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def _memory_path(memory_type: str) -> Path:
    _ensure_dir()
    return _MEMORY_DIR / f"{memory_type}.jsonl"


def _write_memory_db(memory_type: str, content: dict[str, Any], source: str) -> None:
    import psycopg

    conn = psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        connect_timeout=5,
    )
    try:
        key = str(content.get("key", "")).strip()
        value_json = {
            "value": content.get("value"),
            "source": content.get("source", source),
        }
        confidence = str(content.get("confidence", "medium") or "medium")
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO qbot_v2.qbot_memory (memory_type, key, value, source, confidence)
                VALUES (%s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (key) DO UPDATE SET
                    created_at = now(),
                    memory_type = EXCLUDED.memory_type,
                    value = EXCLUDED.value,
                    source = EXCLUDED.source,
                    confidence = EXCLUDED.confidence
                """,
                (
                    memory_type,
                    key,
                    json.dumps(value_json, ensure_ascii=False, default=str),
                    source,
                    confidence,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def write_memory(memory_type: str, content: dict[str, Any], source: str = "qbot3") -> None:
    entry = {
        "type": memory_type,
        "content": content,
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        _write_memory_db(memory_type, content, source)
    except Exception:
        pass
    path = _memory_path(memory_type)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def read_memory(memory_type: str, limit: int = 20) -> list[dict[str, Any]]:
    path = _memory_path(memory_type)
    if not path.is_file():
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries[-limit:]


def search_memory(query: str, memory_type: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    ql = query.lower()
    results = []
    types = [memory_type] if memory_type else ["confirmed_fact", "conversation_summary"]
    for mt in types:
        for entry in read_memory(mt, limit=50):
            content_str = json.dumps(entry.get("content", {}), ensure_ascii=False).lower()
            if ql in content_str:
                results.append(entry)
    return results[:limit]


def clear_memory(memory_type: str | None = None) -> None:
    if memory_type:
        path = _memory_path(memory_type)
        if path.is_file():
            path.unlink()
    else:
        for mt in ["confirmed_fact", "conversation_summary"]:
            clear_memory(mt)
