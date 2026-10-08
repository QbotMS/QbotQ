# Dostep DEMO do qbot-web przez QR (2026-10-07)

Kod: `qbot_web_auth.py` (przeplyw, polityka), podpiecie w `qbot_web.py` (`_webauth_guard`, `_owner_user`,
`_current_user`, router przed `app.mount`). Tabele: `sql/web_demo_auth_v1.sql`
(`qbot_v2.web_device_auth_requests`, `qbot_v2.web_sessions`). Testy: `tests/test_web_demo_auth.py`,
`tests/test_webauth_hardening.py`. Analiza wyjsciowa: dokument „Albert.cytr.us — ocena logowania i dostepu
demonstracyjnego przez QR” (2026-10-07).

## Decyzje wlasciciela (2026-10-07)
- Zakres demo: podglad WSZYSTKICH modulow, zero zapisow. AI (Albert) tylko zapisane analizy — bez przeliczania.
- Sesja demo 1 h bezwzglednie, bez przedluzania. QR wazny 2 min (+60 s na odbior po zatwierdzeniu).
- Wylaczone z demo: zaproszenia gosci (linki-przepustki), adresy/grupy mailowe, RSVP, harmonogramy wysylek,
  towarzysze jazd (dane innych osob), Strava poza statusem, Komoot/Hammerhead, PDF-y, funkcje wolajace
  AI lub platne Google przy braku cache (pogoda planera, noclegi, atrakcje, opis, tlo) oraz parametry
  wymuszajace przeliczenie (`rebuild`, `fresh`, `force`, `refresh`, `recompute`, `regen*`).

## Przeplyw
1. Komputer: `POST /auth/device/start` -> `{id, code, approve_path}` + ciasteczko `qbot_devreq`
   (HttpOnly, Secure, Path=/auth/device) z sekretem przegladarki. QR prowadzi do `approve_path`; QR NIE
   zawiera sekretu odbioru.
2. Telefon (pelna sesja `qbot_session`): `GET /auth/device/approve?id=` pokazuje kod porownawczy, konto,
   zakres, czas, urzadzenie; `POST /auth/device/decide` (token CSRF = HMAC z wartosci podpisu i ciasteczka).
3. Komputer odpytuje `GET /auth/device/status` (min. 1 s), po APPROVED `POST /auth/device/claim`:
   jedna atomowa operacja UPDATE ... WHERE status='APPROVED' + INSERT sesji (`request_id` UNIQUE) ->
   ciasteczko `qbot_demo` (losowy token; w bazie tylko sha256).
4. Kazde zadanie demo: walidacja w bazie (cache 5 s, czyszczony przy uniewaznieniu), wlasciciel musi
   nadal istniec w `.env.webauth`, blad bazy = odmowa.
5. Koniec: `POST /auth/demo/logout` (komputer) albo `POST /api/auth/sessions/revoke` `{id|'all', csrf}`
   (wlasciciel; lista + csrf z `GET /api/auth/sessions`).

## Polityka demo (qbot_web_auth.demo_allows) — DOMYSLNIE ZAKAZ
- Tylko GET/HEAD (+ `POST /auth/demo/logout`). Strony statyczne dozwolone poza `DEMO_BLOCKED_PAGES`.
- `/api/*` WYLACZNIE z listy `DEMO_ALLOWED_API_GET`. NOWY endpoint jest w demo zablokowany, dopoki ktos
  swiadomie nie dopisze go do listy (po sprawdzeniu, ze GET niczego nie zapisuje i nie wola AI/Google).
- `/auth/*` zablokowane dla demo (demo nie zatwierdza urzadzen ani nie zarzadza sesjami).
- Pelne ciasteczko wlasciciela ma pierwszenstwo przed demo.
- `_current_user()` zwraca wlasciciela takze dla demo (odczyt danych); `_owner_user()` — tylko pelna sesja.
  Ochrona zapisow opiera sie na bramce: wszystkie metody inne niz GET/HEAD sa dla demo odrzucane (403).

## Ograniczenia
- Uniewaznienie blokuje kolejne zadania; nie cofa pobranych plikow ani zrzutow ekranu.
- Limity (oczekujace zadania, odpytywanie, proby logowania) sa w pamieci procesu — restart je czysci.

## Interfejs
- `/login`: przycisk „Dostęp tymczasowy przez telefon” (`qbot_web_auth_ui.LOGIN_QR_HTML/SCRIPT`): QR (SVG z
  biblioteki `qrcode`), kod porownawczy, odliczanie, odpytywanie co 2 s, automatyczny odbior i przejscie na `/`.
- QR prowadzi na `QBOT_WEB_PUBLIC_URL` (domyslnie https://albert.cytr.us) + `/auth/device/approve?id=`.
- `nav.js` (`qAuthBadge`): w demo pomaranczowa plakietka „Tryb demo — tylko podgląd · zostało N min” z
  przyciskiem Wyloguj; u wlasciciela link „Dostępy tymczasowe” -> `/auth/sessions` (lista + konczenie).

## Odczyt bez skutkow ubocznych
- `qbot_trener_api.week_get` dla demo pomija porzadki zapisujace (`calendar_changed`, `_ensure_horizon`,
  `_match_done`) — wykryte przejsciem przegladarki jako demo (licznik zapisow `trainer_session` +1).
- Statyki: demo nie pobiera `*.bak*` ani plikow/katalogow zaczynajacych sie od `_`.
- Weryfikacja zmian: przejscie wszystkich stron jako demo + porownanie `pg_stat_user_tables` (qbot_v2)
  przed/po; dopuszczalna jest tylko pamiec podreczna pogody (`meteo_point_cache`, dane publiczne).

## Strona startowa (2026-10-07)
- `/login` = wizytowka serwisu (`qbot_web_landing.py`): mapa topograficzna (poziomice marching squares z
  wirtualnego terenu), trasa rysowana przy wejsciu, profil wysokosci we wkladce, legenda modulow, tryb nocny
  (prefers-color-scheme), prefers-reduced-motion = stan koncowy bez animacji.
- „Zaloguj” otwiera `<dialog>` z formularzem (te same pola, `next`, komunikaty `err`) i QR. Przy `err` okno
  otwiera sie samo. Strona bez zewnetrznych zasobow (przed zalogowaniem statyki sa niedostepne).
- Tresci publiczne: wylacznie ogolny opis modulow, bez danych uzytkownika.
- v2 (2026-10-07, po uwagach wlasciciela): styl strony Start (index.html: Big Shoulders Display / Hanken
  Grotesk / JetBrains Mono, akcent #e8742a, tryb nocny). Hero = 3 zdjecia z jazd (przenikanie + powolny najazd),
  kafle modulow na zdjeciach (odslaniane przy przewijaniu), animowany profil trasy z paskiem nawierzchni.
  Mapa topograficzna z v1 usunieta.
- Zdjecia: `/opt/qbot/web/landing/` (hero-1..3, m-*.jpg) = wybrane 'liked' z qbot_v2.strava_photo, ponownie
  zakodowane BEZ EXIF/GPS. Publiczne WYLACZNIE przez `/landing/` (wyjatek w bramce + osobny StaticFiles).
  Podmiana zdjecia = nowy plik o tej samej nazwie, zawsze bez metadanych.
- v3 (2026-10-07): tlo hero = film `hero.mp4` (1080p, ~9,4 MB) / `hero-m.mp4` (720p, ~3,1 MB, ekrany <=820 px),
  kadr `hero-poster.jpg`; przy prefers-reduced-motion tylko kadr. Montaz 11 ujec (~30,5 s, 10 MB / 3,9 MB; w tym 3 statyczne krajobrazy z postojow i krotkich plikow; cz-b, bez dzwieku,
  -map_metadata -1) z nagran DJI Osmo Nano 'Sycylia 2026' (Pulpit wlasciciela). Ujecia wybrane z danych 1 Hz
  (zjazdy/podjazdy dopasowane czasem nagrania; czas: activity_record.ts AT TIME ZONE 'Europe/Warsaw' = UTC)
  i z klatek podgladowych (miejscowosci); bez twarzy i tablic. Ziarno filmowe = nakladka CSS `.grain` (SVG
  feTurbulence), nie w pliku wideo. Skrypty: Mac ~/Downloads/qbot_frames/{extract.sh,build_video.sh}
  (ffmpeg z Homebrew, uruchamiane przez kolejke DC; build_video.sh sam wysyla pliki scp na serwer).
- Haslo hero: 'Tylko' + rotujaca linia co 3,6 s: nowe kwadraty / najlepsze trasy (wlasciciel) + prawdziwy
  szuter / twarde dane / dobra pogoda (propozycje). Lista HASLA w skrypcie qbot_web_landing.py.
- Adresy filmu i kadru dostaja ?v=<data pliku> (qbot_web_landing.render) - nowy montaz wysylany przez
  build_video.sh jest widoczny od razu, bez restartu i bez starej kopii w pamieci przegladarki.
  build_video.sh tworzy tez out/check.jpg (klatka ze srodka kazdego ujecia) do kontroli montazu.
