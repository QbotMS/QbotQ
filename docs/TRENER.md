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
4. **Bilans, statusy celów, Czas, pogoda auto, badania** (ZROBIONE 2026-09-23): `qbot_trener_stats.py`,
   migracja `sql/trainer_v3.sql`, testy `tests/test_trener_stats.py`. Szczegóły w sekcji „Etap 4” niżej.
5. **Telegram, Albert, zestawy ćwiczeń** (ZROBIONE 2026-09-23) — sekcje „Etap 5” i „Zestawy ćwiczeń” niżej. **Serwis zamknięty 2026-09-23.**

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

## Etap 4

- `GET /balance` — bilans z okna `food.smooth_days` (dom. 14): `food.source` 0 = logi, 1 = logi gdy ≥70% dni z wpisami
  (inaczej waga), 2 = waga. Logi = SUM(`intake_items.kcal`) per `intake_logs.date`; wydatek = `energy_daily.total_kcal_eff`
  (fallback `total_kcal`, bez dni `partial`); z wagi = nachylenie MNK wagi (`fitmodel_daily.weight_kg`) × 7700 kcal/kg.
  Cel tempa: z aktywnego celu wagi (kg do terminu) albo suwak `food.loss_kg_wk`. + seria 30 dni (waga, średnia 7 d).
- `GET /goals/status` — per cel: `level` g/y/r/n, tekst, wiersze (ma/potrzeba/uwaga), `progress`.
  Wyprawa: km/dzień i m/dzień = najlepsza średnia z serii ≥3 dni (dni ≥20 km), rekordy dnia, najdłuższa seria,
  CTL teraz vs rekord 18 mies. (bez wymyślonego „potrzebnego CTL”). Waga: śr. 7 dni, tempo 30 d vs potrzebne do terminu.
  Objętość: km/h od `date_from` vs liniowe tempo. FTP: przyrost od startu celu vs czas. Nawyk: 4 ostatnie tygodnie.
- `GET /time` — optimum h z Sezonu, limit `load.budget_h`, wolne okna tygodnia (okna treningu lub domyślne minus
  zajętości i dni rest/choroba/wyprawa), optimum per miesiąc.
- `/labs` CRUD (`trainer_lab`) — wyniki badań z datą.
- Pogoda auto: `trainer_auto_cache['weather']` liczone w tle (wątek w qbot-web, ~25 s, archiwum Open-Meteo dla
  jazd z 2 lat), odświeżane gdy starsze niż 7 dni; `/auto` zwraca wx.* z opisem. **Silnik planu używa tych wartości
  jako bazy** (ręczne nadpisania wygrywają).

## Etap 5

- **Telegram** `qbot_trener_notify.py`: cron root `*/15 * * * *` → `qbot_trener_notify.py tick` (log
  `/var/log/qbot-trener-notify.log`, zainstalowany 2026-09-23 za zgodą użytkownika). Okna: rozliczenie ndz 19:00–19:59,
  plan tygodnia pn 07:00 (bieżący) lub ndz 20:00 (następny; brakujący plan generuje się sam i zapisuje jako zaakceptowana
  zmiana `telegram_autoplan`), dzień 07:00 lub 2 h przed sesją. Deduplikacja `trainer_notify_log` (`sql/trainer_v4.sql`).
  Ustawienia `notify.*` z Kalibracji. Użytkownik = najwięcej wierszy trainer_* (bez kont z `_`), albo env `TRENER_USER`.
  Wysyłka: `qbot_config.TELEGRAM_TOKEN/CHAT_ID`, czysty tekst. `preview plan|day|review`, `send-test`.
  API `GET /notify/preview?kind=plan|day|review` (podgląd w Kalibracji → Pilnowanie).
- **Garmin: USUNIĘTE 2026-09-23** (decyzja użytkownika: treningi w Garminie zbędne). Moduł był w commicie c3d410e,
  usunięty w commicie zamykającym; historia w git.
- **Albert**: narzędzie `trainer_week` (odczyt: plan tygodnia, statusy celów, bilans) + wpis w `_SYSTEM`. Routing:
  `qbot_query_handler` intent `trainer_week` (frazy „plan treningowy”, „trener”, „co mam dziś trenować”…) PRZED
  `training_recent`, w `OPEN_DOMAIN_INTENTS` → Albert. Pusty Trener zwraca poprawny komunikat (nie błąd — inaczej pętla).

## Zestawy ćwiczeń (`qbot_trener_workouts.py`)

- **Siła = obwód na całe ciało** przy każdej sesji (6 slotów: nogi, klatka, plecy, barki, brzuch, tył ciała) + 2 ćwiczenia
  **akcentu**, który rotuje co sesję: klatka + ramiona → plecy → nogi → brzuch. Sprzęt: hantle, ławka, masa ciała (pompki,
  deski…). Numer sesji = liczba wcześniejszych sesji siłowych użytkownika (nie pominiętych) → akcent i wariant ćwiczeń
  (pula rotuje co cykl 4 akcentów). Dawkowanie wg okresu Sezonu: rt 2 rundy 40/20 s; bz 3(–4) rundy 8–12 powt.;
  bd 3 rundy + jednonóż; tp 2 rundy podtrzymania; rg/ev 1 runda; wersja minimum = 1 runda.
- **Wioślarz** wg okresu: rt spokojnie 18–22/min; bz 3 × 8′ / 2′; bd 6 × 3′ / 2′; + przypomnienie techniki.
- Gdzie widać: `GET /week` → `sessions[].details` (szczegóły treningu w UI), Telegram (poranna wiadomość dnia),
  Albert (`trainer_week` → sekcja „Zestawy ćwiczeń”). Sesja siłowa w silniku nazywa się „Siła obwodowa”.

## Dalej (poza zakresem zamkniętego serwisu)

- **Generator programu treningu** — do zaprojektowania osobno (patrz TODO).
