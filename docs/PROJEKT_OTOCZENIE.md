# WARSTWA OTOCZENIA TRASY (route_shade_layer) — dokumentacja

Status: zbudowane i zweryfikowane na trasie 55798129. Domyślnie WYŁĄCZONE w precompute
(flaga `QBOT_ROUTE_SHADE_ENABLED`). Niezacommitowane (czeka na restart DC). Data: 2026-06-30.

---

## 1. PO CO (cel)

Warstwa opisuje, **co otacza drogę w przekroju** w każdym węźle osi trasy: po której stronie
jest las, a po której pole/zabudowa — wraz z kierunkiem jazdy. To jest wsad pod **cień w analizie
cieplnej (WBGT)**: mając klasę pokrycia po lewej/prawej i azymut słońca o godzinie przejazdu,
konsument sam rozstrzyga, czy rowerzysta jedzie w cieniu, czy w pełnym słońcu. Wtórnie: materiał
pod ocenę otoczenia/nawierzchni (np. „droga leśna" vs „odkryta polna").

Kluczowa rzecz, której stara warstwa nie umiała: **droga na SKRAJU lasu**. Pojedyncza próbka na
osi widzi „las" albo „pole", a realnie liczy się, że las jest po JEDNEJ stronie. Stąd przekrój.

---

## 2. SKĄD (źródło danych) — i dlaczego nie OSM

**Źródło: ESA WorldCover v200 (rok 2021), raster 10 m, 11 klas pokrycia terenu.**
- Licencja: CC-BY (darmowe, do użytku z atrybucją).
- Hosting: publiczny bucket AWS `s3://esa-worldcover` (host `esa-worldcover.s3.eu-central-1.amazonaws.com`),
  anonimowo, jako COG (Cloud-Optimized GeoTIFF).
- Kafle 3°×3°, nazwa po lewym-dolnym rogu: `NxxExxx` (np. nasz rejon = `N51E021`), ~70–100 MB/kafel.
- Każdy piksel ma przypisaną klasę — **brak dziur**.

**Dlaczego WorldCover, a nie OSM (poprzednie źródło):**
OSM land-cover dawał ~53% trasy oznaczone jako „teren otwarty", co w rzeczywistości znaczyło
„BRAK poligonu w OSM" (nieznane), a nie „potwierdzone pole". Przyczyny: tag opcjonalny, pomijane
relacje multipolygon, próbkowanie tylko po osi co 80 m. Efekt: na tej samej trasie OSM pokazywał
30% drzew, WorldCover 57% — OSM ukrywał połowę cienia. WorldCover klasyfikuje każdy piksel, więc
„nieznane" znika. OSM zostaje jako legacy/fallback tam, gdzie WorldCover nie pokrywa (patrz §7).

11 klas (kod → pl): 10 drzewa · 20 zarośla · 30 trawy · 40 uprawy · 50 zabudowa · 60 goły grunt ·
70 śnieg/lód · 80 woda · 90 mokradła · 95 namorzyny · 100 mchy/porosty. Słownik w tabeli
`qbot_v2.worldcover_classes` (kod, name_pl, name_en, is_tree) — surowe kody same się tłumaczą JOIN-em.

---

## 3. GDZIE (gdzie to żyje) — kod, baza, cache, wpięcie

**Kod (qbot3/routes/):**
- `worldcover_tiles.py` — menedżer cache kafli + CLI. Funkcje: `tile_name(lat,lon)`, `ensure_tile`
  (pobiera z AWS jeśli brak, atomowo, indeksuje), `touch_tile` (LRU), `tiles_for_bbox`, `prune`,
  `geocode_label` (Nominatim — ludzka nazwa kafla), CLI: `status / where LAT LON / get TILE /
  name TILE [label] / rm TILE [--dry-run] / prune [--max-gb X|--older-than DNI] [--dry-run]`.
- `route_shade_store.py` — writer `ensure_route_shade(*, route_id=None, route_base_id=None) -> dict`.
  Otwiera własne połączenie do bazy. Zwraca m.in. `shade_layer_count`, `coverage_pct`, `tiles_used`,
  `tiles_missing`.

**Schemat (sql/):**
- `route_shade_store_v1.sql` — tworzy `worldcover_classes` (legenda) + `route_shade_layer`.

**Baza (qbot_v2):**
- `route_shade_layer` — dziecko `route_base` (FK ON DELETE CASCADE), 1:1 z `route_axis_segments`
  (siatka ~50 m). Kolumny: `route_base_id`, `route_version_key`, `segment_index`, `heading_deg`,
  `class_center`, `class_left_10`, `class_left_20`, `class_right_10`, `class_right_20`,
  `n_valid` (ile z 5 pikseli odczytano), `source` (`worldcover_v200_2021`), `tile` (użyty kafel),
  `coverage_status` (`ok`/`partial`/`missing`/`unknown`), `meta_json` (lat/lon węzła, offsety),
  `created_at`, `updated_at`. UNIQUE(`route_base_id`, `segment_index`). Indeksy na base_id,
  version_key, (base_id,segment_index), coverage_status, class_center.

**Cache kafli na dysku:**
- `/opt/qbot/app/data/worldcover/` + `index.json` (śledzi rozmiar, datę pobrania, ostatnie użycie,
  etykietę). LRU + `prune`. Kafel pobierany RAZ na region i reużywany.

**Wpięcie w precompute:**
- `route_precompute_orchestrator.py` — `SHADE_JOB = ("route_shade", ensure_route_shade,
  "shade_layer_count")`, dokładany do sekwencji TYLKO gdy flaga `QBOT_ROUTE_SHADE_ENABLED` ustawiona.
  Domyślnie sekwencja bez zmian: `[route_base, route_surface, route_landcover, route_poi]`.

---

## 4. JAK DZIAŁA (mechanika)

1. Z `route_axis_segments` (siatka 50 m, `AXIS_SAMPLE_M=50`) bierze dla każdego węzła punkt środkowy
   i końce odcinka → liczy `heading_deg` (kierunek jazdy) i wektory prostopadłe lewo/prawo.
2. W każdym węźle próbkuje **5 punktów przekroju** prostopadle do jazdy:
   `class_left_20, class_left_10, class_center, class_right_10, class_right_20`
   (offsety ±10 i ±20 m; piksel WorldCover = 10 m, więc gęściej byłoby redundantne).
3. `_TileReader` czyta okno bbox trasy z każdego potrzebnego (cache'owanego) kafla RAZ do pamięci,
   potem próbkuje w pamięci — bez odczytu piksel-po-pikselu z dysku.
4. Zapisuje **wyłącznie surowe kody klas + heading**. `coverage_status`: `ok` (5/5), `partial`,
   `missing` (0/5 → fallback do OSM).

Wynik weryfikacji (55798129): 1423 węzły, pokrycie ~100%, asymetria stron poprawna
(np. droga ze ścianą lasu po jednej stronie: jedna strona „drzewa", druga „trawy").

---

## 5. DLACZEGO TAK (decyzje projektowe)

- **Tylko surowe klasy, ZERO pochodnych** (żadnego „osłona %", „cień", werdyktów). Interpretację robi
  konsument: WBGT liczy cień wzgl. słońca z heading + klas stron + azymutu słońca o danej godzinie;
  ocena nawierzchni weźmie z tego swoje. Jedna warstwa, wielu konsumentów, brak zaszytych założeń.
- **Przekrój 5 punktów, nie pojedyncza oś** — bo decyduje strona (droga na skraju lasu). To był
  powód istnienia tej warstwy.
- **50 m / ±10 / ±20 m** — 50 m dziedziczone z osi kanonicznej; offsety dobrane do piksela 10 m
  (pas ±20 m pokrywa typową szerokość drogi + przydrożny pas).
- **Cache kafli** — pobranie raz na region (3°×3°), reużycie na kolejnych trasach.
- **Flaga, domyślnie OFF** — warstwa wchodzi do precompute dopiero świadomie (flip flagi + restart
  qbot-api), żeby nie zmieniać istniejącego potoku bez decyzji.

---

## 6. CO ODRZUCONO I DLACZEGO (żeby nikt nie odtwarzał)

**Wysokość drzew (Meta/WRI 1 m canopy height) — zbudowane i USUNIĘTE 2026-06-30.**

Próbowaliśmy dołożyć do tego samego przekroju wysokość koron (5 kolumn `canopy_*`) z Meta/WRI 1 m
(AWS `s3://dataforgood-fb-data/...`, kafle po QuadKey). Działało (100% pokrycia, sensowne wartości),
ale **wyrzucone z rozmysłem**:

- **Zły reżim.** Jedyny konsument to WBGT = **lato + wysokie słońce**. Latem w południe słońce stoi
  ~60° → cień ≈ 0,6 × wysokość: 4 m krzaki rzucają ~2,5 m (do drogi nie dojdą), a żeby cień sięgnął
  jezdni ~10 m w bok, korona musi stać praktycznie na skraju OD STRONY SŁOŃCA. W tym reżimie decyduje
  **„czy las jest przy drodze po stronie słońca" (klasa + przekrój) + azymut słońca**, a nie przeciętna
  wysokość. Wysokość dokłada się tylko w wąskim pasku przypadków.
- **Źle policzona dla tego celu.** Trzymaliśmy wysokość uśrednioną do 10 m, a uśrednianie rozmywa
  właśnie krawędź las/luka, która przesądza, czy czubek cienia ląduje na asfalcie.
- **Ciężki ingest.** Plik Meta to ~493 MB/kafel, 1 m, BEZ piramidy podglądów → ~90 s i ~1 GB na trasę.
- **Wartość po innej stronie.** Wysokość ma sens przy NISKIM słońcu (wiosna/jesień, rano/wieczór,
  długie cienie) — to całoroczny feels-like (UTCI / temp. operacyjna, TASK 23), NIE WBGT.

Wniosek: gdyby kiedyś robić indeks niskiego słońca, najpierw klasa + geometria słońca, a wysokość
co najwyżej zgrubnie (wysoki las / nie), i raczej z jednorazowego downsampla całego kafla do 10 m,
nie z ciężkiego odczytu per trasa. Na dziś: niepotrzebne, więc usunięte (kod, kolumny, moduł).

**Cień TERENU (rzeźba, grzbiety zasłaniające słońce)** — to NIE warstwa otoczenia, tylko element
WBGT (analiza pod słońce). Zapisane jako osobne TODO przy TASK 22 (źródło: Copernicus DEM GLO-30,
metoda kątów horyzontu). Tu świadomie nieobecne.

---

## 7. STAN / CZEGO JESZCZE NIE MA (uczciwie)

- Flaga `QBOT_ROUTE_SHADE_ENABLED` **wyłączona** — warstwa nie liczy się w precompute, dopóki nie
  zostanie włączona + restart qbot-api.
- **Konsument niewpięty.** Docelowo read-path (raport / `route_canonical_read`) ma preferować
  shade_layer, a OSM land-cover zdegradować do fallbacku tam, gdzie `coverage_status='missing'`.
  Jeszcze nie zrobione.
- **Niezacommitowane** (blокада: zawieszony connector Desktop Commander; commit jako qbot + naprawa
  własności `.git`/plików czeka na restart DC).
- Pliki warstwy: `qbot3/routes/worldcover_tiles.py`, `qbot3/routes/route_shade_store.py`,
  `sql/route_shade_store_v1.sql`, wpięcie w `route_precompute_orchestrator.py`.
