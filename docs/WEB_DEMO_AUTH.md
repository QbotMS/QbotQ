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
- Interfejs (przycisk QR na /login, rysowanie QR, plakietka demo i wylogowanie w nav.js, ekran sesji)
  — osobny etap; rysowanie QR wymaga biblioteki `qrcode` w .venv.
