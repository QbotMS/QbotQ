#!/usr/bin/env python3
"""QBot3 LLM Provider Interface — provider-agnostic, swappable via ENV.

Each provider implements:
  plan(context, tools, user_message) -> dict  (plan JSON)
  answer(context, plan, tool_results) -> dict  (answer JSON)

Providers are selected via ALBERT_LLM_PROVIDER env var.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlanResult:
    intent: str = ""
    mode: str = "read_only"  # read_only | plan_only | write
    tools_to_call: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    write_action: str | None = None
    write_payload: dict[str, Any] = field(default_factory=dict)
    requires_confirm: bool = False
    confidence: float = 0.0
    needs_clarification: bool = False
    clarification_question: str = ""
    needed_context: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnswerResult:
    answer: str = ""
    status: str = "ok"  # ok | partial | no_data | draft | clarify | error
    confidence: str = "medium"  # low | medium | high
    missing_fields: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    @abstractmethod
    def plan(self, context: dict[str, Any], tools_desc: list[dict[str, Any]], user_message: str) -> PlanResult:
        ...

    @abstractmethod
    def answer(self, context: dict[str, Any], plan: dict[str, Any], tool_results: list[dict[str, Any]]) -> AnswerResult:
        ...


def get_llm_provider() -> LLMProvider:
    provider_name = os.getenv("ALBERT_LLM_PROVIDER", "openai").lower().strip()
    if provider_name == "mock":
        from qbot3.llm.mock_provider import MockProvider
        return MockProvider()
    if provider_name == "deepseek":
        from qbot3.llm.deepseek_provider import DeepSeekProvider
        return DeepSeekProvider()
    from qbot3.llm.openai_provider import OpenAIProvider
    return OpenAIProvider()
