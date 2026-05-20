#!/usr/bin/env python3
"""Small JSON cache helpers for external QBot calls."""
from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


def load_cache(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_cache(path: Path, data: dict, *, keep: int = 100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(data) > keep:
        for key in sorted(data.keys())[: len(data) - keep]:
            del data[key]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_failed(value: Any) -> bool:
    return value is None or (isinstance(value, dict) and bool(value.get("error")))


def _cached_value(entry: dict, reason: str) -> Any:
    value = copy.deepcopy(entry.get("value"))
    if isinstance(value, dict):
        value["cache_hit"] = True
        value["cache_reason"] = reason
        value["cached_at"] = entry.get("cached_at")
    return value


def cached_call(path: Path, key: str, fetch: Callable[[], Any], *, keep: int = 100) -> Any:
    cache = load_cache(path)
    try:
        value = fetch()
    except Exception as exc:
        if key in cache:
            return _cached_value(cache[key], str(exc))
        raise

    if _is_failed(value):
        if key in cache:
            reason = value.get("error") if isinstance(value, dict) else "empty response"
            return _cached_value(cache[key], str(reason))
        return value

    cache[key] = {"cached_at": datetime.now().isoformat(), "value": value}
    write_cache(path, cache, keep=keep)
    return value
