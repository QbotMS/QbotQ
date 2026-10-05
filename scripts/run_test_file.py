#!/usr/bin/env python3
"""Uruchamia funkcje test_* z jednego pliku testow (pytest-style) bez pytesta.
  .venv/bin/python3 scripts/run_test_file.py tests/test_route_attraction_engine.py"""
import importlib.util
import sys
import traceback

sys.path.insert(0, "/opt/qbot/app")
path = sys.argv[1]
spec = importlib.util.spec_from_file_location("t", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ok = fail = 0
for name in sorted(n for n in dir(mod) if n.startswith("test_")):
    try:
        getattr(mod, name)()
        ok += 1
    except Exception:
        fail += 1
        print("FAIL", name)
        traceback.print_exc()
print(f"OK {ok}, FAIL {fail}")
sys.exit(1 if fail else 0)
