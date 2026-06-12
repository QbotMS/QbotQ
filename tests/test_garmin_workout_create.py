from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import qbot_mcp_adapter
from qbot_garmin_workouts import build_workout_dto, execute_garmin_workout_create
from qbot3.safety import _ACTION_ALLOWLIST
from qbot3.tool_registry import list_write_tools


def test_build_workout_dto_from_simplified_payload() -> None:
    dto = build_workout_dto(
        {
            "name": "Joga test",
            "sport": "yoga",
            "steps": [
                {"category": "POSE", "exerciseName": "CAT", "seconds": 120, "description": "opis"},
                {"category": "POSE", "exerciseName": "MOUNTAIN", "seconds": 60},
            ],
        }
    )

    assert dto["workoutName"] == "Joga test"
    assert dto["sportType"]["sportTypeKey"] == "yoga"
    assert dto["estimatedDurationInSecs"] == 180
    assert len(dto["workoutSegments"]) == 1
    assert len(dto["workoutSegments"][0]["workoutSteps"]) == 2


def test_dry_run_builds_dto_without_upload(monkeypatch) -> None:
    def boom(*_args, **_kwargs):  # pragma: no cover - defensive
        raise AssertionError("garmin_client must not be called on dry-run")

    monkeypatch.setattr("qbot_garmin_workouts.garmin_client", boom)

    result = execute_garmin_workout_create(
        {
            "name": "Joga test",
            "sport": "yoga",
            "steps": [{"category": "POSE", "exerciseName": "CAT", "seconds": 120}],
        },
        idempotency_key="garmin-test-dry-run",
        confirm=True,
        dry_run=True,
        source="pytest",
    )

    assert result["status"] == "DRY_RUN_OK"
    assert result["workoutName"] == "Joga test"
    assert result["workoutId"] is None
    assert result["verified"] is False
    assert result["payload"]["workoutSegments"][0]["workoutSteps"][0]["exerciseName"] == "CAT"


def test_execute_real_run_uses_upload_and_verifies(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def fake_audit_record(**kwargs):
        calls.append((kwargs["status"], kwargs))

    fake_client = SimpleNamespace(
        upload_workout=lambda dto: {"workoutId": 123456789, "workoutName": dto["workoutName"]},
        get_workout_by_id=lambda wid: {"workoutId": wid, "workoutName": "Joga test"},
    )

    monkeypatch.setattr("qbot_garmin_workouts.audit_lookup", lambda _idem: None)
    monkeypatch.setattr("qbot_garmin_workouts.audit_record", fake_audit_record)
    monkeypatch.setattr("qbot_garmin_workouts.garmin_client", lambda: fake_client)

    result = execute_garmin_workout_create(
        {
            "name": "Joga test",
            "sport": "yoga",
            "steps": [{"category": "POSE", "exerciseName": "CAT", "seconds": 120}],
        },
        idempotency_key="garmin-test-real",
        confirm=True,
        dry_run=False,
        source="pytest",
    )

    assert result["status"] == "success"
    assert result["workoutId"] == "123456789"
    assert result["verified"] is True
    assert [status for status, _ in calls] == ["PENDING", "SUCCESS"]


def test_allowlists_include_garmin_workout_create() -> None:
    assert "garmin_workout_create" in qbot_mcp_adapter._ACTION_EXECUTE_ALLOWLIST
    assert "garmin_workout_create" in _ACTION_ALLOWLIST
    assert "garmin_workout_create" in list_write_tools()
