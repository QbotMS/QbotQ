import math

from qbot3.routes.route_attraction_engine import classify, normalize_google_source_candidates, rank_candidates


def _row(name, km, *, extract="", tags=None, qid=None, pageid=1, lat=None):
    return {
        "name": name,
        "lat": lat if lat is not None else 50.0 + km / 10000.0,
        "lon": 17.0,
        "km": float(km),
        "dist": 300.0,
        "sources": {"wikipedia"} if pageid else {"osm"},
        "pageid": pageid,
        "wiki": f"https://pl.wikipedia.org/?curid={pageid}" if pageid else None,
        "qid": qid,
        "extract": extract,
        "image": None,
        "tags": tags or {},
        "osm_ids": [],
    }


def _city_entity(name):
    return {"labels": {"pl": {"value": name}}, "descriptions": {"pl": {"value": "miasto w Polsce"}}, "types": ["miasto"]}


def test_feedback_categories_and_filters():
    city = _row("Prudnik", 40, qid="Q1")
    assert classify(city, _city_entity("Prudnik"))[0] == "historic_town"
    assert classify(_row("Zabytkowa Altana", 20, pageid=None), {})[0] is None
    assert classify(_row("Kapliczka św. Jana", 20, pageid=None), {})[0] is None
    assert classify(_row("Pałac w Kopicach", 20, pageid=None, tags={"historic": "manor"}), {})[0] == "castle_palace"


def test_generic_archaeology_drops_below_selection_but_visible_tower_survives():
    generic = _row("Grodzisko stożkowate", 20, extract="stanowisko archeologiczne", qid="Q10")
    visible = _row("Grodzisko Prudnik Dębowiec - wieża rycerska", 40,
                   extract="stanowisko archeologiczne, zachowane ruiny wieży", qid="Q11")
    result = rank_candidates([generic, visible], [], {"Q10": {}, "Q11": {}}, 100)
    names = {row["name"] for row in result["candidates"]}
    assert generic["name"] not in names
    assert visible["name"] in names


def test_required_towns_share_one_candidate_pool_and_density_is_bounded():
    names = ["Tułowice", "Grodków", "Kamieniec Ząbkowicki", "Nysa", "Prudnik"]
    rows = [_row(name, 10 + index * 25, qid=f"Q{index + 1}") for index, name in enumerate(names)]
    entities = {row["qid"]: _city_entity(row["name"]) for row in rows}
    for index in range(30):
        rows.append(_row(f"Pałac testowy {index}", 2 + index * 4, pageid=None,
                         tags={"historic": "manor"}, lat=49.0 + index / 1000.0))
    result = rank_candidates(rows, [], entities, 100)
    selected = {row["name"] for row in result["candidates"]}
    assert set(names) <= selected
    assert len(result["candidates"]) <= math.ceil(12)
    assert sum(row["is_recommended"] for row in result["candidates"]) <= math.ceil(2.5)


def test_candidate_keys_and_ranking_are_stable():
    rows = [_row("Pałac w Mosznej", 10, qid="Q123"), _row("Fort Prusy", 40, pageid=None, tags={"historic": "fort"})]
    first = rank_candidates(rows, [], {"Q123": {}}, 100)
    second = rank_candidates(reversed(rows), [], {"Q123": {}}, 100)
    assert [(row["candidate_key"], row["score"]) for row in first["candidates"]] == [
        (row["candidate_key"], row["score"]) for row in second["candidates"]
    ]


def test_google_names_enter_the_same_semantic_gate_not_a_separate_whitelist():
    raw = [
        {"name": "Pałac testowy", "lat": 50.0, "lon": 17.0, "route_km": 10,
         "distance_to_track_m": 200, "google_place_id": "palace", "source_tags": "tourism=attraction"},
        {"name": "Super Atrakcja", "lat": 50.1, "lon": 17.0, "route_km": 30,
         "distance_to_track_m": 200, "google_place_id": "generic", "source_tags": "tourism=attraction"},
    ]
    rows = normalize_google_source_candidates(raw)
    result = rank_candidates(rows, raw, {}, 100)
    assert [row["name"] for row in result["candidates"]] == ["Pałac testowy"]
    assert result["candidates"][0]["candidate_key"] == "google:palace"
