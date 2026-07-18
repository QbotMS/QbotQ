# PROJEKT — Zakładka „Odżywianie" (żywienie + skład ciała)

_Utworzono: 2026-07-17. Zaktualizowano: 2026-07-17 (stan ŻYWY po wdrożeniu — zastępuje pierwotny plan)._
_Wzorzec UI: docs/FORMA_UI_LAYOUT.md. Decyzja: docs/DECISIONS.md (2026-07-17). Żywy system wygrywa — weryfikuj pola na bazie._

Strona: `forma.html`, zakładka `<section data-qtab="Odżywianie">`. Moduł rysujący: `nutrition-render.js` (POZA repo, żywe od razu). Backend: `qbot_web.py` (REPO → restart + commit).

## Źródła danych (zweryfikowane na żywo)
- **`qbot_v2.albert_day_view`** (1 wiersz/dzień, klucz `date`) — energia i jedzenie: `active_kcal`, `resting_kcal`, `expenditure_kcal` (=aktywne+pasywne), `intake_kcal`, `intake_protein_g/carbs_g/fat_g`, `balance_kcal`, `has_intake`, `intake_source`, `intake_quality`. Spalanie zwykle pełne; intake/bilans z lukami (dni bez wpisów jedzenia → puste słupki intake / brak bilansu).
- **`qbot_v2.fitmodel_daily.weight_kg`** — waga codzienna, aktualna.
- **Skład ciała = WIDOKI** (NIE `body_daily`, które było nieaktualne — ostatni pomiar 2026-05-31):
  - `qbot_v2.body_trend_full_composition` — seria dzień po dniu.
  - `qbot_v2.body_latest_full_composition` — ostatni pomiar każdego pola.
  - Źródło: Garmin INDEX_SCALE. Kolumny: `weight_kg, bmi, body_fat_pct, body_water_pct, muscle_mass_kg, bone_mass_kg`. **Brak** visceral i fat_mass_kg. **UWAGA:** `muscle_mass_kg` = realne kg (~68), inaczej niż stare ~32 w `body_daily` (zmiana źródła/skali).

## Backend (qbot_web.py — REPO: restart qbot-web + commit)
- `_build_nutrition_data(conn, start, end)` → `{series:[{day, kcal_total, kcal_active, kcal_passive, intake_kcal, protein_g, carbs_g, fat_g, balance_kcal, weight_kg, body_fat_pct, muscle_mass_kg, body_water_pct, intake_source}], body_latest:{pole:{value,day}}}`. Energia/intake/bilans z `albert_day_view` (`date<=dzis`), waga z `fitmodel_daily`, skład z widoków kompozycji.
- `GET /api/nutrition/data?start&end` (domyślnie 90 dni).
- `POST /api/nutrition/analyze` tryby `cards` / `chart` (dietetyk sportowy, prosty język, format jak `_STYLE`).

## Frontend (nutrition-render.js — POZA repo)
IIFE; korzysta z globalnych `asideShow`/`esc` z forma-render.js. Własne okno danych 7/30/90 (`localStorage qnut_win`), własny zakres wykresu ze strzałkami prev/next (`qnut_crange`), zapamiętane chipy (`qnut_flags3`).

### Karta bilansu (`#nut-balance`)
Układ POZIOMY, 3 kolumny: **Wydatkowanie** (duże kcal po lewej + aktywne/pasywne + śr./dzień) · środek **Bilans** (deficyt zielony / nadwyżka czerwony) · **Przyjęte** (duże kcal po prawej). Pod „Przyjęte": pasek proporcji makro + 3 wiersze **B / W / T** z: gramami, **udziałem % w diecie** (liczonym po kcal, spójnym z paskiem) i **trendem w oknie** (strzałka ↑/↓/→ + %, porównanie 1. vs 2. połowy okna).

### Pasek „Skład ciała" (`#nut-body`)
Jednolinijkowe kafle: **etykieta · wartość · DELTA w oknie · data pomiaru**. Delta = ostatni − pierwszy pomiar w wybranym oknie (strzałka neutralna, bez oceny dobre/złe). Badge „nieaktualne" gdy ostatni pomiar >30 dni.

### Wykres (jeden inline SVG) — 9 niezależnych chipów
- **Spalone** — słupki: aktywne (ciemniejsze) na pasywnych (jaśniejsze).
- **Zjedzone** — LINIA z kropkami (bursztyn). _(Zmiana wzgl. pierwotnego planu: linia, nie overlay słupka.)_
- **Waga** — LINIA czerwona na osi PRAWEJ (kg).
- **% tłuszczu / Mięśnie / Woda** — osobne krzywe kreskowane, KAŻDA własna skala (trend).
- **Białko / Węgle / Tłuszcze** — linie kreskowane na WSPÓLNEJ skali gramów (porównywalne między sobą).
- Etykieta bilansu dnia nad słupkami tylko dla okna ≤31 dni. Hover = tooltip wartości dnia.

### Konwencja kolorów (żaden nie powtarza się między kategoriami)
Białko fiolet `#b45cf0` · Węgle żółty `#eab308` · Tłuszcze(dieta) brąz `#a16207` · %tłuszczu róż `#e06fae` · Mięśnie indygo `#7c8cff` · Woda turkus `#33bcbc` · Spalone-akt `#4f9e6a` / pas `#8fbfa2` · Zjedzone `#f0a13a` · Waga `#e5484d`.

### Analiza AI (prawy drawer)
„Analiza kafli" → mode `cards`; „Analiza wykresu" → mode `chart`.

## Osadzanie w DZIŚ (window.QNut)
Moduł wystawia `window.QNut = {ready(), balanceHTML(), bodyHTML()}`; `renderCards()` po odświeżeniu woła `window.renderTodayNut` (jeśli ustawione). Dzięki temu zakładka DZIŚ osadza „Bilans energetyczny" i/lub „Skład ciała" jako widżety (patrz FORMA_UI_LAYOUT.md sekcja 9). Style tych widżetów są globalne w forma.html, więc renderują się poprawnie poza własną zakładką.

## Otwarte (TODO użytkownika, poza kodem)
- Jak uzupełniać niezalogowane dni jedzenia (ostatnio odpuszczone) — w te dni puste słupki intake / brak bilansu.


## Presety szybkiego szacunku (malo / normalnie / popuscilem)
_Dodane 2026-07-17/18. Odpowiedz na TODO ponizej "jak uzupelniac niezalogowane dni"._ 

Cel: gdy nie chce sie logowac jedzenia pozycja po pozycji, jednym klikiem w kalendarzu przypisac dniu SZACUNEK spozycia.

### Model: ABSOLUTNE kotwice kcal (nie offset od spalania)
- `qbot_nutrition_presets.py` -> `ANCHORS_KCAL = {malo:2200, normalnie:2700, popuscilem:3100}` (kcal, edytowalne recznie; kotwice percepcji uzytkownika).
- Makra kazdego poziomu = **mediana realnych logowanych dni** w pasmie wokol kotwicy (auto-aktualizuja sie wraz z historia). `popuscilem` flagowany `low_confidence` (malo probek w pasmie).
- Filtr realnych dni: bez `source ILIKE %preset%/%recovery%`, bez `quality='estimated'`, `kcal>=1200`, ostatnie 30 probek.
- Bilans do wagi liczony osobno (intake - realny wydatek) -- preset podaje TYLKO intake.

### Endpointy (qbot_web.py)
- `GET /api/nutrition/preset/values?day=` -> 3 opcje (label/kcal/makra/n_days/low_confidence) + `has_real_intake` + `already_preset`.
- `POST /api/nutrition/preset/apply {day, level}` -> zapis `intake_logs` source='preset_estimate' quality='estimated' + 1 pozycja zbiorcza. ODMAWIA gdy dzien ma realne jedzenie; ponowny klik kasuje poprzedni preset (bez dublowania).
- `GET /api/nutrition/day-summary?day=` -> `kind` logged/preset/empty + kcal + makra + lista pozycji + `preset_label`.
- `GET /api/nutrition/status?start=&end=` -> mapa `{date: 'logged'|'preset'}` dla siatki kalendarza (puste dni pominiete).

### Kalendarz (statyki poza repo: kalendarz-render.js, kalendarz.html)
- **Kafelek "Zywienie"** w otwartym dniu (`loadNutriTile` -> `#nutriBox`): ZALOGOWANE (kcal+makra+lista pozycji) / SZACUNEK + etykieta presetu / brak wpisow. Odswieza sie po apply lub dodaniu jedzenia.
- **Ikonka przy dacie w siatce**: emoji 🍽 (to samo co przycisk na sidebarze) + **kropka statusu** obok: zielona = zalogowane, niebieska = preset, czerwona = brak. Status pobierany raz w `load()` z `/api/nutrition/status` -> `NUTRI`. Emoji nie da sie przefarbowac na niebieski/czerwony, wiec status niesie kropka, nie kolor talerza.

### Odlozone
- **Eviction**: gdy uzytkownik pozniej wpisze RECZNIE realne jedzenie na dzien z presetem, preset NIE jest auto-usuwany (ryzyko dublowania) -- apply pilnuje tylko kierunku "nie dodawaj presetu gdy jest realne".
- **Auto-przypisanie** presetu pustym dniom (np. domyslnie normalnie) -- nie zrobione.
