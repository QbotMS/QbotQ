#!/usr/bin/env python3
"""QBot3 LLM layer — provider-agnostic interface.

Usage:
  from qbot3.llm.base import get_llm_provider
  llm = get_llm_provider()
  plan = llm.plan(context, tools, user_message)
  answer = llm.answer(context, plan, tool_results)
"""

from qbot3.llm.base import get_llm_provider, LLMProvider, PlanResult, AnswerResult

__all__ = ["get_llm_provider", "LLMProvider", "PlanResult", "AnswerResult"]
