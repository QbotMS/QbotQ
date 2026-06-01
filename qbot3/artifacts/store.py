"""QBot Artifacts Store.

Controlled workspace store for persistent artifacts.
All paths are relative to /opt/qbot/artifacts.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

ARTIFACTS_ROOT = Path("/opt/qbot/artifacts")
SQL_PATH = Path(__file__).resolve().parents[2] / "sql" / "qbot_artifacts_v1.sql"

_TYPE_DIR = {
    "route": "projects",
    "poi": "projects",
    "plan": "projects",
    "report": "reports",
    "export": "projects",
    "database": "domains",
    "import": "imports",
    "document": "projects",
}

_TTL_DAYS = {"tmp": 7, "import": 30, "report": 365}
_BASE_PROJECT_ID = "tuscany_2026"
_GARAGE_ARTIFACT_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
_GARAGE_IDEMPOTENCY_KEY = "garage_db_main"


def _db_conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "5")),
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_path(rel_path: str) -> Path:
    full = (ARTIFACTS_ROOT / rel_path).resolve()
    root = ARTIFACTS_ROOT.resolve()
    if not str(full).startswith(str(root)):
        raise ValueError(f"Niedozwolona ścieżka: {rel_path}")
    return full


def _versioned_path(abs_dir: Path, filename: str) -> Path:
    candidate = abs_dir / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for version in range(2, 1000):
        alt = abs_dir / f"{stem}_v{version}{suffix}"
        if not alt.exists():
            return alt
    raise RuntimeError(f"Nie mogę znaleźć wolnej nazwy dla {candidate.name}")


def _artifact_sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8")


def ensure_schema() -> None:
    if not SQL_PATH.exists():
        raise FileNotFoundError(f"SQL file missing: {SQL_PATH}")
    with _db_conn() as conn:
        conn.execute(_artifact_sql())
        conn.commit()


def _seed_garage_artifact() -> None:
    garage_path = ARTIFACTS_ROOT / "domains/garage/garage.db"
    if not garage_path.exists():
        return

    size_bytes = garage_path.stat().st_size
    sha256 = _sha256(garage_path)
    metadata = {
        "description": "Baza sprzętu rowerowego MS",
        "tables": ["gear", "bikes", "components", "fitting", "memories"],
        "root_path": str(garage_path.relative_to(ARTIFACTS_ROOT)),
    }

    with _db_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO qbot_v2.artifacts (
                artifact_id, project_id, artifact_type, mutation_type, title,
                filename, mime_type, file_path, size_bytes, sha256, source,
                status, parent_artifact_id, version, expires_at, idempotency_key, metadata_json
            )
            VALUES (
                %s, %s, %s::qbot_v2.artifact_type, %s::qbot_v2.mutation_type, %s,
                %s, %s, %s, %s, %s, %s,
                %s::qbot_v2.artifact_status, %s, %s, %s, %s, %s::jsonb
            )
            ON CONFLICT (idempotency_key) DO UPDATE SET
                project_id = EXCLUDED.project_id,
                artifact_type = EXCLUDED.artifact_type,
                mutation_type = EXCLUDED.mutation_type,
                title = EXCLUDED.title,
                filename = EXCLUDED.filename,
                mime_type = EXCLUDED.mime_type,
                file_path = EXCLUDED.file_path,
                size_bytes = EXCLUDED.size_bytes,
                sha256 = EXCLUDED.sha256,
                source = EXCLUDED.source,
                status = EXCLUDED.status,
                version = EXCLUDED.version,
                metadata_json = EXCLUDED.metadata_json,
                updated_at = now()
            """,
            (
                str(_GARAGE_ARTIFACT_ID),
                None,
                "database",
                "source",
                "Garage database",
                "garage.db",
                "application/x-sqlite3",
                "domains/garage/garage.db",
                size_bytes,
                sha256,
                "manual",
                "active",
                None,
                1,
                None,
                _GARAGE_IDEMPOTENCY_KEY,
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
        conn.commit()


def ensure_bootstrap() -> None:
    ensure_schema()
    _seed_garage_artifact()


def _serialize(row: dict | None) -> dict | None:
    if not row:
        return None
    data = dict(row)
    for key in ("created_at", "updated_at", "expires_at"):
        if isinstance(data.get(key), datetime):
            data[key] = data[key].isoformat()
    return data


def _ttl_for(artifact_type: str, is_tmp: bool) -> datetime | None:
    if is_tmp:
        return datetime.now(timezone.utc) + timedelta(days=_TTL_DAYS["tmp"])
    if artifact_type == "import":
        return datetime.now(timezone.utc) + timedelta(days=_TTL_DAYS["import"])
    if artifact_type == "report":
        return datetime.now(timezone.utc) + timedelta(days=_TTL_DAYS["report"])
    return None


def register_existing_file(
    file_path: str,
    *,
    artifact_type: str,
    title: str,
    project_id: str | None = None,
    mutation_type: str = "source",
    source: str = "albert",
    parent_artifact_id: str | None = None,
    idempotency_key: str | None = None,
    metadata: dict | None = None,
    version: int = 1,
    status: str = "active",
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    ensure_bootstrap()

    rel = str(file_path).replace("\\", "/").lstrip("/")
    abs_path = _safe_path(rel)
    if not abs_path.exists():
        raise FileNotFoundError(f"Brak pliku artefaktu: {abs_path}")

    size_bytes = abs_path.stat().st_size
    sha256 = _sha256(abs_path)
    filename = abs_path.name
    mime_map = {
        ".gpx": "application/gpx+xml",
        ".geojson": "application/geo+json",
        ".json": "application/json",
        ".md": "text/markdown",
        ".csv": "text/csv",
        ".fit": "application/octet-stream",
        ".pdf": "application/pdf",
        ".sqlite": "application/x-sqlite3",
        ".db": "application/x-sqlite3",
    }
    mime_type = mime_map.get(abs_path.suffix.lower(), "application/octet-stream")
    idempotency_key = idempotency_key or f"{artifact_type}:{rel}"

    with _db_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO qbot_v2.artifacts (
                artifact_id, project_id, artifact_type, mutation_type,
                title, filename, mime_type, file_path,
                size_bytes, sha256, source, status,
                parent_artifact_id, version, expires_at, idempotency_key, metadata_json
            )
            VALUES (
                %s, %s, %s::qbot_v2.artifact_type, %s::qbot_v2.mutation_type,
                %s, %s, %s, %s,
                %s, %s, %s, %s::qbot_v2.artifact_status,
                %s, %s, %s, %s, %s::jsonb
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING *
            """,
            (
                str(uuid.uuid5(uuid.NAMESPACE_URL, f"qbot3.artifact:{idempotency_key}")),
                project_id,
                artifact_type,
                mutation_type,
                title,
                filename,
                mime_type,
                rel,
                size_bytes,
                sha256,
                source,
                status,
                parent_artifact_id,
                version,
                expires_at,
                idempotency_key,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT * FROM qbot_v2.artifacts WHERE idempotency_key = %s",
                (idempotency_key,),
            ).fetchone()
        conn.commit()
    return _serialize(dict(row))  # type: ignore[arg-type]


def save_file(
    content: bytes | str,
    filename: str,
    artifact_type: str,
    title: str,
    project_id: str | None = None,
    mutation_type: str = "source",
    source: str = "albert",
    parent_artifact_id: str | None = None,
    idempotency_key: str | None = None,
    metadata: dict | None = None,
    subdir: str | None = None,
    is_tmp: bool = False,
) -> dict[str, Any]:
    ensure_bootstrap()

    if idempotency_key:
        with _db_conn() as conn:
            existing = conn.execute(
                "SELECT * FROM qbot_v2.artifacts WHERE idempotency_key = %s",
                (idempotency_key,),
            ).fetchone()
        if existing:
            return _serialize(dict(existing))  # type: ignore[arg-type]

    if subdir:
        rel_dir = subdir.strip("/")
    elif project_id:
        rel_dir = f"projects/{project_id}/{_TYPE_DIR.get(artifact_type, 'misc')}"
    else:
        rel_dir = _TYPE_DIR.get(artifact_type, "misc")

    if is_tmp:
        rel_dir = "tmp"

    abs_dir = _safe_path(rel_dir)
    abs_dir.mkdir(parents=True, exist_ok=True)
    abs_path = _versioned_path(abs_dir, filename)

    mode = "wb" if isinstance(content, (bytes, bytearray)) else "w"
    with abs_path.open(mode) as fh:
        if mode == "wb":
            fh.write(bytes(content))
        else:
            fh.write(str(content))

    expires_at = _ttl_for(artifact_type, is_tmp)
    result = register_existing_file(
        str(abs_path.relative_to(ARTIFACTS_ROOT)),
        artifact_type=artifact_type,
        title=title,
        project_id=project_id,
        mutation_type=mutation_type,
        source=source,
        parent_artifact_id=parent_artifact_id,
        idempotency_key=idempotency_key or f"{source}:{abs_path.name}:{title}",
        metadata=metadata,
        version=1,
        status="tmp" if is_tmp else "active",
        expires_at=expires_at,
    )
    return result


def list_projects() -> list[dict[str, Any]]:
    ensure_bootstrap()
    with _db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM qbot_v2.projects WHERE status = 'active' ORDER BY start_date NULLS LAST, project_id"
        ).fetchall()
    return [_serialize(dict(row)) for row in rows]  # type: ignore[list-item]


def list_artifacts(
    project_id: str | None = None,
    artifact_type: str | None = None,
    status: str = "active",
) -> list[dict[str, Any]]:
    ensure_bootstrap()
    _VALID_ARTIFACT_TYPES = frozenset({"route", "poi", "plan", "report", "export", "database", "import", "document"})
    conditions = ["status = %s::qbot_v2.artifact_status"]
    params: list[Any] = [status]
    if project_id:
        conditions.append("project_id = %s")
        params.append(project_id)
    if artifact_type and artifact_type in _VALID_ARTIFACT_TYPES:
        conditions.append("artifact_type = %s::qbot_v2.artifact_type")
        params.append(artifact_type)

    where = " AND ".join(conditions)
    with _db_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM qbot_v2.artifacts WHERE {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
    return [_serialize(dict(row)) for row in rows]  # type: ignore[list-item]


def search_artifacts(
    query: str = "",
    project_id: str | None = None,
    artifact_type: str | None = None,
    status: str = "active",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search artifacts by filename, title, or project ID (partial match).

    Args:
        query: text to search in filename, title, project_id, artifact_id
        project_id: filter by project
        artifact_type: filter by type
        status: filter by status (default active)
        limit: max results

    Returns list of artifact dicts.
    """
    ensure_bootstrap()
    _VALID_ARTIFACT_TYPES = frozenset({"route", "poi", "plan", "report", "export", "database", "import", "document"})
    conditions = ["status = %s::qbot_v2.artifact_status"]
    params: list[Any] = [status]
    if project_id:
        conditions.append("project_id = %s")
        params.append(project_id)
    if artifact_type and artifact_type in _VALID_ARTIFACT_TYPES:
        conditions.append("artifact_type = %s::qbot_v2.artifact_type")
        params.append(artifact_type)
    if query:
        conditions.append(
            "(filename ILIKE %s OR title ILIKE %s OR project_id ILIKE %s OR artifact_id::text ILIKE %s)"
        )
        like = f"%{query}%"
        params.extend([like, like, like, like])

    where = " AND ".join(conditions)
    with _db_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM qbot_v2.artifacts WHERE {where} ORDER BY created_at DESC LIMIT %s",
            params + [limit],
        ).fetchall()
    return [_serialize(dict(row)) for row in rows]  # type: ignore[list-item]


def get_artifact(artifact_id: str) -> dict[str, Any] | None:
    ensure_bootstrap()
    with _db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM qbot_v2.artifacts WHERE artifact_id = %s",
            (artifact_id,),
        ).fetchone()
    return _serialize(dict(row)) if row else None


def read_file(artifact_id: str) -> bytes:
    artifact = get_artifact(artifact_id)
    if not artifact:
        raise FileNotFoundError(f"Artefakt {artifact_id} nie istnieje")
    path = _safe_path(str(artifact["file_path"]))
    return path.read_bytes()


def read_artifact_content(
    identifier: str,
    start_line: int = 1,
    max_lines: int = 200,
    max_bytes: int = 65536,
) -> dict[str, Any]:
    """Read artifact content from filesystem via DB record.

    Args:
        identifier: artifact_id UUID, filename, title, file_path, or full path
        start_line: 1-indexed line to start reading from
        max_lines: max lines to return
        max_bytes: max bytes to read

    Returns dict with ok/status/content or error.
    """
    import json as _json
    from pathlib import Path as _Path

    _ALLOW_ROOTS: list[_Path] = [
        _Path("/opt/qbot/artifacts/reports").resolve(),
        _Path("/opt/qbot/artifacts/gravel").resolve(),
        _Path("/opt/qbot/artifacts/route_logistics").resolve(),
        _Path("/opt/qbot/artifacts/projects").resolve(),
        _Path("/opt/qbot/app/docs").resolve(),
        _Path("/opt/qbot/docs").resolve(),
    ]

    _DENY_SUBSTRINGS: list[str] = [
        ".env", "config/", "secrets", "token", "private_key",
        "backup", "/tmp/", "/logs/", "__pycache__", ".git/",
    ]

    _DENY_EXTENSIONS: set[str] = {
        ".db", ".sqlite", ".sqlite3",
        ".tar.gz", ".tgz", ".zip", ".gz",
        ".gpx", ".tcx", ".fit",
        ".geojson", ".png", ".jpg", ".jpeg", ".gif", ".bmp",
        ".ico", ".svg", ".pdf", ".pyc", ".pyo",
    }

    _BINARY_NULL_THRESHOLD = 0.01

    def _is_binary(path: _Path) -> bool:
        try:
            chunk = path.read_bytes()[:8192]
            if not chunk:
                return False
            null_count = chunk.count(b"\x00")
            return null_count / len(chunk) >= _BINARY_NULL_THRESHOLD
        except Exception:
            return True

    def _is_allowed(path: _Path) -> str | None:
        resolved = path.resolve()
        resolved_str = str(resolved)
        lower = resolved_str.lower()
        for pattern in _DENY_SUBSTRINGS:
            if pattern in lower:
                return f"Path matches denylist pattern: {pattern}"
        for ext in _DENY_EXTENSIONS:
            if lower.endswith(ext):
                return f"File extension '{ext}' is denied"
        try:
            for root in _ALLOW_ROOTS:
                if resolved.is_relative_to(root):
                    return None
        except (ValueError, RuntimeError):
            pass
        return f"Path not in allowlist roots"

    if not identifier or not identifier.strip():
        return {"ok": False, "status": "INVALID", "identifier": identifier, "error": "identifier is empty"}

    ident = identifier.strip()

    # Step 1: find active record in qbot_v2.artifacts
    record = None
    try:
        with _db_conn() as conn:
            # Try artifact_id UUID
            try:
                uid = uuid.UUID(ident)
                record = conn.execute(
                    "SELECT * FROM qbot_v2.artifacts WHERE artifact_id = %s AND status = 'active'::qbot_v2.artifact_status",
                    (str(uid),),
                ).fetchone()
            except (ValueError, AttributeError):
                pass

            # Try filename, title, file_path
            if not record:
                like = f"%{ident}%"
                record = conn.execute(
                    """SELECT * FROM qbot_v2.artifacts
                       WHERE status = 'active'::qbot_v2.artifact_status
                         AND (filename ILIKE %s OR title ILIKE %s OR file_path ILIKE %s)
                       ORDER BY created_at DESC LIMIT 1""",
                    (like, like, like),
                ).fetchone()

            # Try full path match against file_path
            if not record and "/" in ident:
                clean_path = ident.replace("/opt/qbot/artifacts/", "").replace("opt/qbot/artifacts/", "").lstrip("/")
                record = conn.execute(
                    "SELECT * FROM qbot_v2.artifacts WHERE file_path ILIKE %s AND status = 'active'::qbot_v2.artifact_status LIMIT 1",
                    (f"%{clean_path}%",),
                ).fetchone()
    except Exception as exc:
        return {"ok": False, "status": "DB_ERROR", "identifier": ident, "error": str(exc)}

    if not record:
        return {"ok": False, "status": "NOT_FOUND", "identifier": ident,
                "error": f"No active artifact found for identifier: {ident}"}

    record = dict(record)

    # Step 2: resolve file path and check security
    raw_file_path = record.get("file_path")
    if not raw_file_path:
        return {"ok": False, "status": "NOT_FOUND", "identifier": ident,
                "error": "Record has no file_path", "artifact_id": str(record.get("artifact_id", ""))}

    abs_path = _safe_path(raw_file_path)

    deny = _is_allowed(abs_path)
    if deny:
        return {"ok": False, "status": "DENIED", "identifier": ident,
                "error": deny, "artifact_id": str(record["artifact_id"]),
                "path": str(abs_path)}

    if not abs_path.exists():
        return {"ok": False, "status": "NOT_FOUND", "identifier": ident,
                "error": f"File does not exist on disk: {abs_path}",
                "artifact_id": str(record["artifact_id"]), "path": str(abs_path)}

    if not abs_path.is_file():
        return {"ok": False, "status": "DENIED", "identifier": ident,
                "error": "Not a regular file", "artifact_id": str(record["artifact_id"]),
                "path": str(abs_path)}

    file_size = abs_path.stat().st_size
    if file_size > max_bytes:
        return {"ok": False, "status": "TOO_LARGE", "identifier": ident,
                "error": f"File is {file_size} bytes (max {max_bytes})",
                "artifact_id": str(record["artifact_id"]), "size_bytes": file_size}

    if _is_binary(abs_path):
        return {"ok": False, "status": "BINARY_FILE", "identifier": ident,
                "error": "File appears to be binary", "artifact_id": str(record["artifact_id"])}

    # Step 3: read content
    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError) as exc:
        return {"ok": False, "status": "READ_ERROR", "identifier": ident,
                "error": f"Read failed: {exc}", "artifact_id": str(record["artifact_id"])}

    lines = text.splitlines(keepends=True)
    total_lines = len(lines)
    start_idx = max(0, start_line - 1)
    end_idx = min(total_lines, start_idx + max_lines)
    selected = lines[start_idx:end_idx]
    content = "".join(selected)

    truncated = False
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > max_bytes:
        content_bytes = content_bytes[:max_bytes]
        content = content_bytes.decode("utf-8", errors="replace")
        if not content.endswith("\n"):
            content = content.rsplit("\n", 1)[0] + "\n"
        truncated = True

    actual_line_count = content.count("\n")
    if content and not content.endswith("\n"):
        actual_line_count += 1

    tags_val = record.get("tags")
    if isinstance(tags_val, str):
        try:
            tags_val = _json.loads(tags_val)
        except Exception:
            tags_val = []

    return {
        "ok": True,
        "status": "READ_OK",
        "artifact_id": str(record["artifact_id"]),
        "filename": record.get("filename", ""),
        "title": record.get("title", ""),
        "artifact_type": record.get("artifact_type", ""),
        "project_id": record.get("project_id"),
        "path": str(abs_path),
        "file_path": raw_file_path,
        "size_bytes": file_size,
        "line_count": total_lines,
        "start_line": start_idx + 1,
        "end_line": start_idx + actual_line_count,
        "content": content,
        "truncated": truncated,
        "metadata": record.get("metadata_json"),
        "tags": tags_val,
        "sources_used": ["qbot_v2.artifacts", "artifact_file_read"],
    }


def cleanup_expired() -> int:
    ensure_bootstrap()
    with _db_conn() as conn:
        rows = conn.execute(
            """
            UPDATE qbot_v2.artifacts
            SET status = 'deleted'::qbot_v2.artifact_status
            WHERE expires_at < now() AND status = 'tmp'::qbot_v2.artifact_status
            RETURNING file_path
            """
        ).fetchall()
        conn.commit()

    deleted = 0
    for row in rows:
        try:
            path = _safe_path(str(row["file_path"]))
            if path.exists():
                path.unlink()
                deleted += 1
        except Exception:
            pass
    return deleted
