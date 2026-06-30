# Analiza przewyższeń i podjazdów trasy (2C)

> Podsystem `route_elevation_engine` + `route_elevation_store`. Decyzje i kalibracja: wpisy „2C …" w `docs/DECISIONS.md`. Stan: wdrożone 2026-06-30, w orchestratorze domyślnie wyłączone.

## Po co to jest
Dla zaplanowanej trasy liczymy gęsty profil wysokości i wykrywamy podjazdy — tak, żeby raport mógł pokazać nie tylko „ile metrów w górę", ale też **gdzie są podjazdy i czy w środku są ścianki**. Celem jest ujęcie zbliżone do tego, co pokazuje Hammerhead Karoo (Climber).

## Skąd biorą się dane wysokości
- **Źródło: opentopodata SRTM30m** — ta sama rodzina DEM, na której stoi Karoo (SRTM/GMTED/3DEP). Dzięki temu wynik jest blisko tego, co policzy licznik.
- **RWGPS nie daje podjazdów** — z trasy RWGPS mamy tylko sumę przewyższeń, gęsty ślad i nawierzchnię; listy podjazdów tam nie ma.
- **Valhalla `/height` jest niedostępna** — publiczna instancja zwraca puste wysokości wszędzie (też w Alpach), zweryfikowane 2026-06-30. Nieużywana.
- Karoo i tak dostaje trasę jako GPX i liczy podjazdy sam na urządzeniu — nie ma gotowca do podebrania.

## Jak liczymy
- **Siatka 50 m** wzdłuż trasy (wspólna z warstwą nawierzchni).
- **Surowy profil** (wysokość co 50 m) trzymamy wiernie — to fundament analityczny.
- **Dwa lokalne okna wygładzania** (nie globalne — globalne spłaszczyłoby ścianki):
  - **~200 m** do **sumy przewyższeń** — wyznaczone empirycznie pod barometr (surowy SRTM 50 m zawyża i robi fantomy). Na trasie 55798129 daje ~427 m vs 403 m z RWGPS.
  - **~100 m** do **detekcji granic podjazdów i ścianek** — okno 200 m przesuwa pozorny szczyt o ~pół okna i sztucznie wydłużałoby krótkie podjazdy.
- **Progi Karoo:** podjazd to odcinek **≥ 400 m** o średnim nachyleniu **≥ 3%**.
- **Podjazd dwupoziomowo:**
  - **nagłówek** — start, koniec, długość, przewyższenie, średnie i maksymalne nachylenie, „severity",
  - **segmenty 100 m** — każdy z własnym gradientem i kategorią stromości (`lagodny`/`umiarkowany`/`stromy`/`bardzo_stromy`). To one pokazują, czy „średnie 5%" to równy podjazd, czy 3% z wstawkami 9-procentowych ścianek.
- Precyzja do metra i do 0,1% jest świadomie nieistotna — liczy się sygnatura podjazdu i profil ścianek, nie to czy ma 120 czy 140 m.

## Co ląduje w bazie (`qbot_v2`)
Obie tabele to dzieci `route_base` (`ON DELETE CASCADE`), niosą `route_version_key`. DDL: `sql/route_elevation_store_v1.sql`.
- **`route_elevation_samples`** — gęsty profil, 1 wiersz na węzeł 50 m (`elevation_m` surowy, `source`, `smoothing_version`). `UNIQUE (route_base_id, sample_index)`.
- **`route_climb_events`** — nagłówek podjazdu + **segmenty 100 m jako `segments_json`** (JSON, nie osobna tabela). `UNIQUE (route_base_id, event_index)`.

## Jak uruchomić
- Funkcja: `ensure_route_elevation(route_base_id=… | route_id=…)` z `qbot3/routes/route_elevation_store.py`.
- CLI (z dowodem idempotencji): uruchomienie z `route_id` i `--repeat 2` — dwa przebiegi muszą dać **identyczny `content_hash`**.
- W orchestratorze precompute: job `route_elevation` jest **za bramką** `QBOT_ROUTE_ELEVATION_ENABLED` (domyślnie `0`). Przy `0` orchestrator zachowuje się jak wcześniej (job nie wchodzi do sekwencji).

## Idempotencja
Profil — upsert po `(route_base_id, sample_index)` (liczba węzłów stała dla wersji). Podjazdy — `delete + insert` dla `route_base_id` (liczba zmienna między przeliczeniami), wszystko w jednej transakcji. Dowód: powtórny zapis daje identyczną zawartość (hash z odczytu z bazy).

## Kalibracja (metoda powtarzalna)
Okno wygładzania i progi stroimy porównując **ramka po ramce** wysokość z urządzenia (`activity_record`, 1 Hz, barometr) z SRTM na **górzystych** przejechanych jazdach (Castagneto, Suchedniów, Skarżysko). Wynik: duże podjazdy zawsze się pokrywają; ascent najbliżej barometru przy oknie ~150–250 m → przyjęte ~200 m.

## Ograniczenia (uczciwie)
- SRTM jest strojony pod barometr (fizyczna prawda przejazdu). Karoo używa SRTM, ale z własnym, nieznanym wygładzaniem — zgodność jest **bliska, nie co do metra**.
- Pokrycie podjazdów względem urządzenia nie jest 100% w obie strony; różnice są na granicznych podjazdach, nie na dużych.
- opentopodata ma limity (1000/dobę, 1/s, 100 punktów/zapytanie) — na jedną trasę ~7 zapytań wystarcza; przy masowym backfillu trzeba cache albo własnej instancji SRTM.

## Pliki
- Silnik (czysta logika, bez DB): `qbot3/routes/route_elevation_engine.py`
- Writer/store + CLI: `qbot3/routes/route_elevation_store.py`
- DDL: `sql/route_elevation_store_v1.sql`
- Testy offline: `tests/test_route_elevation_engine.py`, `tests/test_route_elevation_store.py`
- Wpięcie (wyłączone): `qbot3/routes/route_precompute_orchestrator.py`

## Granice
Podsystem zasila tylko dwie tabele. Nie przepina raportu trasy, nie zmienia `route_analysis_run`, nie dodaje publicznych narzędzi Alberta. Integracja z samym raportem (read-path) to osobny krok.

Aktualizacja 2026-06-30: route_report może teraz czytać canonical `route_elevation_samples` i `route_climb_events` addytywnie jako sekcję „profil wysokości / podjazdy", ale bez zmiany algorytmu wyceny czasu ani legacy sekcji A3/A8.
