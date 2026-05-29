#!/usr/bin/env python3
"""Internal capability: llm_status (active).

Resolves LLM config exactly matching qgpt_client.py runtime logic.
No guessing, no default fallback to wrong provider.
"""

from __future__ import annotations

import os
from typing import Any

from qbot3.capabilities.base import (
    Capability, CapabilityDef,
    PROMOTION_ACTIVE, SAFETY_READ_ONLY_CONFIG,
)


def _resolve_llm_runtime() -> dict[str, Any]:
    """Resolve LLM runtime config exactly like qgpt_client.py does.

    qgpt_client.py logic:
      1. _use_openai_compatible() → bool(QGPT_API_KEY) or localhost base URL
      2. If compatible → qgpt_chat() with QGPT_MODEL + QGPT_FALLBACK_MODEL
      3. If not compatible → _anthropic_text() using ANTHROPIC_API_KEY

    Returns resolved transport, model, key status, mismatch detection.
    """
    has_qgpt_key = bool(os.getenv("QGPT_API_KEY"))
    has_openai_key = bool(os.getenv("OPENAI_API_KEY"))
    has_openrouter_key = bool(os.getenv("OPENROUTER_API_KEY"))
    has_anthropic_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    has_deepseek_key = bool(os.getenv("DEEPSEEK_API_KEY"))
    base_url = (os.getenv("QGPT_BASE_URL") or "").lower()

    # Active model from env
    active_model = os.getenv("ALBERT_LLM_MODEL") or os.getenv("QGPT_MODEL") or ""
    fallback_model = os.getenv("QGPT_FALLBACK_MODEL") or ""
    provider_setting = os.getenv("ALBERT_LLM_PROVIDER", "openai")

    # Detect transport matching qgpt_client.py runtime logic
    if provider_setting == "mock":
        return {
            "transport": "mock",
            "active_model": "mock",
            "fallback_model": "none",
            "config_ok": True,
            "mismatch": False,
            "note": "Mock provider — no real API calls",
        }

    # Runtime: _use_openai_compatible()
    uses_openai_compatible = has_qgpt_key or base_url.startswith(("http://localhost", "http://127.0.0.1"))

    if uses_openai_compatible:
        # OpenAI-compatible path — could be OpenRouter or real OpenAI API
        if has_openrouter_key or "openrouter" in base_url:
            transport = "openrouter"
        elif has_openai_key:
            transport = "openai_api"
        elif has_qgpt_key:
            # Generic OpenAI-compatible key, source unknown
            transport = "openai_compatible"
        else:
            transport = "local"
        return {
            "transport": transport,
            "active_model": active_model or "not set",
            "fallback_model": fallback_model or "none",
            "config_ok": True,
            "mismatch": False,
            "key": transport,
        }

    # Runtime: _anthropic_text() fallback
    if has_anthropic_key:
        anthropic_model = os.getenv("ANTHROPIC_MODEL", "")
        model_to_use = active_model or anthropic_model or "claude-sonnet-4-6"
        # Detect mismatch: anthropic transport with non-anthropic model
        model_lower = model_to_use.lower()
        is_anthropic_model = ("claude" in model_lower or "anthropic" in model_lower or not model_lower)
        mismatch = not is_anthropic_model and bool(model_to_use)
        return {
            "transport": "anthropic_api",
            "active_model": model_to_use,
            "fallback_model": "none",
            "config_ok": not mismatch,
            "mismatch": mismatch,
            "mismatch_detail": f"anthropic_api with non-Anthropic model '{model_to_use}'" if mismatch else "",
            "key": "anthropic_api",
            "key_note": "Anthropic API key present but historical quota = 0 — runtime may fail",
        }

    # No usable transport found
    return {
        "transport": "none",
        "active_model": active_model or "not set",
        "fallback_model": "none",
        "config_ok": False,
        "mismatch": True,
        "mismatch_detail": "No usable LLM provider configured: no QGPT_API_KEY, no OPENAI_API_KEY, no OPENROUTER_API_KEY, no ANTHROPIC_API_KEY",
    }


class LlmStatusCapability(Capability):
    def manifest(self) -> CapabilityDef:
        return CapabilityDef(
            name="llm_status",
            description="LLM runtime config: aktywny transport (openrouter/openai_api/anthropic_api/mock), model, fallback, mismatch detection. Odzwierciedla rzeczywisty runtime qgpt_client.py.",
            safety_class=SAFETY_READ_ONLY_CONFIG,
            capability_type=SAFETY_READ_ONLY_CONFIG,
            data_sources=["env vars", "qgpt_client.py runtime logic"],
            promotion_state=PROMOTION_ACTIVE,
            inputs_schema={},
            output_schema={},
            reason_existing_insufficient="Previous version didn't match actual qgpt_client.py runtime resolution, causing misleading transport detection",
        )

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        runtime = _resolve_llm_runtime()
        transport = runtime["transport"]

        data = {
            "active_transport": transport,
            "active_model": runtime["active_model"],
            "fallback_model": runtime["fallback_model"],
            "config_ok": runtime["config_ok"],
            "mismatch": runtime.get("mismatch", False),
            "keys": {
                "openai_api": "configured" if os.getenv("OPENAI_API_KEY") else "not_configured",
                "openrouter": "configured" if os.getenv("OPENROUTER_API_KEY") else "not_configured",
                "anthropic_api": "unusable" if os.getenv("ANTHROPIC_API_KEY") else "not_configured",
                "deepseek": "configured" if os.getenv("DEEPSEEK_API_KEY") else "not_configured",
            },
            "secrets_masked": True,
        }

        if runtime.get("key_note"):
            data["note"] = runtime["key_note"]
        if runtime.get("mismatch_detail"):
            data["mismatch_detail"] = runtime["mismatch_detail"]

        # Build summary
        parts = []
        if transport == "mock":
            parts.append("Transport: mock (testing, no real API)")
            parts.append(f"Model: {runtime['active_model']}")
        elif transport == "none":
            parts.append("❌ No usable LLM transport configured")
            parts.append(f"Model: {runtime['active_model']}")
            parts.append(f"Issue: {runtime.get('mismatch_detail', 'unknown')}")
        elif transport == "anthropic_api":
            parts.append("Transport: anthropic_api ⚠️ (legacy fallback, likely 0 quota)")
            parts.append(f"Model: {runtime['active_model']}")
            if runtime.get("mismatch"):
                parts.append(f"⚠️ CONFIG MISMATCH: {runtime.get('mismatch_detail', '')}")
            else:
                parts.append("Fallback: none (Anthropic has no configured fallback)")
        elif transport == "openrouter":
            parts.append("Transport: openrouter")
            parts.append(f"Model: {runtime['active_model']}")
            if runtime["fallback_model"] and runtime["fallback_model"] != "none":
                parts.append(f"Fallback: {runtime['fallback_model']} (same transport)")
        elif transport == "openai_api":
            parts.append("Transport: openai_api")
            parts.append(f"Model: {runtime['active_model']}")
            if runtime["fallback_model"] and runtime["fallback_model"] != "none":
                parts.append(f"Fallback: {runtime['fallback_model']}")
        else:
            parts.append(f"Transport: {transport}")
            parts.append(f"Model: {runtime['active_model']}")

        data["summary"] = " | ".join(parts)
        return {"status": "OK" if runtime["config_ok"] else "CONFIG_MISMATCH", "data": data, "summary": data["summary"]}
