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
2. **Zakładka TRENER w `forma.html`** (ZROBIONE 2026-09-23): `/opt/qbot/web/public/trener.js` + `trener.css`
   (poza repo, klasy `tr-*` pod `#p-trener`). Podzakładki: Tydzień (podgląd: zajętości z wpisów + Kalendarz +
   zrobione z Garmina; plan od Etapu 3), Cele (CRUD), Dostępność (wpisy + siatka tygodnia + szablony),
   Sezon (liczony w przeglądarce z celów trip/long_ride z datą), Kalibracja (nadpisania, zapis automatyczny).
   Czas i Bilans z mockupu — w Etapie 4.
3. **Silnik planu tygodnia** (ZROBIONE 2026-09-23): `qbot_trener_engine.py` (czysta `plan_week(ctx)` + `build_context`),
   testy `tests/test_trener_engine.py`. Szczegóły w sekcji „Silnik” niżej.
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
- `GET /auto` → wartości auto liczone na żywo: `regen.sensitivity` (Spearman gotowość rano vs EF jazdy/norma 28 d;
  <20 jazd → 5), `regen.min_pct` (+ próg gotowości = percentyl z 365 dni), `regen.heavy_gap_h` (≥120 XSS:
  najmniejsze k dni, w których ≥75% powrotów HRV≥97% mediany 7 d i RHR≤mediana+1). Pogoda auto — Etap 4.

## Klucze nadpisań (`trainer_settings.overrides`)

`load.*`, `int.*`, `regen.*`, `food.*`, `wx.*`, `notify.*` (suwaki/przełączniki; przełącznik = indeks opcji),
`mix.<rower|sila|wiosl|joga|trenazer>.<1..12>` (sesji/tydz. w miesiącu), `yoga.<reguła>.on|min`, `yoga.hard_xss`,
`yoga.long_h`, `season.taper_w|regen_w|light_every_w|volume|rt_end|bz_end`. Definicje i wartości domyślne: tablica `G`
/`MIXD`/`YOGA` w `trener.js` (Etap 3 przeniesie je do Pythona jako źródło dla silnika).

Walidacja: `clean_*` w module (400 z czytelnym komunikatem). Testy: `tests/test_trener_api.py`.

## Silnik planu (Etap 3)

Kolejność w `plan_week`: (0) dni wyprawy z celów → tylko joga przed jazdą; delegacja → tylko joga hotelowa 06:30–09:00;
choroba → dzień pusty + 2 kolejne dni „brak czasu”; (1) **długa jazda** w sb/nd (lub urlop) z najlepszą pogodą i
największym oknem, ~45% minut roweru; (2) pozostałe jazdy — rozrzucone (maks. odstęp), bez dnia po ciężkiej długiej
(≥ `yoga.hard_xss`) w oknie `regen.heavy_gap_h`; zła pogoda → wioślarz (jeśli miesiąc na to pozwala) albo pominięcie;
(3) mocny akcent tylko w Budowie (`int.hard_per_week`, odstęp `int.hard_gap_days` od długiej); (4) siła — nie dzień po
dniu, nie w przeddzień długiej, chętnie w dni bez roweru; (5) wioślarz — chętnie w dni ze złą pogodą; (6) joga wg reguł
(dzień po długiej: 40′ gdy wolny, 15′ gdy inny trening; dni bez treningu 30′); (7) min. dni wolnych; (8) „brak czasu”
i gotowość dziś < próg → wersje minimum.

Budżet tygodnia = godziny z Sezonu (okres, tydzień lżejszy, objętość), obcięte do `load.budget_h`, minus sesje
zachowane (ręczne / zrobione / pominięte / z przeszłych dni) i aktywności spoza planu z minionych dni.
Liczba sesji = Mix miesiąca (`mix.*` lub domyślne), korekty okresu (Regeneracja: rower ≤2, bez siły/wiosła; Taper: siła ≤1).
Okna: wpisy `pref` per aktywność; brak okna → 09:00–20:00 (dni robocze) / 07:00–20:00 (weekend, urlop).
Zajętości: wpisy `busy` + wydarzenia Kalendarza z godziną (blok 2,5 h). `flex` = trening dozwolony, ale ≤ `max_min`.
Pogoda: Open-Meteo forecast (10 dni, cache 1 h) dla „domu” = najczęstszy punkt startu z 60 ostatnich jazd; agregat
08–18: wiatr średni, porywy maks., odczuwalna min/max (`apparent_temperature`), opad maks. mm/h i szansa, pokrywa śnieżna.
Bez celów sezon = „Baza + siła” (6,5 h).

API tygodnia: `GET /week` (dopasowuje zrobione z Garmina: ten sam dzień + sport, najbliższa godzina → `done` +
`training_session_id`; zwraca `meta` z fazą, celem h, dniami (typ, zajętości, pogoda), FTP, LTHR jeśli ustawione w env
`RIDER_LTHR_BPM`, ostrzeżenia, ostatnią nierozstrzygniętą zmianę), `POST /week/generate {start}` (kasuje tylko przyszłe
sesje auto w stanie plan i układa od nowa → `trainer_change`), `POST /week/action {day, action}` (rest/del → `calendar_entry`
kind event z `note='[trener]'`, ill → kind illness, short → `trainer_day`, clear → usuwa wpisy `[trener]` z dnia i stan;
potem przeliczenie), `POST /week/undo {id}` (przywraca sesje sprzed zmiany i usuwa jej wpisy w Kalendarzu), `POST /week/accept {id}`.
Każda edycja sesji z UI (POST/PUT `/sessions`) ustawia `source='manual'` → przeliczenie jej nie rusza.
