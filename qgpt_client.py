#!/usr/bin/env python3
"""Wspólny klient LLM dla QBot.

Najpierw używa API kompatybilnego z OpenAI Chat Completions, jeśli jest
skonfigurowany klucz OpenAI/QGPT:
  QGPT_BASE_URL=https://api.openai.com/v1
  QGPT_MODEL=gpt-4.1-mini
  QGPT_API_KEY=...

Jeśli nie ma QGPT_API_KEY/OPENAI_API_KEY, używa Anthropic Messages API:
  ANTHROPIC_API_KEY=...
  ANTHROPIC_MODEL=claude-sonnet-4-6

Lokalny QGPT bez autoryzacji jest dozwolony tylko dla localhost/127.0.0.1.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from qbot_config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    QGPT_API_KEY,
    QGPT_BASE_URL,
    QGPT_MODEL,
    QGPT_FALLBACK_MODEL,
    QGPT_TIMEOUT_SEC,
)

CORE_INSTRUCTIONS_PATH = Path("/opt/qbot/app/QBOT_INSTRUCTIONS.md")


@lru_cache(maxsize=1)
def qbot_core_instructions() -> str:
    try:
        return CORE_INSTRUCTIONS_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _merge_system(system: str | None) -> str | None:
    core = qbot_core_instructions()
    if core and system:
        return f"{core}\n\nModule-specific instructions:\n{system}"
    return system or core or None


def _chat_url() -> str:
    if QGPT_BASE_URL.endswith("/chat/completions"):
        return QGPT_BASE_URL
    return f"{QGPT_BASE_URL}/chat/completions"


def _headers() -> dict[str, str]:
    headers = {"content-type": "application/json"}
    if QGPT_API_KEY:
        headers["authorization"] = f"Bearer {QGPT_API_KEY}"
    elif not (
        QGPT_BASE_URL.startswith("http://localhost")
        or QGPT_BASE_URL.startswith("http://127.0.0.1")
    ):
        raise RuntimeError("Brak QGPT_API_KEY lub OPENAI_API_KEY w /opt/qbot/app/.env")
    return headers


def _use_openai_compatible() -> bool:
    return bool(QGPT_API_KEY) or QGPT_BASE_URL.startswith(
        ("http://localhost", "http://127.0.0.1")
    )


def _anthropic_text(
    messages: list[dict[str, str]],
    *,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0,
) -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "Brak QGPT_API_KEY/OPENAI_API_KEY oraz ANTHROPIC_API_KEY w /opt/qbot/app/.env"
        )

    payload: dict[str, Any] = {
        "model": ANTHROPIC_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system:
        payload["system"] = system

    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "content-type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        json=payload,
        timeout=QGPT_TIMEOUT_SEC,
    )
    r.raise_for_status()
    data: dict[str, Any] = r.json()
    parts = [
        block.get("text", "")
        for block in data.get("content", [])
        if block.get("type") == "text"
    ]
    text = "".join(parts).strip()
    if not text:
        raise RuntimeError(f"Niepoprawna odpowiedź Anthropic: {data}")
    return text


def qgpt_chat(
    messages: list[dict[str, str]],
    *,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0,
) -> str:
    system = _merge_system(system)
    if not _use_openai_compatible():
        return _anthropic_text(
            messages,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    payload_messages: list[dict[str, str]] = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages.extend(messages)

    payload = {
        "messages": payload_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    models_to_try = [QGPT_MODEL]
    if QGPT_FALLBACK_MODEL and QGPT_FALLBACK_MODEL not in models_to_try:
        models_to_try.append(QGPT_FALLBACK_MODEL)

    last_exc: Exception | None = None
    for mdl in models_to_try:
        try:
            attempt_payload = dict(payload)
            attempt_payload["model"] = mdl
            r = httpx.post(
                _chat_url(),
                headers=_headers(),
                json=attempt_payload,
                timeout=QGPT_TIMEOUT_SEC,
            )
            r.raise_for_status()
            data: dict[str, Any] = r.json()
            try:
                choices = data.get("choices", [])
                if not choices:
                    raise RuntimeError("No choices in response")
                choice = choices[0]
                finish_reason = choice.get("finish_reason", "unknown")
                msg = choice.get("message") or {}
                content = msg.get("content")
                provider = data.get("provider", data.get("model_info", {}).get("provider_name", ""))
                resp_model = data.get("model", mdl)
                if isinstance(content, str) and content.strip():
                    return content.strip()
                has_reasoning = "reasoning" in msg or "reasoning_details" in msg
                detail_parts = [f"model={resp_model}"]
                if provider:
                    detail_parts.append(f"provider={provider}")
                detail_parts.append(f"finish_reason={finish_reason}")
                if has_reasoning:
                    detail_parts.append("reasoning_present=true")
                raise RuntimeError(
                    f"Model returned empty message.content ({'; '.join(detail_parts)})"
                )
            except RuntimeError:
                raise
            except Exception as e:
                raise RuntimeError(f"Niepoprawna odpowiedź QGPT: {data}") from e
        except Exception as exc:
            last_exc = exc
            continue

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("QGPT request failed without exception")


def qgpt_text(
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0,
) -> str:
    return qgpt_chat(
        [{"role": "user", "content": prompt}],
        system=system,
        max_tokens=max_tokens,
        temperature=temperature,
    )


def parse_json_text(text: str) -> Any:
    clean = text.strip()
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.MULTILINE).strip()
    return json.loads(clean)


def qgpt_json(
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0,
) -> Any:
    return parse_json_text(
        qgpt_text(
            prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    )
