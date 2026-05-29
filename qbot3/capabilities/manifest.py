#!/usr/bin/env python3
"""QBot3 Capability Manifest — validation and schema checks.

Every capability must pass manifest validation before it can be promoted to 'active'.
"""

from __future__ import annotations

from typing import Any

from qbot3.capabilities.base import (
    Capability, ALLOWED_SAFETY_CLASSES, ALLOWED_PROMOTION_STATES,
    AUTO_BUILDABLE_TYPES, PROMOTION_ACTIVE,
)


def validate_manifest(cap: Capability) -> list[str]:
    errors: list[str] = []
    d = cap.definition

    if not d.name:
        errors.append("name is required")
    if not d.description:
        errors.append("description is required")
    if d.safety_class not in ALLOWED_SAFETY_CLASSES:
        errors.append(f"Invalid safety_class: {d.safety_class}")
    if d.promotion_state not in ALLOWED_PROMOTION_STATES:
        errors.append(f"Invalid promotion_state: {d.promotion_state}")
    if not isinstance(d.inputs_schema, dict):
        errors.append("inputs_schema must be a dict")
    if not isinstance(d.output_schema, dict):
        errors.append("output_schema must be a dict")
    if not isinstance(d.data_sources, list):
        errors.append("data_sources must be a list")
    if d.capability_type and d.safety_class == "READ_ONLY" and d.capability_type not in ("READ_ONLY_FILE", "READ_ONLY_DB", "READ_ONLY_API"):
        errors.append(f"Unsupported READ_ONLY capability_type: {d.capability_type}")

    return errors


def can_promote_to_active(cap: Capability) -> tuple[bool, list[str]]:
    errors = validate_manifest(cap)
    if errors:
        return False, errors

    d = cap.definition
    if d.promotion_state == "active":
        return True, []

    # Active requires tests — verify the capability module path for test existence
    if not _has_test(cap):
        errors.append("Active capabilities must have tests (test_ cap_module.py in tests/)")

    # Active must have valid data_sources
    if not d.data_sources:
        errors.append("Active capabilities must declare data_sources")

    return len(errors) == 0, errors


def _has_test(cap: Capability) -> bool:
    import os
    name = cap.definition.name
    test_path = f"/opt/qbot/app/tests/test_capability_{name}.py"
    alt_path = f"/opt/qbot/app/tests/test_cap_{name}.py"
    return os.path.isfile(test_path) or os.path.isfile(alt_path)
