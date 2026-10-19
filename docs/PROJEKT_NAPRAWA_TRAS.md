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
