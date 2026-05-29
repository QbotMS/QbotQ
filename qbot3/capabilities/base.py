#!/usr/bin/env python3
"""QBot3 Capability — standard contract for internal capabilities.

Public MCP tools: only qbot.query and qbot.action_execute.
Internal capabilities are discovered and called by qbot.query only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, NOT_IMPLEMENTED

# ── Promotion states ──────────────────────────────────────────────────
PROMOTION_PROPOSED = "proposed"
PROMOTION_DRAFT = "draft"
PROMOTION_TESTED = "tested"
PROMOTION_ACTIVE = "active"
PROMOTION_DISABLED = "disabled"

# ── Safety classes ────────────────────────────────────────────────────
SAFETY_READ_ONLY_CONFIG = "READ_ONLY_CONFIG"
SAFETY_READ_ONLY_FILE = "READ_ONLY_FILE"
SAFETY_READ_ONLY_DB = "READ_ONLY_DB"
SAFETY_READ_ONLY_HTTP_STATUS = "READ_ONLY_HTTP_STATUS"
SAFETY_WRITE_DRAFT = "WRITE_DRAFT"
SAFETY_WRITE_EXECUTE = "WRITE_EXECUTE"
SAFETY_DESTRUCTIVE_BLOCKED = "DESTRUCTIVE_BLOCKED"

# Groups
READ_ONLY_SAFETY = (
    SAFETY_READ_ONLY_CONFIG, SAFETY_READ_ONLY_FILE,
    SAFETY_READ_ONLY_DB, SAFETY_READ_ONLY_HTTP_STATUS,
)
WRITE_SAFETY = (SAFETY_WRITE_DRAFT, SAFETY_WRITE_EXECUTE)
ALLOWED_SAFETY_CLASSES = READ_ONLY_SAFETY + WRITE_SAFETY + (SAFETY_DESTRUCTIVE_BLOCKED,)
ALLOWED_PROMOTION_STATES = (
    PROMOTION_PROPOSED, PROMOTION_DRAFT, PROMOTION_TESTED,
    PROMOTION_ACTIVE, PROMOTION_DISABLED,
)

# Auto-buildable types (Albert can auto-generate these)
AUTO_BUILDABLE_TYPES = (
    SAFETY_READ_ONLY_CONFIG, SAFETY_READ_ONLY_FILE,
    SAFETY_READ_ONLY_DB, SAFETY_READ_ONLY_HTTP_STATUS,
)
# Not auto-buildable (proposal only, manual implementation required)
NON_AUTO_BUILDABLE_TYPES = (SAFETY_WRITE_DRAFT, SAFETY_WRITE_EXECUTE, SAFETY_DESTRUCTIVE_BLOCKED)


def is_auto_buildable(safety_class: str) -> bool:
    return safety_class in AUTO_BUILDABLE_TYPES


def is_read_only(safety_class: str) -> bool:
    return safety_class in READ_ONLY_SAFETY


def is_write(safety_class: str) -> bool:
    return safety_class in WRITE_SAFETY


# ── Capability proposal model ──────────────────────────────────────────
@dataclass
class CapabilityProposal:
    name: str
    description: str
    domain: str
    safety_class: str = SAFETY_READ_ONLY_FILE
    data_sources: list[str] = field(default_factory=list)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    risks: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    tests_required: list[str] = field(default_factory=list)
    promotion_state: str = PROMOTION_PROPOSED
    auto_buildable: bool = False
    reason_existing_insufficient: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description[:200],
            "domain": self.domain,
            "safety_class": self.safety_class,
            "data_sources": self.data_sources,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "risks": self.risks,
            "forbidden_actions": self.forbidden_actions,
            "tests_required": self.tests_required,
            "promotion_state": self.promotion_state,
            "auto_buildable": self.auto_buildable,
            "reason_existing_insufficient": self.reason_existing_insufficient[:300],
        }


# ── Capability contract ───────────────────────────────────────────────
@dataclass
class CapabilityDef:
    name: str
    description: str
    safety_class: str = SAFETY_READ_ONLY_FILE
    inputs_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    data_sources: list[str] = field(default_factory=list)
    promotion_state: str = PROMOTION_DRAFT
    capability_type: str = SAFETY_READ_ONLY_FILE
    reason_existing_insufficient: str = ""
    manifest_version: int = 2

    def __post_init__(self) -> None:
        if self.safety_class not in ALLOWED_SAFETY_CLASSES:
            raise ValueError(f"Invalid safety_class: {self.safety_class}")
        if self.promotion_state not in ALLOWED_PROMOTION_STATES:
            raise ValueError(f"Invalid promotion_state: {self.promotion_state}")


class Capability(ABC):
    def __init__(self) -> None:
        self._def = self.manifest()

    @abstractmethod
    def manifest(self) -> CapabilityDef:
        ...

    @abstractmethod
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        ...

    @property
    def definition(self) -> CapabilityDef:
        return self._def

    def is_active(self) -> bool:
        return self._def.promotion_state == PROMOTION_ACTIVE

    def is_auto_buildable(self) -> bool:
        return is_auto_buildable(self._def.safety_class)

    def is_read_only(self) -> bool:
        return is_read_only(self._def.safety_class)

    def summary(self) -> dict[str, Any]:
        d = self._def
        return {
            "name": d.name,
            "description": d.description[:120],
            "safety_class": d.safety_class,
            "promotion_state": d.promotion_state,
            "capability_type": d.capability_type,
            "data_sources": d.data_sources,
            "is_active": self.is_active(),
            "auto_buildable": self.is_auto_buildable(),
        }
