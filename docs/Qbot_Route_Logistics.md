# QBot Route Logistics

Trójtaktowy system wyszukiwania, zatwierdzania i importu POI do RWGPS.
POI są wstrzykiwane jako `<wpt>` do oryginalnego GPX trasy przed importem.

## Architektura

```
TEMPO 1 — CANDIDATES          TEMPO 2 — COMMIT-POI         TEMPO 3 — RWGPS IMPORT
─────────────────────         ──────────────────────        ──────────────────────────
GPX + Overpass                 candidates.json               route_with_selected_poi.gpx
    │                               │                                 │
    ▼                               ▼                                 ▼
candidates.json ◄─ ręczny ──►  selected_poi.json        POST /api/v1/routes.json
candidates.geojson     wybór   selected_poi.geojson      (nowa kopia trasy)
candidates.md                  selected_poi.gpx  ← debug  rwgps_import_result.json
candidates.xlsx                route_with_selected_poi.gpx ← IMPORT TO RWGPS
debug.json                     poi_commit_summary.md      route_logistics_final_summary.md
                               status: GPX_READY_FOR_     status: RWGPS_ROUTE_WITH_POI_
                                         RIDEWITHGPS_               IMPORTED
                                         IMPORT
```

**Zasada:** Candidates ≠ POI. Do GPX trafiają wyłącznie ręcznie zatwierdzone POI.
**Import:** POI są wstrzykiwane do oryginalnego GPX trasy jako `<wpt>` — powstaje
`route_with_selected_poi.gpx`. Ten plik jest importowany do RWGPS jako nowa kopia.
`selected_poi.gpx` (tylko waypointy) jest artefaktem debug/review, nie plikiem importowym.
RWGPS `points_of_interest` PUT nie jest używany (HTTP 500).

## Komendy CLI

```bash
# TEMPO 1 — szukaj kandydatów
.venv/bin/python scripts/route_logistics_candidates.py --route-id 55395119 --mode full
.venv/bin/python scripts/route_logistics_candidates.py --route-id 55401067 --mode attractions
.venv/bin/python scripts/route_logistics_candidates.py --route-id 55395119 --mode lodging --require '{"people":2,"budget":150}'

# TEMPO 2 — zatwierdź POI
.venv/bin/python scripts/route_logistics_commit_poi.py --route-id 55395119 --select food_001,water_003
.venv/bin/python scripts/route_logistics_commit_poi.py --route-id 55395119 --select food_001 water_003

# CLI wrapper
scripts/q/route_logistics candidates --route-id 55395119 --mode full
scripts/q/route_logistics commit-poi --route-id 55395119 --select food_001
```

## Kategorie i bufory

| Kategoria | Domyślny bufor | Opis |
|-----------|---------------|------|
| shops | 500 m | Sklepy, supermarkety, markety |
| water | 500 m | Woda pitna, źródła, krany |
| pharmacy | 500 m | Apteki, kliniki, szpitale |
| food | 1000 m | Restauracje, kawiarnie, bary |
| attractions | 1000 m | Muzea, punkty widokowe, zabytki |
| bike_service | 3000 m | Serwisy rowerowe, wypożyczalnie |
| transport | 1000 m | Dworce, przystanki, promy |
| lodging | wymagane --require | Hotele, hostele, kempingi |

## Lodging

Wymaga parametrów użytkownika:
```bash
--require '{"people":2,"budget":150,"radius_from_stage_end_m":5000,"room_type":"twin"}'
```

Bez --require zwraca NEEDS_REQUIREMENTS.

## Źródła

- **P0:** OSM Overpass API (overpass-api.de)
- **P1/P2:** web/live search (jeśli dostępne)
- Nigdy nie zgaduj ceny, dostępności, ocen ani godzin otwarcia.

## Pliki / artefakty

Wszystkie pod `/opt/qbot/artifacts/route_logistics/{route_id}/`:

| Plik | Tempo | Opis |
|------|-------|------|
| `candidates.json` | 1 | JSON contract CANDIDATES_READY |
| `candidates.geojson` | 1 | FeatureCollection dla mapy |
| `candidates.md` | 1 | Raport czytelny |
| `candidates.xlsx` | 1 | Excel (fallback CSV) |
| `debug.json` | 1 | Debug + timing |
| `selected_poi.json` | 2 | JSON contract GPX_READY_FOR_RIDEWITHGPS_IMPORT |
| `selected_poi.geojson` | 2 | GeoJSON tylko selected (review) |
| `selected_poi.gpx` | 2 | GPX \<wpt\> tylko selected (debug, NIE importować) |
| `route_with_selected_poi.gpx` | 2 | Oryginalny track + \<wpt\> POI (import do RWGPS) |
| `poi_commit_summary.md` | 2 | Raport commita |
| `rwgps_import_result.json` | 3 | Wynik importu RWGPS |
| `route_logistics_final_summary.md` | 3 | Raport końcowy |

## Statusy kandydata

- `CANDIDATE` — domyślny status
- `CONFIRMED` — potwierdzony
- `SOURCE_ONLY` — tylko ze źródła
- `LOW_CONFIDENCE` — niska pewność
- `NEEDS_REVIEW` — wymaga przeglądu
- `NEEDS_REQUIREMENTS` — wymaga parametrów
- `DETOUR` — objazd/poza trasą
- `PRICE_UNKNOWN` / `AVAILABILITY_UNKNOWN`

## Obsługa błędów

- `NEEDS_REQUIREMENTS` — brak wymaganych parametrów
- Plik candidates.json nie istnieje → podpowiedź: uruchom candidates najpierw
- Nieprawidłowe candidate_id → błąd + lista dostępnych ID
- GPX nie istnieje → błąd z listą szukanych ścieżek

## Pliki modułu

| Plik | Opis |
|------|------|
| `scripts/lib/route_logistics.py` | Biblioteka: modele, Overpass, bufory, GPX I/O, writery |
| `scripts/route_logistics_candidates.py` | TEMPO 1: wyszukiwanie kandydatów |
| `scripts/route_logistics_commit_poi.py` | TEMPO 2: zatwierdzanie POI |
| `scripts/q/route_logistics` | CLI wrapper |
| `scripts/smoke_route_logistics.py` | Testy smoke (14 testów) |
| `scripts/lib/__init__.py` | Marker pakietu |
