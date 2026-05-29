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


PROMOTION_DRAFT = "draft"
PROMOTION_TESTED = "tested"
PROMOTION_ACTIVE = "active"
PROMOTION_DISABLED = "disabled"

SAFETY_READ_ONLY = "READ_ONLY"
SAFETY_WRITE = "WRITE"

ALLOWED_SAFETY_CLASSES = (SAFETY_READ_ONLY, SAFETY_WRITE)
ALLOWED_PROMOTION_STATES = (PROMOTION_DRAFT, PROMOTION_TESTED, PROMOTION_ACTIVE, PROMOTION_DISABLED)

# Albert can auto-build only these types
AUTO_BUILDABLE_TYPES = ("READ_ONLY_FILE", "READ_ONLY_DB")


@dataclass
class CapabilityDef:
    name: str
    description: str
    safety_class: str = SAFETY_READ_ONLY
    inputs_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    data_sources: list[str] = field(default_factory=list)
    promotion_state: str = PROMOTION_DRAFT
    capability_type: str = "READ_ONLY_FILE"
    reason_existing_insufficient: str = ""
    manifest_version: int = 1

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

    def summary(self) -> dict[str, Any]:
        d = self._def
        return {
            "name": d.name,
            "description": d.description[:120],
            "safety_class": d.safety_class,
            "promotion_state": d.promotion_state,
            "capability_type": d.capability_type,
            "data_sources": d.data_sources,
        }
