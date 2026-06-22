#!/usr/bin/env python3
"""Albert model profiles — przelaczanie gpt / gemini / claude w locie.

Aktywny profil trzymany w data/albert_model.json (zmiana bez restartu).
Kazdy profil ma DEDYKOWANY, jawny endpoint + klucz (niezalezny od QGPT_*).
Klucze czytane z env (autorytatywne: /etc/qbot/qbot-api.env).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_STATE = Path(__file__).resolve().parents[2] / "data" / "albert_model.json"
DEFAULT = "gemini"

PROFILES: dict[str, dict] = {
    "gpt": {
        "label": "GPT (OpenAI)",
        "base_url_env": "QBOT_PLANNER_BASE_URL",
        "base_url_default": "https://api.openai.com/v1",
        "model_env": "QBOT_PLANNER_MODEL",
        "model_default": "gpt-5.4-mini",
        "key_env": "QBOT_PLANNER_API_KEY",
    },
    "gemini": {
        "label": "Gemini 2.5 Flash",
        "base_url_env": None,
        "base_url_default": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model_env": None,
        "model_default": "gemini-2.5-flash",
        "key_env": "GEMINI_API_KEY",
    },
    "claude": {
        "label": "Claude Sonnet 4.6",
        "base_url_env": None,
        "base_url_default": "https://api.anthropic.com/v1/",
        "model_env": None,
        "model_default": "claude-sonnet-4-6",
        "key_env": "ANTHROPIC_API_KEY",
    },
}


def get_active() -> str:
    try:
        data = json.loads(_STATE.read_text(encoding="utf-8"))
        name = str(data.get("active", DEFAULT)).lower().strip()
        return name if name in PROFILES else DEFAULT
    except Exception:
        return DEFAULT


def set_active(name: str) -> bool:
    name = (name or "").lower().strip()
    if name not in PROFILES:
        return False
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps({"active": name}, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


def resolve(name: str | None = None) -> dict:
    name = (name or get_active()).lower().strip()
    if name not in PROFILES:
        name = DEFAULT
    p = PROFILES[name]
    base_url = (os.getenv(p["base_url_env"]) if p["base_url_env"] else None) or p["base_url_default"]
    model = (os.getenv(p["model_env"]) if p["model_env"] else None) or p["model_default"]
    key = os.getenv(p["key_env"], "") or ""
    return {
        "name": name,
        "label": p["label"],
        "base_url": base_url,
        "model": model,
        "api_key": key,
        "key_present": bool(key.strip()),
    }


def public_status(name: str | None = None) -> dict:
    r = resolve(name)
    return {
        "profile": r["name"],
        "label": r["label"],
        "model": r["model"],
        "base_url": r["base_url"],
        "key_present": r["key_present"],
    }
