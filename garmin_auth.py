#!/usr/bin/env python3
"""Garmin Connect auth helpers for Q-bot automations.

Configuration:
- GARMIN_TOKENSTORE: optional tokenstore directory/string, defaults to
  /opt/qbot/app/.garmin_tokens
- GARMIN_EMAIL / GARMIN_PASSWORD: optional fallback credentials when tokens
  cannot be loaded or must be refreshed by garminconnect.

No token or password values are logged by this module.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from garminconnect import Garmin


APP_DIR = Path("/opt/qbot/app")
DEFAULT_TOKENSTORE = APP_DIR / ".garmin_tokens"
DEFAULT_PROFILE = APP_DIR / ".garmin_profile.json"


class GarminAuthError(RuntimeError):
    pass


def garmin_client() -> Garmin:
    load_dotenv(APP_DIR / ".env")

    tokenstore = os.getenv("GARMIN_TOKENSTORE", str(DEFAULT_TOKENSTORE)).strip()
    email = os.getenv("GARMIN_EMAIL", "").strip() or None
    password = os.getenv("GARMIN_PASSWORD", "").strip() or None

    if not tokenstore and not (email and password):
        raise GarminAuthError("Garmin auth missing: set GARMIN_TOKENSTORE or GARMIN_EMAIL/GARMIN_PASSWORD")

    client = Garmin(email, password)
    if tokenstore:
        client.login(tokenstore=tokenstore)
    else:
        client.login()

    if DEFAULT_PROFILE.exists():
        try:
            profile: dict[str, Any] = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
            if profile.get("display_name"):
                client.display_name = profile["display_name"]
        except Exception:
            pass
    return client


def upload_activity(fit_path: Path, *, method: str = "upload") -> dict[str, Any]:
    client = garmin_client()
    method = method.lower().strip()
    if method == "import":
        result = client.import_activity(str(fit_path))
    elif method == "upload":
        result = client.upload_activity(str(fit_path))
    else:
        raise ValueError("Garmin upload method must be 'upload' or 'import'")

    activity_id = extract_activity_id(result)
    activity_url = f"https://connect.garmin.com/modern/activity/{activity_id}" if activity_id else None
    return {
        "status": "success",
        "method": method,
        "raw": result,
        "activityId": activity_id,
        "activityUrl": activity_url,
    }


def extract_activity_id(result: Any) -> str | None:
    if isinstance(result, dict):
        for key in ("activityId", "activity_id", "internalId", "uploadId"):
            value = result.get(key)
            if value:
                return str(value)
        detailed = result.get("detailedImportResult") or result.get("detailedImportResultDto")
        if isinstance(detailed, dict):
            for bucket in ("uploadSuccesses", "successes"):
                values = detailed.get(bucket)
                if isinstance(values, list) and values:
                    found = extract_activity_id(values[0])
                    if found:
                        return found
            for key in ("activityId", "activity_id"):
                value = detailed.get(key)
                if value:
                    return str(value)
        for key in ("activityId", "activity_id"):
            for value in walk_values(result, key):
                if value:
                    return str(value)
    return None


def walk_values(value: Any, wanted_key: str):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == wanted_key:
                yield item
            yield from walk_values(item, wanted_key)
    elif isinstance(value, list):
        for item in value:
            yield from walk_values(item, wanted_key)
