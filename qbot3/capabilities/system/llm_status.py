#!/usr/bin/env python3
"""Internal capability: llm_status (proposed).

Status: proposed — not yet active. Returns provider, model, fallback info.
SAFE: only reads env vars, masks secrets. No side effects.
"""

from __future__ import annotations

import os
from typing import Any

from qbot3.capabilities.base import (
    Capability, CapabilityDef,
    PROMOTION_PROPOSED, SAFETY_READ_ONLY_CONFIG,
)


class LlmStatusCapability(Capability):
    def manifest(self) -> CapabilityDef:
        return CapabilityDef(
            name="llm_status",
            description="Status używanego modelu LLM i providera. Tylko odczyt — bez sekretów.",
            safety_class=SAFETY_READ_ONLY_CONFIG,
            capability_type=SAFETY_READ_ONLY_CONFIG,
            data_sources=["env vars (masked)", "ALBERT_LLM_PROVIDER", "ALBERT_LLM_MODEL"],
            promotion_state=PROMOTION_PROPOSED,
            inputs_schema={},
            output_schema={
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "model": {"type": "string"},
                    "fallback_available": {"type": "boolean"},
                },
            },
            reason_existing_insufficient="No existing capability reads LLM provider config without exposing secrets",
        )

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        provider = os.getenv("ALBERT_LLM_PROVIDER", "openai")
        model = os.getenv("ALBERT_LLM_MODEL", "")
        qgpt_model = os.getenv("QGPT_MODEL", "")
        fallback_model = os.getenv("QGPT_FALLBACK_MODEL", "")

        # Mask secrets — never expose API keys
        has_openai = bool(os.getenv("OPENAI_API_KEY") or os.getenv("QGPT_API_KEY"))
        has_deepseek = bool(os.getenv("DEEPSEEK_API_KEY"))
        has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))

        resolved_model = model or qgpt_model or "gpt-4.1-mini (default)"
        return {
            "status": "OK",
            "data": {
                "provider": provider,
                "model": resolved_model,
                "fallback_model": fallback_model or "none",
                "providers_configured": {
                    "openai": has_openai,
                    "deepseek": has_deepseek,
                    "anthropic": has_anthropic,
                },
                "secrets_masked": True,
                # Note: field names avoid "api_key"/"secret" to prevent false secret-leak detection
            },
            "summary": (
                f"Provider: {provider} | Model: {resolved_model} | "
                f"Fallback: {fallback_model or 'none'} | "
                f"Keys: openai={'✅' if has_openai else '❌'} "
                f"deepseek={'✅' if has_deepseek else '❌'} "
                f"anthropic={'✅' if has_anthropic else '❌'}"
            ),
        }
