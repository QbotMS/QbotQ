"""Testy qbot_webpush (2026-10-13): payloady, klucz VAPID, obsluga wygaslej subskrypcji."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, "/opt/qbot/app")
import qbot_webpush as WP  # noqa: E402


def _it(i, kind="jazda"):
    return {"id": i, "key": f"jazda:{i}", "kind": kind, "title": f"T{i}", "body": f"B{i}", "url": f"/r?{i}"}


class T(unittest.TestCase):
    def test_payloads_single(self):
        p = WP.build_payloads([_it(1)])
        self.assertEqual(len(p), 1)
        self.assertTrue(p[0]["title"].endswith("T1"))
        self.assertEqual(p[0]["tag"], "jazda:1")
        self.assertEqual(p[0]["url"], "/r?1")

    def test_payloads_collapse(self):
        p = WP.build_payloads([_it(i) for i in range(8)])
        self.assertEqual(len(p), WP.MAX_PER_TICK)
        self.assertIn("jeszcze 4", p[-1]["title"])

    def test_public_key_generated(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.dict(os.environ, {"QBOT_VAPID_PEM": os.path.join(d, "k.pem")}):
                k1 = WP.public_key()
                k2 = WP.public_key()
                self.assertEqual(k1, k2)            # klucz trwaly, nie losowany za kazdym razem
                self.assertEqual(len(k1), 87)       # 65 bajtow P-256 w base64url
                self.assertEqual(oct(os.stat(os.path.join(d, "k.pem")).st_mode & 0o777), "0o600")

    def test_gone_subscription(self):
        from pywebpush import WebPushException
        resp = mock.Mock(status_code=410)
        with mock.patch("pywebpush.webpush", side_effect=WebPushException("gone", response=resp)):
            r = WP._send_one({"endpoint": "https://x", "p256dh": "a", "auth": "b"}, {"title": "t"})
        self.assertEqual(r, "gone")

    def test_subscribe_rejects_incomplete(self):
        with self.assertRaises(ValueError):
            WP.subscribe(mock.Mock(), {"endpoint": "http://x", "keys": {}})


if __name__ == "__main__":
    unittest.main()
