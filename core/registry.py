"""core/registry.py — rejestr modułów QBot.

Jedyne źródło prawdy dla:
  - listy zarejestrowanych modułów
  - allowlisty action_execute (generowanej z manifestów)
  - domeny modułu (closed/open)

Dodawanie modułu: dopisz nazwę do _REGISTERED_MODULES i utwórz
modules/<nazwa>/manifest.py z polem MANIFEST.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any

_REGISTERED_MODULES: list[str] = [
    "nutrition",
    "routes",     # domena otwarta — Planner LLM-first
    # "wellness",  # domena zamknięta
    # "calendar",  # domena zamknięta
]

# Akcje nie należące jeszcze do żadnego modułu — usuwać w miarę dodawania modułów
_BASE_ALLOWLIST: set[str] = {
    "planning_fact_add",
    "planning_fact_update",
    "garmin_workout_create",
    "qbot_doc_append",
    "qbot_doc_replace_section",
    "qbot_doc_update",
    "rwgps_gpx_import",
    "route_poi_analyze",
    "rwgps_route_profile_sample",
    "rwgps_route_profile_export_csv",
    "qbot_artifact_put",
    "qbot_artifact_get",
}


@lru_cache(maxsize=1)
def _load_manifests() -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    for name in _REGISTERED_MODULES:
        try:
            mod = importlib.import_module(f"modules.{name}.manifest")
            manifests[name] = mod.MANIFEST
        except Exception as e:
            import logging
            logging.getLogger("qbot.registry").warning(
                "Nie można załadować manifestu modułu %s: %s", name, e
            )
    return manifests


def get_manifests() -> dict[str, dict[str, Any]]:
    return _load_manifests()


def get_allowlist() -> set[str]:
    """Zwraca pełną allowlistę action_execute — suma manifestów + base."""
    result: set[str] = set(_BASE_ALLOWLIST)
    for manifest in _load_manifests().values():
        result.update(manifest.get("write_actions", []))
    return result


def get_domain(module_name: str) -> str | None:
    """Zwraca domenę modułu ('closed' / 'open') lub None jeśli moduł nieznany."""
    m = _load_manifests().get(module_name)
    return m.get("domain") if m else None


def list_modules() -> list[str]:
    return list(_load_manifests().keys())
