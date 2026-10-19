---
tytul: Audyt kompletności wiki
dzial: system
typ: przeglad
opis: Pokazuje, które automaty, wiadomości, ekrany i elementy zaplecza mają opis w wiki.
tagi: [audyt, wiki, kompletność, automaty, strony]
synonimy: [czego brakuje w wiki, mapa pokrycia dokumentacji, inwentarz qbot]
skroty: [API, Telegram, GPX]
gdzie_widac: [Wiki]
liczby: [19 definicji systemd, 266 ścieżek HTTP, 36 stron HTML, 84 narzędzia, 235 tabel]
zalezy_od: [system/automaty, system/strony-www, albert/narzedzia]
wplywa_na: [system/automaty, system/strony-www, albert/index, mapa-serwisu]
zrodla_kodu: [docs/wiki/_work/audit_inventory.py, docs/wiki/_indeks.json, /etc/systemd/system qbot, /var/spool/cron/crontabs, qbot_web.py, qbot_api.py]
aktualizacja: 18.10.2026
---

# Audyt kompletności wiki

## Zakres

Porównałem spis haseł wiki z timerami i usługami systemowymi, dostępnymi wpisami crontaba, harmonogramami w kodzie, wysyłkami powiadomień, stronami WWW, narzędziami Alberta i tabelami `qbot_v2`. Audyt jest migawką odczytu z 18.10.2026. Nazwy techniczne poniżej służą do odnalezienia elementu; nie oznaczają, że właściciel musi znać je na co dzień.

Skrypt inwentaryzacyjny znajduje się w `_work/audit_inventory.py`. Zbiera kandydatów z kodu i konfiguracji oraz robi krótki, wyłącznie odczytowy odczyt listy tabel. Pełny spis ścieżek stron i tabel zapisano niżej.

## Wynik porównania

Przeglądany `_indeks.json` zawierał 157 wpisów. Pięć widocznych funkcji nie miało osobnego hasła: planer wyposażenia, kalibracja zdjęć, dodawanie produktu ze sklepu, zaproszenia dla gości i symulator QExt2. Dopisałem pięć haseł. Część opisywał wcześniej ogólny spis stron, ale nie wystarczał on, by właściciel wiedział, jak użyć tych funkcji.

| Element | Hasło wiki albo BRAK | Wynik |
|---|---|---|
| Timery i usługi systemd `qbot*` | [Automaty QBota](system/automaty.md), [Kopie bazy](system/kopie-bazy.md), [Audyt tygodniowy](system/audyt-tygodniowy.md), [Strażnicy](straznicy/index.md), [Status](system/status.md) | Wszystkie 19 definicji są wymienione w tym audycie. Timer nocnej aktualizacji wiki wcześniej nie był wymieniony w haśle Automatów. |
| Dostępny crontab roota | [Automaty QBota](system/automaty.md), [Połączenia](polaczenia/harmonogram-importow.md), [Strażnicy](straznicy/index.md), hasła tematyczne | 17 aktywnych wierszy odczytano i przypisano w sekcji „Automaty”. |
| Crontab konta `qbot` | **BRAK danych** | Plik istnieje, ale system odmówił odczytu. Nie da się porównać jego harmonogramów. |
| Wiadomości Telegram i inne powiadomienia | [Albert przez Telegram](albert/telegram.md), [Strażnicy](straznicy/index.md), [Powiadomienia Trenera](trener/powiadomienia.md), [Ostrzeżenie o deszczu](pogoda/ostrzezenia.md), [Strava](polaczenia/strava.md), [Centrum powiadomień](system/centrum-powiadomien.md) i hasła tematyczne | Wyszukanie dało 131 dopasowań, w tym wywołania poczty i fałszywe dopasowania. Główne rzeczywiste ścieżki przypisano według obszaru. |
| Ścieżki HTTP w `qbot_web.py` i `qbot_api.py` | [Strony WWW](system/strony-www.md), hasła funkcji | 266 dekoratorów z metodą i ścieżką znaleziono w dwóch plikach; 218 zaczyna się od `/api/`. Są rozpisane według grup niżej. |
| Strony HTML w publicznym serwisie | [Strony WWW](system/strony-www.md), [Mapa serwisu](mapa-serwisu.md), hasła działów | 36 stron. Pięć funkcji wskazanych wyżej dostało osobne hasła. Makiety i podglądy są opisane z zaznaczeniem, że pokazują dane przykładowe. |
| Zakładki stron | [Strony WWW](system/strony-www.md), [Trening](trener/index.md), [Forma](forma/index.md), [Garaż](garaz/index.md), [SETUP](system/strony-www.md) | Potwierdzono osobne zakładki Formy, w tym „Krzywa mocy”, główne zakładki Garażu i SETUP oraz dynamiczne panele Treningu. Nie pobrano zrzutu każdej zakładki. |
| Narzędzia Alberta | [Narzędzia Alberta](albert/narzedzia.md), [Routing](albert/routing.md), hasła domen | 84 wpisy rejestru, przypisane do istniejących haseł grupami. Nie stwierdzono osobnego brakującego działania dla właściciela. |
| Tabele `qbot_v2` | Hasła tematyczne, [Strony WWW](system/strony-www.md) | 235 nazw tabel. Rejestry pomocnicze i techniczne są zebrane w aneksie; nie wymagają 235 osobnych stron dla właściciela. |

## Automaty

Poniższe pliki usług i timerów odczytano w `/etc/systemd/system`. To dowód istnienia konfiguracji, nie dowód, że jednostka była aktywna w chwili odczytu.

| Jednostka lub zadanie | Hasło wiki albo BRAK | Ustalenie |
|---|---|---|
| `qbot-api.service` | [Albert](albert/index.md), [Status](system/status.md) | Usługa API. |
| `qbot-backup.timer` i `.service` | [Kopie bazy](system/kopie-bazy.md) | Codziennie 03:20. |
| `qbot-dev-mcp.service` | [MCP](albert/mcp.md), [Status](system/status.md) | Serwer narzędzi developerskich. |
| `qbot-garmin-watch.timer` i `.service` | [Garmin](polaczenia/garmin.md), [Strażnik Garmin](straznicy/garmin.md) | Start po 5 minutach od uruchomienia; kolejne przebiegi co 10 minut. |
| `qbot-guest-forecast.timer` i `.service` | [Zaproszenia dla gości](trasy/zaproszenia-gosci.md) | Codziennie 07:00 i 18:00; kontrola zmian prognozy dla zaproszonych. |
| `qbot-komoot-watch.timer` i `.service` | [Komoot](polaczenia/komoot.md) | Start po 3 minutach; kolejne kontrole co 5 minut. |
| `qbot-mcp-bridge.service` | [MCP](albert/mcp.md) | Mostek MCP. |
| `qbot-nutrition-watchdog.timer` i `.service` | [Strażnik żywienia](straznicy/zywienie.md) | Codziennie 08:00. Stan aktywności nie został odczytany. |
| `qbot-qlab-server.service` | [Status](system/status.md) | Serwer laboratorium. |
| `qbot-web.service` | [Strony WWW](system/strony-www.md) | Serwer ekranów WWW. |
| `qbot-weekly-audit.timer` i `.service` | [Audyt tygodniowy](system/audyt-tygodniowy.md) | Poniedziałek 02:30 czasu Warszawy. |
| `qbot-wiki-nightly.timer` i `.service` | [Automaty QBota](system/automaty.md), [Wiki](README.md) | Codziennie 23:50 uruchamia nocną aktualizację wiki. Wcześniej nie było jej w spisie automatów. |

W dostępnym crontabie roota znaleziono te aktywne wpisy. Zapis „qbot: brak dostępu” dotyczy osobnego pliku crontaba użytkownika i nie oznacza pustego harmonogramu.

| Pora lub rytm | Zadanie | Hasło wiki albo BRAK |
|---|---|---|
| Co 10 min, trzy profile | Synchronizacja Hammerhead → Garmin | [Garmin — sekcja Hammerhead/Karoo](polaczenia/garmin.md#hammerheadkaroo--garmin-tacx) |
| Codziennie 03:17 | Porządkowanie przeterminowanych artefaktów | [Automaty QBota](system/automaty.md) — techniczny automat |
| Co minutę | Przypomnienia | [Albert i QBot przez Telegram](albert/telegram.md), [Centrum powiadomień](system/centrum-powiadomien.md) |
| Codziennie 00:15 | Migawka profilu Xert | [Xert](polaczenia/xert.md) |
| Co 2 min | Przetwarzanie odpowiedzi Telegrama | [Albert i QBot przez Telegram](albert/telegram.md), [Potwierdzenia tras](trasy/potwierdzenia-telegram.md) |
| Niedziela 19:00 | Przegląd tygodnia | [Trener](trener/index.md) |
| Codziennie 04:45 | Dzienny przebieg ModelQ i kontroli po jeździe | [ModelQ](modelq/index.md), [Strażnicy](straznicy/index.md) |
| Co 30 min | Import FIT z QExt2 | [QExt2](qext2/przeplyw-jazdy.md), [Harmonogram importów](polaczenia/harmonogram-importow.md) |
| Codziennie 05:30 | Sprawdzenie duplikatów | [Automaty QBota](system/automaty.md) — techniczna kontrola |
| Co 15 min | Withings → Garmin | [Withings](polaczenia/withings.md) |
| Co 15 min | Powiadomienia Trenera | [Powiadomienia Trenera](trener/powiadomienia.md) |
| Co 15 min | Kontrola importu Garmina | [Strażnik Garmin](straznicy/garmin.md) |
| Poniedziałek 05:15 | Przeliczenie modelu prędkości | [Czas przejazdu](trasy/czas-przejazdu.md) |
| Co 15 min | Przypomnienie Brokuła | [Brokuł](zdrowie/brokul.md) |

Dzienny przebieg ModelQ uruchamia się także po imporcie nowej jazdy. To wywołanie zdarzeniowe, nie dodatkowa stała pora w crontabie; potwierdza je przepływ importu. Opisują go [Import FIT](modelq/import-fit.md) i hasła [Strażników](straznicy/index.md).

W kilku usługach są też pętle uruchamiane przy starcie aplikacji. Nie są osobnymi timerami systemd. Odczytano je bez uruchamiania tych zadań:

| Pętla wewnątrz usługi | Rytm z kodu | Hasło wiki |
|---|---|---|
| Liczenie dzwonka i wysyłanie powiadomień przeglądarki | Co 60 s | [Centrum powiadomień](system/centrum-powiadomien.md) |
| Pobieranie klatek radaru i sprawdzanie nowych opadów | Co 300 s (5 min) | [Radar](pogoda/radar.md), [Ostrzeżenie o deszczu](pogoda/ostrzezenia.md) |
| Sprawdzalność modeli pogody | Co 600 s (10 min); właściwe pomiary są wykonywane według własnych terminów | [Sprawdzalność prognoz](pogoda/sprawdzalnosc.md) |
| Pobieranie i rysowanie mapy pogody | Co 1 200 s (20 min) | [Mapa modeli](pogoda/mapa-modeli.md) |
| Kontrola zmian w QExt2 i aktualizacja symulatora | Co 600 s (10 min) | [Symulator QExt2](qext2/symulator.md) |
| Odświeżanie pogody na trasie podczas aktywnej jazdy Karoo | Co 60 s sprawdza sygnał; dla danej trasy wynik odświeża nie częściej niż co 900 s | [Pogoda w QExt2](pogoda/qext2.md) |
| Pobieranie nowych zdjęć z jazd Stravy | Co 3 godz. w godzinach 07–22; pierwsza kontrola 10 min po uruchomieniu | [Kalibracja zdjęć](garaz/kalibracja-zdjec.md) |
| Publikowanie opisu i roweru jazdy na Stravie | Co 1 200 s (20 min), w godzinach 06–23 | [Strava](polaczenia/strava.md) |

Powyższe częstotliwości opisują kod. Nie potwierdzają, że usługa była aktywna w chwili odczytu ani że wykonała każdą próbę.

## Wysyłanie wiadomości

Wyszukiwanie wzorców wysyłki dało 131 dopasowań w 38 plikach kodu poza archiwami. To liczba miejsc, w których wystąpił wzorzec, a nie 131 rodzajów wiadomości. Dopasowania obejmowały też pocztę e-mail oraz funkcje pomocnicze. Główne widoczne grupy mają przypisania:

| Co może dotrzeć do użytkownika | Hasło wiki |
|---|---|
| Odpowiedzi i pomoc w rozmowie | [Albert i QBot przez Telegram](albert/telegram.md) |
| Pytania o jazdę, zapas i potwierdzenie dalszej pracy | [Strażnicy](straznicy/index.md), [Potwierdzenia tras w Telegramie](trasy/potwierdzenia-telegram.md), [ModelQ](modelq/index.md) |
| Importy Garmin, żywienie, kontrola tygodniowa | [Strażnik Garmin](straznicy/garmin.md), [Strażnik żywienia](straznicy/zywienie.md), [Audyt tygodniowy](system/audyt-tygodniowy.md) |
| Zmiana pogody przed jazdą lub dla zaproszonego gościa | [Ostrzeżenie o deszczu](pogoda/ostrzezenia.md), [Zaproszenia dla gości](trasy/zaproszenia-gosci.md) |
| Powiadomienia Trenera, Brokuła i przypomnienia | [Powiadomienia Trenera](trener/powiadomienia.md), [Brokuł](zdrowie/brokul.md), [Centrum powiadomień](system/centrum-powiadomien.md) |
| Aktualizacja statusu po publikacji Stravy lub obserwacji Komoot | [Strava](polaczenia/strava.md), [Komoot](polaczenia/komoot.md) |
| Prośby o potwierdzenie gościa lub zmiany w zaproszeniu | [Zaproszenia dla gości](trasy/zaproszenia-gosci.md), [Kontakty w SETUP](system/kontakty.md) |

Nie każde wywołanie `send` wysyła Telegram. Część obsługuje e-mail, a część tylko buduje albo testuje wiadomość. Dokładnego doręczenia nie potwierdza sam kod wysyłający.

## Strony i zakładki

Poniższe 36 stron znaleziono w katalogu publicznym. Strony pomocnicze lub makiety oznaczyłem jako zaplecze, a widoczne funkcje przypisałem do istniejącego lub nowego hasła.

| Strona | Hasło wiki albo BRAK | Klasyfikacja |
|---|---|---|
| `cwiczenia.html` | [Ćwiczenia i ściąga](trener/cwiczenia-sciaga.md) | Opisane |
| `dashboard.html` | [Mapa serwisu](mapa-serwisu.md), [Trening](trener/index.md), [Forma](forma/index.md) | Opisane jako widok „Dziś” |
| `forma.html` | [Forma](forma/index.md), [Statystyki](forma/statystyki.md), [Wykresy](forma/wykresy.md) | Opisane; zakładki „Statystyki” i „Krzywa mocy” |
| `garaz.html` | [Garaż](garaz/index.md) | Opisane |
| `index.html` | [Mapa serwisu](mapa-serwisu.md) | Opisane |
| `jedzenie.html` | [Zdrowie i jedzenie](zdrowie/index.md) | Przekierowuje do Zdrowia |
| `kalendarz.html` | [Kalendarz treningowy](trener/kalendarz.md) | Przekierowuje do Treningu |
| `mq2.html` | [ModelQ](modelq/index.md) | Opisane |
| `naprawa-trasy.html` | [Naprawa tras](trasy/naprawa-tras.md) | Opisane |
| `okno-makieta.html` | [Okno jazdy](pogoda/okno-jazdy.md) | Makieta, nie osobny dział funkcji |
| `planer-wyposazenia.html` | [Planer wyposażenia](garaz/planer-wyposazenia.md) | Nowe hasło |
| `planer-wyprawy-druk.html`, `planer-wyprawy.html` | [Planer wyprawy](trasy/planer-wyprawy.md) | Opisane |
| `pogoda-foto/podglad.html` | **BRAK osobnego hasła** | Widok pomocniczy zdjęć pogody; przeznaczenie dla właściciela niepotwierdzone |
| `pogoda-makieta.html` | [Pogoda](pogoda/index.md) | Makieta, nie osobna funkcja |
| `pogoda-wyprawy.html`, `pogoda.html` | [Pogoda](pogoda/index.md), [Pogoda na trasie](pogoda/pogoda-na-trasie.md) | Opisane |
| `qbot-dodaj.html` | [Dodawanie produktu ze sklepu](garaz/dodaj-zakup-ze-sklepu.md) | Nowe hasło |
| `qext2-makieta.html` | [Symulator QExt2](qext2/symulator.md) | Widoczny podgląd trzech ekranów w dziale Garaż; dane przykładowe, nie pochodzą z licznika |
| `raport-dzien.html` | [Raport dnia](trasy/raport-dnia.md) | Opisane |
| `raport-gosc.html` | [Zaproszenia dla gości](trasy/zaproszenia-gosci.md) | Nowe hasło |
| `raport-jazdy.html` | [Raport jazdy](raport-jazdy/index.md) | Opisane |
| `raport-print.html` | [Raport jazdy](raport-jazdy/index.md) | Techniczny wydruk raportu |
| `raport-trasy.html` | [Analiza trasy](trasy/analiza-trasy.md) | Opisane |
| `sciaga.html` | [Ćwiczenia i ściąga](trener/cwiczenia-sciaga.md) | Opisane |
| `setup.html` | [Strony WWW](system/strony-www.md), [Kontakty](system/kontakty.md), [Status](system/status.md) | Główne zakładki ustawień |
| `status.html` | [Status](system/status.md) | Opisane |
| `strava.html` | [Strava](polaczenia/strava.md) | Opisane |
| `trener-fragment.html`, `trener.html`, `trening.html` | [Trening](trener/index.md), [Bilans i masa ciała](trener/bilans-waga.md), [Kalendarz](trener/kalendarz.md) | Fragment lub przekierowania do Treningu |
| `wiki-dane/index.html`, `wiki.html` | [Wiki QBota](README.md) | Podgląd danych i interfejs wiki |
| `wyprawa-oczekiwanie.html` | [Zaproszenia dla gości](trasy/zaproszenia-gosci.md) | Nowe hasło obejmuje oczekiwanie na PDF |
| `zdjecia.html` | [Kalibracja zdjęć](garaz/kalibracja-zdjec.md) | Nowe hasło |
| `zdrowie.html` | [Zdrowie i jedzenie](zdrowie/index.md) | Opisane |

### Zakładki i podwidoki

- Forma: w HTML są zakładki „Statystyki” i „Krzywa mocy”; zakładka Krzywa mocy nie miała dotąd własnego hasła, ale jest teraz wymieniona w [Wykresach](forma/wykresy.md).
- Garaż: interfejs buduje zakładki roweru, części, odzieży, sprzętu, wypraw, fittingu, instrukcji, notatek i zakupów; opisy są w [dziale Garaż](garaz/index.md). Planner wyposażenia jest oddzielną stroną i dostał osobne hasło.
- Trening: część paneli powstaje z plików skryptów, a nie ze statycznych zakładek HTML. Główne tematy są w [dziale Trener](trener/index.md). Nie spisywałem nazw sekcji, których kod frontu nie ujawnia jako stabilnej listy.
- SETUP: widoczne główne obszary to Powiadomienia, Trening, Połączenia, Dostępy, Kontakty i QExt2. Ich opisy są rozłożone w dziale [System](system/index.md) oraz [Połączenia](polaczenia/index.md).

## Narzędzia Alberta

Rejestr zawiera 84 pozycje: odczyty statusu i zdrowia, integracje, operacje tras, pliki oraz dozwolone zapisy. To zaplecze rozmowy, więc nie wymaga osobnej strony dla każdej nazwy. Właściwe grupy opisują [Narzędzia Alberta](albert/narzedzia.md); dostęp publicznego MCP opisuje osobne hasło [MCP](albert/mcp.md).

| Grupa widoczna dla właściciela | Pokrycie |
|---|---|
| Status, forma i gotowość | [Forma](forma/index.md), [Status](system/status.md), [Albert](albert/narzedzia.md) |
| Żywienie, sen, serce i suplementy | [Zdrowie](zdrowie/index.md), [Albert](albert/narzedzia.md) |
| Pogoda i okno jazdy | [Pogoda](pogoda/index.md), [Albert](albert/narzedzia.md) |
| Trasy, profil, czas i punkty | [Trasy](trasy/index.md), [Albert](albert/narzedzia.md) |
| Garaż, pliki i dokumenty | [Garaż](garaz/index.md), [Albert](albert/narzedzia.md) |
| Odczytowe zapytania do zaplecza i zapisy | [Ograniczenia Alberta](albert/ograniczenia.md), [Albert przez Telegram](albert/telegram.md) |

## Endpointy i tabele techniczne

Poniższe elementy są techniczne. Ich obecność w tabeli nie oznacza brakującego hasła dla użytkownika. Opisy ekranów i domen wskazują odpowiednie hasła; pełne ścieżki służą do kompletnego przeglądu.

| Grupa endpointów | Ile deklaracji | Hasło wiki |
|---|---:|---|
| Serwer WWW: trasy, raporty i zaproszenia | 212 ścieżek `/api/` | [Trasy](trasy/index.md), [Zaproszenia](trasy/zaproszenia-gosci.md), [Strony WWW](system/strony-www.md) |
| Serwer WWW: Forma, Garaż, zdrowie, Trener, Pogoda, Status | Włączone do 212 powyżej | Odpowiednie działy [Forma](forma/index.md), [Garaż](garaz/index.md), [Zdrowie](zdrowie/index.md), [Trener](trener/index.md), [Pogoda](pogoda/index.md), [System](system/index.md) |
| API i integracje: pozostałe ścieżki `/api/` | 6 ścieżek | [MCP](albert/mcp.md), [Połączenia](polaczenia/index.md), [Zdrowie](zdrowie/index.md) |
| Pozostałe ścieżki HTTP z obu plików | 48 ścieżek spośród 266 | [Strony WWW](system/strony-www.md), [MCP](albert/mcp.md), odpowiednie działy |

Spis 235 tabel składa się z danych jazd i ModelQ, zdrowia i jedzenia, profilu Garażu, tras i ich warstw, pogody, powiadomień, integracji, narzędzi Trenera i kopii historycznych. Wiki opisuje użytkowe grupy, nie schemat bazy danych.

<details>
<summary>Pełny spis ścieżek HTTP i dodatkowych dopasowań (282)</summary>

Wśród 282 surowych dopasowań jest 266 deklaracji metod HTTP oraz 16 dopasowań montażu routerów, komentarzy i podobnych nazw. Spośród 266 ścieżek HTTP, 218 zaczyna się od `/api/`: 212 jest w `qbot_web.py`, a 6 w `qbot_api.py`.

- `GET /login` — `qbot_web.py:270`
- `POST /login` — `qbot_web.py:285`
- `GET /api/prefs` — `qbot_web.py:369`
- `POST /api/prefs` — `qbot_web.py:384`
- `GET /api/forma/activities` — `qbot_web.py:409`
- `GET /api/forma/heart` — `qbot_web.py:439`
- `GET /api/forma/ecg` — `qbot_web.py:447`
- `POST /api/forma/ecg/ai` — `qbot_web.py:464`
- `GET /api/forma/heart/report.pdf` — `qbot_web.py:495`
- `GET /api/forma/ecg.pdf` — `qbot_web.py:510`
- `GET /api/forma/activity` — `qbot_web.py:523`
- `GET /healthz` — `qbot_web.py:549`
- `GET /api/routes/ready` — `qbot_web.py:554`
- `GET /api/routes/{route_id}/geometry` — `qbot_web.py:590`
- `GET /api/routes/{route_id}/spine` — `qbot_web.py:637`
- `GET /api/noclegi` — `qbot_web.py:696`
- `GET /api/planer/atrakcja` — `qbot_web.py:868`
- `GET /api/planer/foto/{place_id}` — `qbot_web.py:938`
- `GET /api/planer/opis` — `qbot_web.py:951`
- `GET /api/planer/tlo` — `qbot_web.py:968`
- `GET /hammerhead-dostep` — `qbot_web.py:1040`
- `POST /api/hammerhead/refresh-token` — `qbot_web.py:1048`
- `GET /brokul-dostep` — `qbot_web.py:1186`
- `GET /api/brokul/session/status` — `qbot_web.py:1195`
- `POST /api/brokul/session` — `qbot_web.py:1204`
- `GET /komoot-dostep` — `qbot_web.py:1224`
- `GET /api/komoot/session/status` — `qbot_web.py:1232`
- `POST /api/komoot/session` — `qbot_web.py:1244`
- `POST /api/planer/opis-dni` — `qbot_web.py:1267`
- `POST /api/planer/dodaj-do-qbot` — `qbot_web.py:1292`
- `GET /api/planer/dzien/gpx` — `qbot_web.py:1318`
- `GET /api/routes/{route_id}/tiles` — `qbot_web.py:1357`
- `GET /api/routes/{route_id}/surface-segments` — `qbot_web.py:1609`
- `GET /api/routes/{route_id}/surface-categories` — `qbot_web.py:1766`
- `GET /api/routes/{route_id}/segments/candidate` — `qbot_web.py:1957`
- `GET /kanon` — `qbot_web.py:2177`
- `GET /api/report/gpx` — `qbot_web.py:2934`
- `POST /api/report/attractions/fetch` — `qbot_web.py:3027`
- `POST /api/report/push-karoo` — `qbot_web.py:3060`
- `GET /api/planer/dzien` — `qbot_web.py:4198`
- `POST /api/pogoda/mail` — `qbot_web.py:4561`
- `GET /api/planer/pogoda` — `qbot_web.py:4651`
- `POST /api/planer/wykonalnosc` — `qbot_web.py:4882`
- `POST /api/planer/forma-plus` — `qbot_web.py:4922`
- `POST /api/planer/ubior` — `qbot_web.py:4956`
- `POST /api/planer/planned-load/recompute` — `qbot_web.py:5063`
- `GET /api/report/data` — `qbot_web.py:5092`
- `GET /api/config/map` — `qbot_web.py:5107`
- `GET /api/report/plan` — `qbot_web.py:5116`
- `GET /g/assets/{name}` — `qbot_web.py:5170`
- `GET /g/{token}` — `qbot_web.py:5183`
- `GET /api/guest/{token}` — `qbot_web.py:5191`
- `GET /api/guest/{token}/gpx` — `qbot_web.py:5223`
- `POST /api/guest/{token}/rsvp` — `qbot_web.py:5233`
- `POST /api/invites` — `qbot_web.py:5246`
- `GET /api/invites` — `qbot_web.py:5279`
- `GET /api/invites/preview` — `qbot_web.py:5312`
- `POST /api/invites/send` — `qbot_web.py:5326`
- `POST /api/invites/revoke` — `qbot_web.py:5412`
- `GET /api/route-intro` — `qbot_web.py:5422`
- `POST /api/route-intro` — `qbot_web.py:5434`
- `GET /api/report/kit` — `qbot_web.py:5455`
- `POST /api/report/kit` — `qbot_web.py:5473`
- `POST /api/report/kit/manual` — `qbot_web.py:5501`
- `POST /api/report/outfit/note` — `qbot_web.py:5527`
- `GET /api/report/outfit/lessons` — `qbot_web.py:5553`
- `POST /api/report/outfit/lessons` — `qbot_web.py:5564`
- `GET /api/report/outfit/gear` — `qbot_web.py:5587`
- `GET /api/report/outfit/fav` — `qbot_web.py:5594`
- `POST /api/report/outfit/fav` — `qbot_web.py:5605`
- `GET /api/report/outfit` — `qbot_web.py:5623`
- `POST /api/report/outfit` — `qbot_web.py:5635`
- `POST /api/report/plan/save` — `qbot_web.py:5676`
- `POST /api/report/day-pack` — `qbot_web.py:5723`
- `GET /api/report/day-pack/status` — `qbot_web.py:5737`
- `GET /api/report/day-packs` — `qbot_web.py:5747`
- `GET /api/report/day-pack` — `qbot_web.py:5758`
- `GET /api/report/history` — `qbot_web.py:5770`
- `GET /api/report/snapshot/{snapshot_id}` — `qbot_web.py:5791`
- `GET /api/report/mail-recipients` — `qbot_web.py:6159`
- `POST /api/report/send-email` — `qbot_web.py:6172`
- `GET /api/report/schedules` — `qbot_web.py:6306`
- `POST /api/report/schedule` — `qbot_web.py:6325`
- `DELETE /api/report/schedule/{schedule_id}` — `qbot_web.py:6370`
- `POST /api/report/schedule/{schedule_id}/run` — `qbot_web.py:6382`
- `GET /api/report/schedule/{schedule_id}` — `qbot_web.py:6401`
- `GET /api/rides/ready` — `qbot_web.py:6498`
- `GET /api/ride-report/data` — `qbot_web.py:6535`
- `POST /api/ride-report/analyze` — `qbot_web.py:6577`
- `GET /api/ride-report/energia` — `qbot_web.py:6586`
- `GET /api/ride-report/status` — `qbot_web.py:6606`
- `GET /api/ride-report/tiles` — `qbot_web.py:6618`
- `GET /api/ride-report/w2` — `qbot_web.py:6683`
- `POST /api/ride-report/correlate` — `qbot_web.py:6765`
- `GET /api/ride-gear/options` — `qbot_web.py:6872`
- `GET /api/radar/meta` — `qbot_web.py:7046`
- `GET /api/radar/frame/{fid}.png` — `qbot_web.py:7058`
- `GET /api/radar/punkt` — `qbot_web.py:7070`
- `GET /api/pogoda/dom` — `qbot_web.py:7077`
- `GET /api/pogoda/model` — `qbot_web.py:7090`
- `GET /api/pogoda/warunki` — `qbot_web.py:7097`
- `GET /api/pogoda/kwadraty` — `qbot_web.py:7107`
- `GET /api/pogoda/sprawdzalnosc` — `qbot_web.py:7143`
- `GET /api/pogoda/mapa/meta` — `qbot_web.py:7209`
- `GET /api/pogoda/mapa/{layer}/{rid}.png` — `qbot_web.py:7216`
- `GET /api/pogoda/mapa/korekta` — `qbot_web.py:7226`
- `GET /api/pogoda/charakter` — `qbot_web.py:7233`
- `GET /api/pogoda/ostrzezenie` — `qbot_web.py:7240`
- `GET /api/pogoda/okno` — `qbot_web.py:7252`
- `GET /api/pogoda/jazdy-trasy` — `qbot_web.py:7285`
- `GET /api/pogoda/weekend` — `qbot_web.py:7315`
- `GET /api/pogoda/weekend/{key}.png` — `qbot_web.py:7362`
- `GET /api/pogoda/sprawdzalnosc-radar` — `qbot_web.py:7375`
- `GET /api/pogoda/sprawdzalnosc-szansa` — `qbot_web.py:7386`
- `GET /api/push/key` — `qbot_web.py:7402`
- `POST /api/push/subscribe` — `qbot_web.py:7418`
- `POST /api/push/unsubscribe` — `qbot_web.py:7441`
- `POST /api/push/test` — `qbot_web.py:7460`
- `GET /api/notif` — `qbot_web.py:7475`
- `GET /api/notif/history` — `qbot_web.py:7496`
- `GET /api/setup/notif` — `qbot_web.py:7507`
- `GET /api/setup/qext2` — `qbot_web.py:7520`
- `POST /api/setup/qext2` — `qbot_web.py:7534`
- `POST /api/setup/notif` — `qbot_web.py:7559`
- `POST /api/notif/read` — `qbot_web.py:7578`
- `POST /api/notif/dismiss` — `qbot_web.py:7596`
- `GET /api/bike-tasks` — `qbot_web.py:7615`
- `POST /api/bike-tasks/save` — `qbot_web.py:7627`
- `POST /api/bike-tasks/done` — `qbot_web.py:7645`
- `POST /api/ride-gear/save` — `qbot_web.py:7662`
- `GET /api/gear-obs/note/{note_id}` — `qbot_web.py:7726`
- `POST /api/gear-obs/answer` — `qbot_web.py:7732`
- `GET /api/gear-obs/gear/{gear_id}` — `qbot_web.py:7746`
- `POST /api/gear-obs/proposal` — `qbot_web.py:7755`
- `GET /api/garage/list` — `qbot_web.py:7847`
- `POST /api/garage/save` — `qbot_web.py:7898`
- `POST /api/garage/ratings` — `qbot_web.py:8038`
- `POST /api/garage/toggle` — `qbot_web.py:8081`
- `POST /api/garage/photo` — `qbot_web.py:8116`
- `POST /api/garage/photo/delete` — `qbot_web.py:8155`
- `POST /api/garage/scrape` — `qbot_web.py:8199`
- `POST /api/garage/scrape-page` — `qbot_web.py:8221`
- `POST /api/garage/photo/from-url` — `qbot_web.py:8243`
- `GET /api/equipment/list` — `qbot_web.py:8312`
- `POST /api/equipment/save` — `qbot_web.py:8328`
- `POST /api/equipment/toggle` — `qbot_web.py:8382`
- `GET /api/bike/config` — `qbot_web.py:8401`
- `POST /api/bike/component/save` — `qbot_web.py:8437`
- `_gw_mount(gc, int(gid), cols.get("bike_id"), source="manual")  # przelozenie kol recznie` — `qbot_web.py:8505`
- `POST /api/bike/component/toggle` — `qbot_web.py:8515`
- `POST /api/garage/delete` — `qbot_web.py:8580`
- `POST /api/equipment/delete` — `qbot_web.py:8586`
- `POST /api/bike/component/delete` — `qbot_web.py:8592`
- `POST /api/bike/fitting/save` — `qbot_web.py:8659`
- `POST /api/bike/fitting/delete` — `qbot_web.py:8686`
- `POST /api/bike/geometry/save` — `qbot_web.py:8701`
- `POST /api/bike/body/save` — `qbot_web.py:8725`
- `POST /api/bike/body/delete` — `qbot_web.py:8739`
- `POST /api/bike/bike/save` — `qbot_web.py:8755`
- `POST /api/bike/bike/delete` — `qbot_web.py:8791`
- `POST /api/bike/tire/save` — `qbot_web.py:8836`
- `POST /api/bike/tire/delete` — `qbot_web.py:8896`
- `GET /api/garage/prefs` — `qbot_web.py:8917`
- `POST /api/garage/prefs` — `qbot_web.py:8936`
- `GET /api/instructions/list` — `qbot_web.py:8977`
- `POST /api/instructions/save` — `qbot_web.py:8992`
- `POST /api/instructions/toggle` — `qbot_web.py:9037`
- `POST /api/instructions/delete` — `qbot_web.py:9057`
- `GET /api/bike-notes/list` — `qbot_web.py:9098`
- `POST /api/bike-notes/save` — `qbot_web.py:9111`
- `POST /api/bike-notes/delete` — `qbot_web.py:9150`
- `GET /api/forma/event-prep` — `qbot_web.py:9433`
- `POST /api/forma/analyze` — `qbot_web.py:9443`
- `GET /api/planer/wyposazenie/pogoda` — `qbot_web.py:9744`
- `POST /api/planer/wyposazenie/generate` — `qbot_web.py:10123`
- `GET /api/planer/wyposazenie/garage-options` — `qbot_web.py:10629`
- `GET /api/planer/wyposazenie/kategorie` — `qbot_web.py:10805`
- `GET /api/planer/wyposazenie/zasady` — `qbot_web.py:10836`
- `POST /api/planer/wyposazenie/garage-add` — `qbot_web.py:10860`
- `POST /api/planer/wyposazenie/save` — `qbot_web.py:10886`
- `GET /api/planer/wyposazenie/list` — `qbot_web.py:10973`
- `GET /api/planer/wyposazenie/bags` — `qbot_web.py:11029`
- `GET /api/planer/wyposazenie/summary` — `qbot_web.py:11054`
- `GET /api/calendar` — `qbot_web.py:11115`
- `GET /api/calendar/wx` — `qbot_web.py:11208`
- `POST /api/calendar/entry` — `qbot_web.py:11308`
- `POST /api/calendar/delete` — `qbot_web.py:11384`
- `POST /api/calendar/edit` — `qbot_web.py:11406`
- `POST /api/mail-groups/import-rsvp` — `qbot_web.py:11535`
- `POST /api/mail-groups/{group_id}/sync` — `qbot_web.py:11577`
- `GET /api/mail-groups` — `qbot_web.py:11595`
- `POST /api/mail-groups` — `qbot_web.py:11605`
- `DELETE /api/mail-groups/{group_id}` — `qbot_web.py:11627`
- `POST /api/mail-groups/{group_id}/members` — `qbot_web.py:11639`
- `DELETE /api/mail-groups/{group_id}/members/{member_id}` — `qbot_web.py:11667`
- `GET /api/planer/termin` — `qbot_web.py:11680`
- `GET /api/planer/wyposazenie/termin` — `qbot_web.py:11681`
- `POST /api/calendar/route` — `qbot_web.py:11759`
- `GET /api/watch/face` — `qbot_web.py:11977`
- `GET /api/forma/data` — `qbot_web.py:12037`
- `GET /api/forma/season/analyze` — `qbot_web.py:12115`
- `POST /api/forma/season/analyze` — `qbot_web.py:12166`
- `GET /api/forma/season` — `qbot_web.py:12179`
- `GET /api/forma/cda` — `qbot_web.py:12193`
- `GET /api/power/curve` — `qbot_web.py:12207`
- `GET /api/stats/rides` — `qbot_web.py:12288`
- `GET /api/nutrition/status` — `qbot_web.py:12484`
- `GET /api/nutrition/day-summary` — `qbot_web.py:12502`
- `GET /api/nutrition/preset/values` — `qbot_web.py:12540`
- `POST /api/nutrition/preset/apply` — `qbot_web.py:12566`
- `GET /api/nutrition/items` — `qbot_web.py:12606`
- `POST /api/nutrition/item/update` — `qbot_web.py:12644`
- `POST /api/nutrition/item/delete` — `qbot_web.py:12721`
- `GET /api/nutrition/data` — `qbot_web.py:12749`
- `POST /api/nutrition/analyze` — `qbot_web.py:12763`
- `GET /api/modelq2/data` — `qbot_web.py:12838`
- `POST /api/modelq2/recompute` — `qbot_web.py:12967`
- `GET /api/wyprawa/pdf-start` — `qbot_web.py:13481`
- `GET /api/wyprawa/pdf` — `qbot_web.py:13508`
- `GET /wyprawa-rsvp` — `qbot_web.py:13746`
- `POST /api/wyprawa/rsvp` — `qbot_web.py:13788`
- `POST /api/wyprawa/send-email` — `qbot_web.py:13828`
- `GET /api/wyprawa/rsvp-list` — `qbot_web.py:13897`
- `GET /reports/{fn}` — `qbot_web.py:13921`
- `# Musi byc PRZED app.mount("/"), inaczej statyki przechwyca sciezke. Dok.: docs/TRENER.md` — `qbot_web.py:13939`
- `app.include_router(_trener_build_router(_db_conn, _current_user))` — `qbot_web.py:13941`
- `app.include_router(_food_build_router(_current_user, _owner_user))` — `qbot_web.py:13943`
- `app.include_router(_trend_ai_build_router(_current_user, _owner_user))` — `qbot_web.py:13945`
- `app.include_router(_supl_build_router(_current_user, _owner_user))` — `qbot_web.py:13947`
- `app.include_router(_gaudit_build_router(_current_user))` — `qbot_web.py:13949`
- `app.include_router(_zakupy_build_router(_current_user, _owner_user))` — `qbot_web.py:13951`
- `app.include_router(_strava_build_router(_db_conn, _current_user))` — `qbot_web.py:13953`
- `app.include_router(_start_build_router(_db_conn, _current_user))` — `qbot_web.py:13955`
- `app.include_router(_status_build_router(_current_user, _owner_user))` — `qbot_web.py:13957`
- `app.include_router(_weekend_build_router(_current_user, _owner_user))` — `qbot_web.py:13959`
- `app.include_router(_wda.build_router())` — `qbot_web.py:13963`
- `app.mount("/landing", StaticFiles(directory="/opt/qbot/web/landing"), name="landing")  # publiczne zdjecia /login` — `qbot_web.py:13964`
- `app.mount("/", StaticFiles(directory=WEB_ROOT, html=True), name="static")` — `qbot_web.py:13967`
- `GET /health` — `qbot_api.py:854`
- `GET /fitmodel/buckets/active` — `qbot_api.py:864`
- `GET /fitmodel/buckets/active/` — `qbot_api.py:865`
- `GET /photos/activities` — `qbot_api.py:872`
- `GET /photos/activities/` — `qbot_api.py:873`
- `GET /ride-readiness` — `qbot_api.py:884`
- `GET /ride-readiness/` — `qbot_api.py:885`
- `POST /nutrition/intake/text` — `qbot_api.py:1139`
- `POST /nutrition/foods` — `qbot_api.py:1159`
- `GET /nutrition/foods/search` — `qbot_api.py:1172`
- `POST /nutrition/meals` — `qbot_api.py:1182`
- `POST /nutrition/hydration` — `qbot_api.py:1203`
- `GET /nutrition/day/{date_str}` — `qbot_api.py:1216`
- `POST /nutrition/import/cronometer/servings-csv` — `qbot_api.py:1225`
- `POST /q` — `qbot_api.py:1282`
- `POST /rwgps-webhook/{webhook_secret}` — `qbot_api.py:1301`
- `POST /telegram/webhook/{webhook_secret}` — `qbot_api.py:1390`
- `GET /mcp/` — `qbot_api.py:1533`
- `GET /mcp` — `qbot_api.py:1534`
- `GET /mcp/health` — `qbot_api.py:1566`
- `GET /mcp/health/` — `qbot_api.py:1567`
- `GET /mcp/tools` — `qbot_api.py:1584`
- `GET /mcp/tools/` — `qbot_api.py:1585`
- `POST /mcp/` — `qbot_api.py:1599`
- `POST /mcp` — `qbot_api.py:1600`
- `GET /api/surface/by-name` — `qbot_api.py:1628`
- `GET /api/poi/by-name` — `qbot_api.py:1801`
- `GET /api/plan/by-name` — `qbot_api.py:2081`
- `GET /api/weather/by-name` — `qbot_api.py:2095`
- `GET /api/weather/point` — `qbot_api.py:2120`
- `GET /api/ef/typical` — `qbot_api.py:2134`
- `GET /mcp/.well-known/oauth-protected-resource` — `qbot_api.py:2178`
- `GET /.well-known/oauth-protected-resource` — `qbot_api.py:2179`
- `GET /.well-known/oauth-authorization-server` — `qbot_api.py:2189`
- `GET /mcp/.well-known/oauth-authorization-server` — `qbot_api.py:2190`
- `POST /oauth/register` — `qbot_api.py:2235`
- `POST /oauth/register/` — `qbot_api.py:2236`
- `GET /oauth/authorize` — `qbot_api.py:2253`
- `GET /oauth/authorize/` — `qbot_api.py:2254`
- `POST /oauth/authorize` — `qbot_api.py:2263`
- `POST /oauth/authorize/` — `qbot_api.py:2264`
- `POST /oauth/token` — `qbot_api.py:2287`
- `POST /oauth/token/` — `qbot_api.py:2288`
- `app.include_router(_dash_router)` — `qbot_api.py:2310`

</details>

<details>
<summary>Wpisy rejestru narzędzi Alberta (84)</summary>

`status`, `readiness`, `system_env_status`, `planning_facts`, `planning_fact_lookup`, `weather_forecast`, `nutrition_template_list`, `nutrition_template_get`, `nutrition_write_resolve`, `nutrition_day_summary`, `nutrition_meal_list`, `nutrition_range_summary`, `wellness_day`, `sleep_day`, `xert_readiness`, `fitness_status`, `garmin_diagnostics`, `garmin_live_fetch`, `rwgps_route_list`, `rwgps_route_fetch`, `route_stage_plan_analyze`, `route_gpx_split`, `stage_gpx_analyze`, `rwgps_route_surface_analyze`, `garage_status`, `artifacts_list`, `artifact_save`, `canonical_docs`, `mcp_tools_list`, `withings_sync_status`, `qbot_status_overview`, `food_weekend_plan`, `gate_status`, `hammerhead_sync_status`, `llm_status`, `system_logs_recent`, `docs_list_qbot`, `nutrition_balance_today`, `garmin_energy_today`, `garmin_sync_status`, `rwgps_route_last`, `rwgps_artifact_status`, `rwgps_route_find`, `route_plan_analysis`, `ride_analysis`, `route_profile_detail`, `route_list`, `route_recompute`, `route_attractions`, `route_delete`, `tire_pressure`, `trainer_week`, `heart_health`, `supplements`, `wiki`, `weather_now`, `ride_window`, `ride_where`, `weather_skill`, `route_fuel_plan`, `route_time_estimate`, `route_wbgt`, `route_artifact_enrich_dry_run`, `route_poi_analyze`, `route_poi_analyze_readonly`, `route_report`, `route_day_plan`, `route_analysis`, `rwgps_poi_push`, `rwgps_route_import_gpx`, `artifact_search`, `db_schema_list`, `db_table_describe`, `db_sample_rows`, `db_select_readonly`, `garage_tables`, `garage_select`, `nutrition_log_add`, `nutrition_log_delete`, `nutrition_log_correct`, `garmin_workout_create`, `planning_fact_add`, `planning_fact_update`, `memory_confirmed_fact_add`

</details>

<details>
<summary>131 dopasowań wysyłek i powiadomień znalezionych w kodzie</summary>

Dopasowania zawierają również pocztę e-mail, metody pomocnicze i miejsca testowe; to indeks plik:wiersz z wyszukania, nie 131 odrębnych typów wiadomości.

- `email_reply_processor.py:87`
- `email_reply_processor.py:92`
- `email_reply_processor.py:126`
- `email_reply_processor.py:131`
- `email_reply_processor.py:245`
- `email_reply_processor.py:246`
- `email_reply_processor.py:252`
- `email_reply_processor.py:255`
- `email_reply_processor.py:262`
- `email_reply_processor.py:387`
- `email_reply_processor.py:388`
- `email_reply_processor.py:396`
- `email_reply_processor.py:399`
- `email_reply_processor.py:407`
- `qbot_strava_publish.py:827`
- `komoot_watch.py:53`
- `komoot_watch.py:56`
- `komoot_watch.py:149`
- `komoot_watch.py:174`
- `komoot_watch.py:365`
- `komoot_watch.py:429`
- `qbot_roadmap_runner.py:43`
- `qbot_roadmap_runner.py:618`
- `qbot_roadmap_runner.py:621`
- `qbot_roadmap_runner.py:829`
- `qbot_roadmap_runner.py:1038`
- `qbot_roadmap_runner.py:1274`
- `qbot_roadmap_runner.py:1640`
- `qbot_web_auth.py:242`
- `qbot_web.py:4640`
- `qbot_web.py:5392`
- `qbot_web.py:6201`
- `qbot_web.py:6236`
- `qbot_web.py:6286`
- `qbot_web.py:6297`
- `qbot_web.py:13676`
- `qbot_web.py:13682`
- `qbot_web.py:13818`
- `qbot_web.py:13822`
- `qbot_web.py:13880`
- `qbot_trener_notify.py:189`
- `qbot_dev_mcp_gate.py:73`
- `qbot_telegram_client.py:41`
- `qbot_telegram_client.py:47`
- `qbot_pogoda_alert.py:166`
- `qbot_telegram_tools.py:344`
- `qbot_telegram_tools.py:347`
- `qbot_telegram_tools.py:432`
- `qbot_telegram_tools.py:436`
- `qbot_telegram_tools.py:462`
- `qbot_telegram_tools.py:501`
- `monitor.py:13`
- `monitor.py:15`
- `monitor.py:70`
- `telegram_reply_processor.py:86`
- `telegram_reply_processor.py:238`
- `telegram_reply_processor.py:346`
- `telegram_reply_processor.py:348`
- `qbot_api.py:265`
- `qbot_api.py:1385`
- `qbot_api.py:1502`
- `qbot_api.py:1503`
- `qbot_api.py:1507`
- `qbot_api.py:1509`
- `qbot_api.py:1511`
- `qbot_food_log.py:422`
- `qbot_food_log.py:1076`
- `qbot_food_log.py:1078`
- `weekly_review.py:30`
- `weekly_review.py:33`
- `weekly_review.py:111`
- `reminder_daemon.py:73`
- `reminder_daemon.py:174`
- `qbot_qcal_telegram.py:68`
- `qbot_qcal_telegram.py:72`
- `tests/test_route_precompute_trigger.py:426`
- `tests/test_route_precompute_trigger.py:440`
- `tests/test_route_precompute_trigger.py:441`
- `tests/test_route_precompute_trigger.py:456`
- `tests/test_route_precompute_trigger.py:476`
- `tests/test_route_precompute_trigger.py:477`
- `tests/test_route_precompute_trigger.py:485`
- `tests/test_route_precompute_trigger.py:504`
- `tests/test_route_precompute_trigger.py:511`
- `tests/test_route_precompute_trigger.py:531`
- `tests/test_route_precompute_trigger.py:536`
- `tests/test_route_precompute_trigger.py:559`
- `_bak_archive/20260618_201630_qbot_api.py:248`
- `_bak_archive/20260618_201630_qbot_api.py:1209`
- `_bak_archive/20260618_201630_qbot_api.py:1210`
- `_bak_archive/20260618_201630_qbot_api.py:1214`
- `_bak_archive/20260618_201630_qbot_api.py:1216`
- `_bak_archive/20260618_201630_qbot_api.py:1218`
- `scripts/qext2_watch.py:271`
- `scripts/qext2_watch.py:284`
- `scripts/qext2_watch.py:323`
- `scripts/zakupy_ceny_worker.py:28`
- `scripts/zakupy_ceny_worker.py:74`
- `scripts/weekly_audit.py:99`
- `scripts/guest_forecast_watch.py:93`
- `scripts/nutrition_watchdog.py:29`
- `scripts/nutrition_watchdog.py:132`
- `scripts/garmin_watch.py:83`
- `scripts/route_precompute_trigger.py:211`
- `scripts/route_precompute_trigger.py:399`
- `scripts/rebuild_ride_reports.py:77`
- `scripts/rebuild_ride_reports.py:131`
- `scripts/rebuild_ride_reports.py:135`
- `scripts/speed_model_recalibrate.py:45`
- `scripts/komoot_analyze_worker.py:42`
- `scripts/verify_dupes.py:113`
- `scripts/verify_dupes.py:121`
- `scripts/verify_dupes.py:177`
- `archive/fitmodel_power_meter_guard.20261018.py:292`
- `fitmodel/telegram_notify.py:16`
- `fitmodel/cp_breakthrough.py:108`
- `fitmodel/load_guard.py:97`
- `fitmodel/glycogen.py:557`
- `fitmodel/glycogen.py:572`
- `fitmodel/glycogen.py:617`
- `fitmodel/glycogen.py:620`
- `fitmodel/wbal_feel.py:72`
- `_bak_archive/20260716_calendar_core/qbot_qcal_cli.py:160`
- `_bak_archive/20260716_calendar_core/qbot_qcal_cli.py:161`
- `scripts/wiki_bg/runner.py:119`
- `scripts/wiki_bg/pass6.py:31`
- `docs/wiki/_work/audit_inventory.py:36`
- `qbot3/routes/gear_obs.py:601`
- `qbot3/rides/ride_report_notify.py:40`
- `qbot3/rides/ride_report_notify.py:111`
- `qbot3/rides/ride_report_notify.py:203`

</details>

<details>
<summary>Pełny spis nazw tabel qbot_v2</summary>

`activity_device`, `activity_event`, `activity_fit_raw`, `activity_lap`, `activity_record`, `app_settings`, `artifacts`, `athlete_profile`, `bak_20260928_fitmodel_daily`, `bak_20260928_modelq2_ride`, `bak_20260928_modelq2_signature`, `bak_20261008_fitmodel_daily`, `bak_20261008_modelq2_anchor`, `bak_20261008_modelq2_ride`, `bak_20261008_modelq2_signature`, `bak_20261008b_fitmodel_daily`, `bak_20261008b_fitmodel_ride_quarantine`, `bak_20261008b_modelq2_ride`, `bak_20261008b_modelq2_signature`, `bak_20261008c_fitmodel_daily`, `bak_20261008c_modelq2_ride`, `bak_20261008c_modelq2_signature`, `bak_20261014_fitmodel_daily`, `bak_20261014_modelq2_anchor`, `bak_20261014_modelq2_ride`, `bak_20261014_modelq2_signature`, `bak_20261014b_fitmodel_daily`, `bak_20261014b_modelq2_ride`, `bak_20261014b_modelq2_signature`, `bak_20261014c_fitmodel_daily`, `bak_20261014c_modelq2_ride`, `bak_20261014c_modelq2_signature`, `bak_20261015_fitmodel_daily`, `bike_odometer`, `bike_sensor`, `blood_pressure`, `body_circumference`, `body_daily`, `body_daily_backup_20260531_2002`, `body_measurements`, `body_measurements_backup_20261013`, `body_measurements_staging`, `brokul_delivery_days`, `brokul_meals`, `brokul_notify`, `calendar_day_route`, `calendar_entry`, `calendar_reminder_fired`, `cda_crr`, `cda_xss_calib`, `change_log`, `cp_breakthrough`, `cp_bt_checked`, `daily_summary`, `days`, `ecg_recording`, `energy_daily`, `fitmodel_daily`, `fitmodel_daily_v1_backup`, `fitmodel_ingest_status`, `fitmodel_ingest_status_bak_20261004`, `fitmodel_param`, `fitmodel_qext2_ride`, `fitmodel_ride_buckets`, `fitmodel_ride_quarantine`, `fitmodel_segment`, `fitmodel_segment_bak_20260707`, `fitmodel_segment_bak_20261004`, `fitmodel_surface_cal`, `fitmodel_wbal_ride`, `fitmodel_wbal_ride_v1_backup`, `fitmodel_week_plan`, `fitmodel_xert_bench`, `food_analysis`, `food_catalog`, `food_day`, `food_dish_ratings`, `food_entries`, `food_favorites`, `food_items`, `food_taste_profile`, `food_week_ai`, `food_weekend_plan`, `fueling_events`, `garmin_daily_raw`, `garmin_workout_write_audit`, `gear_cassette`, `geo_rev_cache`, `google_places_cache`, `google_places_usage`, `heart_ai`, `hr_at_power`, `hr_xss_calib`, `hydration_events`, `incident_tickets`, `intake_items`, `intake_logs`, `karoo_live`, `komoot_seen_tours`, `load_guard`, `lthr_daily`, `lthr_ride`, `lthr_window`, `mail_group`, `mail_group_member`, `meal_log_items`, `meal_logs`, `meal_templates`, `meteo_point_cache`, `meter_phys`, `modelq2_anchor`, `modelq2_ride`, `modelq2_signature`, `modelq2_xert_bench`, `notif`, `nutrition_daily_summary`, `nutrition_day_plan_meals`, `nutrition_day_plans`, `outfit_lessons`, `planer_pogoda_cache`, `planer_route_opis`, `planer_route_opis_dni`, `planer_route_tlo`, `planned_load_daily`, `pogoda_alert`, `pogoda_eps_verif`, `pogoda_obs`, `pogoda_prog`, `pogoda_radar_verif`, `pogoda_stacja`, `power_meter_guard`, `projects`, `push_sub`, `qbot_artifacts`, `qbot_doc_write_audit`, `qbot_import_runs`, `qbot_memory`, `qbot_nutrition_daily`, `qbot_planning_facts`, `qbot_plans`, `qbot_sleep_daily`, `qbot_wellness_daily`, `qbot_wellness_notes`, `qext2_aero_record`, `qext2_cassette_report`, `qext2_settings`, `real_load_guard_log`, `report_mail_recipients`, `report_schedule`, `report_schedule_sent`, `ride_cassette`, `ride_cda`, `ride_climb_efforts`, `ride_companion`, `ride_drivetrain`, `ride_frames`, `ride_heat_drift`, `ride_hrr`, `ride_invite`, `ride_p_at_hr`, `ride_power_curve`, `ride_report_ask`, `ride_report_data`, `ride_report_data_v1_backup`, `route_admin_cache`, `route_analysis_run`, `route_artifacts`, `route_attraction_layer`, `route_attraction_run`, `route_axis_segments`, `route_base`, `route_climb_events`, `route_day_pack`, `route_elevation_samples`, `route_frame_weather`, `route_frames`, `route_intro`, `route_kit`, `route_landcover_layer`, `route_outfit`, `route_outfit_fav`, `route_parse_results`, `route_poi_layer`, `route_poi_meta`, `route_poi_prefs`, `route_point_geo_cache`, `route_precompute_jobs`, `route_report_snapshots`, `route_shade_layer`, `route_stage_lineage`, `route_surface_context`, `route_surface_layer`, `route_surface_profiles`, `route_surface_segments`, `route_wind_clim`, `season_ai`, `sleep_daily`, `sleep_wake_label`, `spo2_daily`, `start_trip`, `strava_activity`, `strava_auth`, `strava_gear_map`, `strava_photo`, `strava_publish`, `strava_taste`, `supplement`, `supplement_dose`, `supplement_log`, `threshold_sync_log`, `tool_calls`, `trainer_auto_cache`, `trainer_change`, `trainer_day`, `trainer_exercise`, `trainer_exercise_user`, `trainer_goal`, `trainer_lab`, `trainer_notify_log`, `trainer_rating`, `trainer_rule`, `trainer_session`, `trainer_settings`, `trainer_workout`, `training_sessions`, `trip_story`, `ui_prefs`, `wbal_feel`, `web_device_auth_requests`, `web_sessions`, `wellness_daily`, `worldcover_classes`, `wyprawa_report`, `wyprawa_rsvp`, `xert_profile_snapshots`

Lista jest zgodna z 235 nazwami zwróconymi przez odczyt `information_schema` z 18.10.2026.

</details>

> DO SPRAWDZENIA: crontab użytkownika `qbot` jest nieczytelny dla bieżącego konta. Uzupełnić porównanie po uzyskaniu odczytu.

## Wpływa na / Zależy od

- **Wpływa na:** spis haseł, mapę serwisu i kolejne aktualizacje wiki.
- **Zależy od:** odczytanych plików systemowych, kodu, stron publicznych, spisu haseł oraz schematu bazy z chwili audytu.

## Powiązane hasła

- [Automaty QBota](system/automaty.md)
- [Strony WWW](system/strony-www.md)
- [Narzędzia Alberta](albert/narzedzia.md)
- [Mapa serwisu](mapa-serwisu.md)
- [Rzeczy do sprawdzenia](_DO_SPRAWDZENIA.md)

## Zrodla

- `_work/audit_inventory.py` — skrypt spisujący timery, crontab, wywołania, ścieżki, narzędzia i tabele.
- `_indeks.json` — tytuły, tekst i źródła haseł przed dodaniem czterech nowych stron.
- `/etc/systemd/system/qbot*` — pliki timerów i usług.
- `/var/spool/cron/crontabs/*` — crontab roota; plik użytkownika `qbot` był nieczytelny.
- `/opt/qbot/app/qbot_web.py`, `/opt/qbot/app/qbot_api.py` — deklaracje ścieżek HTTP.
- `/opt/qbot/app/qbot3/tool_registry.py` — lista 84 narzędzi.
- `information_schema.tables` — nazwy tabel w schemacie `qbot_v2`.
