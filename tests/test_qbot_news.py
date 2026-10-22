import datetime as dt
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
import qbot_news as N  # noqa: E402

RSS = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>x</title>
<item><title>Sejm &amp; Senat: ustawa</title><link>https://a/1</link><guid>g1</guid>
<description>&lt;p&gt;Opis &lt;b&gt;tu&lt;/b&gt;&lt;/p&gt;</description><pubDate>Thu, 22 Oct 2026 12:00:00 +0200</pubDate></item>
<item><title>Bez daty</title><link>https://a/2</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Etna wybucha</title>
<link href="https://b/1"/><id>tag:b,1</id><updated>2026-10-22T10:00:00Z</updated><summary>lawa</summary></entry></feed>"""


class T(unittest.TestCase):
    def test_parse_rss(self):
        it = N.parse_feed(RSS)
        self.assertEqual(len(it), 1)
        self.assertEqual(it[0]["title"], "Sejm & Senat: ustawa")
        self.assertEqual(it[0]["summary"], "Opis tu")
        self.assertEqual(it[0]["guid"], "g1")

    def test_parse_atom(self):
        it = N.parse_feed(ATOM)
        self.assertEqual(it[0]["link"], "https://b/1")
        self.assertEqual(it[0]["published"].tzinfo is not None, True)

    def test_threshold(self):
        self.assertEqual((N.threshold("wysoka"), N.threshold("normalna"), N.threshold("niska")), (3, 4, 5))
        self.assertIsNone(N.threshold("wylaczony"))

    def test_effective_importance(self):
        p = [{"date_from": dt.date(2027, 5, 1), "date_to": dt.date(2027, 5, 14), "importance": "niska"}]
        self.assertEqual(N.effective_importance("normalna", p, dt.date(2027, 5, 3)), "niska")
        self.assertEqual(N.effective_importance("normalna", p, dt.date(2027, 5, 15)), "normalna")

    def test_source_active(self):
        s = {"importance": "wysoka", "active_from": dt.date(2027, 5, 1), "active_to": dt.date(2027, 5, 14)}
        self.assertTrue(N.source_active(s, dt.date(2027, 5, 1)))
        self.assertFalse(N.source_active(s, dt.date(2027, 5, 15)))
        self.assertFalse(N.source_active({"importance": "wylaczony"}, dt.date(2027, 5, 1)))
        self.assertTrue(N.source_active({"importance": "normalna"}, dt.date(2027, 5, 1)))

    def test_trim(self):
        self.assertEqual(N.trim_text("Krótko"), "Krótko")
        t = N.trim_text("Sejm uchwalił nową ustawę o obronie cywilnej kraju")
        self.assertLessEqual(len(t), 32)
        self.assertTrue(t.endswith("…"))

    def test_order(self):
        base = dt.datetime(2026, 10, 22, 12, tzinfo=dt.timezone.utc)
        rows = [{"eff_importance": "niska", "score": 5, "published_at": base},
                {"eff_importance": "wysoka", "score": 3, "published_at": base},
                {"eff_importance": "wysoka", "score": 4, "published_at": base}]
        rows.sort(key=N.order_key)
        self.assertEqual([(r["eff_importance"], r["score"]) for r in rows], [("wysoka", 4), ("wysoka", 3), ("niska", 5)])


if __name__ == "__main__":
    unittest.main()
