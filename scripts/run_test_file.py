#!/usr/bin/env python3
"""Uruchamia testy z jednego pliku bez pytesta: funkcje test_* oraz klasy unittest.TestCase.
  .venv/bin/python3 scripts/run_test_file.py tests/test_route_attraction_engine.py"""
import importlib.util
import sys
import traceback
import unittest

sys.path.insert(0, "/opt/qbot/app")
sys.path.insert(0, "/opt/qbot/app/tests")
path = sys.argv[1]
spec = importlib.util.spec_from_file_location("t", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ok = fail = 0
for name in sorted(n for n in dir(mod) if n.startswith("test_")):
    obj = getattr(mod, name)
    if not callable(obj) or isinstance(obj, type):
        continue
    try:
        obj()
        ok += 1
    except Exception:
        fail += 1
        print("FAIL", name)
        traceback.print_exc()
suite = unittest.defaultTestLoader.loadTestsFromModule(mod)
if suite.countTestCases():
    res = unittest.TextTestRunner(stream=sys.stdout, verbosity=0).run(suite)
    ok += res.testsRun - len(res.failures) - len(res.errors)
    fail += len(res.failures) + len(res.errors)
print(f"OK {ok}, FAIL {fail}")
sys.exit(1 if fail else 0)
