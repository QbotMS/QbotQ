#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path("/opt/qbot/app")

REQUIRED_FILES = [
    ROOT / "AGENTS.md",
    ROOT / "governance" / "claude_execution_policy.md",
    ROOT / "governance" / "data_routing.md",
    ROOT / "data_registry" / "modules.yaml",
    ROOT / "data_registry" / "routing_rules.yaml",
    ROOT / "task_specs" / "templates" / "qbot_task_spec_template.md",
    ROOT / "task_specs" / "templates" / "data_module_audit_task.md",
]

REQUIRED_MODULES = [
    "garage",
    "rider_profile",
    "routes",
    "rides",
    "qext",
    "lab",
    "system",
]

REQUIRED_HEADINGS = [
    "## Task ID",
    "## Context",
    "## Goal",
    "## Scope",
    "## Out of scope",
    "## Files to inspect",
    "## Required data",
    "## Allowed changes",
    "## Forbidden changes",
    "## Implementation steps",
    "## Tests",
    "## Acceptance criteria",
    "## Final report format",
]


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    sys.exit(1)


def main() -> int:
    for path in REQUIRED_FILES:
        if not path.is_file():
            fail(f"missing required file: {path.relative_to(ROOT)}")

    modules_text = (ROOT / "data_registry" / "modules.yaml").read_text(encoding="utf-8")
    for module in REQUIRED_MODULES:
        if f"  {module}:" not in modules_text:
            fail(f"modules.yaml is missing module: {module}")

    routing_text = (ROOT / "governance" / "data_routing.md").read_text(encoding="utf-8")
    if "Garage is not a general knowledge base" not in routing_text:
        fail("data_routing.md is missing the Garage general knowledge base rule")

    template_text = (ROOT / "task_specs" / "templates" / "qbot_task_spec_template.md").read_text(
        encoding="utf-8"
    )
    for heading in REQUIRED_HEADINGS:
        if heading not in template_text:
            fail(f"task spec template is missing heading: {heading}")

    audit_text = (ROOT / "task_specs" / "templates" / "data_module_audit_task.md").read_text(
        encoding="utf-8"
    )
    if "Garage was historically used as a broader data store." not in audit_text:
        fail("data module audit task template was not updated as expected")

    print("OK: governance artifacts validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
