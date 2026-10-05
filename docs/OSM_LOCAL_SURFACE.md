# Lokalne zrodlo drog OSM dla nawierzchni (Polska)

_Wprowadzone 2026-10-05._

## Po co
Silnik nawierzchni (`tools/rwgps/route_surface_engine.py`) pobieral drogi z publicznego
Overpass. 2026-10-05 overpass-api.de zaczal odrzucac IP serwera (135.181.133.182,
Connection refused na wszystkich adresach v4/v6), maps.mail.ru i kumi/private.coffee
dawaly timeout, overpass.openstreetmap.fr = 403 (whitelista). Efekt: trasa
komoot-3331694546 (Szlak Orlich Gniazd) miala 1/3 dlugosci "unmatched" i analiza
byla odrzucana. Trzy serwery overpass-api.de to jeden operator - zapas byl pozorny.

## Jak dziala
- Dane: Geofabrik `europe/poland-latest.osm.pbf` (te same dane OSM co Overpass,
  odswiezane przez Geofabrik codziennie) -> `/opt/qbot/data/osm/`.
- `scripts/osm_extract_fetch.py --start|--status|--run` - pobranie + kontrola MD5.
- `scripts/osm_local_build.py --start|--status|--run` - osmium tags-filter w/highway
  -> osmium export geojsonseq -> SQLite `roads.sqlite` (tabela ways + R-tree bbox + meta).
  Budowa do `.tmp`, podmiana atomowa. Trzymane tagi: highway, surface, tracktype,
  smoothness, name, ref, bicycle, access, cycleway, service, mtb:scale, sac_scale.
- `tools/rwgps/osm_local.py` - `covers_bbox()` (4 rogi prostokata kawalka w
  `poland.poly`), `query_ways()` - wynik w formacie Overpass.
- Silnik: `_chunk_payload` w `_fetch_highways_along_track` - kawalek w Polsce ->
  baza lokalna; poza Polska / przy granicy / blad bazy -> Overpass (z ponawianiem).
  Metryki: `local_osm_chunks`, `overpass_chunks`, `local_osm_errors`.
- Wylacznik: `QBOT_SURFACE_LOCAL_OSM=0`.

## Odswiezanie
Cron (root lub qbot), raz w tygodniu, np. poniedzialek 04:20:
`cd /opt/qbot/app && .venv/bin/python3 scripts/osm_extract_fetch.py --run && .venv/bin/python3 scripts/osm_local_build.py --run && .venv/bin/python3 scripts/osm_landmarks_build.py --run`
Pobranie ~1 min, budowa ~15 min. Stara baza dziala do chwili podmiany.

## Ponawianie Overpass (dla tras poza Polska)
Nieudany kawalek: 2 dodatkowe rundy po 20 s, kazdy kawalek dzielony na pol
(`QBOT_OVERPASS_CHUNK_RETRY_ROUNDS`, `QBOT_OVERPASS_CHUNK_RETRY_PAUSE_SEC`).
Trwaly brak -> ostrzezenie z km + `OVERPASS_INCOMPLETE`; slabszy czastkowy profil nie
nadpisuje lepszego (client.py); komunikat odrzucenia mowi wprost o awarii serwerow map
(route_surface_store._low_quality_reason).

## Inne kraje
Dograc plik kraju z Geofabrik + jego .poly i rozszerzyc budowe (obecnie tylko Polska).

## Zabytki dla atrakcji (2026-10-05)
- `scripts/osm_landmarks_build.py --start|--status|--run` - z tego samego pliku Polski: osmium tags-filter
  (historic, heritage, military, tourism, man_made) -> export -> SQLite `landmarks.sqlite` (srodek obiektu,
  wszystkie tagi, R-tree). Filtr = dawne zapytanie Overpass (`is_landmark`). Ok. 6 min.
- `tools/rwgps/osm_local.py`: `landmarks_enabled()`, `covers_bbox_landmarks()`, `query_landmarks()` (format
  Overpass `out center tags`).
- `qbot3/routes/route_attraction_sources.discover_osm_landmarks`: kawalek w PL -> baza lokalna; reszta Overpass.
  Wylacznik `QBOT_ATTR_LOCAL_OSM=0`.
