#!/usr/bin/env python3
"""Read-only artifact file access for QBot MCP.

Provides _tool_qbot_artifact_read() — safe, allowlisted file reading.
Callable through qbot.query or directly via MCP tools/call.

Security:
  - Allowlist: /opt/qbot/artifacts/{reports,gravel,route_logistics,projects} + /opt/qbot/app/docs
  - Denylist: .env, config, secrets, tokens, keys, backups, logs, tmp, *.db, *.tar.gz, *.gpx, *.tcx
  - Path traversal protection via pathlib.Path.resolve()
  - 256 KB size limit with line-based chunking
  - Binary file detection
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Allowlist roots
# ---------------------------------------------------------------------------

_ALLOW_ROOTS: list[Path] = [
    Path("/opt/qbot/artifacts/reports").resolve(),
    Path("/opt/qbot/artifacts/gravel").resolve(),
    Path("/opt/qbot/artifacts/route_logistics").resolve(),
    Path("/opt/qbot/artifacts/projects").resolve(),
    Path("/opt/qbot/app/docs").resolve(),
    Path("/opt/qbot/docs").resolve(),
]

# ---------------------------------------------------------------------------
# Denylist — patterns matched against the full resolved path (lowercase)
# ---------------------------------------------------------------------------

_DENY_SUBSTRINGS: list[str] = [
    ".env",
    "config/",
    "secrets",
    "token",
    "private_key",
    "backup",
    "/tmp/",
    "/logs/",
    "__pycache__",
    ".git/",
]

_DENY_EXTENSIONS: set[str] = {
    ".db", ".sqlite", ".sqlite3",
    ".tar.gz", ".tgz", ".zip", ".gz",
    ".gpx", ".tcx", ".fit",
    ".geojson",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".pdf",
    ".pyc", ".pyo",
}

_DENY_PREFIXES: list[str] = [
    "qbot_replay_",
    "backups/",
]

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

MAX_BYTES = 256_000  # 256 KB
DEFAULT_MAX_LINES = 200

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BINARY_NULL_THRESHOLD = 0.01  # 1% null bytes → treat as binary


def _is_binary(path: Path) -> bool:
    """Quick check: read first 8 KB, look for null bytes above threshold."""
    try:
        chunk = path.read_bytes()[:8192]
        if not chunk:
            return False
        null_count = chunk.count(b"\x00")
        return null_count / len(chunk) >= _BINARY_NULL_THRESHOLD
    except Exception:
        return True  # safer to reject on error


def _check_deny(path: Path, path_str: str) -> str | None:
    """Return DENY reason string, or None if allowed."""
    lower = path_str.lower()

    # Substring checks
    for pattern in _DENY_SUBSTRINGS:
        if pattern in lower:
            return f"Path matches denylist pattern: {pattern}"

    # Extension check
    ext = _deny_ext(lower)
    if ext:
        return f"File extension '{ext}' is denied (binary/non-readable format)"

    # Prefix check (on filename)
    name_lower = path.name.lower()
    for prefix in _DENY_PREFIXES:
        if name_lower.startswith(prefix):
            return f"Filename matches denylist prefix: {prefix}"

    return None


def _deny_ext(lower_path: str) -> str | None:
    for ext in _DENY_EXTENSIONS:
        if lower_path.endswith(ext):
            return ext
    # Also check compound extensions like .tar.gz
    if lower_path.endswith(".tar.gz"):
        return ".tar.gz"
    return None


def _is_under_allowlist(resolved: Path) -> bool:
    """Check if resolved path is under any allowlist root."""
    try:
        for root in _ALLOW_ROOTS:
            if resolved.is_relative_to(root):
                return True
    except (ValueError, RuntimeError):
        pass
    return False


# ===================================================================
# Public tool
# ===================================================================

def _tool_qbot_artifact_read(args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read an allowlisted artifact file.

    Args:
        identifier: artifact_id UUID, filename, title, or full path
        path: absolute or relative path to file (fallback if identifier not given)
        start_line: 1-indexed line to start from (default 1)
        max_lines: max lines to return (default 200, max 2000)
        max_bytes: max bytes to return (default 256000)

    Returns structured JSON with content or error.
    """
    _args = args or {}
    identifier = str(_args.get("identifier", "")).strip()
    raw_path = str(_args.get("path", "")).strip()
    start_line = int(_args.get("start_line", 1))
    max_lines = min(int(_args.get("max_lines", DEFAULT_MAX_LINES)), 2000)
    req_max_bytes = min(int(_args.get("max_bytes", MAX_BYTES)), MAX_BYTES)

    # ── If identifier is provided, use DB-backed read ──
    if identifier:
        try:
            from qbot3.artifacts.store import read_artifact_content
            return read_artifact_content(
                identifier=identifier,
                start_line=start_line,
                max_lines=max_lines,
                max_bytes=req_max_bytes,
            )
        except ImportError:
            return _error("READ_ERROR", "artifact store module not available", identifier)
        except Exception as exc:
            return _error("READ_ERROR", f"artifact read failed: {exc}", identifier)

    # ── Fallback: direct path read ──
    if not raw_path:
        return _error("DENIED", "No path or identifier provided", raw_path)

    # Normalize / resolve
    try:
        resolved = Path(raw_path).resolve()
    except (RuntimeError, OSError) as exc:
        return _error("READ_ERROR", f"Path resolution failed: {exc}", raw_path)

    resolved_str = str(resolved)

    # ── Check denylist ──
    deny_reason = _check_deny(resolved, resolved_str)
    if deny_reason:
        return _error("DENIED", deny_reason, resolved_str)

    # ── Check allowlist ──
    if not _is_under_allowlist(resolved):
        return _error("DENIED",
                      f"Path not in allowlist roots: {[str(r) for r in _ALLOW_ROOTS]}",
                      resolved_str)

    # ── Check exists / is file ──
    if not resolved.exists():
        return _error("NOT_FOUND", f"File does not exist: {resolved_str}", resolved_str)
    if not resolved.is_file():
        return _error("DENIED", f"Not a regular file: {resolved_str}", resolved_str)

    # ── Check size ──
    file_size = resolved.stat().st_size
    if file_size > MAX_BYTES:
        return _error("TOO_LARGE",
                      f"File is {file_size} bytes (max {MAX_BYTES})",
                      resolved_str,
                      extra={"size_bytes": file_size})

    # ── Check binary ──
    if _is_binary(resolved):
        return _error("BINARY_FILE",
                      "File appears to be binary (not readable as text)",
                      resolved_str)

    # ── Read file ──
    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError) as exc:
        return _error("READ_ERROR", f"Read failed: {exc}", resolved_str)

    lines = text.splitlines(keepends=True)
    total_lines = len(lines)

    # Apply start_line / max_lines
    start_idx = max(0, start_line - 1)
    end_idx = min(total_lines, start_idx + max_lines)
    selected_lines = lines[start_idx:end_idx]

    # Apply max_bytes truncation
    content = "".join(selected_lines)
    truncated = False
    if len(content.encode("utf-8")) > req_max_bytes:
        # Truncate to byte limit
        content_bytes = content.encode("utf-8")[:req_max_bytes]
        content = content_bytes.decode("utf-8", errors="replace")
        # Remove partial last line if any
        if not content.endswith("\n"):
            content = content.rsplit("\n", 1)[0] + "\n"
        truncated = True

    actual_line_count = content.count("\n")
    if content and not content.endswith("\n"):
        actual_line_count += 1

    return {
        "ok": True,
        "status": "READ_OK",
        "path": resolved_str,
        "size_bytes": file_size,
        "line_count": total_lines,
        "start_line": start_idx + 1,
        "end_line": start_idx + actual_line_count,
        "content": content,
        "truncated": truncated,
        "tool": "qbot_artifact_read",
        "safety_class": "READ_ONLY",
    }


def _error(
    status: str,
    error: str,
    path: str,
    extra: dict | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "status": status,
        "path": path,
        "error": error,
        "tool": "qbot_artifact_read",
        "safety_class": "READ_ONLY",
    }
    if extra:
        result.update(extra)
    return result


# ===================================================================
# CLI smoke test
# ===================================================================

if __name__ == "__main__":
    import sys
    test_path = sys.argv[1] if len(sys.argv) > 1 else "/opt/qbot/artifacts/reports"
    result = _tool_qbot_artifact_read({"path": test_path})
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
