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

## Edytor celów (2026-09-23, po uwagach użytkownika)

Inne pola dla każdego rodzaju (formularz przebudowuje się po zmianie rodzaju / aktywności):
wyprawa (od–do → dni same; trasa z QBota wypełnia km / przewyższenie z osi 50 m / przeważającą nawierzchnię; nawierzchnia
i bagaż jako przyciski; „dodaj do Kalendarza”), długa jazda (dzień + godzina startu, trasa, docelowy czas), objętość
(okres rok / sezon IV–IX / własny; aktywność; miara zależna od aktywności: rower km|h, wioślarz h|sesje, siła/joga sesje|h),
waga i FTP (tylko „do kiedy”; FTP w W albo W/kg), nawyk (aktywność; razy/tydz., rower też km/tydz., joga + minuty),
inne (opis). Walidacja dat i wymaganych pól, podpowiedzi na żywo (km/dzień, x/tydz., potrzebne tempo) i ocena realności
przed zapisem. API: `POST /goals/preview` (nic nie zapisuje), `GET /route_summary?route_id=`, `POST /goals/{id}/calendar`
(wpis kind=event, note `[trener-cel]`, ponowne wywołanie aktualizuje zamiast dublować). FTP w podglądzie nowego celu:
potrzebny przyrost %/mies. (≤1% realne, ≤2% ambitne, więcej mało realne).

## Gotowość do wyprawy — co jest „wyprawą” (2026-09-23, poprawka po 2 błędach)

Wyprawa = dni jazdy **z punktu do punktu**: start dnia ≤ 15 km od końca poprzedniego dnia jazdy **i** start przesunięty
≥ 10 km względem poprzedniego startu (dozwolony 1 dzień przerwy). Pętle z jednej bazy (Mazury 08.2025, Sycylia 08.2026)
i dni jazdy wokół domu **nie są** wyprawą. Punkt odniesienia = najcięższa wyprawa (km + przewyższenie/10); km/dzień,
m/dzień i liczba dni z TEGO SAMEGO wyjazdu. Na danych: 07.2025 (2 dni), Toskania 06.2026 (7 dni, 511 km, 7 259 m),
Opole 08.2026 (3 dni). Bez GPS — przybliżenie seriami dni. Dane dzienne: `_daily_km_up` (cache 10 min).

## Model sezonu (2026-09-23, po uwagach użytkownika)

Sezon Y = rok treningowy: **start = pierwszy dzień roboczy po świętach** (od 27.12.Y-1, bez weekendów, 1.01, 6.01) =
start **bazy**; → budowa i szczyty pod wyprawy A (taper / wyprawa / regeneracja) → **jazda sezonowa** (po ostatniej A
albo cały sezon, gdy brak A) → **roztrenowanie** (auto: 1.10 albo po regeneracji ostatniej A) → **totalny luz**
(auto: 12.12) do dnia przed startem sezonu Y+1. W luzie silnik nie planuje sesji, a Telegram milczy.
Nadpisania per sezon w zakładce Sezon: `season.<Y>.start | bz_end | roz | luz` (puste = auto). Globalne: taper, regeneracja,
tydzień lżejszy, objętość. Przykład: 2026 kończy się roztrenowaniem 28.09–13.12 i luzem 14–27.12; sezon 2027 startuje 28.12.2026.
API `GET /season` (tygodnie z okresem i sezonem, granice sezonów z flagami auto, plan km celów objętości).

Cele objętości: plan rozkładany na miesiące wg **Twojego rytmu roku** (udział km w miesiącach z 2 lat jazd), postęp
porównywany z tą krzywą (nie liniowo); przed startem okresu status mówi „start dd.mm.rrrr · teraz: <okres> sezonu Y”.
Z planu km na dany miesiąc wynika **minimalny budżet godzin** tygodnia (km/tydz. ÷ Twoja średnia prędkość ze 120 dni),
obcięty do `load.budget_h`. W edytorze okresy: sezon bieżący / następny, rok kalendarzowy, jazda IV–IX, własny.

### Ocena wyprawy — porównanie z historią (poprawka 2026-09-23)

Okna = N kolejnych dni jazdy na wyprawach (N = długość celu; gdy żadna wyprawa nie była tak długa — najdłuższe możliwe).
**km/dzień i m/dzień porównywane osobno** z najlepszym oknem dla każdej miary (zmiana przewyższenia nie może zmienić
oceny km), plus **wysiłek dzienny = km + m/10** z jednego bloku (czy oba naraz). „Gotowy” = każda miara ≥ 90% potrzeb.

## Jazdy zaplanowane w Kalendarzu (2026-09-23)

Wydarzenie Kalendarza z podpiętą trasą (`calendar_day_route`, np. z Analizy trasy / Planera) = **Twoja jazda**, nie
zajętość: silnik wstawia ją jako sesję roweru o godzinie z wydarzenia (czas ≈ km ÷ średnia prędkość ze 120 dni; km, +m,
XSS z notatki wydarzenia albo z `route_base`), odejmuje od budżetu i liczby jazd. Jeśli jest długa (≥ 0,8 × „długiej
jazdy” albo ≥ 80 km) — to ona jest długą jazdą tygodnia (silnik nie dokłada drugiej), siła nie w ten dzień ani w
przeddzień, joga po długiej — dzień później. W UI wydarzenia z godziną nie są już dublowane.

## Weryfikacja AI („silnik liczy, AI sprawdza, Ty decydujesz”, 2026-09-23)

`qbot_trener_review.py`, `POST /week/review {start, force?}`. Po „przelicz tydzień” i akcjach dnia UI sam uruchamia
weryfikację (przycisk „sprawdź plan” na żądanie). AI (QGPT_MODEL, dziś gpt-6-luna, ~12 s) dostaje zwarty kontekst: dni
(typ, zajętości, pogoda, wpisy i notatki Kalendarza, sesje planu z flagą ręczna/długa/XSS, zrobione z Garmina), faza,
cel h, gotowość, nadchodzące cele (90 dni), progi, wyniki reguł. Zwraca JSON z maks. 6 uwagami (dzień, waga, problem,
dlaczego — fakt z danych, sugestia). Walidacja (dzień w tygodniu, waga z listy, przycięcie), cache 30 min. **AI niczego
nie zmienia.** Reguły (`check_rules`) rozszerzone: siła w dniu / przeddzień długiej, dwie długie/ciężkie pod rząd,
trening w REST/choroba, kolizja z zajętością — działają też dla sesji ręcznych (silnik ich nie rusza, więc ostrzega).

## Horyzont planu i Twoje zmiany (2026-09-23)

- **Trener planuje sam bieżący + 2 kolejne tygodnie**: pusty tydzień w tym zakresie planuje się przy otwarciu
  (`_ensure_horizon` w `GET /week`, zmiana `auto_horizon` od razu zaakceptowana) i co noc 05:00–05:15 (cron tick).
  Tygodni z jakąkolwiek sesją nie przelicza sam — od tego jest „przelicz tydzień”.
- **Twoje zmiany**: dodane (`note` „dodane przez Ciebie”, usunięcie kasuje), przeniesione / zmienione (`source=manual`,
  silnik nie rusza), usunięte sesje trenera = `status=skip` + „usunięte przez Ciebie” (↺ przywróć; silnik nie wstawia
  zastępstwa tego sportu). Podsumowanie tygodnia pokazuje licznik zmian i sumy z nimi.
- **Cel godzin = widełki ±25%** (UI i AI: w widełkach bez komentarzy).
- **Ostrzeżenia** (`check_rules_detailed`): obiekty `{key, text, session_id, acked}`; „rozumiem, zostaw” zapisuje klucz
  w `trainer_session.acks` (`sql/trainer_v5.sql`) — wyciszone nie wracają w regułach ani w AI.
- **AI** dostaje gotowe sumy godzin, widełki i flagi decyzji (ręczna / usunięta / wyciszone) i ma je szanować.

## Porównanie silników — ODRZUCONE i USUNIĘTE (2026-09-23)

Użytkownik: układ tygodniowy jest lepszy, ma być spójny między tygodniami. Model bloku (poniżej, historycznie) usunięty
(commit z usunięciem; wcześniejszy 598762e). Opis zostaje jako zapis decyzji.


`qbot_trener_block.py` + `GET /compare?weeks=3` + podzakładka „Porównanie 🧪” (nic nie zapisuje). Model bloku:
XSS → CTL (τ 42) / ATL (τ 7) / TSB rano jak w ModelQ (sprawdzone na danych 22→23.09); cel formy per okres
(RAMP: baza +3, budowa +4, jazda 0, roztrenowanie −2, taper −5, regeneracja −3 CTL/tydz.) → dzienne XSS ≈ CTL + 6·przyrost;
stałe sesje (Kalendarz, wyprawy, Twoje) liczone najpierw, reszta → godziny (~45 XSS/h, obcięte do budżetu); dzień z TSB
rano < −25 = dzień luzu (bez roweru/siły/wioślarza, hook `fatigue_days` w `plan_week`); druga iteracja luzuje dni,
w które sam plan wpędziłby w zmęczenie. Haki w silniku (`target_h_override`, `fatigue_days`) są aktywne tylko,
gdy przekaże je model bloku — obecne planowanie się nie zmienia. Decyzja o podmianie: po przeglądzie użytkownika.

## Spójność tygodni (2026-09-23, decyzja: zostaje układ tygodniowy)

- **Odpoczynek po wyprawie z danych** (`trip_recovery` → cache `trip_rec`, Kalibracja „Odpoczynek po wyprawie”, klucz
  `regen.trip_rec_d`): ile dni po wyprawach (z punktu do punktu) HRV ≥ 97% normy i tętno ≤ norma+1; mediana, min. 2
  (użytkownik), max. 5. Dziś: 07.2025 → 4, Toskania → 1, Opole → 3 ⇒ **3 dni**. W tych dniach bez roweru / siły /
  wioślarza (joga ok), także przez granicę tygodni. **Dzień przed wyprawą** — wolny (joga ok).
- **Dni wyprawy liczone osobno**: cel tygodnia × (dni bez wyprawy / 7) na resztę tygodnia; dni wyprawy nie zabierają
  budżetu ani liczby jazd.
- **Rytm poprzedniego tygodnia**: silnik preferuje te same dni tygodnia dla siły, jazd i długiej jazdy.
- **Płynny przyrost**: max +`load.max_inc_pct` (7%) względem poprzedniego zwykłego tygodnia (bez wyprawy / choroby,
  nie po tygodniu lżejszym).
- **Siła 48 h także nd→pn**. „Długa jazda” tylko gdy ≥ 50% progu długiej (inaczej „Rower dłużej”).
