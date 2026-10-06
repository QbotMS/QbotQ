import math

from qbot3.routes.route_attraction_engine import (
    CANDIDATES_PER_100_KM, RECOMMENDED_MAX_PER_100_KM, RECOMMENDED_QUALITY_SCORE,
    classify, dedupe, normalize_google_source_candidates, rank_candidates,
)


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
    assert len(result["candidates"]) <= math.ceil(CANDIDATES_PER_100_KM)
    assert sum(row["is_recommended"] for row in result["candidates"]) <= math.ceil(RECOMMENDED_MAX_PER_100_KM)


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
    assert len(result["candidates"]) == 3  # ceil(10 km * 25/100) = 3
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


def test_dense_heritage_route_recommends_all_strong_stops_within_cap():
    """v2.3: szlak zamkow - kazdy mocny przystanek polecony, ale nie ponad sufit."""
    rows = [_row(f"Zamek testowy {i}", 5 + i * 9, pageid=None, tags={"historic": "castle"},
                 lat=50.0 + i / 100.0) for i in range(18)]
    result = rank_candidates(rows, [], {}, 180)
    strong = [r for r in result["candidates"] if r["score"] >= RECOMMENDED_QUALITY_SCORE]
    rec = [r for r in result["candidates"] if r["is_recommended"]]
    assert len(rec) >= min(len(strong), math.ceil(1.8 * RECOMMENDED_MAX_PER_100_KM))
    assert len(rec) <= math.ceil(1.8 * RECOMMENDED_MAX_PER_100_KM)
    assert len(rec) >= math.ceil(1.8 * 2.5)


def test_merge_keeps_castle_tags_when_plaque_is_merged():
    """Rabsztyn 2026-10-05: tablica 'Ruiny zamku' obok zamku nie moze zamienic go w pomnik."""
    castle = _row("Zamek w Rabsztynie", 130.4, pageid=None, qid="Q9386720", lat=50.3,
                  tags={"historic": "castle", "heritage": "2", "castle_type": "defensive"})
    castle["dist"] = 73.0
    plaque = _row("Ruiny zamku Rabsztyn", 130.4, pageid=None, lat=50.3002,
                  tags={"historic": "memorial", "memorial": "plaque"})
    plaque["dist"] = 101.0
    merged = dedupe([plaque, castle])
    castles = [m for m in merged if m["name"] == "Zamek w Rabsztynie"]
    assert len(castles) == 1 and castles[0]["tags"]["historic"] == "castle"
    result = rank_candidates([castle, plaque], [], {"Q9386720": {}}, 100)
    assert [row["name"] for row in result["candidates"]] == ["Zamek w Rabsztynie"]


def test_city_cluster_limited_to_two_recommended():
    """v2.4: 5 mocnych obiektow w jednym miescie -> max 2 polecane, reszta miejsc dla szlaku."""
    city = [_row(f"Kamienica {i}", 180.0 + i * 0.1, pageid=None, tags={"historic": "castle", "heritage": "2"},
                 lat=50.0610 + i * 0.001) for i in range(5)]
    for row in city:
        row["lon"] = 19.937
        row["dist"] = 50.0
    route = [_row(f"Zamek szlaku {i}", 20 + i * 30, pageid=None, tags={"historic": "castle", "heritage": "2"},
                  lat=50.5 + i * 0.1) for i in range(5)]
    for row in route:
        row["dist"] = 50.0
    result = rank_candidates(city + route, [], {}, 182)
    rec = [r for r in result["candidates"] if r["is_recommended"]]
    assert sum(1 for r in rec if r["name"].startswith("Kamienica")) <= 2
    assert sum(1 for r in rec if r["name"].startswith("Zamek szlaku")) == 5


def test_stop_named_after_main_object():
    """v2.4: Wawel - przystanek nazywa sie od zamku, nie od wiezy/grobow o wyzszej ocenie."""
    from qbot3.routes.route_attraction_engine import collapse_stops
    tower = {"name": "Wieza Jana III Sobieskiego", "km": 180.0, "lat": 50.054, "lon": 19.935,
             "score": 80.0, "category": "castle_palace"}
    castle = {"name": "Zamek Krolewski na Wawelu", "km": 180.1, "lat": 50.0541, "lon": 19.9351,
              "score": 75.0, "category": "castle_palace"}
    stops = collapse_stops([tower, castle])
    assert len(stops) == 1
    assert stops[0]["name"] == "Zamek Krolewski na Wawelu"
    assert stops[0]["score"] == 80.0
    assert "Wieza Jana III Sobieskiego" in stops[0]["nearby"]


def test_palace_does_not_rename_town_hall_tower():
    """v2.4 regresja 06.10: Rynek - 'Wieza ratuszowa' nie zmienia sie w palac, Barbakan w 'Klasztorek'."""
    from qbot3.routes.route_attraction_engine import collapse_stops
    tower = {"name": "Wieza ratuszowa w Krakowie", "km": 180.0, "lat": 50.0616, "lon": 19.9368,
             "score": 88.0, "category": "historic_building"}
    palace = {"name": "Palac Malachowskich", "km": 180.1, "lat": 50.0617, "lon": 19.9370,
              "score": 80.0, "category": "historic_building"}
    barb = {"name": "Barbakan", "km": 180.5, "lat": 50.0655, "lon": 19.9417, "score": 84.0,
            "category": "fortification"}
    kl = {"name": "Klasztorek", "km": 180.5, "lat": 50.0656, "lon": 19.9418, "score": 70.0,
          "category": "historic_building"}
    names = sorted(s["name"] for s in collapse_stops([tower, palace, barb, kl]))
    assert names == ["Barbakan", "Wieza ratuszowa w Krakowie"]


def test_google_popularity_scales_with_reviews():
    """v2.5: bardzo popularne miejsce (50 tys. opinii) dostaje wyraznie wiecej niz 1000 opinii."""
    from qbot3.routes.route_attraction_engine import _google_score
    small = _google_score(4.6, 1000)
    huge = _google_score(4.6, 50000)
    assert huge - small >= 3.0
    assert _google_score(4.6, 5) < 2.5  # popularnosc ~0, gwiazdki wygladzone do sredniej
    assert huge <= 13.5


def test_tomb_does_not_swallow_castle():
    """Wawel 2026-10-06: blizsze 'Groby Krolewskie' (tomb) nie wchlaniaja zamku (castle, Q18820)."""
    tomb = _row("Groby Krolewskie na Wawelu", 180.0, pageid=None, lat=50.0540,
                tags={"historic": "tomb", "amenity": "crypt"})
    tomb["dist"] = 696.0
    castle = _row("Zamek Krolewski na Wawelu", 180.0, pageid=None, qid="Q18820", lat=50.0541,
                  tags={"historic": "castle", "heritage": "2"})
    castle["dist"] = 746.0
    merged = dedupe([tomb, castle])
    assert sorted(m["name"] for m in merged) == ["Groby Krolewskie na Wawelu", "Zamek Krolewski na Wawelu"]
    result = rank_candidates([tomb, castle], [], {"Q18820": {}}, 100)
    assert [r["name"] for r in result["candidates"]] == ["Zamek Krolewski na Wawelu"]


def test_dense_city_uses_smaller_cluster():
    """v2.6: gesto (miasto) -> skupisko 0,8 km: dwie grupy po 4 obiekty ~1 km od siebie
    (Rynek / Wawel) daja po 2 polecane, nie 2 na cale miasto."""
    names = [["Sukiennice", "Barbakan", "Arsenal", "Kurdybanek"], ["Wawel", "Smocza", "Kanonicza", "Dom Dlugosza"]]
    rows = []
    for g, lat0 in enumerate((50.0610, 50.0520)):  # ~1 km miedzy grupami
        for i in range(4):
            # rozne km: bez scalania w przystanek i bez kary za bliskosc na trasie
            r = _row(names[g][i], 20.0 + (g * 4 + i) * 20.0, pageid=None,
                     tags={"historic": "castle", "heritage": "2"}, lat=lat0 + i * 0.0005)  # grupa ~170 m, przerwa ~830 m
            r["lon"] = 19.937
            r["dist"] = 50.0
            rows.append(r)
    result = rank_candidates(rows, [], {}, 182)
    rec = {r["name"] for r in result["candidates"] if r["is_recommended"]}
    assert len(rec & set(names[0])) == 2
    assert len(rec & set(names[1])) == 2
