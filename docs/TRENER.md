# QBot — TRENER (sekcja Formy)

_Utworzono: 2026-09-23. Żywy system wygrywa — weryfikuj na kodzie i bazie._

## Cel

AI-wspomagany planer treningów w Formie (5. zakładka „Trener”): cele sezonu, dostępność
(zajęte / elastyczne / okna treningu z aktywnościami), kalibracja, sezon tydzień po tygodniu,
plan tygodnia z przeplanowaniem (REST / choroba / delegacja / brak czasu / przeciąganie).

Wzorzec UI (zaakceptowany mockup, dane przykładowe): `/opt/qbot/web/public/trener-mock.html`
(poza repo). Mockup NIE jest źródłem danych.

## Decyzje (2026-09-23)

- **Dane startują puste.** Niczego z mockupu nie przenosimy (cele, reguły, daty wypraw, suwaki) —
  użytkownik wprowadza sam w UI.
- **Wartości „auto” kalibracji nie są zapisywane** — liczone na żywo z bazy (czułość na gotowość,
  próg „wersji minimum” = najsłabsze X% dni, przerwa po ciężkiej jeździe z powrotu HRV/RHR,
  progi pogody z historii jazd + Open-Meteo archive). `trainer_settings.overrides` trzyma
  WYŁĄCZNIE ręczne nadpisania; klucz z wartością `null` = powrót do auto.
- **Temperatura w regułach pogody = odczuwalna z prognozy (METEO)**, nie termometr urządzenia
  (w danych rozrzut termometru vs powietrze p10–p90 ≈ −4,6…+3,8 °C).
- **Istniejący `fitmodel/week_planner.py` zostaje** jako źródło budżetu obciążenia (Etap 3), nie jest
  zastępowany.
- **Osobny moduł** `qbot_trener_api.py` (APIRouter), montowany w `qbot_web.py` jednym include
  PRZED `app.mount("/")` — żeby nie rozdmuchiwać 11-tysięcznego `qbot_web.py`.

## Etapy

1. **Fundament danych** — tabele + API (ZROBIONE 2026-09-23).
2. Zakładka TRENER w `forma.html` (+ `trener.js`, CSS z mockupu), zapis celów / reguł / kalibracji.
3. Silnik planu tygodnia (Python): sezon + mix + reguły + Kalendarz + gotowość/HRV + METEO;
   akcje po stronie serwera; REST DAY → `calendar_entry`; auto-dopasowanie zrobionych z `training_sessions`.
4. Bilans z wagi (gdy brak logów), statusy celów na bieżąco.
5. Telegram (plan pn / rozliczenie nd), wysyłka do Garmina (dziś tylko joga), narzędzie Alberta
   (+ `_SYSTEM` w tym samym commicie).

## Dane (sql/trainer_v1.sql, schemat qbot_v2, per `username`)

| tabela | co |
|---|---|
| `trainer_goal` | cele: kind trip/long_ride/volume/weight/power/habit/other, priority A/B/C, date_from/to, target jsonb, status active/paused/done/dropped |
| `trainer_rule` | wpisy tygodnia: kind busy/flex/pref, `windows` jsonb, `period` jsonb, max_min (flex) |
| `trainer_settings` | `overrides` jsonb — tylko ręczne nadpisania |
| `trainer_session` | plan dzień po dniu: sport rower/sila/wiosl/joga, start_time, dur_min, min_min (wersja minimum), zone, xss, is_long, status plan/done/skip, cut, source manual/auto, training_session_id (dopasowanie), garmin_workout_id |
| `trainer_change` | dziennik zmian (before/after, accepted) — pod Akceptuj/Cofnij |

`windows`: `[{"d":[7×0|1|2], "k":"h"|"all"|"var", "a":"HH:MM", "b":"HH:MM", "ac":[...]}]` —
d: 0 nie / 1 tak / 2 czasem; `ac` puste = wszystkie aktywności (dla `busy` zawsze puste).
`period`: `{"m":"all"}` | `{"m":"yearly","f":"DD.MM","t":"DD.MM"}` | `{"m":"once","f":"RRRR-MM-DD","t":"RRRR-MM-DD"}`.

## API (`/api/trener`, za bramką logowania, username z ciasteczka)

- `GET/POST /goals`, `PUT/DELETE /goals/{id}`
- `GET/POST /rules`, `PUT/DELETE /rules/{id}`
- `POST /sessions`, `PUT/DELETE /sessions/{id}`
- `GET /settings`, `POST /settings {"overrides":{klucz: wartość|null}}` (scalanie; null usuwa)
- `GET /week?start=RRRR-MM-DD` → tydzień pn–nd: `sessions` + `calendar` (calendar_entry nachodzące)
  + `activities` (training_sessions z tygodnia)
- `GET /health` → czy tabele istnieją

Walidacja: `clean_*` w module (400 z czytelnym komunikatem). Testy: `tests/test_trener_api.py`.
