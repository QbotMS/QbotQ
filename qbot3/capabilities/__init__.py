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
    Capability, CapabilityDef, PROMOTION_ACTIVE, PROMOTION_DRAFT,
    PROMOTION_TESTED, PROMOTION_DISABLED,
)

_CAPABILITY_REGISTRY: dict[str, Capability] = {}
_REGISTRY_INITIALIZED = False


def _discover_capabilities() -> dict[str, Capability]:
    registry: dict[str, Capability] = {}
    pkg_path = Path(__file__).parent
    for importer, modname, ispkg in pkgutil.iter_modules([str(pkg_path)]):
        if modname in ("base", "__init__", "manifest", "test_harness"):
            continue
        if ispkg:
            # Walk subpackages
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
        })
    return sorted(result, key=lambda x: x["name"])


def propose_capability(intent: str, reason: str) -> dict[str, Any]:
    """Generate a proposal for a missing capability."""
    return {
        "status": "CAPABILITY_MISSING",
        "intent": intent,
        "reason": reason,
        "proposal": {
            "needed_capability": f"{intent.replace(' ', '_')}_status" if intent else "custom_capability",
            "intent": intent,
            "safety_class": "READ_ONLY",
            "data_sources": ["unknown — needs investigation"],
            "required_inputs": {},
            "expected_outputs": {"status": "str", "data": "dict"},
            "reason_existing_insufficient": reason,
            "auto_buildable": False,
            "message": f"QBot3 nie ma capability dla '{intent}'. "
                       f"Potrzebna nowa capability typu READ_ONLY — zdefiniuj w qbot3/capabilities/.",
        }
    }
