"""Dostep demo przez QR (2026-10-07): pelny cykl na prawdziwej bazie, fikcyjny wlasciciel.
Sprzata po sobie (wiersze wlasciciela TEST_OWNER i utworzone zadania)."""
import os
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

import qbot_web  # noqa: E402
import qbot_web_auth as wda  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_OWNER = "__test_wda__"
USERS = {TEST_OWNER: "haslo-testowe"}
SIGN = "test-sign-wda"


def _client():
    return TestClient(qbot_web.app, base_url="https://testserver", follow_redirects=False)


class WebDemoAuthTest(unittest.TestCase):
    def setUp(self):
        self._cfg = mock.patch.object(qbot_web, "_webauth_load", return_value=(dict(USERS), SIGN))
        self._cfg.start()
        wda.clear_demo_cache()
        wda._poll_last.clear()
        self.req_ids = []
        self.owner_ck = qbot_web._webauth_cookie_make(TEST_OWNER, SIGN)[0]

    def tearDown(self):
        self._cfg.stop()
        wda.clear_demo_cache()
        with qbot_web._db_conn() as conn:
            conn.execute("DELETE FROM qbot_v2.web_sessions WHERE owner=%s", (TEST_OWNER,))
            if self.req_ids:
                conn.execute("DELETE FROM qbot_v2.web_device_auth_requests WHERE id = ANY(%s)",
                             (self.req_ids,))

    # --- pomocnicze
    def _start(self, pc):
        r = pc.post("/auth/device/start")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.req_ids.append(d["id"])
        return d

    def _owner(self):
        c = _client()
        c.cookies.set("qbot_session", self.owner_ck)
        return c

    def _approve(self, rid, decision="approve"):
        ph = self._owner()
        page = ph.get("/auth/device/approve", params={"id": rid})
        self.assertEqual(page.status_code, 200, page.text)
        csrf = page.text.split('name="csrf" value="')[1].split('"')[0]
        return ph.post("/auth/device/decide", data={"id": rid, "decision": decision, "csrf": csrf})

    def _wait_poll(self):
        wda._poll_last.clear()

    def _demo_client(self):
        pc = _client()
        d = self._start(pc)
        self.assertEqual(self._approve(d["id"]).status_code, 200)
        r = pc.post("/auth/device/claim")
        self.assertEqual(r.status_code, 200, r.text)
        return pc, d

    # --- przeplyw
    def test_full_flow_and_single_use(self):
        pc = _client()
        d = self._start(pc)
        self.assertRegex(d["code"], r"^[A-Z0-9]{3}-[A-Z0-9]{3}$")
        self.assertEqual(pc.get("/auth/device/status").json()["status"], "PENDING")
        self.assertEqual(pc.post("/auth/device/claim").status_code, 409)   # przed zatwierdzeniem
        self.assertEqual(self._approve(d["id"]).status_code, 200)
        self._wait_poll()
        self.assertEqual(pc.get("/auth/device/status").json()["status"], "APPROVED")
        r = pc.post("/auth/device/claim")
        self.assertEqual(r.status_code, 200)
        sc = r.headers.get("set-cookie", "").lower()
        self.assertIn("qbot_demo=", sc)
        self.assertIn("secure", sc)
        self.assertIn("httponly", sc)
        self.assertEqual(pc.post("/auth/device/claim").status_code, 401)  # ciasteczko zadania usuniete
        self.assertEqual(pc.get("/auth/demo/whoami").json()["kind"], "demo")

    def test_qr_id_alone_cannot_claim(self):
        pc = _client()
        d = self._start(pc)
        self._approve(d["id"])
        thief = _client()
        self.assertEqual(thief.post("/auth/device/claim").status_code, 401)
        thief.cookies.set(wda.REQ_COOKIE, d["id"] + ".zgadniety-sekret", path="/auth/device")
        self.assertEqual(thief.post("/auth/device/claim").status_code, 409)
        self.assertEqual(pc.post("/auth/device/claim").status_code, 200)

    def test_concurrent_claim_creates_one_session(self):
        pc = _client()
        d = self._start(pc)
        self._approve(d["id"])
        ck = pc.cookies.get(wda.REQ_COOKIE)
        codes = []

        def go():
            c = _client()
            c.cookies.set(wda.REQ_COOKIE, ck, path="/auth/device")
            codes.append(c.post("/auth/device/claim").status_code)

        ts = [threading.Thread(target=go) for _ in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sorted(codes), [200, 409, 409, 409])
        with qbot_web._db_conn() as conn:
            n = conn.execute("SELECT count(*) AS n FROM qbot_v2.web_sessions WHERE request_id=%s",
                             (d["id"],)).fetchone()["n"]
        self.assertEqual(n, 1)

    def test_denied_and_expired_cannot_claim(self):
        pc = _client()
        d = self._start(pc)
        self.assertEqual(self._approve(d["id"], "deny").status_code, 200)
        self.assertEqual(pc.post("/auth/device/claim").status_code, 409)
        pc2 = _client()
        d2 = self._start(pc2)
        with qbot_web._db_conn() as conn:
            conn.execute("UPDATE qbot_v2.web_device_auth_requests SET expires_at=now()-interval '1 second' "
                         "WHERE id=%s", (d2["id"],))
        self.assertEqual(pc2.get("/auth/device/status").json()["status"], "EXPIRED")
        self.assertEqual(self._owner().get("/auth/device/approve", params={"id": d2["id"]}).status_code, 410)
        self.assertEqual(pc2.post("/auth/device/claim").status_code, 409)

    def test_approve_requires_owner_and_csrf(self):
        pc = _client()
        d = self._start(pc)
        anon = _client()
        r = anon.get("/auth/device/approve", params={"id": d["id"]})
        self.assertEqual(r.status_code, 303)
        self.assertIn("/login", r.headers["location"])
        r = self._owner().post("/auth/device/decide", data={"id": d["id"], "decision": "approve", "csrf": "x"})
        self.assertEqual(r.status_code, 403)
        self._wait_poll()
        self.assertEqual(pc.get("/auth/device/status").json()["status"], "PENDING")

    # --- polityka demo
    def test_demo_read_only_policy(self):
        pc, _ = self._demo_client()
        self.assertEqual(pc.get("/api/config/map").status_code, 200)            # dozwolony odczyt
        self.assertEqual(pc.post("/api/garage/delete", json={"id": 1, "confirm": True}).status_code, 403)
        self.assertEqual(pc.post("/api/prefs", json={}).status_code, 403)
        self.assertEqual(pc.get("/api/invites").status_code, 403)               # linki-przepustki
        self.assertEqual(pc.get("/api/report/mail-recipients").status_code, 403)  # dane innych
        self.assertEqual(pc.get("/api/noclegi").status_code, 403)               # platne Google
        self.assertEqual(pc.get("/api/ride-report/w2", params={"rebuild": 1}).status_code, 403)
        self.assertEqual(pc.get("/api/nowy-niezgloszony-endpoint").status_code, 403)  # domyslnie zakaz
        self.assertEqual(pc.get("/komoot-dostep").status_code, 403)
        self.assertEqual(pc.get("/openapi.json").status_code, 403)

    def test_start_returns_qr_for_public_url(self):
        d = self._start(_client())
        r = _client().post("/auth/device/start")
        self.req_ids.append(r.json()["id"])
        svg = r.json()["qr_svg"]
        self.assertTrue(svg and svg.lstrip().startswith(("<svg", "<?xml")), svg[:80] if svg else svg)
        self.assertTrue(d["approve_path"].startswith("/auth/device/approve?id="))

    def test_login_page_has_qr_button(self):
        r = _client().get("/login")
        self.assertIn('id="qrgo"', r.text)
        self.assertIn("/auth/device/start", r.text)

    def test_sessions_page_owner_only(self):
        self.assertEqual(_client().get("/auth/sessions").status_code, 303)
        r = self._owner().get("/auth/sessions")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/api/auth/sessions", r.text)
        pc, _ = self._demo_client()
        self.assertEqual(pc.get("/auth/sessions").status_code, 403)

    def test_demo_static_policy(self):
        self.assertTrue(wda.demo_allows("GET", "/forma.html"))
        self.assertTrue(wda.demo_allows("GET", "/vendor/leaflet.js"))
        self.assertFalse(wda.demo_allows("GET", "/raport-render.js.bak.20261007_074519"))
        self.assertFalse(wda.demo_allows("GET", "/_dev_write_probe.txt"))
        self.assertFalse(wda.demo_allows("GET", "/reports/_tmp/x.json"))
        self.assertFalse(wda.demo_allows("GET", "/strava.html"))

    def test_demo_cannot_approve_other_devices_or_manage_sessions(self):
        pc, _ = self._demo_client()
        other = _client()
        d2 = self._start(other)
        self.assertEqual(pc.get("/auth/device/approve", params={"id": d2["id"]}).status_code, 403)
        self.assertEqual(pc.post("/auth/device/decide",
                                 data={"id": d2["id"], "decision": "approve", "csrf": "x"}).status_code, 403)
        self.assertEqual(pc.get("/api/auth/sessions").status_code, 403)
        self.assertEqual(pc.post("/api/auth/sessions/revoke", json={"id": "all"}).status_code, 403)

    def test_logout_blocks_further_requests(self):
        pc, _ = self._demo_client()
        self.assertEqual(pc.post("/auth/demo/logout").status_code, 200)
        self.assertEqual(pc.get("/api/config/map").status_code, 401)

    def test_owner_revoke_and_expiry(self):
        pc, _ = self._demo_client()
        own = self._owner()
        lst = own.get("/api/auth/sessions").json()
        self.assertEqual(len(lst["sessions"]), 1)
        r = own.post("/api/auth/sessions/revoke", json={"id": lst["sessions"][0]["id"], "csrf": "zly"})
        self.assertEqual(r.status_code, 403)
        r = own.post("/api/auth/sessions/revoke", json={"id": lst["sessions"][0]["id"], "csrf": lst["csrf"]})
        self.assertEqual(r.json()["revoked"], 1)
        self.assertEqual(pc.get("/api/config/map").status_code, 401)
        pc2, _ = self._demo_client()
        with qbot_web._db_conn() as conn:
            conn.execute("UPDATE qbot_v2.web_sessions SET expires_at=now()-interval '1 second' "
                         "WHERE owner=%s AND revoked_at IS NULL", (TEST_OWNER,))
        wda.clear_demo_cache()
        self.assertEqual(pc2.get("/api/config/map").status_code, 401)

    def test_demo_dies_when_owner_removed_or_db_down(self):
        pc, _ = self._demo_client()
        with mock.patch.object(qbot_web, "_webauth_load", return_value=({"inny": "x"}, SIGN)):
            self.assertEqual(pc.get("/api/config/map").status_code, 401)
        wda.clear_demo_cache()

        def boom():
            raise RuntimeError("db down")
        with mock.patch.dict(wda._deps, {"db": boom}):
            self.assertEqual(pc.get("/api/config/map").status_code, 401)

    def test_current_user_maps_demo_to_owner_only_via_gate(self):
        req = mock.Mock()
        req.cookies = {}
        req.scope = {"qbot_auth": {"kind": "demo", "owner": TEST_OWNER}}
        self.assertEqual(qbot_web._current_user(req), TEST_OWNER)
        self.assertIsNone(qbot_web._owner_user(req))
        req.scope = {}
        self.assertIsNone(qbot_web._current_user(req))


if __name__ == "__main__":
    unittest.main()
