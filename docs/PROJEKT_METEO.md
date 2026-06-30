# PROJEKT: Model meteo QBota (WBGT + odczuwalne/UTCI + pogoda a czas jazdy)

> Jeden dokument startowy dla NOWEJ SESJI. Stan na 2026-06-30.
> Szczegóły i dowody: docs exchange CURRENT.md (wpisy TASK 22, TASK 23, „B4-v2 — POGODA…", decyzje 2026-06-30) oraz docs/DECISIONS.md.
> Konwencja pracy: po polsku, bez spekulacji, „bez dowodu nie ma sukcesu", weryfikacja jako qbot, .bak przed zmianą.

## ZAKRES SILNIKA METEO — aktualizacja 2026-06-30 (sesja weryfikacyjna)
> Ta sekcja NADPISUJE wcześniejsze ujęcie „tylko WBGT". Wątki 1–3 poniżej to detale trybu UPAŁ.

### Jeden silnik, wiele trybów
Nie budujemy osobnych projektów na upał/opad/burzę/wiatr. Jeden SILNIK METEO; zagrożenia to jego TRYBY,
dzielące wspólny szkielet: oś trasy (segmenty + km + przewyższenie) × ETA per segment (model czasu) ×
Open-Meteo (godzinowo) × wzorzec alertu „najgorsze ciągłe okno".
Tryby: (1) UPAŁ [najdalej; WBGT + cień + przewyższenie], (2) WIATR [route_weather._rel_wind, m/s, gotowe],
(3) OPAD [Open-Meteo], (4) BURZA [proxy CAPE/kod/porywy, stopniowana z twardym sufitem NO-GO],
w tle (5) ODCZUWALNE/ZIMNO [UTCI/operacyjna = Wątek 2, NIE zbudowane].

### Granica QBot vs QExt2 (ważne — nie mieszać)
- QBot = analiza/plan trasy: OSTRZEGA i doradza (kiedy gorąco, gdzie się nakłada, sugestia startu, plan picia).
- „Heat-optimal power per segment" (rozpiska mocy / wskazania dynamiczne na żywo) → QExt2 / Karoo, NIE QBot.
  Model bilansu cieplnego policzony i działa jako dowód fizyki; w QBocie służy tylko jako UZASADNIENIE alertów,
  nie jako reżyser mocy.

### Jedno źródło prawdy
Jeden przebieg silnika → tabela co 30 min (per okno: zakres km, WBGT, Feel, opad, wiatr-vs-kierunek, burza,
dominujące ryzyko). LLM i wszystkie odczyty (tekst, WEB) biorą dane Z TEJ TABELI — nic nie liczone osobno obok
(lekcja z diagnozy raportu: sekcje w izolacji = sprzeczności i fałszywa pewność).
ALE: analiza WBGT / punktów krytycznych liczona na PEŁNEJ rozdzielczości (~50 m / per segment), nie z okien 30 min
— inaczej gubimy iglice (dowiedzione na makiecie). Zasada: licz gęsto, pokazuj rzadziej, alerty z gęstego.

### Produkty
- TEKST (teraz): alerty z ciągłej ekspozycji („X min nieprzerwanie w 'bardzo wysoka', km A–B, ~godz."),
  SUGESTIA STARTU (przelicz kilka godzin startu, wybierz najlepsze okno względem WSZYSTKICH trybów —
  np. burza o 14:00 to twarde ograniczenie, nie miękki koszt), lekki plan picia (z masy ciała). + alert_level jako flaga.
- WEB (kolejny krok): dwie krzywe — temperatura termometr + WBGT — plus skala zagrożenia. Bez osobnej warstwy lasu
  (cień siedzi już w WBGT; rysowanie lasu = przyczyna zamiast skutku).

### Źródło danych
Open-Meteo, tryb best_match (dla PL wybiera ICON-D2/ICON-EU na krótki termin — najlepsze na burze, globalne dalej).
ECMWF dostępny w Open-Meteo gdyby trzeba (open-data od 2025-10). Radiacja (shortwave+direct) w tym samym zapytaniu
— powód, dla którego NIE OpenWeatherMap (tam radiacja to osobny płatny produkt, a „ECMWF" to tylko dane referencyjne).
Opcjonalnie: rozjazd modeli jako sygnał pewności.

### Zrobione dziś (2026-06-30, zacommitowane jako qbot)
- solar_azimuth_deg w qbot_wbgt_tools.py (solver nietknięty — dowód z diff).
- qbot3/routes/route_shade_resolver.py: segment_tau() — reguła cienia oparta na danych trasy 55798129
  (cień = klasa 10 drzewa; oba boki/środek → fdir×0.10 prześwit; jeden bok → azymut + taper wysokości;
  zabudowa = brak cienia; cossza<CZA_MIN = pomiń; chmury obsłużone, bo tau mnoży fdir_base z radiacji z chmurami).

### NIE zbudowane (kolejka)
Feel/UTCI (Wątek 2); join „segment→godzina" + fdir_eff do solvera (silnik WBGT-w-czasie); pola alert_level/surface;
tryby opad/burza + wiatr-jako-alert; tabela 30-min; sugestia startu; plan picia z masy.

## Cel projektu
Dać QBotowi spójny, rowerowy obraz warunków atmosferycznych dla trasy:
(a) ryzyko cieplne (WBGT), (b) całoroczne odczuwalne ze słońcem (UTCI / temperatura operacyjna),
(c) świadomą decyzję, czy i jak pogoda wpływa na czas jazdy.
Tani screen bramkuje drogą analizę; wszystko uczciwe co do pewności prognozy.

## Zasady nadrzędne (wiążące dla całego projektu)
- Wiatr ZAWSZE w m/s (nie km/h).
- Pogoda to NAKŁADKA zależna od czasu startu (overlay w route_analysis_run), NIE cecha trasy.
- Pogoda NIE wchodzi do modelu prędkości/czasu (decyzja 2026-06-30) — patrz Wątek 3.
- Liczenie WBGT/UTCI jest tanie → bramkuj ESKALACJĘ/pokazanie, nie samo liczenie.
- Rowerowo = wiatr EFEKTYWNY (otoczenie + pozorny ~7–8 m/s przy 25–30 km/h), nie sam stacyjny.
- Horyzont zaufania prognozy ograniczony; nie udawać precyzji, której nie ma.

## Wątek 1 — WBGT (stres cieplny) [NARZĘDZIE GOTOWE + ZAREJESTROWANE I W PROMPCIE, integracja TODO]
Stan: `qbot_wbgt_tools.py` żywe i zarejestrowane jako `route_wbgt` (Liljegren 2008, solver vendored; źródło Open-Meteo
— jedyne z darmową radiacją; wiatr m/s; strefy ACSM). Działa end-to-end z VPS.

Dług do domknięcia — ZAMKNIĘTY 2026-06-30 (zweryfikowane na żywym kodzie):
- ZROBIONE: wpis o `route_wbgt` JEST w prompcie Alberta (`_SYSTEM` w qbot3/llm/albert.py, ~linia 205) — param lat/lon/date/from/to, strefy ACSM, okno przejazdu, „pokaż analysis w całości".
- ZROBIONE: zarejestrowane w qbot3/tool_registry.py (route_wbgt → _load_route_wbgt_tool).
- ZROBIONE: zacommitowane — qbot_wbgt_tools.py śledzony i czysty (nie pojawia się w `git status`).

TODO — wpięcie w analizę trasy (projekt zamknięty koncepcyjnie, kod NIE zaczęty), bramkowane warstwowo:
- TIER 0 (darmowy): jeśli prognoza Tmax < ~20°C → pomiń WBGT całkowicie.
- TIER 1 (tani, 1 zapytanie): WBGT w 1 punkcie rozłożony na OKNIE PRZEJAZDU (start + tempo z modelu czasu → godzina na km).
  Wymaga: (a) join „segment → godzina" (route_time_estimate × szereg WBGT); (b) dodać do route_wbgt pole maszynowe
  `alert_level` (0–4) + `surface:bool`, by raport/planner decydował bez parsowania polskich stringów; (c) próg/politykę
  trzymać POZA fizycznym toolem (orkiestracja/planning_fact — regulowalne, personalizowane).
- TIER 2 (tylko gdy Tier 1 zaskoczy ORAZ trasa ma kontrast ekspozycji): WBGT per segment, podając TEMU SAMEMU solverowi
  lokalnie skorygowane wejścia (NIE nową pogodę): cień (las/wood z landcover → fdir≈0), odkryte/asfalt = baseline,
  bliskość wody → bump wilgotności. Wymaga ziarnistości klas landcover (zależność — patrz „Blokery").
- WIATR EFEKTYWNY dla Tier 2: do solvera podać wiatr otoczenia (wektor) złożony z pozornym (prędkość gruntowa z modelu
  czasu + heading), nie sam stacyjny. Na wolnym stromym podjeździe w bezwietrze pozorny→0 PRZY maks. produkcji ciepła
  = realna kulminacja ryzyka. Spina się z narracją „pod wiatr w lesie ≠ pod wiatr po asfalcie".

TODO — wizualizacja w raporcie web (albert.cytr.us): wykres WBGT-w-czasie w sekcji „strategia w czasie".
Preferencja: SVG generowany w Pythonie i wstrzykiwany jak mapa (bez JS/CDN, wchodzi w PDF) albo Chart.js inline.
NIE robić wykresu danych jako PNG. UWAGA: /opt/qbot/web/ jest POZA safe-root DEV → edycja przez Desktop Commander po SSH.

Horyzont zaufania prognozy WBGT: twarde okno ~3 dni; +4–7 tylko trend; >15 dni brak danych. WBGT degraduje się jako
prognoza SZYBCIEJ niż sama temperatura (wilgoć + radiacja = zmienne najtrudniej przewidywalne).

## Wątek 2 — Odczuwalne całoroczne / UTCI [NIE ZACZĘTE] (był TASK 23)
Problem: WBGT to TYLKO upał (radiacja waży 20%, asymetryczny — tłumi słońce). Przy ~15°C w słońcu pokaże „niskie",
choć na skórze grzeje jak 25–30°C. Nie naciągać WBGT do feels-like — to OSOBNE narzędzie.

Składnik już liczony: `solve_globe()` zwraca temperaturę kuli Tg ≈ średnia temperatura promieniowania (Tmrt), po czym
ją PORZUCA. Krok 0: zwracać Tg/Tmrt obok WBGT.

Trzy poziomy (tani → docelowy):
1. Temperatura operacyjna To = (h_c·Ta + h_r·Tmrt)/(h_c+h_r) — liczalna od ręki z danych, które już mamy.
2. UTCI (DOCELOWE, standard outdoor): wielomian Bröde 2012, czysty Python, ZWENDOROWAĆ jak solver Liljegrena.
   Wejścia = to co już pobieramy (Ta, RH, wiatr, Tmrt z radiacji). Symetryczny (chłód i upał).
3. NIE OWM feels_like (brak słońca), NIE wind chill (tylko zimno).
Rowerowo: też wiatr efektywny. Caveat: indeksy zakładają referencyjny ubiór/metabolizm → wartość poglądowa, kierunek poprawny.
Architektura: dwa komplementarne odczyty bramkowane reżimem — WBGT (ciepła połowa) + UTCI/operacyjna (całoroczny feels-like).
Reużywają tej samej radiacji i Tg.

## Wątek 3 — Pogoda a CZAS jazdy [DECYZJA: POZA modelem; warunki powrotu]
DECYZJA 2026-06-30: pogoda NIE wchodzi do route_time_estimate v2 — ani temperatura, ani wiatr.
Dowód (7 jazd ref): temperatura w komforcie 8–28°C bez mierzalnego wpływu (Pearson r=−0.14); wiatr czytelny dopiero przy
silnym opozycyjnym ≥3–4 m/s (~6–9% wolniej), reszta w szumie (r=−0.56, n=7). Pogoda zostaje DORADCZO w prognozie planu
(`route_weather.py` liczy składową czołową per pudełko).
WARUNKI POWROTU (czego brakuje, by skalibrować):
- Kara cieplna >~30°C: wymaga UPALNYCH jazd w próbce (teraz brak).
- Realne „prawo wiatru": więcej WIETRZNYCH jazd + kontrola mocy + lepszy wiatr (rider-level/multi-point) + parowanie
  czoło-vs-plecy wewnątrz jazd. Przyczyny obecnego szumu: kompensacja mocą, wiatr 10 m otwarte ≠ osłonięty gravel,
  pętle (czoło/plecy się znoszą).

## Gdzie to żyje (architektura)
- Konsument: `route_analysis_run` — pogoda/WBGT/cold-risk jako OVERLAY zależny od `start_time` (DECISIONS.md).
- Znormalizowane segmentowe overlaye pogody/WBGT/cold-risk = odłożone do Fazy 2B/2C route store (DECISIONS.md).
- Advisory dziś: `route_weather.py` (OWM primary + Open-Meteo fallback; per pudełko temp/opady/wiatr + składowa względem
  kierunku jazdy; `_rel_wind`). Key OPENWEATHERMAP_API_KEY w .env.local.

## Narzędzia i dane (gotowe klocki)
- `qbot_wbgt_tools.py` (route_wbgt): WBGT + solver kuli (Tg/Tmrt w środku). Open-Meteo (radiacja). Strefy ACSM.
- `tools/rwgps/route_weather.py`: prognoza per pudełko + `_rel_wind` (składowa wzdłużna/boczna). Wiatr m/s.
- `qbot3/routes/route_elevation_engine.py`: SRTM30m + wygładzanie; daje grade/heading per segment (dla wiatru efektywnego/ETA).
- `route_time_estimate` (projekt B4-v2): prędkość per segment → godzina na km (potrzebne do Tier 1 i wiatru efektywnego).
- Open-Meteo: forecast (radiacja, ~+14 dni) i ARCHIVE/ERA5 (historia, do analiz wstecz). timezone GMT dla spójności z FIT (UTC).

## Zależności / blokery
- LANDCOVER (ziarnistość las/odkryte) — oddane drugiej sesji. ODBLOKOWUJE Tier 2 WBGT (cień = fdir≈0). Bez tego Tier 2 nie ma sensu.
- route_time_estimate v2 (osobny projekt B4-v2, krzywa prędkości skalibrowana) — potrzebny do joinu czasowego (Tier 1)
  i do wiatru efektywnego (prędkość gruntowa per segment). To NIE ten sam projekt; tu jest tylko zależnością.
- Albert _SYSTEM: każda zmiana narzędzia = wpis w prompcie w tym samym kroku (twarda reguła).

## Sugerowana kolejność dla nowej sesji
1. ZROBIONE (2026-06-30, zweryfikowane): dług WBGT domknięty — wpis route_wbgt w _SYSTEM (albert.py) + rejestr (tool_registry.py) + commit jako qbot.
2. Tier 0 + Tier 1: pole `alert_level`/`surface` w route_wbgt + join „segment→godzina" z modelem czasu + bramka progowa.
   (Duża wartość, prawie gotowe; nie wymaga landcoveru.) ← NASTĘPNY KROK
3. UTCI krok 0: zwracać Tg/Tmrt obok WBGT (tani, odblokowuje Wątek 2).
4. UTCI/operacyjna: zwendorować wielomian Bröde 2012 + temperatura operacyjna; bramkowane reżimem obok WBGT.
5. Tier 2 WBGT: po potwierdzeniu ziarnistości landcover (cień/woda + wiatr efektywny per segment).
6. Wizualizacja: wzorcowy blok wykresu WBGT-w-czasie (SVG-w-Pythonie) wstrzyknięty w raport web (PoC).
NIE robić Wątku 3 (pogoda w czasie) póki nie ma upalnych/wietrznych danych — to świadomie odłożone.

## Status jednym zdaniem
WBGT policzony, żywy, zarejestrowany i w prompcie Alberta (zostaje integracja bramkowana Tier 0/1/2); UTCI/feels-like nietknięte;
wpływ pogody na czas jazdy świadomie pominięty do czasu lepszych danych. Wszystko spięte wiatrem efektywnym i overlayem per czas startu.
