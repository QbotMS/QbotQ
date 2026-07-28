# QBot -- CURRENT (handoff sesji)

## [2026-07-28] Porzadki: commity, push, sprzatanie plikow

STAN PO SESJI (zweryfikowany na zywo):
- Repo czyste: `git status` bez zmian, `main` == `origin/main`.
- Commit 1bf0b34 (push origin/main): hammerhead - odpornosc na wygasly refresh token
  (fallback do logowania zamiast wyjatku, hammerhead_auth.py) + antyspam alertu
  "brak danych lokalnych" w ride_report.py (znacznik data/missing_data_alerts.json,
  alert leci RAZ na aktywnosc, nie przy kazdym cronie) + qbot-hammerhead-sync
  + .gitignore (docs/audit/enrich_trigger.json). Kod dzialal na zywo od wczesniejszej
  sesji, ale nie byl w repo.

SKASOWANE (DC/SSH):
- scripts/qext2_fresh.patch, qext2_rsrv_batt.patch, qext2_tf_session.patch - QExt2 to
  OSOBNY projekt, nie nalezy do repo QBota.
- docs/CURRENT.md.bak, docs/DECISIONS.md.bak, docs/architecture/MODELQ_V2.md.bak.
- qbot3/routes/planer_stage_export.py.bak (2 szt.), route_attraction_store.py.bak.
- data/garage.db.bak - 7 starych kopii; ZOSTAJE najnowsza garage.db.bak.20260728_081025.

ZOSTAWIONE SWIADOMIE:
- .env*.bak (3 szt.: _bak_archive/.env.bak, _bak_archive/.env.local.bak,
  config/profiles/michal.env.bak) - sekrety, nie kasowane bez osobnej decyzji.
- outgoing/garmin_proxy/hammerhead_44954...fit.bak.20260719_201939 - powiazany
  z niedokonczona korekta FIT z 19.07.

ZAMKNIETE STARE STATUSY:
- Wszystkie wczesniejsze "[ZAMKNIETE 2026-07-28] DO DOKONCZENIA (recznie -- brak commit/push w DEV MCP)" oraz
  "DO ZROBIENIA: qbot_web.py niezacommitowany" sa NIEAKTUALNE - oznaczone prefiksem
  [ZAMKNIETE 2026-07-28]. Nic nie czeka na commit ani na push.
- scripts/_tmp_*.py, scripts/_new_block_planned_load.txt oraz .bak w /opt/qbot/web/public:
  sprawdzone - juz ich nie ma.
- Tablica robocza (worklock) pusta - zadna sesja nic nie trzyma.



## Sesja 2026-07-27 -- Planer wyprawy: data trwala, PDF (tresc+FORMA), ogonki, nazwy postojow

WYKONANE I WDROZONE (na zywo, zweryfikowane):
- DATA WYPRAWY TRWALA: pole #wyprawa-data zapisywane w wersji/historii/szkicu
  (planer_saved / planer_hist / planer_draft) i odtwarzane przy wczytaniu (pole +
  feasDeparture + refreshFeas). Wczesniej data zyla tylko ulotnie w polu -> gubiona po
  reloadzie i po wczytaniu wersji z historii. (planer-wyprawy-render.js)
- GODZINA WERSJI lokalna: verName formatuje saved_at przez new Date() -> koniec z UTC
  08:59, pokazuje lokalne 10:59.
- PDF FORMA: data plynie planer -> wyprawa-oczekiwanie -> /api/wyprawa/pdf-start -> strona
  druku (?departure=); render liczy XSS/forme; body dostaje klase pdf-forma; #ocena-formy
  odslaniana w druku TYLKO na pierwszej sekcji (ALL) i gdy jest data; bez daty pomijana.
  (planer-wyprawy-render.js, wyprawa-oczekiwanie.html, qbot_web.py: &departure= w URL druku
  + wait az forma sie doliczy)
- PDF PELNA TRESC (bug): builder lewego panelu (#allpanel) PRZENOSIL OPIS/tabele/FORMA/tlo do
  paneli .ap-pane{display:none} i robil to TAKZE w trybie druku -> tresc byla w DOM, ale
  niewidoczna -> PDF jej nie pokazywal. FIX: build() pomijany gdy print=1 -> tresc zostaje w
  .wrap i jest widoczna (jak przed dodaniem panelu). Zweryfikowane na ZLOZONYM dokumencie
  (offsetHeight): opis 605, tlo hist 740, tlo geo 499, FORMA 415. (planer-wyprawy.html)
- PDF STARY CACHE (bug): _wyprawa_source_hash zaczynal sie od "v2" i nie zmienial przy
  zmianach layoutu/FORMY -> serwowal zapisany, bledny PDF. FIX: bump "v2"->"v3" + czyszczenie
  wpisu trasy w qbot_v2.wyprawa_report. Test: pdf-start cached:false, build od nowa 71 s,
  8.7 MB, bez bledu. (qbot_web.py)
- OGONKI W OPISACH LLM: 3 prompty w qbot3/routes/planer_opis.py (_SYS, _SYS_DZIEN, _SYS_TLO)
  dostaly twarda instrukcje o pelnej polszczyznie (a c e l n o s z z). Cache Oppelnera
  (planer_route_opis_dni/opis/tlo) wyczyszczony i zregenerowany. Efekt: Dzien->Dzien z ogonkiem,
  trase->trase z ogonkiem, wiekszosci -> wiekszosci z ogonkami.
- OGONKI W "OCENA FORMY": 14 sztywnych stringow werdyktu w fitmodel/expedition_feasibility.py
  przepisane z ogonkami (Dzien powyzej sciany, Srednia miesci sie, Narastajace zmeczenie ...).
  Deterministyczne, bez LLM/cache. Cache PDF trasy wyczyszczony.
- NAZWY POSTOJOW: nocleg / od-do dnia / fakty PDF braly NAJBLIZSZE PO KM ignorujac dist_m
  (odleglosc od trasy) -> lapaly przysiolki z boku (Gorniak 1615 m, Gorka 546 m). FIX:
  score = |km - punkt| + 3.0*(dist_m/1000) w _nearest_town (planer_opis.py), _place_at_km i
  _wyprawa_place_at_km (qbot_web.py). Efekt: cut 119.5 -> Ziebice, cut 234.55 -> Prudnik.

COMMITY:
- 5d7e6f5 (push origin/main): data wyprawy trwala + FORMA w PDF + ogonki opisow + nazwy
  postojow wazone dist_m (qbot_web.py, qbot3/routes/planer_opis.py).
- DO COMMITA (jawne sciezki, bez -a): qbot_web.py (v3 + wait FORMA) +
  fitmodel/expedition_feasibility.py (ogonki werdyktu) + docs/CURRENT.md.
- Statyk planer-wyprawy.html jest POZA repo aplikacji (wlasne .git w /opt/qbot/web/public) --
  zywy natychmiast; ten commit go nie obejmuje.

OTWARTE / UWAGI:
- FLAGA /opt/qbot/artifacts/noclegi_offline.flag (offline testy, 24.07) nadal WLACZONA ->
  /api/noclegi zwraca OFFLINE, front planera utyka na "sprawdzam noclegi..." (obsluguje tylko
  status OK). Do decyzji: wylaczyc flage (koszty Google) czy poprawic UI na czytelny komunikat.
- NAZWY POSTOJOW: brak rangi/populacji miejsca w route_poi_layer (zrodlo geonames, wszystko
  jako 'town'); dist_m to jedyny sygnal. Duze miasto dalej od trasy niz wies przy niej ->
  wybierze blizsza. Twarda ranga (dociagniecie populacji z geonames) = osobne zadanie.
- Kanal SSH (MacOS-MCP:Shell) wielokrotnie wieszal sie ~4 min na komendach git (echo ok
  przechodzi). Commity robione recznie przez uzytkownika w terminalu.

---

## Sesja 2026-07-25 -- awaria lancucha Karoo -> Garmin -> baza (dwa wygasle dostepy)

Decyzja: docs/DECISIONS.md (wpis 2026-07-25).

OBJAW ZGLOSZONY PRZEZ UZYTKOWNIKA: Telegram wysylal co 30 min "Raport z jazdy nie zostal
wygenerowany / Brak danych aktywnosci w lokalnej bazie" dla i169091100 (Afternoon Ride).

PRZYCZYNA (dwa niezalezne wygasniecia w tym samym oknie):
1. Hammerhead: refresh odrzucany od 2026-07-24 13:10 (`invalid_grant / invalid refresh token`,
   potwierdzone realnym zapytaniem do dashboard.hammerhead.io/v1/auth/token). Logowanie
   przez SRAM ID (SSO) => sciezka GARMIN-owa "email+haslo" NIE ISTNIEJE dla Hammerheada,
   `grant_type=password` nie zadziala. Jedyna droga: swiezy `jwt:refresh` z przegladarki.
2. Garmin: `API Error 401 / Failed to retrieve social profile`. Profil michal wskazywal na
   WLASNY magazyn `.garmin_tokens/michal/` (token wygasl 2026-05-20 04:15, plik nietkniety
   od 19 maja -- sync odswiezal sesje TYLKO W PAMIECI i nigdy nie zapisywal). Magazyn
   domyslny `.garmin_tokens/` byl caly czas zywy (odswiezany co 15 min przez importer).

WZORZEC DO ZAPAMIETANIA (wylozyl system DWUKROTNIE tego samego wieczoru):
istnieje magazyn DOMYSLNY i magazyn PROFILOWY; utrzymywany przy zyciu jest domyslny,
a sync czyta profilowy. Przy Hammerheadzie formularz zapisal do domyslnego zamiast do
`michal.json`; przy Garminie profilowy gnil od maja. Przed kazda zmiana poswiadczen
SPRAWDZIC, ktory plik realnie czyta dany proces (`HAMMERHEAD_TOKENSTORE`,
`GARMIN_TOKENSTORE` w config/profiles/<profil>.env).

WYKONANE I WDROZONE (zweryfikowane na zywo):
- `hammerhead_auth.py::get_tokens` -- nieudany refresh nie przerywa procesu wyjatkiem,
  tylko pozwala sprobowac kolejnych drog (logowanie) i dopiero na koncu zglasza brak.
- `qbot_web.py` -- nowy `GET /hammerhead-dostep` (formularz za sesja) + `POST
  /api/hammerhead/refresh-token`. Uzytkownik wkleja `jwt:refresh` z przegladarki PROSTO
  na serwer; wartosc nie przechodzi przez model ani przez zapis rozmowy. Endpoint zapisuje
  do magazynu domyslnego ORAZ do kazdego `HAMMERHEAD_TOKENSTORE` z config/profiles/*.env
  (zwraca liste `stores`), zeby rozjazd plikow sie nie powtorzyl.
- `config/profiles/michal.env` -- `GARMIN_TOKENSTORE` przepiety z `.garmin_tokens/michal`
  na wspolny `.garmin_tokens` (ten sam uzytkownik: get_full_name="Michal", id=63697126,
  potwierdzone na zywo). Kopia: `michal.env.bak.20260725_220140`.
- `qbot-hammerhead-sync` -- Garmin `409 Duplicate Activity` to NIE porazka: status
  `duplicate`, exit_code 0, aktywnosc odznaczona jako przetworzona (`uploaded`). Bez tego
  sync w nieskonczonosc wysylal to samo i meldowal blad co 10 min.
- `qbot-hammerhead-sync` -- `_sync_alert()` / `_sync_alert_clear()`: JEDEN komunikat na
  Telegram przy realnej awarii, wyciszenie 6 h (`state/sync_alert_state.json`), udany
  przebieg kasuje wyciszenie. W tresci link do /hammerhead-dostep.
- `ride_report.py` -- alert "brak danych aktywnosci" wysylany RAZ na aktywnosc
  (`data/missing_data_alerts.json`), nie przy kazdym przebiegu crona co 30 min.

DOWODY NA ZYWO:
- 21:50 pierwszy pobrany FIT od 24.07 (216144 b, activityTime 2026-07-25T11:44:16Z).
- 22:15:07 jazda w bazie: external_id 23731387812, "Marki Kolarstwo", garmin_live,
  20.8 km, 3503 s, 145 W, aerobic_training_eff 2.4, activity_record 3502 rekordy 1 Hz.
- 22:40 sync zwraca `"status": "duplicate"` zamiast `"failed"`; brak pliku wyciszenia
  alarmu => zaden falszywy alarm nie poszedl.

USTALENIE MERYTORYCZNE (korekta bledu asystenta): przystanek na Garminie NIE jest zbedna
petla. `qbot_activity_ingest.py` pobiera FIT Z POWROTEM z Garmina
(`download_activity(..., ORIGINAL)`) i nie ma ani jednego odwolania do Hammerheada, a
`import_garmin_training.py` bierze z API Garmina pola LICZONE PRZEZ GARMINA
(`aerobicTrainingEffect`, `anaerobicTrainingEffect`, `intensityFactor`), ktorych plik
z Karoo nie zawiera. Plik w `hammerhead_originals/` to kopia robocza, NIE zrodlo bazy.
UWAGA: `docs/archive/MODELQ_V1.md` twierdzi, ze strumienie 1 Hz pochodza z
`hammerhead_originals` -- to nieaktualne (dokument v1, zarchiwizowany). Zywy kod wygrywa.

OTWARTE:
- Nie ustalono, ktora droga dzisiejsza jazda trafila na Garmina (jedyna zalogowana proba
  wysylki zwrocila 409 "juz mam"; nazwa "Marki Kolarstwo" to nazewnictwo Garmina, nie
  Karoo). Do wyjasnienia przy nastepnej jezdzie.
- W przebiegu 22:40 pojawil sie warning `No such field 6 for dev_data_index 3` (pola
  developerskie QExt2 w walidacji FIT). Nie blokuje syncu; `qbot_activity_ingest.py` ma na
  to monkey-patch `_safe_get_dev_type`, `qbot-hammerhead-sync` nie ma. Do sprawdzenia.
- Rozwazyc uporzadkowanie wzorca "magazyn domyslny vs profilowy" dla wszystkich integracji.

---

## Sesja 2026-07-24 -- raport trasy: asfalt niebieski + zoom wykresu przy zaznaczeniu

WYKONANE I WDROZONE (na zywo; statyk POZA repo -- brak commita kodu):
- Kolor asfaltu: SCAT[1] #000000 -> #1565c0 w /opt/qbot/web/public/raport-render.js. Niebieski na wykresie, mapie, legendzie i paskach udzialu (jedno zrodlo). CSS .cx-asf/.d.asf w raport.css celowo nietkniety (zakres = wykres+mapa).
- Zoom wykresu: zaznaczenie fragmentu wykresu zoomuje teraz WYKRES (okno widoku VIEW; os km/siatka/profil/wiatr/pogoda przeliczane do zakresu) ORAZ mape (jak dotad). Klik bez przeciagniecia = reset do calej trasy. Dodany clipPath na polu wykresu (dane nie wychodza na opisy osi). Podpowiedz legendy -> 'zoom wykresu i mapy'. Dotyczy TYLKO pojedynczej trasy; renderDayChart (wielodniowy) nietkniety.
- Weryfikacja na zywo: dev_fetch /raport-render.js => 200 + marker 'zoom wykresu i mapy'; grupy <g clip-path> zbilansowane; skrypty-latki _tmp_patch_* samo-usuniete.

UWAGA: raport-render.js jest poza repo (zywy natychmiast) -- ten commit obejmuje wylacznie wpis CURRENT.

---

## Sesja 2026-07-23 -- bezpiecznik kosztow Google Places + guard atrakcji

Decyzja: docs/DECISIONS.md (wpis 2026-07-23).

WYKONANE I WDROZONE (na zywo, zweryfikowane):
- Bezpiecznik Places: modul `qbot3/routes/google_places_budget.py` + tabela `qbot_v2.google_places_usage`. Limity 200/dobe, 1000/miesiac (env-owalne). Wpiety przed KAZDYM searchNearby (route_analyzer supply+atrakcje, tools/rwgps/google_places). Przekroczenie => zero wywolan. Test na zywo: limit 0 blokuje bez naliczenia.
- Guard atrakcji: `ensure_route_attractions(force=False)` zwraca opublikowany run z bazy (`CACHED_KEPT`) bez Google. Test: komoot-3088315688 -> CACHED_KEPT run 8, licznik 0/200, 0/1000 bez zmian.
- Endpoint `/api/report/attractions/fetch?force=1`; front `raport-render.js` v=2026072301 (raport-trasy.html, raport-print.html): domyslny przycisk z bazy, osobny "Odswiez z Google".

COMMIT: aef6cce (push origin/main).

OTWARTE: sprzatnac stare fetch_google_*.py (Toskania) i stare .bak w katalogu glownym; ew. podglad zuzycia licznika Places w UI.

---

## Sesja 2026-07-18 -- wspólne atrakcje + Planer Wypraw -> dzienne GPX + sprzątanie

Pełna dokumentacja: `docs/PLANER_WYPRAW_ATRAKCJE.md`. Decyzja: `docs/DECISIONS.md`.

WYKONANE I WDROŻONE:
- Planer Wypraw i Analiza Trasy czytają jeden opublikowany ranking atrakcji.
- Ranking `route_attractions_v2.2`: pełna baza Wikipedia/Wikidata + selektywny, globalny OSM dla historii, dziedzictwa, fortyfikacji i wartościowych konstrukcji. Dodano pola bitew, obronę, schrony oraz `cultural_landmark` dla miejsc typu Caminito del Rey; widoczna archeologia jest premiowana, a niewidoczne grodziska karane.
- Przywrócone zdjęcia, krótkie opisy i linki źródłowe atrakcji.
- `POST /api/planer/dodaj-do-qbot` tworzy wszystkie dzienne GPX jednym żądaniem.
- `route_stage_lineage` wiąże dzień z rodzicem i zakresem km. Atrakcje dnia są wycinkiem publikacji rodzica, bez zapytań zewnętrznych; nawierzchnia i POI logistyczne również są dziedziczone.
- Zmieniony podział usuwa poprzednie dzienne rekordy, artefakty, warstwy i dokładne GPX dopiero po poprawnym zapisaniu nowego zestawu. Identyczny podział jest idempotentny; trasy ręczne są chronione.
- Produkcja: `qbot-web` active, frontend Planera `v27`, migracja zastosowana.
- Korytarz atrakcji wynosi 2050 m. Odległość jest miękką karą rankingu; usunięto twardą bramkę 800 m.
- OSM działa w oddzielnych, cache'owanych fragmentach. `DEGRADED_OSM` nie ukrywa kompletnego wyniku Wikipedii; kolejne pobranie ponawia brakujące fragmenty.
- Test produkcyjny `Małe Gosie NEW`: run 15 `COMPLETE`, Wikipedia 26, OSM 58, 9 kandydatów; w wyniku są schron „Sulin” i Obrona Wizny.
- Testy: Planer 15/15, silnik atrakcji 11/11, store atrakcji 11/11.
- FIX 2026-07-18: usunięto błędną minimalną gęstość publikacji `floor(km/100*10)`. Kompletny wynik z co najmniej jednym kandydatem jakościowym jest publikowany; norma per 100 km pozostaje tylko celem/limitem rankingu.

COMMITY: `f577e34`, `692b029`, `c972a5a`, `74e31d2`, `d4238e3`, `ef2d82c`, `eea9287`. Dwa ostatnie są w `origin/main`.

OTWARTE: monitorować `cleanup_warnings` oraz `source_status_json.missing_chunks` dla publicznych instancji OSM. Zdjęcie i dłuższy opis są pokazywane tylko wtedy, gdy Wikipedia/Wikidata/OSM udostępniają te dane; silnik ich nie zmyśla.

---

## Sesja 2026-07-17/18 -- Presety zywienia + kafelek/ikonka jedzenia w kalendarzu + rekonstrukcja dni + fix bialych pol

Pelna decyzja: docs/DECISIONS.md (wpis 2026-07-17/18 presety zywienia). Model/dane: docs/PROJEKT_ODZYWIANIE.md (sekcja "Presety szybkiego szacunku").

WYKONANE (na zywo, zweryfikowane):
- BUG KRYTYCZNY: trigger qbot_v2.refresh_day_flags() wskazywal na skasowana tabele calendar_events -> BLOKOWAL wszystkie zapisy do intake_logs/energy_daily/sleep_daily/training_sessions/wellness_daily (zrodlo WRITE_INCONSISTENT). Fix: CREATE OR REPLACE, has_calendar z calendar_entry(day). Utrwalone: sql/refresh_day_flags_fix.sql + naglowek DEPRECATED w sql/calendar_core_v1.sql (commit 65a3edb).
- PRESETY ZYWIENIA (3 poziomy, model ABSOLUTNY): malo=2200, normalnie=2700, popuscilem=3100 kcal (kotwice percepcji, edytowalne: ANCHORS_KCAL w qbot_nutrition_presets.py). Makra = mediana realnych logowanych dni w pasmie wokol kotwicy (auto-aktualizacja; popuscilem = low_confidence). Pierwsza wersja liczyla expenditure+-offset -- BLAD (intake nie zalezy od spalania danego dnia), przebudowane na absolutne kotwice.
  - Modul qbot_nutrition_presets.py -> compute_presets(conn): {label,kcal,carbs_g,protein_g,fat_g,n_days,low_confidence}. Filtry: tylko realne dni (bez source ILIKE %preset%/%recovery%, bez quality='estimated'), kcal>=1200, ostatnie 30 probek.
  - Endpointy qbot_web.py: GET /api/nutrition/preset/values?day=, POST /api/nutrition/preset/apply {day,level}, GET /api/nutrition/day-summary?day=, GET /api/nutrition/status?start=&end=.
  - apply: intake_logs source='preset_estimate' quality='estimated' + 1 pozycja; ODMAWIA gdy jest realne jedzenie; ponowny klik kasuje poprzedni preset.
- KALENDARZ UI (statyki poza repo: kalendarz-render.js, kalendarz.html):
  - Kafelek "Zywienie" w otwartym dniu (loadNutriTile/#nutriBox): ZALOGOWANE (kcal+makra+lista) / SZACUNEK+etykieta / brak. Odswieza sie po apply/dodaniu (load->buildDrawer).
  - Ikonka przy dacie w SIATCE: emoji 🍽 (to samo co przycisk sidebar) + kropka statusu: zielona=zalogowane, niebieska=preset, czerwona=brak. Status z GET /api/nutrition/status -> NUTRI w load(). (Emoji nie da sie przefarbowac -> status niesie kropka, nie kolor talerza; odrzucono kolorowany SVG - brzydki maly.)
  - Przyciski "Dodaj" NA GORE (nad Forme), TYLKO IKONY 48x48 + tooltip (title). Sekcja "Wpisy dziennika" pod przyciski, nad Forme. Kolejnosc dbody: Dodaj -> Wpisy -> Forma -> Jazdy -> Zywienie -> Trasa.
  - Etykiety .frm label --muted->--ink. FIX bialych pol: input/textarea/select/date color var(--ink) jasny -> #17251b ciemny + ::placeholder #9aa39a.
  - Cache-bust kalendarz-render.js ?v=17 -> ?v=22.
- REKONSTRUKCJA DNI (zapisane w bazie):
  - 27.06: 7 pozycji 3292 kcal (W468/B123/T97, source='user_estimate' quality='manual') + RECZNA korekta wydatku o mecz (zegarek nie zlapal): energy_daily active 740->2090, total 3021->4371, source='garmin_live+manual_pilka'. Bilans -1079. ZALOZENIE: pelne 1350 na wierzch 740 (mozliwe drobne dublowanie z krokami).
  - 09.07: preset "popuscilem" 3100 kcal -- potwierdzony ze wszedl.
  - Wczesniej: 14.06 (660), 15.06 (2011), 16.07 (re-final 2429), 25.06 (2950), 26.06 (3426), 17.07 (2381).

PUSTE DNI ZYWIENIA (do uzupelnienia): 10-16.07 (7 dni; 09.07 ma preset).

[ZAMKNIETE 2026-07-28] DO DOKONCZENIA (recznie -- brak commit/push w DEV MCP):
1. Commit JAWNYCH sciezek (bez -a):
   qbot_web.py + qbot_nutrition_presets.py + sql/refresh_day_flags_fix.sql + sql/calendar_core_v1.sql + docs/CURRENT.md docs/DECISIONS.md docs/PROJEKT_ODZYWIANIE.md
   msg np.: "zywienie: presety szacunku (2200/2700/3100) + /api/nutrition/{preset,day-summary,status}; fix trigger refresh_day_flags; kalendarz kafelek+ikonka (+docs)"
   Statyki POZA repo: kalendarz-render.js, kalendarz.html

ODLOZONE (decyzja przed kodem):
- choroba -> event (zmiana modelu: choroba ma nasilenie + end_day). NIE ruszone.
- auto-przypisanie presetu pustym dniom.
- eviction presetu przy pozniejszym recznym wpisaniu realnego jedzenia (apply pilnuje tylko jednej strony).
- pelne DDL calendar_entry do sql/ (osobna sesja).

UWAGA porzadkowa: duzo scripts/_tmp_*.py z tej sesji + .bak w web/public i docs -- do usuniecia recznie (rm niedostepny w DEV MCP).

---

## Sesja 2026-07-17 (2) -- Raport trasy: proza LLM (split+retry) + Szczegoly UI + kalendarz dzwonek

Pelna decyzja: docs/DECISIONS.md (wpis 2026-07-17 (2)). Raport: docs/RAPORT_WEB.md
(sekcje "Proza LLM raportu (_report_prose)" i "Zakladka Szczegoly trasy").

WYKONANE (na zywo, zweryfikowane):
- Raport trasy -- pusta Strategia/Ubior/Opony: przyczyna = drugi (duzy) call LLM w _report_prose
  (qbot_web.py) czasem sie urywal (model rozumujacy wlicza reasoning do budzetu tokenow) i cala
  proza planu leciala na None (brak fallbacku). FIX (decyzja 1+2): rozbicie #2 na DWA mniejsze
  zapytania -- A: strategia; B: ubior + sprzet_opony -- po 4000 tokenow + helper _ask_plan z 1x
  retry gdy ktorys klucz nie jest dict (salvage czesciowy). Prompty A/B wycinane z istniejacego
  sys2 po markerach ("strategia: OBIEKT", "sprzet_opony: OBIEKT", "ubior: OBIEKT") -- jedno zrodlo
  promptu. Sygnatura zwrotu _report_prose bez zmian. Weryfikacja na zywo (bez zapisu snapshotu):
  _build_report_data(55930010) -> strategia dict (calosc + 5 etapow), ubior dict (2 zestawy),
  opony dict (wheelset), etapy pogody = 4. Stary snapshot z pusta strategia (np. 29 "Male Gosie")
  zostaje pusty -- przegenerowac (Parametry -> Generuj). REPO: qbot_web.py (restart + commit).
- Zakladka "Szczegoly trasy" (raport.css + raport-trasy.html, statyki poza repo):
  (a) scroll-lock -- strona nie scrolluje, scrolluje TYLKO okno zakladki
  (body.rtab-szczegoly{overflow:hidden}; wysokosc panelu w JS = innerHeight - top - 16,
  przeliczana na resize i przy zwijaniu Parametrow);
  (b) maly margines na dole (16 px pod panelem + 14 px padding w .multi-body);
  (c) delikatnie wieksze czcionki tekstow paneli (~+1 px na kluczowych klasach);
  (d) wieksze odstepy miedzy wierszami (line-height ~1.6-1.7 + oddech w wierszach tabel);
  (e) FIX czytelnosci: .press-cur (wyrozniony wiersz tabeli cisnien) mial zaszyte jasne tlo
  #f3efe6 -> w ciemnym motywie jasny tekst znikal; teraz rgba(60,107,71,.16) + color:var(--ink).
  Cache-bust raport.css ?v=2026071718. Zakladka Mapa i raport dnia nietkniete.
- Kalendarz (kalendarz-render.js + kalendarz.html, statyki poza repo): gdy dzien ma JAZDE i
  przypomnienie, belka przypomnienia (wypadala z komorki) zamieniana na maly dzwonek 🔔 w prawym
  dolnym rogu (liczba gdy >1, tooltip z trescia; klik w komorke otwiera dzien). Bez jazdy --
  belka jak dotad. Rezerwa .day.has-rem .marks{padding-right:20px}. JS ?v=17.

[ZAMKNIETE 2026-07-28] DO DOKONCZENIA (recznie -- brak commit/push w DEV MCP):
1. Commit JAWNYCH sciezek (bez -a): qbot_web.py (_report_prose split+retry) +
   docs/CURRENT.md + docs/DECISIONS.md + docs/RAPORT_WEB.md
   msg np.: "raport trasy: proza LLM split+retry; szczegoly UI; kalendarz dzwonek (+docs)"
   Statyki POZA repo (bez commitu): raport.css, raport-trasy.html, kalendarz-render.js, kalendarz.html

---

## Sesja 2026-07-17 (cz.2) -- DZIS hero split + aktywnosci + panel jazdy, no-store /api, Doradca+plan, zoom kafla

Pelna decyzja: docs/DECISIONS.md (2026-07-17 cz.2). UI: docs/FORMA_UI_LAYOUT.md (sekcje 1/9/10).

WYKONANE (na zywo, zweryfikowane):
- Hero DZIS podzielony na 2: stan dnia | "Ostatnie aktywnosci" (3). Endpoint GET /api/forma/activities?n=3 (training_sessions). Aktywnosc 2-wierszowa: dyscyplina+kiedy / nazwa(link)+dystans+TSS. "Gdzie" z activity_name (brak kolumny lokalizacji).
- Panel szczegolow jazdy: GET /api/forma/activity?external_id= (moc/NP/IF/HR/kadencja/kalorie/TSS + has_report). Klik nazwy -> asideShow(rideDetailHtml); DRUGI klik zamyka (toggle). has_report -> przycisk "Otworz raport trasy" -> /raport-jazdy.html?ride=<eid> w nowej karcie. Test: 23633651158 has_report=True.
- Naprawa "wykresy nie odswiezaja sie po jezdzie": _no_cache_static ustawia Cache-Control: no-store dla /api/ (dane w bazie byly swieze; winny cache przegladarki). Zweryfikowane naglowki. UWAGA: mozliwa druga przyczyna = nocne przeliczanie fitmodel_daily biezacego dnia (osobne zadanie).
- Doradca (coach) czyta plan: _forma_planned_events(conn, days_ahead=21) z calendar_entry kind='event'; doklejane do promptu coach + instrukcja periodyzacji. Dowod: Doradca sam rozpisal taper pod "dluga jazde 2026-07-19 >100km".
- DZIS bez scrolla: .qtab-panel[data-qtab=Dziś] max-height calc(100dvh-168px)+overflow hidden, #dzis-board overflow hidden, .wrap padding-bottom 80->24, ciasniejszy hero.
- Aktywnosci 2-wierszowe (dystans+TSS po prawej nazwy) -> nizszy hero.
- Powiekszanie kafla: .tile[data-k] + openTileZoom -> modal .tilez (duza wartosc, delta, powiekszony wykres, opis+interp). Zamkniecie klik gdziekolwiek lub Esc.
- qbot-web zrestartowany (active). Statyki: forma.html, forma-render.js ?v=32 (poza repo).

[ZAMKNIETE 2026-07-28] DO DOKONCZENIA (recznie -- brak commit/push w DEV MCP):
1. Commit JAWNYCH sciezek (bez -a):
   qbot_web.py + docs/FORMA_UI_LAYOUT.md docs/DECISIONS.md docs/CURRENT.md docs/CONTEXT.md
   msg: "forma: /api/forma/activities+activity(has_report), no-store /api, Doradca+plan, DZIS hero split + zoom kafla + docs"
   (statyki forma.html/forma-render.js sa POZA repo -- bez commitu)

---

## Sesja 2026-07-17 -- Odzywianie (przebudowa), DZIS konfigurowalny, prefs na serwerze

Pelna decyzja: docs/DECISIONS.md (2026-07-17). Dane zakladki: docs/PROJEKT_ODZYWIANIE.md. UI: docs/FORMA_UI_LAYOUT.md (sekcje 5/9).

WYKONANE (na zywo, zweryfikowane):
- Odzywianie: sklad ciala przepiety body_daily -> widoki body_trend_full_composition / body_latest_full_composition (stare bylo z 2026-05-31; muscle_mass_kg to teraz realne kg ~68). Karta bilansu (uklad poziomy IN/OUT, makro z udzialem % i trendem w oknie), pasek skladu ciala jednolinijkowy z DELTA w oknie, wykres 9 chipow (sklad ciala rozbity na osobne, linie makro B/W/T na wspolnej skali gramow, waga czerwona linia na osi prawej, zjedzone LINIA zamiast overlay).
- DZIS konfigurowalny: przycisk "Dostosuj" (chipy on/off; grupy Panel/Moc/Obciazenie/Wellness/Zywienie), reuzycie tile(); widzety zywienia osadzone przez window.QNut (balanceHTML/bodyHTML) + notyfikacja window.renderTodayNut.
- Prefs na serwerze: tabela qbot_v2.ui_prefs + sql/ui_prefs_v1.sql (idempotentny, sprawdzony na bazie); endpointy GET/POST /api/prefs (_current_user z ciasteczka webauth). Round-trip GET->POST->GET OK (user=admin, wiersz testowy posprzatany). Front: zapis na serwer (debounce 400ms) + localStorage fallback; DZIS dociaga prefs przy starcie i nadpisuje lokalne.
- qbot-web zrestartowany (active). Statyki: forma.html, forma-render.js ?v=23, nutrition-render.js ?v=8 (poza repo, zywe od razu).

[ZAMKNIETE 2026-07-28] DO DOKONCZENIA (recznie -- brak commit/push w DEV MCP):
1. Commit JAWNYCH sciezek (bez -a): qbot_web.py + sql/ui_prefs_v1.sql
   msg: "DZIS: server-side prefs (ui_prefs + /api/prefs GET/POST)"
   (statyki w web/public sa POZA repo -- bez commitu)

UWAGA porzadkowa: kilka starych scripts/_tmp_*.py z wczesniejszych sesji (m.in. _tmp_deploy_js.py po awarii base64) -- do usuniecia recznie (rm niedostepny w DEV MCP).

---

## Sesja 2026-07-16 -- zaoranie starego podsystemu KALENDARZA (wariant B)

Pelna decyzja: docs/DECISIONS.md (2026-07-16). Skrot ponizej.

WYKONANE (na zywo, zweryfikowane):
- Backup 6 tabel: _bak_archive/20260716_190931_calendar_tables_backup.json (DDL+wiersze).
- Odpiety caly stary kalendarz (qcal) od Alberta, konektora ChatGPT, CLI, safety,
  raportu dziennego. Rejestr Alberta = 68 narzedzi, zero kalendarza (list_all_tools i
  tool_descriptions = BRAK); qbot-api/web/mcp-bridge/dev-mcp = active.
- DROP 6 tabel: public.{calendar_events, calendar_days, calendar_daily_snapshots,
  qcal_write_audit, reminders} + qbot_v2.calendar_events. Nowy kalendarz
  qbot_v2.calendar_entry nietkniety.
- Wariant B: event_morning_report.py + tools/trip_stages.py PRZEPIETE z calendar_events
  na qbot_planning_facts (route_stages). Zweryfikowane: start Toskanii 2026-06-05,
  okno eventu 06-05..06-11.
- Transport Telegrama i potwierdzenia tras nietkniete (smoke OK).
- 3 pliki-rdzen przeniesione do _bak_archive/20260716_calendar_core/ (mv zrobiony):
  qbot_calendar_core.py, qbot_calendar_cli.py, qbot_qcal_cli.py.

SPRZATANIE POZOSTALOSCI (runda 2, zweryfikowane importy):
- Produkcyjne, izolowane: qbot_capabilities.py (usuniete 6 wpisow qcal, zostalo 16),
  core/change_log.py (mapowania na skasowane tabele), qbot3/llm/openai_provider.py
  (przyklad promptu z calendar_events), qbot3/context_builder.py (wskazowka calendar_snapshot),
  qbot3/query_decomposer.py (mapy pol calendar_event_add/reminder_add).
- Testowe: qbot3/llm/mock_provider.py (3 galezie kalendarzowe = fikcja testowa) + usuniete
  6 testow kalendarza/qcal w test_qbot3_acceptance.py. Suite: 59 testow, tylko 3 wczesniejsze
  faile (nutrition WRITE_INCONSISTENT / naming qbot.query / core.planner -- NIE nasze).

DECYZJA (A): pozostale odwolania qcal w ZYWYM klasyfikatorze zapytan
(qbot_query_router.py ~40, write_router.py ~8, qbot_orchestrator.py ~9, drobne w innych)
ZOSTAWIONE swiadomie. Sa martwe i bezpieczne: readery zneutralizowane (NO_DATA), writery
odrzucane przez allowliste, narzedzia wyrejestrowane, ZADNE nie wykonuje SQL na skasowanych
tabelach. Pelne wyciecie = spory refaktor zywej sciezki klasyfikacji, niski zysk, wieksze
ryzyko -- odlozone. grep na 'qcal'/'calendar' NIE bedzie czysty i to jest OK.

TESTY (uruchamiane programowo przez unittest; DEV MCP blokuje pytest z argumentami):
- tests/test_qbot_qcal_telegram.py -> 12/12 PASS, bez zmian (transport + confirm_route_analysis).
- tests/test_route_precompute_trigger.py -> 17/17 PASS, bez zmian.
- tests/test_qbot3_acceptance.py -> 59 testow; poprawki: test_table_describe (calendar_events
  -> training_sessions), test_tool_registry_includes_all (usuniete asercje qcal_*), usuniete
  6 testow kalendarza/qcal. Pozostale 3 faile WCZESNIEJSZE/niezwiazane (patrz DECISIONS).

[ZAMKNIETE 2026-07-28] DO DOKONCZENIA (recznie / Desktop Commander -- brak commit/push w DEV MCP):
1. Commit (qbot przez runuser) + push (root). tool_registry.py i albert.py MUSZA byc
   w tym samym commicie (juz zmienione razem). Pliki-rdzen: git zobaczy jako usuniete
   (przeniesione do _bak_archive) -- podac jawnie lub osobny 'git rm'.

PLIKI ZMIENIONE (repo, do commitu):
  qbot3/safety.py, qbot3/agent_runtime.py, qbot3/tool_registry.py, qbot3/llm/albert.py,
  qbot_mcp_adapter.py, qbot_query_planner.py, qbot_query_router.py, qbot_ask_cli.py,
  qbot_nutrition_cli.py, qbot_capabilities.py, qbot_qcal_telegram.py,
  daily_report_adapter.py, core/registry.py, core/change_log.py,
  event_morning_report.py, tools/trip_stages.py,
  qbot3/llm/openai_provider.py, qbot3/llm/mock_provider.py, qbot3/context_builder.py,
  qbot3/query_decomposer.py,
  tests/test_qbot3_acceptance.py,
  docs/DECISIONS.md, docs/CURRENT.md, docs/CONTEXT.md
  USUNIETE z repo (przeniesione do _bak_archive/20260716_calendar_core/):
  qbot_calendar_core.py, qbot_calendar_cli.py, qbot_qcal_cli.py


---

## Sesja 2026-07-20 -- Scheduled: poranna weryfikacja duplikatow jazd (tylko zglasza)

WYKONANE (na zywo, zweryfikowane):
- Nowy skrypt scripts/verify_dupes.py -- wykrywa zdublowane jazdy i TYLKO raportuje (nic nie kasuje).
- Duplikat (qbot_v2.training_sessions): (1) same_start = ten sam start do minuty + dystans +-1% + czas +-2% pod >1 external_id (podwojny import); (2) row_dupe = to samo external_id w >1 wierszu.
- Dla kazdego ID pokazuje slad w tabelach (activity_record/qext2_ride/wbal_ride/segment/ride_buckets) -> widac, ktora kopia ma strumienie 1Hz, a ktora jest pusta.
- Anty-spam: pelny obraz zawsze do logu; Telegram TYLKO o NOWYCH grupach. Stan: data/verify_dupes_seen.json.
- Flagi: --dry-run (test bez wysylki i bez zapisu stanu), --force-telegram.
- Cron root (obok pipeline/raportow): 30 5 * * * -> po nocnym fitmodel.daily_job (04:45). Log: /opt/qbot/logs/verify_dupes.log.
- Weryfikacja na zywo: 9 realnych par (maj, garmin_live, podwojny import); w kazdej parze dokladnie jedna kopia ma 1Hz. Pierwszy Telegram wyslany, drugi bieg = cisza (anty-spam OK).
- Commit: 7fb7aaa (origin/main).

OTWARTE / DECYZJA UZYTKOWNIKA:
- 9 par to STARE duplikaty -- do ewentualnego recznego wyczyszczenia (zostawic kopie z 1Hz, skasowac pusta). Skrypt sam NIE kasuje.
- Sprzatanie .bak: dorzucic scripts/verify_dupes.py.bak.1784579684 do listy .bak do usuniecia (rm blokowany w dev_shell_exec).

## 2026-07-24 -- ctlXss dla Karoo (audyt pol QExt2, pkt 3)

- `mcp_server.py`: helper `_modelq_ctl_xss()` + pole `ctlXss` w payloadzie
  `/ride-readiness`. Zweryfikowane na zywo (63.9). Restart `q-bot.service`.
- Ustalona sciezka zywa endpointu (patrz DECISIONS): most `/root/qbot-mcp`
  proxuje na `q-bot.service` -> `/opt/qbot/app/mcp_server.py`.
  `qbot_api.py` zawiera martwy duplikat `/ride-readiness`.
- Strona Karoo (repo QExt2): budzet RSRV natywnie w XSS z `ctlXss`.


## [2026-07-27] Planowane obciazenie z Planera Wypraw (XSS/dzien) -- Kroki 1+2
Cel: system ma widziec planowane obciazenie na kolejne dni (wyprawy z Planera).
- Tabela qbot_v2.planned_load_daily (migracja sql/planned_load_daily_v1.sql, idempotentna): day+source PK, entry_id, route_id, stage_idx, xss, dist_km, moving_h, note. OSOBNO od fitmodel_daily (plan != fakt).
- qbot_web.py: _dni_cuts_for_route + _recompute_planned_load_for_entry (XSS/dzien = podzial Planera dni_json -> cuts -> _planer_stage_xss; dzien N = event.day + N-1; idempotentne, best-effort). Endpoint POST /api/planer/planned-load/recompute. Hook w POST /api/calendar/route (po zapisie mapowania trasy, w try/except -- nie psuje zapisu).
- Widocznosc: _forma_planned_events dokleja 'planowane obciazenie: MM-DD ~X XSS ... (razem ~T)'; prompt Doradcy traktuje XSS jak realny trening. /api/calendar zwraca days[d].planned_xss + liste 'planned'. kalendarz-render.js: badge w komorce dnia + chip 'Planowane XSS' w szufladzie (statyk poza repo, zywe od razu).
- Backfill wyprawy 1-3.08 (entry_id=13, komoot-3088315688): 01.08 ~372 XSS / 02.08 ~305 / 03.08 ~231 (razem ~908). Zweryfikowane na zywym kodzie.
- [ZAMKNIETE 2026-07-28] DO ZROBIENIA (poza kanalem DEV): commit qbot_web.py + sql/planned_load_daily_v1.sql jawnymi sciezkami (qbot/runuser, push root). Sprzatanie przez DC/SSH: scripts/_new_block_planned_load.txt + stare .bak (_tmp_check_plan_events.py.bak.*, _tmp_inspect_planer_schema.py.bak.*).
- MOZLIWE DALEJ (Krok 3, nie robione): projekcja TSB/ATL do przodu na wykresie Formy z planned_load_daily (silnik simulate_expedition juz jest).

## [2026-07-27] Kafel 'Najblizszy cel' w DZIS (wariant C)
- GET /api/forma/event-prep -> event / target / stages / total_xss / verdict / ceilings / walls / simulation / taper / limits.
- KLUCZOWA KOREKTA (wykryta na zywo): najblizszym wpisem byla delegacja 'Kania' 29.07 i kafel liczyl do niej tapering. Rozdzielono: 'event' (najblizszy wpis) vs 'target' (najblizszy z planned_load_daily). Przygotowanie liczone ZAWSZE dla target; urlop/delegacja lada jako 'limits' (po drodze). Rest pomijany.
- LLM: /api/forma/analyze mode='event' - prompt dostaje etapy, sufity, werdykt, min TSB i JAWNIE liczbe dni do startu (pierwszy test mylil delegacje ze startem - doprecyzowane w patchu E4).
- Front (statyki, poza repo): forma.html #dzis-event + CSS .evp (grid 3 kolumny, na waskim 1); forma-render.js EVP/renderEventPrep/loadEventPrep, chip 'Najblizszy cel' (event_prep) w Dostosuj, domyslnie wlaczony, przycisk AI -> runAnalyze('event').
- Zweryfikowane na zywo: endpoint 200 (target=wyprawa 1-3.08, 372/305/231 XSS, verdict silnika, dzien 1 'powyzej rekordu dnia'), node --check forma-render.js OK, /forma.html zawiera #dzis-event, LLM zwraca plan w 2 akapitach.
- DO ZROBIENIA: wizualne sprawdzenie w przegladarce (claude-in-chrome) - nie robione w tej sesji.

## [2026-07-27] Odzież: rozbicie „Bottoms / Bibs” na „Bibs shorts” + „Trousers”
**Kryterium (użytkownik):** `Bibs shorts` = TYLKO krótkie spodenki do jazdy z wkładką. `Trousers` = szorty bez wkładki, długie spodnie, wszystkie długie tights/bibtights (nawet z szelkami).

- **Baza** (garage.db): 21 pozycji rozdzielone — 11 → `Bibs shorts`, 10 → `Trousers`. Kategoria „Bottoms / Bibs” już NIE ISTNIEJE (0 wierszy, 0 wystąpień w kodzie).
- **Rozstrzygnięcia graniczne (zatwierdzone):** wszystkie DŁUGIE → Trousers, w tym PEdALED Odyssey Winter Tights, Pearl Izumi AmFIB Bib Tight (no chamois), Rapha Core Winter Bibtights (no chamois). Castelli Thermal Bibshorts → Bibs shorts (ocieplane, ale krótkie). POC Cadence Cargo Shorts → Trousers (szorty bez wkładki).
- **Kod — 6 miejsc** (`qbot_web.py` ×5 + `planer-wyposazenia.html` ×1):
  1. prompt generatora zestawów (wymóg „spodenki z wkładką”) → kategoria `Bibs shorts`
  2. `RIDE_GEAR_SLOTS` → dwa sloty zamiast jednego
  3. logika liczby sztuk: `Bibs shorts` bez zmian (2, przy deszczu i ≥4 dni → 3); **`Trousers` → 1 para**
  4. `WORN_OK` → obie kategorie mogą być „na sobie”
  5. `CLOTH` (endpoint /api/planer/wyposazenie/kategorie) → obie
  6. `FAM` w Plannerze: `Bibs shorts`→[Bibs shorts]; `Trousers`→[Trousers, Mid Layer Bottom, Base Layer Bottom]
- **Dowód na żywo:** oba sloty w API zakładki Odzież; stara kategoria zniknęła; generator Plannera widzi obie; endpoint kategorii zwraca obie. Podział pozycji zweryfikowany po nazwach (9 aktywnych Bibs shorts + 2 archiwalne, 10 Trousers).
- **Kanał:** Qbot DEV MCP wypadł z sesji — praca przez `ssh q` (MacOS-MCP). UWAGA: **heredoc przez ssh dwukrotnie zawiesił kanał na ~4 min**, mimo czysto ASCII treści. Działający wzorzec: zapis skryptu lokalnie → `scp` → `ssh python3`.
- **[ZAMKNIETE 2026-07-28] DO ZROBIENIA:** `qbot_web.py` NADAL NIEZACOMMITOWANY — teraz już trzy zmiany: (1) is_set/set_items, (2) rejestr kategorii wyprawowych, (3) rozbicie Bottoms/Bibs. Commit jako qbot + push jako root.
