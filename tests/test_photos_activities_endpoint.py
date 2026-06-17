from __future__ import annotations

import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

import qbot_api
from qbot_api import app


def _fake_api_db_module() -> types.SimpleNamespace:
    return types.SimpleNamespace(init_db=lambda: None, ping=lambda: True)


class _FakeCursor:
    def __init__(self, rows_by_sql: dict[str, list[dict]]):
        self.rows_by_sql = rows_by_sql
        self.executed: list[tuple[str, tuple | None]] = []
        self._rows: list[dict] = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        sql_lower = sql.lower()
        for pattern, rows in self.rows_by_sql.items():
            if pattern in sql_lower:
                self._rows = rows
                break
        else:
            self._rows = []
        return self

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows_by_sql: dict[str, list[dict]]):
        self.cursor_obj = _FakeCursor(rows_by_sql)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        return self.cursor_obj.execute(sql, params)


class _FakePsycopgModule:
    def __init__(self, rows_by_sql: dict[str, list[dict]]):
        self.rows_by_sql = rows_by_sql
        self.connections: list[_FakeConn] = []

    def connect(self, **kwargs):
        conn = _FakeConn(self.rows_by_sql)
        self.connections.append(conn)
        return conn


class TestPhotosActivitiesEndpoint(unittest.TestCase):
    def test_photos_activity_row_payload_prefers_real_end_timestamp(self):
        row = {
            "id": 11,
            "source": "qbot_v2.training_sessions",
            "activity_name": "Evening ride",
            "started_at": datetime(2026, 6, 13, 18, 30, tzinfo=timezone(timedelta(hours=2))),
            "ended_at": datetime(2026, 6, 13, 20, 5, tzinfo=timezone(timedelta(hours=2))),
            "elapsed_duration_sec": 5220,
            "duration_s": 5400,
            "distance_m": 48000.0,
        }

        payload = qbot_api._photos_activity_row_payload(row, "qbot_v2.training_sessions")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["startLocal"], "2026-06-13T18:30:00+02:00")
        self.assertEqual(payload["endLocal"], "2026-06-13T20:05:00+02:00")
        self.assertEqual(payload["durationSec"], 5220)

    def test_photos_activity_row_payload_falls_back_to_duration_when_end_timestamp_missing(self):
        row = {
            "id": 12,
            "source": "qbot_v2.training_sessions",
            "activity_name": "Morning ride",
            "started_at": datetime(2026, 6, 13, 7, 10, tzinfo=timezone(timedelta(hours=2))),
            "elapsed_duration_sec": 4500,
            "duration_s": 5400,
            "distance_m": 32000.0,
        }

        payload = qbot_api._photos_activity_row_payload(row, "qbot_v2.training_sessions")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["startLocal"], "2026-06-13T07:10:00+02:00")
        self.assertEqual(payload["endLocal"], "2026-06-13T08:25:00+02:00")
        self.assertEqual(payload["durationSec"], 4500)

    def test_load_photos_activity_rows_prefers_qbot_v2(self):
        rows_by_sql = {
            "from qbot_v2.training_sessions": [
                {
                    "id": 101,
                    "source": "garmin",
                    "activity_name": "Morning ride",
                    "started_at": datetime(2026, 6, 13, 18, 30, tzinfo=timezone(timedelta(hours=2))),
                    "duration_s": 5400,
                    "distance_m": 92400.0,
                    "external_id": "garmin-101",
                    "date": datetime(2026, 6, 13).date(),
                }
            ],
            "from public.training_sessions": [
                {
                    "id": 202,
                    "source": "garmin",
                    "title": "Fallback ride",
                    "started_at": datetime(2026, 6, 12, 18, 30, tzinfo=timezone(timedelta(hours=2))),
                    "ended_at": datetime(2026, 6, 12, 19, 45, tzinfo=timezone(timedelta(hours=2))),
                    "duration_sec": 4500,
                    "distance_km": 55.0,
                }
            ],
        }

        fake_pg = _FakePsycopgModule(rows_by_sql)
        with patch("psycopg.connect", new=fake_pg.connect):
            rows = qbot_api._load_photos_activity_rows(days=30)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], 101)
        self.assertEqual(rows[0]["_source"], "qbot_v2.training_sessions")
        self.assertEqual(rows[0]["activity_name"], "Morning ride")
        self.assertEqual(rows[0]["distance_m"], 92400.0)
        self.assertEqual(rows[0]["duration_s"], 5400)
        self.assertIn("select *", fake_pg.connections[0].cursor_obj.executed[0][0].lower())

    def test_load_photos_activity_rows_falls_back_to_public(self):
        rows_by_sql = {
            "from qbot_v2.training_sessions": [],
            "from public.training_sessions": [
                {
                    "id": 202,
                    "source": "garmin",
                    "title": "Fallback ride",
                    "started_at": datetime(2026, 6, 12, 18, 30, tzinfo=timezone(timedelta(hours=2))),
                    "duration_sec": 4500,
                    "distance_km": 55.0,
                }
            ],
        }

        with patch("psycopg.connect", new=_FakePsycopgModule(rows_by_sql).connect):
            rows = qbot_api._load_photos_activity_rows(days=30)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], 202)

    def test_photos_activities_endpoint_formats_qbot_v2_rows_and_sorts_newest_first(self):
        rows = [
            {
                "id": 1,
                "source": "qbot_v2.training_sessions",
                "activity_name": "Older ride",
                "started_at": datetime(2026, 6, 12, 8, 15, tzinfo=timezone(timedelta(hours=2))),
                "elapsed_duration_sec": 5400,
                "duration_s": 5400,
                "distance_m": 64200.0,
                "external_id": "older-1",
                "date": datetime(2026, 6, 12).date(),
            },
            {
                "id": 2,
                "source": "qbot_v2.training_sessions",
                "activity_name": "Newer ride",
                "started_at": datetime(2026, 6, 13, 18, 30, tzinfo=timezone(timedelta(hours=2))),
                "ended_at": datetime(2026, 6, 13, 20, 10, tzinfo=timezone(timedelta(hours=2))),
                "duration_s": 4500,
                "distance_m": 72300.0,
                "external_id": "newer-2",
                "date": datetime(2026, 6, 13).date(),
            },
        ]

        with patch.dict(sys.modules, {"api_db": _fake_api_db_module()}), patch(
            "qbot_api._load_photos_activity_rows", return_value=rows
        ):
            client = TestClient(app)
            response = client.get("/photos/activities?days=30")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "activities": [
                    {
                        "id": "2",
                        "source": "qbot_v2.training_sessions",
                        "title": "Newer ride",
                        "startLocal": "2026-06-13T18:30:00+02:00",
                        "endLocal": "2026-06-13T20:10:00+02:00",
                        "distanceKm": 72.3,
                        "durationSec": 4500,
                    },
                    {
                        "id": "1",
                        "source": "qbot_v2.training_sessions",
                        "title": "Older ride",
                        "startLocal": "2026-06-12T08:15:00+02:00",
                        "endLocal": "2026-06-12T09:45:00+02:00",
                        "distanceKm": 64.2,
                        "durationSec": 5400,
                    },
                ]
            },
        )

    def test_photos_activities_endpoint_returns_fallback_when_empty(self):
        with patch.dict(sys.modules, {"api_db": _fake_api_db_module()}), patch(
            "qbot_api._load_photos_activity_rows", return_value=[]
        ):
            client = TestClient(app)
            response = client.get("/photos/activities?days=30")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "activities": [
                    {
                        "id": "manual_2026-05-24_test",
                        "source": "fallback",
                        "title": "Fallback photos activity 2026-05-24",
                        "startLocal": "2026-05-24T00:00:00+02:00",
                        "endLocal": "2026-05-24T23:59:59+02:00",
                        "distanceKm": None,
                        "durationSec": 86399,
                    }
                ]
            },
        )

    def test_photos_activities_endpoint_caps_results_at_100(self):
        base = datetime(2026, 6, 1, 6, 0, tzinfo=timezone(timedelta(hours=2)))
        rows = [
            {
                "id": idx,
                "source": "qbot_v2.training_sessions",
                "title": f"Ride {idx}",
                "started_at": base + timedelta(minutes=idx),
                "duration_s": 3600,
                "distance_km": float(idx),
            }
            for idx in range(101)
        ]

        with patch.dict(sys.modules, {"api_db": _fake_api_db_module()}), patch(
            "qbot_api._load_photos_activity_rows", return_value=rows
        ):
            client = TestClient(app)
            response = client.get("/photos/activities?days=30")

        self.assertEqual(response.status_code, 200)
        activities = response.json()["activities"]
        self.assertEqual(len(activities), 100)
        self.assertEqual(activities[0]["id"], "100")
        self.assertEqual(activities[-1]["id"], "1")
