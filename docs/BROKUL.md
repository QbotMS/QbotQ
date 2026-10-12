# Jedzenie w QBot: Diety od Brokuła + jedzenie spoza diety (od 12.10.2026)

Koncept (uzgodniony 12.10.2026): Brokuł jako baza, wszystko inne wpisywane na Telegramie, dzień zamykany
o 20:00. Kolejne etapy (do zrobienia): pas 🔥 Jedzenie, cele kroczące 99/95/90 kg + ważenie, kalibracja
i cel kcal dnia z dokładką pod trening, pasy 💪/📉, piątkowy plan weekendu. Patrz docs/TODO.md.

## Brokuł (qbot_brokul.py, qbot_brokul_meals.py)
- **Sesja**: logowanie hasłem NIEMOŻLIWE (niewidoczna reCAPTCHA – sprawdzone 12.10.2026). Michał wkleja nagłówek
  Cookie na **https://albert.cytr.us/brokul-dostep**; zapis do `.brokul_session` (600, qbot) dopiero po udanym teście.
  Ciasteczka Cloudflare są odrzucane. Powiadomień z aplikacji Brokuła nie da się czytać (iOS) – nie używamy.
- **Import co 3 h** (cron */15, `scripts/brokul_tick.py`): `/customer/diets/` → numery menu → menu
  (`/customer/diets/menu/item/<id>/`, 5 dni do przodu = do końca zamówienia) + **harmonogram dostaw**
  (`/customer/diets/day/order_item_id/<id>/` → `brokul_delivery_days`). Posiłek `pending` z dnia, którego nie ma
  w harmonogramie → `cancelled` (dzień odwołany/przeniesiony w panelu). Między importami odczyt co ≥20 min
  (podtrzymanie sesji). Sesja wygasła → jedna wiadomość z linkiem.
- **Statusy** `brokul_meals.status`: pending / eaten (+`eaten_day`) / skipped / fridge („zjem później”) /
  discarded (z lodówki wyrzucone) / cancelled. Do bilansu (`intake_*`, source='brokul', 'imported') wchodzi
  WYŁĄCZNIE `eaten`, w dniu `eaten_day` (z lodówki = dzień zjedzenia, nie dostawy). `sodium_mg = sól × 400`.
  Pierwszy realny wpis dnia usuwa szacunek z presetu tego dnia.
- **Koniec zamówienia**: 7:00–9:59, gdy do ostatniego dnia dostawy ≤2 dni → jedno przypomnienie.

## Jedzenie spoza diety (qbot_food_log.py)
- Telegram: **każdy wolny tekst i każde zdjęcie = jedzenie** (stary parser wellness/sprzęt/kalendarz + fallback
  QGPT wyłączony 12.10.2026; komendy tras „NN TAK”/„przelicz trasę” mają pierwszeństwo).
- Przepływ: surowa treść ZAWSZE najpierw do `food_entries` (idempotencja po `tg_message_id`) → dzień
  (`wczoraj`, `przedwczoraj`, dzień tygodnia, `DD.MM`; domyślnie dziś; 00:00–03:59 = wczoraj) → katalog
  (`food_catalog`: ta sama fraza + ta sama porcja potwierdzona ≥2× → „jak zwykle”, bez AI) → inaczej AI
  (Anthropic, `ANTHROPIC_MODEL`) → kcal + PEŁNE makra (bez makr wpis odrzucony). Porcja niejasna → pytanie
  z 3–4 wariantami. Nie jedzenie → pytanie „to jednak jedzenie?”.
- Potwierdzenie `✅ #id · DD.MM (dz)` + [➖ mniej ×0,25] [✔ OK] [➕ więcej] [← dzień wcześniej] [🗑 usuń].
  Wybór wariantu i OK uczą katalog. Błąd AI → wpis `failed`, ponowienie z ticka (max 4 próby), widoczny o 20:00.
- Zapis: `intake_logs` (meal_type='poza_dieta', source='telegram', 'estimated') + `intake_items` (×skala).
- **Historia Michała jako punkt odniesienia** (od 12.10.2026): przed szacowaniem QBot szuka podobnych wcześniejszych
  wpisów w `intake_items` (bez Brokuła i szacunków presetu; dopasowanie po początkach słów) i podaje je AI. Ten sam
  produkt → wartości i porcja z historii (`src` „historia DD.MM”). Powód: AI zgadywało opakowania (chrupki 40 g vs
  realne 60 g, McCrispy 630 vs 880 kcal).
- **Pewność każdej pozycji** (`conf`): ✔ pewne (historia, etykieta, znana wartość przy podanej ilości) · ~ średnie ·
  ⚠️ zgrubne (porcja i skład zgadywane). Widoczna w potwierdzeniu.
- **Poprawka pojedynczej pozycji**: odpowiedź (reply) na potwierdzenie, np. „makaron ok. 600 g” → AI zmienia tylko tę
  pozycję (`src` „poprawka”), skala wlicza się w pozycje, intake przepisany, potwierdzenie i wiadomość dnia odświeżone.

## Wiadomość dnia (20:00, także dni bez diety)
Brokuł (✅ / ❌ / 📦 później, cofnij, „wszystkie zjedzone”, „wszystkie do lodówki”), lodówka (zjadłem dziś / 🗑),
wpisy poza dietą, szybkie przyciski [✔ Nic poza dietą] [🥨 Przekąska 250] [🍫 Słodycze 350]
[🍽 Na mieście S 600 / M 900 / L 1300] (zgrubne, z makrami; poprawka ➖/➕), suma dnia z `intake_*`,
stan zamknięcia. **Dzień zamknięty** (`food_day.closed_at`, pod pas Jedzenia): brak `pending` w Brokule ORAZ
(„Nic poza dietą” albo ≥1 wpis); dzień bez dostawy: ≥1 wpis (albo „Nic” + coś z lodówki).
Wiadomość aktualizuje się po każdej zmianie (także po wpisie z Telegrama).

## Pasy, okno żywieniowe, waga vs jedzenie (qbot_food_streaks.py, od 12.10.2026)
- **🔥 Jedzenie**: dzień zamknięty (`food_day.closed_at`) do 12:00 następnego dnia. Przekroczenie kcal NIE zrywa.
- **🕗 Okno 10:00–20:00** (przed 10 tylko czarna kawa, po 20 nic) – na zaufaniu: przycisk „🕗 Okno dotrzymane” /
  „✖ Złamane” w wiadomości dnia, do 12:00 następnego dnia (`food_day.window_ok`). Wpis z porą podaną poza oknem
  (AI wyciąga `time` → `food_entries.eaten_time`, np. „o 21:30”) = złamane, chyba że klikniesz inaczej.
  **Zwolnione** (neutralne, nie rośnie i nie zrywa): trening ≥ 90 min (wykonany z `training_sessions` albo w planie
  Trenera), `calendar_entry` event_type delegacja/urlop albo tytuł z „wyprawa” (decyzja Michała 12.10.2026).
- **Mrożenie** ❄️: za każde 7 dni pasa +1 (max 2), osobno dla każdego pasa; dzień niezaliczony zużywa mrożenie.
  Dni przed 13.10.2026 (LAUNCH) bez terminu. Kamienie milowe 3/7/14/30/50/100/150/200/365 → krótka wiadomość (raz).
  Licznik w 2. linii wiadomości dnia.
- **Waga vs jedzenie** (`discrepancy`): 14 dni do wczoraj; bilans z wpisów (zamknięte dni: intake − `energy_daily`)
  vs bilans z trendu PRAWDZIWYCH ważeń (`body_measurements`, NIE `fitmodel_daily` – tam ostatni pomiar jest
  przepisywany na kolejne dni). Rozbieżność = bilans z wagi − bilans z wpisów: 🟢 ≤150, 🟡 ≤400, 🔴 >400 kcal/dz.
  Warunki: ≥80% zamkniętych dni, ≥4 ważenia rozłożone na ≥10 dni, pierwszy tydzień diety (woda) pomijany →
  pierwszy wynik najwcześniej 31.10.2026. Linia w niedzielnym rozliczeniu Trenera (`text_review`).
  Stan na 12.10.2026: tylko 5 realnych ważeń w 60 dniach – bez częstszego ważenia monitor nie ruszy.

## Przyciski (telegram_reply_processor)
`br:<e|s|p|f|d|w>:<id>[:RRRRMMDD]`, `br:<a|z>:RRRRMMDD` → qbot_brokul_meals.handle_callback;
`fd:<o|m|p|k|b|x|r>:<id>[:n]`, `qk:RRRRMMDD:<none|snack|sweet|out_*|bf_*|ln_*|dn_*|win_ok|win_no>` → qbot_food_log.handle_callback.
Przyciski nie wygasają (stan w bazie).

## Pliki
`qbot_brokul.py` (sesja, /brokul-dostep), `qbot_brokul_meals.py` (menu, harmonogram, statusy, tick),
`qbot_food_log.py` (wpisy, AI, katalog, wiadomość dnia), `scripts/brokul_tick.py` (`--init`, `--import`,
`--send DD.MM.RRRR`), `sql/brokul_v1.sql`, `sql/food_v1.sql`, `tests/test_brokul.py`, `tests/test_food_log.py`,
`qbot_web.py` (`/brokul-dostep`, `/api/brokul/session[/status]`).
