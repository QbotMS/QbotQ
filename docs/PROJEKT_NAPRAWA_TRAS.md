# Projekt: Modyfikacja / naprawa tras (naprawa-trasy.html)

_Status: PAUZA (2026-07-01). Funkcjonalnie działa i jest wdrożone na WEB. Zatrzymane na
zewnętrznej awarii publicznej Valhalli — do dokończenia weryfikacji odcinka z drogą S8,
gdy usługa wróci. Poza tym temat gotowy do podjęcia w dowolnym momencie._

## Cel

Moduł do interaktywnej naprawy tras zaimportowanych z RWGPS: wykrywa odcinki o
ryzykownej/niepewnej nawierzchni (na bazie już istniejącego `route_surface_layer`),
pokazuje je na mapie i w tabeli z uzasadnieniem po polsku, i na żądanie proponuje
lokalny objazd przez publiczny silnik routingu Valhalla — jako podgląd/propozycję do
oceny człowieka, nie automatyczny zapis.

## Co jest wdrożone

**Backend:** `/opt/qbot/app/qbot_web.py` (serwis `qbot-web`, FastAPI, port 30181).
Endpointy:
- `GET /api/routes/ready` — trasy z routes store z zakończonym etapem nawierzchni.
- `GET /api/routes/{id}/geometry` — surowa geometria trasy (bez klasyfikacji).
- `GET /api/routes/{id}/surface-segments` — trasa pocięta na ciągłe odcinki
  dobra/ryzykowna, z numeracją, uzasadnieniem po polsku i rozkładem "było"
  (`original_breakdown`).
- `GET /api/routes/{id}/segments/candidate?km_from=&km_to=` — proponowany objazd
  (Valhalla) + ocena pewności nawierzchni objazdu (Valhalla `trace_attributes`).

**Frontend:** `/opt/qbot/web/public/naprawa-trasy.html` — mapa Leaflet+OSM,
tabela odcinków ryzykownych, przyciski "Nowy kandydat" / "Usuń", numerowane
znaczniki na mapie klikalne (auto-generują kandydata).

**Strona główna:** `/opt/qbot/web/public/index.html` przebudowana na układ kafelkowy
(dziś: raport trasy, modyfikacja tras + dwa miejsca na przyszłe testy).
Dawny testowy raport przeniesiony na `/opt/qbot/web/public/raport-trasy.html`.

## Kluczowe decyzje architektoniczne (chronologicznie)

1. **Lista tras do wyboru = tylko routes store z policzoną nawierzchnią** (Wariant A) —
   nie z RWGPS API na żywo. Napełnianie routes store (webhook + auto-przeżuwanie) to
   osobny, równoległy wątek, poza zakresem tego modułu.

2. **Dopasowanie nawierzchni do geometrii idzie po kilometrażu (km_from/km_to), nigdy
   po segment_index.** `route_axis_segments` (50m, ~1423 wiersze) i
   `route_surface_layer` (odcinki OSM, ~76 wierszy) mają NIEZALEŻNĄ numerację —
   wczesna wersja pomyliła je i klasyfikowała ~95% trasy jako ryzykowną.

3. **Punkty zakotwiczenia objazdu są cofnięte w głąb dobrej nawierzchni** (nie
   dokładnie na granicy ryzykownego odcinka) — inaczej Valhalla musiała wjeżdżać w
   zły fragment tylko po to, żeby dosięgnąć punktu startu objazdu ("wjazd-cofka-wyjazd").

4. **Progresywne próbkowanie promienia** (0.3 / 1.0 / 2.0 / 3.0 km) zamiast jednego
   sztywnego bufora — zatrzymuje się na pierwszym promieniu, który daje dobrą
   nawierzchnię (Valhalla `trace_attributes`, nie zgadywanie).

5. **`use_roads=0.7`** (nie 0.3) w kosztach Valhalli — niższa wartość aktywnie
   odciągała routing od prawdziwych dróg w stronę duktów/ścieżek. Sprawdzone
   eksperymentalnie: `avoid_bad_surfaces` i `bicycle_type` osobno nie miały żadnego
   efektu przy wąskim buforze; `use_roads` miał efekt dopiero przy szerszym buforze,
   gdzie realna droga była fizycznie w zasięgu.

6. **Brak limitu proporcji długości per-kandydat.** Próbowano wdrożyć limit
   "kandydat nie dłuższy niż 115% zastępowanego odcinka" — WYCOFANE. Użytkownik:
   długi objazd (nawet 10 km) jest akceptowalny, jeśli prowadzi dobrą nawierzchnią.
   Jedyne kryterium akceptacji dziś: `still_risky == False` (z `trace_attributes`).
   `replaced_km` (ile oryginalnej trasy między kotwicami zastępuje kandydat) jest
   zwracane w odpowiedzi jako informacja, nie jako filtr.

7. **Flaga "brak realnej alternatywy" zależy WYŁĄCZNIE od jakości nawierzchni
   kandydata**, nie od różnicy dystansu. Wcześniejsza wersja wymagała też
   `abs(delta_km) < 0.3`, co ukrywało przypadki, gdzie Valhalla proponowała DŁUŻSZY
   objazd wciąż w większości po złej nawierzchni (realne przypadki: +0.6 km przy
   78% dirt, +0.73 km przy 90% dirt).

8. **Reguła "przyzwoity grade"**: dla dróg `highway=track`, `tracktype` grade1–4
   ZAWSZE wygrywa nad wywnioskowaną etykietą `surface` (ground/grass) — ryzykowne
   jest wyłącznie: brak tracktype LUB grade5. Dowód: 3 odcinki na trasie testowej
   miały jawny tag `tracktype=grade4` (przyzwoita droga), a mimo to wpadały do
   "ryzykowne" tylko dlatego, że heurystyka nadała im surface=ground/grass.

9. **Minimalna długość zgłaszanego problemu: 200 m.** Odcinki krótsze (widziano
   50–150 m) to szum, nie realny problem dla rowerzysty — nie są już zgłaszane
   jako osobny alert.

10. **Bliskie odcinki ryzykowne (< 200 m przerwy) są scalane** w jeden, żeby
    tabela nie zasypywała mikro-fragmentami.

## Otwarty, nierozwiązany problem systemowy (WAŻNE — do rozstrzygnięcia w sesji "generator tras")

Dwa niezgodne systemy oceny nawierzchni:
- **System A** (nasz, `route_surface_layer` — tagi OSM + reguły projektu) napędza
  raport i alerty.
- **System B** (wewnętrzny model nawierzchni Valhalli) napędza objazdy.

Sprawdzone na żywo (trasa 55798129, okno 10–17.75 km): 53% odcinka ma jawny tag OSM
`surface=*`, 47% jest wywnioskowane. Realny `dirt` z jawnym tagiem to tylko 0.10 km
(1%), a Valhalla mimo to raportuje ~60% "dirt" dla tego samego odcinka. System A jest
bliżej prawdy wszędzie, gdzie stoi na jawnym tagu OSM.

**Zalecana reguła dla przyszłego generatora tras** (NIE wdrożona jeszcze jako
osobna logika w tym module — dziś objazd po prostu ufa Valhalli/System B):
autorytet nawierzchni nie "A albo B", tylko wg obecności jawnego tagu OSM pod
segmentem. Segment z tagiem → A wygrywa. Segment bez tagu → uczciwa szara strefa,
ostrożność Valhalli ma sens.

**Niezweryfikowane:** czy powyższe reguły (tag-wins, grade1-4-zawsze-ok) trzymają
się na innych trasach niż testowa 55798129.

## Znane ograniczenia i dług techniczny

- Detekcja "ślepych zaułków" (trasa robi zawrócenie w środku odcinka) — prosty test
  stosunku odległości prostej do długości ścieżki daje fałszywe alarmy (np. seg. 13
  na trasie testowej ma zawrócenie w środku, ale realny objazd i tak działa dobrze).
  Potrzebna dokładniejsza metoda (np. wykrywanie faktycznego nawrotu >150° w
  geometrii) przed automatyzacją.
- Przy gęstych, blisko siebie położonych odcinkach ryzykownych, szeroki bufor
  zakotwiczenia (do 3km) może teoretycznie wejść w sąsiedni zły odcinek —
  niezabezpieczone.
- Największy promień eskalacji może wypaść tuż za końcem trasy (np. 71.35km przy
  trasie 71.14km) i po cichu się pomija zamiast policzyć do samego końca.
- **Cap na CAŁKOWITĄ długość całej trasy** (nie pojedynczego kandydata) — jeśli
  suma zaakceptowanych objazdów znacząco wydłuża całą trasę, trzeba to jakoś
  ograniczyć/sygnalizować. To PRZYSZŁE zadanie, nie teraz.
- Moduł to na razie czysty PODGLĄD — nie ma mechanizmu zapisu/zszycia zaakceptowanego
  objazdu z powrotem do trasy (eksport nowej, złożonej trasy). To naturalny
  następny krok, niezbudowany.
- Zależność od publicznego, darmowego serwera Valhalli (`valhalla1.openstreetmap.de`)
  bez gwarancji dostępności — 2026-07-01 serwer miał przejściową awarię (nginx 502,
  proces Valhalli niedostępny, nie rate-limit z naszej strony — zweryfikowane po
  treści odpowiedzi błędu). Odcinek "11" (w okolicy drogi S8) czeka na ponowną
  weryfikację po powrocie usługi — hipoteza (niepotwierdzona): S8 to droga
  ekspresowa, Valhalla może strukturalnie zabraniać na niej ruchu rowerowego.

## Dane testowe

Trasa 55798129 (RWGPS, ~71km, Brańszczyk Gravel) — celowo ułożona po niepewnych
drogach pod zbieranie kwadratów StatsHunters, stąd realna trudność jest oczekiwana,
nie jest artefaktem błędu.
