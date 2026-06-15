"""core/planner.py - Planner LLM-first dla domeny routes.

Hierarchia modeli (konfiguracja w /opt/qbot/app/.env):
  1. QBOT_PLANNER_API_KEY + QBOT_PLANNER_MODEL  -> primary (np. gpt-4o, claude-3-5-sonnet)
    QBOT_PLANNER_BASE_URL (opcjonalnie, domyslnie OpenAI)
  2. Gemini flash (QGPT_API_KEY + QGPT_BASE_URL)  -> fallback free

Przyklad konfiguracji OpenAI:
    QBOT_PLANNER_API_KEY=sk-...
    QBOT_PLANNER_MODEL=gpt-4o
"""

# DEPRECATED (2026-06-15, Krok 3 Albert-first): plan_routes() nie jest już wywoływane z qbot3/adapters/mcp_adapter.py - Albert obsługuje zapytania routowe bezpośrednio (toolset już kompletny, zobacz _session_notes/krok3_diagnoza.md). Plik zostaje do obserwacji, usunięcie w Kroku 5 (porządki) po potwierdzeniu że nic go nie woła.

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

_log = logging.getLogger("qbot.planner")
_MAX_STEPS = 12

# Plik override: "openai" lub "gemini" — przełączany przez intent planner_switch
_OVERRIDE_FILE = Path(os.path.join(os.path.dirname(__file__), "..", ".planner_active"))


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
    return name

_SYSTEM_PROMPT = (
    "Jestes asystentem rowerowym Michala (kolarz gravel/bikepacking, Warszawa). "
    "Odpowiadasz zwiezle po polsku. "
    "Do odpowiedzi uzywasz TYLKO dostepnych narzedzi - nie wymyslaj danych. "
    "Gdy pytanie dotyczy trasy: najpierw wyszukaj route_id, potem pobierz szczegoly. "
    "Gdy pytanie dotyczy tylko listy lub ostatniej trasy RWGPS, zakoncz po rwgps_route_list "
    "albo rwgps_route_last i nie pobieraj GPX, profilu, artefaktow ani analiz etapow. "
    "Nie uruchamiaj route_gpx_split ani route_stage_plan_analyze, chyba ze user wprost prosi "
    "o split, GPX, profil, etap albo analize. "
    "Gdy pytanie wymaga profilu wysokosci, nawierzchni, ryzyka (np. gravel/bagaz) lub innej "
    "analizy trasy, a user NIE podal numeru etapu: dziala samodzielnie - NAJPIERW "
    "rwgps_route_last (uzyskaj route_id), POTEM rwgps_route_fetch z tym route_id (uzyskaj GPX), "
    "POTEM odpowiednie narzedzie analizy (stage_gpx_analyze / route_poi_analyze / "
    "route_stage_plan_analyze). NIE proś usera o plik GPX, link ani route_id - masz narzedzia, "
    "ktore to pobiora. Pros o dane tylko jesli narzedzia faktycznie zwrocily blad/brak danych. "
    "Dla Tuscany 2026 E07 / etapu 7 / TT E07 i pytan o finalna albo aktualna trase do analiz "
    "uzywaj live route_id 55567991; nie traktuj local artifact/new_route_id 55590078 jako "
    "route_id do analiz live. Jesli w odpowiedzi lub tool call pojawi sie 55590078, zamien "
    "go na 55567991 dla analiz live. "
    "Jesli pytanie miesza terminologie Garmin (aktywnosc/trening/przejazd zarejestrowany) "
    "z RWGPS (trasa zaplanowana) w sposob niejednoznaczny - zapytaj usera ktore zrodlo ma na "
    "mysli, nie wybieraj jednego bezkrytycznie. "
    "Link do trasy w odpowiedzi nazywaj 'Link do trasy' lub 'Link', "
    "nigdy 'URL API' ani 'API'. "
    "Dla route_poi_analyze: jesli user pyta o POI/atrakcje/jedzenie/wode dla KONKRETNEGO ETAPU (np. \"etap 2\", \"stage 3\") i NIE podal wlasnego zakresu km (\"od-do\"), wywolaj route_poi_analyze z parametrem stage=<numer etapu> (oraz project_id jesli wiadomo) - NIE podawaj wtedy route_id, km_from ani km_to, system wyliczy je automatycznie z planu etapow. NIE pytaj usera o zakres km w tym przypadku. Jesli route_poi_analyze zwroci STAGE_NOT_FOUND, dopiero wtedy powiedz userowi czego brakuje (np. ze plan etapow nie zawiera tego numeru). Dla zapytan o trase NIE zwiazanych z konkretnym etapem (np. user podal wlasny route_id i zakres km), uzywaj route_id/km_from/km_to jak dotychczas. "
    "Nie uzywaj artifacts_list ani artifact_search jako kroku eksploracyjnego przed albo po wywolaniu narzedzia analizy (route_poi_analyze, rwgps_route_surface_analyze, stage_gpx_analyze, route_stage_plan_analyze) - wywoluj narzedzie analizy bezposrednio, chyba ze user wprost prosi o wyszukanie istniejacego raportu lub artefaktu. Kazde narzedzie analizy wywoluj NAJWYZEJ RAZ na zapytanie: jesli juz masz jego wynik w tej rozmowie, podsumuj go i odpowiedz - nie wywoluj go ponownie z innymi parametrami bez wyraznej potrzeby. "
    "Gdy brak danych - powiedz wprost i zaproponuj co mozna zrobic."
)


def _planner_config() -> tuple[str, str, str]:
    """Zwraca (api_key, base_url, model) dla primary Plannera."""
    try:
        from qbot_config import load_dotenv as _load
        _load()
    except Exception:
        pass

    key = os.getenv("QBOT_PLANNER_API_KEY", "")
    url = os.getenv("QBOT_PLANNER_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("QBOT_PLANNER_MODEL", "")
    return key, url, model


def _load_route_tools() -> tuple[list[dict], dict]:
    """Laduje narzedzia routes z qbot3/tool_registry + buduje OpenAI tools_spec."""
    from qbot3.tool_registry import tool_descriptions, lookup
    from modules.routes.manifest import MANIFEST

    allowed_names = set(MANIFEST.get("planner_tools", []))
    all_tools = tool_descriptions()

    filtered = [t for t in all_tools if t["name"] in allowed_names]
    tools_spec = []
    for t in filtered:
        name = t.get("name", "")
        if not name:
            continue
        args_schema = t.get("args_schema") or {}
        if not isinstance(args_schema, dict):
            args_schema = {}
        if "type" not in args_schema:
            args_schema = {"type": "object", "properties": args_schema}
        if "properties" not in args_schema:
            args_schema["properties"] = {}
        tools_spec.append({
            "type": "function",
            "function": {
                "name": name,
                "description": (t.get("description") or "")[:500],
                "parameters": args_schema,
            },
        })

    tool_map = {t["name"]: lookup(t["name"]) for t in filtered if lookup(t["name"])}

    return tools_spec, tool_map


def _execute_tool(name: str, input_args: dict, tool_map: dict) -> dict:
    spec = tool_map.get(name)
    if not spec:
        return {"error": "Nieznane narzedzie: " + name}
    callable_fn = spec.get("callable")
    wrapped = spec.get("wrapped")
    try:
        if callable_fn:
            return callable_fn(wrapped, input_args) if wrapped else callable_fn(input_args)
        return {"error": "Brak callable dla " + name}
    except Exception as exc:
        return {"error": str(exc)[:300]}


_META_NEG = ("bez profil", "bez gpx", "nie analizuj", "bez analiz", "nie pobieraj")
_META_POS = ("pokaz", "pokaż", "summary", "podsumowanie", "basic", "lista tras",
             "ostatnia tras", "ostatnie tras", "metadane", "podstawowe info", "pokaze")
_ANALYSIS = ("profil", "profile", "gpx", "etap", "stage", "split", "nawierzchn",
             "surface", "podjazd", "climb", "poi", "analiz", "atrakcj",
             "gravel", "bagaz", "bagaż", "ryzyk", "sensown", "fragment")


def _is_metadata_only(question: str) -> bool:
    """True gdy pytanie to czysta metadana (pokaz/lista/ostatnia) bez analizy."""
    ql = (question or "").lower()
    if any(n in ql for n in _META_NEG):
        return True
    if any(a in ql for a in _ANALYSIS):
        return False
    return any(p in ql for p in _META_POS)


def _is_reasoning_model(model: str) -> bool:
    ml = (model or "").lower()
    return ml.startswith(("gpt-5", "o1", "o3", "o4"))


def _oai_create_kwargs(model, messages, tools, tool_choice):
    """Args dla chat.completions.create zaleznie od typu modelu.
    Rozumujace (gpt-5*, o1/o3/o4*): max_completion_tokens, bez temperature.
    Klasyczne (gpt-4.1*, gemini*): max_tokens + temperature=0."""
    kw = {"model": model, "messages": messages, "tools": tools, "tool_choice": tool_choice}
    if _is_reasoning_model(model):
        kw["max_completion_tokens"] = 4000
    else:
        kw["max_tokens"] = 1500
        kw["temperature"] = 0
    return kw


def _oai_responses_tools(tools: list[dict]) -> list[dict]:
    """Konwersja tooli z formatu chat.completions na responses.create."""
    response_tools: list[dict] = []
    for t in tools:
        fn = t.get("function", {}) if isinstance(t, dict) else {}
        name = fn.get("name")
        if not name:
            continue
        response_tools.append({
            "type": "function",
            "name": name,
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
            "strict": fn.get("strict", False),
        })
    return response_tools


def _responses_output_text(response) -> str:
    text = (getattr(response, "output_text", None) or "").strip()
    if text:
        return text
    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", "") != "message":
            continue
        for block in getattr(item, "content", []) or []:
            if getattr(block, "type", "") == "output_text":
                part = getattr(block, "text", "")
                if part:
                    chunks.append(part)
    return " ".join(chunks).strip()


def _run_openai_tool_loop(
    question: str,
    api_key: str,
    base_url: str,
    model: str,
    label: str,
) -> dict[str, Any]:
    import openai as _openai
    import json as _json
    from qbot3.context_builder import build_context

    tools, tool_map = _load_route_tools()
    if not tools:
        raise RuntimeError("Brak narzedzi dla modulu routes")

    if _is_metadata_only(question):
        _meta_allowed = {"rwgps_route_last", "rwgps_route_list"}
        _filtered = [t for t in tools if t.get("function", {}).get("name") in _meta_allowed]
        if _filtered:
            tools = _filtered
            _log.info("Planner %s: metadata-only gate -> %d narzedzi", label, len(tools))

    client = _openai.OpenAI(api_key=api_key, base_url=base_url)
    tool_log: list[str] = []
    if _is_reasoning_model(model):
        response_tools = _oai_responses_tools(tools)
        if not response_tools:
            raise RuntimeError("Brak narzedzi dla modulu routes")
        ctx = build_context(question)
        ctx_str = ""
        if ctx:
            ctx_str = f"\n\nKontekst: {_json.dumps(ctx, ensure_ascii=False, default=str)}"
        _log.info("Planner %s: model=%s tools=%d q=%s", label, model, len(response_tools), question[:60])

        response = client.responses.create(
            model=model,
            instructions=_SYSTEM_PROMPT + ctx_str,
            reasoning={"effort": "low"},
            include=["reasoning.encrypted_content"],
            max_output_tokens=4000,
            tools=response_tools,
            input=[{"role": "user", "content": question}],
        )

        _seen: dict[str, Any] = {}
        for step in range(_MAX_STEPS):
            tool_calls = [item for item in (getattr(response, "output", []) or []) if getattr(item, "type", "") == "function_call"]
            if not tool_calls:
                answer = _responses_output_text(response) or "Brak odpowiedzi od plannera."
                return {
                    "status": "OK",
                    "answer": answer,
                    "intent": "planner_routes",
                    "planner": label,
                    "steps": step + 1,
                    "tool_calls": tool_log,
                    "sources_used": tool_log,
                }

            next_input: list[dict[str, Any]] = []
            for tc in tool_calls:
                tool_name = getattr(tc, "name", "")
                try:
                    args = _json.loads(getattr(tc, "arguments", "") or "{}")
                except Exception:
                    args = {}
                spec = tool_map.get(tool_name)
                fn = spec.get("callable") if spec else None
                wrapped = spec.get("wrapped") if spec else None
                _dkey = tool_name + "|" + _json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
                _readonly = (spec or {}).get("safety") == "read" or (spec or {}).get("mode") == "read_only"
                if _readonly and _dkey in _seen:
                    res = _seen[_dkey]
                    _log.info("Planner %s: dedup skip %s", label, tool_name)
                else:
                    try:
                        if wrapped and fn:
                            res = fn(wrapped, args)
                        elif fn:
                            res = fn(args)
                        else:
                            res = {"error": f"Brak callable dla {tool_name}"}
                    except Exception as exc:
                        res = {"error": str(exc)[:200]}
                    if _readonly:
                        _seen[_dkey] = res
                    tool_log.append(tool_name)
                next_input.append({
                    "type": "function_call_output",
                    "call_id": getattr(tc, "call_id", ""),
                    "output": _json.dumps(res, ensure_ascii=False, default=str)[:4000],
                })

            response = client.responses.create(
                model=model,
                reasoning={"effort": "low"},
                include=["reasoning.encrypted_content"],
                max_output_tokens=4000,
                tools=response_tools,
                previous_response_id=getattr(response, "id", None),
                input=next_input,
            )

        raise RuntimeError(f"Planner reasoning przekroczyl limit krokow ({_MAX_STEPS})")

    ctx = build_context(question)
    ctx_str = ""
    if ctx:
        ctx_str = f"\n\nKontekst: {_json.dumps(ctx, ensure_ascii=False, default=str)}"
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM_PROMPT + ctx_str},
        {"role": "user", "content": question},
    ]

    _log.info("Planner %s: model=%s tools=%d q=%s", label, model, len(tools), question[:60])

    for step in range(_MAX_STEPS):
        response = client.chat.completions.create(
            **_oai_create_kwargs(model, messages, tools, "auto")
        )
        msg = response.choices[0].message
        finish = response.choices[0].finish_reason
        answer_text = (msg.content or "").strip()
        tool_calls = msg.tool_calls or []

        if not tool_calls or finish == "stop":
            answer = answer_text or "Brak odpowiedzi od plannera."
            return {
                "status": "OK",
                "answer": answer,
                "intent": "planner_routes",
                "planner": label,
                "steps": step + 1,
                "tool_calls": tool_log,
                "sources_used": tool_log,
            }

        assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content}
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ]
        messages.append(assistant_msg)

        for tc in tool_calls:
            tool_name = tc.function.name
            try:
                args = _json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            spec = tool_map.get(tool_name)
            fn = spec.get("callable") if spec else None
            wrapped = spec.get("wrapped") if spec else None
            try:
                if wrapped and fn:
                    res = fn(wrapped, args)
                elif fn:
                    res = fn(args)
                else:
                    res = {"error": f"Brak callable dla {tool_name}"}
            except Exception as exc:
                res = {"error": str(exc)[:200]}
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": _json.dumps(res, ensure_ascii=False, default=str)[:4000],
            })
            tool_log.append(tool_name)

    try:
        _final = client.chat.completions.create(
            **_oai_create_kwargs(model, messages, tools, "none")
        )
        _ans = (_final.choices[0].message.content or "").strip()
    except Exception as _exc:
        _log.warning("Planner %s force-answer error: %s", label, _exc)
        _ans = ""
    return {
        "status": "OK" if _ans else "no_data",
        "answer": _ans or "Wyczerpano kroki plannera bez finalnej odpowiedzi.",
        "intent": "planner_routes",
        "planner": label,
        "steps": _MAX_STEPS,
        "tool_calls": tool_log,
        "sources_used": tool_log,
        "warnings": ["max_steps_forced_answer"],
    }



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
    import json as _json
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
            answer = " ".join(text_blocks).strip() or "Brak odpowiedzi od Claude."
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
            results_content.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": _json.dumps(res, ensure_ascii=False, default=str)[:4000],
            })
            tool_log.append(block.name)
        messages.append({"role": "user", "content": results_content})

    raise RuntimeError(f"Claude Planner przekroczyl limit krokow ({_MAX_STEPS})")


def _plan_with_albert(question: str, api_key: str, base_url: str, model: str,
                      label: str) -> dict[str, Any]:
    """OpenAI-compatible planner loop for routes, without Albert runtime."""
    return _run_openai_tool_loop(question, api_key, base_url, model, label)


def _plan_routes_gemini_fallback(question: str) -> dict[str, Any]:
    """Fallback: Gemini PRO przez QGPT endpoint (OpenRouter lub Google AI)."""
    try:
        from qbot_config import QGPT_API_KEY, QGPT_BASE_URL, QGPT_MODEL
        key = os.getenv("QBOT_PLANNER_GEMINI_API_KEY") or QGPT_API_KEY or ""
        url = (os.getenv("QBOT_PLANNER_GEMINI_BASE_URL") or QGPT_BASE_URL or "").rstrip("/")
        # Używaj modelu zgodnego z aktywnym OpenAI-compatible endpointem Gemini.
        model = (
            os.getenv("QBOT_PLANNER_GEMINI_MODEL")
            or QGPT_MODEL
            or "gemini-2.5-flash-lite"
        )
    except Exception:
        key, url, model = "", "", "gemini-2.5-flash-lite"

    _log.info("Planner Gemini PRO fallback: model=%s", model)
    return _run_openai_tool_loop(question, key, url, model, "gemini_pro_fallback")


def _try_openai(question: str):
    """Proba OpenAI. Zwraca wynik lub None przy bledzie/braku konfiguracji."""
    key, url, model = _planner_config()
    if not (key and model):
        _log.warning("Planner OpenAI: brak QBOT_PLANNER_API_KEY/MODEL")
        return None
    try:
        result = _run_openai_tool_loop(question, key, url, model, "openai_" + model)
        result["active_provider"] = "openai"
        return result
    except Exception as exc:
        _log.warning("Planner OpenAI error (%s)", exc)
        return None


import re as _re

_API_ROUTE_LINK_RE = _re.compile(
    r"https?://(?:www\.)?ridewithgps\.com/api/v1/routes/(\d+)(?:\.json)?"
)


def _normalize_route_links(result: dict[str, Any]) -> dict[str, Any]:
    """Zamienia linki API RWGPS na uzytkowe: /api/v1/routes/<id>.json -> /routes/<id>."""
    if isinstance(result, dict):
        ans = result.get("answer")
        if isinstance(ans, str):
            result["answer"] = _API_ROUTE_LINK_RE.sub(
                r"https://ridewithgps.com/routes/\1", ans
            )
    return result


_SOURCE_GARMIN_NEG_RE = re.compile(r"\bnie\b[^.,;:!?]{0,20}garmin|bez\s+garmin", re.IGNORECASE)


def _is_ambiguous_source(question: str) -> bool:
    """True gdy pytanie miesza zrodlo Garmin (nie-negowane) i RWGPS jednoczesnie."""
    ql = (question or "").lower()
    has_garmin = "garmin" in ql
    has_rwgps = any(t in ql for t in ("rwgps", "ride with gps", "ridewithgps"))
    if not (has_garmin and has_rwgps):
        return False
    if _SOURCE_GARMIN_NEG_RE.search(ql):
        return False
    return True


def _ambiguous_source_response(question: str) -> dict[str, Any]:
    return {
        "status": "OK",
        "answer": (
            "Pytanie miesza dwa zrodla: Garmin (aktywnosc/przejazd zarejestrowany) "
            "oraz RWGPS (trasa zaplanowana). Doprecyzuj ktore masz na mysli: "
            "(a) ostatnia AKTYWNOSC z Garmina, czy (b) ostatnia TRASA zaplanowana w RWGPS?"
        ),
        "intent": "ambiguous_source",
        "planner": "ambiguous_source_guard",
        "steps": 0,
        "tool_calls": [],
        "sources_used": [],
        "active_provider": "none",
    }


def plan_routes(question: str) -> dict[str, Any]:
    """Wrapper: normalizuje linki RWGPS w odpowiedzi plannera (api/v1 -> uzytkowy)."""
    return _normalize_route_links(_plan_routes_impl(question))


def _plan_routes_impl(question: str) -> dict[str, Any]:
    """Glowna funkcja Plannera.

    Hierarchia wg aktywnego providera:
      claude -> Claude Sonnet -> OpenAI (gpt-4.1-mini) -> Gemini PRO
      openai -> OpenAI -> Gemini PRO
      gemini -> Gemini PRO bezposrednio
    """
    if _is_ambiguous_source(question):
        _log.info("Planner ambiguous_source guard -> clarify q=%s", question[:60])
        return _ambiguous_source_response(question)
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
    return result
