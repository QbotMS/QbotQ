# GEAR-OBS — obserwacje przy rzeczach z Garażu (AI)

Decyzja: docs/DECISIONS.md, wpis 2026-10-18 (GEAR-OBS). Kod: `qbot3/routes/gear_obs.py`, front: `/opt/qbot/web/public/gear-obs-ui.js`.

## Po co
Uwagi Michała o ubiorze („wszystko przeciekło, buty w miejscu Boa”) nie mogą sztywno przestawiać oceny z audytu (0/1).
Jedno zdarzenie to poszlaka z możliwymi innymi przyczynami. AI zbiera obserwacje przy rzeczach, waży je i pisze „co wiemy”.
Audyt (`gear.a_*`) zostaje bazą — zmienia się wyłącznie po zatwierdzeniu propozycji przez Michała.

## Przepływ
1. **Źródła uwag**
   - po jeździe: „W czym jechałem” w raporcie jazdy (`/api/ride-gear/save`, slot `_uwagi`) → `submit_ride_note(ride_key)`;
     ta sama treść = bez zmian, inna = nowy rozbiór, pusta = obserwacje znikają;
   - przed jazdą: „Uwagi do AI” w Analizie trasy (`/api/report/outfit/note`) → `submit_route_note(route_id, date, text)`.
2. **Rozbiór (AI, w tle)** — `process_note`: obserwacje tylko dla rzeczy z kontekstu (komplet jazdy / propozycja ubioru):
   aspekt, wynik, opis, inne możliwe przyczyny, waga (słaba/średnia/mocna). Preferencje i polecenia NIE są obserwacjami
   (obsługują je wnioski `outfit_lessons`). Pogoda z danych bywa błędna — przy sprzeczności AI wierzy Michałowi.
   Niejasne → JEDNO pytanie (`status=pytanie`), odpowiedź `/api/gear-obs/answer` → ponowny rozbiór.
3. **Co wiemy** — `refresh_knowledge(gear_id)`: 1–2 zdania dla doradcy + pewność (niska/średnia/wysoka).
4. **Propozycja zmiany audytu** — tylko gdy ≥2 obserwacje tego samego aspektu, nie wszystkie słabe (pilnowane w kodzie),
   pola: a_rain, a_wind, a_fit, a_status, a_temp_min, a_temp_max, a_wet_cold; wartości z `qbot_garage_audit_api.OPTIONS`.
   Nowa propozycja → Centrum powiadomień (`qbot_notif`, klucz `gearobs:prop:<id>`, kind `ubior`) + Telegram (link do Garażu).
   Decyzja w Garażu: Zatwierdź (zmiana pola, `a_src` + „GEAR-OBS data”, `a_date`) / Odrzuć (AI nie wraca z tą samą
   propozycją bez nowych obserwacji). Po decyzji lub wycofaniu propozycji powiadomienie się zamyka.
5. **Doradca ubioru** — `outfit_advisor.kandydaci` dodaje pole `co_wiemy`; zasady: docs/OUTFIT_ADVISOR_RULES.md sekcja 12.

## Dane (garage.db)
- `gear_obs_note` — uwaga, źródło (`po_jezdzie` / `przed_jazda`), ref (ride_key / route|data), kontekst, pytanie/odpowiedź,
  status (`przetwarzanie | gotowa | pytanie | bez_obserwacji | bez_rzeczy | blad`).
- `gear_obs` — obserwacje (note_id, gear_id, data, aspekt, wynik, opis, inne_przyczyny, waga).
- `gear_knowledge` — co_wiemy, pewność, liczba obserwacji, propozycja (JSON) i jej status (`czeka | zatwierdzona | odrzucona`).

## API (qbot_web.py)
- `GET /api/gear-obs/note/{id}` — stan rozbioru uwagi + obserwacje (okienko po zapisie).
- `POST /api/gear-obs/answer` `{note_id, answer}` — odpowiedź na pytanie albo wyjaśnienie/poprawka.
- `GET /api/gear-obs/gear/{gear_id}` — sekcja w Garażu.
- `POST /api/gear-obs/proposal` `{gear_id, decision: zatwierdz|odrzuc}`.

## Front
`gear-obs-ui.js` (raport-jazdy.html, raport-trasy.html, garaz.html):
- okienko w prawym dolnym rogu po zapisie uwagi (`QGearObs.watch(note_id)`): postęp → pytanie albo zapisane obserwacje + „Dopisz wyjaśnienie”;
- Garaż, okno rzeczy: sekcja „Obserwacje z jazd (AI)” NAD „Oceną z audytu”, układ poziomy (co wiemy + propozycja obok siebie,
  obserwacje jako przewijany rząd kart), link „popraw” przy każdej obserwacji.

## Utrzymanie
- Jednorazowy przebieg starych uwag: `scripts/gear_obs_backfill.py start` (odłącza się, wynik w /opt/qbot/artifacts/gear_obs_backfill.txt).
- Rozbiór i „co wiemy” idą wątkami w procesie qbot-web — po restarcie w trakcie uwaga zostaje w `przetwarzanie`;
  ponowny zapis uwagi albo odpowiedź uruchamia ją znowu.
