"""Garage/gear import tools — raw 1:1 import to PostgreSQL.

Read-only tools for audit, preview, status, list, get, and search.
One write-safe tool for import execution with dry_run=true default.
No normalization, no category invention — raw 1:1 import only.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path("/opt/qbot/app")
_OUTGOING = _PROJECT_ROOT / "outgoing"
_DATA = _PROJECT_ROOT / "data"

_MAX_TEXT_LENGTH = 500
_SENSITIVE_FIELDS = {"serial_number", "password", "token", "secret", "purchase_price"}


def _sanitize_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key in _SENSITIVE_FIELDS:
        return "[REDACTED]"
    if isinstance(value, str) and len(value) > _MAX_TEXT_LENGTH:
        return value[:_MAX_TEXT_LENGTH] + "..."
    if isinstance(value, bytes):
        return f"[BINARY {len(value)} bytes]"
    return value


def _sanitize_row(row: dict) -> dict:
    return {k: _sanitize_value(k, v) for k, v in row.items()}


def _sanitize_rows(rows: list[dict]) -> list[dict]:
    return [_sanitize_row(r) for r in rows]


def _list_files(root: Path, patterns: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pattern in patterns:
        for path in sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
            abs_path = str(path)
            if abs_path in seen:
                continue
            seen.add(abs_path)
            try:
                st = path.stat()
            except OSError:
                continue
            results.append({
                "name": path.name,
                "path": str(path.relative_to(_PROJECT_ROOT)),
                "size_bytes": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            })
    return results


def _pg_tables_exist() -> bool:
    try:
        from api_db import _conn as pg_conn
        with pg_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name IN "
                "('qbot_garage_sources','qbot_garage_raw_records','qbot_garage_import_runs')"
            ).fetchone()
            return row["cnt"] == 3
    except Exception:
        return False


def _init_pg_tables() -> dict:
    sql_path = _PROJECT_ROOT / "sql" / "garage_raw_import_v1.sql"
    if not sql_path.exists():
        return {"ok": False, "error": f"SQL file not found: {sql_path}"}
    try:
        from api_db import _conn as pg_conn
        ddl = sql_path.read_text(encoding="utf-8")
        with pg_conn() as conn:
            conn.execute(ddl)
            conn.commit()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ═══════════════════════════════════════════════════════════════════════
#  GARAGE TOOLS
# ═══════════════════════════════════════════════════════════════════════

def _tool_qbot_garage_legacy_file_audit(_args: dict | None = None) -> dict[str, Any]:
    """Scan for garage/gear source files: SQLite, CSV, JSON, reports."""
    candidate_files: list[dict[str, Any]] = []

    candidate_files.extend(_list_files(_PROJECT_ROOT, [
        "data/garage.db",
        "data/garage*.db",
        "data/gear*.json",
        "data/bike*.json",
        "data/gear*.csv",
        "data/bike*.csv",
    ]))

    candidate_files.extend(_list_files(_OUTGOING, [
        "**/gear*.csv",
        "**/gear*.json",
        "**/bike*.csv",
        "**/bike*.json",
        "**/garage*.csv",
        "**/garage*.json",
        "**/reports/*.json",
    ]))

    candidate_files.extend(_list_files(_PROJECT_ROOT, [
        "outgoing/*garage*.json",
        "outgoing/*gear*.json",
        "outgoing/*bike*.json",
    ]))

    garage_db = _DATA / "garage.db"
    sqlite_found = garage_db.exists()
    total_files = len(candidate_files)
    total_size = sum(f["size_bytes"] for f in candidate_files)

    status = "OK" if candidate_files else "WARN"

    return {
        "tool": "qbot_garage_legacy_file_audit",
        "status": status,
        "safety_class": "READ_ONLY",
        "sqlite_garage_db_found": sqlite_found,
        "sqlite_path": str(garage_db.relative_to(_PROJECT_ROOT)) if sqlite_found else None,
        "total_files": total_files,
        "total_size_bytes": total_size,
        "candidate_files": candidate_files[:50],
        "notes": (
            "Read-only file scan. Source file is data/garage.db (SQLite). "
            "No mutations performed."
        ),
    }


def _tool_qbot_garage_import_preview(_args: dict | None = None) -> dict[str, Any]:
    """Read data/garage.db SQLite and show table names, row counts, sample rows.

    Args: {"limit_rows_per_table": 3} — max sample rows per table.
    No import performed. Read-only.
    """
    _args = _args or {}
    limit = min(max(int(_args.get("limit_rows_per_table", 3)), 1), 20)

    garage_db = _DATA / "garage.db"
    if not garage_db.exists():
        return {
            "tool": "qbot_garage_import_preview",
            "status": "WARN",
            "safety_class": "READ_ONLY",
            "garage_db_found": False,
            "garage_db_path": str(garage_db.relative_to(_PROJECT_ROOT)),
            "tables": [],
            "notes": "data/garage.db not found. Nothing to preview.",
        }

    tables: list[dict[str, Any]] = []
    total_rows = 0

    try:
        conn = sqlite3.connect(str(garage_db))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        table_names = [r["name"] for r in cur.fetchall()]

        for tname in table_names:
            cur.execute(f'SELECT COUNT(*) AS cnt FROM "{tname}"')
            row_count = cur.fetchone()["cnt"]
            total_rows += row_count

            cur.execute(f'SELECT * FROM "{tname}" LIMIT {limit}')
            samples_raw = [dict(r) for r in cur.fetchall()]
            samples = _sanitize_rows(samples_raw)

            cur.execute(f'PRAGMA table_info("{tname}")')
            columns = [r["name"] for r in cur.fetchall()]

            tables.append({
                "table": tname,
                "row_count": row_count,
                "columns": columns,
                "sample_rows": samples,
            })

        conn.close()
    except Exception as exc:
        return {
            "tool": "qbot_garage_import_preview",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "garage_db_found": True,
            "error": str(exc),
            "notes": "Failed to read data/garage.db.",
        }

    return {
        "tool": "qbot_garage_import_preview",
        "status": "OK",
        "safety_class": "READ_ONLY",
        "garage_db_found": True,
        "garage_db_path": str(garage_db.relative_to(_PROJECT_ROOT)),
        "garage_db_size_bytes": garage_db.stat().st_size,
        "total_tables": len(tables),
        "total_rows": total_rows,
        "tables": tables,
        "notes": (
            "Read-only preview of data/garage.db. "
            f"Sample rows are sanitized (sensitive fields redacted, text truncated at {_MAX_TEXT_LENGTH} chars). "
            "No import performed."
        ),
    }


def _tool_qbot_garage_import_execute(_args: dict | None = None) -> dict[str, Any]:
    """Import garage.db data into PostgreSQL tables (1:1 raw import).

    Args:
        {"source": "garage.db", "dry_run": true}
        dry_run defaults to true for safety.
        When dry_run=false: compute SHA256 of source, check dedup,
        insert raw records 1:1 without normalization.

    Tables: qbot_garage_sources, qbot_garage_raw_records, qbot_garage_import_runs.
    Tables must exist first (run sql/garage_raw_import_v1.sql).
    """
    _args = _args or {}
    source = str(_args.get("source", "garage.db"))
    dry_run = bool(_args.get("dry_run", True))

    allowed_sources = {"garage.db"}
    if source not in allowed_sources:
        return {
            "tool": "qbot_garage_import_execute",
            "status": "BLOCKED_UNKNOWN_SOURCE",
            "safety_class": "WRITE_SAFE",
            "source": source,
            "allowed_sources": sorted(allowed_sources),
            "notes": f"Source '{source}' not in allowlist.",
        }

    garage_db = _DATA / "garage.db"
    if not garage_db.exists():
        return {
            "tool": "qbot_garage_import_execute",
            "status": "WARN",
            "safety_class": "WRITE_SAFE",
            "source": source,
            "garage_db_found": False,
            "notes": "data/garage.db not found. Nothing to import.",
        }

    if not _pg_tables_exist():
        init_result = _init_pg_tables()
        if not init_result["ok"]:
            return {
                "tool": "qbot_garage_import_execute",
                "status": "BLOCKED_NO_TABLES",
                "safety_class": "WRITE_SAFE",
                "source": source,
                "tables_exist": False,
                "init_error": init_result.get("error"),
                "notes": (
                    "PostgreSQL tables (qbot_garage_sources, qbot_garage_raw_records, "
                    "qbot_garage_import_runs) do not exist and could not be created. "
                    "Run sql/garage_raw_import_v1.sql manually."
                ),
            }

    source_bytes = garage_db.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    source_size = len(source_bytes)

    from api_db import _conn as pg_conn

    existing = None
    try:
        with pg_conn() as conn:
            existing = conn.execute(
                "SELECT id, created_at FROM qbot_garage_sources WHERE source_sha256=%s",
                (source_sha256,),
            ).fetchone()
    except Exception as exc:
        return {
            "tool": "qbot_garage_import_execute",
            "status": "ERROR",
            "safety_class": "WRITE_SAFE",
            "source": source,
            "error": str(exc),
            "notes": "Failed to check existing imports.",
        }

    if dry_run:
        return {
            "tool": "qbot_garage_import_execute",
            "status": "DRY_RUN",
            "safety_class": "WRITE_SAFE",
            "dry_run": True,
            "source": source,
            "source_sha256": source_sha256,
            "source_size_bytes": source_size,
            "already_imported": bool(existing),
            "existing_import_at": existing["created_at"].isoformat() if existing else None,
            "tables_exist": True,
            "would_import": not bool(existing),
            "notes": (
                "Dry-run only. Set dry_run=false to execute import. "
                + ("Source already imported — would skip." if existing else "Would proceed with import.")
            ),
        }

    if existing:
        source_id = existing["id"]
        try:
            with pg_conn() as conn:
                count = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM qbot_garage_raw_records WHERE source_id=%s",
                    (source_id,),
                ).fetchone()["cnt"]
                last_run = conn.execute(
                    "SELECT * FROM qbot_garage_import_runs WHERE source_id=%s ORDER BY id DESC LIMIT 1",
                    (source_id,),
                ).fetchone()
        except Exception as exc:
            return {
                "tool": "qbot_garage_import_execute",
                "status": "ERROR",
                "safety_class": "WRITE_SAFE",
                "error": str(exc),
                "notes": "Failed to query existing import records.",
            }

        return {
            "tool": "qbot_garage_import_execute",
            "status": "SKIPPED_ALREADY_IMPORTED",
            "safety_class": "WRITE_SAFE",
            "dry_run": False,
            "source": source,
            "source_sha256": source_sha256,
            "already_imported": True,
            "existing_source_id": source_id,
            "existing_import_at": existing["created_at"].isoformat(),
            "existing_count": count,
            "last_run": dict(last_run) if last_run else None,
            "notes": "Source already imported. Skipping duplicate import.",
        }

    try:
        sqlite_conn = sqlite3.connect(str(garage_db))

        with pg_conn() as pg:
            with pg.transaction():
                source_result = pg.execute(
                    "INSERT INTO qbot_garage_sources (source_path, source_sha256, file_size_bytes, source_type) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    (str(garage_db.relative_to(_PROJECT_ROOT)), source_sha256, source_size, "sqlite"),
                ).fetchone()
                source_id = source_result["id"]

                table_counts: dict[str, int] = {}
                total_imported = 0

                for tname in _source_tables(sqlite_conn):
                    columns = _table_columns(sqlite_conn, tname)
                    sqlite_conn.row_factory = sqlite3.Row
                    cur = sqlite_conn.execute(f'SELECT * FROM "{tname}"')
                    rows = [dict(r) for r in cur.fetchall()]
                    table_counts[tname] = len(rows)

                    for idx, row in enumerate(rows):
                        pg.execute(
                            "INSERT INTO qbot_garage_raw_records "
                            "(source_id, source_table, record_index, raw_data) "
                            "VALUES (%s, %s, %s, %s)",
                            (source_id, tname, idx, json.dumps(row, ensure_ascii=False)),
                        )
                        total_imported += 1

                pg.execute(
                    "INSERT INTO qbot_garage_import_runs "
                    "(source_id, rows_imported, table_counts, status, started_at, finished_at) "
                    "VALUES (%s, %s, %s, %s, NOW(), NOW())",
                    (
                        source_id,
                        total_imported,
                        json.dumps(table_counts, ensure_ascii=False),
                        "completed",
                    ),
                )

        sqlite_conn.close()
    except Exception as exc:
        return {
            "tool": "qbot_garage_import_execute",
            "status": "ERROR",
            "safety_class": "WRITE_SAFE",
            "dry_run": False,
            "source": source,
            "source_sha256": source_sha256,
            "error": str(exc),
            "notes": "Import failed. No partial data committed (transaction rolled back).",
        }

    return {
        "tool": "qbot_garage_import_execute",
        "status": "OK",
        "safety_class": "WRITE_SAFE",
        "dry_run": False,
        "source": source,
        "source_sha256": source_sha256,
        "source_size_bytes": source_size,
        "source_id": source_id,
        "rows_imported": total_imported,
        "table_counts": table_counts,
        "notes": f"Imported {total_imported} rows across {len(table_counts)} tables. 1:1 raw import, no normalization.",
    }


def _source_tables(sconn: sqlite3.Connection) -> list[str]:
    cur = sconn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [r[0] for r in cur.fetchall()]


def _table_columns(sconn: sqlite3.Connection, table: str) -> list[str]:
    cur = sconn.execute(f'PRAGMA table_info("{table}")')
    return [r[1] for r in cur.fetchall()]


def _tool_qbot_garage_raw_status(_args: dict | None = None) -> dict[str, Any]:
    """Show source files found, last import run, total raw records, safety class."""
    audit = _tool_qbot_garage_legacy_file_audit()

    last_run = None
    total_raw = 0
    sources_count = 0
    pg_reachable = False

    try:
        from api_db import _conn as pg_conn
        with pg_conn() as conn:
            pg_reachable = True
            src_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM qbot_garage_sources"
            ).fetchone()
            sources_count = src_count["cnt"] if src_count else 0

            raw_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM qbot_garage_raw_records"
            ).fetchone()
            total_raw = raw_count["cnt"] if raw_count else 0

            lr = conn.execute(
                "SELECT * FROM qbot_garage_import_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if lr:
                last_run = {
                    "id": lr["id"],
                    "source_id": lr["source_id"],
                    "rows_imported": lr["rows_imported"],
                    "table_counts": lr["table_counts"] if isinstance(lr["table_counts"], dict) else json.loads(lr["table_counts"]) if isinstance(lr["table_counts"], str) else {},
                    "status": lr["status"],
                    "started_at": lr["started_at"].isoformat() if lr["started_at"] else None,
                    "finished_at": lr["finished_at"].isoformat() if lr["finished_at"] else None,
                }
    except Exception:
        pass

    return {
        "tool": "qbot_garage_raw_status",
        "status": "OK" if total_raw > 0 else "WARN",
        "safety_class": "READ_ONLY",
        "source_files": {
            "count": audit.get("total_files", 0),
            "candidates": audit.get("candidate_files", [])[:10],
        },
        "sqlite_garage_db_found": audit.get("sqlite_garage_db_found", False),
        "postgres_reachable": pg_reachable,
        "pg_sources_count": sources_count,
        "pg_total_raw_records": total_raw,
        "last_import_run": last_run,
        "notes": (
            "Read-only status. source_files from filesystem scan, "
            "pg_* from PostgreSQL (qbot_garage_sources, qbot_garage_raw_records, qbot_garage_import_runs)."
        ),
    }


def _tool_qbot_garage_raw_list(_args: dict | None = None) -> dict[str, Any]:
    """List raw records from PostgreSQL.

    Args: {"table": "qbot_garage_raw_records", "limit": 50}
    Sanitizes output.
    """
    _args = _args or {}
    table = str(_args.get("table", "qbot_garage_raw_records"))
    limit = min(max(int(_args.get("limit", 50)), 1), 200)

    allowed_tables = {"qbot_garage_raw_records", "qbot_garage_sources", "qbot_garage_import_runs"}
    if table not in allowed_tables:
        return {
            "tool": "qbot_garage_raw_list",
            "status": "BLOCKED_UNKNOWN_TABLE",
            "safety_class": "READ_ONLY",
            "table": table,
            "allowed_tables": sorted(allowed_tables),
            "notes": f"Table '{table}' not in allowlist.",
        }

    if not _pg_tables_exist():
        return {
            "tool": "qbot_garage_raw_list",
            "status": "BLOCKED_NO_TABLES",
            "safety_class": "READ_ONLY",
            "table": table,
            "notes": "PostgreSQL garage tables do not exist. Run sql/garage_raw_import_v1.sql first.",
        }

    try:
        from api_db import _conn as pg_conn
        with pg_conn() as conn:
            if table == "qbot_garage_raw_records":
                rows = conn.execute(
                    "SELECT id, source_id, source_table, record_index, raw_data, created_at "
                    "FROM qbot_garage_raw_records ORDER BY id ASC LIMIT %s",
                    (limit,),
                ).fetchall()
            elif table == "qbot_garage_sources":
                rows = conn.execute(
                    "SELECT * FROM qbot_garage_sources ORDER BY id DESC LIMIT %s",
                    (limit,),
                ).fetchall()
            elif table == "qbot_garage_import_runs":
                rows = conn.execute(
                    "SELECT * FROM qbot_garage_import_runs ORDER BY id DESC LIMIT %s",
                    (limit,),
                ).fetchall()
            else:
                rows = []

            total = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM {table}"
            ).fetchone()["cnt"]

    except Exception as exc:
        return {
            "tool": "qbot_garage_raw_list",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "table": table,
            "error": str(exc),
            "notes": "Failed to list records.",
        }

    sanitized: list[dict] = []
    for r in rows:
        row_dict = dict(r)
        if table == "qbot_garage_raw_records" and "raw_data" in row_dict:
            raw_data = row_dict["raw_data"]
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except json.JSONDecodeError:
                    pass
            if isinstance(raw_data, dict):
                row_dict["raw_data"] = _sanitize_row(raw_data)
        elif table != "qbot_garage_raw_records":
            row_dict = _sanitize_row(row_dict)
        if "created_at" in row_dict and row_dict["created_at"] is not None:
            try:
                row_dict["created_at"] = row_dict["created_at"].isoformat()
            except AttributeError:
                pass
        sanitized.append(row_dict)

    return {
        "tool": "qbot_garage_raw_list",
        "status": "OK" if sanitized else "WARN",
        "safety_class": "READ_ONLY",
        "table": table,
        "total_rows_in_table": total,
        "returned": len(sanitized),
        "limit": limit,
        "rows": sanitized,
        "notes": f"Read-only list. {len(sanitized)} of {total} rows from {table}.",
    }


def _tool_qbot_garage_raw_get(_args: dict | None = None) -> dict[str, Any]:
    """Get a single raw record by id.

    Args: {"record_id": 1}
    """
    _args = _args or {}
    record_id = int(_args.get("record_id", 1))

    if not _pg_tables_exist():
        return {
            "tool": "qbot_garage_raw_get",
            "status": "BLOCKED_NO_TABLES",
            "safety_class": "READ_ONLY",
            "notes": "PostgreSQL garage tables do not exist. Run sql/garage_raw_import_v1.sql first.",
        }

    try:
        from api_db import _conn as pg_conn
        with pg_conn() as conn:
            row = conn.execute(
                "SELECT id, source_id, source_table, record_index, raw_data, created_at "
                "FROM qbot_garage_raw_records WHERE id=%s",
                (record_id,),
            ).fetchone()

            if not row:
                return {
                    "tool": "qbot_garage_raw_get",
                    "status": "NOT_FOUND",
                    "safety_class": "READ_ONLY",
                    "record_id": record_id,
                    "notes": f"No record found with id={record_id}.",
                }

            row_dict = dict(row)

            source_info = conn.execute(
                "SELECT source_path, source_sha256 FROM qbot_garage_sources WHERE id=%s",
                (row_dict["source_id"],),
            ).fetchone()

    except Exception as exc:
        return {
            "tool": "qbot_garage_raw_get",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "record_id": record_id,
            "error": str(exc),
            "notes": "Failed to get record.",
        }

    raw_data = row_dict["raw_data"]
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except json.JSONDecodeError:
            pass
    if isinstance(raw_data, dict):
        raw_data = _sanitize_row(raw_data)

    if row_dict.get("created_at"):
        try:
            row_dict["created_at"] = row_dict["created_at"].isoformat()
        except AttributeError:
            pass

    return {
        "tool": "qbot_garage_raw_get",
        "status": "OK",
        "safety_class": "READ_ONLY",
        "record_id": record_id,
        "source_id": row_dict["source_id"],
        "source_table": row_dict["source_table"],
        "record_index": row_dict["record_index"],
        "raw_data": raw_data,
        "created_at": row_dict.get("created_at"),
        "source": {
            "path": source_info["source_path"] if source_info else None,
            "sha256": source_info["source_sha256"] if source_info else None,
        },
        "notes": "Read-only record retrieval. Sensitive fields redacted.",
    }


def _tool_qbot_garage_raw_search(_args: dict | None = None) -> dict[str, Any]:
    """LIKE search across raw records (JSONB text).

    Args: {"query": "rower", "limit": 20}
    Read-only.
    """
    _args = _args or {}
    query = str(_args.get("query", "")).strip()
    limit = min(max(int(_args.get("limit", 20)), 1), 100)

    if not query:
        return {
            "tool": "qbot_garage_raw_search",
            "status": "BLOCKED_EMPTY_QUERY",
            "safety_class": "READ_ONLY",
            "notes": "Query string is required.",
        }

    if len(query) < 2:
        return {
            "tool": "qbot_garage_raw_search",
            "status": "BLOCKED_QUERY_TOO_SHORT",
            "safety_class": "READ_ONLY",
            "query": query,
            "notes": "Query must be at least 2 characters.",
        }

    if not _pg_tables_exist():
        return {
            "tool": "qbot_garage_raw_search",
            "status": "BLOCKED_NO_TABLES",
            "safety_class": "READ_ONLY",
            "notes": "PostgreSQL garage tables do not exist. Run sql/garage_raw_import_v1.sql first.",
        }

    pattern = f"%{query}%"

    try:
        from api_db import _conn as pg_conn
        with pg_conn() as conn:
            rows = conn.execute(
                "SELECT id, source_id, source_table, record_index, raw_data, created_at "
                "FROM qbot_garage_raw_records "
                "WHERE raw_data::text ILIKE %s "
                "ORDER BY id ASC LIMIT %s",
                (pattern, limit),
            ).fetchall()

            total_matches = conn.execute(
                "SELECT COUNT(*) AS cnt FROM qbot_garage_raw_records "
                "WHERE raw_data::text ILIKE %s",
                (pattern,),
            ).fetchone()["cnt"]

    except Exception as exc:
        return {
            "tool": "qbot_garage_raw_search",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "query": query,
            "error": str(exc),
            "notes": "Search failed.",
        }

    sanitized: list[dict] = []
    for r in rows:
        row_dict = dict(r)
        raw_data = row_dict["raw_data"]
        if isinstance(raw_data, str):
            try:
                raw_data = json.loads(raw_data)
            except json.JSONDecodeError:
                pass
        if isinstance(raw_data, dict):
            row_dict["raw_data"] = _sanitize_row(raw_data)
        if row_dict.get("created_at"):
            try:
                row_dict["created_at"] = row_dict["created_at"].isoformat()
            except AttributeError:
                pass
        sanitized.append(row_dict)

    return {
        "tool": "qbot_garage_raw_search",
        "status": "OK" if sanitized else "NO_MATCHES",
        "safety_class": "READ_ONLY",
        "query": query,
        "total_matches": total_matches,
        "returned": len(sanitized),
        "limit": limit,
        "results": sanitized,
        "notes": (
            f"Read-only ILIKE search across raw_data::text. "
            f"Found {total_matches} total matches, returning {len(sanitized)}."
        ),
    }
