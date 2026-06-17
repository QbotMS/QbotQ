#!/usr/bin/env python3
"""patch_claude_provider.py — dodaje Claude jako provider + gpt-4.1-mini + fallback chain.

Hierarchia gdy aktywny 'claude':
  Claude Sonnet -> OpenAI (gpt-4.1-mini) -> Gemini PRO

Przełączanie przez Q:
  'planner claude' / 'planner openai' / 'planner gemini'
"""

import ast, os, shutil
from datetime import datetime

BASE = "/opt/qbot/app"
PLANNER = f"{BASE}/core/planner.py"
HANDLER = f"{BASE}/qbot_query_handler.py"


def patch_file(path, old, new, label):
    src = open(path, encoding="utf-8").read()
    if old not in src:
        raise SystemExit(f"BLAD: anchor '{label}' nie znaleziony w {path}")
    patched = src.replace(old, new, 1)
    ast.parse(patched)
    bak = path + ".bak." + datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, bak)
    open(path, "w", encoding="utf-8").write(patched)
    print(f"  OK: {path}")


# ─────────────────────────────────────────────────────────────
# 1. planner.py: rozszerz _get_active_provider + set_active_provider
# ─────────────────────────────────────────────────────────────

OLD_GET = '''\
def _get_active_provider() -> str:
    """Zwraca aktywnego providera: 'openai' lub 'gemini'."""
    try:
        v = _OVERRIDE_FILE.read_text(encoding="utf-8").strip().lower()
        if v in ("openai", "gemini"):
            return v
    except FileNotFoundError:
        pass
    # domyslnie: openai jesli klucz skonfigurowany, inaczej gemini
    key, _, model = _planner_config()
    return "openai" if (key and model) else "gemini"


def set_active_provider(name: str) -> str:
    """Zapisuje aktywnego providera do pliku. Zwraca nowa wartosc."""
    name = name.lower().strip()
    if name not in ("openai", "gemini"):
        raise ValueError(f"Nieznany provider: {name}. Dozwolone: openai, gemini")
    _OVERRIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _OVERRIDE_FILE.write_text(name, encoding="utf-8")
    _log.info("Planner provider ustawiony na: %s", name)
    return name'''

NEW_GET = '''\
_VALID_PROVIDERS = ("claude", "openai", "gemini")


def _get_active_provider() -> str:
    """Zwraca aktywnego providera: 'claude', 'openai' lub 'gemini'."""
    try:
        v = _OVERRIDE_FILE.read_text(encoding="utf-8").strip().lower()
        if v in _VALID_PROVIDERS:
            return v
    except FileNotFoundError:
        pass
    # domyslnie: openai jesli klucz skonfigurowany, inaczej gemini
    key, _, model = _planner_config()
    return "openai" if (key and model) else "gemini"


def set_active_provider(name: str) -> str:
    """Zapisuje aktywnego providera. Zwraca nowa wartosc."""
    name = name.lower().strip()
    if name not in _VALID_PROVIDERS:
        raise ValueError(f"Nieznany provider: {name}. Dozwolone: {', '.join(_VALID_PROVIDERS)}")
    _OVERRIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _OVERRIDE_FILE.write_text(name, encoding="utf-8")
    _log.info("Planner provider ustawiony na: %s", name)
    return name'''

# ─────────────────────────────────────────────────────────────
# 2. planner.py: dodaj _plan_with_claude() + _claude_config()
# ─────────────────────────────────────────────────────────────

OLD_ALBERT = '''\
def _plan_with_albert(question: str, api_key: str, base_url: str, model: str,'''

NEW_ALBERT = '''\
def _claude_config() -> tuple[str, str]:
    """Zwraca (api_key, model) dla Claude."""
    try:
        from qbot_config import load_dotenv as _load
        _load()
    except Exception:
        pass
    key = os.getenv("ANTHROPIC_API_KEY", "")
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    return key, model


def _load_route_tools_for_claude() -> tuple[list[dict], dict]:
    """Laduje narzedzia routes w formacie Anthropic (input_schema)."""
    from qbot3.tool_registry import tool_descriptions, lookup
    from modules.routes.manifest import MANIFEST

    allowed_names = set(MANIFEST.get("planner_tools", []))
    anthropic_tools = []
    tool_map: dict[str, dict] = {}

    for t in tool_descriptions():
        name = t["name"]
        if name not in allowed_names:
            continue
        spec = lookup(name)
        if not spec:
            continue
        raw_schema = t.get("args_schema") or {}
        properties: dict = {}
        required: list = []
        for param, pdef in raw_schema.items():
            properties[param] = pdef if isinstance(pdef, dict) else {"type": "string"}
            if not isinstance(pdef, dict) or pdef.get("required", True):
                required.append(param)
        anthropic_tools.append({
            "name": name,
            "description": t.get("description", ""),
            "input_schema": {"type": "object", "properties": properties, "required": required},
        })
        tool_map[name] = spec

    return anthropic_tools, tool_map


def _plan_with_claude(question: str) -> dict[str, Any]:
    """Planner z natywnym Anthropic SDK (tool_use loop)."""
    import anthropic as _ant
    key, model = _claude_config()
    if not key:
        raise RuntimeError("Brak ANTHROPIC_API_KEY")

    client = _ant.Anthropic(api_key=key)
    tools, tool_map = _load_route_tools_for_claude()
    if not tools:
        raise RuntimeError("Brak narzedzi dla modulu routes")

    messages: list[dict] = [{"role": "user", "content": question}]
    tool_log: list[str] = []

    _log.info("Planner Claude: model=%s tools=%d q=%s", model, len(tools), question[:60])

    for step in range(_MAX_STEPS):
        response = client.messages.create(
            model=model,
            max_tokens=1500,
            system=_SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )
        tool_blocks = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b.text for b in response.content if b.type == "text"]

        if not tool_blocks:
            answer = "\n".join(text_blocks).strip() or "Brak odpowiedzi od Claude."
            _log.info("Planner Claude done: steps=%d", step + 1)
            return {
                "status": "OK",
                "answer": answer,
                "intent": "planner_routes",
                "active_provider": "claude",
                "steps": step + 1,
                "tool_calls": tool_log,
                "sources_used": tool_log,
            }

        messages.append({"role": "assistant", "content": response.content})
        results_content = []
        for block in tool_blocks:
            spec = tool_map.get(block.name)
            try:
                fn = spec.get("callable") if spec else None
                wr = spec.get("wrapped") if spec else None
                res = fn(wr, block.input) if (fn and wr) else (fn(block.input) if fn else {"error": "no callable"})
            except Exception as exc:
                res = {"error": str(exc)[:200]}
            import json as _json
            results_content.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": _json.dumps(res, ensure_ascii=False, default=str)[:4000],
            })
            tool_log.append(block.name)
        messages.append({"role": "user", "content": results_content})

    raise RuntimeError(f"Claude Planner przekroczyl limit krokow ({_MAX_STEPS})")


def _plan_with_albert(question: str, api_key: str, base_url: str, model: str,'''

# ─────────────────────────────────────────────────────────────
# 3. planner.py: plan_routes() — nowa hierarchia Claude→OpenAI→Gemini
# ─────────────────────────────────────────────────────────────

OLD_PLAN = '''\
def plan_routes(question: str) -> dict[str, Any]:
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

NEW_PLAN = '''\
def _try_openai(question: str) -> dict[str, Any] | None:
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

    # Gemini PRO — ostatni fallback (lub primary gdy provider=="gemini")
    result = _plan_routes_gemini_fallback(question)
    result["active_provider"] = "gemini"
    return result'''

# ─────────────────────────────────────────────────────────────
# 4. qbot_query_handler.py — dodaj 'planner claude' do keywords i handlera
# ─────────────────────────────────────────────────────────────

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
            _labels = {"planner_switch_claude": "claude", "planner_switch_openai": "openai", "planner_switch_gemini": "gemini"}
            _names = {"claude": "Claude Sonnet (→ OpenAI → Gemini)", "openai": "OpenAI gpt-4.1-mini (→ Gemini)", "gemini": "Gemini PRO"}
            if intent in _labels:
                _prov = _labels[intent]
                set_active_provider(_prov)
                _msg = f"Planner: {_names[_prov]} aktywny."
            else:
                _active = _get_active_provider()
                _msg = f"Aktywny planner: {_active.upper()} ({_names.get(_active, _active)}). Komendy: 'planner claude / openai / gemini'."
            return _envelope("planner_switch", _msg, sources_used=[])
        except Exception as _ps_exc:
            return _envelope("planner_switch", f"Blad: {_ps_exc}", sources_used=[])'''


def main():
    print("=== patch_claude_provider ===")

    # planner.py — 3 patche
    patch_file(PLANNER, OLD_GET, NEW_GET, "get_set_provider")
    patch_file(PLANNER, OLD_ALBERT, NEW_ALBERT, "claude_functions")
    patch_file(PLANNER, OLD_PLAN, NEW_PLAN, "plan_routes")

    # handler — 2 patche
    patch_file(HANDLER, OLD_KW, NEW_KW, "planner_kw_claude")
    patch_file(HANDLER, OLD_HANDLER, NEW_HANDLER, "planner_handler_claude")

    # .env: gpt-4o -> gpt-4.1-mini
    env_path = f"{BASE}/.env"
    env_src = open(env_path, encoding="utf-8").read()
    if "QBOT_PLANNER_MODEL=gpt-4o" in env_src:
        updated = env_src.replace("QBOT_PLANNER_MODEL=gpt-4o", "QBOT_PLANNER_MODEL=gpt-4.1-mini", 1)
        open(env_path, "w", encoding="utf-8").write(updated)
        print("  OK .env: gpt-4o -> gpt-4.1-mini")
    else:
        print("  .env: QBOT_PLANNER_MODEL nie wymaga zmiany (sprawdz recznie)")

    print("\nOK. systemctl restart qbot-api")


if __name__ == "__main__":
    main()
