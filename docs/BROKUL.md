# Diety od Brokuła → QBot (od 12.10.2026)

Import jadłospisu z panelu klienta dietyodbrokula.pl i potwierdzanie zjedzonych posiłków na Telegramie.

## Jak to działa
- **Sesja**: logowanie hasłem jest NIEMOŻLIWE (formularz chroni niewidoczna reCAPTCHA – sprawdzone 12.10.2026,
  odpowiedź „Coś poszło nie tak z reCAPTCHA”). Michał loguje się w przeglądarce i wkleja nagłówek Cookie na
  **https://albert.cytr.us/brokul-dostep**. Zapis do `/opt/qbot/app/.brokul_session` (600, qbot) tylko po udanym teście.
  Ciasteczka Cloudflare (`cf_clearance`, `__cf_bm`, `_cfuvid`) są odrzucane (przypięte do IP przeglądarki).
- **Cron** (root): `*/15 * * * * runuser -u qbot -- .venv/bin/python3 scripts/brokul_tick.py >> logs/brokul.log`
  - co 3 h import menu (`/customer/diets/` → linki `/customer/diets/menu/item/<id>/` → parser → `qbot_v2.brokul_meals`),
  - między importami odczyt panelu co ≥20 min (podtrzymanie sesji, odświeżone ciasteczka wracają do pliku),
  - od 20:00 jedno podsumowanie dnia na Telegramie (`qbot_v2.brokul_notify` pilnuje, żeby nie było drugiego),
  - sesja wygasła → jedna wiadomość z linkiem do `/brokul-dostep` (`data/brokul_state.json: expired_notified`).
- **Bilans**: do `intake_logs`/`intake_items` wchodzi WYŁĄCZNIE posiłek potwierdzony ✅ (decyzja 12.10.2026).
  `source='brokul'`, `quality_status='imported'`, `meal_type='brokul_<typ>'`, `eaten_at` = przybliżona pora posiłku,
  `sodium_mg = sól_g × 400`. Pierwsze ✅ danego dnia usuwa szacunek z presetu tego dnia (bez podwójnego liczenia).
- **Przyciski** (`br:e|s|p:<id>`, `br:a:<RRRRMMDD>`): ✅ zjadłem / ❌ pominąłem / ponowne kliknięcie stanu = cofnij /
  „Zjadłem wszystkie pozostałe”. Wiadomość się aktualizuje (stan + suma zjedzonych makr). Obsługa:
  `telegram_reply_processor.py` → `qbot_brokul_meals.handle_callback`.

## Pliki
- `qbot_brokul.py` – sesja, pobieranie stron, status, strona `/brokul-dostep` (FORM_HTML).
- `qbot_brokul_meals.py` – parser, baza, Telegram, `tick()`.
- `scripts/brokul_tick.py` – cron; `--init` (tabele), `--import`, `--send DD.MM.RRRR` (wymuś podsumowanie).
- `sql/brokul_v1.sql` – `brokul_meals` (pełne dane: makra, cukry, nasycone, sól, skład, alergeny, status), `brokul_notify`.
- `qbot_web.py` – `GET /brokul-dostep`, `GET /api/brokul/session/status`, `POST /api/brokul/session`.
- `tests/test_brokul.py` – parser (mini HTML + próbka 25 posiłków w /opt/qbot/artifacts/brokul_menu_sample.html).

## Parser
Dzień: `div.meals[data-day]`; posiłek: dziecko-karta z `<h3>` (typ); nazwa: pierwszy `<p>` ≠ „Wartości…”;
wartości po ikonie `use href=...#macros-*` (energy_value, fat, saturated_acids, carbohydrates, sugar, protein,
salt) z zapasem po etykiecie; skład: tekst po „Składniki:” do „Z uwagi na…”; alergeny: zdanie „Z uwagi na…”.
Posiłek bez nazwy/kcal/B/W/T NIE jest zapisywany (reguła: zawsze pełne makra).
Ponowny import aktualizuje tylko posiłki `pending`; potwierdzonych nie rusza.

## Do obserwacji
- jak długo żyje sesja przy podtrzymywaniu co 20 min (stored_at / expired_at w `data/brokul_state.json`),
- czy numer menu zmienia się przy nowym zamówieniu (import bierze wszystkie linki z panelu – powinno działać samo).
