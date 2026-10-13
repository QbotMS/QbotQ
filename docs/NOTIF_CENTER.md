# QBot — Centrum powiadomień (dzwonek)

_Utworzono 2026-10-08. Żywy system wygrywa — weryfikuj na kodzie._

## Co to jest
Dzwonek w prawym górnym rogu obok przycisku Wyloguj (od 2026-10-08; wcześniej w lewym menu pod ☰). Pomarańczowa plakietka z liczbą = nieprzeczytane.
Na telefonie ta sama plakietka jest na pływającym przycisku menu. Klik → panel wysuwany obok dzwonka
(komputer: tuż przy menu, na wysokości dzwonka; telefon: pełna wysokość z lewej). Zamykanie panelu: × w nagłówku, Esc, klik obok,
ponowny klik w dzwonek. Otwarcie panelu oznacza wszystko jako przeczytane. Telegram działa jak dotąd — dzwonek go nie zastępuje.

## Warstwy
- Tabela `qbot_v2.notif` (`sql/notif_v1.sql`): key (unikalny), kind, title, body, url, action (JSONB), read_at, resolved_at.
- Logika: `qbot_notif.py` — `push()` (zmiana treści lub ponowne otwarcie ⇒ nieprzeczytane), `resolve()`, `sync_live()`, `listing()`, `mark_read()`, `dismiss()`.
- API (`qbot_web.py`): `GET /api/notif` (stan na żywo przeliczany najwyżej co 60 s), `POST /api/notif/read` ({ids} albo {} = wszystkie), `POST /api/notif/dismiss` ({id}).
- Front: `nav.js` (`qBell`, odpytywanie co 2 min i przy powrocie na kartę), style w `nav.css` (sekcja CENTRUM POWIADOMIEN). Statyki poza repo, kopia w web_public/.

## SETUP > Powiadomienia (2026-10-08)
- Strona `/setup.html` (zębatka — najniższa pozycja menu, `nav.js` foot). Zakładka **Powiadomienia**: checklista 14 rodzajów w grupach
  Jazdy / Pogoda / Trasy / Trener / Dane / System, z „zaznacz/odznacz wszystkie” w grupie; zapis od razu.
- Katalog rodzajów: `qbot_notif.SOURCES` (id, grupa, nazwa, opis, prefiksy kluczy) + `source_of(key)`. Nowe źródło = dopisz wiersz do SOURCES.
- Zapis: `qbot_v2.app_settings` (`sql/app_settings_v1.sql`), klucz `notif.enabled` = {id: bool}; brak wpisu = włączone.
- API: `GET/POST /api/setup/notif`. Wyłączone rodzaje są odfiltrowane w `listing()` (lista i plakietka); dalej się zapisują i są w Historii.
- Kolejne zakładki SETUP: `<button data-t>` w `#tabs` + `<section data-p>` w setup.html.

## Usuwanie i historia (2026-10-08)
- **×** przy każdej pozycji = usuń z listy (`POST /api/notif/dismiss`): ustawia `dismissed_at` + `resolved_at`, wiersz ZOSTAJE w bazie.
  Usunięta pozycja nie wraca, dopóki nie zmieni się jej treść (np. nowe zadanie przy rowerze, inny licznik logowań) — wtedy pojawia się znów jako nowa.
- **Historia** (przycisk w nagłówku panelu, `GET /api/notif/history?days=90`): wszystkie pozycje z 90 dni ze statusem:
  aktywne / nowe, usunięte DD.MM HH:MM, załatwione samo DD.MM HH:MM, wygasło (zdarzenie starsze niż 14 dni).
- Kolumna `dismissed_at`: `sql/notif_v2.sql`. Nic nie jest kasowane fizycznie.

## Dwa rodzaje pozycji
1. **Stan na żywo** (`live:*`) — liczony przy odczycie, sam znika gdy warunek ustąpi:
   - `live:rower:<bike_id>` — otwarte zadania przy rowerze (garage.db `bike_task`), przycisk „Zrobione”, link do jazdy;
   - `live:trasa:<id>` — trasy czekające na potwierdzenie w Telegramie (`telegram_pending_actions`, status pending, nieprzeterminowane);
   - `live:dane:sen|waga` — brak świeżych danych > 3 dni (`qbot_wellness_daily.sleep_score`, `fitmodel_daily.weight_kg`).
   - `live:ubior:<ride_key>` — jazda rowerowa z ostatnich 3 dni bez wpisanego ubioru/roweru (garage.db `ride_gear_log`, bez slotów pogody `_temp_*`, `_precip`);
   - `live:pogoda:<session_id>` — zaplanowana jazda rowerowa Trenera dziś/jutro + prognoza Trenera (`qbot_trener_engine.forecast`, punkt domowy): deszcz > 0,5 mm/h albo ≥ 60%, wiatr > 8 m/s albo porywy > 14 m/s, odczuwalna ≤ 0 °C, burza, śnieg. Przeliczane najwyżej co 30 min (błąd prognozy → ponowna próba za 5 min);
   - `live:system:svc:<usługa>` — długo działająca usługa (qbot-api, -web, -mcp-bridge, -dev-mcp, -qlab-server) nie jest active, albo dowolna `qbot*` w stanie failed (np. backup z timera);
   - `live:system:dysk` — zajętość / ≥ 90%;
   - `live:demo:<id>` — prośba o dostęp demo (QR) czeka na zatwierdzenie.
2. **Zdarzenia** (`trener:*`) — kopia wiadomości Trenera: plan tygodnia, rozliczenie, zmiana planu z Kalendarza, przeliczenie po wykonaniu (`qbot_trener_notify._nc`). Widoczne 14 dni, można „ukryj”.
   Inne zdarzenia (krok 2): `jazda:<ride_key>` „Nowa jazda” (jazdy rowerowe z ostatnich 3 dni, czas = start jazdy),
   `system:demo:<id>` „Wejście demo przez QR”, `system:restart:<usługa>:<NRestarts>` samoczynny restart usługi,
   `system:login:<RRRR-MM-DD>` „Nieudane logowania dziś: N” (z `qbot_web._login_record_failure`; testy: `QBOT_NOTIF_DISABLE=1`).
   `push(..., at=)` ustawia czas zdarzenia zamiast czasu wykrycia.

## Jak dodać nowe źródło
Zdarzenie: `import qbot_notif as NF; NF.push(cur, "<modul>:<id>", "<kind>", tytul, tresc, url)` + commit.
Stan na żywo: dopisz funkcję `live_*` i jej wywołanie w `sync_live` (osobny try — błąd jednego źródła nie blokuje reszty).
Ikony rodzajów: `KIND_ICON` w `qbot_notif.py`.

## Krok 2 (zrobione 2026-10-08)
Jazdy, pogoda przed jazdą, system — jak wyżej. Analiza AI jazdy nie jest osobnym powiadomieniem (generuje się na żądanie).

## Testy
`tests/test_notif.py` (4), `tests/test_notif_step2.py` (4), `tests/test_notif_setup.py` (2).

## Powiadomienia na komputerze — Web Push (2026-10-13)
Pozycje dzwonka trafiają też jako powiadomienia systemowe (Centrum powiadomień na Macu; Safari / Chrome). Etap 1: komputer.
iPhone później — wymaga dodania strony do ekranu początkowego (iOS 16.4+); wysyłka z serwera zostaje ta sama.
- **Stan na żywo liczony w tle**: pętla w `qbot-web` (`_push_loop`, wątek startowany w `@app.on_event("startup")`) co 60 s robi
  `qbot_webpush.tick()` = `sync_live()` + wysyłka. Wcześniej `sync_live` był wołany WYŁĄCZNIE przy otwarciu dzwonka (`GET /api/notif`).
  Wspólna blokada `_NOTIF_LOCK` — pętla i odczyt dzwonka nie liczą naraz. Wyłączenie pętli: `QBOT_WEBPUSH_LOOP=0` (albo `QBOT_NOTIF_DISABLE=1`).
- **Co idzie**: każda pozycja nowa albo ze zmienioną treścią (`notif.pushed_at < updated_at`), nieprzeczytana, niezamknięta, nieusunięta,
  rodzaj włączony w SETUP > Powiadomienia. Raz na wszystkie zapisane urządzenia. Zdarzenia z innych procesów (Trener z crona) też — pętla czyta tabelę.
  Więcej niż 5 naraz → 4 osobno + 1 zbiorcze. `tag` = klucz pozycji (nowa wersja zastępuje starą w Centrum powiadomień).
- **Start bez zalewu**: przy pierwszym `ensure()` wszystkie istniejące pozycje dostały `pushed_at` (znacznik `app_settings` `webpush.init`).
- **Ślad pracy pętli**: `app_settings` `webpush.tick` = {at, items, ...}; SETUP pokazuje „Serwer sprawdzał: HH:MM”.
- **Pliki**: `qbot_webpush.py` (tabela `qbot_v2.push_sub`, kolumna `notif.pushed_at`, VAPID, wysyłka `pywebpush`),
  `/opt/qbot/web/public/sw-push.js` (service worker; publiczny w bramce logowania — sam skrypt, bez danych), SETUP > Powiadomienia
  (ramka „Powiadomienia na tym komputerze”: Włącz / Wyślij test / Wyłącz).
- **API**: `GET /api/push/key` (klucz publiczny, urządzenia, ostatni obrót pętli), `POST /api/push/subscribe|unsubscribe|test` (tylko właściciel, nie demo).
- **Klucz VAPID**: `/opt/qbot/app/.env.webpush.pem` (poza gitem, 600, tworzony przy pierwszym użyciu; `QBOT_VAPID_PEM` nadpisuje). Zmiana klucza = urządzenia trzeba włączyć ponownie.
- **Wygasłe subskrypcje** (404/410 z usługi push) usuwane automatycznie; inne błędy w `push_sub.last_err`.
- **Zależność**: `pywebpush` w `.venv` (instalacja: `runuser -u qbot -- /opt/qbot/app/.venv/bin/pip install pywebpush`).
- Testy: `tests/test_webpush.py` (5).

### Wygląd + QBot jako aplikacja (2026-10-13, etap 1b)
- Safari na Macu pokazuje w powiadomieniu ikonę Safari i adres strony — strona nie może tego zmienić. Zmienia to dopiero
  **QBot jako aplikacja**: Safari > Plik > Dodaj do Docka (macOS 14+). Wtedy powiadomienia mają ikonę i nazwę QBot.
  W aplikacji z Docka powiadomienia trzeba włączyć OSOBNO (Setup > Powiadomienia > Włącz) — to osobna „przeglądarka”.
- Pliki: `manifest.webmanifest` (nazwa QBot, start /, standalone, ikony), `icon-192.png`, `icon-512.png`, `apple-touch-icon.png`
  (wyrenderowane z `favicon.svg`, 12% marginesu na czarnym tle). Linki do nich wstrzykuje `nav.js` w `<head>` każdej strony.
  Wszystkie cztery są publiczne w bramce logowania (przeglądarka pobiera je bez ciasteczka).
- Teksty: tytuł = tytuł pozycji dzwonka BEZ emoji (ikonę daje system), treść = opis pozycji. Ponad 5 naraz → „Jeszcze N nowych w dzwonku”.
- Ten sam manifest i ikona posłużą do iPhone'a (TODO [WEBPUSH-IPHONE]).
