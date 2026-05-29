#!/usr/bin/env python3
"""Q Secrets Store reader — centralised secret access with fallback.

Preference:
  1. Q_SECRETS_STORE or QBOT3_SECRETS_STORE env var
  2. /opt/q/secrets/ (default new store)
  3. legacy path (/opt/qbot/app/.config/) if not found in new store

Usage:
  from q_secrets_reader import read_secret, secret_path
  token = read_secret("garmin", "michal_tokens.json")
  path = secret_path("hammerhead", "michal_tokens.json")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_SECRETS_STORE = Path(os.getenv("Q_SECRETS_STORE") or os.getenv("QBOT3_SECRETS_STORE") or "/opt/q/secrets")
_SOURCE_LOG: list[str] = []

# Legacy fallback paths
_LEGACY_PATHS: dict[str, Path] = {
    "garmin": Path("/opt/qbot/app/.garmin_tokens"),
    "hammerhead": Path("/opt/qbot/app/.hammerhead_tokens"),
    "hikconnect": Path("/opt/qbot/app/.env"),
    "telegram": Path("/opt/qbot/app/.env.local"),
}


def _log_source(source: str) -> None:
    if source not in _SOURCE_LOG:
        _SOURCE_LOG.append(source)


def source_log() -> list[str]:
    return list(_SOURCE_LOG)


def read_secret(category: str, filename: str, legacy_fallback: Path | None = None) -> str | None:
    """Read a secret from the store, fallback to legacy path.
    
    Returns None if not found in either location.
    """
    new_path = _SECRETS_STORE / category / filename
    if new_path.is_file():
        _log_source(f"secrets_store:{category}/{filename}")
        try:
            return new_path.read_text(encoding="utf-8", errors="ignore").strip()
        except (OSError, PermissionError):
            pass

    if legacy_fallback:
        old_path = legacy_fallback / filename if legacy_fallback.is_dir() else legacy_fallback
        if old_path.is_file():
            _log_source(f"legacy:{old_path}")
            try:
                return old_path.read_text(encoding="utf-8", errors="ignore").strip()
            except (OSError, PermissionError):
                pass
    elif category in _LEGACY_PATHS:
        legacy_base = _LEGACY_PATHS[category]
        if legacy_base.is_dir():
            for f in legacy_base.rglob(filename):
                if f.is_file():
                    _log_source(f"legacy:{f}")
                    try:
                        return f.read_text(encoding="utf-8", errors="ignore").strip()
                    except (OSError, PermissionError):
                        pass

    return None


def secret_path(category: str, filename: str) -> Path | None:
    """Return the path to a secret file, preferring new store."""
    new_path = _SECRETS_STORE / category / filename
    if new_path.is_file():
        _log_source(f"secrets_store:{category}/{filename}")
        return new_path

    if category in _LEGACY_PATHS:
        legacy_base = _LEGACY_PATHS[category]
        if legacy_base.is_dir():
            for f in legacy_base.rglob(filename):
                if f.is_file():
                    _log_source(f"legacy:{f}")
                    return f

    return None


def secret_exists(category: str, filename: str) -> tuple[bool, str]:
    """Check if a secret exists. Returns (exists, source_description)."""
    new_path = _SECRETS_STORE / category / filename
    if new_path.is_file():
        try:
            new_path.read_bytes()
            return True, f"store:{category}/{filename}"
        except (OSError, PermissionError):
            return False, f"store:{category}/{filename} (permission)"

    if category in _LEGACY_PATHS:
        legacy_base = _LEGACY_PATHS[category]
        if legacy_base.is_dir():
            for f in legacy_base.rglob(filename):
                if f.is_file():
                    try:
                        f.read_bytes()
                        return True, f"legacy:{f.relative_to(Path('/opt/qbot/app'))}"
                    except (OSError, PermissionError):
                        return False, f"legacy:{f} (permission)"

    return False, "not_found"
