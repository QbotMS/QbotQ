"""Qbot artifact tools — safe PostgreSQL-backed CRUD + workspace write preview."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_WORKSPACE_ROOT: Path = Path("/opt/qbot/workspace")
_MAX_CONTENT: int = 100_000
_MAX_TITLE: int = 200
_BLOCKED_PATHS: set[str] = {".env", ".env.local", ".git", ".venv", "keys", "secrets", "token"}
_BLOCKED_DIRS: set[str] = {"systemd", "/etc", "/var", "/root"}

_SENSITIVE_WORDS: set[str] = {"password", "secret", "token", "apikey", "api_key", "pgpassword",
                               "HIKCONNECT", "GATE_TOKEN", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"}


def _has_secrets(content: str) -> bool:
    cl = content.lower()
    return any(s.lower() in cl for s in _SENSITIVE_WORDS)


def _validate_artifact(title: str, content: str) -> str | None:
    if not title or len(title) > _MAX_TITLE:
        return f"title must be 1-{_MAX_TITLE} chars"
    if not content or len(content) > _MAX_CONTENT:
        return f"content must be 1-{_MAX_CONTENT} bytes"
    if _has_secrets(content) or _has_secrets(title):
        return "content contains sensitive words — rejected"
    return None


# ──────────── qbot_artifact_create ──────────────────────────────────────

def _tool_qbot_artifact_create(args: dict | None = None) -> dict[str, Any]:
    title = str((args or {}).get("title", ""))[:_MAX_TITLE]
    content = str((args or {}).get("content", ""))[:_MAX_CONTENT]
    artifact_type = str((args or {}).get("artifact_type", "report"))
    tags = (args or {}).get("tags", []) or []
    if isinstance(tags, str):
        tags = [tags]
    source_plan_id_raw = (args or {}).get("source_plan_id")

    error = _validate_artifact(title, content)
    if error:
        return {"tool": "qbot_artifact_create", "status": "error", "error": error}

    plan_id = None
    if source_plan_id_raw is not None:
        try:
            plan_id = int(source_plan_id_raw)
        except (ValueError, TypeError):
            return {"tool": "qbot_artifact_create", "status": "error", "error": "invalid source_plan_id"}

    try:
        import psycopg
        from psycopg.rows import dict_row
        import os
        conn = psycopg.connect(
            host=os.getenv("PGHOST", "localhost"), port=os.getenv("PGPORT", "5432"),
            dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
            password=os.getenv("PGPASSWORD", ""), row_factory=dict_row,
        )
        row = conn.execute(
            """INSERT INTO qbot_artifacts (artifact_type, title, content, tags, source_plan_id)
               VALUES (%s, %s, %s, %s, %s) RETURNING id, created_at""",
            (artifact_type, title, content, json.dumps(tags), plan_id),
        ).fetchone()
        conn.commit()
        conn.close()
        return {
            "tool": "qbot_artifact_create",
            "status": "ok",
            "artifact_id": row["id"],
            "created_at": row["created_at"].isoformat(),
            "title": title,
            "artifact_type": artifact_type,
            "size_bytes": len(content.encode("utf-8")),
        }
    except Exception as exc:
        return {"tool": "qbot_artifact_create", "status": "error", "error": str(exc)}


# ──────────── qbot_artifact_list ────────────────────────────────────────

def _tool_qbot_artifact_list(args: dict | None = None) -> dict[str, Any]:
    limit_raw = (args or {}).get("limit", 20)
    try:
        limit = int(limit_raw)
    except (ValueError, TypeError):
        limit = 20
    limit = max(1, min(100, limit))

    try:
        import psycopg
        from psycopg.rows import dict_row
        import os
        conn = psycopg.connect(
            host=os.getenv("PGHOST", "localhost"), port=os.getenv("PGPORT", "5432"),
            dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
            password=os.getenv("PGPASSWORD", ""), row_factory=dict_row,
        )
        rows = conn.execute(
            "SELECT id, created_at, artifact_type, title, tags FROM qbot_artifacts ORDER BY id DESC LIMIT %s",
            (limit,),
        ).fetchall()
        conn.close()
        items = []
        for r in rows:
            tags_val = r.get("tags")
            if isinstance(tags_val, str):
                try:
                    tags_val = json.loads(tags_val)
                except Exception:
                    tags_val = []
            items.append({
                "id": r["id"], "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                "artifact_type": r["artifact_type"], "title": r["title"], "tags": tags_val,
            })
        return {"tool": "qbot_artifact_list", "count": len(items), "artifacts": items}
    except Exception as exc:
        return {"tool": "qbot_artifact_list", "status": "error", "error": str(exc)}


# ──────────── qbot_artifact_get ─────────────────────────────────────────

def _tool_qbot_artifact_get(args: dict | None = None) -> dict[str, Any]:
    artifact_id_raw = (args or {}).get("id", 0)
    try:
        artifact_id = int(artifact_id_raw)
    except (ValueError, TypeError):
        return {"tool": "qbot_artifact_get", "status": "error", "error": f"invalid id: {artifact_id_raw}"}

    try:
        import psycopg
        from psycopg.rows import dict_row
        import os
        conn = psycopg.connect(
            host=os.getenv("PGHOST", "localhost"), port=os.getenv("PGPORT", "5432"),
            dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
            password=os.getenv("PGPASSWORD", ""), row_factory=dict_row,
        )
        row = conn.execute("SELECT * FROM qbot_artifacts WHERE id = %s", (artifact_id,)).fetchone()
        conn.close()
        if not row:
            return {"tool": "qbot_artifact_get", "status": "error", "error": f"artifact {artifact_id} not found"}
        tags_val = row.get("tags")
        if isinstance(tags_val, str):
            try:
                tags_val = json.loads(tags_val)
            except Exception:
                tags_val = []
        content = row["content"]
        if len(content) > _MAX_CONTENT:
            content = content[:_MAX_CONTENT] + "...<truncated>"
        return {
            "tool": "qbot_artifact_get",
            "id": row["id"],
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "artifact_type": row["artifact_type"], "title": row["title"],
            "content": content, "tags": tags_val, "source_plan_id": row.get("source_plan_id"),
        }
    except Exception as exc:
        return {"tool": "qbot_artifact_get", "status": "error", "error": str(exc)}


# ──────────── qbot_workspace_write_file_preview ─────────────────────────

def _tool_qbot_workspace_write_file_preview(args: dict | None = None) -> dict[str, Any]:
    rel = str((args or {}).get("relative_path", ""))
    content = str((args or {}).get("content", ""))

    if not rel or not content:
        return {"tool": "qbot_workspace_write_file_preview", "status": "error", "error": "relative_path and content required"}

    if rel.startswith("/") or ".." in rel:
        return {"tool": "qbot_workspace_write_file_preview", "status": "BLOCKED",
                "would_write": False, "policy_status": "BLOCKED",
                "warnings": ["Absolute paths and '..' are blocked"]}

    parts = rel.replace("\\", "/").split("/")
    for part in parts:
        if part.lower() in _BLOCKED_PATHS or part in _BLOCKED_DIRS or part.startswith("."):
            return {"tool": "qbot_workspace_write_file_preview", "status": "BLOCKED",
                    "would_write": False, "policy_status": "BLOCKED",
                    "warnings": [f"Blocked path component: {part}"]}

    if _has_secrets(content):
        return {"tool": "qbot_workspace_write_file_preview", "status": "BLOCKED",
                "would_write": False, "policy_status": "BLOCKED",
                "warnings": ["Content contains sensitive words"]}

    target = _WORKSPACE_ROOT / rel

    return {
        "tool": "qbot_workspace_write_file_preview",
        "would_write": True,
        "target_path": str(target),
        "size_bytes": len(content.encode("utf-8")),
        "policy_status": "PREVIEW_ONLY",
        "warnings": ["This is a preview — file NOT written to disk (v1 restriction)"],
        "status": "ok",
    }
