#!/usr/bin/env python3
"""patch_claude_v3.py — Claude provider: wstawia claude_funcs_src.py + plan_routes + handler."""

import ast, os, shutil
from datetime import datetime

BASE = "/opt/qbot/app"
PLANNER = f"{BASE}/core/planner.py"
HANDLER = f"{BASE}/qbot_query_handler.py"
FUNCS_SRC = f"{BASE}/claude_funcs_src.py"


def patch_file(path, old, new, label):
    src = open(path, encoding="utf-8").read()
    if old not in src:
        raise SystemExit(f"BLAD: anchor '{label}' nie znaleziony w {path}")
    patched = src.replace(old, new, 1)
    try:
        ast.parse(patched)
    except SyntaxError as e:
        raise SystemExit(f"BLAD skladni po '{label}': {e}")
    bak = path + ".bak." + datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, bak)
    open(path, "w", encoding="utf-8").write(patched)
    print(f"  OK: {path} [{label}]")


# ── 1. Wstaw funkcje Claude przed _plan_with_albert ──────────────────────────
claude_funcs = open(FUNCS_SRC, encoding="utf-8").read()
# AST check samych funkcji (jako modul z dummy importami)
_dummy = "from __future__ import annotations\nimport os\nfrom typing import Any\n_log=None\n_MAX_STEPS=6\n_SYSTEM_PROMPT=''\n" + claude_funcs
try:
    ast.parse(_dummy)
    print("  AST OK: claude_funcs_src.py")
except SyntaxError as e:
    raise SystemExit(f"BLAD skladni claude_funcs_src.py: {e}")

ALBERT_ANCHOR = "def _plan_with_albert(question: str, api_key: str, base_url: str, model: str,"
patch_file(PLANNER, ALBERT_ANCHOR, claude_funcs.rstrip() + "\n\n\n" + ALBERT_ANCHOR, "claude_functions")

# ── 2. Nowe plan_routes() ─────────────────────────────────────────────────────
OLD_PLAN = '''def plan_routes(question: str) -> dict[str, Any]:
    """Glowna funkcja Plannera.

    Hierarchia (wg _get_active_provider()):
      openai -> primary (OpenAI) -> Gemini PRO fallback
      gemini -> Gemini PRO bezposrednio
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
            _log.warning("Planner: brak QBOT_PLANNER_API_KEY lub MODEL -> Gemini PRO")

    result = _plan_routes_gemini_fallback(question)
    result["active_provider"] = "gemini"
    return result'''

NEW_PLAN = '''def _try_openai(question: str):
    """Proba OpenAI. Zwraca wynik lub None przy bledzie/braku konfiguracji."""
    key, url, model = _planner_config()
    if not (key and model):
        _log.warning("Planner OpenAI: brak QBOT_PLANNER_API_KEY/MODEL")
        return None
    try:
        result = _plan_with_albert(question, key, url, model, "openai_" + model)
        result["active_provider"] = "openai"
        return result
    except Exception as exc:
        _log.warning("Planner OpenAI error (%s)", exc)
        return None


def plan_routes(question: str) -> dict[str, Any]:
    """Glowna funkcja Plannera.

    Hierarchia wg aktywnego providera:
      claude -> Claude Sonnet -> OpenAI (gpt-4.1-mini) -> Gemini PRO
      openai -> OpenAI -> Gemini PRO
      gemini -> Gemini PRO bezposrednio
    """
    provider = _get_active_provider()
    _log.info("Planner active_provider=%s q=%s", provider, question[:60])

    if provider == "claude":
        try:
            return _plan_with_claude(question)
        except Exception as exc:
            _log.warning("Planner Claude error (%s) -> OpenAI fallback", exc)
        result = _try_openai(question)
        if result:
            result["fallback_from"] = "claude"
            return result

    elif provider == "openai":
        result = _try_openai(question)
        if result:
            return result

    result = _plan_routes_gemini_fallback(question)
    result["active_provider"] = "gemini"
    return result'''

patch_file(PLANNER, OLD_PLAN, NEW_PLAN, "plan_routes")

# ── 3. Handler keywords + block ───────────────────────────────────────────────
OLD_KW = '''    (["planner openai", "planner gpt", "przełącz planner na openai", "przelacz planner na openai",
       "ustaw planner openai", "aktywuj openai planner"], "planner_switch_openai"),
    (["planner gemini", "przełącz planner na gemini", "przelacz planner na gemini",
       "ustaw planner gemini", "aktywuj gemini planner"], "planner_switch_gemini"),
    (["aktywny planner", "który planner", "status planner", "planner status",
       "jaki planner", "aktywny llm", "planner aktywny"], "planner_status"),'''

NEW_KW = '''    (["planner claude", "przełącz planner na claude", "przelacz planner na claude",
       "ustaw planner claude", "aktywuj claude planner"], "planner_switch_claude"),
    (["planner openai", "planner gpt", "przełącz planner na openai", "przelacz planner na openai",
       "ustaw planner openai", "aktywuj openai planner"], "planner_switch_openai"),
    (["planner gemini", "przełącz planner na gemini", "przelacz planner na gemini",
       "ustaw planner gemini", "aktywuj gemini planner"], "planner_switch_gemini"),
    (["aktywny planner", "który planner", "status planner", "planner status",
       "jaki planner", "aktywny llm", "planner aktywny"], "planner_status"),'''

OLD_HANDLER = '''    if intent in ("planner_switch_openai", "planner_switch_gemini", "planner_status"):
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
            return _envelope("planner_switch", f"Blad: {_ps_exc}", sources_used=[])'''

NEW_HANDLER = '''    if intent in ("planner_switch_claude", "planner_switch_openai", "planner_switch_gemini", "planner_status"):
        try:
            from core.planner import set_active_provider, _get_active_provider
            _labels = {
                "planner_switch_claude": "claude",
                "planner_switch_openai": "openai",
                "planner_switch_gemini": "gemini",
            }
            _names = {
                "claude": "Claude Sonnet (-> OpenAI -> Gemini)",
                "openai": "OpenAI gpt-4.1-mini (-> Gemini)",
                "gemini": "Gemini PRO",
            }
            if intent in _labels:
                _prov = _labels[intent]
                set_active_provider(_prov)
                _msg = f"Planner: {_names[_prov]} aktywny."
            else:
                _active = _get_active_provider()
                _msg = f"Aktywny: {_active.upper()} — {_names.get(_active, _active)}. Komendy: planner claude / openai / gemini."
            return _envelope("planner_switch", _msg, sources_used=[])
        except Exception as _ps_exc:
            return _envelope("planner_switch", f"Blad: {_ps_exc}", sources_used=[])'''

patch_file(HANDLER, OLD_KW, NEW_KW, "planner_kw_claude")
patch_file(HANDLER, OLD_HANDLER, NEW_HANDLER, "planner_handler_claude")

# ── 4. .env: gpt-4o -> gpt-4.1-mini ─────────────────────────────────────────
env_path = f"{BASE}/.env"
env_src = open(env_path, encoding="utf-8").read()
if "QBOT_PLANNER_MODEL=gpt-4o\n" in env_src:
    open(env_path, "w").write(env_src.replace("QBOT_PLANNER_MODEL=gpt-4o\n", "QBOT_PLANNER_MODEL=gpt-4.1-mini\n", 1))
    print("  OK .env: gpt-4o -> gpt-4.1-mini")
else:
    print("  .env: QBOT_PLANNER_MODEL bez zmian")

print("\nOK. systemctl restart qbot-api")
