"""Pamiec podreczna Google Places (2026-10-06). Bez prawdziwego Google: httpx.post podmieniony;
cache/budzet podmienione na slowniki w pamieci (bez bazy)."""
import os
import sys
from unittest import mock

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from qbot3.artifacts import route_analyzer as ra  # noqa: E402
from qbot3.routes import google_places_cache as gc  # noqa: E402


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


def _fake_store():
    store = {}
    return store, (lambda k: store.get(k)), (lambda k, req, places: store.__setitem__(k, places))


def test_second_call_served_from_cache_without_http():
    store, fget, fput = _fake_store()
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(json)
        return _Resp({"places": [{"id": "p1", "displayName": {"text": "Zamek"}}]})

    with mock.patch.object(gc, "get", side_effect=fget), mock.patch.object(gc, "put", side_effect=fput), \
            mock.patch.object(ra.httpx, "post", side_effect=fake_post):
        a = ra._route_poi_v2_google_search_nearby(50.1234, 19.5, radius_m=1800, api_key="x",
                                                  included_types=["tourist_attraction"])
        b = ra._route_poi_v2_google_search_nearby(50.12341, 19.50001, radius_m=1800, api_key="x",
                                                  included_types=["tourist_attraction"])
    assert a == b and len(calls) == 1
    assert calls[0]["maxResultCount"] == 20


def test_cache_key_depends_on_types_and_radius():
    k1 = gc.cache_key(50.1, 19.5, 1800, ["a", "b"], 20)
    assert k1 == gc.cache_key(50.1, 19.5, 1800, ["b", "a"], 20)
    assert k1 != gc.cache_key(50.1, 19.5, 2300, ["a", "b"], 20)
    assert k1 != gc.cache_key(50.1, 19.5, 1800, ["a"], 20)
    assert k1 != gc.cache_key(50.1, 19.5, 1800, ["a", "b"], 10)


def test_cached_point_does_not_reserve_budget():
    with mock.patch.object(gc, "get", return_value=[{"id": "p"}]):
        assert ra.google_nearby_is_cached(50.1, 19.5, 1800, ["tourist_attraction"]) is True
    with mock.patch.object(gc, "get", return_value=None):
        assert ra.google_nearby_is_cached(50.1, 19.5, 1800, ["tourist_attraction"]) is False
