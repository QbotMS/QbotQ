"""Utwardzenie logowania qbot-web (2026-10-07): fail-closed bramki, bezpieczny next,
Secure na ciasteczku, limit nieudanych prob. Bez prawdziwej konfiguracji (_webauth_load podmieniony)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

import qbot_web  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

USERS = {"tester": "haslo-ż-1"}
SIGN = "test-sign-value"


class WebauthHardeningTest(unittest.TestCase):
    def setUp(self):
        qbot_web._login_failures.clear()
        self._delay = mock.patch.object(qbot_web, "_LOGIN_FAIL_DELAY_S", 0)
        self._delay.start()
        self.client = TestClient(qbot_web.app, base_url="https://testserver", follow_redirects=False)

    def tearDown(self):
        self._delay.stop()
        qbot_web._login_failures.clear()

    def _cfg(self, users=USERS, sign=SIGN):
        return mock.patch.object(qbot_web, "_webauth_load", return_value=(dict(users), sign))

    def _post(self, username, password, nxt="/"):
        return self.client.post("/login", data={"username": username, "password": password, "next": nxt})

    # 1) fail-closed
    def test_guard_denies_when_config_missing(self):
        with self._cfg(users={}, sign=""):
            r = self.client.get("/api/routes/ready")
        self.assertEqual(r.status_code, 503)

    def test_guard_denies_when_sign_missing(self):
        with self._cfg(sign=""):
            r = self.client.get("/forma.html")
        self.assertEqual(r.status_code, 503)

    def test_guard_still_requires_cookie_with_config(self):
        with self._cfg():
            r = self.client.get("/api/routes/ready")
        self.assertEqual(r.status_code, 401)

    # 2) next
    def test_safe_next_cases(self):
        f = qbot_web._webauth_safe_next
        self.assertEqual(f("/forma.html?x=1"), "/forma.html?x=1")
        for bad in ["//evil.com", "/\\evil.com", "https://evil.com", "evil", "", "/\t/evil.com",
                    "/a\nb", None]:
            self.assertEqual(f(bad), "/", repr(bad))

    def test_login_form_escapes_next(self):
        with self._cfg():
            r = self.client.get("/login", params={"next": '/x"><script>alert(1)</script>'})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("<script>alert", r.text)
        self.assertIn("&quot;&gt;&lt;script&gt;", r.text)

    def test_login_form_rejects_external_next(self):
        with self._cfg():
            r = self.client.get("/login", params={"next": "//evil.com"})
        self.assertIn('name="next" value="/"', r.text)

    def test_login_redirect_never_external(self):
        with self._cfg():
            r = self._post("tester", USERS["tester"], nxt="//evil.com")
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/")

    # 3) Secure + udane logowanie
    def test_login_success_sets_secure_cookie(self):
        with self._cfg():
            r = self._post("tester", USERS["tester"], nxt="/forma.html")
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/forma.html")
        sc = r.headers["set-cookie"].lower()
        self.assertIn("qbot_session=", sc)
        self.assertIn("secure", sc)
        self.assertIn("httponly", sc)
        self.assertIn("samesite=lax", sc)

    def test_non_ascii_wrong_password_no_500(self):
        with self._cfg():
            r = self._post("tester", "złe-hasło")
        self.assertEqual(r.status_code, 303)
        self.assertIn("err=1", r.headers["location"])

    # 4) limit prob
    def test_lockout_after_max_failures(self):
        with self._cfg():
            for _ in range(qbot_web._LOGIN_FAIL_MAX):
                r = self._post("tester", "zle")
                self.assertIn("err=1", r.headers["location"])
            r = self._post("tester", USERS["tester"])
        self.assertIn("err=2", r.headers["location"])
        self.assertNotIn("set-cookie", r.headers)

    def test_unknown_usernames_do_not_lock_real_user(self):
        with self._cfg():
            for i in range(qbot_web._LOGIN_FAIL_MAX + 3):
                self._post("obcy%d" % i, "zle")
            r = self._post("tester", USERS["tester"])
        self.assertEqual(r.headers["location"], "/")
        self.assertIn("qbot_session=", r.headers.get("set-cookie", ""))

    def test_lock_expires_after_window(self):
        with self._cfg():
            for _ in range(qbot_web._LOGIN_FAIL_MAX):
                self._post("tester", "zle")
        later = __import__("time").time() + qbot_web._LOGIN_FAIL_WINDOW_S + 1
        self.assertFalse(qbot_web._login_locked("tester", USERS, now=later))

    def test_success_clears_failures(self):
        with self._cfg():
            for _ in range(qbot_web._LOGIN_FAIL_MAX - 1):
                self._post("tester", "zle")
            self._post("tester", USERS["tester"])
            self.assertFalse(qbot_web._login_locked("tester", USERS))
            r = self._post("tester", "zle")
        self.assertIn("err=1", r.headers["location"])


if __name__ == "__main__":
    unittest.main()
