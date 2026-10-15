"""Bezpiecznik (15.10.2026): funkcje czasu lokalnego qTsLocal/qDateLocal sa skopiowane w kilkunastu plikach stron
(swiadoma decyzja: jedna linijka, wspolny plik = przerobka wielu stron). Kopie MUSZA byc identyczne -- inaczej daty
na roznych stronach zaczna sie rozjezdzac. Zmieniasz jedna kopie -> zmien wszystkie."""
import os
import re
import unittest

PUB = "/opt/qbot/web/public"
RX = re.compile(r"function qTsLocal\(.*?function qDateLocal\(d\)\{.*?\}", re.S)


class QDateCopiesIdentical(unittest.TestCase):
    def test_copies_identical(self):
        found = {}
        for fn in sorted(os.listdir(PUB)):
            if not fn.endswith((".js", ".html")) or ".bak" in fn:
                continue
            with open(os.path.join(PUB, fn), encoding="utf-8", errors="ignore") as f:
                m = RX.search(f.read())
            if m:
                found.setdefault(m.group(0), []).append(fn)
        self.assertGreaterEqual(sum(len(v) for v in found.values()), 1, "nie znaleziono zadnej kopii")
        self.assertEqual(len(found), 1, "rozne wersje qTsLocal/qDateLocal: %s" % [v for v in found.values()])


if __name__ == "__main__":
    unittest.main()
