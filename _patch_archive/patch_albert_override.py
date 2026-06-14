#!/usr/bin/env python3
"""Dodaj opcjonalne api_key/base_url/model do albert.run() i orchestrate_query()."""
import ast, shutil, datetime

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

# ── Patch albert.py ───────────────────────────────────────────────────
AL = '/opt/qbot/app/qbot3/llm/albert.py'
with open(AL, encoding='utf-8') as f:
    al = f.read()
shutil.copy(AL, f'{AL}.bak.{ts}')

old_run_def = 'def run(question: str, tools_spec: list[dict], execute_tool_fn, context: dict) -> dict[str, Any]:'
new_run_def = 'def run(question: str, tools_spec: list[dict], execute_tool_fn, context: dict,\n        override_api_key: str = "", override_base_url: str = "", override_model: str = "") -> dict[str, Any]:'

old_client = '    client = openai.OpenAI(api_key=_API_KEY, base_url=_BASE_URL)'
new_client = (
    '    _eff_key = override_api_key or _API_KEY\n'
    '    _eff_url = override_base_url or _BASE_URL\n'
    '    _eff_model = override_model or _MODEL\n'
    '    client = openai.OpenAI(api_key=_eff_key, base_url=_eff_url)'
)

# Zamień też _MODEL na _eff_model w pętli (pierwsze użycie w chat.completions.create)
old_model_usage = '"model": _MODEL,'
new_model_usage = '"model": _eff_model,'

if old_run_def in al and old_client in al:
    al = al.replace(old_run_def, new_run_def, 1)
    al = al.replace(old_client, new_client, 1)
    al = al.replace(old_model_usage, new_model_usage)
    ast.parse(al)
    with open(AL, 'w', encoding='utf-8') as f:
        f.write(al)
    print("OK: albert.run() accepts override params")
else:
    print("FAIL albert.py:", old_run_def in al, old_client in al)

# ── Patch agent_runtime.py — build_tools_spec i albert_run call ──────
AR = '/opt/qbot/app/qbot3/agent_runtime.py'
with open(AR, encoding='utf-8') as f:
    ar = f.read()
shutil.copy(AR, f'{AR}.bak.{ts}')

old_albert_run = (
    '    albert_result = albert_run(\n'
    '        question=question,\n'
    '        tools_spec=tools_spec,\n'
    '        execute_tool_fn=_execute_single_tool,\n'
    '        context=ctx,\n'
    '    )'
)
new_albert_run = (
    '    albert_result = albert_run(\n'
    '        question=question,\n'
    '        tools_spec=tools_spec,\n'
    '        execute_tool_fn=_execute_single_tool,\n'
    '        context=ctx,\n'
    '        override_api_key=os.getenv("QGPT_ANALYTICAL_API_KEY", ""),\n'
    '        override_base_url=os.getenv("QGPT_ANALYTICAL_BASE_URL", ""),\n'
    '        override_model=os.getenv("QGPT_ANALYTICAL_MODEL", ""),\n'
    '    )'
)
if old_albert_run in ar:
    ar = ar.replace(old_albert_run, new_albert_run, 1)
    ast.parse(ar)
    with open(AR, 'w', encoding='utf-8') as f:
        f.write(ar)
    print("OK: orchestrate_query passes override params to albert_run")
else:
    print("FAIL agent_runtime: block not found")
    idx = ar.find('albert_run(')
    print("context:", repr(ar[idx:idx+200]))
