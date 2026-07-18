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


def test_palace_ancillary_objects_and_village_article_mentions_are_noise():
    assert classify(_row("Taras Pałacowy", 10, pageid=None, tags={"tourism": "attraction"}), {})[0] is None
    assert classify(_row("Oficyna pałacowa z XIX wieku", 10, pageid=None, tags={"tourism": "attraction"}), {})[0] is None
    assert classify(_row("Pałac", 10, pageid=None, tags={"tourism": "attraction"}), {})[0] is None
    assert classify(_row("Park przypałacowy", 10, pageid=None, tags={"tourism": "attraction"}), {})[0] is None
    assert classify(_row("Dawny budynek gospodarczy przy pałacu", 10, pageid=None, tags={"tourism": "attraction"}), {})[0] is None
    village = _row("Kozielno", 10, extract="Kozielno – wieś w Polsce. We wsi znajduje się pałac.")
    assert classify(village, {})[0] is None


def test_tangible_landmark_is_not_absorbed_by_nearby_historic_town():
    town = _row("Kamieniec Ząbkowicki", 138.0, qid="Q1", lat=50.45)
    palace = _row("Pałac Marianny Orańskiej", 138.2, pageid=None,
                  tags={"tourism": "attraction"}, lat=50.4505)
    result = rank_candidates([town, palace], [], {"Q1": _city_entity(town["name"])}, 100)
    assert {row["name"] for row in result["candidates"]} == {town["name"], palace["name"]}


def test_candidate_pool_keeps_nearby_quality_while_recommendations_use_spacing():
    rows = [
        _row("Fort Alpha", 20.0, pageid=None, tags={"historic": "fort"}, lat=50.0),
        _row("Fort Beta", 21.0, pageid=None, tags={"historic": "fort"}, lat=50.01),
        _row("Fort Gamma", 22.0, pageid=None, tags={"historic": "fort"}, lat=50.02),
    ]
    result = rank_candidates(rows, [], {}, 10)
    assert len(result["candidates"]) == 2  # ceil(1.2)
    assert all(row["selection_score"] == row["score"] for row in result["candidates"])


def test_wizna_battlefield_is_not_rejected_by_incidental_sacred_text():
    defence = _row(
        "Obrona Wizny", 64.9,
        extract="Bitwa pod Wizną. Walki toczyły się również w pobliżu kościoła.",
        lat=50.0,
    )
    hill = _row(
        "Góra Strękowa", 64.1,
        extract="Miejsce bitwy i linia obrony; w opisie wspomniano również kaplicę.",
        lat=50.01,
    )
    result = rank_candidates([defence, hill], [], {}, 100)
    assert {row["name"] for row in result["candidates"]} == {defence["name"], hill["name"]}
    assert all(row["category"] == "historic_site" for row in result["candidates"])


def test_global_engineering_landmark_survives_without_polish_fort_keywords():
    caminito = _row(
        "Caminito del Rey", 45, extract="A historic walkway fixed to the walls of a gorge in Andalusia.",
        tags={"tourism": "attraction", "man_made": "bridge"},
    )
    result = rank_candidates([caminito], [], {}, 100)
    assert result["candidates"][0]["category"] == "cultural_landmark"


def test_exceptional_place_up_to_two_km_uses_penalty_instead_of_hard_rejection():
    landmark = _row("Historic aqueduct", 50, extract="engineering landmark", tags={"heritage": "yes"})
    landmark["dist"] = 1900.0
    result = rank_candidates([landmark], [], {}, 100)
    assert [row["name"] for row in result["candidates"]] == [landmark["name"]]
