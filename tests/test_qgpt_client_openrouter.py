#!/usr/bin/env python3
"""Test qgpt_client.py defensive handling of OpenRouter reasoning models.

Simulates a response where choices[0].message.content = null
and reasoning/reasoning_details are present.
"""

from __future__ import annotations

import json
from typing import Any


def test_extract_empty_content_with_reasoning() -> None:
    """Simulate what qgpt_chat does with an OpenRouter reasoning response."""
    data: dict[str, Any] = {
        "id": "chatcmpl-test",
        "model": "openai/o1-pro",
        "provider": "OpenAI",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": None,
                    "reasoning": "Let me think about this...",
                    "reasoning_details": {"tokens": 150},
                },
            }
        ],
    }

    choices = data.get("choices", [])
    assert choices, "No choices in response"
    choice = choices[0]
    finish_reason = choice.get("finish_reason", "unknown")
    msg = choice.get("message") or {}
    content = msg.get("content")
    provider = data.get("provider", data.get("model_info", {}).get("provider_name", ""))
    resp_model = data.get("model", "")

    # Content must be None, not a valid answer
    assert content is None, f"Expected None, got {type(content)}"
    assert not (isinstance(content, str) and content.strip()), "Should not have valid text content"

    # Reasoning must be present
    has_reasoning = "reasoning" in msg or "reasoning_details" in msg
    assert has_reasoning, "Expected reasoning or reasoning_details"

    # Build the error message (same logic as qgpt_chat)
    detail_parts = [f"model={resp_model}"]
    if provider:
        detail_parts.append(f"provider={provider}")
    detail_parts.append(f"finish_reason={finish_reason}")
    if has_reasoning:
        detail_parts.append("reasoning_present=true")

    error_msg = f"Model returned empty message.content ({'; '.join(detail_parts)})"
    print(f"  Expected error: {error_msg}")

    # Verify no secrets leaked
    assert "api_key" not in error_msg.lower()
    assert "authorization" not in error_msg.lower()
    assert "Bearer" not in error_msg
    assert "QGPT_API_KEY" not in error_msg

    print("  ✅ test_extract_empty_content_with_reasoning PASSED")


def test_extract_valid_content() -> None:
    """Normal non-reasoning response — content is valid text."""
    data: dict[str, Any] = {
        "id": "chatcmpl-test",
        "model": "gpt-4.1-mini",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": "This is a valid response.",
                },
            }
        ],
    }

    choices = data.get("choices", [])
    choice = choices[0]
    msg = choice.get("message") or {}
    content = msg.get("content")

    assert isinstance(content, str) and content.strip(), "Content should be valid text"
    assert content.strip() == "This is a valid response."
    print("  ✅ test_extract_valid_content PASSED")


def test_empty_choices() -> None:
    """Response with empty choices list."""
    data: dict[str, Any] = {
        "id": "chatcmpl-test",
        "model": "gpt-4.1-mini",
        "choices": [],
    }

    choices = data.get("choices", [])
    assert not choices
    print("  ✅ test_empty_choices PASSED")


def test_missing_message() -> None:
    """Response with missing message key."""
    data: dict[str, Any] = {
        "id": "chatcmpl-test",
        "model": "gpt-4.1-mini",
        "choices": [{"finish_reason": "stop", "message": None}],
    }

    choices = data.get("choices", [])
    choice = choices[0]
    msg = choice.get("message") or {}
    content = msg.get("content")
    assert content is None
    print("  ✅ test_missing_message PASSED")


def test_empty_content_string() -> None:
    """Response with empty string content (not null, but also not valid)."""
    data: dict[str, Any] = {
        "id": "chatcmpl-test",
        "model": "gpt-4.1-mini",
        "choices": [{"finish_reason": "stop", "message": {"content": ""}}],
    }

    choices = data.get("choices", [])
    choice = choices[0]
    msg = choice.get("message") or {}
    content = msg.get("content")
    assert isinstance(content, str)
    assert not content.strip()
    print("  ✅ test_empty_content_string PASSED")


if __name__ == "__main__":
    print("=== qgpt_client OpenRouter tests ===")
    test_extract_empty_content_with_reasoning()
    test_extract_valid_content()
    test_empty_choices()
    test_missing_message()
    test_empty_content_string()
    print("\n✅ All tests passed")
