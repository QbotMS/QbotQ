import inspect
from pathlib import Path

from qbot3.routes import route_attraction_store as store
from qbot3.routes.route_attraction_store import get_route_attractions


class _Result:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        if isinstance(self.value, list):
            return self.value[0] if self.value else None
        return self.value

    def fetchall(self):
        return self.value if isinstance(self.value, list) else []


class _Conn:
    def __init__(self, *, enabled=True, rows=None, schema=True, published=True):
        self.enabled = enabled
        self.rows = rows or []
        self.schema = schema
        self.published = published
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append((" ".join(query.split()), params))
        if "to_regclass('qbot_v2.route_attraction_run')" in query:
            value = "qbot_v2.route_attraction_run" if self.schema else None
            return _Result((value, value))
        if "to_regclass('qbot_v2.route_poi_prefs')" in query:
            return _Result(("qbot_v2.route_poi_prefs",))
        if "SELECT attractions_enabled" in query:
            return _Result({"attractions_enabled": self.enabled})
        if "SELECT run_id FROM qbot_v2.route_attraction_run" in query:
            return _Result({"run_id": 7} if self.published else None)
        if "FROM qbot_v2.route_attraction_run" in query:
            return _Result(self.rows)
        raise AssertionError(query)


def _row():
    return {
        "candidate_key": "wikidata:Q1", "name": "Nysa", "category": "historic_town",
        "category_label": "historyczne miejsce / rynek", "km_on_route": 187.7,
        "distance_from_route_m": 100.0, "lat": 50.47, "lon": 17.33, "visit_min": 25,
        "score": 81.0, "selection_score": 81.0, "candidate_rank": 1,
        "is_recommended": True, "recommended_rank": 1, "why": "miasto",
        "extract": "", "wiki_url": "https://example.test", "wikidata_id": "Q1",
        "image_url": None, "rating": None, "rating_count": None, "nearby_json": [],
    }


def test_reader_returns_none_before_migration_for_legacy_fallback():
    assert get_route_attractions(_Conn(schema=False), 10) is None


def test_disabled_attractions_return_empty_without_touching_legacy_layer():
    conn = _Conn(enabled=False, rows=[_row()])
    assert get_route_attractions(conn, 10) == []
    assert not any("route_poi_layer" in query for query, _ in conn.queries)


def test_reader_uses_published_layer_and_maps_existing_web_contract():
    conn = _Conn(rows=[_row()])
    rows = get_route_attractions(conn, 10, km_from=100, km_to=200, tier="recommended")
    assert rows[0]["name"] == "Nysa"
    assert rows[0]["km"] == 187.7
    assert rows[0]["dist_m"] == 100
    assert rows[0]["place_id"] == "wikidata:Q1"
    query, params = conn.queries[-1]
    assert "r.published=true" in query and "a.is_recommended=true" in query
    assert params == (10, 100.0, 200.0)


def test_enabled_route_without_published_run_uses_legacy_fallback():
    assert get_route_attractions(_Conn(enabled=True, published=False), 10) is None


def test_published_empty_result_does_not_resurrect_legacy_attractions():
    assert get_route_attractions(_Conn(enabled=True, published=True, rows=[]), 10) == []


def test_attraction_writer_is_separate_and_publish_schema_has_one_active_run():
    writer_source = inspect.getsource(store.ensure_route_attractions) + inspect.getsource(store._insert_layer)
    assert "route_poi_layer" not in writer_source
    assert "DELETE FROM" not in writer_source
    migration = (Path(__file__).parents[1] / "sql" / "route_attraction_store_v1.sql").read_text()
    assert "route_attraction_one_published_uq" in migration
    assert "WHERE published" in migration
    assert "GRANT SELECT, INSERT, UPDATE, DELETE" in migration
    assert "GRANT USAGE, SELECT ON SEQUENCE" in migration


def test_route_attractions_tool_accepts_canonical_komoot_route_ids():
    registry = (Path(__file__).parents[1] / "qbot3" / "tool_registry.py").read_text()
    section = registry.split("def _load_route_attractions_tool", 1)[1].split("\ndef _", 1)[0]
    assert "rid.isdigit()" not in section
    assert "A-Za-z0-9._:-" in section
