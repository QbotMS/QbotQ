
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
