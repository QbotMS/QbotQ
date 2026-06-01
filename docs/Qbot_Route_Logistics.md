# QBot Route Logistics

Dwutaktowy system wyszukiwania i zatwierdzania POI przy trasach rowerowych.

## Architektura

```
TEMPO 1 — CANDIDATES                    TEMPO 2 — COMMIT-POI
─────────────────────────               ────────────────────────
GPX + Overpass                           candidates.json
    │                                         │
    ▼                                         ▼
candidates.json ◄── ręczny wybór ───►   selected_poi.json
candidates.geojson                       selected_poi.geojson
candidates.md                            selected_poi.gpx
candidates.xlsx                          poi_commit_summary.md
debug.json
```

**Zasada:** Candidates ≠ POI. Do GPX trafiają wyłącznie ręcznie zatwierdzone POI.

## Komendy CLI

```bash
# TEMPO 1 — szukaj kandydatów
python3 scripts/route_logistics_candidates.py --route-id 55395119 --mode full
python3 scripts/route_logistics_candidates.py --route-id 55401067 --mode attractions
python3 scripts/route_logistics_candidates.py --route-id 55395119 --mode lodging --require '{"people":2,"budget":150}'

# TEMPO 2 — zatwierdź POI
python3 scripts/route_logistics_commit_poi.py --route-id 55395119 --select food_001,water_003
python3 scripts/route_logistics_commit_poi.py --route-id 55395119 --select food_001 water_003

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
| `selected_poi.json` | 2 | JSON contract POI_READY_FOR_IMPORT |
| `selected_poi.geojson` | 2 | GeoJSON tylko selected |
| `selected_poi.gpx` | 2 | GPX \<wpt\> tylko selected |
| `poi_commit_summary.md` | 2 | Raport commita |

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
