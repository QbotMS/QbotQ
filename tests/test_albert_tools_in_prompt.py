"""Bezpiecznik (15.10.2026) -- twarda regula projektu z CONTEXT.md: kazde narzedzie Alberta (qbot3/tool_registry.py) MUSI byc
opisane w jego instrukcji (_SYSTEM w qbot3/llm/albert.py), a opis narzedzia ma < 500 znakow (build_tools_spec obcina).
Bez wzmianki w instrukcji Albert nie wie, kiedy po narzedzie siegnac. Stan przed bezpiecznikiem: 29 narzedzi bez wzmianki, 4 opisy obcinane."""
import os
import re
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")


class AlbertToolsInPrompt(unittest.TestCase):
    def setUp(self):
        from qbot3.tool_registry import tool_descriptions
        self.tools = [t for t in tool_descriptions() if t.get("status") != "error"]
        with open("/opt/qbot/app/qbot3/llm/albert.py", encoding="utf-8") as f:
            self.prompt = f.read()

    def test_every_tool_mentioned(self):
        missing = sorted({t["name"] for t in self.tools if not re.search(r"\b" + re.escape(t["name"]) + r"\b", self.prompt)})
        self.assertEqual(missing, [], "narzedzia bez wzmianki w instrukcji Alberta: %s" % missing)

    def test_descriptions_short(self):
        long_ = sorted(t["name"] for t in self.tools if len(t.get("description") or "") >= 500)
        self.assertEqual(long_, [], "opisy >= 500 znakow (zostana obciete): %s" % long_)


if __name__ == "__main__":
    unittest.main()
