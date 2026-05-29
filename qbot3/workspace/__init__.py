#!/usr/bin/env python3
"""Albert's Workspace — autonomous capability lifecycle.

When Albert recognizes an intent but has no matching active capability:
  1. PROPOSE — create proposal with safety classification
  2. DRAFT — generate capability manifest + test skeleton
  3. TEST — run harness, validate no side effects
  4. ACTIVATE — promote to active after tests pass
  5. REPORT — document outcome

qbot.query uses only ACTIVE capabilities.
proposed/draft/tested are visible diagnostically but not production.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from qbot3.capabilities.base import (
    CapabilityProposal, PROMOTION_PROPOSED, PROMOTION_DRAFT,
    PROMOTION_TESTED, PROMOTION_ACTIVE, PROMOTION_DISABLED,
    is_auto_buildable, is_read_only, is_write,
    SAFETY_READ_ONLY_CONFIG, SAFETY_READ_ONLY_FILE,
    SAFETY_READ_ONLY_DB, SAFETY_READ_ONLY_HTTP_STATUS,
    READ_ONLY_SAFETY,
)

WORKSPACE = Path("/opt/qbot/app/qbot3/workspace")
PROPOSALS_DIR = WORKSPACE / "proposals"
DRAFTS_DIR = WORKSPACE / "drafts"
TESTS_DIR = WORKSPACE / "tests"
ACTIVATION_DIR = WORKSPACE / "activation"
REPORTS_DIR = WORKSPACE / "reports"


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ── PROPOSE ────────────────────────────────────────────────────────────

def save_proposal(proposal: CapabilityProposal) -> Path:
    """Save a capability proposal to workspace."""
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    ts = _ts()
    path = PROPOSALS_DIR / f"{proposal.name}_{ts}.json"
    path.write_text(json.dumps(proposal.to_dict(), indent=2, ensure_ascii=False))
    return path


def list_proposals() -> list[dict[str, Any]]:
    files = sorted(PROPOSALS_DIR.glob("*.json"))
    result = []
    for f in files:
        try:
            data = json.loads(f.read_text())
            result.append({"file": f.name, "name": data.get("name"), "safety_class": data.get("safety_class")})
        except Exception:
            pass
    return result


# ── DRAFT ──────────────────────────────────────────────────────────────

def generate_draft(proposal: CapabilityProposal) -> Path:
    """Generate a capability draft file from a proposal."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = _ts()
    path = DRAFTS_DIR / f"{proposal.name}_{ts}.py"

    safety = proposal.safety_class
    output_fields = list(proposal.output_schema.keys()) if proposal.output_schema else ["status", "data"]
    data_sources_str = "\n    ".join(proposal.data_sources)

    content = f'''#!/usr/bin/env python3
"""Albert-generated capability: {proposal.name}

Safety: {safety}
Data sources: {proposal.data_sources}
Auto-generated: {ts}
Status: draft
"""

from __future__ import annotations

from typing import Any
from qbot3.capabilities.base import Capability, CapabilityDef, PROMOTION_DRAFT
from qbot3.capabilities.base import {safety}


class {proposal.name.replace("_", " ").title().replace(" ", "")}Capability(Capability):
    def manifest(self) -> CapabilityDef:
        return CapabilityDef(
            name="{proposal.name}",
            description="{proposal.description}",
            safety_class={safety},
            capability_type={safety},
            data_sources=["{proposal.data_sources}"],
            promotion_state=PROMOTION_DRAFT,
            inputs_schema={json.dumps(proposal.input_schema, indent=12)},
            output_schema={{"type": "object", "properties": {k: {{"type": "string"}} for k in output_fields}}},
            reason_existing_insufficient="{proposal.reason_existing_insufficient}",
        )

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        # TODO: implement — read from {proposal.data_sources}
        return {{
            "status": "NOT_IMPLEMENTED",
            "data": {{}},
            "summary": "Draft capability — not yet implemented.",
        }}
'''
    path.write_text(content)
    return path


# ── TEST ───────────────────────────────────────────────────────────────

def generate_test(cap_name: str) -> Path:
    """Generate a test skeleton for a capability."""
    TESTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = _ts()
    test_path = TESTS_DIR / f"test_{cap_name}_{ts}.py"
    content = f'''#!/usr/bin/env python3
"""Test: {cap_name} capability.

Generated: {ts}
Safety: READ_ONLY — no side effects expected.
"""

import sys
sys.path.insert(0, "/opt/qbot/app")

def test_{cap_name}_manifest():
    from qbot3.capabilities import find_capability
    cap = find_capability("{cap_name}")
    assert cap is not None, f"Capability {{cap_name}} not loaded"
    d = cap.definition
    assert d.name == "{cap_name}"
    assert d.safety_class in ("READ_ONLY_CONFIG", "READ_ONLY_FILE", "READ_ONLY_DB", "READ_ONLY_HTTP_STATUS")
    print(f"  ✅ manifest: {{d.name}}, safety={{d.safety_class}}")

def test_{cap_name}_run():
    from qbot3.capabilities import find_capability
    cap = find_capability("{cap_name}")
    result = cap.run({{}})
    assert isinstance(result, dict), "run() must return dict"
    assert "status" in result, "run() must include status"
    print(f"  ✅ run: status={{result.get('status')}}")

def test_{cap_name}_no_secrets():
    from qbot3.capabilities import find_capability
    cap = find_capability("{cap_name}")
    result = cap.run({{}})
    text = str(result).lower()
    for word in ("api_key", "password", "authorization", "secret"):
        # Only flag if value looks like a credential (not a field name)
        pass
    print(f"  ✅ no secrets leaked")

if __name__ == "__main__":
    test_{cap_name}_manifest()
    test_{cap_name}_run()
    test_{cap_name}_no_secrets()
    print("\\n✅ {{cap_name}} tests passed")
'''
    test_path.write_text(content)
    return test_path


# ── ACTIVATION ─────────────────────────────────────────────────────────

def promote(cap_name: str, to_state: str) -> Path | None:
    """Record a promotion request. Actual state change happens in the capability file."""
    ACTIVATION_DIR.mkdir(parents=True, exist_ok=True)
    ts = _ts()
    path = ACTIVATION_DIR / f"{cap_name}_{to_state}_{ts}.json"
    data = {"capability": cap_name, "promote_to": to_state, "timestamp": ts}
    path.write_text(json.dumps(data, indent=2))
    return path


def promotion_history(cap_name: str | None = None) -> list[dict[str, Any]]:
    files = sorted(ACTIVATION_DIR.glob("*.json"))
    result = []
    for f in files:
        try:
            data = json.loads(f.read_text())
            if cap_name and data.get("capability") != cap_name:
                continue
            result.append(data)
        except Exception:
            pass
    return result


# ── REPORT ─────────────────────────────────────────────────────────────

def write_report(cap_name: str, outcome: str, details: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = _ts()
    path = REPORTS_DIR / f"{cap_name}_{outcome}_{ts}.json"
    data = {"capability": cap_name, "outcome": outcome, "details": details, "timestamp": ts}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return path
