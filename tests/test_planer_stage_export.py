import inspect
from pathlib import Path

import pytest

from qbot3.routes import planer_stage_export as export


class _FakeResult:
    def __init__(self, rows=None, rowcount=0):
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeTransaction:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def __init__(self, lineage_rows, *, profiles_by_artifact_id=None, parse_results_by_artifact_id=None, fail_on=None):
        self.lineage_rows = list(lineage_rows)
        self.profiles_by_artifact_id = profiles_by_artifact_id or {}
        self.parse_results_by_artifact_id = parse_results_by_artifact_id or {}
        self.fail_on = fail_on
        self.deleted_tables = []
        self.deleted_route_ids = []
        self.deleted_route_base_ids = []
        self.deleted_artifact_ids = []
        self.deleted_profile_ids = []
        self.deleted_segment_profile_ids = []
        self.queries = []

    def transaction(self):
        return _FakeTransaction(self)

    def _count_parse_results(self, artifact_ids):
        if self.parse_results_by_artifact_id:
            return sum(len(self.parse_results_by_artifact_id.get(int(artifact_id), [])) for artifact_id in artifact_ids)
        return len(list(artifact_ids))

    def _count_profiles(self, artifact_ids):
        return sum(len(self.profiles_by_artifact_id.get(int(artifact_id), [])) for artifact_id in artifact_ids)

    def execute(self, query, params=()):
        sql = " ".join(str(query).split())
        self.queries.append((sql, params))
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("forced db failure")
        if "FROM qbot_v2.route_stage_lineage" in sql and "SELECT" in sql:
            return _FakeResult([row for row in self.lineage_rows if row.get("route_artifact_id") is not None])
        if sql.startswith("SELECT count(*) AS n FROM qbot_v2.route_parse_results"):
            return _FakeResult([{"n": self._count_parse_results(list(params[0]))}])
        if sql.startswith("SELECT count(*) AS n FROM qbot_v2.route_surface_profiles"):
            return _FakeResult([{"n": self._count_profiles(list(params[0]))}])
        if sql.startswith("SELECT count(*) AS n FROM qbot_v2.route_surface_segments"):
            return _FakeResult([{"n": self._count_profiles(list(params[0]))}])
        if sql.startswith("DELETE FROM qbot_v2.route_artifacts"):
            self.deleted_tables.append("route_artifacts")
            self.deleted_artifact_ids.extend(list(params[0]))
            return _FakeResult(rowcount=len(list(params[0])))
        if sql.startswith("DELETE FROM qbot_v2.route_stage_lineage"):
            self.deleted_tables.append("route_stage_lineage")
            self.deleted_route_base_ids.extend(list(params[0]))
            return _FakeResult(rowcount=len(list(params[0])))
        if sql.startswith("DELETE FROM qbot_v2.route_base"):
            self.deleted_tables.append("route_base")
            self.deleted_route_ids.extend(list(params[0]))
            return _FakeResult(rowcount=len(list(params[0])))
        raise AssertionError(f"unexpected query: {sql}")


def test_bounds_create_one_stage_per_day():
    assert export._validated_bounds([30, 75.5], 120.0) == [
        (0.0, 30.0),
        (30.0, 75.5),
        (75.5, 120.0),
    ]


@pytest.mark.parametrize("cuts", [[30, 30], [70, 20], [-1], [121], [0.4, 1.0]])
def test_bounds_reject_invalid_or_too_short_days(cuts):
    with pytest.raises(ValueError):
        export._validated_bounds(cuts, 120.0)


def test_child_ids_are_deterministic_per_split_and_day():
    stages = export._validated_bounds([30, 75.5], 120.0)
    key = export._split_key("parent-version", stages)
    assert export._child_route_id("komoot-123", key, 1) == export._child_route_id("komoot-123", key, 1)
    assert export._child_route_id("komoot-123", key, 1) != export._child_route_id("komoot-123", key, 2)


def test_export_does_not_call_attraction_discovery():
    source = (
        inspect.getsource(export.create_planer_day_routes)
        + inspect.getsource(export._inherit_parent_baseline)
        + inspect.getsource(export._cleanup_superseded_planer_day_routes)
    )
    assert "ensure_route_attractions" not in source
    assert "discover_sources" not in source
    assert "Wikipedia" not in source
    assert "Wikidata" not in source
    assert "Google" not in source
    assert "parent_route_slice" in source
    assert "route_surface_layer" in source
    assert "route_poi_layer" in source
    assert "route_artifacts" in source
    assert "route_parse_results" in source
    assert "stage_route_id ~" in source
    assert "_cleanup_superseded_planer_day_routes" in source


def test_cleanup_removes_superseded_children_artifacts_and_files(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "EXPORT_ROOT", tmp_path)
    old_route_1 = "planer-aaaa1111-bbbbbbbbbb-d01"
    old_route_2 = "planer-aaaa1111-cccccccccc-d02"
    for route_id in (old_route_1, old_route_2):
        (tmp_path / f"rwgps_{route_id}.gpx").write_text("<gpx />", encoding="utf-8")

    conn = _FakeConn(
        [
            {
                "stage_route_base_id": 21,
                "stage_route_id": old_route_1,
                "split_key": "old-split",
                "day_index": 1,
                "route_artifact_id": 301,
                "route_parse_result_id": 401,
            },
            {
                "stage_route_base_id": 22,
                "stage_route_id": old_route_2,
                "split_key": "old-split",
                "day_index": 2,
                "route_artifact_id": 302,
                "route_parse_result_id": 402,
            },
        ],
        profiles_by_artifact_id={
            301: [{"id": 401, "route_artifact_id": 301}],
            302: [{"id": 402, "route_artifact_id": 302}],
        },
    )

    result = export._cleanup_superseded_planer_day_routes(
        conn,
        parent_route_base_id=10,
        current_split_key="current-split",
    )

    assert result["removed_route_count"] == 2
    assert result["removed_artifact_count"] == 2
    assert result["removed_parse_result_count"] == 2
    assert result["removed_surface_profile_count"] == 2
    assert result["removed_surface_segment_count"] == 2
    assert result["removed_file_count"] == 0
    assert result["removed_route_ids"] == [old_route_1, old_route_2]
    assert result["removed_artifact_ids"] == [301, 302]
    assert result["missing_file_count"] == 0
    assert result["warnings"] == []
    assert conn.deleted_tables == [
        "route_artifacts",
        "route_stage_lineage",
        "route_base",
    ]
    assert result["file_targets"] == [
        (old_route_1, tmp_path / f"rwgps_{old_route_1}.gpx"),
        (old_route_2, tmp_path / f"rwgps_{old_route_2}.gpx"),
    ]
    file_result = export._cleanup_superseded_planer_day_route_files(result["file_targets"])
    assert file_result["removed_file_count"] == 2
    assert file_result["missing_file_count"] == 0
    assert file_result["warnings"] == []
    assert not (tmp_path / f"rwgps_{old_route_1}.gpx").exists()
    assert not (tmp_path / f"rwgps_{old_route_2}.gpx").exists()


def test_cleanup_same_split_does_not_remove_current_set(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "EXPORT_ROOT", tmp_path)
    current_route = "planer-aaaa1111-bbbbbbbbbb-d01"
    (tmp_path / f"rwgps_{current_route}.gpx").write_text("<gpx />", encoding="utf-8")

    conn = _FakeConn([])
    result = export._cleanup_superseded_planer_day_routes(
        conn,
        parent_route_base_id=10,
        current_split_key="bbbbbbbbbb",
    )

    assert result["removed_route_count"] == 0
    assert result["removed_artifact_count"] == 0
    assert result["removed_parse_result_count"] == 0
    assert result["removed_file_count"] == 0
    assert result["removed_route_ids"] == []
    assert result["file_targets"] == []
    assert conn.deleted_tables == []
    assert (tmp_path / f"rwgps_{current_route}.gpx").exists()


def test_cleanup_refuses_manual_routes_even_if_lineage_contains_them(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "EXPORT_ROOT", tmp_path)
    manual_route = "manual-123"
    (tmp_path / f"rwgps_{manual_route}.gpx").write_text("<gpx />", encoding="utf-8")

    conn = _FakeConn(
        [
            {
                "stage_route_base_id": 77,
                "stage_route_id": manual_route,
                "split_key": "old-split",
                "day_index": 1,
            }
        ]
    )

    result = export._cleanup_superseded_planer_day_routes(
        conn,
        parent_route_base_id=10,
        current_split_key="current-split",
    )

    assert result["removed_route_count"] == 0
    assert result["removed_artifact_count"] == 0
    assert result["removed_parse_result_count"] == 0
    assert result["removed_file_count"] == 0
    assert result["removed_route_ids"] == []
    assert result["file_targets"] == []
    assert conn.deleted_tables == []
    assert result["warnings"] == []
    assert (tmp_path / f"rwgps_{manual_route}.gpx").exists()


def test_cleanup_missing_file_is_informational(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "EXPORT_ROOT", tmp_path)
    route_id = "planer-aaaa1111-bbbbbbbbbb-d01"
    conn = _FakeConn(
        [
            {
                "stage_route_base_id": 21,
                "stage_route_id": route_id,
                "split_key": "old-split",
                "day_index": 1,
                "route_artifact_id": 301,
                "route_parse_result_id": 401,
            }
        ],
        profiles_by_artifact_id={301: [{"id": 401, "route_artifact_id": 301}]},
    )

    result = export._cleanup_superseded_planer_day_routes(
        conn,
        parent_route_base_id=10,
        current_split_key="current-split",
    )

    assert result["removed_route_count"] == 1
    assert result["removed_artifact_count"] == 1
    assert result["removed_file_count"] == 0
    assert result["warnings"] == []
    assert result["file_targets"] == [(route_id, tmp_path / f"rwgps_{route_id}.gpx")]

    file_result = export._cleanup_superseded_planer_day_route_files(result["file_targets"])
    assert file_result["removed_file_count"] == 0
    assert file_result["missing_file_count"] == 1
    assert file_result["missing_file_paths"] == [str(tmp_path / f"rwgps_{route_id}.gpx")]
    assert file_result["warnings"] == []


def test_cleanup_db_failure_keeps_current_routes_and_reports_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "EXPORT_ROOT", tmp_path)
    route_id = "planer-aaaa1111-bbbbbbbbbb-d01"
    (tmp_path / f"rwgps_{route_id}.gpx").write_text("<gpx />", encoding="utf-8")
    conn = _FakeConn(
        [
            {
                "stage_route_base_id": 21,
                "stage_route_id": route_id,
                "split_key": "old-split",
                "day_index": 1,
                "route_artifact_id": 301,
                "route_parse_result_id": 401,
            }
        ],
        profiles_by_artifact_id={301: [{"id": 401, "route_artifact_id": 301}]},
        fail_on="DELETE FROM qbot_v2.route_base",
    )

    result = export._cleanup_superseded_planer_day_routes(
        conn,
        parent_route_base_id=10,
        current_split_key="current-split",
    )

    assert result["removed_route_count"] == 0
    assert result["removed_artifact_count"] == 0
    assert result["removed_file_count"] == 0
    assert result["warnings"] == ["db cleanup failed: forced db failure"]
    assert result["file_targets"] == []
    assert (tmp_path / f"rwgps_{route_id}.gpx").exists()


def test_create_planer_day_routes_defers_file_cleanup_until_after_db_commit(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "EXPORT_ROOT", tmp_path)
    source_path = tmp_path / "source.gpx"
    source_path.write_text("<gpx />", encoding="utf-8")

    parent = {
        "route_id": "parent-123",
        "route_base_id": 11,
        "route_version_key": "version-key",
        "distance_m": 10000.0,
    }
    state = {}

    class _CommitConn:
        def __init__(self):
            self.committed = False
            self.queries = []

        def transaction(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self.committed = exc_type is None
            return False

        def execute(self, query, params=()):
            sql = " ".join(str(query).split())
            self.queries.append((sql, params))
            return _FakeResult(rowcount=1)

    class _DummyConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    parent_lookup_conn = _DummyConn()
    create_conn = _CommitConn()
    cleanup_conn = _CommitConn()
    db_conns = iter([parent_lookup_conn, create_conn, cleanup_conn])

    monkeypatch.setattr(export, "_db_conn", lambda: next(db_conns))
    monkeypatch.setattr(export, "_route_base_row", lambda conn, route_id: parent)
    monkeypatch.setattr(export, "_resolve_source_path", lambda parent_row, conn: str(source_path))
    monkeypatch.setattr(export, "_parent_name", lambda conn, route_base: "Parent route")
    monkeypatch.setattr(export, "_parse_gpx_points", lambda path: ([{"cum_km": 0.0}, {"cum_km": 10.0}], None))
    monkeypatch.setattr(export, "_build_segment_points", lambda points, start_km, end_km: (points, end_km))
    monkeypatch.setattr(export, "_gpx_xml", lambda segment, parent_name, title: b"<gpx />")
    monkeypatch.setattr(export, "_validate_gpx_file", lambda file_path, distance_km: {"valid_gpx": True})
    monkeypatch.setattr(
        export,
        "_register_canonical_gpx",
        lambda file_path, child_route_id, title, lineage_meta: {
            "route_artifact_id": 99,
            "route_base_id": 88,
            "route_version_key": "child-version",
        },
    )
    monkeypatch.setattr(export, "_inherit_parent_baseline", lambda conn, **kwargs: {})

    def fake_cleanup(conn, *, parent_route_base_id, current_split_key):
        state["cleanup_conn"] = conn
        return {
            "removed_route_count": 0,
            "removed_artifact_count": 0,
            "removed_parse_result_count": 0,
            "removed_surface_profile_count": 0,
            "removed_surface_segment_count": 0,
            "removed_file_count": 0,
            "removed_route_ids": [],
            "removed_artifact_ids": [],
            "removed_file_paths": [],
            "missing_file_count": 0,
            "missing_file_paths": [],
            "warnings": [],
            "file_targets": [("planer-abcdef12-1234567890-d01", tmp_path / "rwgps_planer-abcdef12-1234567890-d01.gpx")],
        }

    def fake_file_cleanup(file_targets):
        assert state["cleanup_conn"].committed is True
        return {
            "removed_file_count": len(file_targets),
            "removed_file_paths": [str(path) for _, path in file_targets],
            "missing_file_count": 0,
            "missing_file_paths": [],
            "warnings": [],
        }

    monkeypatch.setattr(export, "_cleanup_superseded_planer_day_routes", fake_cleanup)
    monkeypatch.setattr(export, "_cleanup_superseded_planer_day_route_files", fake_file_cleanup)

    result = export.create_planer_day_routes(route_id="parent-123", cuts=[5])

    assert create_conn.committed is True
    assert cleanup_conn.committed is True
    assert state["cleanup_conn"] is cleanup_conn
    assert result["cleanup"]["removed_file_count"] == 1
    assert result["cleanup_warnings"] == []


def test_lineage_schema_pins_parent_and_km_range():
    migration = (Path(__file__).parents[1] / "sql" / "route_stage_lineage_v1.sql").read_text()
    assert "parent_route_base_id" in migration
    assert "parent_km_from" in migration
    assert "parent_km_to" in migration
    assert "UNIQUE (parent_route_base_id, split_key, day_index)" in migration
