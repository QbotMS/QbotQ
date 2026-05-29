#!/usr/bin/env python3
"""QBot3 Capability Registry — discovers and loads internal capabilities.

Usage:
  from qbot3.capabilities import capability_registry, find_capability
  cap = find_capability("daily_report_status")
  if cap and cap.is_active():
      result = cap.run(context)
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any

from qbot3.capabilities.base import (
    Capability, CapabilityDef, CapabilityProposal,
    PROMOTION_ACTIVE, PROMOTION_DRAFT, PROMOTION_PROPOSED,
    PROMOTION_TESTED, PROMOTION_DISABLED,
    SAFETY_READ_ONLY_CONFIG, SAFETY_READ_ONLY_FILE,
    SAFETY_READ_ONLY_DB, SAFETY_READ_ONLY_HTTP_STATUS,
    is_auto_buildable,
)

_CAPABILITY_REGISTRY: dict[str, Capability] = {}
_REGISTRY_INITIALIZED = False

# Known intent -> proposal generators
_INTENT_PROPOSALS: dict[str, dict[str, Any]] = {
    "llm_status": {
        "name": "llm_status",
        "description": "Status używanego modelu LLM i providera. Tylko odczyt — bez sekretów.",
        "domain": "system",
        "safety_class": SAFETY_READ_ONLY_CONFIG,
        "data_sources": ["env vars (masked)", "provider config"],
        "input_schema": {},
        "output_schema": {
            "provider": "str",
            "model": "str",
            "fallback_available": "bool",
            "fallback_used": "bool",
        },
        "risks": ["żadne sekrety nie są ujawniane"],
        "forbidden_actions": ["logowanie env", "wypisywanie API keys"],
        "tests_required": ["schema valid", "no secrets in output", "run has no side effects"],
        "auto_buildable": True,
    },
    "workflow_status": {
        "name": "workflow_status",
        "description": "Status zewnętrznego workflow Q. Zwraca źródła, ostatni znany stan, możliwe read-only kroki.",
        "domain": "system",
        "safety_class": SAFETY_READ_ONLY_FILE,
        "data_sources": ["config", "state files", "recent logs"],
        "input_schema": {"workflow_name": {"type": "string"}},
        "output_schema": {
            "workflow": "str",
            "sources_checked": "list",
            "last_known_status": "str",
            "read_only_possible": "bool",
        },
        "risks": ["brak — tylko odczyt istniejących plików"],
        "forbidden_actions": ["uruchamianie workflow", "wysyłanie komend"],
        "tests_required": ["schema valid", "run has no side effects"],
        "auto_buildable": False,  # needs domain knowledge per workflow
    },
}


def _discover_capabilities() -> dict[str, Capability]:
    registry: dict[str, Capability] = {}
    pkg_path = Path(__file__).parent
    for importer, modname, ispkg in pkgutil.iter_modules([str(pkg_path)]):
        if modname in ("base", "__init__", "manifest", "test_harness"):
            continue
        if ispkg:
            subpkg = importlib.import_module(f"qbot3.capabilities.{modname}")
            subpath = pkg_path / modname
            for sub_importer, sub_modname, sub_ispkg in pkgutil.iter_modules([str(subpath)]):
                if sub_modname.startswith("_"):
                    continue
                full_modname = f"qbot3.capabilities.{modname}.{sub_modname}"
                try:
                    mod = importlib.import_module(full_modname)
                    for attr_name in dir(mod):
                        attr = getattr(mod, attr_name)
                        if isinstance(attr, type) and issubclass(attr, Capability) and attr is not Capability:
                            try:
                                instance = attr()
                                name = instance.definition.name
                                if name in registry:
                                    raise RuntimeError(f"Duplicate capability name: {name}")
                                registry[name] = instance
                            except Exception as exc:
                                print(f"  ⚠️  Capability {full_modname}.{attr_name}: {exc}")
                except Exception as exc:
                    print(f"  ⚠️  Capability module {full_modname}: {exc}")
    return registry


def init_registry() -> dict[str, Capability]:
    global _CAPABILITY_REGISTRY, _REGISTRY_INITIALIZED
    if _REGISTRY_INITIALIZED:
        return _CAPABILITY_REGISTRY
    _CAPABILITY_REGISTRY = _discover_capabilities()
    _REGISTRY_INITIALIZED = True
    return _CAPABILITY_REGISTRY


def capability_registry() -> dict[str, Capability]:
    return init_registry()


def find_capability(name: str) -> Capability | None:
    return init_registry().get(name)


def find_capability_by_intent(intent: str) -> Capability | None:
    """Match a capability by intent name (fuzzy: exact match or intent in description)."""
    il = intent.lower()
    for name, cap in init_registry().items():
        if name.lower() == il:
            return cap
        if il in cap.definition.description.lower():
            return cap
    return None


def list_capabilities(promotion_state: str | None = None) -> list[dict[str, Any]]:
    caps = init_registry()
    result = []
    for name, cap in caps.items():
        d = cap.definition
        if promotion_state and d.promotion_state != promotion_state:
            continue
        result.append({
            "name": name,
            "description": d.description[:120],
            "safety_class": d.safety_class,
            "promotion_state": d.promotion_state,
            "capability_type": d.capability_type,
            "data_sources": d.data_sources,
            "is_active": cap.is_active(),
            "auto_buildable": cap.is_auto_buildable(),
        })
    return sorted(result, key=lambda x: x["name"])


def _save_proposal_to_workspace(proposal: CapabilityProposal) -> None:
    """Save proposal to workspace for tracking."""
    try:
        from qbot3.workspace import save_proposal
        save_proposal(proposal)
    except Exception:
        pass  # workspace not required for core function


def propose_capability(intent: str, reason: str, domain_hint: str = "") -> dict[str, Any]:
    """Generate a concrete capability proposal for a missing intent.

    Uses _INTENT_PROPOSALS for known intents, otherwise generates a generic proposal.
    Saves all proposals to workspace/ for tracking.
    """
    il = intent.lower().replace(" ", "_")
    auto_buildable = False
    forbidden = ["write", "upload", "delete", "modify", "unlock", "send"]
    risks = ["brak — tylko odczyt"]

    # Check known proposals
    for key, proposal in _INTENT_PROPOSALS.items():
        if key in il or il in key:
            cap = CapabilityProposal(**proposal)
            cap.reason_existing_insufficient = reason
            _save_proposal_to_workspace(cap)
            return {
                "status": "CAPABILITY_MISSING",
                "intent": intent,
                "reason": reason,
                "proposal": cap.to_dict(),
                "auto_buildable": cap.auto_buildable,
                "message": (
                    f"QBot3 nie ma aktywnej capability dla '{intent}'. "
                    f"Propozycja: '{cap.name}' ({cap.safety_class}, auto_buildable={cap.auto_buildable}). "
                    f"Źródła: {cap.data_sources}. "
                    f"Zakazane: {cap.forbidden_actions}. "
                    f"Utwórz w qbot3/capabilities/ i promuj do active."
                ),
            }

    # Domain-based heuristic proposal
    domain = domain_hint or il
    if any(k in domain for k in ("config", "status", "health", "version", "info")):
        auto_buildable = True
        safety = SAFETY_READ_ONLY_CONFIG
        data_sources = ["env vars (masked)", "runtime config"]
    elif any(k in domain for k in ("file", "log", "report")):
        auto_buildable = True
        safety = SAFETY_READ_ONLY_FILE
        data_sources = ["file system paths"]
    elif any(k in domain for k in ("db", "database", "sql", "query")):
        auto_buildable = True
        safety = SAFETY_READ_ONLY_DB
        data_sources = ["DB tables"]
    elif any(k in domain for k in ("http", "endpoint", "api")):
        auto_buildable = True
        safety = SAFETY_READ_ONLY_HTTP_STATUS
        data_sources = ["HTTP endpoint"]
    else:
        auto_buildable = False
        safety = SAFETY_READ_ONLY_FILE
        data_sources = ["unknown — needs investigation"]
        forbidden = ["write", "upload", "delete", "modify", "unlock", "send", "exec"]

    if auto_buildable:
        risks = ["brak — tylko odczyt, żadnych skutków ubocznych"]

    proposal = {
        "name": f"{domain.replace('-', '_')}_status",
        "description": f"Status/odczyt dla domeny '{domain}'. Tylko read-only.",
        "domain": domain,
        "safety_class": safety,
        "data_sources": data_sources,
        "input_schema": {},
        "output_schema": {"status": "str", "data": "dict"},
        "risks": risks,
        "forbidden_actions": forbidden,
        "tests_required": [
            "schema valid",
            "no secrets in output",
            "run has no side effects",
            "import works",
        ],
        "promotion_state": PROMOTION_PROPOSED,
        "auto_buildable": auto_buildable,
        "reason_existing_insufficient": reason,
    }

    # Save generic proposal to workspace
    try:
        cap = CapabilityProposal(**proposal)
        _save_proposal_to_workspace(cap)
    except Exception:
        pass

    return {
        "status": "CAPABILITY_MISSING",
        "intent": intent,
        "reason": reason,
        "proposal": proposal,
        "auto_buildable": auto_buildable,
        "message": (
            f"QBot3 nie ma capability dla '{intent}'. "
            f"Propozycja: '{proposal['name']}' ({proposal['safety_class']}, "
            f"auto_buildable={auto_buildable}). "
            f"Źródła: {proposal['data_sources']}. "
            f"Zakazane: {proposal['forbidden_actions']}. "
            f"{'Możliwy automatyczny draft.' if auto_buildable else 'Wymaga ręcznej implementacji.'}"
        ),
    }
