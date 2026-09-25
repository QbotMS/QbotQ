"""Straznik strefy czasowej: to, co widzi uzytkownik, ma byc w czasie polskim."""
import os
import re
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
import qbot_time as QT  # noqa: E402

PUB = "/opt/qbot/web/public"
APP = "/opt/qbot/app"
SKIP_DIRS = {".venv", "archive", "_bak_archive", ".ms-playwright", ".git", "node_modules", "tests",
             "vendor", "data", "__pycache__", "gear"}
# trener.js liczy dni na znacznikach Date.UTC (celowo, spojnie w calym pliku)
JS_ALLOW = {"trener.js"}


def _files(root, exts):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if not fn.endswith(exts) or ".bak" in fn or "-old" in fn or "mock" in fn or fn.startswith("_tmp_"):
                continue
            yield os.path.join(dp, fn)


def _lines(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read().split("\n")


class TestQbotTime(unittest.TestCase):
    def test_to_local(self):
        self.assertEqual(QT.fmt_local("2026-09-25T12:00:00Z"), "2026-09-25 14:00")
        self.assertEqual(QT.fmt_local("2026-01-10 11:00:00"), "2026-01-10 12:00")  # naiwny = UTC, zima +1
        self.assertTrue(QT.iso_local().endswith(("+02:00", "+01:00")))


class TestNoUtcForUser(unittest.TestCase):
    def test_js_no_utc_today_or_label(self):
        bad = []
        rx_today = re.compile(r"toISOString\(\)\.slice\(0,\s*10\)")
        rx_label = re.compile(r"\+\s*' UTC")
        for p in _files(PUB, (".js", ".html")):
            if os.path.basename(p) in JS_ALLOW:
                continue
            for i, ln in enumerate(_lines(p), 1):
                if rx_today.search(ln) or rx_label.search(ln):
                    bad.append("%s:%d" % (os.path.basename(p), i))
        self.assertEqual(bad, [], "czas/data w UTC na stronie -- uzyj qDateLocal()/qTsLocal(): %s" % bad)

    def test_py_no_utc_today(self):
        bad = []
        rx = re.compile(r"now\((?:tz=)?(?:_?dt\.)?(?:timezone\.utc|UTC)\)(?:\s*\+\s*timedelta\([^)]*\))?\)?\s*\.(?:date\(\)|strftime\(\"%Y-%m-%d\"\))")
        for p in _files(APP, (".py",)):
            if "/scripts/" in p:
                continue
            for i, ln in enumerate(_lines(p), 1):
                if rx.search(ln):
                    bad.append("%s:%d" % (p.replace(APP + "/", ""), i))
        self.assertEqual(bad, [], "'dzisiaj' liczone w UTC -- uzyj qbot_time.today_local(): %s" % bad)


if __name__ == "__main__":
    unittest.main()
