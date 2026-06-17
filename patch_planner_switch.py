#!/usr/bin/env python3
"""patch_planner_switch.py — OpenAI primary + Gemini PRO fallback + przełączanie przez query."""

import ast, os, shutil
from datetime import datetime

BASE = "/opt/qbot/app"


def patch_file(path, old, new, label):
    src = open(path, encoding="utf-8").read()
    if old not in src:
        raise SystemExit(f"BLAD: anchor '{label}' nie znaleziony w {path}")
    patched = src.replace(old, new, 1)
    ast.parse(patched)
    bak = path + ".bak." + datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, bak)
    open(path, "w", encoding="utf-8").write(patched)
    print(f"  OK patch: {path}")


# ─────────────────────────────────────────────────────────────
# 1. core/planner.py — override file + Gemini PRO + plan_routes
# ─────────────────────────────────────────────────────────────

PLANNER_OLD = '''\
from __future__ import annotations

import json
import logging
import os
from typing import Any

_log = logging.getLogger("qbot.planner")
_MAX_STEPS = 6'''

PLANNER_NEW = '''\
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

_log = logging.getLogger("qbot.planner")
_MAX_STEPS = 6

# Plik override: "openai" lub "gemini" — przełączany przez intent planner_switch
_OVERRIDE_FILE = Path(__file__).parent.parent / ".planner_active"


def _get_active_provider() -> str:
    """Zwraca aktywnego providera: 'openai' lub 'gemini'."""
    try:
        v = _OVERRIDE_FILE.read_text(encoding="utf-8").strip().lower()
        if v in ("openai", "gemini"):
            return v
    except FileNotFoundError:
        pass
    key, _, model = _planner_config()
    return "openai" if (key and model) else "gemini"


def set_active_provider(name: str) -> str:
    """Zapisuje aktywnego providera. Zwraca nowa wartosc."""
    name = name.lower().strip()
    if name not in ("openai", "gemini"):
        raise ValueError(f"Nieznany provider: {name}. Dozwolone: openai, gemini")
    _OVERRIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _OVERRIDE_FILE.write_text(name, encoding="utf-8")
    _log.info("Planner provider ustawiony na: %s", name)
    return name'''

GEMINI_OLD = '''\
def _plan_routes_gemini_fallback(question: str) -> dict[str, Any]:
    """Fallback: Gemini free (istniejacy klucz QGPT_API_KEY)."""
    try:
        from qbot_config import QGPT_API_KEY, QGPT_BASE_URL, QGPT_MODEL
        key = QGPT_API_KEY or ""
        url = (QGPT_BASE_URL or "").rstrip("/")
        # Upgrade modelu dla Plannera jesli to flash-lite
        model = QGPT_MODEL or ""
        if "flash-lite" in model:
            model = "gemini-2.5-flash"
    except Exception:
        key, url, model = "", "", "gemini-2.5-flash"

    _log.info("Planner Gemini fallback: model=%s", model)
    return _plan_with_albert(question, key, url, model, "gemini_fallback")'''

GEMINI_NEW = '''\
def _plan_routes_gemini_fallback(question: str) -> dict[str, Any]:
    """Fallback/override: Gemini PRO przez QGPT endpoint (OpenRouter lub Google AI)."""
    try:
        from qbot_config import QGPT_API_KEY, QGPT_BASE_URL
        key = os.getenv("QBOT_PLANNER_GEMINI_API_KEY") or QGPT_API_KEY or ""
        url = (os.getenv("QBOT_PLANNER_GEMINI_BASE_URL") or QGPT_BASE_URL or "").rstrip("/")
        model = os.getenv("QBOT_PLANNER_GEMINI_MODEL", "google/gemini-2.5-pro")
    except Exception:
        key, url, model = "", "", "google/gemini-2.5-pro"

    _log.info("Planner Gemini PRO: model=%s", model)
    return _plan_with_albert(question, key, url, model, "gemini_pro")'''

PLAN_OLD = '''\
def plan_routes(question: str) -> dict[str, Any]:
    """Glowna funkcja Plannera.

    Hierarchia: primary (OpenAI/dowolny) -> Gemini free -> RuntimeError -> keyword handler.
    """
    key, url, model = _planner_config()

    if key and model:
        try:
            _log.info("Planner primary: model=%s url=%s q=%s", model, url, question[:60])
            return _plan_with_albert(question, key, url, model, "primary_" + model)
        except Exception as exc:
            _log.warning("Planner primary error (%s) -> Gemini fallback", exc)

    return _plan_routes_gemini_fallback(question)'''

PLAN_NEW = '''\
def plan_routes(question: str) -> dict[str, Any]:
    """Glowna funkcja Plannera.

    Hierarchia wg _get_active_provider():
      openai: OpenAI primary -> Gemini PRO fallback na blad
      gemini: Gemini PRO bezposrednio
    """
    provider = _get_active_provider()
    _log.info("Planner active_provider=%s q=%s", provider, question[:60])

    if provider == "openai":
        key, url, model = _planner_config()
        if key and model:
            try:
                result = _plan_with_albert(question, key, url, model, "openai_" + model)
                result["active_provider"] = "openai"
                return result
            except Exception as exc:
                _log.warning("Planner OpenAI error (%s) -> Gemini PRO fallback", exc)
        else:
            _log.warning("Planner: brak QBOT_PLANNER_API_KEY/MODEL -> Gemini PRO")

    result = _plan_routes_gemini_fallback(question)
    result["active_provider"] = "gemini"
    return result'''

# ─────────────────────────────────────────────────────────────
# 2. qbot_query_handler.py — keyword intent + handler
# ─────────────────────────────────────────────────────────────

KW_OLD = '    (["/help", "help", "pomoc", "co umiesz", "co potrafisz", "lista komend", "komendy", "funkcje qbot", "co mozesz"], "qbot_help"),'

KW_NEW = '''    (["planner openai", "planner gpt", "przełącz planner na openai", "przelacz planner na openai",
       "ustaw planner openai", "aktywuj openai planner"], "planner_switch_openai"),
    (["planner gemini", "przełącz planner na gemini", "przelacz planner na gemini",
       "ustaw planner gemini", "aktywuj gemini planner"], "planner_switch_gemini"),
    (["aktywny planner", "który planner", "status planner", "planner status",
       "jaki planner", "aktywny llm", "planner aktywny"], "planner_status"),
    (["/help", "help", "pomoc", "co umiesz", "co potrafisz", "lista komend", "komendy", "funkcje qbot", "co mozesz"], "qbot_help"),'''

HANDLER_OLD = '    if intent == "qbot_help":\n        return _handle_qbot_help()'

HANDLER_NEW = '''    if intent in ("planner_switch_openai", "planner_switch_gemini", "planner_status"):
        try:
            from core.planner import set_active_provider, _get_active_provider
            if intent == "planner_switch_openai":
                set_active_provider("openai")
                _msg = "Planner: OpenAI (GPT) aktywny. Nastepne zapytania trasowe uzywaja GPT."
            elif intent == "planner_switch_gemini":
                set_active_provider("gemini")
                _msg = "Planner: Gemini PRO aktywny. Nastepne zapytania trasowe uzywaja Gemini."
            else:
                _active = _get_active_provider()
                _msg = f"Aktywny planner: {_active.upper()}. Mozna zmienic: 'planner openai' lub 'planner gemini'."
            return _envelope("planner_switch", _msg, sources_used=[])
        except Exception as _ps_exc:
            return _envelope("planner_switch", f"Blad: {_ps_exc}", sources_used=[])

    if intent == "qbot_help":
        return _handle_qbot_help()'''


def main():
    planner = f"{BASE}/core/planner.py"
    handler = f"{BASE}/qbot_query_handler.py"

    print("=== patch_planner_switch ===")

    patch_file(planner, PLANNER_OLD, PLANNER_NEW, "planner_header")
    patch_file(planner, GEMINI_OLD, GEMINI_NEW, "gemini_fallback")
    patch_file(planner, PLAN_OLD, PLAN_NEW, "plan_routes")
    patch_file(handler, KW_OLD, KW_NEW, "planner_kw")
    patch_file(handler, HANDLER_OLD, HANDLER_NEW, "planner_handler")

    # .env — placeholdery
    env_path = f"{BASE}/.env"
    env_src = open(env_path, encoding="utf-8").read()
    additions = []
    if "QBOT_PLANNER_API_KEY" not in env_src:
        additions += [
            "",
            "# OpenAI primary Planner — wpisz klucz z platform.openai.com/api-keys",
            "QBOT_PLANNER_API_KEY=",
            "QBOT_PLANNER_MODEL=gpt-4o",
            "QBOT_PLANNER_BASE_URL=https://api.openai.com/v1",
            "# Gemini PRO fallback — przez QGPT endpoint (OpenRouter)",
            "QBOT_PLANNER_GEMINI_MODEL=google/gemini-2.5-pro",
        ]
    if additions:
        with open(env_path, "a", encoding="utf-8") as f:
            f.write("\n".join(additions) + "\n")
        print(f"  OK .env: dodano placeholdery")

    print("\nOK.")
    print("Wpisz klucz: echo 'QBOT_PLANNER_API_KEY=sk-...' >> /opt/qbot/app/.env")
    print("Nastepny krok: systemctl restart qbot-api")


if __name__ == "__main__":
    main()
