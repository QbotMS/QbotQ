#!/usr/bin/env python3
"""patch_planner_handler.py — tylko handler + keywords w qbot_query_handler.py."""

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
    handler = f"{BASE}/qbot_query_handler.py"
    print("=== patch_planner_handler ===")
    patch_file(handler, KW_OLD, KW_NEW, "planner_kw")
    patch_file(handler, HANDLER_OLD, HANDLER_NEW, "planner_handler")

    # .env placeholdery
    env_path = f"{BASE}/.env"
    env_src = open(env_path, encoding="utf-8").read()
    if "QBOT_PLANNER_API_KEY" not in env_src:
        with open(env_path, "a") as f:
            f.write("\n# OpenAI primary Planner\nQBOT_PLANNER_API_KEY=\nQBOT_PLANNER_MODEL=gpt-4o\nQBOT_PLANNER_BASE_URL=https://api.openai.com/v1\nQBOT_PLANNER_GEMINI_MODEL=google/gemini-2.5-pro\n")
        print("  OK .env: dodano placeholdery")
    else:
        print("  .env: QBOT_PLANNER_* juz sa")

    print("\nOK. systemctl restart qbot-api")


if __name__ == "__main__":
    main()
