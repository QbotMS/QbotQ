import inspect
from pathlib import Path

import pytest

from qbot3.routes import planer_stage_export as export


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
    source = inspect.getsource(export.create_planer_day_routes) + inspect.getsource(export._inherit_parent_baseline)
    assert "ensure_route_attractions" not in source
    assert "discover_sources" not in source
    assert "Wikipedia" not in source
    assert "Wikidata" not in source
    assert "Google" not in source
    assert "parent_route_slice" in source
    assert "route_surface_layer" in source
    assert "route_poi_layer" in source
    assert "status='disabled'" in source


def test_lineage_schema_pins_parent_and_km_range():
    migration = (Path(__file__).parents[1] / "sql" / "route_stage_lineage_v1.sql").read_text()
    assert "parent_route_base_id" in migration
    assert "parent_km_from" in migration
    assert "parent_km_to" in migration
    assert "UNIQUE (parent_route_base_id, split_key, day_index)" in migration
