# QBot — Decyzje architektoniczne

> Jeden punkt prawdy dla decyzji projektowych. Najnowsze na górze.
> Konwencja: przed każdą edycją tego pliku → kopia `DECISIONS.md.bak.RRRRMMDD_GGMMSS`.

---


## 2026-07-06 -- DECYZJA: Komoot -> Karoo (wariant A) z bramka Telegram (przyciski)

**Status:** dziala end-to-end na zywo (test 2963663831 "TEST 18.05"). Commit 0e7bc29
(6 plikow) + poprawka telegram_reply_processor (przyciski zostaja przy bledzie)
+ handler webhooka w qbot_api.py (rownolegla sesja, uspiony).

**Po co:** trasy planowane w Komoot maja same trafiac do QBota (analiza nawierzchni/
POI/wysokosci) i na Karoo, bez recznego eksportu GPX.

**Model (wariant A, 1:1 jak RWGPS + bramka):**
1. Planujesz w Komoot -> natywny sync Komoot wrzuca gola trase na Karoo.
2. Timer co 5 min (komoot_watch.check_once) wykrywa nowa/zmieniona trase.
3. Telegram: powiadomienie z przyciskami [Analizuj]/[Pomin] + sygnatura.
4. [Analizuj] -> pelny ingest (komoot_watch.analyze_tour), material czeka w web.
   [Pomin] -> oznacz jako pominiete (do nastepnej zmiany changed_at).
5. Raport (LLM) + POI generujesz w web.
6. RECZNIE "Wyslij na Karoo" -> push kopii [Q]; poprzednia kopia QBota tej trasy
   jest kasowana (delete-before-create). Jedna kopia QBota per trasa.

**Sygnatura nazwy na Karoo:** `[Q] <nazwa> · <data utworzenia RRRR-MM-DD> · #<tour_id>`.
Zrodlo daty = swieze meta z Komoot (pole `date`), nie tabela stanu.

**Dedup (wariant A):** przed POST push_karoo robi GET listy tras Hammerhead i DELETE
kazdej z sourceId == "qbot-<route_id>". Push zawsze RECZNY (jak RWGPS).

**Watcher = tylko powiadamiaj:** komoot_watch sam NIE ingestuje i NIE pushuje. Analiza
dopiero po klikniet. przycisku. Pierwszy przebieg (pusta tabela) = SEED (~598 tras
oznaczonych jako widziane, bez pytania). Stan: qbot_v2.komoot_seen_tours.

**Ponowne pytanie (doprecyzowane 2026-07-06):** TYLKO przy zmianie GEOMETRII. Kolumna
`komoot_geo_sig` = hash zaokraglonych wspolrzednych; przy zmianie `changed_at` watcher
pobiera geometrie i porownuje -- taka sama (edycja nazwy/meta) => cicha aktualizacja bez
powiadomienia; inna albo brak bazy => pyta. Baza sig zakladana leniwie (seed nie liczy).

**Transport Telegrama:** callback z przyciskow dociera do AKTYWNEGO odbiornika updateow.
W trakcie sesji cron telegram_reply_processor dlugo dostawal 409 (inny konsument
getUpdates); po restartach 409 znikl i to on odbiera callbacki
(telegram_reply_processor.handle_komoot_callback). Rownolegle qbot_api.py ma handler
dla WEBHOOKA (uspiony, bo webhook niezarejestrowany). Oba wspolistnieja bezpiecznie:
Telegram to webhook ALBO polling -- po wlaczeniu webhooka polling milknie (409),
a handler qbot_api przejmuje. **Zablokowane 2026-07-06:** webhook jawnie usuniety (deleteWebhook), polling = transport kanoniczny.

**Prawa plikow:** outgoing/komoot musi nalezec do usera qbot (handler dziala jako qbot).
Jednorazowo: chown -R qbot:qbot outgoing/komoot (pliki zrobione przez DEV jako root
blokowaly nadpisanie -> [Errno 13]).

**Pliki:** komoot_auth.py, tools/komoot/client.py, komoot_ingest.py, komoot_watch.py,
qbot_web.py (push_karoo: encoder 1D elevation.polyline + dedup), telegram_reply_processor.py
(callback polling), qbot_api.py (callback webhook), deploy/qbot-komoot-watch.service (+ timer 5 min).

---

## 2026-07-06 -- DECYZJA: XSS (odpowiednik Xert Strain Score) liczony z ModelQ

**Status:** gotowe w QBot (walidacja + backfill), wpiete w wbal_replay/daily_job.
Port do QExt2 -- OSOBNA sprawa (nastepny krok, wymaga build+CI).

**Po co:** XSS ma pokazywac "jak ciezka byla jazda" wzgledem chwilowego pulapu
mocy (MPA), nie wzgledem stalego FTP. To rozni go od TSS: ta sama moc liczy
sie WIECEJ pod zmeczeniem. QExt2 potrzebuje tego on-device (jak ciezko juz
pojechales), operujac na danych pobranych na starcie jazdy (CP, W') -- co juz
dostaje. Wiec da sie policzyc bez dostepu do serwera w trakcie.

**Dlaczego NIE z TSS:** TSS to jedna zagregowana liczba (NP/FTP) -- nie zachowuje
momentu zmeczenia. XSS wymaga mocy sekunda-po-sekundzie + stanu W'bal w kazdej
chwili. To DOKLADNIE to, co liczy Krok 3 (wbal_replay.py) -- stad XSS dopisany
do tej samej petli, bez duplikacji.

**Sprawdzone:** QBot mial juz silnik strain (fitmodel/buckets.py: (P/FTP)^4) --
ale to jest wzgledem STALEGO FTP, blizej TSS, NIE XSS. XSS potrzebuje MPA.
Xert per-jazda strain/XSS NIE jest dostepny w bazie (xert_profile_snapshots.
strain = NULL; raw_json ma tylko dzienny completedXSS/xss_goal, nie per aktywnosc).

**Wzor (finalny):**
    fatigue(t) = 1 - wBal(t)/W'_eff        # 0 pelny bak -> 1 pusty
    strain_rate = (moc_3s/CP_eff) * (1 + XSS_BETA*fatigue) * (100/3600) * dt
    XSS = suma strain_rate przez cala jazde
- Kotwica 1h @ CP = 100 XSS Z DEFINICJI (przy moc=CP fatigue~0, wiec baza=100
  niezaleznie od BETA). Zweryfikowane syntetycznie: 100.0 dla BETA in {0.5,1,2}.
- fatigue liczony ze STANU wBal PRZED wydatkiem danej sekundy (spojnie z W'bal).
- moc: ta sama usredniona 3s co W'bal (spojnosc silnika).

**Kalibracja BETA (nie zgadywanie -- dopasowanie do Xerta):** brak per-jazda
Xert XSS, wiec kotwica = Xert `training_load` (=EWMA dziennego XSS, tau~42).
Policzono nasza EWMA-CTL (tau=42) z naszych XSS dla obu wariantow:
    BETA=0.5 -> EWMA-CTL 53.9
    BETA=1.0 -> EWMA-CTL 59.6   <-- wybrane
    Xert training_load (odniesienie) = 62.4
BETA=1.0 trafia ~4% (i nasza EWMA jeszcze sie "rozpedza" -- dane dopiero od
2026-05-21, ~7 tyg -- wiec realnie bedzie jeszcze blizej). BETA=0.5 zanizal.

**Zakres:** tylko TOTAL XSS (jedna liczba), bez podzialu Low/High/Peak
(decyzja Michal -- podzial wymagalby PP na Karoo, dzis nie wysylamy). Kolumny
`xss`, `xss_per_h` w fitmodel_wbal_ride. Backfill 22 jazd OK. Dzisiejsza jazda
(23496824503): XSS=100.4 (94.1/h). Liczy sie automatycznie z W'bal (krok 2d
daily_job) -- zero dodatkowej roboty per jazda.

**NIE zrobione (swiadomie):** (a) port do QExt2 -- osobny krok; (b) wyswietlanie
XSS w raporcie/Telegramie; (c) CTL/forma z XSS (mozna, gdy uzbiera sie wiecej
danych -- na razie EWMA rozpedza sie na 7 tyg).


## 2026-07-06 -- DECYZJA: wbal_replay.py wpiety na stale -> fitmodel_wbal_ride

**Status:** gotowe, dziala w `daily_job.py` (krok 2d, po cp_wprime/readiness).

**Kontekst:** `fitmodel/wbal_replay.py` (Krok 3, zwalidowany wczesniej dzisiaj:
0.49pp roznicy vs prawdziwe QExt2) byl samodzielnym skryptem diagnostycznym --
wyniki widoczne tylko przy recznym odpaleniu.

**Decyzja:** nowa tabela `qbot_v2.fitmodel_wbal_ride` (per external_id):
status (OK/NO_DATA/NO_BASELINE), ftp_base_w, wprime_base_kj, final_wbal_pct,
min_wbal_pct, liczniki tickow/zamrozen/postojow, pelny `segments_json`.
Funkcja `run_for_new_rides()` liczy TYLKO nowe jazdy (nie w tabeli), zapisuje
KAZDY status (nie tylko OK) -- unika pulapki z `fit_ingest.ingest_all_new`
(tam jazdy bez segmentu byly liczone w kolko, bo "przetworzone" bylo mylone
z "ma segment"; tu rozroznione od razu). Wpiete jako krok 2d w `daily_job.py`
(raz dziennie 4:45, po cp_wprime zeby miec swiezy FTP/W').

**Backfill wykonany dzisiaj:** 325 kandydatow (cala historia activity_record),
30 sekund. 22 jazdy OK (od 2026-05-21, kiedy zaczyna sie ftp_est_w), 303
NO_BASELINE (starsze, nie beda juz probowane w kolko). Dzisiejsza jazda
(23496824503): final=33.5%, min=0.0% -- zgadza sie z wczesniejszym recznym
testem co do przecinka.

**Nie zrobione dzisiaj (out of scope):** wyswietlanie tych danych gdziekolwiek
(raport jazdy, Telegram) -- na razie to tylko tabela w bazie, cichy backend
zbierajacy dane do przyszlej analizy/walidacji.


## 2026-07-06 -- DECYZJA: todayFactor z ModelQ (nigdy wczesniej nie bylo wysylane)

**Status:** gotowe, `qbot_api.py`, live-tested.

**Odkrycie (Michal):** RSRV na Karoo mial byc odpowiednikiem Garmin Stamina.
Sprawdzone w historii gita -- pole `todayFactor` NIGDY nie istnialo w
`/ride-readiness` (zero commitow je dodajacych/usuwajacych). QExt2 zawsze
dostawal default 1.0 z `json.optDouble("todayFactor", 1.0)`. To znaczy W'bal
`cf` i RSRV `baseReserve` ZAWSZE dzialaly na sztywnej 1.0, bez wzgledu na
realna forme dnia -- silniki byly gotowe, wejscie nigdy nie bylo podlaczone.

**Decyzja:** `todayFactor` = ModelQ `readiness_score` (HRV+RHR+sen, z-score,
juz istniejacy, wczesniej "backstage, nic go nie uzywalo") przez liniowy
mapping: `todayFactor = clamp(1.0 + 0.05*readiness_score, 0.5, 1.1)`.

**Zacisk SZEROKI (0.5-1.1), nie 0.85-1.05:** sprawdzony kod QExt2
(`rideReservePercent`) -- RSRV startuje z `todayFactor*100` BEZ dodatkowego
zacisku, podczas gdy W'bal `cf` przycina `readiness` do 0.85-1.05 SAM, w
miejscu uzycia (`RideDataAggregator.kt`). Wysylanie juz przycietego do
0.85-1.05 zubozyloby sygnal dla RSRV. Kazdy odbiorca przycina po swojemu.

**Wspolczynnik 0.05 -- sprawdzony na 30 dniach realnych danych przed wdrozeniem:**
zakres wynikowy 0.934-1.048, nigdy nie dotyka twardych granic (poza jednym
prawie-dotknieciem na gorze). Najgorszy dzien (score -1.31, "zmeczony") ->
0.934; najlepszy (score ~0.95, "swiezy") -> 1.048.

**Zweryfikowane live:** `/ride-readiness` zwraca teraz `todayFactor` (dzis:
0.982, z readiness_score=-0.36).

**WAZNE -- nie mylic z RSRV formula:** to naprawia tylko WEJSCIE do RSRV/W'bal
na Karoo. Czy sam WZOR RSRV (tempo TSS-penalty, tempo odbudowy 30min) faktycznie
"czuje sie" jak Stamina -- do oceny PO obejrzeniu kilku prawdziwych jazd z
realnym todayFactor, nie teraz na sucho. Patrz TODO.md sekcja RSRV.


## 2026-07-06 -- DECYZJA: kotwica W' z drogi -- weryfikacja mocy PO zdarzeniu W'bal=0%

**Status:** gotowe, `fitmodel/cp_wprime.py`, live-tested.

**Problem z prosta wersja (odrzucona):** zdarzenie QExt2 W'bal=0% NIE jest
niezaleznym dowodem numerycznym -- Karoo liczy to z TEJ SAMEJ liczby W', ktora
mu wyslalismy z `/ride-readiness`. Samo "doszlo do zera" nie potwierdza, ze
20.31 kJ to poprawna wartosc -- potwierdza tylko, ze urzadzenie poprawnie
liczy do zera to, co mu podalismy (obwodowe rozumowanie).

**Rzetelna wersja (wdrozona):** sprawdz MOC PO zdarzeniu 0% -- to jest
niezalezne od naszej liczby. Jesli rider realnie musial zwolnic do/ponizej CP,
model (CP+W') jest potwierdzony. Jesli dalej ciagnal wyraznie powyzej CP przez
`ROAD_ANCHOR_WINDOW_S=90` sekund (margines >5%), to fizyczny dowod, ze mial
jeszcze zapas ktorego model nie widzial -> W' PRAWDOPODOBNIE NIEDOSZACOWANE.

**Wynik na zywej jezdzie (2026-07-06, zdarzenie 0% o 10:30:44, CP_eff=241W):**
srednia moc w kolejne 90s = 307W -- WYRAZNIE powyzej CP. Nadwyzka pracy: ~6.0 kJ
ponad obecny model (20.31 kJ) -- sugeruje realne W' blizej ~26 kJ, nie 20.3 kJ.
**Status: CONTRADICTED** (nie CONFIRMED) -- czyli obecny estymator raczej
zanizony, nie zawyzony.

**Decyzja o dzialaniu (celowo konserwatywna):** kotwica NIGDY nie zmienia
automatycznie samej liczby `wprime_modelq_kj` -- tylko:
- status="confirmed" + obecna pewnosc="medium" -> podnosi do "high" + notatka.
- status="contradicted" -> NIE zmienia pewnosci w dol ani w gore, tylko dopisuje
  jawne UWAGA do `wprime_source` z konkretnym ~kJ niedoszacowania, do przegladu
  czlowieka. Jedno zdarzenie to za malo, zeby automatycznie przestrajac model.

**Zakres:** tylko BARDZO swieze zdarzenia (`ROAD_ANCHOR_FRESH_DAYS=14`) --
to sygnal z live-testu, nie archiwum. Parsowanie FIT odporne na dev-field bug
fitparse (ta sama technika co przy diagnozie 20142319334 -- patrz wczesniejszy
wpis 2026-07-06 o postoj/dropout).

**Do rozwazenia w przyszlosci (nie dzis):** po kilku takich zdarzeniach (nie
jednym) mozna by rozwazyc uzycie mediany "kotwic z drogi" jako trzeciej,
niezaleznej metody estymacji W' obok harvestu MMP -- ale to wymaga wiecej
danych niz jedna jazda.


## 2026-07-06 -- DECYZJA: raport jazdy na W' z ModelQ + auto-ingest Strony B co 30 min

**Status:** gotowe.

**1) Wykres W'bal w raporcie jazdy (`qbot3/rides/ride_report_builder.py`):**
byl liczony na W' z Xerta (`_xert_wprime`). Dodano `_modelq_wprime(cur, ride_day)`
-- W' z `fitmodel_daily.wprime_modelq_kj` dla dnia jazdy, fallback do Xerta TYLKO
gdy ModelQ nie ma wartosci (per-pole, jak w `/ride-readiness`). Tagi w raporcie
(`wprime_j`, `wbal_min_pct`) pokazuja prawdziwe zrodlo (`modelq` lub `xert`),
nie zawsze "xert".

**Przy okazji naprawiony bug:** `_wprime()` nigdy nie mial dolnego ograniczenia
`bal>=0` (byl tylko gorny `bal<=Wp`). Ujawnilo sie to na jezdzie 2026-07-06
(`wbal_min_pct=-33%`) po podmianie na mniejsze, dokladniejsze W' z ModelQ
(20.31 vs 22.4 kJ Xert) -- ten sam wysilek stanowi wiekszy % ubytku przy
mniejszej pojemnosci. Dodano `if bal<0: bal=0`. Po naprawie: 0% (zgadza sie
z niezaleznym pomiarem z Kroku 3 / wbal_replay.py dla tej samej jazdy).

**Uwaga:** ten wykres nadal uzywa PROSTSZEGO modelu niz Krok 3 (`wbal_replay.py`)
-- jeden usredniony tau na cala jazde (nie dynamiczny co sekunde), surowa moc
(bez usredniania 3s), brak bramki postoj/dropout. To wystarczylo do zgodnego
zrodla W', ale NIE jest tym samym silnikiem co QExt2/Krok 3. Pelne zrownanie
tych dwoch silnikow to oddzielna sprawa (patrz TODO.md punkt 5 -- integracja
wbal_replay.py na stale).

**2) Strona B (`fitmodel_qext2_ride`) nie mial automatycznego triggera:**
`ingest_all_new()` jest wywolywane w `daily_job.py`, ale ten job leci RAZ
dziennie o 4:45 -- jazda z 09:30 nie pojawilaby sie w tabeli do nastepnego
dnia. Dodano osobny, lekki skrypt `fitmodel/ingest_qext2_fit.py` (TYLKO
ingest_all_new, bez reszty daily_job -- xert_bench/week_planner nie maja sensu
czesciej niz raz dziennie) w cronie roota co 30 minut. Tania operacja (pomija
jazdy juz w bazie), ~58s na pelny katalog.

**Znana, nieblokujaca nieefektywnosc (nie naprawiona dzis):** `ingest_all_new`
sprawdza "juz przetworzone" przez obecnosc w `fitmodel_segment` -- jazdy bez
ani jednego stabilnego segmentu (MIN_START_OFFSET_SECONDS=1200, progi EF) NIGDY
tam nie trafiaja, wiec sa przetwarzane PONOWNIE przy kazdym uruchomieniu
(zweryfikowane: 16-17 plikow za kazdym razem, nie male malejace). Nieszkodliwe
(ON CONFLICT DO UPDATE/DO NOTHING), ale marnuje ~1 min co 30 min. Do poprawy
przy okazji (osobna flaga/tabela "processed_fit_files" zamiast polegania na
fitmodel_segment).


## 2026-07-06 -- DECYZJA: Krok 3 W'bal -- moc 3s zamiast surowej + walidacja na zywej jezdzie

**Status:** gotowe, zwalidowane, `fitmodel/wbal_replay.py`.

**Kontekst:** pierwsza prawdziwa jazda z build-140 QExt2 (2026-07-06 09:30-10:34,
external_id 23496824503) -- Strona A dziala w 100%, wszystkie 7 pol FIT
(qext2_wbal_pct, qext2_cp_eff_w, qext2_wprime_eff_kj, qext2_cf, qext2_wbal_zero,
qext2_readiness, qext2_rsrv_pct) obecne w kazdym z 3783 rekordow.

**Problem:** pierwsza wersja repliki (surowa moc z activity_record) dawala
srednia|diff|=5.6pp, max=13.9pp wzgledem prawdziwego qext2_wbal_pct z FIT-a.

**Przyczyna (potwierdzona w zrodle QExt2, RideDataAggregator.kt):** W'bal na
Karoo NIE jest karmiony surowa moca z sekundy -- subskrybuje
`DataType.Type.SMOOTHED_3S_AVERAGE_POWER` z SDK Karoo (log "PWR_3S"). To
usredniona moc 3-sekundowa, nie chwilowa.

**Decyzja:** replika usrednia ostatnie do 3 sekund `power_w` (rosnace okno na
starcie, potem trailing 3) PRZED podaniem do wzoru rozniczkowego Skiby.
Bufor 3s czyszczony na kazdej duzej dziurze (>=30s, postoj/dropout) -- nie
usredniac przez przerwe.

**Wynik walidacji na FIT (surowe cp_eff_w/wprime_eff_kj z urzadzenia, izolowany
test samego wzoru):** srednia|diff|=0.49pp, max=2.73pp (bylo 5.6pp/13.9pp).

**Wynik walidacji end-to-end (pelny potok: baza activity_record + ModelQ
FTP/W' z fitmodel_daily + moc 3s + bramka postoj/dropout, BEZ podgladania
wartosci z urzadzenia):** replika min W'bal=0.0% (prawdziwe: 0%), koncowe
W'bal=33.5% (prawdziwe: 33%). Roznica <1pp na koncu 64-minutowej jazdy.

**Przy okazji odkryte i wyjasnione (Michal, 2026-07-06):** `qext2_readiness`
na tej jezdzie = 0.9826 (nie domyslne 1.0). Zrodlo: `AthleteData.
applyBaroAdjustment()` mnozy todayFactor przez baroMultiplier (0.80-1.00,
korekta z cisnienia atmosferycznego) przy wczytaniu danych sportowca PRZED
jazda (RideDataAggregator.kt:234) -- "setup" liczony przed startem, nie blad
i nie stary cache.

**Uwaga do Kroku 3 dalej:** ingest `activity_record` (memo z wczesniej: "halted
2026-06-28") w rzeczywistosci DZIALA -- 5 aktywnosci po tej dacie w bazie,
najnowsza dokladnie do konca dzisiejszej jazdy (10:34:51). Wczesniejsza notatka
o zatrzymaniu ingestu byla nieaktualna/bledna -- zweryfikowane live 2026-07-06.


## 2026-07-06 -- DECYZJA: Rozroznianie POSTOJ vs ODPADNIECIE MIERNIKA W LOCIE (Krok 0, W'bal)

**Status:** aktywna, gotowe do wdrozenia w Kroku 3.

**Problem:** duze dziury w mocy (np. 38,9% pokrycia liczonego na caly czas trwania) moga miec dwie rozne przyczyny: (a) urzadzenie przestalo nagrywac (postoj -- jedzenie, awaria, swiadoma pauza) albo (b) miernik mocy odpadl, ale jazda i nagrywanie trwaly dalej (analogia: niewlaczony HR). Traktowanie obu tak samo psuje model W'bal -- (a) uzasadnia pelna odbudowe W', (b) NIE (sportowiec dalej pracowal).

**Dowod na zywo (activity_record, qbot_v2):**
- Postoj: jazda `18856959904` (2025-04-17), dziura 7280s. Zero wierszy w bazie w trakcie przerwy. Dystans przed i po dziurze identyczny co do metra (6787,27 m), predkosc przed = 0,0 m/s. -> 100% pewny postoj.
- Odpadniecie w locie: jazda `20142319334` (2025-08-22), 6 osobnych odcinkow bez mocy, ale urzadzenie CALY CZAS pisalo wiersze (gestosc ok. 1/s). Dwa odcinki: 795s/4432m i 947s/5257m przy 6-7 m/s. -> jazda trwala, miernik po prostu nie raportowal mocy.
- Skala: rekordy "jade, ale bez mocy" to ok. 1,4% wszystkich wierszy w calej bazie (33 366 / 2 350 120) -- rzadkie, zgodnie z oczekiwaniem Michala.

**Decyzja (regula klasyfikacji dziury):**
1. Policz gestosc wierszy w dziurze = liczba_wierszy_w_dziurze / czas_trwania_dziury_s.
2. Gestosc ok. 0 (brak wierszy) + dystans niezmieniony (delta ponizej progu szumu) + predkosc przed ok. 0 -> **POSTOJ** -> pelna odbudowa W' po przerwie (wysoka pewnosc).
3. Gestosc ok. 1 (wiersze sa, tylko power=NULL) + dystans rosnie w trakcie -> **ODPADNIECIE MIERNIKA W LOCIE** -> W'bal ZAMROZONY na czas dziury (bez odejmowania, bez odbudowy); odcinek WYLACZONY z dopasowania CP/W' w Kroku 1.
4. Wszystko pomiedzy (niejednoznaczne) -> NIEPEWNE, bez darmowego bonusu za odpoczynek, traktowac konserwatywnie.

**Do zrobienia w Kroku 3:** wdrozyc powyzsza regule jako bramke przed liczeniem W'bal tick-po-ticku (zamiast jednego progu >=30s traktowanego zawsze jako "stan nieznany").

## 2026-07-03 — DECYZJA: Raport web — warstwa kwadratow StatsHunters na mapie

**Status:** aktywna.

**Problem:** brak podgladu na mapie raportu, ktore kwadraty explorer-tiles (z14) trasa zdobywa, a ktore juz mam.

**Decyzja:** osobny endpoint `GET /api/routes/{route_id}/tiles?margin=N` (qbot_web.py) liczy kafle z14 z geometrii trasy i porownuje z posiadanymi ze StatsHunters (`tools/tile_store.fetch_tiles`, share w env `STATSHUNTERS_SHARE_ID`, cache 24h). Statusy: `new` (trasa, nie mam) / `keep` (trasa, mam) / `owned` (otoczka, mam) / `empty` (otoczka, wolne); `margin` = szerokosc pasa otoczki w kaflach (domyslnie 3). Render w `raport-render.js` (funkcja `setupTiles`): osobny pane `tiles` pod linia trasy, `L.rectangle` per kafel, przycisk "Kwadraty: wl/wyl" w pasku `.map-ctl` + licznik `.map-ctl-info`.

**Pulapka (udokumentowana):** `tools/tile_store.py` uzywa slippy z14 (zgodne ze StatsHunters), a `tools/gpx_history_loader.py` INNEJ siatki 0,01 st. — NIE mieszac; do tej warstwy tylko `tile_store` + SH.

**Cache Cloudflare:** `raport-trasy.html` laduje js/css z `?v=DATA`. Edge cache'uje po pelnym URL -> kazda zmiana js/css wymaga PODBICIA `?v=` w `raport-trasy.html` (to bylo zrodlo "zmiany nie widac"; twardy reload nie pomaga).

**Dowod (trasa 55945214):** endpoint 200, `route=85, new=71, keep=14, owned_total=10803`, z otoczka empty lacznie 331 kafli. Commity `qbot_web.py`: `f333b54` (endpoint), `cdbd0a7` (empty). Pliki js/css/html poza repo. Pelna dok.: `docs/RAPORT_WEB.md`.

## 2026-07-02 — DECYZJA: ATRAKCJE jako opcjonalna warstwa POI (Google, ≤1,5 km) z przełącznikiem per-trasa + polecenie Alberta

**Status:** aktywna decyzja architektoniczna.

**Problem:** po przejściu na Google-only + GeoNames (patrz wpis niżej) atrakcje znikły z warstwy (pochodziły z Overpass). Atrakcje nie są krytyczne dla większości tras (trening), ale bywają potrzebne na wyprawy/zwiedzanie.

**Decyzja:** atrakcje to OPCJONALNA warstwa, domyślnie WYŁĄCZONA, sterowana TRWAŁYM przełącznikiem per-trasa i poleceniem Alberta.
- **Źródło:** Google Places (searchNearby), typy: `tourist_attraction, historical_landmark, museum, art_gallery, church` (kościoły traktowane jako zabytki). BEZ zoo, parków, wesołych miasteczek, akwariów.
- **Promień:** twardo ≤ 1,5 km od śladu (`attractions_m=1500`); próbkowanie co ~3 km, radius 2 km, potem filtr do 1,5 km.
- **Przełącznik steruje POBIERANIEM, nie tylko wyświetlaniem:** gdy OFF (domyślnie) atrakcje nie są w ogóle odpytywane w Google ani zapisywane; gdy ON — każde przeliczenie POI dociąga je do `route_poi_layer` i raport pokazuje sekcję atrakcji. Baza trzyma tylko to, co świadomie włączone.
- **Trwałość:** nowa tabela `qbot_v2.route_poi_prefs (route_id PK, attractions_enabled bool, updated_at)`. `ensure_route_poi` czyta preferencję przy KAŻDYM przeliczeniu (przeżywa pełny recompute; klucz po route_id, więc przeżywa też re-import trasy).

**Polecenie Alberta:** nowe narzędzie `route_attractions(route_id, enable)` — ustawia preferencję i od razu odświeża POI (scope=poi), więc zmiana widoczna natychmiast. Rejestr narzędzi i instrukcja Alberta (`_SYSTEM`) zaktualizowane w tym samym commicie (twarda zasada synchronizacji).

**Skutek uboczny naprawiony przy okazji — płaskie trasy w raporcie:** `read_canonical_route` traktowało 0 wierszy w KAŻDEJ warstwie kanonicznej jako „brak" → cały raport spadał na `legacy_fallback`, chowając sekcje kanoniczne (nawierzchnia, POI, atrakcje, przewyższenia). Płaska trasa (Mazowsze) ma legalnie 0 `route_climb_events`, więc ZAWSZE leciała fallbackiem. Wprowadzono `_CANONICAL_OPTIONAL_LAYERS = {route_climb_events}` — pusta warstwa pochodna nie degraduje już raportu. Trasa 55864231 czyta się teraz jako `canonical`.

**Dowód (55864231):** przełącznik ON → 69 atrakcji w bazie, WSZYSTKIE ≤ 1,5 km, na całej trasie; OFF → 0 (delete+insert czyści). Raport (`read_path=canonical`) pokazuje linię „Atrakcje (zabytki/muzea/turystyczne, ≤1,5 km): 69 — źródło: Google Places". Komenda Alberta ON/OFF przetestowana end-to-end.

**Atrybucja:** atrakcje pochodzą z Google Places (adnotacja w raporcie).

## 2026-07-02 — DECYZJA: POI — miejscowości z lokalnego GeoNames, Overpass w POI wyłączony domyślnie (Opcja 1)

**Status:** aktywna decyzja architektoniczna.

**Choroba (root cause):** aktywny analizator POI (`analyze_route_poi_artifact`, ścieżka v2) liczył chunki sekwencyjnie pod JEDNYM globalnym budżetem czasu (`deadline_sec`≈80 s). Wąskim gardłem było Overpass (rzędu ~88 s na trasę, agresywny throttling z tego serwera), więc po przekroczeniu budżetu cały OGON trasy lądował jako `missing_chunks` (status PARTIAL). Efekt: każdy wolniejszy przejazd miał ucięte POI od pewnego km w górę. Overpass w POI dostarczał NIE nawierzchnię, lecz: miejscowości (`place=*`), wodę (`drinking_water`/`water_tap`), część zaopatrzenia OSM i atrakcje.

**Decyzja (Opcja 1):** Overpass w pipeline POI **wyłączony domyślnie** (`buffers["overpass_enabled"]=False`). Domyślna ścieżka: zaopatrzenie z Google Places + miejscowości z lokalnego **GeoNames** (offline). Overpass wraca tylko świadomie, flagą, na wyprawę.

**Miejscowości → GeoNames (offline, CC-BY):**
- Dane: dumpy GeoNames per kraj, przefiltrowane do klasy cech `P` (miasto/wieś), zapisane jako lekkie TSV w `/opt/qbot/artifacts/geonames/` (`PL_places.tsv`: 47 930 miejscowości). BEZ progu populacji — każde miejsce klasy P jest dobre.
- Nowy moduł `qbot3/routes/geonames_places.py` (bez importów z qbot3 → zero cykli). Skanuje WSZYSTKIE `*_places.tsv`, więc dołożenie `IT_places.tsv`/`ES_places.tsv` na wyprawę nie wymaga zmiany kodu.
- Projekcja w `route_analyzer._geonames_town_candidates`: **lokalne minima** odległości do trasy, nie globalnie najbliższy punkt. Dzięki temu na trasie-pętli miejscowość dostaje wpis przy KAŻDYM przejściu obok niej (noga wyjazdowa i powrotna) → METEO ma pokrycie schronienia na całej długości. Próg `town_max_m` domyślnie 3000 m (parametryzowalny).

**Woda:** za flagą `include_water` (domyślnie OFF). W PL brak wody w warstwie jest zgodny z projektem; docelowo offline OSM na południe Europy.

**Zaopatrzenie:** Google jest primary (bez zmian). Linie shop/amenity Overpass zostają tylko dla trybu z włączonym Overpass.

**Atrakcje:** znikają z warstwy domyślnie (pochodziły z Overpass; analizator nie dociąga atrakcji z Google do `route_poi_layer`). Niekrytyczne — do ewentualnej osobnej decyzji (re-enable flagą na wyprawę albo dodać fetch Google attractions).

**Strażniki (defense-in-depth):**
- `ensure_route_poi`: wynik gorszy niż COMPLETE (PARTIAL/ERROR) **nie nadpisuje** istniejącego COMPLETE (rollback, status `SKIPPED_KEPT_COMPLETE`). Pełny wynik zawsze wygrywa.
- Recompute **zastępuje** całą warstwę POI trasy: `DELETE route_poi_layer WHERE route_base_id` przed insertem. Wcześniej UPSERT po `(route_base_id, poi_key)` tylko doklejał — stare punkty z poprzedniego źródła zostawały (stąd narastanie 20→40→60 i utrzymywanie się Overpassowych townów po migracji).
- Zdjęty cap `town_deduped[:20]` (brał 20 NAJNIŻSZYCH km → gubił całą tylną połowę trasy).

**Dowód (trasa 55864231, 64 km, pętla):** recompute ~1,9 s (było ~90 s), `technical_completeness=COMPLETE`, `missing_chunks=0`, miejscowości 0,0–62,9 km (58 szt., 28 za km 33, 10 za km 50). METEO `_nearest_town_before`: km40→Michałów(39,3), km50→Leśniakowizna(47,9), km55→Kobylak(54,7), km60→Siwki(59,1). Przed poprawką wszystkie cofały do ≤ km 32,85.

**Bez zmian w rejestrze narzędzi:** `tool_registry.py` nietknięty → instrukcja Alberta (`_SYSTEM`) nie wymaga aktualizacji.

**Atrybucja:** dane miejscowości pochodzą z GeoNames (https://www.geonames.org, licencja CC-BY 4.0). Stopka raportu tras zawiera adnotację.


## 2026-07-02 — DECYZJA: route_recompute z parametrem scope (all | poi)

**Status:** wdrozone. Testy zielone (test_route_precompute_orchestrator: 3 nowe routingu + 1 live skip; test_route_precompute_trigger 17). Okablowanie zweryfikowane na zywo (narzedzie ma arg scope, prompt Alberta zawiera scope='poi', sygnatura orkiestratora zaktualizowana).

**Problem/potrzeba (2 scenariusze uzytkownika):**
1. Pobralem trase z RWGPS, ale nie zdecydowalem sie jej przeliczyc — chce uruchomic pelny przelicz recznie.
2. Wracam do JUZ przeliczonej trasy po ~pol roku — chce odswiezyc TYLKO POI (sklepy/woda/godziny), bo reszta danych (osie, nawierzchnia, wysokosci) sie nie zmienia.

Dotychczas route_recompute robil ZAWSZE pelny przelicz (przebudowa route_base od GPX + cala sekwencja). Brak zawezania.

**Decyzja:** route_recompute dostaje opcjonalny scope. Pelny przelicz pozostaje DOMYSLNY (scenariusz 1); dokladamy tryb POI-only (scenariusz 2). NIE zawezamy calkowicie do POI — oba tryby potrzebne.

**Implementacja:**
- route_precompute_orchestrator.ensure_route_precompute(): nowy arg scope="all"|"poi" (walidacja ValueError dla innych). scope="all" = dotychczasowa sciezka (przebudowa base + _effective_job_sequence + pruning do 3 wersji). scope="poi" -> nowa funkcja _ensure_route_precompute_poi_only.
- _ensure_route_precompute_poi_only(): NIE wola ensure_route_base (nie parsuje GPX), odczytuje istniejacy aktywny route_base (_route_base_row); jesli brak -> LookupError z podpowiedzia "uruchom pelny przelicz scope='all'". Uruchamia WYLACZNIE job route_poi (ensure_route_poi, ktory od 2026-07-02 pobiera POI na zywo + zapisuje route_poi_meta). Rejestruje w route_precompute_jobs. NIE przycina wersji (POI-only nie tworzy nowej wersji). Zwrotka: scope="poi", retention=None.
- Zwrotka pelnego przeliczu dostala pole scope="all".
- tool_registry._load_route_recompute_tool: arg scope w args_schema + opis kiedy 'all' a kiedy 'poi'; wrapper mapuje warianty (poi/tylko_poi/...) na "poi", reszta -> "all"; note zalezny od scope.
- Prompt Alberta (qbot3/llm/albert.py _SYSTEM): zaktualizowany w TYM SAMYM commicie (twarda zasada: zmiana narzedzia = zmiana promptu razem) — opisuje kiedy scope='all' (trasa pobrana lecz nieprzeliczona / po odmowie w Telegramie), a kiedy scope='poi' (odswiezenie samego POI juz policzonej trasy).
- Testy: TestRoutePrecomputeScopeRouting (bez zywej bazy) — walidacja scope, scope='poi' omija ensure_route_base, scope='all' domyslnie do niej siega.

**Dowod na zywo (POI-only fetch) ODLOZONY:** sciezka POI-only wola ensure_route_poi = realny fetch Google Places/Overpass (koszt API). Nie uruchamiano automatycznie — to czesc osobno oczekujacego "finalnego przeliczenia trasy testowej", ktore przy okazji zapelni route_poi_meta.

**Nastepne (zatwierdzone, osobno):** ozywienie landcover w ocenie nawierzchni przez WorldCover (lokalne kafle zamiast Overpass) — wymaga osobnego doprecyzowania (mapowanie klas, weryfikacja na trasie); tylko dla odcinkow bez tagu OSM (tag wygrywa).

---

## 2026-07-02 — DECYZJA: nowa tabela route_poi_meta + raport czyta POI WYLACZNIE z bazy (przeciek nr 2)

**Status:** wdrozone. DDL zaaplikowany na zywo (23 kolumny), writer/kanoniczny odczyt/raport podlaczone, testy zielone (test_route_report 64, test_route_poi_store, test_route_canonical_read, test_poi_open_window 5). Dowod na zywo (trasa 55864231): raport czyta 13+12+2+20 POI z route_poi_layer, version-guard=OK.

**Problem (przeciek nr 2 — krok 5 / raport):** qbot_route_report_tool czytal POI z DWOCH miejsc: licznik z bazy, ale TRESC (nazwy sklepow, godziny, luki, klastry) bezposrednio z plikow /opt/qbot/artifacts/reports/poi_analysis_<id>_*.json oraz poi_positions_<id>.json (funkcje _read_poi_analysis_cache i _read_poi_positions_cache globowaly dysk po numerze trasy). To ten sam typ przecieku co krok 3 — raport ma czytac z kanonicznej bazy, nie z przypadkowych artefaktow.

**Brakujace dane (opcja B, wybrana przez uzytkownika):** metadane JAKOSCI analizy POI sa liczone na poziomie CALEJ trasy (nie per-punkt) przez analyze_route_poi_artifact: supply_status, technical_completeness, najdluzsza luka, liczniki open/unknown/closed, poi_source_mode, google_supply_count, missing_chunks (ktore chunki nie pobraly sie z Overpass). Te nie mieszcza sie w per-punktowej route_poi_layer i nie da sie ich odtworzyc z zapisanych punktow (missing_chunks to artefakt momentu pobrania). Decyzja: nowa tabela.

**Nowa tabela qbot_v2.route_poi_meta** (sql/route_poi_meta_v1.sql): jeden wiersz na wersje trasy (UNIQUE route_base_id), dziecko route_base ON DELETE CASCADE (zero sierot, kasuje sie z trasa jak reszta warstw). Kolumny: analysis_status, supply_status, technical_completeness, supply_longest_gap_km/_from_km, supply_open/unknown/closed_count, poi_source_mode, google_supply_count, missing_chunks_count, km_from/km_to, avg_speed_kmh, fetched_at, missing_chunks_json, buffers_json.

**Zmiany:**
- route_poi_store.py: _build_poi_meta_row + _upsert_route_poi_meta; ensure_route_poi zapisuje meta w TEJ SAMEJ transakcji co punkty (fetched_at = moment pobrania). Zwrotka dostala supply_status/technical_completeness/missing_chunks_count/fetched_at.
- route_canonical_read.py: _poi_meta_row czyta route_poi_meta; read_canonical_route wystawia canonical_poi_meta.
- qbot_route_report_tool.py: _read_poi_analysis_cache i _read_poi_positions_cache przepisane — czytaja WYLACZNIE z bazy przez read_canonical_route (route_poi_layer + canonical_poi_meta), zero globowania dysku. Zwracaja ten sam ksztalt co dawny cache dyskowy (mapowanie km_on_route->route_km, distance_from_route_m->distance_to_track_m, opening_hours->opening_hours_osm, provider->open_source), wiec render POI bez zmian. generated_at = route_poi_meta.fetched_at. Dodano linie raportu "Dane POI z dnia: RRRR-MM-DD".

**Version-guard:** dane POI sa Z DEFINICJI z aktywnej wersji trasy (czytane z route_poi_layer pod aktywnym route_base), wiec kotwiczymy blok na route_artifact_id + sha256 z route_base (identyczne z aktywna wersja) -> guard OK. NIE kopiujemy created_at/updated_at (inne zrodlo dat -> falszywy mismatch).

**Do domkniecia przy finalnym przeliczaniu:** route_poi_meta zapelni sie dla istniejacych tras dopiero przy recompute (writer zweryfikowany testami + na zywo, ale realny wiersz meta powstanie przy pobraniu). Do 55864231 obecnie meta=NULL -> raport pokazuje POI z bazy, ale supply_status/generated_at puste do przeliczenia.

**Otwarte (pytanie uzytkownika):** czy route_recompute umie zawezic zakres do samego POI (bez pelnego przeliczania) — do zbadania osobno.

---

## 2026-07-02 — DECYZJA: zasilanie route_poi_layer ZAWSZE na zywo; usuniety przeciek czytania cudzych plikow z dysku + mechanizm 14-dni

**Status:** wdrozone i zweryfikowane (import OK, funkcja/stala usuniete, testy zielone: test_route_poi_store, test_poi_open_window, test_route_report 64).

**Problem (przeciek granicy):** ensure_route_poi (writer warstwy route_poi_layer, krok 3 — telegram_confirm/precompute) mial funkcje _cached_route_poi_analysis, ktora ZANIM zapytala Google/OSM, przeszukiwala /opt/qbot/artifacts/reports/ (i /old/reports/) po plikach poi_analysis_<route_id>_*.json i podnosila najnowszy pasujacy PO SAMYM NUMERZE TRASY. To lamie zasade granicy: writer bazy wolno zasilac WYLACZNIE z jego wlasciwego zrodla (tu: Google Places + Overpass na zywo, przez analyze_route_poi_artifact), nigdy z cudzych, niekontrolowanych artefaktow lezacych we wspolnym folderze raportow. Zbadano na zywo (trasa 55864231): job route_poi w precompute trwal 71 ms (odczyt pliku), nie kilka-kilkanascie s (realny fetch) — dowod, ze krok 3 recyklingowal plik z 2026-06-30 zamiast pobrac swieze dane. Plik mial nawet metke project_id="tuscany_2026" (inny projekt).

**Zasada (doprecyzowana wczesniej z uzytkownikiem):** autorytet zrodla jest PER WARSTWA. Kazde dziecko trasy wolno zasilac tylko z jego zadeklarowanego zrodla — zewnetrzne API (Overpass/Google/opentopodata) ALBO wewnetrzne narzedzie QBot na lokalnych kaflach (WorldCover). Lokalny cache Overpass w analyze_route_poi_artifact (_geofabrik_cache_candidates, /artifacts/overpass_cache) jest DOZWOLONY — to wewnetrzne zrodlo warstwy, nie cudzy raport. Zakazane bylo tylko podnoszenie gotowych poi_analysis_*.json z /artifacts/reports.

**Co zrobiono w qbot3/routes/route_poi_store.py:**
- Usunieto funkcje _cached_route_poi_analysis w calosci.
- ensure_route_poi ZAWSZE wola analyze_route_poi_artifact (zywe Google+Overpass) -> route_poi_layer. fetched_at = moment tego pobrania (uczciwe; wczesniej bywalo klamstwem "teraz" nad starym plikiem).
- Usunieto stala POI_CACHE_MAX_AGE_DAYS=14 i cala logike auto-refresh po 14 dniach (cofniete z commita 3ded59b). Powod: auto-odswiezanie po cichu generowaloby platne zapytania Google przy samym otwarciu starego raportu, bez wiedzy uzytkownika. Odswiezenie ma byc JAWNA decyzja uzytkownika (route_recompute), a raport ma pokazywac date danych POI.
- Zostawiono status="stale" per punkt (_stale_after_for_item, timedelta) jako uczciwy znacznik wieku pojedynczego POI.

**Zwiazane / do zrobienia:** (krok 5) raport route_report nadal czyta POI bezposrednio z pliku (_read_poi_analysis_cache) zamiast z route_poi_layer — osobny przeciek tej samej granicy, do naprawy w nastepnej kolejnosci. Pytanie otwarte: czy route_recompute umie zawezic zakres do samego POI.

---

## 2026-07-02 — DECYZJA: usuniecie warstwy route_landcover_layer (OSM land-cover) — zastapiona przez WorldCover/shade

**Status:** wdrozone. Kod usuniety, tabela qbot_v2.route_landcover_layer ZOSTAJE (usuniemy przy pelnym przeliczaniu wszystkich tras).

**Powod:** route_landcover_layer (OSM land-use przez Overpass) i route_shade_layer (ESA WorldCover, lewo/srodek/prawo od osi) opisuja to samo — otoczenie trasy. WorldCover wygral: dokladniejszy, aktualny, uzywany w raporcie (sekcja A0B). Legacy landcover trafial do raportu WYLACZNIE jako liczba w liczniku warstw, zadna jego tresc nie byla renderowana. Dodatkowo jego job pobieral z Overpass ~48 s przy kazdym przeliczeniu trasy (zbadano na zywo, trasa 55864231: landcover job 23:06:45->23:07:33). Decyzja uzytkownika: nie zostawiac martwych warstw ("za tydzien znow bedziemy analizowac co to jest").

**Co usunieto:**
- qbot3/routes/route_landcover_store.py (writer) + tests/test_route_landcover_store.py — pliki skasowane.
- route_precompute_orchestrator.py: route_landcover usuniety z JOB_SEQUENCE (+ import). Sekwencja bazowa: route_base, route_surface, route_poi (+ opcjonalnie route_shade, route_elevation za bramkami).
- route_canonical_read.py: route_landcover_layer usuniety z _CANONICAL_LAYER_ORDER (bramka kompletnosci) i z budowanego slownika layers; funkcja _landcover_rows skasowana.
- qbot_route_report_tool.py: route_landcover_layer usuniety z licznika warstw A0.
- Testy zaktualizowane: test_route_report, test_route_precompute_trigger, test_route_precompute_orchestrator, test_route_canonical_read, test_route_poi_store.

**Zmiana kontraktu land_cover_preferred_source:** wczesniej "worldcover_shade" gdy pokrycie shade, inaczej "osm_landcover_legacy". Po usunieciu legacy: "worldcover_shade" gdy pokrycie, inaczej "shade_none". Raport renderuje te wartosc verbatim (landscape_source: ...).

**Granica (wazne):** to NIE dotyczy landcover jako kontekstu WEWNATRZ silnika nawierzchni (route_surface_engine._refine_context uzywa landcover/geologii do wnioskowania surface na odcinkach bez tagu OSM). To osobna logika w pamieci, nietknieta. Usunieta zostala tylko osobna, materializowana warstwa-tabela route_landcover_layer.

---

## 2026-07-01 — DECYZJA: route store — wersjonowanie, retencja (keep=3), purge i narzedzia tras Alberta (list/recompute/delete)

**Status:** wdrozone i zweryfikowane na zywo. Pelna dok.: docs/ROUTE_STORE.md.

**Wersjonowanie:** aktywny plik GPX ma STALA nazwe `rwgps_<id>.gpx`; przy zmianie tresci poprzednia wersja archiwizowana jako `rwgps_<id>_<sha10>.gpx` (`tools/rwgps/client.py`). Nowy `route_version_key` = nowy `route_base` (stare zostaja), aktywna = najnowsza. Odrzucono zmiane nazw po sha (dotknelaby ~9 zywych plikow).

**Retencja:** `qbot3/routes/route_versions.py` (`prune_route_versions keep=3`, dry-run domyslnie, aktywna nigdy nie kasowana) + auto-hook po precompute w `route_precompute_orchestrator.py`. CLI: `scripts/route_versions_cli.py`.

**Purge:** `scripts/route_store_purge.py` `purge_route(route_id, confirm)` — dwustopniowo (podglad / realne kasowanie), kasuje route_base+artifacts (kaskady) + surowka + pliki. Kanal admin: `dev_route_store_purge` w `/root/qbot-dev-mcp/server.py` (poza repo).

**Narzedzia Alberta:** `route_list` (odczyt), `route_recompute` (write, aktywna wersja), `route_delete` (write, DWUSTOPNIOWO: podglad -> confirm=true po zgodzie). Rejestr `tool_registry.py`, prompt `albert.py`.

**Trzy warstwy bezpieczenstwa zapisow otwarte WASKO dla tras** (masowe kasowanie i inne destrukcje dalej blokowane): (1) straznik destrukcji `agent_runtime._is_destructive_query` + wyjatek `_looks_like_route_delete_request`; (2) whitelista realnych zapisow w `agent_runtime` (`_execute_single_tool` + `_execute_real_write_tool`); (3) allowlista walidatora `safety._ACTION_ALLOWLIST` (przez `_LEGACY_EXTRA_ACTIONS`). Zabezpieczenie kasowania trzyma dwustopniowy `route_delete`.

**Uzasadnienie kasowania z czatu:** trase zawsze mozna ponownie pobrac z RWGPS.

## 2026-07-01 — DECYZJA: Telegram — koncowe powiadomienie po potwierdzeniu rowniez dla "juz policzone", z czasem liczenia

**Status:** naprawione i zweryfikowane (28 testow zielonych; live #21 i #22). Pelna dok.: docs/TELEGRAM_ROUTE_CONFIRM.md.

**Przyczyna buga:** worker `route_precompute_trigger.py` wysylal koncowe powiadomienie tylko na sciezce "faktycznie przeliczono". Gdy trasa byla juz policzona, funkcja wychodzila w galezi "already complete -> skipped" PRZED wysylka -> brak powiadomienia (ani sent, ani failed).

**Naprawa:** koncowe powiadomienie wysylane TAKZE na sciezce skipped (sukces, tekst "byla juz kompletna"). Idempotencja po `launch_audit_turn_id`.

**Czas liczenia (wariant B):** z metek jobow (`route_precompute_jobs.layer_status_json`: min `started_at` -> max `finished_at`), formatowany `_format_duration_pl`, wstrzykiwany do tekstu ("Czas liczenia: X"). Odrzucono wariant A (czas od TAK) jako mylacy przy "juz policzone".

**action_id audytu:** gdy wynik nie niesie `pending_action_id` (worker CLI), brany z wiersza launch audit -> wpis finalny wiaze sie z numerem akcji.

**Wdrozenie:** worker to swiezy podproces przy kazdym TAK -> poprawka dziala bez restartu qbot-api.

## 2026-07-01 — DECYZJA: RWGPS nowej trasy najpierw pyta przez Telegram, a analiza startuje dopiero po potwierdzeniu

**Status:** wdrożone w webhooku RWGPS, workerze precompute i Telegram gateway.

**Decyzja:** po wykryciu nowej trasy RWGPS worker w trybie `--await-confirmation` materializuje tylko import i tworzy jawny `telegram_pending_actions` o `action_type=confirm_route_analysis`, a następnie wysyła pytanie do aktywnego `chat_id` przez Telegram. Dopiero odpowiedź `tak` uruchamia pełny canonical precompute tej konkretnej trasy.

**Zasada:** ten sam `route_id` / wersja artefaktu nie może spamować Telegrama wielokrotnie. Idempotencja jest oparta o `confirm_route_analysis` + `route_artifact_sha256` / `route_version_key`, a stan jest widoczny w `telegram_pending_actions`, `telegram_conversations` i `telegram_conversation_turns`.

**Naprawa runtime:** cache WorldCover / shade został przeniesiony na writable default `QBOT_WORLDCOVER_DIR=/opt/qbot/artifacts/worldcover`, bo stary `data/worldcover` był root-owned i wywracał `route_shade` podczas precompute.

**Aktualizacja:** pytanie Telegram teraz niesie jawny numer pending action (`#18 ...`), a odświeżenie `expires_at` dzieje się tuż przed realnym `sendMessage`, żeby użytkownik nie potwierdzał wygasłej akcji i żeby odpowiedzi `18 TAK` / `#18 NIE` były jednoznaczne.

**Doprecyzowanie runtime:** odpowiedzi Telegram i renderer kontekstu nie mogą zakładać, że `date_resolution` albo wynik writera zawsze jest słownikiem; `None` ma być traktowane jako brak danych, a nie wyjątek.

**Doprecyzowanie stanu:** `confirm_route_analysis` może przejść do `executed` dopiero po zapisaniu trwałego launch-audytu w DB. Samo `Popen()` bez audytu oznacza `failed`, a numerowane odpowiedzi Telegram nie mogą spadać do ogólnego `qbot.query` fallbacku.

**Doprecyzowanie logów:** log worker-a dla Telegram confirm nie może wskazywać na `/tmp`; używa katalogu kontrolowanego przez QBot pod `/opt/qbot/artifacts/logs/rwgps_confirmations/`, tworzonego bezpiecznie przy pierwszym użyciu.

**Doprecyzowanie uruchomienia:** worker po zakończeniu precompute czeka krótko na trwały `route_precompute_launch_audit`, bo zapis audytu i start procesu mogą się minąć o ułamek sekundy; finalny Telegram jest wysyłany dopiero po znalezieniu tego śladu.

## 2026-07-01 — DECYZJA: modul naprawy tras (naprawa-trasy.html) zaparkowany na zewnetrznej awarii Valhalli

**Status:** wdrozone i dziala na WEB (qbot-web, /naprawa-trasy.html + 4 nowe
endpointy w qbot_web.py). Zatrzymane na przejsciowej awarii publicznej Valhalli
(nginx 502) - do dokonczenia weryfikacji odcinka przy drodze S8 po powrocie uslugi.

**Decyzja:** pelne podsumowanie architektury, wszystkich decyzji (dopasowanie po
km nie po segment_index, kotwice cofniete w dobra nawierzchnie, progresywne
probkowanie promienia 0.3/1.0/2.0/3.0km, use_roads=0.7, brak limitu dlugosci
per-kandydat, regula "przyzwoity grade" dla tracktype, min. 200m na alert) oraz
otwartych problemow (dwa niezgodne systemy oceny nawierzchni A/B - do rozstrzygniecia
w sesji "generator tras", detekcja slepych zaulkow, cap na cala trase) jest w
docs/PROJEKT_NAPRAWA_TRAS.md - NIE duplikowac tutaj, czytac tamten plik jako
zrodlo prawdy dla tego modulu.

**Zasada:** modul to dzis czysty PODGLAD (Valhalla + trace_attributes), bez
zapisu/zszycia zaakceptowanego objazdu z powrotem do trasy - eksport zlozonej
trasy to niezbudowany, naturalny nastepny krok.

**Kontrakt:** kod w qbot_web.py jest w duzej czesci uncommitted (jak i inne pliki
z rownoleglej sesji Cowork - patrz `git status`) - przed commitem zweryfikowac
liste plikow, nie robic zbiorczego `git commit -a`.

---

## 2026-07-01 — DECYZJA: RWGPS webhook najpierw materializuje artefakt, a Telegram używa publicznego qbot.query wrappera

**Status:** wdrożone w workerze precompute i w Telegram gateway.

**Decyzja:** `scripts/route_precompute_trigger.py` ma najpierw upewnić się, że nowa trasa RWGPS ma zapisany `route_artifact` / `route_parse_result`, a dopiero potem uruchamiać canonical `route_base` i `route_precompute_jobs`. Telegramowy gateway ma natomiast korzystać z aktualnego `qbot.query` wrappera, żeby pełny route_report po imporcie widział ten sam publiczny route_report path co MCP / qbot.query.

**Zasada:** RWGPS import jest read-side materializacją canonical stores, a route_report pozostaje oddzielnym read-only renderem. Brak importu nie może wywrócić raportu, ale nowa trasa ma zostać przygotowana bez ręcznej operacji w legacy dumpach.

## 2026-06-30 — DECYZJA: route_report pokazuje canonical surface summary w A3

**Status:** wdrożone minimalnie w `qbot_route_report_tool.py`.

**Decyzja:** gdy `read_canonical_route(route_id)` zwraca `canonical_surface_summary`, route_report pokazuje w A3 canonical summary wyliczony z `qbot_v2.route_surface_layer`, zamiast opierać się wyłącznie na `surface_summary_json`.

**Zasada:** canonical summary ma pokazać `segment_count`, `total_distance_m`, `coverage_pct`, `by_surface`, `by_confidence` i `problem_segments_count`. Legacy `surface_summary_json` zostaje fallbackiem, jeśli canonical summary brak.

**Kontrakt:** A3 ma nie zmieniać A0/A0B/A0C ani A8. Brak canonical summary nie może wywrócić raportu.

## 2026-07-01 — DECYZJA: A3 rozdziela coverage surface od tagów OSM

**Status:** wdrożone w readerze canonical i renderze route_report.

**Decyzja:** A3 pokazuje jawnie `coverage_pct`, `tagged_surface_pct`, `inferred_surface_pct` oraz metryki Overpass chunks, aby nie mylić pokrycia warstwy surface z kompletnością tagów `surface=*` w OSM.

**Zasada:** `coverage_pct` oznacza pokrycie klasyfikacją nawierzchni dla trasy, a nie procent odcinków z bezpośrednim tagiem `surface=*`. `tagged_surface_pct` i `inferred_surface_pct` rozdzielają bezpośrednie odczyty z OSM od odcinków kontekstowych / inferowanych. Gdy dostępne są metryki Overpass, są one czytane z `qbot_v2.route_surface_profiles.surface_summary_json`; jeśli nie ma tego kontraktu, reader nie zgaduje.

**Kontrakt:** brak nowych pól nie wywraca raportu. Legacy fallback pozostaje, a A0/A0B/A0C/A8 nie zmieniają się.

## 2026-06-30 — DECYZJA: canonical reader wystawia surface summary z route_surface_layer

**Status:** wdrożone w `qbot3/routes/route_canonical_read.py`.

**Decyzja:** `read_canonical_route()` wystawia teraz `canonical_surface_summary` policzony z `qbot_v2.route_surface_layer`, aby kolejne przepięcie A3 mogło czytać canonical summary bez ruszania DB schema.

**Zasada:** summary jest wyprowadzany z canonical rows, bez zmiany `layers["route_surface_layer"]` i bez zmiany `layer_counts`. Legacy `surface_summary_json` pozostaje osobnym fallbackiem do czasu pełnego przepięcia A3.

**Kontrakt:** summary musi być bezpieczny przy brakujących `distance_m`, nie może rzucać wyjątkiem i ma pokazywać `segment_count`, `total_distance_m`, `coverage_pct`, `by_surface`, `by_source`, `by_confidence` oraz `problem_segments`.

## 2026-06-30 — DECYZJA: route_report pokazuje canonical marker POI w A8

**Status:** wdrożone minimalnie w `qbot_route_report_tool.py`.

**Decyzja:** jeśli `read_canonical_route(route_id)` zwraca canonical `route_poi_layer`, route_report pokazuje w A8 jawny marker źródła POI z liczbą punktów tej warstwy.

**Zasada:** canonical `route_poi_layer` jest pierwszym sygnałem w A8, a legacy cache / `route_poi_analyze_readonly` pozostają fallbackiem dla szczegółowej logistyki, godzin i listy kandydatów. Brak canonical POI nie wywraca raportu i nie zmienia A0, A0B, A0C ani A3.

**Kontrakt:** raport nie udaje jeszcze pełnej canonical listy logistycznej, jeśli helper zwraca tylko count; marker ma jedynie pokazać, że A8 czyta już canonical store.

## 2026-06-30 — DECYZJA: route_report pokazuje canonical marker nawierzchni w A3

**Status:** wdrożone minimalnie w `qbot_route_report_tool.py`.

**Decyzja:** jeśli `read_canonical_route(route_id)` zwraca canonical `route_surface_layer`, route_report pokazuje w A3 jawny marker źródła nawierzchni z liczbą segmentów tej warstwy.

**Zasada:** canonical `route_surface_layer` jest pierwszym sygnałem w A3, a legacy `surface_summary_json` pozostaje fallbackiem dla szczegółowej klasyfikacji. Brak canonical surface nie wywraca raportu i nie zmienia A0, A0B ani A0C.

**Kontrakt:** raport nie udaje pełnego canonical surface summary, jeśli helper zwraca tylko count; marker ma jedynie pokazać, że A3 czyta już canonical store.

## 2026-06-30 — DECYZJA: route_report pokazuje canonical profil wysokości i podjazdy

**Status:** wdrożone minimalnie w `qbot_route_report_tool.py`.

**Decyzja:** gdy `read_canonical_route(route_id)` zwraca niezerowe `route_elevation_samples` lub `route_climb_events`, route_report pokazuje osobną krótką sekcję o profilu wysokości i podjazdach opartą o canonical store.

**Zasada:** sekcja opisuje `profil wysokości` i `podjazdy / ścianki` jako warstwę canonical (`route_elevation_samples` + `route_climb_events`) i nie myli jej z legacy profilem raportowym. Brak canonical elevation nie wywraca raportu i nie zmienia A0/A0B ani A3/A8.

**Kontrakt:** raport pokazuje liczby próbek i climb events, ale nie przebudowuje jeszcze algorytmu oceny przewyższeń ani time estimate.

## 2026-07-01 — DECYZJA: A0C pokazuje canonical elevation summary i ograniczenie detekcji krótkich ramp

**Status:** wdrożone w `qbot3/routes/route_canonical_read.py` i `qbot_route_report_tool.py`.

**Decyzja:** sekcja A0C ma pokazywać canonical `elevation_summary` z `route_elevation_samples` i `route_climb_events`: `sample_count`, `climb_event_count`, `min_elevation_m`, `max_elevation_m`, `elevation_range_m`, `ascent_smoothed_m`, `descent_smoothed_m`, `smoothing_version`, `max_climb_event_gradient_pct`, `top_climb_events` oraz jawny limit detekcji krótkich ramp. Diagnostyka surowych próbek może zostać pokazana osobno, ale nie jako oficjalna ścianka.

**Zasada:** `route_elevation_samples` jest 50 m profilem, `route_elevation_engine.summarize()` daje smoothed ascent/descent, a `route_climb_events` są segmentowane w 100 m i dostarczają głównej metryki stromizny. Raport ma wprost mówić, że bardzo krótkie strome rampy mogą umknąć. Brak danych nie wywraca raportu i nie zmienia A0/A0B/A3/A8.

## 2026-07-01 — DECYZJA: route_report pokazuje końcowy werdykt trasy jako syntetyczny blok

**Status:** wdrożone w `qbot_route_report_tool.py`.

**Decyzja:** pełny `route_report` pokazuje dodatkową sekcję `WERDYKT TRASY / DECYZJA`, która syntetyzuje już dostępne dane z A0/A0B/A0C/A3/A4/A8 oraz B2/B5 w krótką decyzję dla rowerzysty gravelowego.

**Zasada:** werdykt nie liczy nowych danych i nie dubluje całych sekcji. Ma jawnie mówić, kiedy dane są ograniczone, kiedy nawierzchnia jest częściowo inferowana, kiedy METEO jest unavailable, i kiedy POI/godziny są niepełne. Brak dowolnej warstwy nie wywraca raportu, ale może obniżyć decyzję do `BRAK PEŁNYCH DANYCH`.

## 2026-06-30 — DECYZJA: route_report pokazuje sekcję otoczenia z route_shade_layer / WorldCover

**Status:** wdrożone minimalnie w `qbot_route_report_tool.py`.

**Decyzja:** gdy `read_canonical_route(route_id)` zwraca `land_cover_preferred_source=worldcover_shade` oraz niezerowy `route_shade_layer_count`, route_report pokazuje osobną krótką sekcję „otoczenie trasy" opartą o `route_shade_layer` / WorldCover.

**Zasada:** sekcja otoczenia mówi o przekroju lewo / środek / prawo względem osi trasy i używa nazwy produktu `otoczenie trasy`, a nie samego „landscape" bez wyjaśnienia. Jeśli canonical brak albo preferencja spada do `osm_landcover_legacy`, raport nie udaje WorldCover i zostaje przy legacy fallback bez regresji.

**Marker:** A0 canonical source pozostaje widoczny, ale sekcja otoczenia jest pierwszym merytorycznym przepięciem z canonical store do raportu.

## 2026-06-30 — DECYZJA: route_report pokazuje canonical read-path jako marker, bez przebudowy sekcji A/B

**Status:** wdrożone minimalnie w `qbot_route_report_tool.py`.

**Decyzja:** publiczny route_report najpierw próbuje `read_canonical_route(route_id)` i zapisuje marker źródła danych trasy: `read_path`, `fallback_reason`, `layer_counts`, `route_shade_layer_count`, `shade_coverage_pct` oraz `land_cover_preferred_source`.

**Zasada:** canonical store jest teraz widocznym źródłem diagnostycznym w raporcie, ale sekcje A3/A8/elevation nie zostały jeszcze przepięte na canonical read-path. Legacy fallback pozostaje bez zmian i brak canonical data nie może wywrócić raportu.

**Kontrakt źródła landscape:** gdy helper zwraca `land_cover_preferred_source=worldcover_shade`, raport ma to pokazać jawnie; gdy helper zwraca fallback do OSM, raport ma pokazać ten wybór bez zgadywania.

## 2026-06-30 — DECYZJA: kompletność RWGPS → precompute liczymy po aktywnych jobach orchestratora

**Status:** wdrożone w triggerze precompute.

**Decyzja:** `scripts/route_precompute_trigger.py` nie może już uznawać trasy za kompletną po stałych 4 jobach. Kompletność jest liczona dynamicznie zgodnie z aktywną sekwencją orchestratora (`route_base`, `route_surface`, `route_landcover`, `route_poi` plus opcjonalnie `route_shade` i `route_elevation`).

**Reguła runtime:** `route_shade` jest wymagany, gdy `QBOT_ROUTE_SHADE_ENABLED=1`. `route_elevation` jest wymagany tylko wtedy, gdy `QBOT_ROUTE_ELEVATION_ENABLED=1`. Jeśli flaga jest OFF, dany job nie wchodzi do definicji kompletności.

**Zasada:** precompute completion ma odzwierciedlać faktycznie aktywny canonical store, a nie starszą listę jobów. To domyka RWGPS → precompute → pełny canonical route store bez ruszania raportu, analizy ani promptów LLM.

## 2026-06-30 — DECYZJA: 2C.1 canonical read-helper dla warstw precompute

**Status:** wdrozone jako helper odczytu, bez zmian w raportowaniu.

**Decyzja:** `qbot3/routes/route_canonical_read.py` czyta kanoniczne warstwy trasy z DB i zwraca jawne `read_path="canonical"` albo `read_path="legacy_fallback"` z `fallback_reason`, gdy brakuje danych.

**Zakres odczytu:** helper korzysta z `qbot_v2.route_base`, `qbot_v2.route_axis_segments`, `qbot_v2.route_surface_layer`, `qbot_v2.route_landcover_layer`, `qbot_v2.route_poi_layer`, `qbot_v2.route_elevation_samples` i `qbot_v2.route_climb_events`. Nie renderuje raportu i nie uruchamia analyzers.

**Zasada:** canonical precompute jest primary read-path dla danych trasy, a legacy/cache/analyzers pozostają fallbackiem. `route_analysis_run` nadal jest snapshotem zależnym od `start_time`, nie trwałym magazynem faktów trasy.

**Test:** live smoke dla `55798129` ma potwierdzać obecność `route_base_id=1`, warstw surface/landcover/poi/elevation/climb oraz brak dodatkowych zapisów do `route_precompute_jobs`.

## 2026-06-30 — DECYZJA: 2C store wiring — route_elevation_samples + route_climb_events

**Status:** WDROZONE (silnik + writer + DDL + testy + orchestrator disabled). Tabele utworzone na qbot_v2. Read-path 2C (raport) NIETKNIETY.

**Tabele (DDL: `sql/route_elevation_store_v1.sql`), dzieci `route_base` `ON DELETE CASCADE`, `route_version_key` niesiony jako kolumna; `route_base` BEZ zmian:**
- `route_elevation_samples` — gesty profil 50 m, 1 wiersz/wezel. Surowa wysokosc trzymana wiernie (`elevation_m` NULL przy dziurze DEM); `source` + `smoothing_version`. Wygladzanie/podjazdy sa POCHODNE, nie materializowane tu. `UNIQUE (route_base_id, sample_index)`.
- `route_climb_events` — naglowek podjazdu + segmenty 100 m jako `segments_json` JSONB (seg_index, start_m, end_m, length_m, gradient_pct, category). `UNIQUE (route_base_id, event_index)`.

**Segmenty jako JSON** (nie osobna tabela) — zgodne z idiomem store (`segment_geojson`, `*_meta_json` to jsonb) i decyzja uzytkownika. Segmenty zawsze czytane razem z naglowkiem, zmienna licznosc, brak potrzeby zapytan po segmencie.

**Writer `qbot3/routes/route_elevation_store.py`** (lustro `route_base_store`/`route_surface_store`): `_db_conn`, `ensure_route_elevation(route_base_id|route_id)`, geometria z `route_base.source_path` (GPX) -> SRTM30m -> silnik (`route_elevation_engine`). CLI z `--repeat`.
- Idempotencja: `route_elevation_samples` upsert `ON CONFLICT (route_base_id, sample_index)` (liczba stala dla wersji); `route_climb_events` delete+insert (liczba zmienna), wszystko w jednej `conn.transaction()`.
- `build_rows()` = czysta funkcja dataclasses->wiersze (testowalna offline). `content_hash` (odczyt z DB, posortowany) jako dowod idempotencji.

**Orchestrator `route_precompute_orchestrator.py`:** dodany `ELEVATION_JOB` za bramka `QBOT_ROUTE_ELEVATION_ENABLED` (default `0`) przez `_effective_job_sequence()`. Przy `0` zachowanie BAJT-IDENTYCZNE (job nie wchodzi do sekwencji). Bez zmian w writerach 2B.1–2B.4, `route_analysis_run`, webhooku 2B.6.

**Bramki (dowod, nie na slowo):**
- testy offline: `tests.test_route_elevation_engine` 8/8, `tests.test_route_elevation_store` 3/3,
- orchestrator: OFF=4 joby (bez `route_elevation`), ON=5 (`route_elevation` ostatni),
- zywy zapis 55798129: `route_base_id=1`, 1424 probki, 1 podjazd; dwa przebiegi -> identyczny `content_hash`; `ascent_smoothed` 426.7 m vs RWGPS 403.

**Granice:** tabele zasilane TYLKO przez writer (jawnie lub orchestrator po wlaczeniu bramki); brak publicznych MCP tooli; raport trasy bez zmian.


## 2026-06-30 — DECYZJA: 2C — silnik przewyższeń i podjazdów (elevation/climb)

**Status:** decyzja architektoniczna zamknięta. Kod 2C jeszcze nie wdrożony (decyzja przed kodem). Osobna faza po 2B.5; orchestrator 2B.5 obejmuje TYLKO base/surface/landcover/poi.

**Audyt źródeł (zweryfikowany na żywo, nie z pamięci):**
- `tools/rwgps/climbs.py` = artefakt, błędny (trzy rozjeżdżające się logiki, martwy dla Alberta). NIE jest bazą. Do usunięcia po wejściu 2C.
- `route_brief`/`route_frames` 80 m = legacy/fallback (potwierdza decyzja 2026-06-28).
- `qbot3/artifacts/route_analyzer.analyze_stage_gpx` = dotąd najlepszy WŁASNY detektor (maszyna stanu z histerezą, max grade po oknie 100 m), ale próg ≥1 km/≥30 m → łapie tylko długie podjazdy. Baza algorytmu, nie gotowiec.
- **RWGPS API NIE zwraca podjazdów** (sprawdzone na 55798129): route detail (`/api/v1/routes/{id}.json`) bez pola `climb`; `/routes/{id}/climbs.json` i `/elevation.json` → 404; `?include=climbs`/`?climbs=true` ignorowane; `course_points` to wyłącznie nawigacja (Left/Right/Uturn…). Z RWGPS mamy tylko sumy `elevation_gain/loss`, gęsty ślad (1278 pkt) i nawierzchnię.
- Planowana trasa trafia na Karoo jako **GPX** — Hammerhead liczy Climbera sam na urządzeniu; nie ma gotowej listy do podebrania.
- Wysokość Karoo = otwarty stos DEM: **SRTM/GMTED2010/3DEP + Mapzen/Valhalla terrain** (atrybucja Hammerhead). Climber: progi **≥400 m i ≥3%** (tryb „All Climbs"), profil dzielony **co 100 m**, kolor wg gradientu.
- Valhalla `valhalla1.openstreetmap.de` `/height` = MARTWE (null wszędzie, też w Alpach) — to nie był błąd parsowania w poprzedniej sesji, instancja nie ma DEM. Nieużywalne.
- Działające otwarte DEM (z VPS): **opentopodata `srtm30m`** (rodzina Karoo — WYBRANE) oraz Open-Meteo GLO-90 (Copernicus 90 m — grubszy, limit/min, do profilu analitycznego co najwyżej).

**Źródło i metoda (przyjęte):**
- Siatka **50 m**, wspólna z nawierzchnią (decyzja 2026-06-30).
- `route_elevation_samples`: gęsty profil, źródło wysokości **SRTM30m (opentopodata)**. Surowe próbki trzymane wiernie + `source` + `smoothing_version`.
- Grade/ascent/podjazdy liczone z **LOKALNIE wygładzonego** profilu SRTM oknem **~200 m** (NIE globalnie — 400 m ścianki przeżywają). Okno wyznaczone EMPIRYCZNIE (kalibracja device-vs-SRTM, 3 górzyste jazdy — Castagneto/Suchedniów/Skarżysko: najbliżej barometru 250/150/250 → ~200 m). Surowy SRTM 50 m zawyża ascent +336..+652 m i rozdrabnia podjazdy na fantomy (do 22 zamiast 12) — nieużywalny bez wygładzenia.
- `route_climb_events` = **DWA POZIOMY**: (1) nagłówek podjazdu — start_m, end_m, length_m, elevation_gain_m, avg_gradient_pct, max_gradient_pct, severity, source, detection_version; (2) **segmenty 100 m z gradientem każdego** (profil ścianek, jak Climber) — liczone z WYGŁADZONEGO profilu (inaczej fantomowe ścianki z siatki 30 m). Sam `max_grade` nie mówi, czy ściana jest jedna czy pięć — dopiero rozkład 100 m to pokazuje.
- Detekcja progami Karoo: **≥400 m i ≥3%**. Precyzja do metra/0,1% świadomie nieistotna (120 vs 140 m, 4,5 vs 5% w jeździe bez znaczenia) — liczy się sygnatura podjazdu i profil ścianek.
- Idempotencja/wersjonowanie: `route_base_id + sample_index` / `route_base_id + event_index`, plus `route_version_key` (jak `route_base_store.py`). `smoothing_version`, `detection_version` jako stringi → wynik powtarzalny i wersjonowany.

**Rozdział warstw (kluczowy):**
- `route_elevation_samples` = fundament analityczny, budowany ZAWSZE (zasila ETA/wiatr/moc); może mieć własne wygładzanie.
- `route_climb_events` = warstwa pod sekcję raportu „Przewyższenia" (właściwa dla górzystego terenu), strojona pod ujęcie Climbera.

**Zastrzeżenia (uczciwie):**
- SRTM strojony pod barometr (fizyczna prawda przejazdu); Karoo używa SRTM, ale z własnym nieznanym wygładzaniem → zgodność BLISKA, nie co do metra. Pełna zgodność z Climberem wymagałaby porównania z eksportem z Karoo — poza naszą stroną.
- Pokrycie podjazdów device-vs-SRTM nigdy nie 100% w obie strony (inne źródło + barometr to faktyczna linia, SRTM to ślad GPS na siatce). Duże podjazdy zgadzają się zawsze; różnice na granicznych.
- opentopodata limity (1000/dobę, 1/s, 100 pkt/req): sporadyczny precompute jednej trasy OK (~7 req); przy backfillu wielu tras → cache albo własna instancja SRTM (miejsce na dysku jest).

**Granice 2C (czego NIE robi):** nie przepina raportu trasy; nie miesza elevation do `route_axis_segments`; nie używa 50 m jako jedynego kanonu dla podjazdów; nie rusza writerów 2B.1–2B.4; nie dodaje publicznych MCP tooli; nie zmienia `route_analysis_run`; nie odpala pełnych raportów. Orchestrator 2B.5 zostawia typowany, wyłączony punkt rozszerzenia na elevation/climb job.

**Pliki docelowe:** `qbot3/routes/route_elevation_store.py` + `tests/test_route_elevation_store.py` (lustro `route_base_store.py`: ten sam `_db_conn`, wejście `ensure_route_elevation(route_id)`, upsert z `route_version_key`, CLI). Writer: czyta DEM, zapisuje oba poziomy, idempotentny; nie dotyka raportu/POI/weather.

**Kalibracja jako powtarzalna metoda:** porównanie ramka-po-ramce device (`activity_record`, 1 Hz pozycja+wysokość, 335 jazd) vs SRTM na górzystych jazdach — stroi okno wygładzania i progi. Nie blokuje builda (okno ~200 m przyjęte).


## 2026-06-30 — DECYZJA: route_base, route_poi_layer i route_analysis_run jako rozdzielone warstwy trasy

**Status:** aktywna decyzja architektoniczna.

**Intencja:** QBot rozdziela fakty trasy, półstałe warstwy źródłowe i analizę konkretnego przejazdu. Nie mieszamy danych o trasie z overlayami zależnymi od `start_time`, prognozy i modelu ETA.

**route_base / route_axis_base:** zawiera tylko fakty i półstałe dane źródłowe trasy: `route_id`, `route_artifact_id`, `route_version_key`, `route_modified_at` / `route_updated_at`, `geometry_hash`, raw geometry reference, kanoniczną oś 50 m, `km_from`, `km_to`, `distance`, bazowe `elevation/slope`, oraz obiektywne dane źródłowe: `surface`, `highway`, `tracktype`, `landuse`, `natural`, `forest/wood`, `building/settlement context`, `water/river/lake context`, plus `quality/coverage/status` per source layer. Oś 50 m pozostaje warstwą pomocniczą do joinów, agregacji i raportowania przekrojowego, ale nie jest kanonicznym źródłem prawdy dla `elevation`, `climb` ani `gradient`.

**route_base nie zawiera gotowych ocen ani modeli pochodnych:** nie przechowuje `asphalt_heat_factor`, `sun/shade exposure factor`, `wind exposure factor`, `route risk factor`, `WBGT`, `cold-risk`, `weather`, `open_at_eta`, `recommended stops`, `nutrition/hydration` ani `resupply decision`. Te wartości są liczone później w `route_analysis_run` / `route_report_run` na podstawie `route_base`, `route_poi_layer`, `start_time`, prognozy, ETA i modeli.

**route_poi_layer:** może być półstałą warstwą przy `route_base`. Zawiera `poi_id` / `source_place_id`, `provider`, `name`, `category`, `lat/lon`, `km_on_route`, `distance_from_route_m`, `opening_hours`, `opening_hours_fetched_at`, `source_updated_at`, `confidence`, `validity_hint`, `stale_after`.

**route_poi_layer nie zawiera decyzji dla konkretnego przejazdu:** nie przechowuje `open_at_eta`, `selected_store_in_town`, `recommended_stop`, `refill_priority`, `detour_worth_it` ani `risk_of_closed_at_arrival`.

**route_analysis_run / route_report_run:** jest osobnym snapshotem analizy dla konkretnego `start_time`. Zawiera `route_id`, `route_artifact_id`, `route_version_key`, `start_time`, `assumed_speed_model`, `forecast_provider`, `forecast_fetched_at`, `report_generated_at`, `ETA` per segment, `weather_overlay` per segment, `WBGT_overlay` per segment, `cold_risk_overlay` per segment, `open_at_eta`, `selected POI stops`, `recommended_stop`, `refill_priority`, `enough_for_this_ride`, `selected_store_in_town`, `detour_worth_it`, `risk_of_closed_at_arrival`, `resupply plan` oraz ostrzeżenia o starych godzinach otwarcia.

**Wysokość i podjazdy jako osobna warstwa trasy:** dla przewyższeń nie opieramy się wyłącznie na 50 m axis. Potrzebne są dwie warstwy: `route_elevation_samples` jako gęstszy profil wysokości po oryginalnym GPX/RWGPS albo najgęstszym dostępnym profilu oraz `route_climb_events` jako wykryte podjazdy, krótkie ścianki i strome rampy. `route_analysis_run` ma te warstwy konsumować, nie być jedynym miejscem ich przechowywania.

**Pogoda i oceny czasowe jako overlay:** pogoda, WBGT i cold-risk nie są trwałymi cechami trasy. Są overlayem konkretnego uruchomienia raportu, zależnym od `start_time`, `forecast_fetched_at` i wybranego modelu ETA. Nie zapisujemy ich do `route_base` jako stałej prawdy.

**Półstałość i świeżość POI:** `route_poi_layer` i podstawowe `opening_hours` mogą być cache’owane przy wersji trasy, ale muszą mieć `fetched_at` i `stale_after`. Jeśli dane są stare, `route_analysis_run` ma pokazać `WARN` albo odświeżyć źródło przed użyciem.

**Webhook / web-book event:** gdy QBot dostaje informację o nowej trasie albo nowej wersji istniejącej trasy, powinien automatycznie uruchomić precompute tylko stałej i półstałej bazy trasy.

**Detekcja wersji:** nowa wersja trasy jest identyfikowana przez `route_id`, `route_modified_at` / `route_updated_at` ze źródła, `geometry_hash`, `route_artifact_id` oraz `route_version_key`.

**Automatyczny precompute:** webhook tworzy lub odświeża `route_base`, raw geometry reference, kanoniczną oś 50 m, `elevation_micro_profile`, `climb_events` / `steep_ramp_events`, surface source layer, land-cover / source context layer, `route_poi_layer`, `opening_hours` dla POI oraz `quality/coverage/status` per layer.

**Zakres precompute:** automatyczny precompute nie tworzy pełnego `route_analysis_run` zależnego od konkretnej daty i godziny. Nie tworzy `weather_overlay`, `WBGT_overlay`, `cold_risk_overlay`, `open_at_eta`, `selected_store_in_town`, `resupply plan`, `nutrition/hydration plan` ani final `route_report_run`, chyba że event jawnie zawiera `planned_start_time` i intencję przygotowania raportu dla konkretnego przejazdu.

**Kiedy powstaje run analityczny:** pełna analiza przejazdu powstaje jako osobny `route_analysis_run` / `route_report_run` na żądanie użytkownika, albo automatycznie tylko wtedy, gdy event zawiera `planned_start_time` i jawnie oznacza intencję przygotowania raportu dla konkretnego przejazdu.

**Idempotencja:** webhook dla tej samej `route_version_key` nie tworzy duplikatu. Może odświeżyć półstałe warstwy, jeśli są po terminie `stale_after`. Każdy przebieg zapisuje status: `pending`, `running`, `complete`, `failed`, `partial`.

**Separacja odpowiedzialności:** `route_base` jest trwałą bazą faktów i półstałych danych. `route_analysis_run` jest kasowalnym snapshotem analizy. Cleanup analiz będzie osobnym modułem później.

**Cel operacyjny:** pełny raport trasy składa `route_base`, `route_poi_layer` i `route_analysis_run`, zamiast mieszać dane stałe z czasowymi overlayami. Dzięki temu pogoda, WBGT, cold-risk i decyzje o POI są jednoznacznie przypięte do konkretnego startu, a nie do samej trasy.

## 2026-06-29 — Readiness diagnostics rozdzielają aktywne błędy od szumu

**Status:** wdrożone w diagnostyce, bez zmian runtime.

**Intencja:** `qbot_error_summary` rozdziela teraz `active_errors`, `historical_errors`, `expected_test_errors` i `malformed_legacy_records`. Readiness bazuje wyłącznie na `active_errors`, a nie na historycznych/testowych wpisach w `tool_calls`.

**Guard GATE:** `gate_hikconnect.py` pozostaje oczekiwaną zależnością legacy/QLab. Guard ma go raportować jako `INFO`/`expected_dependency`, nie jako warning blokujący readiness.

**Probe RWGPS:** `rwgps_storage_overview()` preferuje schemat `qbot_v2` dla tabel `route_artifacts`, `route_parse_results`, `route_surface_profiles` i `route_surface_segments`. Brak tabel w `public` sam w sobie nie oznacza missing schema.

**Cutover message:** `95%` w legacy cutover nadal oznacza, że legacy jest włączone. To nie jest błąd runtime, tylko stan przejściowy do pełnego cutoveru.

## 2026-06-29 — Route surface read-path passthrough dla raportu

**Status:** wdrożone w read-path, bez zmian schematu DB i bez zmian WEB.

**Intencja:** `qbot_route_tools.py` przekazuje dalej aktualny `surface_summary_json` shape do danych raportu, wraz z `surface_quality_status`, `tagged_surface_pct`, `inferred_surface_pct`, `unknown_surface_pct`, `geology_context`, `problem_segments`, `surface_percentages_raw` i `surface_percentages_refined`.

**Zgodność:** storage i schema DB pozostają bez zmian. HikConnect/GATE pozostają poza zakresem i nietknięte.

**Następny krok:** potwierdzić na publicznym `qbot.query`, że pełny raport używa `surface_summary_json`, pokazuje `geology_context` jako kontekst ryzyka i cache POI bez ciężkiego refreshu Overpass, a legacy segmenty zostają tylko fallbackiem.

**Regresja testowa:** `tests/test_route_report.py` pilnuje teraz, że full route report dla `55798129` renderuje `surface_summary_json` i `Geologia / podłoże`, nie wraca do legacy `33%`, a brak cache POI kończy się jawnym `PARTIAL` zamiast ciężkiego refreshu.

## 2026-06-29 — POI / zaopatrzenie w raporcie korzysta z cache i priorytetów PL

**Status:** wdrożone w read-path raportu, bez zmian schematu DB i bez ciężkiego refreshu w publicznym runtime.

**Intencja:** sekcja `POI / zaopatrzenie` w pełnym raporcie trasy ma czytać zapisany cache/artifact z punktami zaopatrzenia, pokazywać `km_on_route`, `distance_from_route_m`, `opening_hours`, `eta_at_poi` oraz status `OPEN_AT_ETA` / `UNKNOWN_HOURS` / `CLOSED_AT_ETA`, a nie odpalać publicznego Overpass refreshu.

**Priorytet produktu dla Polski:** sklepy spożywcze i stacje paliw są głównym źródłem zaopatrzenia, bary/restauracje/kawiarnie są pomocnicze, a publiczne `drinking_water` jest tylko bonusem. Brak fontann publicznych nie oznacza braku możliwości zakupu wody.

**Zachowanie awaryjne:** jeśli cache POI nie istnieje, raport pokazuje `UNAVAILABLE` albo `PARTIAL` z jawnym ostrzeżeniem. Legacy ścieżka pozostaje fallbackiem, ale nie może blokować całego raportu.

**Prezentacja A8 2026-06-29:** główna lista `POI / zaopatrzenie` pokazuje tylko punkty `hard_resupply` / `soft_food_stop` do 500 m od śladu. Punkty 500-1000 m mogą pojawić się wyłącznie jako `AWARYJNY_FALLBACK_1KM` przy checkpointach 25% / 50% / 75% trasy, jeśli w okolicy checkpointu nie ma żadnego `OPEN_AT_ETA` do 500 m. Punkty powyżej 1000 m nie trafiają do A8.

**ETA per raport 2026-06-29:** `eta_at_poi` i `OPEN_AT_ETA` / `CLOSED_AT_ETA` w A8 są liczone przy renderowaniu z `ride_start` raportu oraz `km_on_route`. Cache POI może zachować geometrię, godziny i kandydatów, ale nie może narzucać stałego ETA dla innego startu.

**Regresja testowa:** `tests/test_route_report.py` pilnuje, że raport pokazuje jawny status POI, kilometraż punktów, status godzin i klastrowanie, a brak cache nie wywołuje ciężkiej analizy.

## 2026-06-29 — Google Places jest primary dla hard_resupply

**Status:** wdrożone w route-poi analyzerze, bez zmian schematu DB i bez restartu usług.

**Intencja:** w analizie POI dla tras w Polsce `hard_resupply` ma pierwszeństwo z Google Places, a Overpass/OSM pełni rolę fallbacku lub uzupełnienia. Analiza działa po całej trasie w punktach/korytarzu, deduplikuje kandydatów po nazwie, dystansie, klastrze i kilometrze oraz ocenia godziny względem ETA.

**Zachowanie awaryjne:** jeśli Google nie daje kandydatów, Overpass nadal może podać punkt zaopatrzenia. Jeśli chunk się wywala, wynik ma jawne `PARTIAL` z technicznym powodem `analysis_timeout` / `overpass_timeout` / błędem providera.

**Regresja testowa:** dodano syntetyczne testy, które pilnują kolejności providerów, fallbacku Overpass oraz technicznego `PARTIAL` dla route-poi.

## 2026-06-29 — POI rozdziela supply_status od technical_completeness

**Status:** wdrożone w read-path raportu i analizie POI.

**Intencja:** `missing_chunks` z pomocniczego Overpass nie mogą same oznaczać, że zaopatrzenie jest `PARTIAL`, jeśli Google Places znalazł realne `hard_resupply` na trasie. Raport ma pokazywać osobno `supply_status` dla realnego zaopatrzenia oraz `technical_completeness` dla kompletności providerów pomocniczych.

**Reguła produktu:** `supply_status` opiera się na `hard_resupply`, `OPEN_AT_ETA` i długości luki między punktami, a `technical_completeness` wynika z `missing_chunks` i błędów providerów pomocniczych. W statusie zaopatrzenia wolno pokazać `RISK` dla realnej luki kilometrowej, ale nie `PARTIAL` tylko dlatego, że Overpass nie domknął wszystkich chunków.

**Regresja testowa:** testy pilnują, że Google Places primary może dać `supply_status=OK`, gdy techniczna kompletność pozostaje `PARTIAL`.

## 2026-06-29 — Route surface writer path zapisuje pełny aktualny engine output

**Status:** wdrożone w writer path, bez migracji DB i bez zmian WEB.

**Intencja:** `tools/rwgps/client.py` zapisuje teraz do `qbot_v2.route_surface_profiles.surface_summary_json` pełny aktualny engine output z `analyze_route_surface()`, przy zachowaniu kompatybilności przez merge legacy `surface_profile` + current result. Wykorzystywany jest istniejący `JSONB`, więc migracja schematu nie jest wymagana.

**Zapis segmentów:** `surface_segments_json` bierze segmenty z aktualnego wyniku engine, nie tylko z legacy payloadu. Testowo zapisano profile dla `55798129` i `55864231`.

**Następny krok:** sprawdzić, czy WEB/raport czyta nowe pola z `surface_summary_json` bez zmian w rendererze.

## 2026-06-28 — Overpass multi-endpoint fallback dla route_surface_engine

**Status:** wdrożone w kodzie, bez restartu usług i bez migracji DB.

**Intencja:** poprawić coverage dłuższych tras w `route_surface_engine_v1` bez podłączania Valhalli, przez fail-open fallback po globalnych publicznych instancjach Overpass.

**Default endpointy dla tras w Polsce:** `https://overpass-api.de/api/interpreter`, `https://overpass.private.coffee/api/interpreter`, `https://maps.mail.ru/osm/tools/overpass/api/interpreter`. Lista jest konfigurowalna przez `QBOT_OVERPASS_ENDPOINTS`. Regionalne instancje Swiss, Britain/Ireland, Virginia i Ethiopia nie są defaultem; `overpass.openstreetmap.ru` nie jest defaultem.

**Zachowanie produkcyjne:** tryb `first_success` jest domyślny; chunk zatrzymuje się na pierwszym endpointcie z HTTP 200. Timeout, HTTP 429 i HTTP 5xx przechodzą przez retry/backoff i następny endpoint. HTTP 400 kończy dany chunk bez retry, bo oznacza błąd query/syntax. Każdy chunk fail-open zostawia UNKNOWN/LOW_CONFIDENCE zamiast crasha.

**Metryki JSON:** `overpass_metrics` zawiera `endpoints_tried`, `endpoint_stats`, `chunks_total`, `chunks_ok`, `chunks_failed`, `timeout_count`, `http_error_count`, `cache_hit_count`, `selected_endpoint_per_chunk`. Wynik ma `quality_status` wg coverage, refined unknown i udziału inferencji.

**Diagnostyka mirrorów:** `QBOT_OVERPASS_PROBE_ALL=1` albo `analyze_route_surface(..., overpass_probe_all=True)` włącza `probe_all`, który odpytuje każdy default endpoint dla każdego chunka i zapisuje `overpass_probe.endpoint_comparison` z latencją, timeoutami, błędami HTTP oraz liczbą elements/ways/nodes/relations. Nie jest to default produkcyjny.

---

## 2026-06-28 — Geology context scaffold dla analizy nawierzchni

**Status:** wdrożone w kodzie, bez restartu usług i bez migracji DB.

**Intencja:** utrwalić `geology_context` jako stały etap produkcyjnego JSON analizy nawierzchni, ale bez ryzykownego podpinania zewnętrznych API w tej fazie. Geologia jest europejskim kontekstem interpretacyjnym dla całej trasy, nie źródłem prawdy surface.

**Kontrakt JSON:** top-level `geology_context` zawsze zawiera `enabled`, `status`, `provider`, `dominant_region`, `dominant_unit`, `units`, `sections`, `material_hint`, `confidence`, `source_resolution`, `sample_strategy`, `explanation`, `warnings`. Segmenty mogą mieć `geology_hint_applied`, `geology_material_hint` i `risk_flags`.

**Provider chain:** docelowo `EGDI` jest bazowym providerem dla całej Europy; krajowe providery są opcjonalnym enrichment/override dla obsługiwanych krajów, a `heuristic_region_v1` zostaje ostatnim fail-open fallbackiem. Docelowy porządek: 1) EGDI, 2) national provider enrichment tam, gdzie jest to sprawdzone, 3) `heuristic_region_v1`. Nie projektujemy `geology_context` jako listy ręcznych krajowych wyjątków. Włochy i Hiszpania były tylko testami konkretnych krajów, nie granicą systemu. Źródła do kolejnego audytu: Polska PIG-PIB/CBDG/GeoLOG/WMS/WFS, Europa EGDI/INSPIRE/OneGeology, Włochy ISPRA, Hiszpania IGME/REDIAM, a dla CZ/DE/AT/FR/SI/HR potrzebny jest osobny audyt.

**EGDI audyt 2026-06-28:** prototyp opiera się na `https://geoserver.geo-zs.si/egdi-surface-geology/gsmlp/wms` i `GetFeatureInfo` z `INFO_FORMAT=application/json` na warstwie `GeologicUnitView_Lithology`. To działa dla wielu punktów europejskich i zwraca `lithology`, `representativeAge_uri`, `source`, `metadata_uri` oraz geometrię. Pan-europejny OGC API `.../ogc/features` istnieje, ale `collections/GeologicUnitView/items?bbox=...` zwracał w tym audycie `500`/`NullPointerException`, więc nie jest jeszcze bazą prototypu. OneGeology sprawdził się tylko jako techniczny fallback WMS/WFS bez praktycznego coverage dla punktów testowych w Europie Środkowej i Południowej.

**Integracja hook 2026-06-28:** `tools/rwgps/geology_context.py` używa teraz EGDI jako pierwszego realnego provider chain. Jeżeli EGDI zwraca `WARN` albo `UNAVAILABLE`, kod wraca do `heuristic_region_v1`. National provider enrichment nadal pozostaje tylko miejscem na przyszłą implementację.

**Próbkowanie:** geologia używa centroidu, bbox i punktów kontrolnych co 10 km; przy krótkich trasach minimum centroid + start + finish. Nigdy nie używa próbkowania 50 m, bo 50 m dotyczy wyłącznie nawierzchni.

**Fail-open:** jeśli region nie pasuje albo provider zawiedzie, wynik zostaje `WARN`/`UNAVAILABLE`, material hint pozostaje `unknown`, a analiza nawierzchni działa dalej. Heurystyka może dodać tylko kontekst/ryzyka dla UNKNOWN, low confidence i inferowanych track/path/ground, bez nadpisywania `surface_raw`.

---

## 2026-06-28 — Metryki jakości klasyfikacji nawierzchni

**Status:** wdrożone w kodzie, bez restartu usług.

**Intencja:** odróżnić coverage OSM od jakości klasyfikacji surface. Wynik ma pokazywać, ile dystansu pochodzi z jawnego tagu `surface`, ile z inferencji (`highway`, `tracktype`, landcover/service defaults), a ile pozostaje UNKNOWN.

**Kontrakt JSON:** `route_surface_analysis_v1` dodaje `tagged_surface_pct`, `inferred_surface_pct`, `unknown_surface_pct`, `inference_sources_pct`, `inference_sources_m` oraz `problem_segments.top_unknown/top_inferred`. Segmenty mają `classification_source`.

**Quality status:** `GOOD_TAGGED` oznacza dobry coverage i niewielką inferencję; `GOOD_INFERRED` oznacza dobry coverage i niski UNKNOWN, ale istotna część wyniku jest inferowana. `PARTIAL` i `LOW_CONFIDENCE` zostają dla słabszego coverage/UNKNOWN. Stare pola `coverage_pct`, `unknown_pct_raw`, `unknown_pct_refined`, `quality_status` i `overpass_metrics` pozostają kompatybilne.

---

## 2026-06-28 — Gravel surface engine po rzeczywistym śladzie

**Status:** faza 1 wdrożona w kodzie, bez migracji DB i bez restartu usług.

**Intencja:** migrujemy główną analizę nawierzchni gravelowej z `route_frames`/pudełek 80 m na analizę po rzeczywistym śladzie GPX/TCX/JSON/RWGPS. `route_frames` zostają jako legacy/fallback dla profilu, pogody, debug i agregacji, ale nie są źródłem prawdy nawierzchni.

**Parametry nawierzchni:** domyślne próbkowanie surface = 50 m; primary Overpass corridor = 50 m; fallback corridor = 80 m; confidence match distance: 0-25 m high, 25-50 m medium, 50-80 m low. Dystans 150 m nie jest normalnym matchem; może istnieć tylko jako awaryjny debug/fallback z `very_low` i ostrzeżeniem.

**Refinementy:** Valhalla jest fallback/refinement, nie zamiennik OSM. Landcover jest contextual refinement dla UNKNOWN/low/conflict, nie twarde źródło surface. `surface_raw` musi być zachowane, a inferencje mają method/confidence/explanation.

**Geology context:** geologia jest stałym etapem regionalnym, fail-open. Strategia: centroid + bbox + punkty kontrolne co 5-10 km, ewentualne sekcje tylko dla dużych jednostek; bez próbkowania geologii co 50 m. Wynik ma być cache'owany per route/artifact hash/bbox/provider. Provider chain: krajowy -> europejski/globalny fallback. W fazie 1 provider jest jawnie `UNAVAILABLE`, żeby nie dawać fałszywej precyzji.

**WEB:** WEB jest rendererem gotowego DATA JSON/route_surface_analysis_v1, nie źródłem prawdy ani miejscem liczenia nawierzchni.

---

## 2026-06-28 — Audyt i sprzątanie dokumentacji MD

**Status:** wykonane.

Przeprowadzono audyt 100% plików MD w repo i w `/opt/qbot/docs/`. Wynik:

- **29 plików wycofanych** → `docs/archive/retired_20260628/` (prefix `RETIRED_`), w tym 6 plików z `/opt/qbot/docs/` (QBOT_BIBLE, QBOT_KNOWHOW, QBOT_PROJECT_INSTRUCTION_LOCAL i inne).
- Oryginały w `/opt/qbot/docs/` zastąpione stub-ami z redirectem (plik `qbot_query_router.py` referencjonuje QBOT_BIBLE — stub zapobiega błędom przy odczycie).
- `docs/archive/README.md` zaktualizowany o nową sekcję `retired_20260628`.

**Aktywna mapa dokumentów po sprzątaniu:**
- `CLAUDE.md` + `AGENTS.md` — instrukcje pracy Claude/agentów
- `docs/CONTEXT.md` — auto-gen (aktualizuj przez `scripts/build_context.py`)
- `docs/architecture/QBOT_ARCHITEKTURA_QBOT3.md` — kanon architektury
- `QBOT_INSTRUCTIONS.md` — runtime prompt Alberta
- `docs/DECISIONS.md` — ten plik
- `docs/architecture/QBOT_TOOL_REGISTRY_MAP.md` — mapa narzędzi (54 narzędzia, 2026-06-28)
- `docs/architecture/MODELQ.md` — dokumentacja FitModel/ModelQ
- `docs/architecture/ROUTE_REPORT_WEB_ARCHITECTURE.md`, `SURFACE_INTEGRATION_SPEC.md`, `RIDEPHOTO_QBOT_MODUL_SPEC.md` — specs modułów
- `docs/RAMAT_WEB.md`, `docs/Qbot_Route_Logistics.md`, `docs/QBOT3_TELEGRAM_TRANSPARENT_UI.md`, `docs/qbot_mcp_connector.md` — operacyjne
- `governance/` — polityki

---

## 2026-06-22 — Przełącznik modeli Alberta + fixy (ucinanie wyników, loteria route_id) [dokumentacja wdrożonego]

**Status:** wdrożone i ZACOMMITOWANE. Wpis dokumentuje zmiany już obecne w kodzie (TASK 03 = tylko spisanie, bez zmian kodu).

### 1. Przełącznik modeli Alberta (gpt / gemini / claude)
- Moduł `qbot3/llm/model_profiles.py`: słownik `PROFILES` z 3 profilami; każdy ma jawny `base_url` + `model` + `key_env` (niezależne od QGPT_*):
  - `gpt` → base `QBOT_PLANNER_BASE_URL` (default `https://api.openai.com/v1`), model `QBOT_PLANNER_MODEL` (default `gpt-5.4-mini`), klucz `QBOT_PLANNER_API_KEY`
  - `gemini` → `https://generativelanguage.googleapis.com/v1beta/openai`, `gemini-2.5-flash`, klucz `GEMINI_API_KEY`
  - `claude` → `https://api.anthropic.com/v1/`, `claude-sonnet-4-6`, klucz `ANTHROPIC_API_KEY`
  - `DEFAULT = gemini`.
- Aktywny profil w `data/albert_model.json` (`{"active": "..."}`) — zmiana BEZ restartu (plik czytany przy każdym `get_active()`/`resolve()`). Stan na 2026-06-22: `active=claude`.
- API modułu: `get_active()`, `set_active(name)`, `resolve()` (zwraca base_url/model/api_key/key_present z env), `public_status()`.
- `qbot3/agent_runtime.py` (l. 256–269): orkiestracja woła `resolve()` i przekazuje profil do `albert_run` jako `override_api_key` / `override_base_url` / `override_model`.
- Komendy (deterministyczne, `qbot_query_handler.py` l. 392–395 + `handle_query` l. 4865–4879):
  - „model gpt|gemini|claude" (+ synonimy „przełącz na…", „użyj…", „albert na…") → `set_active` + potwierdzenie; ostrzega, gdy brak klucza dla profilu.
  - „jaki model" / „aktywny model" / „który model" / „status modelu" → `public_status` (label, model, klucz jest/BRAK).
- `qbot3/llm/albert.py` `_gen_kwargs(model, base_url, max_n)` (l. 33–43): modele OpenAI gpt-5+/o-series → `max_completion_tokens`, bez `temperature`; pozostałe → `max_tokens` + `temperature=0`.
- Klucz `ANTHROPIC_API_KEY` skonsolidowany do autorytatywnego env `/etc/qbot/qbot-api.env`.

### 2. Fix ucinania długich wyników (profil km-po-km)
- Root cause: wynik KAŻDEGO narzędzia podawany modelowi był cięty do 4000 znaków → `route_profile_detail` urywał się ~km19.
- Fix: relay 4000 → 16000 (`albert.py` l. 441); `max_tokens` 1200 → 5000; `build_detail` w `tools/rwgps/route_brief.py` przepisany na zwięzły (~3,8 tys. znaków).
- Efekt: pełny profil 0→99,3 km w jednym wywołaniu.

### 3. Fix loterii `route_id` (nazwa zamiast numeru)
- Problem: narzędzia tras przy `route_id` = NAZWA zwracały cichy fail ze `status: OK`.
- Fix (`qbot_route_tools.py`): gdy `route_id` nie jest numeryczny → `_resolve_rwgps_route_hint(name)` zamienia nazwę na ID; gdy nierozwiązywalne → `None` (fallback na najnowszą).

### Stan w git
Zmiany zacommitowane: `2f5b62a` + `d8591c4`. HEAD na 2026-06-28: `9b44531`.

---

## 2026-06-21 — ZASADA: instrukcja Alberta zawsze zsynchronizowana z narzędziami (OBOWIĄZKOWE)

**Status:** obowiązujące, twarda reguła procesu.

**Problem:** narzędzia (`qbot3/tool_registry.py`) zmieniają się szybciej niż prompt Alberta (`_SYSTEM` w `qbot3/llm/albert.py`). Gdy dodasz/zmienisz/usuniesz narzędzie, a prompt zostaje w tyle, Albert nie wie że narzędzie istnieje albo do czego służy → myli intencje, wpada w złe narzędzie.

**Reguła:** KAŻDA zmiana narzędzi LUB domen/intencji MUSI być w tym samym kroku odzwierciedlona w prompcie Alberta. Definicja „gotowe" = kod + wpis w rejestrze + AKTUALNY prompt Alberta. Bez aktualizacji promptu zmiana jest NIEUKOŃCZONA.

**Wykryte przy okazji (dług do spłacenia w prompcie _SYSTEM):**
- Brak sekcji o trasach w prompcie → dopisać reguły doboru narzędzi tras: `route_plan_analysis` (podsumowanie planu), `route_profile_detail` (szczegóły z ramek), `ride_analysis` (wykonana jazda/FIT).
- „Styl odpowiedzi" każe streszczać → Albert ucina długie wyniki. Dopisać: gotowe analizy (pole analysis) pokazuj w całości, nie skracaj.
- `build_tools_spec` obcina opis narzędzia do 500 znaków → opisy < 500 znaków, rozróżnienie na początku.

---

## 2026-06-21 — Scalenie analizy tras w jeden pipeline (planowana + wykonana)

**Status:** zatwierdzone i ZAIMPLEMENTOWANE (Faza A + Faza B, rdzeń działa E2E). Stan: zacommitowane.

### Architektura — siatka pudełek 80 m

Trasa = rząd pudełek ~80 m (wspólna siatka geograficzna dla faz A i B).

**Faza A — trasa planowana:** pudełka PRAWDY O DRODZE (nawierzchnia, nachylenie, prognoza pogody + kierunek wiatru względem trasy, briefing ryzyka, forma, wellness, prognoza glikogenu).

**Faza B — trasa wykonana (FIT):** nakłada realny przejazd na te same pudełka. DIFF trasa-vs-plan (próg zboczenia 60 m), realna pogoda (Open-Meteo archive), wnioskowanie o wietrze (korelacja nadwyżki prędkości), werdykt przyłożony do formy+wellness.

### Tabele (qbot_v2) — dodane w tej sesji
`route_frames`, `route_frame_weather`, `ride_frames`.

### Moduły (tools/rwgps/) — dodane
`route_frames.py`, `route_weather.py`, `route_brief.py`, `ride_overlay.py`, `ride_verdict.py`.

### Wpięcie w bota (Albert)
Narzędzia w `qbot3/tool_registry.py`: `route_plan_analysis` (zaplanowana trasa/track), `ride_analysis` (FIT/wykonana jazda). Routing LLM-first przez Alberta — VNEXT nie przechwytuje tych zapytań.

### Sprzątanie (wykonane 2026-06-21)
- `archive/route_legacy_2026-06/` — 22 skrypty starego stacku G (g1-g15, analyze_route_*, route_logistics_*) + `tools/rwgps/overpass_cache.py`. Zero importów w żywym kodzie.
- `scripts/build_context.py` przepisany (usunięto błędny opis „Router v2 → Planner v2 → core/planner.py"; `core/planner.py` NIE ISTNIEJE).
- `qbot_query_handler.py`: usunięty martwy keyword-hack (gałęzie + funkcje `_handle_route_plan_analysis`/`_handle_ride_analysis`).

### TODO (faza B, refinementy — NIE zrealizowane)
- Skojarzenie FIT ↔ plan: auto po starcie+dacie (zaakceptowane); próg zboczenia 60 m (zaakceptowane).
- Przeliczanie nawierzchni tylko dla off_plan > 200 m.
- Carry-forward FTP na dni odpoczynku.
- Pogoda wielopunktowa.
- Wygaszenie starego tagowania nawierzchni z FIT (obecnie fallback w `fitmodel/surface_tag.py`).

---

## 2026-06-21 — Rozstrzygnięcia przed Fazą B

**Pogoda — źródło:** OpenWeatherMap PRIMARY, Open-Meteo FALLBACK. OWM `/data/2.5/forecast` (3-godz., 5 dni); dla dat > 5 dni automatyczny fallback na Open-Meteo (16 dni).

**Bugfix loaderów .env:** pliki `tools/rwgps/*.py` nie zdejmowały cudzysłowów z wartości → klucz OWM leciał z apostrofami → 401. Poprawione w `route_weather`/`route_frames`/`route_brief`.

**Forma „na dziś":** `fitmodel_daily` cron (`daily_job`, 04:45) działa poprawnie. FTP liczony z danych jazdy, wypełnia tylko dni z przejazdem. `route_brief` bierze ostatni niepusty FTP — poprawnie.

---

_Uwaga (2026-06-28): ostatni wpis w tej sekcji zawierał notatkę „STAGED, niezacommitowane" — nieaktualne. Zmiany zostały zacommitowane w `2f5b62a` i `d8591c4`. HEAD: `9b44531`._

Aktualizacja 2026-06-29: route surface writer ma quality gate w `tools/rwgps/client.py`. Partial wynik Overpass lub `LOW_CONFIDENCE` nie nadpisuje dobrego profilu dla tej samej trasy, jeśli istnieje już profil `GOOD_TAGGED` albo `GOOD_INFERRED` z lepszą jakością. Schemat DB bez zmian. Słaby wynik bez lepszego istniejącego profilu może być zapisany z warningiem `LOW_QUALITY_PROFILE_NO_BETTER_EXISTING_PROFILE`. HikConnect/GATE pozostają poza zakresem i nietknięte.
## 2026-06-30 — DECYZJA: etapowanie DB route_base / route_axis / route_analysis_run

**Status:** aktywna decyzja architektoniczna.

**Intencja:** przed implementacją migracji QBot rozdziela docelowy schemat tras na etapy, żeby nie mieszać faktów trasy, półstałych warstw i snapshotów analiz przejazdu.

**Faza 2A — minimalny fundament DB:** wdrażamy tylko tabele wymagane do poprawnego rozdziału bazy trasy od analiz:
- `route_base`,
- `route_axis_segments`,
- `route_surface_layer`,
- `route_landcover_layer`,
- `route_poi_layer`,
- `route_precompute_jobs`,
- `route_analysis_run`.

**Zakres Fazy 2A:** `route_base` i `route_axis_segments` są trwałym fundamentem wersji trasy. `route_surface_layer`, `route_landcover_layer` i `route_poi_layer` są półstałymi warstwami źródłowymi. `route_precompute_jobs` kontroluje automatyczne przeliczenia po webhooku lub backfillu. `route_analysis_run` jest kasowalnym snapshotem konkretnej analizy przejazdu.

**Nie dublujemy bytów:** na tym etapie nie tworzymy osobnej tabeli `route_report_run`. Render raportu jest atrybutem `route_analysis_run` przez `rendered_report_artifact_id`.

**Faza 2B / 2C — później:** odkładamy na kolejne etapy:
- `elevation_micro_profile`,
- `route_climb_events`,
- znormalizowane segmentowe overlaye pogody / WBGT / cold-risk,
- osobny `route_report_run`, jeśli raport zacznie mieć własny cykl życia i wersjonowanie.

**Legacy:** `route_frames` i `route_frame_weather` pozostają legacy/fallbackiem. Nie są nowym modelem docelowym i nie mogą stać się drugą prawdą obok `route_axis_segments`.

**Idempotencja:** `route_base` jest unikalne po `route_id + route_version_key`. Joby precompute są idempotentne po `route_version_key + job_type` albo jawnej wartości `idempotency_key`. `route_analysis_run` może mieć wiele rekordów dla tej samej wersji trasy, bo zależy od `requested_start_time`, prognozy i modelu prędkości.

**Cleanup:** czyszczenie dotyczy tylko `route_analysis_run` i jego przyszłych child-overlayów. `route_base`, `route_axis_segments` i półstałe warstwy trasy nie są usuwane w ramach cleanupu analiz.

**Reuse istniejących analyzerów:** Faza 2A nie tworzy nowych kalkulatorów powierzchni, land-cover, POI, pogody ani raportu. Nowy kod ma być głównie kontraktem DB, writerem wyników i orkiestratorem precompute. Źródłem obliczeń pozostają istniejące narzędzia:
- `route_artifacts` i `route_parse_results` dla faktów trasy,
- parser RWGPS/GPX dla artefaktu i geometrii,
- `route_surface_engine` dla segmentacji 50 m i nawierzchni,
- `_persist_route_surface_profile` / `route_surface_profiles` jako obecny zapis legacy surface,
- `surface_landcover` oraz `route_brief.build_detail(..., land_cover=True)` dla land-cover/context,
- obecny POI analyzer, Google Places, Overpass fallback i `poi_open_window` dla POI oraz `opening_hours`,
- `qbot_route_report_tool`, `qbot_route_analysis_tool`, `route_weather`, WBGT toolchain, speed model i POI ETA/opening-hours evaluator dla `route_analysis_run`.

**Zakaz dublowania:** Nie wolno pisać równoległego analyzera surface, land-cover, POI, weather, ETA/opening-hours ani raportu, jeśli istniejące narzędzie może zostać użyte jako źródło danych. Wyjątkiem jest tylko adapter/writer/orchestrator, który zapisuje wynik istniejącego toola do nowych tabel i pilnuje `route_version_key`.

---

## 2026-07-02 — Fix: koncowe powiadomienie Telegram po potwierdzeniu trasy (trigger_source)

**Objaw:** po `NN TAK` (analiza #23, trasa 55930010 "Male Gosie") analiza wykonala sie
poprawnie i dane trafily do DB (6 warstw complete), ale uzytkownik NIE dostal koncowego
powiadomienia na Telegram. W `telegram_conversation_turns` brak zarowno
`route_confirmation_final_notification_sent`, jak i `_failed`.

**Przyczyna (root cause):** akcja oczekujaca `confirm_route_analysis` byla tworzona przez
webhook RWGPS, ktory zapisywal w jej payloadzie `trigger_source="rwgps_webhook"`
(`route_precompute_trigger._send_route_confirmation_prompt`, payload). Po potwierdzeniu
bramka (`qbot_qcal_telegram._execute_writer`, galaz `confirm_route_analysis`) odczytywala
ten payload i uruchamiala workera z `--trigger-source rwgps_webhook`. Worker liczyl
poprawnie, ale koncowe powiadomienie ma gate: wysyla sie TYLKO dla
`trigger_source == "telegram_confirm"` (`_send_route_confirmation_final_notification`),
wiec bylo po cichu pomijane (`skipped: non_telegram_confirm_trigger`) — bez wpisu audytu.

**Decyzja:** wykonanie akcji `confirm_route_analysis` jest z definicji potwierdzeniem z
Telegrama, wiec w bramce wymuszamy na sztywno `trigger_source = "telegram_confirm"`
(zamiast czytac z payloadu). Naprawia to rowniez akcje juz oczekujace z bledna etykieta.

**Zmiany:** `qbot_qcal_telegram.py` (galaz `confirm_route_analysis`) + test regresyjny
`tests/test_qbot_qcal_telegram.py::test_confirm_route_analysis_forces_telegram_confirm_trigger`
(payload `rwgps_webhook` -> worker startuje z `telegram_confirm`). Testy: 12 + 17 zielone.

**Wdrozenie:** wymaga restartu `qbot-api` (zmiana w gatewayu) — wykonany, usluga active.

**Uwaga poboczna (do osobnego watku):** w `logs/telegram_reply.log` co ~2 min
`409 Conflict` na `getUpdates` = dwoch konsumentow czyta Telegram naraz. Nie jest
przyczyna tego buga (dotyczy odbioru, nie wysylki), ale warto rozdzielic.


## 2026-07-02 — Raport kanoniczny trasy (V1): nowy wariant „kanon"

**Co:** nowy moduł `qbot3/routes/route_report_canonical.py` (`build_canonical_report_v1`)
— jeden, stały 10-sekcyjny układ raportu (makieta 1:1) budowany wyłącznie z żywych,
strukturalnych źródeł. Podpięty jako NOWY wariant `route_report` = „kanon"
(aliasy: kanon/kanoniczny/v2/nowy).

**Warianty pełny/skrócony/grupa NIETKNIĘTE** — 64 testy `tests.test_route_report` przechodzą.

**Źródła sekcji:** route_source (canonical_surface/elevation/poi_summary),
route_surface_layer (highway/tracktype → reguła ryzyka), run_meteo_engine
(WBGT/UTCI/opad/wiatr — tabela 30 min), estimate_route_time_v2, fitmodel_daily
(FTP_est/W-kg/glikogen), route_poi_layer (zaopatrzenie + atrakcje),
Nominatim reverse-geocode (gmina/powiat/województwo, cache).

**Reguła ryzyka nawierzchni (potwierdzona 55798129, zaszyta w module):**
highway=track z tracktype grade1-4 → NIE ryzyko; track bez tracktype / grade5 → ryzyko;
piach → ryzyko. Tag OSM wygrywa nad wnioskowaniem. Zniknął heurystyczny szum
„loose_surface_possible".

**Atrakcje:** włączone per-trasa dla 55930010 (`route_poi_prefs.attractions_enabled=true`),
POI przeliczone na żywo (161 pkt, w tym 39 atrakcji). Uwaga operacyjna: fetch POI
wymaga klucza Google z `/etc/qbot/*.env` — standalone run bez tego env daje
supply_status=UNAVAILABLE i degraduje warstwę; zawsze ładować `/etc/qbot/*.env`.

**Nowe tabele:** `qbot_v2.route_admin_cache` (cache reverse-geocode gmina/powiat/woj.).

**tool_registry NIEZMIENIONY** (kanon to wariant wewnątrz istniejącego route_report),
więc twarda reguła „zmiana narzędzia = wpis w _SYSTEM" nie jest naruszona. Kanon
CELOWO nie jest jeszcze w prompcie Alberta (WIP) — docelowo zastąpi „pełny" po
osiągnięciu parytetu i przepisaniu asercji testów.

**Świadomie zostawione do dopieszczenia:** gęstość sekcji 4 (strategia) — wierna
trasie (Małe Gosie realnie przeplata asfalt z nieotagowanymi trackami).


---

## 2026-07-03 — Model nawierzchni: 5 kategorii + smoothness-degrader + flagi (SPEC, decyzja przed kodem)

Kontekst: rozmowa o wykorzystaniu tagow OSM poza surface/tracktype. Zweryfikowano
na zywo pokrycie tagow (Overpass, probki co 50 m) na trasach 55930010, 55864231,
55918401. Skrypt tymczasowy, self-delete.

### Wyniki pokrycia (pamietac: 3 trasy, NIE reprezentatywne)
| tag              | 55930010 | 55864231 | 55918401 |
|------------------|----------|----------|----------|
| surface          | 53.7%    | 86.3%    | 79.9%    |
| tracktype        | 18.0%    | 47.2%    | 50.9%    |
| smoothness       | 32.6%    | 50.2%    | 19.7%    |
| mtb:scale        | 0%       | 7.6%     | 0%       |
| trail_visibility | 0%       | 0%       | 0%       |
| width            | 0%       | 1.1%     | 0.5%     |
| bicycle          | 2.8%     | 43.9%    | 17.6%    |
| access           | 0%       | 0.1%     | 2.0%     |
| incline          | 0%       | 0.1%     | 0%       |

Kandydaci "kat.5" (brak surface I brak tracktype): 34.1% / 11.9% / 14.0% trasy,
wg highway prawie wylacznie track+path. Z tych odcinkow tag weryfikujacy
(mtb/vis/width) mial: 0% / 0% / 0%. Gole (zero czegokolwiek): 100% / 90.5% / 100%.

### Wnioski empiryczne
- mtb:scale/trail_visibility/width jako "ktos potwierdzil droge" NIE dziala na tych
  danych: tam gdzie sa, way ma juz surface/tracktype; nigdy nie ratuja nieznanego.
- Dziala strona ODWROTNA: brak wszystkiego = czerwona flaga (duzy udzial trasy).
- smoothness ma realne pokrycie (20-50%) — najlepszy z "dodatkowych" tagow.
- incline ~0% -> odrzucone, stromizna wylacznie z DEM.
- Decyzja Michala: reguly zostaja mimo slabego pokrycia — czasem pomoga, nigdy nie
  szkodza (dzialaja tylko w jedna strone), a 3 trasy to za malo by je skreslic.

### MODEL BAZOWY (backup przed zmiana) — obecny stan route_report_canonical.py
- _seg_risk: klasy twarde/gravel/wnioskowane/ryzyko.
  * sand -> ryzyko; track grade5 -> ryzyko; ctx sand_risk=WYSOKIE -> ryzyko
  * tagged_surface -> twarde(_HARD) / gravel
  * inferred_tracktype lub track+grade1-4 -> gravel
  * reszta -> wnioskowane (z WorldCover)
- _macro_blocks: coarse szybko/grunt/ryzyko.
- smoothness: NIE uzywany w raporcie (choc jest w surface_meta_json).

### NOWY MODEL (do wdrozenia, ocena w raporcie, potem decyzja)
5 kategorii (skala szybko->ryzyko):
1. Twarda szybka  — asphalt, concrete, paving_stones
2. Dobry gravel   — compacted, fine_gravel; tracktype grade1-2
3. Zwykly gravel  — gravel, dirt, ground; tracktype grade3; cobblestone (DO POTW.)
4. Trudna/wolna   — grass, mixed(unpaved surowe); tracktype grade4
5. Ryzyko/niepewne— sand, mud, rocky, stony, unknown; tracktype grade5;
                    goly track/path bez tagu; ctx sand_risk=WYSOKIE

Kolejnosc ustalania kategorii bazowej (seg ma surface, cls, highway, tracktype):
  a) cls=inferred_tracktype / track+tracktype -> kategoria wprost z grade
     (grade1->2, grade2->2, grade3->3, grade4->4, grade5->5) — wierniej niz label.
  b) cls=tagged_surface -> tabela surface->kategoria.
  c) brak (goly track/path, inferred_highway) -> kat.5 (czerwona flaga); jesli
     jest kontekst WorldCover las/pole -> zlagodzenie do kat.4 (DO POTW.).

SMOOTHNESS-DEGRADER (nakladany PO kategorii bazowej):
- grunt (kat.2-4): smoothness bad/very_bad -> -1 oczko (min kat.4).
- utwardzone (kat.1): smoothness bad/very_bad -> WPROST kat.4 (nie -1).
- dowolna: smoothness horrible/very_horrible/impassable -> WPROST kat.5.
- smoothness dobry/brak -> bez zmian.
- Uzasadnienie asymetrii: grunt z definicji nierowny (info juz w tracktype ->
  podwojne karanie), asfalt startuje "rowno" -> bad to wylom.
- OTWARTE (decyzja z 2026-07-02): czy degrader dziala tez na segmentach z jawnym
  tagiem surface (dzis _infer_from_tags konczy sie wczesniej). Do rozstrzygniecia.

FLAGI (osobna warstwa, NIE mieszaja sie do kategorii nawierzchni):
- bicycle=no / access=private/no -> flaga "zakaz/prywatne".
- bicycle=dismount -> flaga "prowadzenie".
- Obecnosc mtb:scale/trail_visibility -> modyfikator TYLKO w jedna strone:
  moze sciagnac odcinek z kat.5 nizej ("ktos przejechal"); nigdy nie zaostrza.
- width: tylko obecnosc = potwierdzenie drogi; NIGDY wartosc jako kara (waska != zla).
- Zasada nadrzedna: te tagi nigdy nie tworza ryzyka same z siebie ani nie nadpisuja
  surface/tracktype. Najgorszy przypadek = regula sie nie odpala (bezczynnosc).

### STATUS WDROZENIA
- FAZA 1 (report-only, bez zmian silnika): 5 kategorii + smoothness-degrader.
  Dane dostepne (surface, cls, highway, tracktype juz sa; smoothness dodac do
  _surface_segments). Backup: stare _seg_risk/_macro_blocks zostaja jako *_legacy.
- FAZA 2 (pozniej, wymaga zmiany silnika): persist mtb:scale/trail_visibility/
  width/bicycle/access w surface_meta_json -> wlaczenie FLAG. Odlozone.
- Nastepny krok: potwierdzic komorki DO POTW. (cobblestone kat.3?, mixed kat.3/4?,
  WorldCover-lagodzenie kat.5->4?, degrader na tagged surface?) -> wtedy kod.


### 2026-07-03 (uzup.) — decyzje domkniete + zweryfikowany pipeline + wybor Opcji 2

Rozstrzygniete komorki DO POTW.:
- cobblestone -> kat.3
- mixed (surowe unpaved) -> kat.4
- goly track/path z kontekstem WorldCover: las/pole -> kat.4; piach lub
  nieprzejezdnosc -> kat.5
- degrader smoothness dziala TEZ na segmentach z jawnym tagiem surface -> TAK
  (lapie rozbity asfalt i zryty grade1)

WYBOR ARCHITEKTURY: Opcja 2 — ocena (kategoria) liczona i ZAPISYWANA do DB per
odcinek; raport tylko czyta i wyswietla. Uzasadnienie Michala: "prawda o odcinku"
w bazie; raport dowolnie modelowalny bez utraty mechaniki oceny.

Zweryfikowany pipeline (na zywo, route 55930010 / route_base_id=66):
  silnik (route_surface_engine)
    -> route_surface_profiles.surface_segments_json  [MA smoothness=good, way_id,
       classification_source, tracktype, highway, surface, risk_flags — pelne dane]
    -> [writer route_surface_store.py] -> route_surface_layer.surface_meta_json
       [GUBI smoothness! writer nie kopiuje tego pola]
    -> [Faza 2E] route_surface_context (WorldCover/sand) — ODDZIELNA tabela, 21 wierszy,
       pisana PO route_surface_layer
    -> raport czyta route_surface_layer + route_surface_context
route_surface_layer: brak kolumny kategorii; wszystko poza surface/highway/tracktype
siedzi w surface_meta_json (jsonb).

KLUCZOWA ZALEZNOSC KOLEJNOSCI (orchestrator route_precompute_orchestrator.py):
route_surface (2) -> ... -> route_surface_context (2E). Kontekst piachu/WorldCover
POWSTAJE PO warstwie nawierzchni. Wiec kategorii z regula piachu NIE da sie policzyc
w ensure_route_surface (kontekstu jeszcze nie ma).

PLAN Opcji 2 (do zatwierdzenia, decyzja przed kodem):
1. route_surface_store.py: przeniesc `smoothness` do surface_meta_json (1 linia) —
   potrzebny wsad dla kategoryzatora.
2. NOWY modul route_surface_category_store.py: ensure_route_surface_category(rbid) —
   czyta route_surface_layer (surface, tracktype, highway, smoothness,
   classification_source, risk_flags) + route_surface_context (sand_risk, reason),
   liczy surface_category 1-5 + label + reason + smoothness-degrader, dopisuje do
   surface_meta_json klucze: surface_category, surface_category_label,
   surface_category_reason. (Kolumna realna — opcjonalnie pozniej, DDL.)
3. NOWY krok orkiestratora Faza 2F: route_surface_category, PO route_surface_context.
4. Raport: czyta surface_category z DB i wyswietla (osobny krok, pozniej).
5. Backup: kategoryzator jest ADITYWNY (tylko dodaje klucze) -> stara logika raportu
   _seg_risk/_macro_blocks zostaje nietknieta do momentu przelaczenia raportu na
   odczyt z DB. Rewert = wywalenie kroku 2F.

WLASNOSC WARTA ODNOTOWANIA: krok kategoryzatora to przebieg DB->DB (bez Overpass).
Iteracja progow kategorii = re-run TYLKO tego kroku, tani, bez przeliczania trasy.
To godzi Opcje 2 (trwalosc w DB) z tania iteracja (obawa, ktora ciagnela ku Opcji 1).


### 2026-07-03 (wdrozenie) — FAZA 1 gotowa (niezacommitowane)

Zbudowano (Opcja 2, zapis kategorii do DB; przebieg DB->DB bez Overpass):
1. qbot3/routes/route_surface_store.py — smoothness przenoszony do surface_meta_json
   (patch io.open, bez .bak zrodla).
2. qbot3/routes/route_surface_category_store.py — NOWY. compute_category(...) +
   ensure_route_surface_category(route_id/route_base_id). Dopisuje do
   route_surface_layer.surface_meta_json: surface_category (1-5), _label, _reason.
3. qbot3/routes/route_precompute_orchestrator.py — Faza 2F: krok route_surface_category
   za flaga QBOT_ROUTE_SURFACE_CATEGORY_ENABLED=1, PO route_surface_context.
   Domyslna sekwencja bajt-identyczna gdy flaga=0 (zweryfikowane).
4. tests/test_route_surface_category.py — 17 testow, wszystkie OK.

BUG znaleziony i naprawiony w trakcie: inferred_highway z surface=asphalt/concrete
to WNIOSKOWANA UTWARDZONA (z klasy drogi), NIE goly odcinek. Rozdzielono:
inferred_paved (asphalt/concrete/paving_stones -> tabela; mixed -> kat.4) vs
bare (ground/dirt/unknown z track/path -> kat.5 + kontekst). Bez tego drogi
dojazdowe (service) ladowaly bledne w kat.4.

Dowody na zywo (route_base 66, "Male Gosie"):
- ensure_route_surface(66) -> 58 rows, smoothness w 23 odc.
- ensure_route_surface_category(66) -> 58/58, histogram:
  twarda szybka 21 / dobry gravel 6 / zwykly gravel 4 / trudna 20 / ryzyko 7.
- inferred_highway: 2x asphalt(service)->k1, 15x ground->k4 (zlagodzone WorldCover).
- tagged sand -> k5; grade3 (inferred_tracktype) -> k3; compacted -> k2; mixed -> k4.

NIE zrobione (swiadomie, osobne kroki):
- Przelaczenie RAPORTU na odczyt surface_category z DB (stare _seg_risk/_macro_blocks
  nietkniete = backup dziala). To nastepny krok do oceny w raporcie.
- Wlaczenie flagi QBOT_ROUTE_SURFACE_CATEGORY_ENABLED w env produkcji.
- FAZA 2: flagi bicycle/access/mtb (wymaga persist tagow w silniku).
- COMMIT: sesja weryfikacyjna (build niezacommitowany, zgodnie z modelem pracy).

DEBRIS do sprzatniecia (DC, rm zablokowany w DEV MCP):
- scripts/_tmp_livecat.py.bak.1783061229


### 2026-07-03 (raport - krok danych) — /surface-categories na zywo

Przelaczenie raportu na kategorie z DB, krok 1 (dane, addytywny, backup-safe):
- qbot_web.py: _load_surface_buckets dostaje pola surface_category/_label/_reason
  z surface_meta_json (addytywnie). Istniejacy /surface-segments (ryzyko binarne)
  NIETKNIETY.
- NOWY endpoint GET /api/routes/{id}/surface-categories: wstazka scalonych odcinkow
  tej samej kategorii + surowe bucket-y + km_by_category + has_category.
  Zrodlo: route_surface_layer (przebieg DB->DB, bez Overpass).
- qbot-web zrestartowany (systemctl restart qbot-web).

Dowod na zywo (55930010 Male Gosie, 99.5km):
  km_by_category: k1=41.8 / k2=14.5 / k3=7.0 / k4=35.3 / k5=1.0
  ribbon: 38 scalonych odcinkow; k5 = tag sand 50.2-51.2.
  inferred asphalt (service) poprawnie w k1; gole ground w k4 (WorldCover).

NIE zrobione (nastepny krok, wymaga zgody - edycja WIP raport-v2.html):
- wizualna wstazka 5 kolorow + tooltip w raport-v2.html (frontend). Dzis tylko API.
- ewentualne przelaczenie starego /surface-segments lub sekcji MD na kategorie.


### 2026-07-03 (raport-v2) — drugi wykres: wstazka 5 kategorii pod analiza

- raport-v2.html: dodana sekcja "Nawierzchnia — 5 kategorii" POD istniejacym
  wykresem analizy (przed .stub). Addytywnie: nowy div #catwrap/#cat-body +
  #cat-legend + <script> ktory na window.load fetchuje
  /api/routes/{DATA.route.id}/surface-categories i rysuje kolorowa wstazke
  (proporcja km) + os + legende km/%. Style reuzywaja klas strony (chartwrap,
  chart-legend). Istniejacy renderChart/#chart/DATA NIETKNIETE.
- Backup WIP: /opt/qbot/web/public/raport-v2.html.bak.20260703_102102
- Kolory kat: k1 #3f7a4d, k2 #9ccc5a, k3 #d9a441, k4 #d67a2c, k5 #c2452f.
- Zweryfikowane: HTTP 200, #cat-body obecny, renderChart/#chart/stub nienaruszone.

UWAGA architektoniczna (dlug techniczny do decyzji): ta wstazka pobiera dane
przez fetch z API, a nie z wypalonego bloku DATA (kontrakt "wszystkie liczby z
generatora"). Swiadome, bo: (a) generatora DATA nie ruszamy, (b) dane sa z DB
(deterministyczne). Gdy model kategorii sie ustabilizuje -> zapiec do generatora
DATA jako chart.surface_cat i renderowac w glownym SVG (docelowo), zamiast fetch.

DEBRIS do sprzatniecia (DC): scripts/_tmp_livecat.py.bak.1783061229 (wczesniej).


### 2026-07-03 (korekta) — porownanie modeli na surface-kat.html; raport-v2 przywrocony

- NIEPOROZUMIENIE: poprzednio dodalem wstazke 5-kat do raport-v2.html. Uzytkownik
  chcial porownania na surface-kat.html. -> raport-v2.html PRZYWROCONY z backupu
  (raport-v2.html.bak.20260703_102102), bez zmian (renderChart obecny, cat-body brak).
- surface-kat.html przebudowany na STRONE POROWNAWCZA (3 warstwy, wyrownane po km):
  1) Przewyzszenia — profil z raport-v2 (DATA.chart.ele),
  2) NOWY model 5 kat. — z /api/routes/{id}/surface-categories,
  3) WCZESNIEJSZY model — z raport-v2 (DATA.chart.surface, klasy asfalt/szuter/grunt/ryzyko).
  Dane starego modelu + przewyzszenia pobierane przez fetch raport-v2.html i ekstrakcje
  bloku DATA (new Function) — te SAME liczby co widzi stary raport, bez zmian backendu
  i bez zgadywania generatora DATA. Dziala tylko dla 55930010 (raport-v2 jest baked na te trase).
- Zweryfikowane: surface-kat.html 200; ekstrakcja DATA z raport-v2 poprawna
  (slice ma km_total/ele/surface, start "{ route:{id:55930010...").

DEBRIS (.bak, do DC): raport-v2.html.bak.20260703_102102, surface-kat.html.bak.1783067513,
  scripts/_tmp_livecat.py.bak.1783061229.


### 2026-07-03 — KANONICZNA paleta kolorow nawierzchni (5 kat.)
Uzgodnione z Michalem, obowiazuje w KAZDEJ wizualizacji (surface-kat, docelowo raport-v2):
- k1 twarda szybka  / asfalt        -> ciemny szary  #3a3f47
- k2 dobry gravel   / szuter        -> jasny szary   #9aa3ad
- k3 zwykly gravel  / grunt         -> jasnozielony  #8bc34a
- k4 trudna/wolna                   -> pomaranczowy  #e07b1a
- k5 ryzyko/niepewne                -> czerwony      #c2452f
Stary model (4 klasy) mapowany na te same kolory: asfalt=k1, szuter=k2, grunt=k3, ryzyko=k5
(pomaranczowy k4 nie wystepuje w starym modelu — to celowa roznica do porownania).


### 2026-07-03 (krok 1) — flaga kategorii WLACZONA w produkcji

- /etc/qbot/qbot-api.env: dodano QBOT_ROUTE_SURFACE_CATEGORY_ENABLED=1
  (backup: /etc/qbot/qbot-api.env.bak.20260703_104701).
- systemctl restart qbot-api (uslugi active x3 po restarcie; chwilowy zanik MCP - przejsciowy).
- DOWOD (realny env): active_precompute_job_types() = route_base, route_surface, route_poi,
  route_elevation, route_shade, route_surface_context, route_surface_category (7, ostatni=category).
  => kazdy pelny przelicz (scope=all) bedzie od teraz liczyl i zapisywal surface_category do DB.
- NIE zrobione: pelny end-to-end recompute realnej trasy (Overpass/Valhalla/Google + prune) -
  do uruchomienia na zyczenie. Wiring potwierdzony deterministycznie.
- POZOSTAJE (krok 2): przelaczyc RAPORT (kanoniczny i/lub raport-v2 generator DATA) na odczyt
  surface_category, zeby raport realnie pokazywal nowy model.


### 2026-07-03 (raport → nowy model nawierzchni) — Cz.A raport-v2 + Cz.B kanoniczny

**Cz.A — raport-v2.html** (poza repo, /opt/qbot/web/public, deploy na żywo, backup .bak.*):
- Nawierzchnia pod profilem + mapa + dymek (label+reason) + legenda → 5 kategorii
  (surface_category z DB), paleta KANONICZNA k1 #3a3f47 / k2 #9aa3ad / k3 #8bc34a /
  k4 #e07b1a / k5 #c2452f. Wykres profil/wiatr/pogoda NIETKNIĘTY.
- DATA dostaje `chart.surface_cat` przez NOWY generator
  `scripts/build_raport_v2_surface_cat.py` (import z qbot_web._load_surface_buckets/
  _coalesce_categories → parytet z endpointem /surface-categories; przebieg DB→DATA,
  BEZ fetch w przeglądarce). Stary `chart.surface` ZACHOWANY (czyta go surface-kat.html).

**Cz.B — route_report_canonical.py** → raport kanoniczny na nowy model, 4 koszyki strategii:
- `_surface_segments`: +surface_category/_label/_reason z surface_meta_json.
- `_seg_risk`: klasa z surface_category (szybko k1 / gravel k2+k3 / trudna k4 / ryzyko k5),
  powód = surface_category_reason. Brak kategorii → "nieznane" (sygnał przelicz).
- `_macro_blocks`: 4 koszyki; **trudna NIE połykana** (jak ryzyko) → k4 zawsze widoczna.
  ma_wniosk liczony z cls.
- NOWY helper `_km_by_category(segs)`: dokładny udział km z DB. Werdykt (sek.1) i sek.7
  liczą trudna/ryzyko z PRAWDY per-segment (nie ze scalonych bloków) → werdykt spójny z tabelą.
- Sek.4: legenda 4 koszyki; dopisek "cz. wnioskowana" dla gravel/trudna.
- Sek.7: +wiersz info k4 "trudna/wolna ~X km".
- Usunięto osierocone `_GRADE_OK` (po zmianie _seg_risk). `_HARD` zostaje (sek.3).
  `_GRAVEL` był już nieużywany wcześniej (pre-existing) — DO SPRZĄTNIĘCIA (nie ruszane).
- **DECYZJA:** Sekcja 3 (pewność: tag/tracktype/wnioskowane) NIE reframowana na kategorie —
  to osobna oś (fakt vs interpretacja); reframe by ją zepsuł. Odejście od wcześniejszego
  planu "3C/7 też".
- Bez flagi (model włączony w prod), git = backup, bez *_legacy w kodzie.

**Dowody na żywo (55930010):** km_by_cat k1 41.8 / k2 14.4 / k3 7.0 / k4 35.3 / k5 1.0;
werdykt "trudna ~35.3 km"; strategia 15 bloków (4 szybko / 3 gravel / 7 trudna / 1 ryzyko);
testy kategorii 17/17; render bez błędu.

**Dług techniczny:** (a) generator raport-v2 baked tylko dla 55930010 (jak cały DATA);
(b) `_GRAVEL` do usunięcia; (c) surface-kat.html nadal fetch (znany dług).

## 2026-07-03 — Fix: route_base — dokładnie jedna aktywna wersja na trasę (dezaktywacja starych)

Objaw: wiele wierszy `route_base` ze `status='active'` na ten sam `route_id`
(55864231: 3, 55798129: 2, 55918401: 2). Rozkład statusów w tabeli: wyłącznie `active`.

Przyczyna: klucz konfliktu upsertu to `(route_id, route_version_key)`, więc każda nowa geometria
(nowy `route_version_key`) tworzy NOWY wiersz `route_base`, a stary zostawał `active` — nigdzie
nie było kroku dezaktywacji poprzednich wersji.

Decyzja/naprawa (commit `e334cb7`):
- Kod `route_base_store._upsert_route_base`: po zapisie nowej wersji, w TEJ SAMEJ transakcji
  ustaw `status='disabled'` dla pozostałych wersji tego `route_id` (gdy nowa jest `active`).
- Status `disabled` (nie `stale`): CHECK `route_base_status_chk` dopuszcza tylko
  `active/stale/disabled/failed`; `stale` znaczy zły parse, więc dla ważnej-ale-starej wersji
  właściwe jest `disabled`.
- Dane: jednorazowy UPDATE — najnowsza per `route_id` (max `route_modified_at`) zostaje `active`,
  starsze → `disabled`. Wynik: 6 tras = 6 `active`, 4 `disabled`.

Bezpieczeństwo: `route_base.status` nie jest źródłem wyboru wersji. Raport/geometria/nawierzchnia
wybierają po `route_id` + `ORDER BY route_modified_at DESC` (commit `84c543f`); `_fetch_active_route_version`
działa na `route_artifacts`. Dlatego dezaktywacja starych wierszy niczego nie psuje w read-path.

Powiązane: ten sam commit `84c543f` dodał deterministyczny wybór najnowszej wersji w qbot_web.py oraz
funkcje raportu web (chip pogoda/wiatr, wersja trasy, mapa B/W + przyciski, kolory, wchłanianie
odcinków <300 m) — szczegóły w RAPORT_WEB.md; zmiana store w ROUTE_STORE.md (2a).


## 2026-07-04 — Archiwum wygenerowanych raportow trasy (persist + historia)

Objaw: raport trasy liczyl sie tylko w pamieci przegladarki - odswiezenie strony = utrata
wyniku, trzeba bylo klikac Generuj od nowa za kazdym razem.

Decyzja: kazde wygenerowanie `/api/report/data` zapisuje pelny blok DATA do nowej tabeli
`qbot_v2.route_report_snapshots` (data/godzina zapisu + parametry formularza + dane).
Retencja: 4 najnowsze NA TRASE (route_id) - biezacy + 3 archiwalne: starsze kasowane
automatycznie przy kazdym nowym zapisie (`_save_report_snapshot` w qbot_web.py).

**DECYZJA (dane, nie gotowy HTML):** archiwizujemy surowe dane raportu, nie wyrenderowana
strone. Konsekwencja: gdy w przyszlosci zmieni sie wyglad (raport-render.js/raport.css),
stare zapisane raporty tez skorzystaja z nowego wygladu - "zamrozone" sa tylko liczby
z momentu generowania, nie prezentacja.

**DECYZJA (zakres historii):** archiwum osobne PER TRASA (nie jedna wspolna lista globalna) -
uzytkownik jednoznacznie wybral ten wariant.

Nowe endpointy (qbot_web.py):
- `GET /api/report/history?route_id=` - lista ostatnich zapisow danej trasy (id, data/godzina
  jazdy, dlugie przerwy, kiedy wygenerowano), najnowszy pierwszy.
- `GET /api/report/snapshot/{id}` - dokladnie zapisany blok DATA (bez liczenia od nowa).

Front (raport-trasy.html, poza repo):
- Pasek "Historia" pod paskiem generatora (`#f-history`, styl `.hist-bar`/`.hist-chip` w
  raport.css) - klik na date wczytuje zapisany raport przez `/api/report/snapshot/{id}`.
- Wybor trasy zapamietywany w `localStorage` (`qbot_report_last_route`). Po odswiezeniu
  strony i po kazdej zmianie trasy w dropdownie: automatyczne wczytanie NAJNOWSZEGO zapisu
  tej trasy (bez klikania Generuj) - pola formularza (data/godzina/przerwy) odtwarzane z
  zapisu. Klikniecie Generuj zawsze liczy swiezy raport i dopisuje go do archiwum.
- raport.css bump `?v=2026070401` (nowe klasy .hist-*); raport-render.js BEZ ZMIAN - ten sam
  `window.renderReport(data, mount)` renderuje zarowno swiezo policzone dane jak i zapisany
  snapshot.

**Dowod na zywo:** trasa 55957534 - 5x wygenerowano z roznymi datami, `GET .../history`
zwraca stale dokladnie 4 wpisy (najstarsze automatycznie odpadaja); `GET .../snapshot/{id}`
zwraca identyczny blok DATA co przy oryginalnym generowaniu (nazwa trasy, data startu zgodne).

**Dlug techniczny:** brak sprzatania osieroconych snapshotow po skasowaniu trasy z routes
store (route_report_snapshots nie ma FK do route_base, klucz to tekstowy route_id) - do
rozwazenia przy okazji `route_delete`/`route_store_purge`, jesli kiedys bedzie to problemem
(malo prawdopodobne przy 4 wierszach/trase).


## 2026-07-04 (2) — Wysylka uproszczonego raportu mailem (mapa+wykres jako zrzuty, GPX w zalaczniku)

Cel: mozliwosc wyslania trasy znajomemu mailem - jedno pole (adres) + przycisk, bez
interaktywnosci, tresc czytelna w kazdym kliencie poczty.

**Sekcje mailu (jedna pod druga):** trasa/dystans/przewyzszenie, start, szacowany czas,
mapa (obrazek), pogoda (ogolnie + etapy), profil trasy (obrazek), nawierzchnia (km/%% per
kategoria + opis ryzykownych odcinkow), ostrzezenia. W zalaczniku plik GPX (z POI, ten sam
generator co Karoo).

**DECYZJA (mapa/wykres w mailu):** rozwazono 3 warianty - (A) rysowanie wlasne bez tla ulic
(Pillow), (B) Google Static Maps, (C) zrzut prawdziwej interaktywnej mapy/wykresu przez
headless przegladarke. Google odpada: klucz `GOOGLE_PLACES_API_KEY` nie ma wlaczonego
Static Maps (403 "API not activated"), wlaczenie wymagaloby akcji uzytkownika w Google
Cloud. Wybrano **C** (decyzja uzytkownika, mimo wiekszego kosztu infrastruktury) - realne
ulice/wyglad identyczny z appka, bez zaleznosci od plaskiego API.

**Jak dziala zrzut (C):**
- Nowy plik `/opt/qbot/web/public/raport-print.html` - "cichy" wariant raportu: bez
  formularza, czyta `route_id`/`date`/`time`/... LUB `snapshot_id` z query string, woła
  `/api/report/data` albo `/api/report/snapshot/{id}`, i od razu `window.renderReport(...)`.
  Ten sam `raport-render.js`/`raport.css` co normalny raport - zero duplikacji logiki
  mapy/wykresu.
- `raport-render.js`: dodany sygnal gotowosci kafli mapy - `_tl.once("load", ...)` ustawia
  `window.__QBOT_MAP_READY=true` (plus fallback timeout 4s, gdyby event nie odpalil).
  `raport-print.html` ustawia `window.__QBOT_RENDER_DONE` po zakonczeniu renderReport.
- `qbot_web.py`, `_capture_report_images(snapshot_id)`: Playwright (sync API), headless
  Chromium, otwiera `raport-print.html?snapshot_id=...` z wstrzykniętym ciasteczkiem sesji
  (ten sam HMAC co logowanie - `_webauth_cookie_make`), czeka na oba sygnaly gotowosci,
  robi 2 zrzuty elementow: `#map` i `#chart` (SVG) -> PNG bytes.
- Endpoint zawsze najpierw liczy `_build_report_data` + zapisuje snapshot (uzywa
  `_save_report_snapshot`, ktora teraz zwraca `id` nowego wpisu - potrzebne dla
  raport-print.html, zeby zrzut renderowal DOKLADNIE te same dane co tresc maila, nie
  osobne przeliczenie z ryzykiem driftu np. pogody miedzy dwoma wywolaniami).

**Infrastruktura (jednorazowo, przez Desktop Commander SSH jako root):**
- `pip install playwright` do `.venv` + `playwright install --with-deps chromium`
  (dociaga tez zaleznosci systemowe apt - fonty, libnss, mesa itp., ~76 MB + ~290 MB miejsca).
- Binarki Chromium ladowaly sie domyslnie do `/root/.cache/ms-playwright` - NIEDOSTEPNE dla
  usera `qbot` (usluga qbot-web dziala jako `qbot`, `/root` ma uprawnienia 700). Przeniesione
  do `/opt/qbot/app/.ms-playwright` (chown qbot:qbot) + `Environment=PLAYWRIGHT_BROWSERS_PATH=
  /opt/qbot/app/.ms-playwright` dopisane do `/etc/systemd/system/qbot-web.service` +
  `daemon-reload` + restart. Katalog w `.gitignore` (binarny, ~300 MB, nie do repo).
- Zasoby serwera sprawdzone przed instalacja: 27 GB wolnego dysku, ~3.5 GB dostepnej
  pamieci - bezpieczne dla jednorazowego headless renderu na żądanie (nie stały proces).

**Wysylka:** `smtplib.SMTP_SSL('smtp.gmail.com', 465)`, to samo konto co poranny raport
(`qbot_config.GMAIL_USER`/`GMAIL_APP_PASSWORD`) - nic nowego do zakladania. Obrazki jako
inline (`Content-ID`, `cid:reportmap`/`cid:reportchart`), GPX jako zwykly zalacznik.
Walidacja adresu: prosty regex (`^[^@\s]+@[^@\s]+\.[^@\s]+$`).

**Nowy endpoint:** `POST /api/report/send-email?route_id=&date=&time=&long_stops=&
long_stop_min=&to=`. Zwraca `{status, to, has_map, has_chart, has_gpx}` - front pokazuje
blad jesli ktorys sie nie udal, ale wysylke i tak probuje (np. brak mapy nie blokuje maila).

**Dowod na zywo:** trasa 55957534, wyslano testowo na wlasny adres (z konfiguracji, nie
na obcy) - `{"status":"ok","has_map":true,"has_chart":true,"has_gpx":true}`, calosc (liczenie
+ zrzuty + wysylka) ~32 s.

**Front (raport-trasy.html, poza repo):** drugi wiersz paska - pole e-mail + przycisk
"Wyslij mailem" (`.row-mail`, `.btn-ghost`, `.fld.mail` w raport.css, cache-bust
`?v=2026070403`). Uzywa biezacych wartosci formularza (trasa/data/godzina/przerwy) - te
same co przy Generuj.

**Dlug techniczny / do obserwowania:** headless render dodaje ~5-10 s do czasu wysylki
(oprocz ~20 s liczenia danych) - akceptowalne dla akcji na żądanie, ale gdyby ta funkcja
kiedys mialaby dzialac masowo/w tle, warto rozwazyc pool przegladarek zamiast odpalania
nowej za kazdym razem. Brak retry przy niepowodzeniu zrzutu (map_png/chart_png=None) -
mail i tak leci, tylko bez obrazka/ow.


## 2026-07-04 (3) — Zakladka "Udostepnij", poprawki maila, zoom mapy, opady w mm

Feedback po 2 probkach maila -> lista poprawek:

**Wysylka mailem oparta o snapshot_id (nie route_id+parametry):** `POST /api/report/send-email`
zmieniony na `?snapshot_id=&to=`. Powod pytania uzytkownika "skoro tresc jest w raporcie,
czemu problem z przeniesieniem do maila" - odpowiedz: NIE MA problemu, mail bierze
DOKLADNIE ten sam zapisany raport co jest na ekranie (zero ponownego liczenia, zero
drugiego strzalu do LLM). `/api/report/data` i `/api/report/snapshot/{id}` teraz
dokladaja `data.snapshot_id` do odpowiedzi - front zna go bez dodatkowych zapytan.

**Nowa zakladka "Udostepnij"** (raport-render.js, MULTI array, po "Sprzet"): pole e-mail +
"Wyslij mailem" (woła `/api/report/send-email?snapshot_id=...`), 2 przyciski GPX (z POI /
bez), "Wyslij na Karoo". Usuniety stary pasek pod mapa (`#r-dl`, GPX+Karoo) i stary wiersz
w formularzu raport-trasy.html (`.row-mail`) - wszystko w jednym miejscu, zero duplikacji.

**Email - poprawki tresci:**
- Kafle hero: Dystans / Podjazdy / **Czas w ruchu** (bylo: Dystans / Podjazdy / Zjazdy -
  dwa kafle "przewyzszenie" mylily, brakowalo czasu).
- Nowa sekcja **Przewyzszenia** (podjazdy/zjazdy/liczba + lista, jak w interaktywnym
  raporcie) - wczesniej brakowalo jej calkowicie w mailu.
- **Strategia jazdy**: gdy LLM nie wygenerowal (zdarza sie, dwa wywolania LLM w
  `_report_prose` moga zawiesc) - czytelny komunikat zamiast cichego braku sekcji.
- **Czcionki**: dodano `font-family` na KAZDYM elemencie (wczesniej tabelka z kaflami
  hero nie miala wymuszonej czcionki -> w czesci klientow poczty pokazywala sie Times
  New Roman zamiast reszty tekstu - klasyczna pulapka email HTML, tabele/td nie
  dziedzicza fontu tak jak divy).
- **Opady w mm** (nie tylko %): nowa funkcja `_rain_summary(windows)` - deterministyczna
  (Python, NIE LLM - zgodnie z regula "liczby tylko z kodu"), bierze najgorsze okno
  30-min z `details.weather.windows` (`opad_mm`), pokazuje "Opady: do X mm (~Y%, km A-B)".
  Ten sam mechanizm (`rainSummary()`) dodany do interaktywnej zakladki Pogoda
  (raport-render.js) - dotad NIGDZIE (ani appka, ani mail) nie pokazywalo mm, tylko %.

**Zoom mapy (jeden kod, dwa miejsca - appka i mail-print, bo raport-print.html uzywa
tego samego raport-render.js):** `L.map(...)` dostal `zoomSnap:0.25, zoomDelta:0.5`
(bylo domyslne 1 - skok +/- byl za mocny, cale podwojenie skali za jednym klikiem).
Padding `fitBounds` zmniejszony z 25px na 12px (trasa lepiej wypelnia okno mapy przy
wstepnym dopasowaniu). Nie ruszane: `fitKm` (zoom na wybrany odcinek nawierzchni) -
tam wiekszy padding 30px jest celowy (kontekst wokol odcinka).

**Dowod na zywo:** pelny przeplyw przez Playwright (jak prawdziwy uzytkownik) - wybor
trasy -> Generuj -> klik zakladki "Udostepnij" -> wpisanie maila -> klik "Wyslij mailem"
-> potwierdzenie "Wyslano na ...", zero bledow JS w konsoli. Tresc maila zweryfikowana
programowo: obecne wszystkie 3 kafle, sekcja Przewyzszenia, linijka Opady, Strategia,
POI, 72 wystapienia font-family (spojna czcionka).


## 2026-07-04 (4) — Poprawki po 2. probce maila: escaping, kolory, czas przyjazdu, % nachylenia

**Bug: podwojne escapowanie "&middot;"** w linii moc/zywienie/pojenie strategii (email) -
`_esc(" &middot; ".join(bits))` zamienialo `&` na `&amp;`, wiec w mailu bylo widac
literalny tekst "&middot;" zamiast kropki. Naprawa: escapowac TYLKO pojedyncze elementy
PRZED join, nie caly juz-zbudowany string z encja HTML w srodku.

**Kolory naglowkow sekcji ujednolicone na czarny (INK)** - wczesniej SEC() mial domyslnie
szary (MUTED), a naglowek "Ostrzezenia" specjalnie czerwony -> wygladalo niespojnie.
Teraz WSZYSTKIE naglowki sekcji (Start i czas / Ostrzezenia / Mapa / Pogoda / Profil /
Nawierzchnia / Przewyzszenia / Strategia / POI) sa czarne; kolor ostrzegawczy zostaje
tylko na samych kartach alertow (border-left + tlo), nie na tekscie naglowka.

**Rozmiary czcionek skonsolidowane** do 8 celowych wartosci (bylo wiecej przypadkowych
"prawie takich samych" rozmiarow: 13/13.5 itp.) - kazdy rozmiar ma jedna, jasna role:
eyebrow 10.5 / stat-label 9.5 / naglowek sekcji 12 / meta (SZ_M) 12.5 / tresc (SZ) 14 /
stat-value 19 / tytul 22 / stopka 11.5.

**Godzina przyjazdu przeniesiona do "Start i czas"**: nowa linia "odjazd HH:MM -> przyjazd
ok. HH:MM" (liczona z `start.time` + `time.total_h`, ten sam wzor co `_finish` w
`_report_prose`). Wczesniej ta informacja byla tylko w interaktywnej appce (hero, sub pod
"Czas (z postojami)"), w mailu jej brakowalo.

**% nachylenia nad wykresami w zakladce Przewyzszenia** (raport-render.js,
`climbProfileSVG`): etykieta segmentu pokazywala samo `Math.round(gg)` bez znaku - np.
"8" zamiast "8%". Naprawione: `Math.round(gg)+'%'`.

**Sprawdzone i NIE jest bledem:** "zapisany raport gubi tresci LLM po odswiezeniu" -
zweryfikowano programowo (fresh generacja vs pozniejszy fetch tego samego snapshotu):
`details` dict identyczny 1:1 (strategia, pogoda.ogolne/etapy, sprzet.clothing - wszystko
zgodne). Zapis/odczyt snapshotu dziala poprawnie. Prawdopodobne wyjasnienie: LLM w
`_report_prose` bywa zawodny (2 wywolania, kazde moze sie nie udac) - jesli KONKRETNA
generacja nie dostala strategii/prozy pogodowej, TA WERSJA zostaje zapisana pusta w tych
polach i przy pozniejszym wczytaniu (w tym autoload po odswiezeniu) widac ten sam brak -
to nie jest utrata przy zapisie/odczycie, tylko odziedziczony stan z momentu generowania.
Do potwierdzenia z uzytkownikiem: czy twardy refresh/nowe okno dalej to pokazuje (mozliwe
tez, ze obserwacja byla na starej wersji z cache Cloudflare, jak wczesniej w tej sesji).


## 2026-07-05 (1) -- ModelQ Krok 1: rozdzielenie CP (krotkie okna) od LTP (dlugie okna)

**Diagnoza (zweryfikowana na zywo).** Kolumna `fitmodel_daily.cp_modelq_w` liczyla sie
z DLUGICH okien (300/600/1200/1800 s) i dawala 192.9 W -- co jest LTP, nie CP. Benchmark
potwierdzil: `cp_modelq_w` 192.9 vs Xert LTP 192.8 -> delta 0.1 W. Prawdziwy prog siedzi
w `ftp_est_w` = 252.8 W (Xert TP 249.2). Czyli "CP" bylo zle nazwane.

**Dowod danych (Krok 0).** training_sessions ma komplet krotkich okien MMP (mmp_30/60/120/
300/600_w) dla 267-268 jazd -- skalary z Garmina, NIE zaleza od zepsutego ingestu
activity_record 1Hz (stanal 28.06). Na twardych jazdach CP z okien 120/300/600 laduje przy
FTP (top ~246-256 W). W' z tych okien niewiarygodne (4-10 kJ, nie ~22) -> osobny Krok 2.

**Decyzja.** Rozdzielenie na dwie wielkosci w `fitmodel_daily`:
- `cp_modelq_w` (+ `cp_wprime_r2`, `cp_wprime_note`) = PRAWDZIWE CP z KROTKICH okien
  120/300/600 s (envelope 90d, regresja Work=CP*t+W'). Wartosc ~= FTP.
- `ltp_modelq_w` (+ `ltp_modelq_r2`, `ltp_modelq_note`) = LTP z DLUGICH okien
  300/600/1200/1800 s (dawna zawartosc cp_modelq_w). Odpowiednik Xert LTP.
- `wprime_modelq_kj` bez zmian (intercept dopasowania LTP) -- nadal NIEWIARYGODNE, jawnie
  zostawione dla Kroku 2 (null + range 13-22 kJ + confidence:low).

**Zmiany kodu.** `fitmodel/cp_wprime.py`: dwa dopasowania (CP krotkie / LTP dlugie).
`fitmodel/xert_bench.py`: porownanie LTP<->LTP bierze teraz `ltp_modelq_w` (nie
`cp_modelq_w`); prawdziwe CP jest juz benchmarkowane przez `ftp_est_w` vs `xert_tp_w`
(kolumna bench `cp_modelq_w` zachowuje historyczna nazwe, ale trzyma LTP ModelQ).
`qbot3/rides/ride_report_builder.py`: blok "forma" pokazuje CP i LTP (obie z metkami r2);
benchmark: klucze cp_* -> ltp_* (uczciwa etykieta porownania LTP-do-LTP).

**Backfill.** Dodane kolumny ltp_* (ALTER ADD, addytywne). Przeliczono cp_modelq_w/
ltp_modelq_w dla wszystkich istniejacych wierszy `fitmodel_daily` od 2025-10-01 (107 dni;
najstarszy realny wiersz to 2026-03-21). Tylko UPDATE istniejacych wierszy -- bez tworzenia
pustych rekordow. Wynik: CP 210-242 W, LTP 191-211 W.

**Weryfikacja.** Dry-run cp_wprime: CP=241.9 (r2=0.999), LTP=192.9 (r2=0.996), W'=34.84.
Benchmark: LTP 192.9 vs 192.8 (delta 0.1) OK; FTP 252.8 vs 249.2 (delta 3.6) OK.
py_compile OK dla 3 plikow, import ride_report_builder OK.


## 2026-07-05 (2) -- Karoo przepiete na ModelQ dla FTP+LTP (W' nadal Xert)

Endpoint `/ride-readiness` (qbot_api.py) dawal Karoo (QExt2) FTP/LTP/W' z ZYWEGO Xerta.
Dodano `_modelq_ftp_ltp()`: FTP=`ftp_est_w`, LTP=`ltp_modelq_w` z `fitmodel_daily` nadpisuja
wartosci Xerta tuz przed obliczeniem gotowosci. W' CELOWO zostaje z Xerta (~22 kJ,
zweryfikowane na drodze zdarzeniem W'bal=0%) -- ModelQ W' jest jeszcze niewiarygodne (Krok 2).

QExt2 czyta z tego endpointu pola `ftpWatts`/`ltpWatts`/`wPrimeKj` (JSON), wiec przepiecie
NIE wymagalo przebudowy apki ani wgrywania na Karoo -- czysta zmiana po stronie QBota.

Weryfikacja live: ftpWatts=252.8, ltpWatts=192.9, wPrimeKj=22.5, status=READY,
warning="ftp/ltp z ModelQ; W' z Xert". Fallback: gdy ModelQ puste -> zostaje Xert.

Pozostaje (TODO): po Kroku 2 przepiac tez W' na ModelQ i wtedy usunac zywe wywolanie Xerta
z endpointu (pelne odciecie Xerta).


## 2026-07-05 (3) -- WATEK 2 Strona B: QBot czyta developer fields QExt2 z FIT + KONTRAKT pol

Feasibility potwierdzona: `fit_ingest.py` czyta SUROWE pliki FIT z Karoo
(`outgoing/michal/hammerhead_originals/`), nie dane z API Garmina -> developer fields
QExt2 realnie dotra do QBota ta droga.

Dodano (Strona B, po stronie QBota):
- Tabela `qbot_v2.fitmodel_qext2_ride` (podsumowanie per jazda; self-create przez ensure_qext2_table).
- `parse_fit_qext2_records` + `summarize_qext2` + `upsert_qext2_ride` w fit_ingest.py.
- Hook w `ingest_fit_file` (bezpieczny: no-op gdy plik nie ma pol QExt2).
Weryfikacja: py_compile OK; stary FIT -> 0 rekordow QExt2, qext2_saved=False, segmenty
nietkniete, tabela powstala. Pelny test end-to-end dopiero po wdrozeniu Strony A + jezdzie.

KONTRAKT POL (developer data fields, developerDataIndex=0) -- Strona A (QExt2) MUSI pisac
DOKLADNIE te nazwy, B je czyta:
- qext2_wbal_pct     (uint8,  %)      W'bal 0-100
- qext2_cp_eff_w     (uint16, W)      efektywne CP (per tick)
- qext2_wprime_eff_kj(float32, kJ)    efektywne W' (per tick)
- qext2_cf           (float32, factor) readiness*upal*ostre zmeczenie
- qext2_wbal_zero    (uint8,  bool)   1 gdy W'bal==0 w tym rekordzie
- qext2_readiness    (float32, factor) todayFactor uzyty w jezdzie
- qext2_rsrv_pct     (uint8,  %)      RSRV zapas calej jazdy 0-100
Odrzucone swiadomie: wiatr (inne zrodlo niz kanoniczne Open-Meteo QBota -> unikamy 2 zrodel),
fueling (na razie). NP/IF/TSS/decoupling NIE zapisujemy -- QBot policzy z surowej mocy/HR.


## 2026-07-05 (4) -- Krok 2: W' z harvestu near-max + przedzial + pewnosc (koniec z 34.8 kJ)

Zawyzony W' z intercepta LTP (~34.8 kJ, submaks artefakt) PORZUCONY. Nowa metoda W' =
3 warstwy; wdrozone warstwy 2 i 3:
- (1, PENDING) kotwica z drogi: zdarzenie QExt2 W'bal=0% -- dojdzie ze Strona B (FIT).
- (2) HARVEST: w oknie 90d szukamy jazd z prawdziwie twardym krotkim fragmentem
  (mmp_60 LUB mmp_120 >= 0.92*best w oknie), liczymy W' z {60,120,300} (Work=CP*t+W'),
  bierzemy NAJWYZSZE (W' ujawnia sie tylko przy pelnym wyczerpaniu). Okno 30s odrzucone
  (inna fizjologia, zaniza fit).
- (3) brak swiezego (<=60d) twardego fragmentu -> wprime_modelq_kj=NULL + przedzial
  13-22 kJ + confidence:low. Zero zgadywania.
Pewnosc: high (<=30d i P120>=0.95*best), medium (<=60d), low (stara/brak -> przedzial).

Kolumny fitmodel_daily: wprime_modelq_kj (harvest lub NULL), wprime_lo_kj, wprime_hi_kj,
wprime_confidence, wprime_source. W' znika z dopasowania LTP w cp_wprime.py.

Weryfikacja (live): dzis W'=20.31 kJ, confidence=high, zrodlo "jazda 2026-06-05 (30d),
4 twarde w oknie" -- zgodne z kotwica z drogi (~22 kJ). Backfill 107 dni (high 90, medium 17).
py_compile OK, import ride_report_builder OK.

Raport jazdy: blok "forma" pokazuje teraz W' + pewnosc + przedzial. Wykres W'bal NADAL
uzywa W' z Xerta (~22) -- przelaczenie na ModelQ razem z Karoo w jednej przebudowie QExt2
(zeby QBot i Karoo sie nie rozjechaly). Karoo /ride-readiness W' tez przelaczymy wtedy.


## 2026-07-05 (5) -- WATEK 2 Strona A: QExt2 pisze pola do FIT (deploy key + CI build)

Strona A domknieta: rozszerzenie QExt2 (Kotlin, Karoo) zapisuje 7 developer data fields
@1Hz do pliku FIT jazdy -- te same nazwy/typy co KONTRAKT ze Strony B (wpis (3) wyzej).
Zmiany w QExt2 (OSOBNE repo github.com/QbotMS/QExt2, NIE /opt/qbot/app), commit 0b4ee18, +54/-2:
- extension_info.xml: fitFile="true" (rozszerzenie deklaruje zapis do FIT).
- StatsCalculator: gettery effectiveCpW()/effectiveWPrimeKj().
- RideDataAggregator + StatsRideSnapshot: +4 pola snapshotu (cfEff, cpEffW, wPrimeEffKj, readiness).
- QExt2PrimaryExtension.startFit(): emituje WriteToRecordMesg @1Hz (7 pol), tylko gdy W'bal>=0.
Marker 0%-zdarzenia jako osobny WriteEventMesg swiadomie POMINIETY w v1 (niepewne enumy) --
per-rekord flaga qext2_wbal_zero wystarcza.

DROGA WDROZENIA (bez tokena w jawnej postaci -- twarda granica Claude):
- deploy key ED25519 na serwerze (/root/.ssh/qext2_github_ed25519, alias SSH github-qext2),
  czesc publiczna autoryzowana przez Michala na GitHub (write access). Sekret nigdy nie przechodzi przez Claude.
- push: ssh q 'git -C /opt/qbot/qext2_deploy ...' (klon QExt2 na serwerze /opt/qbot/qext2_deploy, do reuzycia).
- APK buduje GitHub Actions (.github/workflows/build.yml, on: push main -> gradlew assembleDebug,
  JDK17, SDK na runnerze) -- lokalnie sie nie da (serwer i Mac bez Android SDK/Javy). Push = automatyczny build.

DOWOD: push 92ba3e4..0b4ee18 -> CI run #140 SUCCESS -> Release "QExt2 Auto Build" tag build-140,
app-debug.apk 4.35 MB. Kod skompilowal sie czysto za pierwszym razem mimo braku lokalnego builda.
Michal pobiera APK z Release i sideloaduje na Karoo.

POZOSTALO (osobne decyzje, nie zrobione): (a) przelaczyc W' na Karoo /ride-readiness z Xerta na
ModelQ (ModelQ W' juz wiarygodne, ~20.3 kJ high); (b) wykres W'bal w raporcie z Xerta na ModelQ;
(c) kosmetyczna etykieta zrodla w QExt2 (xertStatus -> ModelQ); (d) pierwszy realny test end-to-end:
po jezdzie z tym APK Strona B odczyta 7 pol z FIT do fitmodel_qext2_ride.


## 2026-07-05 (6) -- Naprawa zapisu zywienia: znikajace/podwojnie liczone posilki

**Diagnoza (4 rundy audytu, task_specs/TS-2026-07-05-NUTRITION-WRITE-FIX.md).** Objaw "jedzenie
znika" mial TRZY niezalezne przyczyny:
1. `daily_summary_compute` liczyl if/else (albo `intake_items` albo stary `meal_log_items`, NIGDY
   oba) -> pierwszy zapis dnia przelaczal "zeszyt" -> weryfikacja zapisu porownujaca sume dnia
   przed/po widziala spadek i kasowala poprawnie wstawiony wiersz.
2. Sprzeczny fragment promptu Alberta sugerowal nieistniejacy tryb draft/action_execute
   (sporadyczny, potwierdzony realnym zgloszeniem z ChatGPT).
3. Walidacja sugar-type w `_validate_and_fix_meal_items` zerowala makra/kcal niezaleznie od
   powyzszych dwoch przyczyn.

**Decyzja (P1 = wariant B).** Weryfikacja zapisu PO ID WSTAWIONEGO WIERSZA (istnienie + suma kcal
tego wiersza zgodna z oczekiwana), NIE po porownaniu sumy dnia przed/po. `daily_summary_compute`
liczy juz WYLACZNIE z `intake_items` (koniec przelaczania zeszytu).

**Zmiany i commity:**
- `e8f6b3a` -- P1 wariant B + hotfix: `meal_log_delete` przelicza cache po kasowaniu.
- `fb2290b` -- Etap 1: usunieta sprzeczna regula draft/action_execute z promptu Alberta;
  potwierdzenie tylko po `write_committed=true`.
- `532e2b4` -- watchdog: alert gdy kcal dnia < 50% mediany z 14 dni (lapie czesciowa utrate
  posilkow, nie tylko puste dni).
- `3813fdd` -- Etap 3a: `daily_summary_compute` tylko z `intake_items`.
- `b482076` -- Etap 3b: `build_snapshot` czyta z `qbot_v2.intake_logs` zamiast legacy (snapshot
  widzial 5 z 153 pozycji przed fixem).
- `c44e8a4` + `80dc5d6` -- wylaczenie nieuzywanego/nierzetelnego kanalu logowania jedzenia przez
  Telegram (kod martwy, potwierdzone 0 wpisow za ostatni tydzien).

**Pozostale (NIE zrobione, patrz TODO.md):** usuniecie walidacji sugar-type (przyczyna 3, plaster
zostaje), sierota w starym `meal_logs` (id=16), `_action_exec_nutrition_delete/correct`
(qbot_mcp_adapter.py) robi UPDATE bez filtra `source` (tor martwy, ale moze nadpisac cudze wiersze).


## 2026-07-04 (5) -- Logowanie do panelu qbot-web: formularz HTML + sesja HMAC

Cloudflare Access niedostepny na tym serwerze. Wdrozone dwuetapowo:
1. Basic Auth (login+haslo) na cala strone albert.cytr.us, /healthz bez zmian (commit c1a0ed0).
2. Formularz HTML logowania (autofill Keychain/Passwords: autocomplete="username"/
   "current-password") + ciasteczko sesji podpisane HMAC, wazne 365 dni (HttpOnly,
   SameSite=Lax). Token podpisu w .env.webauth jako WEBAUTH_TOKEN. Wszystkie trasy chronione
   oprocz /healthz i /login; endpointy /api/* zwracaja 401 JSON zamiast przekierowania.

**Weryfikacja na zywo:** pelny przeplyw potwierdzony -- brak sesji -> redirect /login; zle dane ->
blad; dobre dane -> ciasteczko + powrot; kolejne wejscie z ciasteczkiem -> bez ponownego
logowania; /api/* bez sesji -> 401.

**Uwaga dokumentacyjna:** kod jest obecny i aktywny na HEAD (_webauth_cookie_make w qbot_web.py),
ale dokladny numer commita etapu 2 (sam formularz HTML, w odroznieniu od Basic Auth c1a0ed0) nie
zostal jednoznacznie potwierdzony w historii gita przy pisaniu tego wpisu -- sesja wdrozeniowa
miala zawieszenie Desktop Commandera przy koncowym commicie. Jesli kiedys wazne, sprawdzic przez
przegladanie diffow wokol tego fragmentu.


## 2026-07-05 (7) -- Raport z jazdy: W1 automatyczny przy imporcie (Krok B) + W2 na zadanie + nowa lista jazd

**Ustalenie architektoniczne (koryguje wczesniejsze zalozenie).** Garmin Connect jest JEDYNYM
kanonicznym zrodlem danych jazdy (FIT z Garmina = te same dane co z Karoo + wylaczna analityka
Firstbeat: Training Load, MMP, strefy). Most Karoo->Garmin sluzy WYLACZNIE do dostarczenia jazdy
do Garmina, NIE jest wyzwalaczem dalszych krokow. `external_id` (numer Garmina) = klucz wiazacy
`activity_fit_raw`, `activity_record`, `training_sessions`, `ride_report_data`.

**Zrobione:**
- Backfill 3 brakujacych jazd w activity_record (01.07, 02.07, 04.07): ingested=3 skipped=335
  errors=0.
- Krok B: `_build_report_safe(aid)` wpiete w `ingest_one` (with_report=True) -- raport W1 (liczby)
  liczy sie AUTOMATYCZNIE przy kazdym imporcie jazdy i zapisuje pod external_id (ON CONFLICT DO
  UPDATE, jeden raport na jazde, nadpisywany).
- Cron co 15 min (9-23) na serwerze: backfill 20 0 2025-01-01 report.
- `/api/rides/ready` przepisany z ride_frames+blokada testowa na activity_fit_raw JOIN
  training_sessions (50 ostatnich jazd, numer Garmina, nazwa, flaga has_report).
- W2 (analiza LLM nad W1) zweryfikowana dla jazdy 23475899142 (Tarczyn) -- generowana WYLACZNIE
  na zadanie (rebuild=1), nie automatycznie (koszt LLM przy kazdym otwarciu).

**Commity:** e0f153e (Krok B), 78aa3b3 (Faza 3 W2 + /api/rides/ready).

**Odlozone:** historyczny backfill raportow wstecz (backfill 2000 0 2025-01-01 report) --
jednorazowe zadanie na pozniej.


## 2026-07-07 (1) -- Strefy HR na Karoo (Coggan %LTHR) + wiadra Low/High/Peak (zaplanowane, nie zrobione)

**Strefy HR (ZROBIONE i wypchniete):** poprzednia sesja (przerwana) ustalila LTHR=132 bpm
(32 odcinki 170-240W >=4min z 8 jazd, maj-lipiec, stabilne 5 miesiecy -- srednia 133.6, mediana
133.4, wazona dlugoscia 133.3, same >=8min: 130.1). Wybrany model: Coggan %LTHR (nie prostszy
wariant "te same progi co dzis tylko od LTHR") -- lepiej rozdziela mocne wysilki, poprawnie
klasyfikuje zdarzenie W'bal=0% jako Z5 (bylo Z3 w starym %maxHR).

Wdrozenie: `PrimaryRideSnapshot.kt` (`hrDisplay`), stala `LTHR_BPM = 132` (hardcode w companion
object, NIE z serwera/AthleteDataStore -- swiadomie prosciej na start, do rozwazenia pozniej jesli
LTHR bedzie trzeba przeliczac czesciej). Progi: Z1<107 / Z2 107-119 / Z3 119-125 / Z4 125-140 /
Z5>140 (81/90/95/106% LTHR). Commit `f13cd6b` w `QbotMS/QExt2` (main), push potwierdzony
(origin/main = HEAD). Michal: pobrac nowy APK z Releases po zakonczeniu builda CI i sideload przez
Hammerhead Companion, jak przy Stronie A.

**Wiadra Low/High/Peak (ZAPLANOWANE, KOD NIE PISANY):** odkryto ze silnik juz istnieje --
`fitmodel/buckets.py` (`compute_buckets`, i=moc/FTP, strain=i^4*100/3600, progi 0.90/1.20 +
przelew 10/10/5%), dzis liczony tylko offline po jezdzie (`fitmodel/ride_buckets.py`). Cel: to
samo live na Karoo. UI zatwierdzone przez Michala (mockup `mockup_wiadra_stats.html`): dolny
wiersz field_stats_3x3 -- BAT/h + BLEFT zostaja (to bateria Karoo, NIE AXS -- pierwotne zalozenie
bledne, skorygowane przez Michala), trzecia komorka (dzis "D BAT"/W' balance) -> 3 pionowe slupki
kolorowe (Low zielony #4ADE80 / High zolty #FACC15 / Peak czerwony #FF5252).

OTWARTE, NIE ROZSTRZYGNIETE: czy wypelnienie slupka = (a) % udzial w sumie strainu narastajacym w
jezdzie (prosty, gotowy do wdrozenia od reki) czy (b) % realizacji przewidzianego celu dla
KONKRETNEJ trasy (wymaga nowego, niezbudowanego modelu przewidywania rozkladu wysilku z profilu
trasy -- potwierdzono grepem, ze taki model dzis nie istnieje w kodzie). Michal nie zdecydowal --
pelny opis i TODO w `TODO.md` sekcja [WIADRA] (dodana 2026-07-07).


## 2026-07-07 (2) -- Kafelek WEB "Forma (ModelQ)": dane + zakres 90 dni + wykres, baner CTL/ATL

**Kontekst:** Michal poprosil o kafelek WEB dot. formy (jak raport trasy/jazdy), oparty o ModelQ:
forma aktualna, forma w definiowanym okresie, interaktywny wykres kluczowych parametrow.

**Zywy stan danych (sprawdzone, nie zgadywane):** `fitmodel_daily` ma 1589 dni (od 2022), ale
ModelQ realnie liczy od 2026-05-01. Od tej daty (68 dni, stan 2026-07-07): CP/LTP/W'(+pewnosc)
i `readiness_score/label/note` (gotowosc z HRV+RHR+sen, z-score vs baseline 60d) sa wypelnione
gesto (67-68/68) -- i NIEUDOKUMENTOWANE w MODELQ.md (dopisac przy okazji, dokument stary wzgledem
schematu). FTP_est 37/68, sen/RHR 34/68, glikogen 50/68, W/kg tylko 14/68 -- dziurawe.

**Decyzje (Michal, 2026-07-07):**
1. Geste serie (CP/LTP/W'/readiness/HRV) -> linie ciagle na wykresie. Dziurawe serie
   (FTP_est, W/kg, sen, RHR, glikogen) -> renderowane jako PUNKTY bez laczenia linia przez
   dziury (`showLine:false`/`spanGaps:false`), zeby nie sugerowac ciaglosci ktorej nie ma.
   Karta "Dzis" pokazuje dla kazdego pola ostatnia znana wartosc + date, jesli nie jest
   z dzisiaj (np. "W/kg: 2.49 (dane z 6 lipca)").
2. Domyslny zakres wykresu: 90 dni (presety 7/30/90/365 + wlasny zakres dat).
3. Gotowosc pokazuje tez pelny tekst uzasadnienia (readiness_note, z-score HRV/RHR/sen),
   nie tylko etykiete.
4. Prawdziwe CTL/ATL/TSB (forma w sensie TrainingPeaks) NIE ISTNIEJE jeszcze w silniku
   (patrz DECYZJA 2026-07-06 "XSS" -- EWMA-CTL swiadomie odlozone, za malo tygodni danych).
   Strona ma baner "W budowie" zamiast tej sekcji + gotowy kontrakt pod pozniejsze wpiecie
   (patrz Wdrozenie).

**Wdrozenie:**
- Endpoint `GET /api/forma/data?start=&end=` (`qbot_web.py`, funkcje `_build_forma_data` +
  `forma_data`) -- czyta `qbot_v2.fitmodel_daily` w podanym zakresie (`series`) + osobno ostatnia
  nie-null wartosc kazdego pola z ostatnich 400 dni niezaleznie od zakresu (`latest`), zeby waskie
  okno wykresu nie psulo karty "Dzis". Pole `training_load` zawsze `null` -- KONTRAKT: gdy silnik
  CTL/ATL/TSB (osobna sesja, dzis) bedzie gotowy, wystarczy wypelnic to pole (np.
  `{"ctl":.., "atl":.., "tsb":..}`) -- front automatycznie przelaczy sie z banera na wlasciwa
  karte formy, bez zmian w HTML/JS.
- Strona `forma.html` + `forma-render.js` w `/opt/qbot/web/public/` (POZA repo, zywe od razu,
  wzor jak `raport-jazdy.html` -- ten sam Chart.js 4.4.1 z CDN, ta sama paleta CSS).
- Kafelek w `index.html` ("Forma (ModelQ)", badge "na zywo").
- Zweryfikowane na zywo: wywolanie `_build_forma_data` bezposrednio na produkcyjnej bazie
  (zakres 2026-06-08 -> 2026-07-07) zwraca poprawny, JSON-serializowalny wynik; `qbot-web`
  zrestartowany po zmianie `qbot_web.py`, usluga `active`.

**NIE zrobione (swiadomie, nastepny krok):** sekcja CTL/ATL/TSB (czeka na osobna sesje Michala);
ewentualne dopisanie `readiness_score/label/note` do schematu w `MODELQ.md` (dokument stary).


## 2026-07-07 (3) -- FTP/CP/LTP/W': diagnoza "absurdalnej zmiennosci" + decyzja tlumienia i zaniku (SPECYFIKACJA, KOD NIE PISANY)

**Kontekst:** przy budowie kafelka Forma Michal zauwazyl skoki FTP_est (+27W w jeden dzien,
5->6 marca 2026) i spadek (-9W, 11->12 kwietnia). Zbadano zywy kod i dane -- rozszerzono na
CP/LTP (podobne, gorsze) i W' (juz czesciowo zaadresowane).

### FTP_est -- wina modelu (brakujaca implementacja)

Mechanizm: `EF_med_28d` to mediana z segmentow w oknie 28 dni. Zywy dowod (`ftp_resolver.py`,
`compute_ef_median`): 5.03->5.06.2026 mediana skoczyla 1.473->1.651 bo z okna wypadly 4 slabsze
segmenty z 5.02 (EF ~1.29-1.45), zostaly glownie mocne segmenty z grupowej jazdy 4-5.03
(EF ~1.6-1.8). Analogicznie spadek 11->12.04 (wypadly 2 mocne segmenty z 14.03).

MODELQ.md par.4.3 opisuje tlumienie "zmiana_tyg = clip(+/-0.5*delta), tlumienie 50%,
anti-jitter" -- **sprawdzono grepem w `ftp_resolver.py`: tego tlumienia NIE MA w kodzie**.
FTP_est leci 1:1 za skladem mediany, bez wygladzenia.

**Decyzja:** dopisac brakujace tlumienie zgodnie z JUZ ISTNIEJACYM opisem w MODELQ.md 4.3
(to przywrocenie udokumentowanego zachowania, nie nowy projekt). Ograniczyc dzienna zmiane
FTP_est do +/-50% delty wzgledem dnia poprzedniego.

### CP/LTP -- wina modelu (zla konstrukcja, gorsza niz FTP)

Mechanizm: `_envelope_curve()` bierze `MAX(mmp_{d}_w)` per dlugosc (CP: 120/300/600s, LTP:
300/600/1200/1800s) w oknie 90 dni, z ROZNYCH jazd, i dopasowuje linia prosta przez raptem
3 (CP, wszystkie wymagane) albo 3-4 (LTP, min 3) punkty. Zywy dowod: 19->20.06.2026 najlepszy
wynik 10-min wszedl do okna (242W->266W z jednej zwyklej jazdy) -> CP 210->242W (+31W/dzien).
8->9.06 najlepszy 10-min WYPADL z okna (251W->242W) -> CP 222->210W (-12W). r^2~1.0 przy kazdym
skoku -- przy n=3 to nic nie mowi o jakosci (linia przez 3 punkty prawie zawsze "pasuje idealnie").
Zero tlumienia w `cp_wprime.py` (sprawdzone grepem).

**Rozstrzygniecie filozoficzne (Michal):** skok W GORE po mocnym wysilku jest zasadny (twardy
dowod zdolnosci, natychmiastowa rewizja w gore OK). Spadek z dnia na dzien TYLKO dlatego ze stary
rekord wypadl z okna -- NIE jest zasadny (detrening to tygodnie, nie przelacznik). Model
potrzebuje asymetrii: szybko w gore na nowym dowodzie, wolno w dol przy braku dowodu.

**Decyzja (potwierdzona):**
1. Grace period 60 dni pelnego zaufania od dnia ustanowienia rekordu (zgodnie z juz istniejacym
   `PP_FRESH_DAYS=60` dla Peak Power -- ten sam prog, spojnosc).
2. Dni 60-120: **liniowy** zanik od wartosci rekordu do podlogi (nie wykladniczy -- brak podstaw
   fizjologicznych do konkretnego ksztaltu, liniowy jest prosty do wytlumaczenia i debugowania,
   spojny z filozofia ModelQ "prostota ponad wyrafinowanie" -- por. tlumienie FTP=stala 0.5,
   LTHR na sztywno).
3. Po dniu 120: trzyma podloge, dopoki nie pojawi sie nowy twardy wynik.
4. **Podloga CP i LTP = FTP_est** (biezacy, z czestszego silnika EF) -- brak swiezego dowodu na
   cos wiecej -> wracamy do tego, co wiemy na pewno.
5. Architektura: dzisiejsze `MAX()` w oknie 90 dni trzeba ROZDZIELIC od wygasania -- szukanie
   rekordu bez sztywnego okna (albo dlugie, np. 365 dni, zeby stare rekordy sprzed lat nie liczyly
   sie wiecznie), a wiek/zanik liczony WYLACZNIE z daty ustanowienia rekordu, nie z granicy okna
   zapytania. Otwarte do wdrozenia: gdzie trzymac (wartosc, data) per dlugosc -- nowe kolumny czy
   osobna tabela `fitmodel_cp_records` (per duration, per metric).

### W' -- juz czesciowo zaadresowane, brakuje zaniku

`_wprime_harvest()` juz ma `WPRIME_FRESH_DAYS=60` (ten sam prog!) -- ale po przekroczeniu 60 dni
skacze NATYCHMIAST z konkretnej liczby na staly przedzial 13-22 kJ (`_range()`), bez zaniku.

**Decyzja:** dodac ten sam wzorzec co CP/LTP -- dni 60-120 liniowy zanik z wartosci harvestu do
podlogi. **Podloga W' = 13 kJ (dolna granica przedzialu, NIE srodek 17.5 kJ)** -- swiadomie
zachowawczo, bo W' steruje pacingiem/rezerwa (Karoo) i lepiej zanizyc niz przeszacowac ("zero
wysilkow do trupa", spojne z filozofia ModelQ).

### Status

**SPECYFIKACJA ZATWIERDZONA (Michal), KOD NIE PISANY.** Dotyka `fitmodel/ftp_resolver.py` (FTP
tlumienie) i `fitmodel/cp_wprime.py` (CP/LTP ratchet+zanik, W' zanik) + prawdopodobnie nowa
tabela/kolumny na (wartosc, data) rekordu per dlugosc. Pelny opis w `TODO.md` sekcja [FORMA-MODEL].


## 2026-07-07 (4) -- FTP/CP/LTP/W': WDROZONE + zweryfikowane na zywo

Implementacja specyfikacji z 2026-07-07 (3). Zmiany w `fitmodel/ftp_resolver.py` i
`fitmodel/cp_wprime.py`, nowa tabela `qbot_v2.fitmodel_cp_records` (ratchet: duration_s PK,
best_w, best_date, updated_at).

**FTP tlumienie:** `apply_ftp_damping()` + `_fetch_last_ftp_est()`, uzywa istniejacego
`ftp_damping_factor=0.5` z `fitmodel_param` (byl w bazie, nigdy nieczytany). Test na znanym
przypadku 5->6 marca: surowy skok +27,2W -> po tlumieniu +13,6W. `notes` w `fitmodel_daily`
teraz pokazuje `ftp_raw=...; damping=0.5` dla przejrzystosci.

**CP/LTP ratchet+zanik:** `_update_cp_records()` (ratchet, wolane z `run_daily` przed liczeniem,
pomijane przy `dry_run`), `_envelope_curve_decayed()` zastepuje surowy `_envelope_curve()` w
`compute_cp_wprime`. Podloga = biezacy `ftp_est_w` (fallback `ftp_anchor_w`). Zasiew ratchetu na
zywej bazie: 120s=367W(05.06), 300s=280W(20.06), 600s=266W(20.06) -- wszystkie < 60d, bez zaniku,
CP=241,9W (identyczne z wynikiem sprzed zmiany -- brak regresji na swiezych danych). 1200s=248W
(10.09.2025!) i 1800s=232W(24.09.2025) -- >300d, w pelni zdryfowane do podlogi. Symulacja w przod
(bez zapisu): 07.09->08.09 bez zmian (w grace), 03.09.2026 czesciowy zanik (CP 241,9->250,9,
krzywa 367/280/266 -> 309,6/273,1/262,6), 01.11.2026 pelny zanik (curve = {252.3,252.3,252.3},
CP=252,3=floor dokladnie). Mechanizm dziala zgodnie ze specyfikacja: brak wiecej "urwiska".

**W' zanik:** analogiczny liniowy zanik 60->120d do podlogi `WPRIME_RANGE_LO=13kJ` (zamiast
natychmiastowego skoku do przedzialu 13-22). Dzisiejszy przypadek (32d) nadal w grace period,
bez zmiany (20,31 kJ, confidence medium) -- brak regresji.

**Zapis na zywo (prawdziwy, nie dry-run):** `update_fitmodel_daily` + `cp_wprime.run_daily`
uruchomione dla 2026-07-07, zapisane do `fitmodel_daily`. `qbot-api` zrestartowany, smoke
`/fitmodel/buckets/active` OK (`ftp_w=252.3`).

**Testy:** `pytest` (425 testow) -- 14 niepowiazanych failow w innych modulach (route POI, nutrition,
capabilities) sprzed tej zmiany, zero dotyczy fitmodel/ftp_resolver/cp_wprime (brak dedykowanych
testow jednostkowych dla tego pakietu -- do rozwazenia osobno).

Commit `cd1ce29`, push potwierdzony (`fb18c50..cd1ce29`).

**NIE ZROBIONE (do decyzji z Michalem):** czy przeliczyc historycznie (backfill) cala
`fitmodel_daily` nowa logika, czy zostawic historie jak jest i dzialac tylko od teraz. Ratchet
(`fitmodel_cp_records`) jest juz zasiany z pelnej historii `training_sessions`, wiec backfill
dotyczylby tylko przepisania kolumn `ftp_est_w`/`cp_modelq_w`/`ltp_modelq_w`/`wprime_*` w starych
wierszach `fitmodel_daily`.


## 2026-07-07 (5) -- Backfill FTP/CP/LTP/W': decyzja Michala + zakres + wdrozenie

**Decyzja (Michal, 2026-07-07):** przeliczyc historie nowa logika (nie zostawiac jak jest).

**Znaleziona niezacommitowana zmiana w `fitmodel/cp_wprime.py` (przed backfillem):**
Ratchet oparty o tabele `fitmodel_cp_records` (najlepszy wynik W CALEJ HISTORII, bez granicy
czasowej) psulby przeliczanie starych dni -- dzien X widzialby rekordy ustanowione PO dniu X
(podgladanie przyszlosci). Zastapione `_best_effort_asof()`: liczy najlepszy wynik na zywo
`WHERE date <= as_of`, poprawne dla kazdego dnia backfillu z osobna. Dodatkowo: clamp -- gdy
surowy fit CP/LTP wychodzi PONIZEJ podlogi FTP_est (zdegenerowany fit przy w pelni zdryfowanych
punktach krzywej), podnoszony do podlogi z jawna notatka UWAGA. `fitmodel_cp_records` zostaje w
bazie jako nieuzywana (juz nieczytana) -- do ewentualnego pozniejszego dropu, nie pilne.
Zweryfikowane: pelny pytest przed commitem -- 425 testow, 14 niepowiazanych failow (te same co
przed zmiana), zero w fitmodel/ftp_resolver/cp_wprime. Commit `32bbe6e`.

**Zakres backfillu (zweryfikowany na zywo):** `fitmodel_daily` ma dane od 2022-03-02 (1589 dni),
ale kolumna `ftp_est_w` jest wypelniona dopiero od 2025-01-01 (553 dni) -- to jedyny sensowny
zakres do przeliczenia (przed tym brak segmentow/danych zrodlowych, przeliczanie byloby no-opem).
W ramach tych 553 dni: 2025-01-01..2025-05-31 (151 dni) maja dane do FTP (tlumienie), ale za malo
historii `training_sessions.mmp_*` (zaczyna sie 2025-05-01) dla sensownego CP/LTP -- te dni dostana
tylko przeliczone FTP, CP/LTP zostana null/za malo punktow (oczekiwane, nie blad). Od 2025-06-01
(402 dni) do dzis -- pelne przeliczenie FTP+CP/LTP/W'.

**Metoda:** chronologicznie (rosnaco po dacie), dla kazdego dnia: `update_fitmodel_daily(conn, day)`
(FTP z tlumieniem -- MUSI byc chronologicznie, bo czyta poprzedni ZAPISANY dzien) nastepnie
`cp_wprime.run_daily(conn, as_of=day, dry_run=False)` (CP/LTP/W' z podloga = swiezo przeliczony
FTP_est tego dnia). Skrypt jednorazowy, bez zapisu do repo (`scripts/_tmp_backfill_fitmodel.py`,
self-cleanup po uruchomieniu).

**Wynik:** Backfill wykonany w calosci -- 553/553 dni (2025-01-01..2026-07-07), 0 bledow.
Wykonany w kilku partiach (limit czasu pojedynczego polaczenia), zweryfikowany po kazdej
partii zapytaniem do bazy. Test 5->6 marca 2026 potwierdzony na realnych danych: surowy
FTP_est skoczylby z 225.5W do 252.8W (+27,3W), po tlumieniu 0.5 wyszlo 222.95W -> 237.85W
(+14,9W) -- zgodne z formula (poprzednia + 0.5*(surowa-poprzednia)). Dni 2025-01-01..2025-05-31
(151 dni) maja poprawnie przeliczone samo FTP -- CP/LTP tam null/za malo punktow, zgodnie z
przewidywaniem (brak historii `training_sessions.mmp_*` przed 2025-05-01). TODO.md wpis (5)
oznaczony jako zrobiony.


## 2026-07-07 (6) -- CTL/ATL/TSB wpiete do kafelka WEB "Forma"

Silnik (`fitmodel/training_load.py`) juz gotowy i ma dane (433 dni) -- API `/api/forma/data`
mialo pole `training_load` na sztywno `None` jako placeholder (patrz TODO.md, DECISIONS.md
2026-07-07 (2)). Front (`forma-render.js`) czeka na ksztalt `{"ctl":.., "atl":.., "tsb":..}`.

**Decyzja (domyslna, do korekty jesli Michal chce inaczej):** w banerze pokazujemy warianty
"raw" (ctl_xss/atl_raw/tsb_raw -- standardowy Bannister/Coggan, porownywalny z innymi
narzedziami typu TrainingPeaks) jako glowne ctl/atl/tsb. Warianty "plus" (skorygowane
readiness_score) dolaczone w payloadzie jako `atl_plus`/`tsb_plus` -- gotowe do pokazania
pozniej, front ich dzis nie czyta (bez zmian w JS/HTML, zgodnie z pierwotnym kontraktem).

**Zmiana:** `qbot_web.py`, nowa funkcja `_build_training_load_latest()` -- ostatnia NIE-NULL
wartosc z `fitmodel_daily` (okno 400 dni wstecz, ta sama konwencja co reszta kafelka "Dzis").
`_build_forma_data()` woa ja zamiast zwracac `None`.

**Zweryfikowane:** wywolanie `_build_forma_data()` bezposrednio (z pominieciem HTTP/auth) na
zywej bazie -- zwraca `{"day": "2026-07-07", "ctl": 81.49, "atl": 66.52, "tsb": 5.87,
"atl_plus": 58.91, "tsb_plus": 14.74}`. Restart `qbot-web` wykonany (przez Qbot DEV MCP --
MacOS-MCP Shell i Desktop Commander zawiesily sie ta sesje, oba kanaly SSH niedostepne).
Pelny pytest po zmianie: 425 testow, 14 niepowiazanych failow (te same co przed zmiana), zero
w qbot_web/fitmodel.


## 2026-07-07 (7) -- fitmodel: zrodlo FIT hammerhead -> archiwum Garmina (koniec duplikacji segmentow)

**Root cause "absurdalnej zmiennosci" FTP/CP (uzupelnia wpis (3)).** Warstwa segmentow EF
karmila sie z DWOCH zrodel: outgoing/michal/hammerhead_originals (Karoo) ORAZ archiwum
Garmina (jednorazowy backfill). Ta sama jazda ma dwa rozne ride_id (Karoo: nazwa pliku
"hammerhead_...", Garmin: numer) -> UNIQUE INDEX (ride_id, started_at) oraz test istniejacej
jazdy po ride_id (fit_ingest.ingest_all_new) NIE lapaly duplikatu miedzy zrodlami.
Efekt: 66 grup duplikatow (72 nadmiarowe wiersze) na 415, ~33% tabeli fitmodel_segment,
zakres 2026-05-02..2026-07-06 (nadal aktywne). W dolku maja (19/23/27.05) dni raportujace
n=2 to byly pojedyncze segmenty zdublowane (n=1) -> mediana EF z jednego latwego segmentu +
10-dniowa dziura danych -> FTP_est zjechal 250->220 mimo braku spadku formy.

**Weryfikacja (na zywo):** garminowy FIT ZACHOWUJE developer fields QExt2 (most Karoo->Garmin
przepuszcza plik 1:1). Parowanie po czasie startu wszystkich 33 karoowych jazd: 0 jazd
tylko-hammerhead, 0 przypadkow "hammerhead ma qext2, garmin nie" -> przelaczenie niczego nie
traci. Jazd wirtualnych: 0; archiwum Garmina pobierane wylacznie dla kolarstwa
(qbot_activity_ingest _is_cycling) -> brak ryzyka trenazera/nie-kolarstwa.

**Decyzja (Michal):** hammerhead wylaczony jako zrodlo danych WSZEDZIE poza rola mostka
(konwersja/wysylka FIT do Garmina, poza QBotem). Dane jazd wylacznie z Garmin API.

**Zrobione (krok 1):** FIT_DIR przepiety z hammerhead_originals na /opt/qbot/artifacts/fit
w 10 plikach: fitmodel/{daily_job,ingest_qext2_fit,fit_ingest,cp_wprime,buckets,glycogen,
ride_buckets,surface_tag}.py, tools/rwgps/ride_overlay.py, qbot_query_handler.py. Zostawione
(mostek/porzadki): qbot3/capabilities/system/hammerhead_sync_status.py, qbot_route_tools.py,
scripts/prune_qbot_artifacts.py. Zweryfikowane: import OK, stale wskazuja archiwum Garmina,
zero konsumenta na hammerheadzie. UWAGA: ingest_qext2_fit.py nazwa/docstring mylaca (czyta
teraz Garmina) -- do poprawy przy centralizacji stalej.

**Do zrobienia:** (2) kopia + DELETE 66 grup duplikatow; (3) doczyt brakujacych garminowych
jazd do fitmodel_segment; (4) przeliczenie FTP/CP od zera; (5) centralizacja stalej FIT_DIR +
utwardzenie modelu (asymetryczny bezpiecznik dol max ~2%/tydz, waga swiezosci, defensywny
filtr virtual/indoor w ingescie).


## 2026-07-07 (8) -- FTP_est: zanik w dni bez jazdy zamiast twardego okna 28 dni (kalibracja z Xerta)

**Problem (koryguje wpisy (3) i (7)).** Dolek FTP 250->220 w kilka dni NIE byl spowodowany
duplikatami (mediana z identycznych duplikatow = mediana z pojedynczych, bez zmian -- to byla
moja pomylka w diagnozie). Prawdziwa przyczyna: twarde okno 28 dni. W 10-dniowej dziurze bez
jazdy (28.05-05.06) dobre segmenty z poczatku maja wypadaly zza krawedzi okna, mediana EF
zjezdzala sama z siebie, a tlumienie gonilo ja w dol: FTP lecial 237->219 (-18 W) MIMO braku
jakiejkolwiek jazdy. Fizjologicznie niemozliwe.

**Slad z Xerta (surowe qbot_v2.xert_profile_snapshots, nie benchmark).** W dni bez jazdy Xert TP
zanika lagodnie ~0.5 W/dzien; ciag 21-27.06: 253.0->249.7 (dzienny spadek maleje monotonicznie
0.559->0.514 w miare zblizania do LTP). Dopasowanie: model staly (dTP) i proporcjonalny
(k=dTP/(TP-LTP)) na waskim zakresie luki (52-58 W) daja niemal rowne CV (0.270 vs 0.263) --
statystycznie remis. Rozstrzyga KSZTALT (malejacy dzienny spadek) + fizjologia (staly zanik w W
przebilby LTP w dol): wybrany model WYKLADNICZY w strone LTP, k~0.009/dzien z luki (TP-LTP).

**Podloga zaniku.** ltp_modelq_w jest tu ZDEGENEROWANE: na rzadkich danych fit CP/LTP pada,
clamp cp_wprime dociaga CP i LTP do podlogi = FTP_est -> w bazie FTP=CP=LTP co do dziesiatej
(potwierdzone 20.05-10.06). Wiec ltp_modelq_w nie nadaje sie na podloge (luka=0, brak zaniku).
Uzyta stabilna, zmierzona podloga aerobowa z param: ftp_decay_floor_w=193 (Xert LTP, benchmark
192.9 vs 192.9).

**Wdrozone (ftp_resolver.update_fitmodel_daily).** Rozgalezienie:
- DZIEN Z JAZDA (kwalifikujacy segment tego dnia AND readiness!=0): mediana EF + tlumienie (bez zmian).
- DZIEN BEZ JAZDY: ftp_est = floor + (prev - floor) * (1 - k), floor=193, k=0.009.
Nowe pomocnicze: _has_qualifying_segment_on_day. Usunieto _fetch_last_ltp (zdegenerowane).
Parametry jako defaulty w kodzie (params.get): ftp_decay_k=0.009, ftp_decay_floor_w=193 --
do dodania w fitmodel_param dla strojenia. notes zawiera mode=ride|decay|bootstrap oraz decay_k.

**Wynik (backfill 2026-05-01..dzis, 68 dni, 0 bledow).** Dziura 28.05-05.06: 237.6->234.5
(-3 W, ~0.4 W/d) zamiast 237->219. Dni z jazda bez zmian.

**Pozostaje (osobne):** (a) w dni z jazda EF zanizza FTP na latwych jazdach turystycznych
(problem kalibracji EF<->FTP na danych submaksymalnych, nie ten bug); (b) dedup w ingescie
(UNIQUE started_at + ON CONFLICT) zamiast recznej kwarantanny 2 plikow; (c) zdegenerowany
CP/LTP przy rzadkich MMP -- oddzielny watek.
