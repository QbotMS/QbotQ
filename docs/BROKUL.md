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

## Cel dnia, dokładka, weekend, 21:30 (qbot_food_plan.py, od 12.10.2026)
- **Model spalania** (12.10.2026, wersja 3 – trzy osobne części): **spoczynek** = BMR Garmina (`resting_kcal`, mediana 14 ostatnich pełnych dni – spada razem z wagą) + **ruch codzienny** = aktywne kcal Garmina − kcal treningów (dzień z treningiem tylko gdy każda sesja ma kcal), mediana **wg dnia tygodnia** z całej historii (do 365 dni, od 28.02.2026; 17–27 próbek/dzień, ściąganie do średniej: 2 pseudo-próbki) + **trening** = plan × kcal/h (mediana z 90 dni: (całość − BMR − ruch dnia tygodnia)/h). **Dzień bieżący** = Garmin do teraz + reszta dnia (baza × pozostała część doby + niezrobiony trening). Dzień miniony = realne `energy_daily`. Strona pokazuje rozbicie „spoczynek + ruch + trening”.
- **Budżet tygodniowy deficytu** (12.10.2026, decyzja Michała – wersja „realna”): tydzień pn–nd ma deficyt 7 × cel bilansu Trenera; **dzień lekki** (bez roweru/wioślarza ≥45 min) = deficyt 300 (Brokuł + 🍏 zaplanowana przekąska ~200 kcal ok. 16:00), **dni z jazdą** = reszta tygodnia proporcjonalnie do kcal treningu, min. 300, **maks. 900** (jazda ≥1,5 h: paliwo w trakcie). Dni minione oceniane wg planu z początku tygodnia; dziś i dni przyszłe przeliczane z realnym bilansem zamkniętych dni (tydzień się domyka). `week_deficits`, `day_deficit`, `target_for(..., day)`.
- **Bezpieczniki** (12.10.2026): choroba w Kalendarzu = dzień bez deficytu (cel = spalanie), budżet tygodnia proporcjonalnie mniejszy, linia „🤒 dziś bez deficytu” rano; 3 zamknięte dni z rzędu z deficytem >900 → rano „⚠️ za mało jedzenia – zjedz cały cel”. Niedzielne rozliczenie Trenera: linia „🍽 Jedzenie tygodnia” (zamknięte dni, śr. kcal, bilans, białko vs 160, passa). Kawy z mlekiem i błonnika świadomie nie śledzimy (decyzja 12.10).
- **Cel dnia** = spalanie − kalibracja (rozbieżność waga vs wpisy, gdy gotowa, max ±500) + cel bilansu Trenera
  (aktywny etap, 12.10: −519). Min. 1800 kcal, zaokrąglenie do 50. **Dokładka** = cel − kcal Brokuła (≥150 kcal,
  inaczej „Brokuł wystarczy”). **Paliwo na rower**: trening ≥75 min → ~50 g węgli/h po pierwszych 45 min („tu jest
  miejsce na słodkie”). Pory posiłków Brokuła pod pierwszy trening z godziną, z oknem 10–20 (trening przed 10:00 i <90 min
  → na czczo; ≥90 min → dzień zwolniony, lekko 1 h przed jazdą).
- Gdzie: blok „🍽 Jedzenie” w porannej wiadomości Trenera (dni z treningiem); linia „🎯 Cel dnia · zjedzone · zostało”
  w wiadomości dnia (20:00).
- **Piątek 7:00–9:59** (raz): plan weekendu – cel kcal, białko ~150 g, treningi, paliwo na rower; AI dopisuje, co zamawiać
  na mieście / czego unikać / co na rower + listę zakupów (liczby ustala QBot, AI ich nie zmienia).
- **21:30–21:59**: jeśli dzień nie jest zamknięty – jedno przypomnienie z licznikiem pasa.
- **Delegacja** w Kalendarzu + niepotwierdzony Brokuł → podpowiedź „📦 Wszystkie na później”.
- **Open Food Facts** (`off_refs`, search.openfoodfacts.org, ≤4 zapytania, ≤7 s): dla fragmentów z marką/sklepem
  kandydaci (na 100 g) trafiają do AI jako podpowiedź – wyniki bywają nietrafione, AI używa tylko przy zgodnej marce i nazwie.

## Pasy 💪 Trening i 📉 Redukcja (qbot_food_streaks.py)
- 💪 dzienny, od PIERWSZEGO dnia w Trenerze (12.10: 23.09.2026): brak sesji `plan` po terminie (wykonane, zmienione przyciskiem REST/brak czasu, odpoczynek) = zaliczony;
  choroba / delegacja / urlop / wyprawa = neutralnie; zdublowana sesja `plan` o nazwie wykonanej = wykonana;
  sesja `plan` po 12:00 następnego dnia = niezaliczony. Nazwa w UI: „Passa” (12.10.2026, wcześniej „Pasy”).
- 📉 tygodniowy (pn–nd, ocena po pn 12:00): ≥2 realne ważenia, ≥5 zamkniętych dni, średni bilans w widełkach
  [cel −300, cel +250] (za duży deficyt też nie jest sukcesem); ≥4 dni wyjazdu = neutralnie.
- Nagłówek wiadomości dnia: `🔥 · 🕗 · 💪 · 📉 tyg. · ❄️`.

## Wykres celu wagi (Trener → Cele)
`qbot_trener_stats.weight_chart` → `status.chart` {plan, meas, forecast, band, today}; rysuje `trener.js` `wchart()`
(SVG: plan z korytarzem ±1 kg, realne ważenia z `body_measurements`, prognoza wg tempa 30 dni, linia „dziś”).

## Wiadomości Telegram – zasada (12.10.2026, prośba Michała: mniej i krócej)
Z harmonogramu tylko DWIE wiadomości dziennie, zwięzłe (~8 linijek), szczegóły na stronie:
- **☀️ Poranek 7:00** (`qbot_trener_notify.tick` → `qbot_food_plan.morning_digest`, klucz `day:<dzień>`): treningi
  (siła/wioślarz: 1 linia + „ćwiczenia: strona Trening”), ⚖️ ważenie, 🍽 rekomendacja (cel kcal, Brokuł, dokładka,
  białko vs norma + co dołożyć, ostrzeżenia: cukry ≥90% limitu, sól >5 g; paliwo na rower, pory posiłków),
  „⏳ wczoraj otwarty”, „📅 Brokuł kończy się…” (≤2 dni), w piątek 1 linia weekendu. Przyciski Trenera tylko gdy jest trening.
- **🌙 Wieczór 20:00**: wiadomość dnia (nagłówek z passą, posiłki w 1 linii, cel, okno, 🎉 kamienie milowe jako linia, stan).
- **Niedziela 20:00**: rozliczenie tygodnia + plan tygodnia Trenera jako JEDNA wiadomość (gdy `notify.week_plan`=2).
- Usunięte osobne wysyłki: osobne „zważ się”, przypomnienie 21:30, piątkowy plan weekendu, koniec diety, kamienie milowe.
- Osobno zostają tylko reakcje i rzeczy „na teraz”: potwierdzenia wpisów, raport z jazdy, trasy, zmiany planu Trenera,
  zadania przy rowerze 2 h przed jazdą, wygasła sesja Brokuła.
- **Normy składników** (`qbot_food_plan.norms`): białko 160 g, tłuszcz min. 70 g, węgle = reszta kcal celu, cukry ≤10%
  energii, nasycone ≤10% energii, sól ≤5 g.

## Analiza (12.10.2026 – przebudowa: tygodniami, wstecz i wzorce)
- Zakładka Analiza = tydzień pn–nd (‹ ›), `GET /api/jedzenie/week?week=` (`qbot_food_api.week_analysis`):
  budżet tygodnia (plan deficytu z `week_deficits` tylko dni ≥ 10.10 vs realizacja = spalone − zjedzone w dniach zamkniętych z realnym spalaniem; ile zostało na dzień; porównanie z poprzednim tygodniem),
  dni pn–nd (plan / było / status: w planie, za mało deficytu, deficyt za mocny), składniki (białko z całego jedzenia; cukry i sól tylko z diety – jawnie),
  wzorce z 4 tygodni (odchylenie od celu: dni robocze vs weekend, z jazdą vs bez, po dobrej vs słabej nocy z `qbot_sleep_daily`; min. 3 dni w grupie), złamane okno, top produkty spoza diety wg kcal.
- Zalecenia AI tygodnia: `food_week_ai` (sql/food_v5.sql), same w ndz od 21:00 (tick Brokuła), przycisk „Przelicz”; bez wiadomości.
- „🎯 Co jeszcze zjeść” przeniesione do karty dnia (zakładka Dni, tylko dziś) – `/api/jedzenie/analysis`.

## Obwody ciała (12.10.2026)
- Tabela `qbot_v2.body_circumference` (sql/food_v4.sql): talia (wymagana), biodra, klatka, udo, ramię, szyja – cm, jeden wpis na dzień.
- Wpis: Jedzenie → **Dni** → karta dnia „📏 Obwody” (od 12.10 wieczorem; wcześniej kafelek w Bilans i waga). POST /api/jedzenie/circ; „Usuń” = usunięcie dnia.
- Widok: seria „talia cm” w wykresie Bilans i waga (grupa skład ciała, własna skala) i w Forma → Trendy → Wellness (oś cm). Wskaźnik talia/wzrost (177 cm), cel < 0,50.
- Przypomnienie: linia w porannej wiadomości tylko w poniedziałek, gdy od ostatniej talii minęło ≥ 14 dni.
- Wykres Bilans i waga: sekcje 50/50 (góra linie, dół kcal), oś kcal od 1500, trend spalania = średnia krocząca 7 dni, uchwyt wysokości (localStorage jedz_bil_h).
- Gotowość usunięta z Wellness – jest na wykresie formy (gotowość 1 noc / 3 dni), gdzie koreluje z obciążeniem.

## Strona „Jedzenie” (https://albert.cytr.us/jedzenie.html, od 12.10.2026)
Menu: pozycja „Jedzenie” (nav.js, po Treningu). Struktura `jedzenie.html`, logika `jedzenie.js`, dane i zapis
`qbot_food_api.py` (`/api/jedzenie/*`, router w `qbot_web.py`). Odczyt: `_current_user` (też demo); zapis: `_owner_user`.
- **Dni**: pasek dni (od 10.10 / 6 dni wstecz do końca zamówienia), karta dnia: Brokuł (✅/❌/📦 = ponowny klik cofa),
  lodówka, wpisy poza dietą (tabela pozycji z ✔/~/?, −25%/+25%, poprawka słowami, przeniesienie dnia, usunięcie),
  dodawanie tekstem (AI, historia + Open Food Facts; niejasna porcja → przyciski wariantów), szybkie przyciski,
  podsumowanie (zjedzone vs cel, makra, spalanie, dokładka, treningi, co brakuje do zamknięcia), okno 10–20.
- **Pasy**: 4 liczniki, postęp do kamienia milowego, mapa dni (tygodnie w kolumnach), tygodnie Redukcji + bieżący tydzień.
- **Bilans i waga**: 42 dni (słupki zjedzone – pełne = dzień zamknięty, linia spalania, cel dnia), cel wagi z wykresem
  (to samo co Trener → Cele), monitor rozbieżności, tygodnie.
- **Menu Brokuła**: dni do przodu z kcal, B/W/cukry/T/nasycone/sól, skład i alergeny, lodówka, stan sesji.
Każda zmiana ze strony odświeża też wiadomość dnia na Telegramie (`refresh_day`).

## Przyciski (telegram_reply_processor)
`br:<e|s|p|f|d|w>:<id>[:RRRRMMDD]`, `br:<a|z>:RRRRMMDD` → qbot_brokul_meals.handle_callback;
`fd:<o|m|p|k|b|x|r>:<id>[:n]`, `qk:RRRRMMDD:<none|snack|sweet|out_*|bf_*|ln_*|dn_*|win_ok|win_no>` → qbot_food_log.handle_callback.
Przyciski nie wygasają (stan w bazie).

## Pliki
`qbot_brokul.py` (sesja, /brokul-dostep), `qbot_brokul_meals.py` (menu, harmonogram, statusy, tick),
`qbot_food_log.py` (wpisy, AI, katalog, wiadomość dnia), `scripts/brokul_tick.py` (`--init`, `--import`,
`--send DD.MM.RRRR`), `sql/brokul_v1.sql`, `sql/food_v1.sql`, `tests/test_brokul.py`, `tests/test_food_log.py`,
`qbot_web.py` (`/brokul-dostep`, `/api/brokul/session[/status]`).
