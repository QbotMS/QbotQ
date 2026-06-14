#!/usr/bin/env python3
"""Patch analytical fallback — tymczasowo ustaw QGPT env na Gemini przed wywołaniem Alberta."""
import ast

lines = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').readlines()

old = (
    '    if _is_analytical and intent not in _ANALYTICAL_INTENTS_EXEMPT and _albert_enabled:\n'
    '        try:\n'
    '            from qbot3.agent_runtime import orchestrate_query\n'
    '            _albert_result = orchestrate_query(question=question)\n'
    '            _albert_result["fallback_reason"] = f"analytical_fallback (intent={intent})"\n'
    '            return _albert_result\n'
    '        except Exception as _exc:\n'
    '            # Albert niedostępny — kontynuuj deterministycznie\n'
    '            pass\n'
)
new = (
    '    if _is_analytical and intent not in _ANALYTICAL_INTENTS_EXEMPT and _albert_enabled:\n'
    '        try:\n'
    '            import os as _os\n'
    '            # Użyj Gemini dla analytical queries (OpenRouter free nie obsługuje tool-calling)\n'
    '            _an_url = _os.getenv("QGPT_ANALYTICAL_BASE_URL")\n'
    '            _an_key = _os.getenv("QGPT_ANALYTICAL_API_KEY")\n'
    '            _an_model = _os.getenv("QGPT_ANALYTICAL_MODEL")\n'
    '            _orig = {}\n'
    '            if _an_url and _an_key and _an_model:\n'
    '                for _k, _v in [("QGPT_BASE_URL", _an_url), ("QGPT_API_KEY", _an_key),\n'
    '                               ("QGPT_MODEL", _an_model), ("ALBERT_LLM_PROVIDER", "openai")]:\n'
    '                    _orig[_k] = _os.environ.get(_k)\n'
    '                    _os.environ[_k] = _v\n'
    '            try:\n'
    '                from qbot3.agent_runtime import orchestrate_query\n'
    '                _albert_result = orchestrate_query(question=question)\n'
    '                _albert_result["fallback_reason"] = f"analytical_fallback (intent={intent})"\n'
    '                return _albert_result\n'
    '            finally:\n'
    '                for _k, _v in _orig.items():\n'
    '                    if _v is None:\n'
    '                        _os.environ.pop(_k, None)\n'
    '                    else:\n'
    '                        _os.environ[_k] = _v\n'
    '        except Exception as _exc:\n'
    '            # Albert niedostępny — kontynuuj deterministycznie\n'
    '            pass\n'
)

content = ''.join(lines)
if old in content:
    content = content.replace(old, new, 1)
    ast.parse(content)
    open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
    print("OK: analytical fallback uses Gemini env vars")
else:
    print("FAIL: block not found")
