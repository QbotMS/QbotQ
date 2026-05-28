#!/usr/bin/env python3
"""Central configuration for QBot local scripts."""
from __future__ import annotations

import base64
import os
from pathlib import Path

from dotenv import load_dotenv


APP_DIR = Path("/opt/qbot/app")
ENV_FILE = APP_DIR / ".env"
DATA_DIR = APP_DIR / "data"
LOG_DIR = Path("/opt/qbot/logs")
APP_LOG_DIR = APP_DIR / "logs"

load_dotenv(ENV_FILE)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return float(raw)


INTERVALS_ATHLETE_ID = env("INTERVALS_ATHLETE_ID")
INTERVALS_API_KEY = env("INTERVALS_API_KEY")

TELEGRAM_TOKEN = env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")

GMAIL_USER = env("GMAIL_USER")
GMAIL_APP_PASSWORD = env("GMAIL_APP_PASSWORD")
EMAIL_TO = env("EMAIL_TO", GMAIL_USER)

LOCATION_LAT = env_float("LOCATION_LAT", 52.2297)
LOCATION_LON = env_float("LOCATION_LON", 21.0122)
LOCATION_NAME = env("LOCATION_NAME", "Warszawa")

MCP_URL = env("QBOT_MCP_URL", "http://127.0.0.1:8002/mcp/")

QGPT_BASE_URL = (
    env("QGPT_BASE_URL")
    or env("QGPT_FALLBACK_BASE_URL")
    or "https://api.openai.com/v1"
).rstrip("/")
QGPT_MODEL = env("QGPT_MODEL") or env("OPENAI_MODEL") or env("QGPT_FALLBACK_MODEL") or "gpt-4.1-mini"
QGPT_API_KEY = (
    env("QGPT_API_KEY")
    or env("OPENAI_API_KEY")
    or env("QGPT_FALLBACK_API_KEY")
    or env("OPENROUTER_API_KEY")
)
QGPT_TIMEOUT_SEC = env_float("QGPT_TIMEOUT_SEC", 60)
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def intervals_headers() -> dict[str, str]:
    token = base64.b64encode(f"API_KEY:{INTERVALS_API_KEY}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def llm_provider() -> str:
    if QGPT_API_KEY:
        return "openai-compatible"
    if QGPT_BASE_URL.startswith(("http://localhost", "http://127.0.0.1")):
        return "local-openai-compatible"
    if ANTHROPIC_API_KEY:
        return "anthropic"
    return "none"
