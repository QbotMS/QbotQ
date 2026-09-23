"""Testy przegladu baz tylko do odczytu (qbot_ro + garage.db) i narzedzi publicznego MCP.

Uruchom: QBOT3_ENABLED=1 .venv/bin/python3 -m unittest tests.test_db_readonly -v
Wymaga zywej bazy (konto qbot_ro, dane w .env.local).
"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from qbot3 import db_introspection as d  # noqa: E402
from qbot3 import garage_readonly as g  # noqa: E402


class TestPostgresReadOnly(unittest.TestCase):
    def test_connects_as_ro_role(self):
        with d._db() as conn:
            row = conn.execute("SELECT current_user AS u, current_setting('transaction_read_only') AS ro").fetchone()
        self.assertEqual(row["u"], "qbot_ro")
        self.assertEqual(row["ro"], "on")

    def test_database_itself_rejects_write(self):
        # z pominieciem filtra tekstu — musi odrzucic sama baza
        with d._db() as conn:
            with self.assertRaises(Exception) as ctx:
                conn.execute("INSERT INTO qbot_v2.calendar_entry (id) VALUES (-1)")
            conn.rollback()
        msg = str(ctx.exception).lower()
        self.assertTrue("read-only" in msg or "permission denied" in msg, msg)

    def test_database_rejects_write_even_with_rw_transaction(self):
        with d._db() as conn:
            with self.assertRaises(Exception):
                conn.execute("SET TRANSACTION READ WRITE")
                conn.execute("DELETE FROM qbot_v2.calendar_entry WHERE id = -1")
            conn.rollback()

    def test_filter_blocks_write(self):
        self.assertEqual(d.db_select_readonly({"sql": "DELETE FROM qbot_v2.calendar_entry"})["status"], "BLOCKED")
        self.assertEqual(d.db_select_readonly({"sql": "SELECT 1; DROP TABLE x"})["status"], "BLOCKED")

    def test_with_allowed(self):
        r = d.db_select_readonly({"sql": "WITH x AS (SELECT 1 AS n) SELECT n FROM x"})
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["rows"][0]["n"], 1)

    def test_row_cap(self):
        r = d.db_select_readonly({"sql": "SELECT generate_series(1, 1000) AS n"})
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["row_count"], 200)
        self.assertTrue(r["truncated"])

    def test_timeout(self):
        r = d.db_select_readonly({"sql": "SELECT pg_sleep(7)"})
        self.assertEqual(r["status"], "TIMEOUT")

    def test_token_column_hidden(self):
        r = d.db_select_readonly({"sql": "SELECT token FROM qbot_v2.ride_invite LIMIT 1"})
        self.assertNotEqual(r["status"], "OK")

    def test_wellness_visible(self):
        r = d.db_select_readonly({"sql": "SELECT count(*) AS n FROM qbot_v2.body_measurements"})
        self.assertEqual(r["status"], "OK")

    def test_schema_list(self):
        r = d.db_schema_list()
        self.assertEqual(r["status"], "OK")
        self.assertIn("qbot_v2", r["schemas"])


class TestGarageReadOnly(unittest.TestCase):
    def test_tables(self):
        r = g.garage_tables()
        self.assertEqual(r["status"], "OK")
        names = {t["table"] for t in r["tables"]}
        self.assertTrue({"bikes", "components", "gear"} <= names)

    def test_select_bikes(self):
        r = g.garage_select({"sql": "SELECT id, name FROM bikes WHERE active=1"})
        self.assertEqual(r["status"], "OK")
        self.assertGreaterEqual(r["row_count"], 1)

    def test_filter_blocks_write(self):
        self.assertEqual(g.garage_select({"sql": "UPDATE bikes SET name='x'"})["status"], "BLOCKED")

    def test_file_itself_is_read_only(self):
        # z pominieciem filtra — plik otwarty w mode=ro + query_only
        c = g._conn()
        try:
            with self.assertRaises(sqlite3.Error):
                c.execute("UPDATE bikes SET name = name WHERE id = -1")
        finally:
            c.close()

    def test_timeout(self):
        r = g.garage_select({"sql": "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT count(*) FROM c"})
        self.assertEqual(r["status"], "TIMEOUT")


class TestPublicMcpTools(unittest.TestCase):
    def setUp(self):
        from qbot3.adapters.mcp_adapter import handle_qbot3_mcp
        self.h = handle_qbot3_mcp

    def test_tools_listed(self):
        r = self.h({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {t["name"] for t in r["result"]["tools"]}
        for n in ("qbot_query", "qbot_db_schema_list", "qbot_db_table_describe", "qbot_db_select",
                  "qbot_garage_tables", "qbot_garage_select"):
            self.assertIn(n, names)

    def test_call_select(self):
        r = self.h({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "qbot_db_select", "arguments": {"sql": "SELECT 1 AS n"}}})
        self.assertEqual(r["result"]["structuredContent"]["status"], "OK")

    def test_call_describe_defaults_to_qbot_v2(self):
        r = self.h({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "qbot_db_table_describe", "arguments": {"table": "fitmodel_daily"}}})
        sc = r["result"]["structuredContent"]
        self.assertEqual(sc["schema"], "qbot_v2")
        self.assertGreater(sc["column_count"], 0)

    def test_call_garage(self):
        r = self.h({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                    "params": {"name": "qbot_garage_select", "arguments": {"sql": "SELECT count(*) AS n FROM gear"}}})
        self.assertEqual(r["result"]["structuredContent"]["status"], "OK")

    def test_dotted_legacy_name(self):
        r = self.h({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                    "params": {"name": "qbot.garage_tables", "arguments": {}}})
        self.assertEqual(r["result"]["structuredContent"]["status"], "OK")


if __name__ == "__main__":
    unittest.main()
