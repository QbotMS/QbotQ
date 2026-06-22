# QBot — Decyzje architektoniczne

> Jeden punkt prawdy dla decyzji projektowych. Najnowsze na górze.
> Konwencja: przed każdą edycją tego pliku → kopia `DECISIONS.md.bak.RRRRMMDD_GGMMSS`.

---

## 2026-06-21 — ZASADA: instrukcja Alberta zawsze zsynchronizowana z narzedziami (OBOWIAZKOWE)

**Status:** obowiazujace, twarda regula procesu.

**Problem:** narzedzia (qbot3/tool_registry.py) zmieniaja sie szybciej niz prompt Alberta
(_SYSTEM w qbot3/llm/albert.py). Gdy dodasz/zmienisz/usuniesz narzedzie, a prompt zostaje w tyle,
Albert nie wie ze narzedzie istnieje albo do czego sluzy -> myli intencje, wpada w zle narzedzie.
To byla glowna przyczyna rozjezdzania sie systemu (np. dodano route_profile_detail, a prompt o
trasach milczal).

**Regula:** KAZDA zmiana narzedzi LUB domen/intencji MUSI byc w tym samym kroku odzwierciedlona w
prompcie Alberta. Definicja "gotowe" = kod + wpis w rejestrze + AKTUALNY prompt Alberta. Bez
aktualizacji promptu zmiana jest NIEUKONCZONA.

**Wykryte przy okazji (dlugi do splacenia w prompcie _SYSTEM):**
- Brak JAKIEJKOLWIEK sekcji o trasach (jest zywienie/kalendarz/bilans) -> dopisac reguly doboru
  narzedzi tras: route_plan_analysis (podsumowanie planu), route_profile_detail (szczegoly z ramek),
  ride_analysis (wykonana jazda/FIT).
- "Styl odpowiedzi" kaze streszczac -> Albert ucina dlugie wyniki (profil km-po-km). Dopisac:
  gotowe analizy (pole analysis) pokazuj w calosci, nie skracaj.
- build_tools_spec obcina opis narzedzia do 500 znakow -> opisy < 500 znakow, rozroznienie na poczatku.

---

## 2026-06-21 — Scalenie analizy tras w jeden pipeline (planowana + wykonana)

**Status:** zatwierdzone, do implementacji etapami.

### Cel
Jedna spójna analiza jazdy zamiast dwóch pokoleń narzędzi (stary stack tras
`tools/rwgps` + `scripts/q/gravel_intelligence_10.py` ORAZ nowy FitModel z 17–19.06).
Budujemy nowe i dostosowane do całości; stare wchłaniamy i wygaszamy.

### Główna zasada
Analiza zawsze przykłada jazdę do MIARKI = forma (FitModel) + wellness. Bez tej
miarki ocena wisi w próżni i model zgaduje z gołego TSS. Forma + wellness wchodzą
ZAWSZE, także w analizie prostej. Xert schodzi do roli benchmarku (kontrolka),
FitModel staje się źródłem prawdy o formie.

### Architektura — dwie fazy, wspólny kręgosłup
Trasa = rząd pudełek po ~80 m (siatka geograficzna, wspólna dla obu faz).
- 80 m wybrane, bo przy 36 km/h to ~8 próbek FIT/pudełko → średnie ze streamu są
  miarodajne (50 m bywa za chude na zjazdach). DO WERYFIKACJI w praniu.
- Drobną mapę drogi (nawierzchnia/nachylenie) można trzymać gęściej; pudełko 80 m
  służy do uśredniania streamu.

**Faza A — trasa planowana (z webhooka RWGPS, też on-demand):**
napełnia pudełka PRAWDĄ O DRODZE — nawierzchnia, nachylenie/podjazd, prognoza
pogody + kierunek wiatru względem trasy. Plus briefing ryzyka, forma, wellness,
prognoza glikogenu → wskazówki i pacing.

**Faza B — trasa wykonana (z FIT, "analiza pełna"):**
nakłada realny przejazd na TE SAME pudełka.
- DIFF trasa-vs-plan (automat): ślad FIT vs plan. Zgodne → użyj prawdy o drodze
  z fazy A, zero nowych zapytań OSM. Zboczenie → przelicz nawierzchnię/podjazd
  TYLKO dla różniących się pudełek.
- Stream z FIT (moc/HR/kadencja) + realna pogoda do pudełek.
- FitModel: strain (3 systemy energetyczne), EF per nawierzchnia → wraca do
  kalibracji modelu (fitmodel_surface_cal).
- Werdykt przyłożony do formy + wellness.

### Przechowywanie — dwie szafy, w każdej półki
Zasada nadrzędna: PRAWDA O DRODZE (nawierzchnia, nachylenie) leży tylko w szafie
"planowane", RAZ. Szafa "wykonane" jej nie kopiuje — wskazuje na nią i dokłada
tylko różnice (delty z miejsc zboczenia). Tak ginie dotychczasowy dublet
nawierzchni (route_surface_segments vs fitmodel_segment.surface_type).

**Szafa 1 — Trasy planowane** (na bazie istniejących `route_*`):
- półka "droga": NOWA tabela `route_frames` = kanoniczna siatka pudełek 80 m
  (nawierzchnia, nachylenie, kierunek względem wiatru). Zasilana przez
  route_parse_results / route_surface_profiles.
- półka "operacje": rejestr co policzono (nawierzchnia/podjazdy/pogoda/briefing),
  kiedy i w jakiej wersji. Kandydat: route_artifacts. Umożliwia SKIP-OSM.

**Szafa 2 — Trasy wykonane** (na bazie istniejących `fitmodel_*`):
- półka "przejazd": NOWA tabela `*_frames` = te same pudełka 80 m wypełnione
  streamem z FIT + realną pogodą + wynikiem wnioskowania o wietrze; wskazuje na
  półkę "droga" z szafy 1. fitmodel_ride_buckets + fitmodel_segment = fizjologia.
- półka "operacje": FIT wczytany, wynik diffu (zgodne/różne pudełka), nawierzchnia
  doliczona tylko dla różnic, strain, wiatr, werdykt.

### Pogoda
Dwa smaki: PROGNOZA (szafa 1, krzyżujemy szacowany czas dojazdu do pudełka z
prognozą dla miejsca+godziny) i REALIA (szafa 2, realny czas z FIT). Kluczowe pole:
KIERUNEK WIATRU WZGLĘDEM KIERUNKU JAZDY per pudełko (kierunek jazdy z kolejnych
punktów GPS × kierunek wiatru → składowa czołowa/tylna). To mostek do wnioskowania
o wietrze przez model ("mała moc + duża prędkość + składowa w plecy → wiatr pomógł"
— wynika z modelu, nie dopisane ręcznie).
Oszczędność: NIE pytamy API per 80 m — pogoda gładka, pytamy rzadko (co kilka km /
~15–30 min) i interpolujemy na pudełka. Na półce "operacje" logujemy godzinę wydania
prognozy (świeżość). Bonus na później: prognoza vs realia = miara zaufania do prognoz.
Cel do wchłonięcia: stary moduł G11 (prawdopodobnie OpenWeatherMap).

### Co wchłaniamy / co ginie / co nowe
WCHŁANIAMY (stare → pudełka): G10 (nawierzchnia OSM), G11 (pogoda), G13 (briefing
ryzyka), tools/rwgps/climbs.py (podjazdy), RWGPS surface-profile-v1.
GINIE: osobne liczenie nawierzchni z FIT-a w FitModel (zostaje tylko jako fallback,
patrz niżej). Architektura skryptów-podprocesów piszących JSON do ARTIFACTS →
zastąpiona funkcjami w pipeline piszącymi do tabel.
NOWE (nie ma w żadnym stacku): (1) automat diff trasa-vs-plan + doliczanie tylko
różnic, (2) wnioskowanie o wietrze z modelu, (3) wspólna siatka pudełek 80 m.

### Przypadek brzegowy — jazda bez planu RWGPS
Brak trasy planowanej → szafa "wykonane" nie ma na co wskazać. Wtedy (i tylko wtedy)
buduje własne pudełka z FIT-a i liczy nawierzchnię z FIT-a — czyli to, co dziś robi
fitmodel/surface_tag.py. To uzasadnia zachowanie tego kodu jako ścieżki awaryjnej.

### Kolejność wygaszania starego (żeby bot nie zgasł)
1. Zbuduj fazę A na siatce pudełek OBOK starej taśmy G; porównuj wyniki na realnych
   trasach. Stare = fallback.
2. Gdy nowe trzyma poziom → przełącz bota na nowe; stare skrypty przestają być wołane
   (leżą jako .bak).
3. Zbuduj fazę B + diff + wiatr.
4. Złóż tagowanie nawierzchni z FIT do roli fallbacku (dedup nawierzchni).
5. Po sprawdzeniu obu faz na produkcji → stary kod do archive; aktualizacja CONTEXT.md.

### TODO (poza pierwszym etapem)
- Wykrywanie SŁABYCH ODCINKÓW we wstępnej analizie nawierzchni → propozycja korekty
  trasy. Szkielet już istnieje: G13 (decyzje ACCEPT_WARNING/REVIEW/OMIT) +
  build_safe_gpx (poprawiony ślad). Wchodzi do szafy "planowane" jako operacja.
- Gate energii (z wcześniejszych ustaleń, osobny wątek).

### Tabele istotne (stan na 2026-06-21, qbot_v2)
route_parse_results(22), route_surface_profiles(17), route_surface_segments(12),
route_artifacts(15) | fitmodel_daily(11), fitmodel_segment(14),
fitmodel_ride_buckets(10), fitmodel_surface_cal(4), fitmodel_xert_bench(6),
fitmodel_week_plan(10), fitmodel_param(4).

---

## 2026-06-21 — POSTĘP implementacji (Faza A gotowa)

**Zbudowane i przetestowane (na produkcji, OBOK starego stacku):**

Tabele (qbot_v2):
- `route_frames` — siatka pudełek 80 m: nawierzchnia, nachylenie, kierunek jazdy (heading). Półka "droga" szafy planowanej.
- `route_frame_weather` — nakładka pogody (kind=forecast|actual): temp, opady, wiatr + **składowa wiatru względem kierunku jazdy** (+ w plecy / − w twarz), ETA per pudełko.

Moduły (tools/rwgps/):
- `route_frames.py` — czyta GPX, interpoluje na równe 80 m, liczy nachylenie/heading, nakłada nawierzchnię z route_surface_segments. CLI: --artifact-id/--route-id, --dry-run, --show.
- `route_weather.py` — prognoza Open-Meteo per pudełko + wiatr względny. NA ŻĄDANIE z datą (--start), nie z webhooka. CLI jw. + --start --speed-kmh.
- `route_brief.py` — czytelny briefing: droga + nawierzchnia + podjazdy + pogoda + które km pod wiatr + forma z fitmodel_daily. Tylko odczyt.

Wpięcia:
- `scripts/surface_enrich_route.py` (worker webhooka RWGPS B3, wołany z qbot_api.py:1179) — po enrichmencie nawierzchni **automatycznie buduje pudełka**; błąd framingu nie wywraca workera (try/except).

Test referencyjny: trasa 55734589 (Wyszogród–Płock) → 1241 pudełek, nawierzchnia 1241/1241, prognoza 27.06: out w plecy / powrót pod wiatr — poprawnie.

**Decyzje doprecyzowane w trakcie:**
- Pudełka 80 m równe dzięki interpolacji na granicach; długość mierzona WZDŁUŻ trasy (nie po cięciwie) — ważne dla późniejszego dopasowania FIT po dystansie.
- Pogoda: jeden kierunek wiatru wystarcza, bo wiatr względny i tak różni się per pudełko przez zmianę heading. Centroid trasy jako v1; wielopunktowe próbkowanie = refinement na później.
- Forma w fitmodel_daily bywa pusta (model nie liczy codziennie) — briefing bierze ostatni wiersz z niepustym FTP.

**Faza B — DO ZROBIENIA (następne), z decyzjami do podjęcia:**
1. Nałożenie FIT na te same pudełka (stream moc/HR/kadencja per pudełko).
2. Diff trasa-vs-plan: próg "zboczenia" do ustalenia.
3. Realna pogoda (kind=actual) z czasów FIT (Open-Meteo archive).
4. Wnioskowanie o wietrze z modelu: formuła (oczekiwana prędkość przy mocy na płaskim vs realna, krzyż z wind_component) — do ustalenia.
5. Werdykt przyłożony do formy+wellness: format/ton — do ustalenia.

---

## 2026-06-21 — Rozstrzygniecia przed Faza B

**Pogoda — zrodlo:** OpenWeatherMap PRIMARY, Open-Meteo FALLBACK (zgodnie ze stanem
projektu: qbot_tool_registry "OWM primary, Open-Meteo fallback"). route_weather.py
przepisany. OWM /data/2.5/forecast (3-godz., 5 dni); dla dat >5 dni automatyczny
fallback na Open-Meteo (16 dni). OWM daje wiatr kierunkowy (wind.deg) + opady (rain.3h).
- BUGFIX: loader .env w modulach tools/rwgps/* nie zdejmowal cudzyslowow z wartosci
  -> klucz OWM lecial z apostrofami -> 401. Poprawione w route_weather/frames/brief.

**Forma "na dzis" — NIE jest zepsuta (diagnoza):** daily_job (cron 04:45) dziala
poprawnie. ftp_resolver liczy FTP z DANYCH JAZDY, wiec wypelnia tylko dni z przejazdem.
Ostatnia jazda 20.06 -> aktualny FTP = 257 W (model tego uzywa: xert_bench loguje
"ftp_est z 2026-06-20"). Pusty wiersz 06-21 = konwencja zapisu (FTP na dniu jazdy,
brak przenoszenia na dni odpoczynku), NIE brak formy. Glikogen 0% = wyjscie modelu.
route_brief juz bierze ostatni niepusty FTP — poprawnie.
- OPCJA (kosmetyka, do decyzji): przenosic ostatni FTP na dni odpoczynku w
  fitmodel_daily, by wiersz dnia byl od razu czytelny. Na razie NIE robione.

**Faza B — decyzje wciaz otwarte (do ustalenia z Michalem):**
1. Skojarzenie FIT <-> planowana trasa (po dacie? starcie? recznie?).
2. Prog "zboczenia" w diffie trasa-vs-plan.
3. Formula wnioskowania o wietrze + format/ton werdyktu.

---

## 2026-06-21 — Faza B GOTOWA (rdzeń projektu dziala E2E)

Decyzje przyjete: (1) FIT<->plan auto po starcie+dacie; (2) prog zboczenia 60 m;
(3) wiatr przez korelacje nadwyzki predkosci, werdykt krotki.

**Zbudowane i przetestowane (na realnym przejezdzie 20.06, trasa 55734589):**

Tabela: `ride_frames` — przejazd na pudelkach planu: n_samples, avg_power/hr/cadence/speed,
t_start/t_mid, dist_from_plan_m, off_plan. Polka "przejazd" szafy wykonanych.

Moduly (tools/rwgps/):
- `ride_overlay.py` — czyta FIT (GPS+stream per sekunda, semicircles jak surface_tag),
  AUTO-kojarzy z planem po starcie (<2 km), przypisuje sekundy do pudelek (okno przesuwne),
  liczy diff (dist_from_plan, off_plan>60 m). CLI: --latest/--fit, --dry-run, --show.
- `ride_verdict.py` — realna pogoda (kind=actual, Open-Meteo recent/archive) per pudelko +
  wiatr wzgledny; WNIOSKOWANIE O WIETRZE (nadwyzka predkosci po odjeciu mocy ~ wind_component
  na plaskim, slope+r); WERDYKT przylozony do formy (ostatni pelny FTP). CLI: --ride latest.

Wynik referencyjny: 1211 pudelek, 200 W (=78% FTP 257 W -> "tempo"), 1079/1211 na planie,
wiatr w plecy +0.7 km/h na 1 m/s (r=0.40).

**Co jeszcze zostaje (integracja + sprzatanie, nie rdzen):**
- Wpiac wywolania w interfejs bota: "analiza planowanej trasy" -> route_brief;
  "ocen jazde" -> ride_overlay+ride_verdict (przez MCP/query router).
- Auto-trigger analizy jazdy po nowym FIT (analogicznie do webhooka tras).
- Zlozyc stare tagowanie nawierzchni z FIT do roli fallback; jazda BEZ planu (orphan) jako tryb fallback w ride_overlay.
- Wygasic stary stack G (G10/G11/G13, gravel_intelligence) -> archive; aktualizacja CONTEXT.md.
- Refinementy: pogoda wielopunktowa; przeliczanie nawierzchni TYLKO dla off_plan>200 m;
  carry-forward FTP na dni odpoczynku.

Nowe tabele qbot_v2 z tej sesji: route_frames, route_frame_weather, ride_frames.
Nowe moduly: tools/rwgps/{route_frames,route_weather,route_brief,ride_overlay,ride_verdict}.py

---

## 2026-06-21 — Wpiecie w bota (gotowe do testow)

Dwa narzedzia wpiete w 3 warstwach (qbot_route_tools / qbot_tool_registry / qbot_query_router):
- qbot_route_plan_analysis -> route_brief (+ opcj. route_weather gdy podany start). Frazy:
  "analiza planowanej trasy", "planowanej trasy", "briefing trasy", "przeanalizuj trase".
- qbot_ride_analysis -> ride_overlay + ride_verdict. Frazy: "ocen jazde", "analiza jazdy",
  "ocen przejazd", "ocen wczorajsza jazde".
Domyslnie: plan = najnowsza otrasowana trasa; jazda = najnowszy FIT. Routing LLM-first
(readery w rejestrze) + fallback keyword (classify_intent — odmiana PL dodana).
qbot-api.service zrestartowany, active. Import-test wszystkich modulow OK.

---

## 2026-06-21 — KOREKTA: wlasciwa warstwa routingu (Router v2, NIE qbot_query_router)

BLAD wczesniejszy: wpinalem analize w qbot_query_router.py (_reader/classify_intent).
To NIE jest zywa sciezka Claude'a dla tras. Wg CONTEXT.md:
  Domena TRAS: Router v2 (qbot_query_handler.py) -> Planner v2 (core/planner.py), NIE Albert.
Zapytanie "pelna analiza trasy" spadalo do Alberta (improwizacja na starych danych: 418 m,
pogoda po nazwie -> Vyshhorod UA).

WLASCIWE wpiecie (dziala, zweryfikowane przez handle_query): qbot_query_handler.py
- INTENT_KEYWORDS: dodane "route_plan_analysis" i "ride_analysis" (na poczatku listy).
- handle_query: galezie PRZED blokiem eskalacji do Alberta (return ucina eskalacje).
- _handle_route_plan_analysis / _handle_ride_analysis -> wolaja qbot_route_tools._tool_*,
  wynik w _envelope(engine=query_vnext). Wyciaga route_id (\d{6,}) i start z pytania.

Test: handle_query("pelna analiza trasy Wyszogrod-Plock") -> engine=query_vnext,
intent=route_plan_analysis, +453 m (spojne), pogoda 24-30C PL, wiatr per km, FTP 257.

Uwaga: edycje w qbot_query_router.py (czesc readerow/keywordow) sa dla sciezki Claude
BEZCZYNNE (to adapter konektora ChatGPT / inna powierzchnia) — nieszkodliwe, mozna zostawic.
Funkcje _tool_* w qbot_route_tools.py + rejestr SA uzywane (handler je wola) — OK.

OSOBNY bug (do naprawy pozniej): generyczne narzedzie pogodowe geokoduje nazwe miasta ->
"Wyszogrod" myli z "Vyshhorod" UA. Analiza trasy go omija (liczy po wspolrzednych).

---

## 2026-06-21 — WLASCIWE rozwiazanie: narzedzia w rejestrze Alberta (LLM-first), koniec keywordow

PROBLEM (slusznie wytkniety przez Michala): keyword/stem matching w qbot_query_handler.py
NIE rozroznia "analiza trasy dzisiejszej" (=jazda FIT) od "analiza planowanej trasy" (=track).
Kazda odmiana PL psula dopasowanie. To byla zla warstwa.

ZYWA SCIEZKA (potwierdzona w kodzie):
  MCP qbot.query -> qbot3/adapters/mcp_adapter.py (_call_tool) -> jesli QBOT_QUERY_VNEXT_ENABLED=1:
  handle_query(); status UNRECOGNIZED/ACTION_REQUIRED -> orchestrate_query() = ALBERT
  (natywny tool-calling agent LLM). Albert dobiera narzedzia z qbot3/tool_registry.py
  (nie qbot_tool_registry.py, nie qbot_query_router.py — tamte sa dla Claude bezczynne).

ZROBIONE:
- qbot3/tool_registry.py: dodane _load_route_plan_analysis_tool + _load_ride_analysis_tool
  (zarejestrowane w 'loaders'), opisy ostro rozdzielaja: route_plan = ZAPLANOWANA trasa (track,
  przed jazda); ride = WYKONANA jazda (FIT, dzisiejsza/wczorajsza). Opisy mowia tez wprost
  "nie lacz z rwgps_route_fetch/route_poi/surface".
- Zawezony opis rwgps_route_fetch (to ono dawalo 418 m): teraz "tylko surowe metadane,
  do analizy uzyj route_plan_analysis".
- USUNIETY keyword-hack z qbot_query_handler.py (_resolve_intent: blok stem-match;
  INTENT_KEYWORDS: 2 wpisy). Route/ride -> UNRECOGNIZED -> Albert decyduje po sensie.
  (Martwe galezie if intent==... + _handle_route_plan_analysis/_handle_ride_analysis
  zostaly w handle_query jako nieosiagalne — do sprzatniecia pozniej, nieszkodliwe.)

TEST (realny adapter, prawdziwy LLM):
- "zrob analize trasy dzisiejszej"   -> Albert wybral ride_analysis  (FIT: 1211 pudelek, 200 W) ✓
- "analiza planowanej trasy 55734589"-> Albert wybral route_plan_analysis (track: +453 m) ✓

UWAGA: Albert parafrazuje pole analysis do wlasnej prozy (liczby OK, format inny niz moj blok
"📋 ANALIZA..."). Jesli ma byc 1:1 — wzmocnic instrukcje verbatim albo pass-through. TODO.

POZOSTALE: QBOT_ROUTES_VIA_ALBERT=1 jest OK (Albert ma teraz wlasciwe narzedzia).
Stary bug pogodowy (nazwa miasta -> Vyshhorod UA) dotyczy generycznego weather, nie analizy trasy.

---

## 2026-06-21 — Sprzatanie tras + naprawa zrodla prawdy

PRZYCZYNA: CONTEXT.md (generowany przez scripts/build_context.py) twierdzil, ze domena TRAS
idzie przez "Router v2 -> Planner v2 (core/planner.py)". core/planner.py NIE ISTNIEJE.
To klamstwo (zapisane przez sesje Claude rano 21.06) wpedzalo kazda kolejna sesje w pogon
za nieistniejaca warstwa; czatowy Claude konfabulowal "Albert nie ma uprawnien do tras"
(w agent_runtime takiej bramki nie ma — blokowane sa tylko operacje destrukcyjne).

NAPRAWIONE:
- scripts/build_context.py: linia routingu przepisana na prawde (trasy -> Albert; route_plan_analysis=
  plan/track, ride_analysis=FIT; Planner v2/core.planner NIE ISTNIEJE; ChatGPT/Telegram = osobny routing).
  CONTEXT.md zregenerowany.
- archive/route_legacy_2026-06/ (git mv): 22 skrypty (stack G g1-g15, analyze_route_poi_*,
  analyze_rwgps_surface, route_logistics_*, smoke_route_logistics) + tools/rwgps/overpass_cache.py.
  Kazdy: 0 importow w repo, brak w cronie, brak w zywych entrypointach. +RETIRED.md.
- qbot_query_handler.py: usuniety martwy kod (galezie + funkcje _handle_route_plan_analysis/
  _handle_ride_analysis, nieosiagalne po usunieciu keyword-hacka).
- Zweryfikowano end-to-end: "dokonaj pelnej analizy technicznej planowanej trasy 55734589" -> +453 m.

ZASADA HIGIENY (kazda sesja): 1) start = CONTEXT.md + CURRENT.md; 2) przed edycja/cieciem pelna
inwentaryzacja + weryfikacja osiagalnosci (grep w CALYM repo, cron, entrypointy); 3) wyparte -> od
razu archive/ (git mv); 4) stan pracy w CURRENT.md.

UWAGA: zmiany STAGED, niezacommitowane. git status pokazuje ~43 pozycje — czesc od innych sesji
z 21.06 (mcp_adapter.py, agent_runtime.py, qbot_api.py). Przed commitem przejrzec git diff.
