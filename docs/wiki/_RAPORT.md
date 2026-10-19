## Spójność końcowa przebiegu 2 -- 18.10.2026 15:25

- Zaktualizowano `README.md`: liczby haseł w 12 działach (151 łącznie) oraz linki do mapy serwisu, zależności, słowniczka i indeksu zrzutów. Wszystkie hasła działów są dostępne z indeksu.
- Poprawiono nieistniejące linki w `mapa-serwisu.md` i szablonie. Pełny skan: 0 uszkodzonych linków, kotwic i obrazów. Słowniczek ma 108 nagłówków; każdy termin ma definicję i link do hasła. Dodano brakujące definicje dla Kod QR, Web Push, UI2 i LTHR.
- Przejrzano opisy wielokrotnie liczonych miar w `zaleznosci.md`: XSS, CTL/ATL/TSB oraz W′bal rozróżniają osobne warianty i źródła; nierozstrzygniętą zgodność W′bal opisano jako niepotwierdzoną.
- Długość 151 stron działów, łącznie z indeksami: średnio 3 720 bajtów (484 słowa) na stronę. Nie wszystkie hasła osiągają typowe 4–10 KB; rozbudowa krótkich haseł i przykłady krok po kroku dla każdego algorytmu wymagają dalszej pracy.
- Pytania do Michała zebrane z etapów: (1) czy zwykły tekst Telegrama ma docelowo przechodzić przez Alberta; (2) czy może udostępnić zrzut otwartej zakładki QExt2/ekranu Karoo oraz odpowiedzi gotowości i danych rzeczywiście odebranych przez urządzenie. Pozostałe otwarte punkty wymagają odczytu systemu lub bazy, nie decyzji właściciela.

# Raport etapów

## QExt2 — pogłębienie -- 18.10.2026 15:12

- Rozbudowano 9 istniejących haseł i dodano `qext2/komunikaty.md` oraz `qext2/dane-trasy.md` dla wcześniejszych braków. `index.md` zawiera przegląd wymiany danych, tabelę ekran → hasło i zrzut SETUP. Dodano `img/qext2-wbal-przyklady.svg`; uzupełniono `_lista_hasel.md`, słowniczek, mapę zależności i `_DO_SPRAWDZENIA.md`.
- Sprawdzono bieżące endpointy QBota, kod odczytu FIT, kod QExt2 dla AUTO/pacingu/bramy/pola AERO, dokumenty QExt2 i SETUP WWW. Baza potwierdziła zapis z 16.10.2026 (4 026 próbek, W′bal min 40%, końcowe 83%) oraz z 18.10.2026 (8 743 próbki kontroli wiatru, mediana 2,4 m/s, 11,4% próbek pod wiatr).
- Rozjazd: `docs/QEXT2_CONFIG.md` nie opisuje nowszych dodatków INFO, AERO i rozszerzonych pól FIT; przyjęto bieżący kod. Zrzut SETUP pokazuje zakładkę QExt2 zamkniętą, nie zawartość ani ustawienia urządzenia.
- Nie potwierdzono zrzutu aktywnego Karoo, odpowiedzi gotowości faktycznie odebranej przez urządzenie, historii decyzji AUTO/pacingu, wyniku AERO w bazie, historycznej próby bramy ani zapisanych odpowiedzi profilu trasy i typowego EF. Otwarte punkty dopisano do `_DO_SPRAWDZENIA.md`.
- Pytania do Michała (max 5): czy może udostępnić zrzut otwartej zakładki QExt2/ekranu Karoo, próbkę odpowiedzi gotowości, historię próby bramy oraz przykład danych trasowych użytych przez urządzenie?

## Pogoda — pogłębienie -- 18.10.2026 14:53

- Rozbudowano `pogoda/index.md` i istniejące hasła: `prognoza.md`, `wiatr.md`, `radar.md`, `ostrzezenia.md`, `sprawdzalnosc.md`, `pogoda-na-trasie.md`, `okno-jazdy.md`, `qext2.md`; dodano odnośniki do zrzutów.
- Dodano: `pogoda/charakter-dnia.md`, `pogoda/warunki-punktowe.md`, `pogoda/mapa-modeli.md`, `pogoda/weekend.md`, `pogoda/ubior.md` oraz wykres `img/radar-sprawdzalnosc.svg`. Zaktualizowano `_lista_hasel.md`, `slowniczek.md`, `zaleznosci.md` i `_DO_SPRAWDZENIA.md`.
- Baza potwierdziła odczyt z 18.10.2026 14:40: przy wyprzedzeniu 30 min 0 trafień, 0 fałszywych alarmów, 2 przeoczenia i 958 poprawnych wskazań braku opadu. Zapis jest pojedynczą próbką.
- Nie potwierdzono: pełnych wag oceny weekendowej, wszystkich kolorów i modeli mapy, przykładu z bazy dla charakteru dnia, przykładowej rekomendacji stroju ani renderowania pogody na urządzeniu QExt2. Zapisano je w `_DO_SPRAWDZENIA.md`.
- Pytania do Michała: brak.

## Połączenia — 18.10.2026 10:29

- Powstały: `polaczenia/index.md`, `garmin.md`, `hammerhead-garmin.md`, `withings.md`, `komoot.md`, `rwgps.md`, `strava.md`, `intervals-icu.md`, `xert.md`, `harmonogram-importow.md`, `uslugi-zewnetrzne.md`; poprawiono `_lista_hasel.md`, `zaleznosci.md`, `slowniczek.md` i `_DO_SPRAWDZENIA.md`.
- Sprawdzono `docs/GARMIN_DANE.md`, `docs/STATUS.md`, `docs/SETUP.md`, `docs/STRAVA_PUBLISH.md` oraz bieżący kod statusu Garmin/Hammerhead/Withings/Komoot i pętlę publikacji Stravy. Podstawowe interwały statusu zgadzają się z kodem; rzeczywistych crontabów/timerów nie odczytano.
- Rozjazd/ograniczenie: Garmin_DANE i STATUS są opisami datowanymi 14–15.10.2026; weryfikacja kodem potwierdziła opisane interwały importu. `STRAVA_PUBLISH.md` z 09.10 zgadza się z kodem pętli publikacji. Nie potwierdzono bieżącego połączenia intervals.icu.
- Nie zdążono: przykłady z bazy dla integracji, sprawdzenia zalogowanego widoku ani pełnego katalogu usług zewnętrznych. Otwarte kwestie wpisano do `_DO_SPRAWDZENIA.md`.
- Nie zdążono: szczegółowych opisów harmonogramów dostawców, których aktywnej konfiguracji nie odczytano.
- Pytania do Michała: brak.

## Pogoda -- 18.10.2026 10:16

- Powstały: `pogoda/index.md`, `pogoda/prognoza.md`, `pogoda/wiatr.md`, `pogoda/radar.md`, `pogoda/ostrzezenia.md`, `pogoda/sprawdzalnosc.md`, `pogoda/okno-jazdy.md`, `pogoda/pogoda-na-trasie.md`, `pogoda/qext2.md`; uzupełniono `_lista_hasel.md`, `zaleznosci.md`, `slowniczek.md` i `_DO_SPRAWDZENIA.md`.
- Sprawdzono wskazane dokumenty źródłowe, kod silnika punktowego, radaru, sprawdzalności, alertów, Okna jazdy, silnika trasowego, endpointów QExt2 oraz aktualny plik strony Pogoda. Odczyt bazy (18.10.2026 10:05) potwierdził pojedyncze przykłady oceny radaru: 30 min — 0 trafień, 0 fałszywych alarmów, 1 przeoczenie, 959 poprawnych wskazań braku opadu.
- Rozjazd: `docs/METEO_ENGINE.md` z 01.07.2026 mówi, że silnik nie jest wpięty w ścieżki użytkowe; bieżący kod używa go w analizie/raporcie trasy i QExt2. `docs/POGODA_RADAR.md` nie opisuje całego obecnego interfejsu. Kod przyjęto jako źródło prawdy.
- Nie potwierdzono: zalogowanego widoku WWW ani renderowania wszystkich pól po stronie QExt2; przykładu zapisanej prognozy trasy; aktywnego wiersza alertu. Szczegóły wpisano do `_DO_SPRAWDZENIA.md`.
- Nie zdążono: osobnych haseł dla charakteru dnia, warunków punktowych, mapy modeli i zespołu, pogody weekendowej oraz doboru ubioru. To dodatkowe funkcje widoczne lub używane na stronie.
- Pytania do Michała: brak.

## Forma -- 18.10.2026 10:07

- Powstały: `forma/index.md`, `forma/ctl-atl-tsb.md`, `forma/status-dnia.md`, `forma/gotowosc.md`, `forma/trendy.md`, `forma/wykresy.md`, `forma/statystyki.md`, `forma/norma-tetna.md`, `forma/hrv.md`, `forma/sen.md`, `forma/body-battery.md`, `forma/waga.md`; poprawiono `_lista_hasel.md`, `zaleznosci.md`, `slowniczek.md`, `_DO_SPRAWDZENIA.md`.
- Sprawdzono wskazane dokumenty, backend Formy i jej statyczne HTML/JS, algorytmy gotowości/statusu/zmęczenia faktycznego oraz krótkie odczyty bazy z 09–18.10.2026. Potwierdzono rozjazd aktualnego UI z `docs/FORMA_UI_LAYOUT.md`.
- Nie sprawdzono pełnego widoku po zalogowaniu, wszystkich interakcji wykresów ani bieżącego ekranu Body Battery poza Formą. Progi statusu HRV oparto na wskazanych dokumentach, nie na pełnej inspekcji modułu. Nie pobrano przykładowych sum statystyk jazd.
- Nie zdążono: osobne hasło o przygotowaniu do wydarzenia/sezonie i szczegółowe hasło o analizie AI trendów; zostały ujęte w hasłach Trendy / zależnościach, bez odrębnego opisu.
- Pytania do Michała: brak.

## Szkielet wiki -- 18.10.2026 09:58

- Powstały: `README.md`, `_szablon.md`, `_DO_SPRAWDZENIA.md`, `_RAPORT.md` oraz puste `index.md` w działach: `modelq`, `forma`, `raport-jazdy`, `trener`, `trasy`, `pogoda`, `zdrowie`, `garaz`, `qext2`, `albert`, `polaczenia`, `system`.
- Nie sprawdzano jeszcze treści haseł, obliczeń ani przykładów z bazy; ten etap obejmował wyłącznie szkielet.
- Pytania do Michała: brak.

## Mapa serwisu -- 18.10.2026 10:01

- Powstały: `mapa-serwisu.md`, `img/mapa-serwisu.svg`, `_lista_hasel.md`; uzupełniono `_DO_SPRAWDZENIA.md`.
- Sprawdzono `nav.js`, strony HTML, crontab roota, timery systemd oraz wskazane fragmenty kodu integracji. Nie potwierdzono zakładek renderowanych dynamicznie ani aktywnego harmonogramu importów Strava i intervals.icu; opisano to jako otwarte kwestie.
- Pytania do Michała: brak na tym etapie.

## Mapa wpływów i zależności -- 18.10.2026 10:25

- Powstały: `zaleznosci.md`, `img/zaleznosci.svg`, `slowniczek.md`; uzupełniono `_DO_SPRAWDZENIA.md`.
- Sprawdzono połączenia w ModelQ, gotowości, Trenerze, raporcie jazdy, mapowaniu roweru i doradcy ubioru. Rozdzielono różne warianty TSB/XSS/W′bal na podstawie kodu.
- Nie potwierdzono zgodności źródeł W′bal dla wszystkich jazd ani pełnej zależności raportu od publikacji Strava.
- Pytania do Michała: brak; kwestie empirycznej zgodności zapisano w `_DO_SPRAWDZENIA.md`.

## ModelQ -- 18.10.2026 10:04

- Powstały/uzupełniono: `modelq/index.md`, `tp.md`, `hie.md`, `pp.md`, `ltp.md`, `cp-wprime.md`, `wprime-bal.md`, `xss.md`, `kotwice.md`, `import-fit.md`, `xert.md`; poprawiono `_lista_hasel.md`, `slowniczek.md`, `zaleznosci.md` i `_DO_SPRAWDZENIA.md`.
- Sprawdzono wskazane dokumenty, kod ModelQ, ekranowe pliki statyczne oraz krótkie odczyty z tabel sygnatur, kotwic i jazd. Dokument `MODELQ.md` jest częściowo starszy; `PROGI_MODELQ.md` kończy się na stanie 08.10. Kod i odczyt bazy są podstawą aktualnych liczb.
- Nie sprawdzono interfejsu HTTP po zalogowaniu ani aktualnej delty Xert–ModelQ. Szczegóły otwarte są w `_DO_SPRAWDZENIA.md`.
- Nie zdążono: osobnego hasła o automatach pytań/strażników ModelQ, przeglądzie TP, przełomie CP, XSS z tętna oraz szczegółach kalibracji HIE z odczuć i jazd. Nie dopisano ich jako zweryfikowanych funkcji.
- Pytania do Michała: brak na tym etapie.


## Raport jazdy -- 18.10.2026 10:08

- Powstały: `raport-jazdy/index.md`, `analiza-jazdy.md`, `plik-fit.md`, `np-if.md`, `wprime-bal.md`, `przewyzszenie.md`, `nawierzchnia-jazdy.md`, `plan-wykonanie.md`, `analiza-ai.md`, `opis-strava.md`; poprawiono `_lista_hasel.md`, `zaleznosci.md`, `slowniczek.md` i `_DO_SPRAWDZENIA.md`.
- Sprawdzono kod W1/W2, FIT, skrypt przebudowy, stronę raportu, `STRAVA_PUBLISH.md` i krótkie odczyty `ride_report_data`. Użyto przykładu jazdy z 16.10.2026.
- Nie potwierdzono w bazie przykładu dopasowanego planu ani przewyższenia dla wybranej jazdy. Osiem najnowszych wierszy raportu nie miało W2; pozostaje sprawdzić automat tworzący analizę. `STRAVA_PUBLISH.md` ma rozbieżność w nazewnictwie FTP/progu względem obecnego raportu.
- Nie zdążono: osobnych haseł o pogodzie w raporcie, prędkości netto/brutto, biegach i napędzie, energii, żywieniu, podziale wysiłku na nawierzchnię/wiatr oraz uzupełnienia danych Strava i samych kryteriów oceny intensywności w opisie.
- Pytania do Michała: brak; brakujące dowody wpisano do `_DO_SPRAWDZENIA.md`.
## Hasła Trener -- 18.10.2026 10:11

- Powstały: `trener/index.md`, `trener/kalendarz.md`, `trener/plan-tygodnia.md`, `trener/gotowosc.md`, `trener/sezon.md`, `trener/dostepnosc.md`, `trener/xss.md`, `trener/sila-wioslarz.md`, `trener/bilans-waga.md`, `trener/powiadomienia.md`, `trener/trasy.md`.
- Uzupełniono `_lista_hasel.md`, `zaleznosci.md`, `slowniczek.md`, `_DO_SPRAWDZENIA.md`.
- Bieżący interfejs sprawdzono w `trener.js` i `kalendarz3.js`; opis `docs/TRENER.md` o osobnej zakładce Tydzień jest nieaktualny.
- Nie sprawdzono: źródłowego wzoru gotowości; aktualnego crona i ostatniego wyniku powiadomień. Wpisano do `_DO_SPRAWDZENIA.md`.
- Nie zdążono: osobne hasła o celach, korekcie pogodowej, adaptacji wykonania, ćwiczeniach i ściądze siłowej, edycji dnia/alertach, raportowaniu AI oraz szczegółowych regułach okien.
- Pytania do Michała: czy rozszerzyć dział o te hasła poboczne w kolejnym etapie?

## Trasy -- 18.10.2026 10:14

- Powstały: `trasy/index.md`, `analiza-trasy.md`, `profil-trasy.md`, `nawierzchnia.md`, `punkty-na-trasie.md`, `atrakcje.md`, `czas-przejazdu.md`, `naprawa-tras.md`, `store-i-wersje.md`, `potwierdzenia-telegram.md`, `planer-wyprawy.md`; poprawiono `_lista_hasel.md`, `zaleznosci.md`, `slowniczek.md` i `_DO_SPRAWDZENIA.md`.
- Sprawdzono wskazane dokumenty, kod warstw tras, stronę raportu i krótkie odczyty bazy. Przykład trasy `komoot-3331694546` z 05.10.2026: 182,6 km, 209 segmentów nawierzchni, 3654 próbki wysokości, 23 podjazdy; wywołanie czasu: 8,70 godz. ruchu i 10,87 godz. łącznie bez długich postojów.
- Rozjazdy: opis czasu v2 jest starszy od kodu/konfiguracji v3; starszy opis raportu WEB nie zawiera obecnych zakładek. Rozjazdy opisano w hasłach i `_DO_SPRAWDZENIA.md`.
- Nie zdążono: pełnych, osobnych haseł dla wszystkich trybów i kategorii punktów oraz działania każdego automatu importu tras. Nie weryfikowano widoku przez zalogowaną przeglądarkę ani bieżącej usługi Valhalla. Otwarte kwestie wpisano do `_DO_SPRAWDZENIA.md`.
- Pytania do Michała: brak.


## Hasła zdrowie — 18.10.2026 10:19

- Powstały: `zdrowie/index.md`, `dziennik.md`, `cel-kcal.md`, `bialko.md`, `okno-10-20.md`, `paliwo-rower.md`, `brokul.md`, `weekend.md`, `suplementy.md`, `serce.md`, `passa.md`, `sen.md`, `energia.md`, `masa-ciala.md`.
- Uzupełniono `_lista_hasel.md`, `zaleznosci.md`, `slowniczek.md` i `_DO_SPRAWDZENIA.md`.
- Sprawdzono `docs/CONTEXT.md`, szablon, `docs/PROJEKT_ODZYWIANIE.md`, `docs/BROKUL.md`, `docs/SUPLEMENTY.md`, `docs/SERCE.md`, `docs/DECISIONS.md`, kod `qbot_food_*`, `qbot_brokul_meals.py` i krótkie odczyty bazy. Przykład dziennika: 14.10.2026, 2604 kcal, 185,1 g białka, bilans −430 kcal.
- Rozjazd: starsze fragmenty `docs/BROKUL.md` mówią o osobnym przypomnieniu 21:30 i wysyłce planu weekendu. Kod `qbot_food_plan.morning_digest` dołącza plan do porannej wiadomości, a `weekend_text` jest odrębną starszą ścieżką. Rozjazd opisano przy `_DO_SPRAWDZENIA.md`.
- Nie zdążono: sprawdzenia widoku WWW po zalogowaniu, odczytu tabel Serce/Suplementy i przykładu z faktycznie zatwierdzonego planu weekendu.
- Pytania do Michała: brak; otwarte weryfikacje zapisano w `_DO_SPRAWDZENIA.md`.

## Garaż -- 18.10.2026 10:45

- Powstały: `garaz/index.md`, `sprzet.md`, `rowery-komponenty.md`, `kola-opony.md`, `rozpoznawanie-roweru.md`, `wybor-roweru.md`, `zakupy.md`, `doradca-ubioru.md`, `faworyci-ubioru.md`, `obserwacje-sprzetu.md`; zaktualizowano `_lista_hasel.md`, `zaleznosci.md`, `slowniczek.md` i `_DO_SPRAWDZENIA.md`.
- Sprawdzono dokumenty GARAZ, ZAKUPY, GEAR_OBS, OUTFIT_ADVISOR_RULES i OUTFIT_FAVORITES, kod API i moduły garażu, doradcy, doboru roweru i rozpoznawania czujników; odczytano dwa rekordy rowerów z SQLite w trybie tylko do odczytu.
- Rozjazd: `OUTFIT_FAVORITES.md` wymienia zadania serwisowe jako wejście AI, natomiast `gear_kit.py` stwierdza, że nie wpływają na wybór. Przyjęto aktualny kod.
- Nie sprawdzono: zalogowanego widoku, konkretnych rekordów zakupów, doboru ubioru, faworytów, obserwacji i wyboru roweru w Postgresie. Brakujące przykłady wpisano do `_DO_SPRAWDZENIA.md`.
- Nie zdążono: pełnego hasła o notatkach warsztatowych, fittingu jako osobnym algorytmie, przypomnieniach zakupów i wyszukiwaniu cen jako odrębnych podfunkcjach. Pytania do Michała: brak.

## QExt2 -- 18.10.2026 10:23

- Powstały: `qext2/index.md`, `przeplyw-jazdy.md`, `kokpit2.md`, `pole-dynamiczne.md`, `tryb-auto.md`, `pacing.md`, `pogoda-info.md`, `brama.md`, `pola-fit.md`; uzupełniono `_lista_hasel.md`, `zaleznosci.md`, `slowniczek.md` i `_DO_SPRAWDZENIA.md`.
- Sprawdzono `docs/QEXT2_CONFIG.md`, endpointy QBota, `fit_ingest.py`, kody Karoo oraz nowsze dokumenty QExt2. Przykład z bazy: jazda `24745225177` z 16.10.2026, 4 026 rekordów, W′ min 40% i końcowe 83%.
- Rozjazd: dokument ustawień QBota nie obejmuje późniejszych funkcji INFO, AERO i nowych pól FIT. Kod jest podstawą opisu. Tabela z bazy nie ma jeszcze kolumn kontroli wiatru mimo kodu zapisu.
- Nie potwierdzono: czasu synchronizacji FIT, rzeczywistej odpowiedzi gotowości odebranej przez Karoo ani bieżących ustawień AUTO/pacing i wyniku AERO z urządzenia. Wpisano do `_DO_SPRAWDZENIA.md`.
- Nie zdążono: osobnego hasła dla każdego endpointu pomocniczego QExt2 (`surface`, `poi`, plan czasu, typowe EF) ani każdego komunikatu KOKPIT z osobna. Zakres ograniczono do wymienionych funkcji widocznych dla użytkownika.
- Pytania do Michała: brak; pytania weryfikacyjne zapisano w `_DO_SPRAWDZENIA.md`.
# Hasła Albert — 18.10.2026 10:27

- Powstały: `albert/index.md`, `routing.md`, `narzedzia.md`, `pamiec.md`, `mcp.md`, `telegram.md`, `ograniczenia.md`; zaktualizowano `_lista_hasel.md`, `slowniczek.md`, `zaleznosci.md` i `_DO_SPRAWDZENIA.md`.
- Sprawdzono architekturę QBot3, `_SYSTEM`, rejestr narzędzi, runtime, adapter MCP, handler zapytań, webhook Telegrama i dokument transparentnego interfejsu.
- Rozjazdy: architektura mówi, że `tools/list` zawiera tylko `qbot_query`, natomiast adapter kodem dołącza też narzędzia podglądu bazy/Garażu. Dokument Telegrama opisuje docelową przezroczystość, ale bieżący webhook rozdziela zwykły tekst i komendy.
- Nie sprawdzono: wyniku `tools/list` na żywym serwerze, aktywnego wariantu pamięci, widoku rozmowy po stronie klienta ani rekordów pamięci w bazie. Nie pobierano przykładu liczbowego z bazy, bo hasła opisują przepływ bez liczb użytkowych.
- Nie zdążono: osobnych haseł dla każdego z kilkudziesięciu narzędzi; najważniejsze grupy zebrano w `albert/narzedzia.md`.
- Pytania do Michała: czy zwykły tekst Telegrama ma już docelowo przechodzić przez Alberta? Pozostałe kwestie wymagają sprawdzenia środowiska, nie decyzji użytkownika.

## Hasła System -- 18.10.2026 11:00

- Powstały: `system/index.md`, `status.md`, `centrum-powiadomien.md`, `dostep-demo.md`, `audyt-tygodniowy.md`, `kopie-bazy.md`, `bezpieczniki.md`, `paleta-ui.md`, `warstwa-legacy.md`; zaktualizowano `_lista_hasel.md`, `zaleznosci.md`, `slowniczek.md`, `_DO_SPRAWDZENIA.md`.
- Sprawdzono wskazane dokumenty oraz bieżący kod kontroli Statusu, audytu tygodniowego, skryptu kopii bazy, logiki demo i dzwonka. Audyt tygodniowy przenosi stare pliki; nie jest kontrolą wyłącznie do odczytu.
- Rozjazd/uwaga: `LEGACY_USAGE.md` podaje decyzję z 22.10.2026, datę przyszłą wobec etapu (18.10.2026); kod Statusu nadal ma kontrolę legacy, ale zwraca stan `off`. Opisano w haśle i `_DO_SPRAWDZENIA.md`.
- Nie sprawdzono: bieżącego wykonania kopii DB i aktywnego timera, żywego widoku WWW po zalogowaniu, ani aktywności licznika legacy. Nie uruchamiano audytu ani testów.
- Nie zdążono: osobnych haseł dla wszystkich rodzajów powiadomień oraz pełnej listy bezpieczników i zasad autoryzacji poza demo. Pytania do Michała: brak; otwarte kwestie wymagają sprawdzenia środowiska.

## P0 -- 18.10.2026 14:24

- Przejrzano 59 pozycji: 18 wyjaśniono i przeniesiono do `_DO_SPRAWDZENIA.md` → „Wyjasnione”; 41 pozostaje pytaniami. Zaktualizowano: `albert/pamiec.md`, `albert/telegram.md`, `qext2/pola-fit.md`, `qext2/przeplyw-jazdy.md`, `pogoda/pogoda-na-trasie.md`, `pogoda/ostrzezenia.md`, `modelq/xert.md`, `raport-jazdy/analiza-ai.md`, `trener/gotowosc.md`, `trener/powiadomienia.md` oraz `_DO_SPRAWDZENIA.md`.
- Odczyty bazy potwierdziły pamięć, kontrolę wiatru, przykład pogody segmentowej, brak alertów w dniu odczytu, benchmark Xerta, najnowszy W2 i ostatnie powodzenia powiadomień Trenera. Crontab potwierdził harmonogramy Hammerhead/Garmin, Withings/Garmin, ingest FIT i Trenera. Zrzut `img/ekrany/mq2.png` potwierdził widok ModelQ.
- Nie udało się sprawdzić: rzeczywistego wyniku `tools/list`, ustawień i odpowiedzi z urządzenia Karoo, działania timerów systemd (brak połączenia z bus), chronologii kopii DB i jej pliku, aktywnych integracji intervals.icu/Strava, zalogowanych widoków (dev_fetch nie odczytał WEBAUTH), dostępu Valhalla oraz pełnej zgodności źródeł W′bal i gotowości.
- `CLAUDE.md` nie znaleziono w wiki ani w `docs`; pozostałe instrukcje początkowe i wskazane pliki kontekstu przeczytano.
- Pytania do Michała (max 5):
  1. Czy może udostępnić wynik `tools/list` oraz określić docelowy routing zwykłego tekstu Telegrama?
  2. Czy może udostępnić dziennik Karoo/QExt2 z `/ride-readiness`, AUTO/pacing, AERO i czasem synchronizacji FIT?
  3. Czy może udostępnić działający dostęp do zalogowanych widoków, aktywnych timerów/usług oraz Valhalli?
  4. Czy chce rozszerzyć wiki o brakujące osobne opisy pogody oraz Hammerhead → Garmin/TACX?
  5. Czy po udostępnieniu danych mamy dokończyć przykłady dla Stravy, intervals.icu, garażu, zdrowia, gotowości i kopii bazy?

## ModelQ pogłębienie -- 18.10.2026 14:24

- Rozbudowano wszystkie 11 haseł ModelQ; dodano pięć brakujących: `bezpieczniki.md`, `odczucie-po-jezdzie.md`, `przeglad-tp.md`, `przelom-cp.md`, `xss-z-tetna.md`. Dodano wykresy `img/modelq-tp-20261016-18.svg` i `img/modelq-xss-20261016-18.svg`.
- Zaktualizowano `modelq/index.md`, `_lista_hasel.md`, `zaleznosci.md`, `slowniczek.md` i `_DO_SPRAWDZENIA.md`.
- Przykłady bazy: 18.10 TP 240,7 W, HIE 19,97 kJ, PP 988,7 W, LTP 190,8 W; jazda 157,7 XSS i minimum W′bal 58%. Benchmark Xert 230 W / 24,0 kJ / 1090 W / 170,1 W.
- Zrzut pokazuje wygładzone LTP 191,2 W i dzienne 190,8 W; osobne pola bazy potwierdzają obie wartości. Nie sprawdzono strony po zalogowaniu, kompletnej drogi importu dla wszystkich aktywności ani historii doręczeń Telegrama. Szczegóły wpisano do `_DO_SPRAWDZENIA.md`.
- Rozjazd w dokumentacji starszej: `MODELQ.md` zawiera starsze współczynniki; aktualne reguły sprawdzono w kodzie i opisano.
- Pytania do Michała: brak; otwarte kwestie wymagają odczytu technicznego, nie decyzji.

## Forma pogłębienie -- 18.10.2026 14:30

- Rozbudowano 12 haseł działu Forma: przegląd, obciążenie/świeżość, status dnia, gotowość, norma pulsu, HRV, sen, Body Battery, masa, trendy, wykresy i statystyki.
- Dodano [SVG obciążeń z 12–18.10](img/forma-obciazenie-20261012-18.svg), przykłady z odczytu bazy, zrzuty ekranu w przeglądzie, mapę elementów ekranu oraz diagramy Mermaid.
- Zaktualizowano `zaleznosci.md` i `slowniczek.md`; lista haseł już zawierała wszystkie pozycje. `CLAUDE.md` w katalogu wiki nie było; przeczytano `/opt/qbot/app/CLAUDE.md`, kontekst i szablon.
- Nie sprawdzono zalogowanego widoku, interakcji wszystkich wykresów, osobnej karty Body Battery ani sum kilometrów/czasu z API Statystyk. Szczegóły w `_DO_SPRAWDZENIA.md`.
- Pytania do Michała: brak.

## Raport jazdy pogłębienie -- 18.10.2026 14:34

- Uporządkowano przegląd działu i rozbudowano 9 haseł tematycznych oraz indeks: `raport-jazdy/index.md`, `analiza-jazdy.md`, `plik-fit.md`, `np-if.md`, `wprime-bal.md`, `przewyzszenie.md`, `nawierzchnia-jazdy.md`, `plan-wykonanie.md`, `analiza-ai.md`, `opis-strava.md`. Dodano zrzut ekranu, mapę „co widzisz → hasło”, diagram całego działu, przykłady krok po kroku i `img/raport-jazdy-moc-20261018.svg`.
- Zaktualizowano `zaleznosci.md`, `slowniczek.md` oraz `_DO_SPRAWDZENIA.md`. Odczyt bazy potwierdził dla jazdy 18.10.2026: 53,9 km, moc średnią 154 W, NP 175 W, próg 241 W, IF 0,72, pracę 1360 kJ i istnienie W2. Inny odczyt potwierdził przewyższenie oraz podział nawierzchni dla jazdy 16.10.2026.
- Nie udało się potwierdzić niezaokrąglonych wartości obliczenia IF, konkretnego dopasowania planu, stanu publikacji Strava ani kompletnej listy dynamicznych kart dla wszystkich jazd. Rozbieżność IF i pozostałe kwestie zapisano w `_DO_SPRAWDZENIA.md`.
- Ograniczenie etapu: hasła są uzupełnione, ale nie osiągają wszędzie zalecanej objętości 4–10 KB; opisy pogłębiono wokół potwierdzonych elementów i nie dopisywano niezweryfikowanych szczegółów.
- Pytania do Michała: brak; otwarte punkty wymagają odczytów danych, nie decyzji właściciela.

## Trener pogłębienie -- 18.10.2026 14:39

- Rozbudowano 16 haseł Trenera: przegląd, kalendarz, plan, gotowość, sezon, dostępność, XSS, siła/wioślarz, bilans i waga, powiadomienia, trasy oraz nowe: cele, korekta pogodowa, adaptacja wykonania, ćwiczenia/ściąga i edycja dnia. Dodano zrzut, tabelę „co widzisz → hasło”, diagram działu, przykłady z 12–18.10.2026 oraz wykresy SVG planu/wykonania i pomiarów masy.
- Zaktualizowano `_lista_hasel.md`, `zaleznosci.md`, `slowniczek.md` i `_DO_SPRAWDZENIA.md`.
- Odczyt bazy potwierdził jazdy 14.10 (60 min, 57 plan/64,5 wykonania), 16.10 (60 min, 57/69,7) i 18.10 (163 min planu, 147 min wykonania, 156/157,7 XSS). Wykres pokazuje wyłącznie plan i wykonanie tych jazd. Przykłady gotowości i pomiarów masy opisano z datami.
- Rozjazd: bieżący widok ma zakładki Kalendarz, Cele i Plan; Dostępność i ustawienia są poza głównym paskiem zakładek. Starszy opis projektu podaje odrębny widok Tydzień. Aktualny interfejs i kod mają pierwszeństwo.
- Dodatkowa rozbieżność: 18.10 zrzut pokazuje 158 planowanych XSS dla „Rembertów”, a odczyt sesji z bazy 156. Nie rozstrzygnięto jej; oznaczono w haśle i `_DO_SPRAWDZENIA.md`.
- Nie sprawdzono: aktywnego celu i indywidualnych reguł dostępności w bazie, pełnego widoku edytora dnia i ściągi ćwiczeń, ani doręczenia i odpowiedzi na konkretną wiadomość pogodową. Szczegóły wpisano do `_DO_SPRAWDZENIA.md`.
- Pytania do Michała: brak; pozostałe punkty wymagają dostępu do widoków lub odczytu danych.

## Trasy pogłębienie -- 18.10.2026 14:46

- Rozbudowano hasła działu: analiza, profil, nawierzchnia, punkty, atrakcje, czas, naprawa, magazyn, Telegram i Planer; odświeżono przegląd oraz dodano hasła [raport dnia](trasy/raport-dnia.md) i [kwadraty mapy](trasy/kwadraty-mapy.md). Wykorzystano zrzuty `raport-trasy.png`, `naprawa-trasy.png`, `raport-dzien.png` oraz dodano SVG próbek wysokości i czasu: `img/trasy-profil-20261005.svg`, `img/trasy-czas-20261005.svg`.
- Zaktualizowano `_lista_hasel.md`, `zaleznosci.md`, `slowniczek.md` i `_DO_SPRAWDZENIA.md`.
- Odczyt bazy potwierdził `komoot-2251353307` z 17.10.2026: 53,7 km i trzy wpisy wersji. Dla `komoot-3331694546` z 05.10.2026 potwierdzono 182,6 km, 209 segmentów nawierzchni, 3654 próbki wysokości i 23 podjazdy. SVG przedstawia wybrane próbki co około 18,3 km.
- Nie udało się sprawdzić stron po zalogowaniu, poprawnego raportu dnia, bieżącej publikacji atrakcji dla `komoot-3120318768` ani dostępności Valhalli. Zrzut strony dnia pokazuje brak wymaganych parametrów. Pozostają również niezweryfikowane kompletne listy kategorii punktów i wszystkie interakcje mapy; wpisano je do `_DO_SPRAWDZENIA.md`.
- Pytania do Michała: brak; otwarte pozycje wymagają dostępu lub aktualnego odczytu.

## Zdrowie pogłębienie -- 18.10.2026 15:00

- Rozbudowano przegląd działu i 14 haseł: dziennik, cel kcal, białko, okno, paliwo, Brokuł, weekend, suplementy, Serce, Passa, sen, energia, masa i dodano `zdrowie/obwody.md`. Dodano diagram działu, mapę elementów ekranu, zrzut główny oraz wykres SVG energii z 14–17.10.2026.
- Zaktualizowano `_lista_hasel.md`, `zaleznosci.md`, `slowniczek.md` i `_DO_SPRAWDZENIA.md`.
- Przykłady z bazy: 14.10.2026 — 2604 kcal, 185,1 g białka, wydatek 3034 kcal; 18.10 — 1873 kcal i 136,7 g białka w późniejszym odczycie; obwody z 13.10 — talia 109 cm, biodra 112,5 cm; sen 16–18.10 — oceny 72, 89, 72.
- Rozjazd do wyjaśnienia: cel białka to 150 g w module planu i 160 g w widoku/API. Zrzut 18.10 ma wcześniejsze liczby niż późniejszy odczyt bazy; zaznaczono to w indeksie.
- Nie sprawdzono zalogowanego WWW, rekordu zatwierdzonego planu weekendu, pełnej serii pomiarów serca ani instrukcji pomiaru obwodów. Wpisano do `_DO_SPRAWDZENIA.md`.
- Pytania do Michała: brak; otwarte pozycje wymagają dalszej weryfikacji technicznej.

## Garaż pogłębienie -- 18.10.2026 15:02

- Zaktualizowano `garaz/index.md`, `garaz/sprzet.md`, `garaz/zakupy.md`; dodano `garaz/fitting.md`, `garaz/notatki-warsztatowe.md`, `garaz/przypomnienia-zakupowe.md`.
- Uzupełniono `_lista_hasel.md`, `zaleznosci.md`, `slowniczek.md` i `_DO_SPRAWDZENIA.md`. Indeks opisuje zrzut ekranu, licznik 68 komponentów, karty rowerów i widoczne kolumny.
- Sprawdzono kontekst, instrukcje, szablon, listę haseł, mapę serwisu, słowniczek, zależności, dokumenty Garażu i zakupów oraz aktualne skrypty interfejsu i fittingu.
- Nie udało się zweryfikować bieżących wpisów bazy, strony po zalogowaniu ani rzeczywistych przykładów fittingu, zakupów, faworytów, obserwacji i dopasowania roweru. Nie wszystkie istniejące hasła Garażu zostały rozbudowane do wymaganej głębokości; ich zakres i brakujące dowody zapisano w `_DO_SPRAWDZENIA.md`.
- Pytania do Michała: brak; pozostałe punkty wymagają technicznego odczytu danych lub widoku.

## Albert pogłębienie -- 18.10.2026 15:13

- Rozbudowano: `albert/index.md`, `routing.md`, `narzedzia.md`, `pamiec.md`, `mcp.md`, `telegram.md`, `ograniczenia.md`; zaktualizowano `slowniczek.md`, `zaleznosci.md`, `_DO_SPRAWDZENIA.md`.
- Zweryfikowano kod Alberta, adaptera MCP, routingu, pamięci i Telegrama; odczyt bazy potwierdził 14 rekordów `confirmed_fact` oraz 1 `conversation_summary` w tabeli pamięci na 18.10.2026.
- Rozjazd: dokument architektury opisuje publiczną listę MCP jako samo `qbot_query`, kod adaptera dodaje narzędzia tylko do odczytu bazy/Garażu. Nie pobrano wyniku działającego serwera. Strona główna ze zrzutu nie zawiera rozmowy Alberta.
- Nie udało się sprawdzić: aktywnego wyniku `tools/list`, rzeczywistego widoku rozmowy, udziału routera/Alberta. Pytanie do Michała: czy zwykły tekst Telegrama ma docelowo przechodzić tą samą drogą co MCP?
- Nie zdążono: osobne hasło dla każdego z kilkudziesięciu narzędzi. Zostały opisane główne grupy; lista szczegółowa wymaga odrębnego zakresu.

## Połączenia pogłębienie -- 18.10.2026 15:15

- Zaktualizowano `polaczenia/index.md` o oba dostarczone zrzuty, opis widocznych liczników, diagram danych i mapę ekranu na hasła. Poprawiono `polaczenia/intervals-icu.md`; dodano hasła TACX i Wellness do `slowniczek.md` oraz mapę przepływów do `zaleznosci.md`.
- Sprawdzono kod importu wellness intervals.icu, synchronizacji progu TP/LTHR, Stravy, Hammerhead/Withings, checków Statusu oraz wskazane dokumenty decyzji. Przeczytano istniejące hasła działu, listę haseł i indeks zrzutów.
- Rozbieżność: Garmin ma opis checku co 10 minut w STATUS/kodzie kontroli, a decyzja z 08.10.2026 mówi o strażniku co 15 minut. Nie sprawdzono aktywnego crontaba/timera.
- Nie pobrano bieżących danych z bazy dla integracji, nie sprawdzono dostępu Stravy po zalogowaniu, aktualnego webhooka RWGPS ani aktywnych poświadczeń intervals.icu. Szczegóły dopisano do `_DO_SPRAWDZENIA.md`.
- Etap nie osiągnął pełnej przebudowy wszystkich haseł 4–10 KB ani przykładów z bazy dla każdego algorytmu. Większość pozostałych haseł zachowała wcześniejszą, krótką treść; dalsza praca jest potrzebna. Pytania do Michała: brak — otwarte pozycje wymagają dalszego odczytu.

## System pogłębienie -- 18.10.2026 15:21

- Rozbudowano 8 istniejących haseł systemu i dodano: `strony-www.md`, `automaty.md`, `dane-i-prywatnosc.md` oraz `kontakty.md`. Zaktualizowano `system/index.md`, `_lista_hasel.md`, `zaleznosci.md`, `slowniczek.md` i `_DO_SPRAWDZENIA.md`.
- Indeks zawiera diagram działu, zrzuty strony startowej/Statusu/SETUP oraz tabelę elementów widocznych na zrzutach → hasła. Każde hasło ma diagram Mermaid, powiązania i źródła.
- Sprawdzono kod kontroli Statusu, powiadomień, demo, audytu, kopii bazy, licznika legacy i tokenów UI2. Odczyt bazy 18.10.2026 15:17: 3 nieprzeczytane i 30 nieukrytych wpisów utworzonych w ostatnich 14 dniach (bez filtra stanu zamknięcia ani ustawień kategorii). Odczyt Statusu z 15:17: audyt 993 testy OK, 12 kandydatów; części stanów usług i Garmin nie dało się uzyskać. `dev_fetch.py` nie uzyskał konfiguracji WEBAUTH.
- Rozbieżność: `status.png` z 14:23 pokazuje wszystkie sprawdzane wiersze jako działające; późniejszy odczyt kodu zwrócił stan zbiorczy `bad` z powodu niedostępnych kontroli. Opisano różnicę bez utożsamiania jej z awarią usługi.
- Nie udało się potwierdzić aktywności timerów, obecności świeżej kopii, zawartości nieprzeczytanych wpisów, zalogowanego widoku SETUP ani kompletnej retencji danych. Szczegóły są w `_DO_SPRAWDZENIA.md`.
- Pytania do Michała: brak; otwarte kwestie wymagają dostępu do widoku lub odczytu technicznego. Data decyzji legacy 22.10.2026 jest przyszła względem etapu i wymaga wyjaśnienia.

## Metaznaczniki M0 -- 18.10.2026 15:51

- Dodano blok metaznaczników do `_szablon.md`, `README.md`, `mapa-serwisu.md`, `zaleznosci.md` i `slowniczek.md`; wyjaśnienie pól dodano do szablonu, a w słowniczku wydzielono dział „Ogólne”.
- Sprawdzono wszystkie odnośniki Markdown do `img/ekrany/` w wiki: brak uszkodzonych odnośników. Zrzuty zostały tylko odczytane.
- Nie udało się sprawdzić: nic w zakresie tego etapu.
- Pytania do Michała: brak.
## ModelQ — metaznaczniki — 18.10.2026 15:52

- Uzupełniono blok metaznaczników na górze wszystkich 16 plików `modelq/*.md`; treści haseł nie zmieniono.
- Zależności porównano z sekcjami haseł oraz mapą w `zaleznosci.md`.

## Forma -- 18.10.2026 15:54

- Dodano metaznaczniki do wszystkich 12 plików `forma/*.md`; treści haseł pozostały bez zmian.
- Powiązania porównano z sekcjami haseł oraz szczegółową mapą w `zaleznosci.md`. Sprawdzono listy i zgodność ścieżek.
- Nie udało się sprawdzić: tablica worklock jest niedostępna do zapisu w środowisku. Nie zmieniano `_DO_SPRAWDZENIA.md`, bo nie pojawiły się nowe niepotwierdzone informacje.
- Pytania do Michała: brak.

## Metaznaczniki Raport jazdy -- 18.10.2026 15:55

- Uzupełniono bloki metaznaczników w 10 plikach `raport-jazdy/*.md`; treści haseł nie zmieniano.
- Wartości i źródła oparto na opisach haseł oraz ich sekcjach „Zrodla”.
- Nie udało się potwierdzić osobno, że każda podana zależność jest kompletna w `zaleznosci.md`; nie zmieniano treści tej mapy.
- Pytania do Michała: brak.

## Metaznaczniki Trenera -- 18.10.2026 15:55

- Uzupełniono bloki metaznaczników w 16 plikach `trener/*.md`.
- Sprawdzono kontekst, szablon, mapę zależności oraz moduły Trenera w kodzie.
- Nie odczytywano bazy; zachowano bez zmian treść haseł.
- `CLAUDE.md` nie znaleziono w katalogu roboczym ani wskazanej ścieżce; nie wpłynęło to na zakres.
- Pytania do Michała: brak.

## Metaznaczniki Trasy -- 18.10.2026 15:56

- Uzupełniono bloki metaznaczników we wszystkich 13 plikach `trasy/*.md`; treści haseł pozostały bez zmian.
- Porównano zależności z sekcjami haseł i mapą `zaleznosci.md`; przejrzano źródła funkcji i tabel wskazane w hasłach.
- Nie udało się potwierdzić nowych elementów; nie dopisywano pozycji do `_DO_SPRAWDZENIA.md`.
- Pytania do Michała: brak.

## Metaznaczniki Pogoda -- 18.10.2026 15:58

- Uzupełniono bloki metaznaczników we wszystkich 14 plikach `pogoda/*.md`; treści haseł nie zmieniano.
- Pola opisowe i źródła porównano z treścią haseł, kodem wskazanym w źródłach oraz sekcjami zależności i mapą `zaleznosci.md`.
- Nie korzystano z bazy danych; dla tego etapu nie były potrzebne nowe przykłady liczbowe.
- `CLAUDE.md` nie ma w katalogu wiki. Nie udało się zweryfikować treści tej instrukcji.
- Pytania do Michała: brak.

## Metaznaczniki Zdrowie -- 18.10.2026 15:59

- Dodano lub ujednolicono bloki metaznaczników we wszystkich 15 plikach `zdrowie/*.md`; treści haseł nie zmieniano.
- Sprawdzono zgodność układu pól, format list i istnienie wskazanych plików źródłowych oraz linkowanych haseł.
- Kod potwierdza rozbieżność celu białka: 150 g w starszym komunikacie planu oraz 160 g w normie i API. Istniejący wpis pozostaje w `_DO_SPRAWDZENIA.md`.
- Nie sprawdzano bazy ani widoku strony; nie dodano nowych niepotwierdzonych twierdzeń wymagających wpisu do `_DO_SPRAWDZENIA.md`.
- Pytania do Michała: czy rozbieżność 150/160 g jest zamierzona?

## Metaznaczniki Garaż -- 18.10.2026 16:00

- Uzupełniono metadane w 13 plikach `garaz/*.md`; treść haseł pozostała bez zmian.
- Porównano zależności z treścią haseł i tabelą Garażu w `zaleznosci.md`; pola „zależy od” i „wpływa na” ustawiono zgodnie z kierunkiem przepływu.
- Nie udało się znaleźć `CLAUDE.md` w katalogu wiki ani jego bezpośrednich katalogach nadrzędnych.
- Nie weryfikowano nowych faktów w bazie; do sprawdzenia wpisy pozostały oznaczone w hasłach.
- Pytania do Michała: brak.

## Metaznaczniki QExt2 -- 18.10.2026 16:02

- Uzupełniono bloki metadanych we wszystkich 11 plikach `qext2/*.md`; treści haseł pozostały bez zmian.
- Pola i powiązania porównano z sekcjami haseł oraz mapą `zaleznosci.md`; źródła sprawdzono względem wpisów w hasłach i kodu QBot/QExt2.
- Nierozstrzygnięte kwestie urządzenia, odpowiedzi na żywo i danych przykładowych są już zapisane w sekcji QExt2 pliku `_DO_SPRAWDZENIA.md`; nie dodano nowych.
- Pytania do Michała: brak nowych pytań.

## Metaznaczniki Albert -- 18.10.2026 16:02

- Dodano bloki metaznaczników do 7 plików `albert/*.md`; poza nimi zmieniono tylko ten raport.
- Zależności zestawiono z sekcją Alberta w `zaleznosci.md`, a źródła kodu z nazwami funkcji w dokumentacji.
- Nie sprawdzano nowych danych z bazy ani odpowiedzi MCP/Telegrama na żywo; nierozstrzygnięte rozbieżności pozostają opisane w hasłach.
- Pytania do Michała: brak.

## Metaznaczniki Połączenia -- 18.10.2026 16:03

- Uzupełniono metadane we wszystkich 11 plikach `polaczenia/*.md`; treść haseł pozostała bez zmian.
- Pola zestawiono z nagłówkami, sekcjami wpływów i zależności oraz wskazanymi źródłami kodu. Interwały w opisach harmonogramu pozostają oczekiwaniami checków, nie potwierdzeniem aktywnych timerów.
- Nie odczytywano bazy ani aktywnej konfiguracji harmonogramów. Otwarte kwestie są już wymienione w sekcji „Połączenia” pliku `_DO_SPRAWDZENIA.md`.
- Pytania do Michała: brak nowych.

## Metaznaczniki System -- 18.10.2026 16:04

- Uzupełniono bloki metadanych w 13 plikach `system/*.md`; poza nimi zmieniono `_DO_SPRAWDZENIA.md` i ten raport.
- Pola zależności porównano z sekcjami haseł i mapą `zaleznosci.md`; źródła kodu odczytano w wymienionych modułach i dokumentach.
- Nie udało się potwierdzić użycia grup adresów z zakładki Kontakty; dopisano tę kwestię do `_DO_SPRAWDZENIA.md`.
- Pytania do Michała: które funkcje korzystają z grup adresów Kontakty i gdzie są one przechowywane?

## ModelQ — pogłębienie — 18.10.2026 20:21

- Sprawdzono reguły dryfu TP/HIE/PP, import próbek, obsługę przełomu, pytania o odczucie i bezpieczniki. Odczyty bazy ograniczono do 16–18.10.2026 oraz krótkich list decyzji.
- Uzupełniono: `modelq/tp.md`, `modelq/hie.md`, `modelq/przelom-cp.md`, `_DO_SPRAWDZENIA.md`.
- Otwartych pozycji ModelQ wymagających decyzji Michała: brak. Ograniczenia weryfikacji: brak historii propozycji/odczuć, brak potwierdzenia doręczeń Telegram oraz brak zalogowanego widoku na żywo.
- Nie stwierdzono rozbieżności danych wymagającej wpisu jako możliwy błąd serwisu.
- Pytania do Michała: brak.

## Forma -- 18.10.2026 20:29

- Pogłębiono: `forma/index.md`, `forma/body-battery.md`, `forma/ctl-atl-tsb.md`, `forma/gotowosc.md`, `forma/hrv.md`, `forma/norma-tetna.md`, `forma/sen.md`, `forma/status-dnia.md`, `forma/statystyki.md`, `forma/trendy.md`, `forma/waga.md`, `forma/wykresy.md`, `img/gotowosc-20261012-18.svg`, `_DO_SPRAWDZENIA.md`.
- Odczyt bazy za 12.10.2026–18.10.2026 potwierdził przykłady obciążenia, świeżości, gotowości, HRV, pulsu, snu, masy i Body Battery. Poprawiono błędny przykład punktacji snu 18.10.2026 z 67 na 72.
- Nie udało się sprawdzić interakcji w zalogowanym widoku ani wyświetlania Body Battery poza stroną Forma: `dev_fetch.py` nie znalazł danych logowania WEBAUTH. Ograniczenie wpisano do haseł i `_DO_SPRAWDZENIA.md`.
- Rozbieżności liczb wymagające zgłoszenia jako błąd serwisu: brak. Pytania do Michała: brak.
## Raport jazdy — pogłębienie — 18.10.2026 20:34

- Pogłębiono `raport-jazdy/index.md`, `analiza-jazdy.md`, `analiza-ai.md`, `np-if.md`, `wprime-bal.md`, `przewyzszenie.md`, `nawierzchnia-jazdy.md`, `plan-wykonanie.md`, `plik-fit.md`, `opis-strava.md`; uzupełniono `_DO_SPRAWDZENIA.md` i dodano `img/raport-jazdy-moc-20261018.svg`.
- Odczytano jazdę 18.10.2026: plan 50,4 km/222 m, wykonanie 53,9 km/216 m. Z 8820 próbek odtworzono NP 174,505 W i IF 0,72499 przy TP 240,700 W. Stan publikacji Strava: `ok`.
- Strona raportu zwróciła treść w zalogowanym żądaniu GET. `dev_fetch.py` nie znalazł WEBAUTH; test interakcji kliknięć nie był celem i nie został wykonany.
- Nie potwierdzono zachowania każdej interakcji w przeglądarce. Karty zależą od danych jazdy. Brak nierozstrzygniętych pytań do Michała.
- Możliwe błędy serwisu: brak; różnica IF wynika z zaokrąglenia NP i TP w widoku.
- Pytania do Michała: brak.

## Zdrowie — pogłębienie — 18.10.2026 21:00

- Zmieniono `zdrowie/bialko.md`, `brokul.md`, `cel-kcal.md`, `dziennik.md`, `energia.md`, `index.md`, `masa-ciala.md`, `obwody.md`, `okno-10-20.md`, `paliwo-rower.md`, `passa.md`, `sen.md`, `serce.md`, `suplementy.md`, `weekend.md`, `_DO_SPRAWDZENIA.md`; dodano `img/zdrowie-deficyt-20261012-18.svg` i `img/zdrowie-paliwo-20261018.svg`.
- Zalogowany GET strony Zdrowie oraz krótkie, tylko do odczytu zapytania/API potwierdziły dziennik, plan weekendu, regularność suplementów, serię ciśnienia i EKG, obwody oraz pomiary ciała.
- Rozbieżność zrzutu i późniejszego podsumowania 18.10 wyjaśniają trzy późniejsze wpisy o łącznej wartości 961 kcal. Zmiana prognozy wydatku o 49 kcal przesunęła cel po zaokrągleniu z 3350 na 3400 kcal. Możliwe błędy serwisu: nie stwierdzono.
- Nie udało się potwierdzić odbioru porannej wiadomości weekendowej na telefonie ani znaleźć w kodzie instrukcji dokładnego ułożenia taśmy do pomiaru. Ograniczenia pozostają w `_DO_SPRAWDZENIA.md` i hasłach.
- Odczyt z 18.10 pokazał dwa czasy treningu: 163 min w Kalendarzu i 8815 s (146,9167 min) w rejestrze jazdy. Okno używa czasu aktywności, a paliwo czasu Kalendarza; nie stwierdzono błędu bez potwierdzenia, który czas ma być zamierzony.
- Pytania do Michała: (1) 150 g w piątkowej wiadomości weekendowej: TAK — pozostawić osobno, NIE — ujednolicić z 160 g; (2) czas paliwa z Kalendarza: TAK — zachować, NIE — oprzeć o zapis jazdy. Szczegóły w `_DO_SPRAWDZENIA.md`.

## Trener -- 18.10.2026 20:37

- Zweryfikowano odczytem tylko do odczytu aktywne cele, indywidualne reguły dostępności i sesje 12.10–18.10.2026.
- Poprawiono `trener/cele.md`, `trener/dostepnosc.md`, `trener/trasy.md`, `trener/cwiczenia-sciaga.md`, `trener/korekta-pogodowa.md`, `trener/powiadomienia.md` oraz przeniesiono rozstrzygnięte punkty Trenera w `_DO_SPRAWDZENIA.md` do „Wyjaśnione”.
- Rozstrzygnięcie liczb: zrzut 18.10 pokazuje 158 jako wykonane XSS (157,699996948242 zaokrąglone), a plan wynosi 156; nie stwierdzono błędu serwisu.
- Ten odczyt wyjaśnia nierozstrzygniętą w raporcie Trenera z 14:39 różnicę 158/156; wcześniejszy wpis zachowuje stan wiedzy z tamtej godziny.
- Szczegółowe panele i doręczenie Telegrama nie zostały zweryfikowane interaktywnie; są opisane jako ograniczenie, nie pytanie do Michała. Bilans dzienny i 14-dniowy nie zostały porównane na tych samych danych.
- Najnowszy odczyt dziennika powiadomień z 18.10 o 20:00 wskazuje plan tygodnia `ok` i przegląd scalony z planem; bieżąca pamięć podręczna nie zawiera propozycji pogody. Nie dowodzi to doręczenia na urządzeniu ani wcześniejszej decyzji użytkownika.
- Pytania do Michała: brak.

## Trasy — pogłębienie raportu dnia — 18.10.2026 20:40

- Rozbudowano `trasy/raport-dnia.md` na podstawie kodu Planera, strony i renderera oraz odczytu GET `/api/planer/dzien` dla trasy Rembertów z 17.10.2026. Przykład zawiera 53,659 km (na ekranie 53,7 km), 259 m podejść, nawierzchnię i profil.
- W `_DO_SPRAWDZENIA.md` przeniesiono rozstrzygnięcia z listy tras; bieżący odczyt atrakcji zwrócił 9 kandydatów, w tym 3 rekomendowane. Źródła tych wpisów, Valhalla i objazd S8 pozostają ograniczeniami, nie pytaniami decyzyjnymi.
- Kod potwierdził rozjazd opisu czasu: dokument raportu wspomina v2, a aktywny moduł próbuje wczytać v3 z konfiguracji i zachowuje v2 jako zapas.
- Nie udało się potwierdzić: aktualnej dostępności Valhalli ani ponownego wyniku objazdu S8; bieżącego podziału źródeł publikacji atrakcji.
- Możliwe błędy serwisu: brak stwierdzonych rozbieżności odpowiedzi i zapisanych danych.
- Pytania do Michała: brak.
## Pogoda — pogłębienie -- 18.10.2026 20:49

- Zmieniono: `pogoda/charakter-dnia.md`, `pogoda/index.md`, `pogoda/mapa-modeli.md`, `pogoda/ostrzezenia.md`, `pogoda/pogoda-na-trasie.md`, `pogoda/prognoza.md`, `pogoda/qext2.md`, `pogoda/radar.md`, `pogoda/sprawdzalnosc.md`, `pogoda/ubior.md`, `pogoda/warunki-punktowe.md`, `pogoda/weekend.md`, `pogoda/wiatr.md`, `_DO_SPRAWDZENIA.md`, `img/radar-sprawdzalnosc.svg`.
- Zweryfikowano kod reguł mapy, weekendu, charakteru dnia, alertów, Okna jazdy, ubioru i API QExt2; odczyt bazy potwierdził próbkę radaru z 20:30, brak zapisanych alertów, 33 cache prognozy bez `per_segment` oraz podsumowanie wiatru jazdy 24766557671. Zalogowany GET `/pogoda-wyprawy.html` zwrócił stronę.
- Skorygowano opis zrzutu głównej Pogody do widocznych wartości: 10,1°C, odczuwalne 8,7°C, wiatr 2,6 m/s i porywy 6,5 m/s.
- Nie udało się sprawdzić: archiwalnych wartości CAPE/LI w bazie, przykładowych wyników Okna jazdy, weekendu i doradcy ubioru, segmentowej odpowiedzi API dla konkretnej trasy ani renderowania pól na urządzeniu QExt2. Nie potwierdzono także wcześniejszego zestawu wartości punktowych z 04.10.2026; te przykłady usunięto. Ograniczenia opisano w hasłach.
- Możliwe błędy serwisu: nie stwierdzono. Wcześniejsze wartości w opisie zrzutu były niezgodne z samym obrazem; poprawiono dokumentację.
- Pytania do Michała: brak decyzji wymagających rozstrzygnięcia.


## Garaż — pogłębienie -- 18.10.2026 21:11

- Pogłębiono hasła: `garaz/index.md`, `sprzet.md`, `rowery-komponenty.md`, `kola-opony.md`, `rozpoznawanie-roweru.md`, `wybor-roweru.md`, `fitting.md`, `doradca-ubioru.md`, `faworyci-ubioru.md`, `obserwacje-sprzetu.md`, `zakupy.md`, `przypomnienia-zakupowe.md`, `notatki-warsztatowe.md`.
- Dodano wykresy: `img/garaz-nawierzchnia-20261018.svg`, `img/garaz-ubior-20261018.svg`, `img/garaz-fitting-2025.svg`, `img/garaz-rozpoznanie-20261004.svg`, `img/garaz-obserwacje-20261018.svg`, `img/garaz-zapas-20261018.svg`; zaktualizowano `_DO_SPRAWDZENIA.md`.
- Odczyty z 18.10.2026 potwierdziły 4 rowery, 72 wpisy części (68 aktywnych), 16 opon, przykłady zakupów i ustawień fittingu oraz wpisy doboru roweru, ubioru, faworytów i obserwacji.
- Licznik 68 odpowiada aktywnym częściom; 4 z 72 wpisów są nieaktywne. Nie stwierdzono błędu serwisu. Dwie aktywne pozycje zakupowe nie mają konfiguracji zapasu.
- Nie sprawdzono kliknięć wszystkich zakładek i przycisków ani osobnego widoku fittingu; opisano to jako ograniczenie. Odczyt statusu `worklock` nie powiódł się, bo `/opt/qbot/app/.worklock.json` jest poza zapisywalnym obszarem i tylko do odczytu.
- Pytania do Michała: brak.

## QExt2 -- pogłębienie -- 18.10.2026 21:22

- Pogłębiono 11 haseł `qext2/*.md`; skorygowano informacje o odbiorze AERO, odpowiedzi gotowości, filtrze prędkości typowego EF i ograniczeniach potwierdzenia z Karoo. Uzupełniono `slowniczek.md`, `zaleznosci.md` i `_DO_SPRAWDZENIA.md`.
- Dodano wykresy oparte na danych z 18.10.2026: `img/qext2-aero-20261018.svg`, `img/qext2-ef-20261018.svg`, `img/qext2-wbal-porownanie-202610.svg`.
- Odczyt odpowiedzi gotowości z tokenem urządzenia zwrócił TP 240,7 W, W′ 20,0 kJ i współczynnik dnia 0,889. Baza potwierdziła 8 819 próbek AERO, dane Rembertowa z 17.10 oraz 22 jazdy do typowego EF. Harmonogram zadań potwierdził odstępy 10 i 30 minut, ale nie opóźnienie konkretnej aktywności.
- Ograniczenia: brak potwierdzenia odbioru przez aktywne Karoo, brak zrzutów jego ekranów i brak dokładnego czasu dostarczenia FIT; dziennik bramy nie rozpoznaje klienta, bo zapisuje `127.0.0.1`.
- Możliwe błędy serwisu: minima W′bal QExt2 i ModelQ różnią się w badanych jazdach (m.in. 11.10: 0% i 6,3%); nie potwierdzono, że to błąd, bo silniki liczą wynik niezależnie. Dziennik bramy zawiera jedną odpowiedź zewnętrznej usługi 405, po której QBot zapisał 503; kolejne wpisy miały stan „ok”.
- Pytania do Michała: brak.

## Albert -- pogłębienie -- 18.10.2026 21:26

- Rozbudowano siedem haseł `albert/*.md`: przegląd, routing, narzędzia, pamięć, MCP, Telegram i ograniczenia. Każde ma diagram, odnośnik do zrzutu głównej strony, sekcje powiązań oraz źródła.
- Odczyt bazy 18.10.2026 potwierdził 14 faktów i 1 podsumowanie rozmowy. Kod potwierdza, że adapter MCP składa sześć pozycji, a zwykły tekst Telegrama korzysta z innej drogi routera. Aktualizowano `_DO_SPRAWDZENIA.md`.
- Nie pobrano odpowiedzi działającego MCP na listę narzędzi: instrukcja ograniczała żądania do GET, a lista wymaga POST. Nie ma zrzutu rozmowy Alberta ani zestawienia produkcyjnego udziału routera i Alberta; opisano je jako ograniczenia.
- Pytanie do Michała: czy zwykły tekst Telegrama ma docelowo korzystać z tej samej ścieżki QBot/Alberta co MCP? (Tak/Nie)


## Połączenia -- pogłębienie -- 18.10.2026 21:29

- Pogłębiono pliki: `polaczenia/garmin.md`, `hammerhead-garmin.md`, `withings.md`, `komoot.md`, `rwgps.md`, `strava.md`, `intervals-icu.md`, `xert.md`, `harmonogram-importow.md`, `index.md`. Każde opisuje przepływ diagramem Mermaid; istniejące zrzuty Status i Strava objaśniono przy właściwych liczbach.
- Odczyt bazy potwierdził przykłady z 18.10 dla Garmina, Stravy i Xerta; artefakt Komoot/RWGPS pochodzi z 17.10. Zalogowany GET potwierdził elementy widoku Strava i SETUP.
- Aktywny crontab potwierdził Hammerhead co 10 min, Garmin co 15 min, Withings co 15 min i Xert o 00:15. Kod checku Garmina nadal oczekuje 10 min. Wpisy importu Garmin v2 są zakomentowane.
- Nie udało się potwierdzić aktywnego timera Komoot, importu wellness intervals.icu, poświadczeń intervals.icu, bieżącej konfiguracji webhooka RWGPS ani autoryzacji Stravy po stronie dostawcy. Ograniczenia opisano w hasłach; nie są pytaniami do Michała.
- Możliwe błędy serwisu: harmonogram strażnika Garmina co 15 min rozmija się z interwałem 10 min wskazanym przez check statusu.
- Pytanie do Michała: czy osobne hasło Hammerhead→Garmin (TACX) pozostawić w WIKI? TAK = utrzymać osobne; NIE = połączyć treść z Garminem.

## Strażnicy -- 18.10.2026 21:44

- Utworzono `straznicy/index.md`, `obciazenie.md`, `cialo.md`, `modelq.md`, `garmin.md`, `zywienie.md`, `import.md`, `destrukcja.md`, `pozostale.md` oraz `img/straznik-obciazenia-20261018.svg`.
- Zaktualizowano `README.md`, `mapa-serwisu.md`, `zaleznosci.md`, `slowniczek.md`, `modelq/bezpieczniki.md`, `system/bezpieczniki.md`, `garaz/sprzet.md`, `_DO_SPRAWDZENIA.md` i ten raport.
- Sprawdzono kod, definicje timerów, cron oraz krótkie odczyty bazy. Odczytano progi load guard, real load guard, ModelQ, Garmin i żywienia; stary power meter guard jest wycofany.
- Nie udało się potwierdzić aktywności timera żywienia ani odbioru poszczególnych alarmów Telegram. Nie istnieje obecnie tabela `modelq_guard_log`; szczegóły w `_DO_SPRAWDZENIA.md`.
- `worklock.py status` nie zadziałał, bo próbował zapisać plik poza dozwolonym obszarem wiki; stan blokad niepotwierdzony. Nie edytowano plików poza `docs/wiki`.
- Pytania do Michała: brak.

## System -- pogłębienie -- 18.10.2026 21:37

- Zaktualizowano hasła `system/status.md`, `kopie-bazy.md`, `audyt-tygodniowy.md`, `automaty.md`, `warstwa-legacy.md`, `paleta-ui.md`, `centrum-powiadomien.md`, `kontakty.md`, `index.md`, `strony-www.md`, `dane-i-prywatnosc.md`, `bezpieczniki.md`, mapę `zaleznosci.md` oraz `_DO_SPRAWDZENIA.md`.
- Zalogowane GET-y z wieczora 18.10.2026 potwierdziły Status „ok”, cztery aktywne usługi, import Garmin o 21:15 i kontrolę o 21:23, kopię z 03:23, 19 włączonych kategorii powiadomień, trzy zapisane urządzenia, brak nowych pozycji w obiegu Web Push o 21:31 oraz 2 grupy kontaktów z 4 adresami.
- Odczyt `systemctl` i katalogu kopii był niedostępny. Inwentaryzacja z 15.10 potwierdza timer kopii tylko na tamten dzień; obecnej aktywności timerów i obecności samego pliku nie potwierdzono. `LEGACY_USAGE.md` opisuje 22.10 jako przyszły termin przeglądu względem tego etapu; licznik działał 18.10.
- Skorygowano opis palety: `setup.png` pokazuje ciemny motyw, natomiast `status.png` białe tło i ciemny panel. Zmiana opisu, nie błąd serwisu.
- Ograniczenia: treść wpisów nieprzeczytanych, faktyczne wyświetlenie powiadomienia na urządzeniu i pełna retencja wszystkich danych. Zapisano je w hasłach; nie są pytaniami do Michała. Pytania do Michała z działu System: brak.
- Możliwe błędy serwisu: nie stwierdzono. Różnica Statusu między 15:17 a 21:23 pokazuje różne wyniki w czasie; jej przyczyny nie dało się niezależnie odtworzyć z powodu niedostępności systemd.

## Audyt kompletności wiki -- 18.10.2026 21:57

- Powstały: `audyt-kompletnosci.md`, `garaz/planer-wyposazenia.md`, `garaz/kalibracja-zdjec.md`, `garaz/dodaj-zakup-ze-sklepu.md`, `trasy/zaproszenia-gosci.md`, `qext2/symulator.md`, `img/zaproszenia-progi-pogody.svg`; skrypt inwentaryzacji `_work/audit_inventory.py`.
- Znaleziono 5 braków w opisach funkcji widocznych dla właściciela. Dopisano 6 haseł: pięć opisów funkcji i hasło audytu. Uzupełniono spis haseł, linki działów i opisy automatów/stron. Audyt zawiera 19 definicji systemd, dostępne wpisy crontaba, 266 dekoratorów HTTP i 16 dodatkowych dopasowań, 36 stron, 84 narzędzia, 235 tabel i 131 dopasowań wysyłek.
- Crontab `qbot` był nieczytelny; nie potwierdzono stanu aktywności timerów, działania wszystkich ekranów na żywo ani doręczenia wiadomości pogodowej. Brakuje też zrzutu otwartej zakładki symulatora QExt2. Szczegóły są w `_DO_SPRAWDZENIA.md`.
- Kontrola linków ujawniła dwa wcześniejsze odnośniki do nieistniejących haseł w `straznicy/cialo.md` i `straznicy/zywienie.md`; nie zmieniałem ich bez potwierdzenia właściwego celu.
- `_indeks.json` nie został przebudowany, bo ograniczenie etapu pozwala zapisywać wyłącznie pliki Markdown i SVG. W indeksie z chwili audytu brakuje więc nowych haseł.
- Pytania do Michała: brak. Do pełnej zgodności wyszukiwania potrzebny będzie osobny krok aktualizacji indeksu JSON.

## Nocna aktualizacja 18.10.2026 -- 18.10.2026 23:51

- Dodano hasła [Centrum CdA](forma/centrum-cda.md) i [Krzywa mocy](forma/krzywa-mocy.md); uzupełniono Formę, analizę jazdy, wpisy Trenera, Stravę, automaty, strony WWW oraz symulator QExt2 o widoczne zmiany z 18.10. Dodano hasła do listy haseł.
- Dziennik dnia uzupełniono podsumowaniem po ludzku i linkami do poprawionych haseł.
- Nie sprawdzono: przykładów CdA/Crr i krzywej mocy z odczytu bazy, otwartych ekranów tych zakładek, niezapisanych elementów WWW oraz miejsc prezentacji glikogenu i P@HR; wpisano je do `_DO_SPRAWDZENIA.md`.
- Pytania do Michała: brak; niepotwierdzone punkty wymagają dostępu do danych i ekranów, nie decyzji właściciela.
## Decyzje Michala 19.10 -- 19.10.2026 07:40

- Zmieniono: `zdrowie/bialko.md`, `zdrowie/weekend.md`, `zdrowie/paliwo-rower.md`, `img/zdrowie-paliwo-20261018.svg`, `polaczenia/garmin.md`, `_DO_SPRAWDZENIA.md`, `polaczenia/index.md`, `system/index.md`, `audyt-kompletnosci.md`, `polaczenia/intervals-icu.md`, `polaczenia/harmonogram-importow.md`, `zaleznosci.md`, `slowniczek.md`, `_lista_hasel.md` i `_RAPORT.md`; usunięto `polaczenia/hammerhead-garmin.md`.
- Sprawdzono commit HEAD i bieżący `qbot_food_plan.py`; baza potwierdza 18.10.2026 jazdę 8 815 s (146,9 min), plan Kalendarza 163 min i wyliczenie 80 g. Ujednolicono cel białka do 160 g. Połączono opis mostka z hasłem Garmin i poprawiono odnośniki.
- W `_DO_SPRAWDZENIA.md` pozostawiono pytanie Telegram → Albert, przeniesiono materiał weryfikacyjny do ograniczeń, a trzy rozstrzygnięte decyzje zapisano w „Wyjaśnione”.
- Nie sprawdzano po zmianach renderowania stron WWW; nie uruchamiano testów ani usług. Wygenerowany `_indeks.json` nadal zawiera usunięte hasło, lecz nie można go zmienić w tym zakresie plików. Pytania do Michała: brak nowych.
