# Projekt: Modyfikacja / naprawa tras (naprawa-trasy.html)

_Status (19.10.2026, sesje naprawa-1910 / router-1910 / router2-1910): WZNOWIONY. Etap 1 wdrożony
(jedna ocena nawierzchni = 5 kategorii z Analizy trasy). Mini-router wdrożony (główny silnik
objazdów w Polsce, Valhalla zapasem). Następnie: Etap 2 ekran nadzoru (makieta w Design),
Etap 3 zapis jako osobna trasa „NAPRAWA" + GPX. Potem wbudowanie w Analizę trasy (ew. Planer wyprawy)._

## Cel

Moduł do NADZOROWANEJ naprawy tras: wykrywa odcinki o złej nawierzchni, proponuje objazdy,
człowiek akceptuje lub odrzuca każdy z nich, a wynik zapisuje się jako osobna trasa
„NAPRAWA" powiązana z oryginałem (nie nowa wersja tej samej trasy — import z Komoota by ją
nadpisał) + plik GPX. Nazwa trasy/pliku do ustalenia (musi zawierać rozpoznawalny `#id`,
bo QExt2 szuka nawierzchni po nazwie).

## Decyzje Michała (19.10.2026)

- Kolejność: najpierw moduł działa funkcjonalnie, potem integracja z Analizą trasy (i może Planerem wyprawy).
- Kandydaci do naprawy: **kat. 5 zawsze, kat. 4 przełącznikiem** (parametr `kat4=1`).
- Wynik: nowa trasa w QBot + GPX, jako osobna trasa „NAPRAWA" (nazwa później).
- Kierunek silnika objazdów: **mini-router na naszej bazie dróg** jako główny, Valhalla tylko
  poza Polską lub gdy nasz router nic nie znajdzie (BRouter nie jest potrzebny).

## Etap 1 — jedna ocena nawierzchni (WDROŻONY 19.10.2026)

`qbot_web.py`:
- `/api/routes/{id}/surface-segments?kat4=0|1` — ryzyko odcinka = `surface_category >= próg`
  (5, z kat4 również 4), te same kategorie co Analiza trasy (`route_surface_category_store`).
  Zwraca `threshold`, per odcinek `category` (najgorsza), `risky_km`, `original_breakdown`
  w kategoriach. Trasa bez 5 kategorii (np. stara 55798129) → **409** „przelicz trasę"
  (strona pokazuje ten komunikat). Kategoryzatora NIE dublujemy w locie.
- `/api/routes/{id}/segments/candidate?...&kat4=0|1` — Valhalla tylko wyznacza drogę; ocena
  objazdu `_detour_surface_categories`: ślad → GPX → silnik nawierzchni (lokalna baza OSM) →
  kontekst WorldCover dla odcinków bez tagu (jak `route_surface_context_store`) →
  `compute_category`. Wcześniejsza ocena kubełkami Valhalli (`trace_attributes`) USUNIĘTA.
  Lepszy kandydat = mniej km złej nawierzchni, przy remisie krótszy. `still_risky` =
  zła nawierzchnia objazdu ≥ 200 m.
- Kotwice na krańcach: promień przed startem / za metą → początek / koniec trasy
  (wcześniej po cichu pomijany albo 404).
- Zapytania do Valhalli z własnym `User-Agent` (`VALHALLA_UA`).

Weryfikacja na żywo: ocena fragmentów tras = kategorie zapisane w Analizie trasy (1:1);
Neverending Bug km 15,3–15,85: 0,55 km kat. 5 → objazd 1,81 km z 0,05 km kat. 5;
odcinek km 0–0,25 dostaje objazd; 55798129 → 409. Czas kandydata 9–11 s (pełna ocena).

## Mini-router (WDROŻONY 19.10.2026, sesja router2-1910)

Moduł `qbot3/routes/route_detour_router.py` (`find_detours`), wołany z endpointu
`/segments/candidate`. Zasady:
- Klasyfikacja drogi = TA SAMA funkcja co silnik nawierzchni (`route_surface_engine._infer_from_tags`)
  + `compute_category` + kontekst WorldCover dla dróg bez danych. ZERO własnych reguł nawierzchni
  (lekcja: własne „unclassified bez tagu = asfalt" dało router 0,22 km vs sędzia 0,7 km złej nawierzchni).
- Obszar +2/+4/+7 km; rośnie tylko gdy objazd nadal zły ORAZ większy obszar poprawia wynik o ≥ 50 m;
  limit 15 000 dróg w obszarze (miasto). Promienie kotwic 0,3/1/2/3 km eskalują na szybkiej ocenie
  routera z tą samą regułą „musi poprawić o ≥ 50 m".
- Do 3 wariantów; wariant pokazywany tylko gdy ≥ 30% jego długości to nowe drogi (kara 2× za drogi
  poprzednich wariantów).
- Ostateczna ocena każdego wariantu: `_detour_surface_categories` (silnik nawierzchni) — sędzia z Analizy trasy.
- Valhalla tylko gdy router nic nie zwróci (poza zasięgiem bazy = poza Polską, brak sieci).
- Zakazy: motorway(+link), `motorroad=yes`, ref S*/A*, schody/perony/budowy/projektowane,
  `bicycle=no|dismount|use_sidepath`, `access=no|private` bez zezwolenia dla rowerów;
  jednokierunkowość (`oneway`, `oneway:bicycle=no`). Krajówek (trunk) NIE wycinamy.
- Odpowiedź endpointu: pola jak wcześniej (najlepszy wariant) + `engine` + `variants[]`
  (coordinates, distance_km, delta_km względem zastępowanego kawałka, source, confidence, still_risky).

Weryfikacja na żywo (19.10, endpoint produkcyjny):
- Bug km 15,3 (kat. 5): 5,4 s; W1 1,84 km (+0,69) **0 km** złej (Valhalla: 0,05); W3 = oryginał (+0,0).
- Bug km 23,0 (kat. 4): 0,8–4 s; 6,47 km, 100% asfalt (Valhalla nic nie znalazła).
- Rembertów km 41,75 (kat. 4): 14,5 s; W1 9,67 km, **0 km** złej (69% kat. 2, 31% kat. 1); router = sędzia.

### Historia testu (19.10.2026, przed wdrożeniem)

Lokalna baza `/opt/qbot/data/osm/roads.sqlite` (Geofabrik, wszystkie drogi `highway`,
pełna geometria, współrzędne zaokrąglone do 7 miejsc) składa się w sieć: skrzyżowania mają
wspólne punkty. Router: drogi z prostokąta wokół odcinka → sieć → koszt = długość ×
waga kategorii (1:1,0 · 2:1,1 · 3:1,4 · 4:3,0 lub 12 przy przełączniku · 5:12) → Dijkstra;
wariant 2 = kara 1,5× za drogę wariantu 1. Kategoria drogi bez tagu MUSI mieć kontekst
WorldCover (bez niego każda goła droga = kat. 5 i router nie widzi objazdów).
Wyniki: Bug km 15,3: 1,81 km / 0,04 km kat. 5 (= Valhalla) w 0,01 s; Rembertów km 41,75
(kat4): 4,99 km, 4,46 km asfaltu, 0,22 km kat. 4; Bug km 23,0: brak lepszej drogi w +2 km.
Do zrobienia: (1) powiększanie obszaru także gdy objazd nadal zły, (2) weryfikacja filtra
zakazów (Rembertów: 854 drogi zablokowane — prawdopodobnie teren wojskowy), (3) poza Polską
Valhalla, (4) ocena przebiegu na mapie (Etap 2).
Filtr zakazów: motorway(+link), `motorroad=yes` (ekspresówki), schody/budowy, `bicycle=no|
dismount|use_sidepath`, `access=no|private` bez zezwolenia dla rowerów. Krajówek (trunk)
NIE wycinamy — rowerem wolno.

## Etap 2 + 3 — ekran nadzoru i zapis trasy NAPRAWA (WDROŻONE 19.10.2026, sesja naprawa3-1910)

Makieta zaakceptowana przez Michała (Design: „Naprawa trasy — ekran nadzoru”). Decyzje:
**tylko komputer** (na iPhonie strona pokazuje komunikat, a przycisk w Analizie trasy jest ukryty);
docelowo część Analizy trasy; nowa trasa po PEŁNYM przeliczeniu trafia do „Udostępnij” → Karoo.

**Strona** `naprawa-trasy.html` (UI2): wybór trasy (`?route=` z Analizy trasy), przełącznik kat. 4,
bilans całej trasy (długość, zła nawierzchnia przed→po, decyzje), lista odcinków ze stanem,
mapa (trasa: dobra/do naprawy, warianty: wybrany/pozostałe), tabela wariantów „było → będzie”
(długość, wydłużenie wzgl. zastępowanego kawałka, zła nawierzchnia, pasek 5 kategorii),
Przyjmij / Zostaw oryginał / Szukaj dalej (większy promień), Zapisz → panel postępu przeliczania.

**Zapis** `POST /api/routes/{id}/repair/save` → `qbot3/routes/route_repair_store.save_repaired_route`:
oryginalny GPX (z wysokością) cięty po km funkcjami Planera (`gpx_splitter`), objazdy wszyte
kotwica–kotwica (wysokość z SRTM30m), kontrola styku objazdu z trasą (≤ 300 m) i nachodzenia;
plik `/opt/qbot/artifacts/exports/rwgps/rwgps_naprawa-<hash8>-<nn>.gpx`, rejestracja
`summarize_rwgps_artifact` + `ensure_route_base` (jak Planer). Nazwa robocza
„<oryginał> · NAPRAWA n” (ostateczna do ustalenia).

**Pochodzenie** w tabeli `qbot_v2.route_repairs` (route_id, parent_route_id, meta_json z objazdami,
precompute_state/jobs). NIE w `route_artifacts.metadata_json` — krok profilu nawierzchni zapisuje
ten rekord na nowo i kasuje dopisane klucze (sprawdzone 19.10).

**Przeliczenie** w tle: `scripts/naprawa_precompute.py` (log `/opt/qbot/artifacts/naprawa_precompute.log`)
wczytuje `/etc/qbot/qbot-api.env` (flagi kroków — bez nich tylko 3 z 7) i woła
`route_precompute_trigger.ensure_route_precompute_trigger` = ta sama ścieżka co import nowej trasy
(profil nawierzchni → route_base → ramki → 7 kroków). Bez profilu krok nawierzchni pada
(„brak profilu nawierzchni”). Telegram po końcu (sukces/błąd). Postęp: `GET /precompute-status`.

**Analiza trasy** (`raport-trasy.html`, osobny skrypt): `GET /repair-info` → zwykła trasa: przycisk
„Napraw trasę” (tylko komputer) + linki do jej napraw; trasa NAPRAWA: zielony pasek „Wersja
naprawiona z trasy X (oryginał bez zmian) · n objazdów · +Δ km · otwórz oryginał”.
„Udostępnij” (GPX z POI, Wyślij na Karoo, mail) działa bez zmian po route_id.

Weryfikacja na żywo: Neverending Bug, objazd W1 km 15,3 → trasa `naprawa-0b1bb1d9-01`
81,82 km (+0,71), przeliczenie 7/7 kroków w 53 s, na liście Analizy trasy, GPX 123 KB;
zrzuty Playwright (komputer, telefon), zero błędów JS. Nieprzetestowane: „Wyślij na Karoo”
(tworzy trasę na koncie Michała — do kliknięcia przez niego).

## Szkic naprawy i zapis z Analizy trasy (WDROŻONE 19.10.2026, sesja szkic-1910)

Decyzja Michała: w oknie NAPRAWA nie zapisujemy trasy (nie widać wpływu na przebieg). Po ustaleniu odcinków
wracamy do Analizy trasy; obok „Napraw trasę” pojawia się ZAPISZ (nowa wersja); na mapie stary i naprawiony
przebieg; zawsze można wejść do „Napraw trasę” i wyłączyć dowolny odcinek. Błąd: przełącznik kat. 4 kasował decyzje.

- Tabela `qbot_v2.route_repair_drafts` (route_id oryginału, kat4, detours jsonb); `route_repair_store.get/put/delete_draft`;
  `GET/PUT/DELETE /api/routes/{id}/repair/draft` (walidacja przebiegu i nachodzenia objazdów).
- „Napraw trasę”: decyzje = lista objazdów w szkicu (zapis automatyczny), NIEZALEŻNA od kat. 4/5 (objazd przypisany
  do odcinka po nakładaniu km); „Zostaw oryginał” usuwa objazd; „Gotowe → wróć do Analizy trasy” zamiast Zapisz.
- Analiza trasy (pływający pasek, mapa przez `qTilesMaps`, bez zmian układu): przy szkicu — „Zapisz naprawioną trasę”
  (POST /repair/save → NAPRAWA n + przeliczenie, postęp w pasku, link do nowej wersji), „Odrzuć szkic”, skrót zmian,
  na mapie stary przebieg (szary przerywany) i naprawiony (fiolet). Szkic zostaje po zapisie (kolejne wersje).
  Na trasie NAPRAWA „Napraw trasę” otwiera szkic oryginału. Liczby w zakładkach dotyczą oryginału do czasu zapisu.
- Weryfikacja Playwright (komoot-3230492853): przyjęcie z kwadratami → szkic na serwerze; kat. 4 wł/wył — decyzja
  zostaje; Analiza trasy: Zapisz/Odrzuć, fioletowy objazd na mapie, zoom 12,4, zero błędów JS.

## Kwadraty, kolory mapy, zakładki promieni (WDROŻONE 19.10.2026, sesja kwadraty-1910)

Decyzje Michała: złe drogi często wynikają z zaliczania kwadratów; kwadrat NIE jest domyślnym
priorytetem — przy odcinku przełącznik „Uwzględnij kwadraty” (domyślnie wył.), bo często
łatanie dziur w kwadratach nie ma znaczenia. Kwadraty widoczne na mapie (wł/wył, jak tło mapy).
Kolory: musi być jasne, jak biegnie nowa trasa. Cofanie do propozycji z mniejszego promienia.

- `qbot3/routes/route_repair_tiles.py`: kafle z14 jak Analiza trasy (`/api/routes/{id}/tiles`,
  cache StatsHunters). Nowe kwadraty kawałka = kafle zastępowanego kawałka − Twoje − kafle reszty
  trasy. Skutek wariantu: zachowane / zgubione / nowe zdobyte — liczony ZAWSZE.
- Router: `find_detours(..., required_tiles=[...])` — etapowy Dijkstra A → dowolny węzeł w kwadracie 1
  → … → B (wjazd w kwadrat wystarcza); obszar obejmuje kwadraty; eskalacja liczy też niezaliczone.
  Przyciąganie kotwic do węzła sieci 150 → 300 m (na długich prostych drogach węzły co kilkaset m —
  router się poddawał i wchodziła Valhalla, która nie zna kwadratów); A/B dopisywane do przebiegu.
- Endpoint kandydata: `squares=1`; odpowiedź `variants[].tiles`, `tiles_new_piece`, `tiles_error`;
  przy `squares` najpierw warianty bez strat kwadratów.
- Strona: przełącznik przy odcinku („ten kawałek zbiera N nowych kwadratów”), plakietka na liście,
  bilans „Nowe kwadraty: przed → po”, kolumna „Kwadraty” w tabeli, warstwa kwadratów (nowe zielone,
  Twoje niebieskie; wymagane — zielona przerywana ramka, zgubione — czerwona) + przyciski „Mapa” /
  „Kwadraty: wł/wył”. Kolory: trasa dobra grafitowa (zieleń ginęła na kwadratach), do naprawy
  czerwona, NOWY PRZEBIEG fioletowy gruby z białym obrysem + punkty A/B, wypadający kawałek czerwony
  przerywany, inne warianty szare kropkowane. „Szukaj dalej” dokłada zakładkę promienia — klik wraca.
- Weryfikacja: komoot-3230492853 km 11,3 (kat. 5, 1 nowy kwadrat): bez kwadratów W1 gubi 1/1;
  z kwadratami 2 warianty 1/1 zachowane, 0 km złej (+0,90 / +3,59 km). Playwright: zakładki,
  cofanie, przyjęcie, bilans, zero błędów JS.

## Kluczowe decyzje architektoniczne (historyczne, 01.07.2026)

1. Lista tras = routes store z policzoną nawierzchnią (`/api/routes/ready`).
2. Dopasowanie nawierzchni do geometrii po kilometrażu (km_from/km_to), nigdy po segment_index.
3. Punkty zakotwiczenia objazdu cofnięte w głąb dobrej nawierzchni.
4. Progresywne próbkowanie promienia (0.3 / 1.0 / 2.0 / 3.0 km).
5. Valhalla `use_roads=0.7`.
6. Brak limitu długości per kandydat (długi objazd OK, jeśli dobra nawierzchnia).
7. „Brak realnej alternatywy" zależy wyłącznie od nawierzchni kandydata.
8. Reguła „przyzwoity grade" — od 19.10 zastąpiona modelem 5 kategorii (tracktype jest w nim).
9. Minimalny zgłaszany problem: 200 m.
10. Bliskie odcinki ryzykowne (< 200 m przerwy) scalane.

Problem „dwóch systemów oceny" (A = nasz, B = Valhalla) z 01.07 — ROZWIĄZANY w Etapie 1
(jedna ocena) i docelowo w mini-routerze (nasz model także wyznacza drogę).

## Znane ograniczenia i dług techniczny

- Detekcja „ślepych zaułków" — fałszywe alarmy; potrzebna metoda nawrotu >150°.
- Szeroki obszar objazdu może zahaczyć sąsiedni zły odcinek — do obsługi w Etapie 2 (bilans całej trasy).
- Brak limitu wydłużenia CAŁEJ trasy — w Etapie 2 bilans na ekranie nadzoru.
- Zapis/zszycie objazdów do trasy — Etap 3.
- Ocena objazdu silnikiem trwa kilka sekund; każdy unikalny objazd zostawia plik w cache silnika.

## Dane testowe

- 55798129 (RWGPS, ~71 km, Brańszczyk Gravel) — stara, bez 5 kategorii (409 do przeliczenia).
- komoot-3340114493 (Neverending Bug, 81 km) — kat. 5 km 15,3–15,85; kat. 4 m.in. km 23,0–24,3.
- komoot-2251353307 (Rembertów, 53,7 km) — kat. 4 m.in. km 41,75–43,25.
