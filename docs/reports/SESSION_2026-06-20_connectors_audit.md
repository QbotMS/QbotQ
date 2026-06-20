# Podsumowanie sesji — audyt connectorów QbotQ i plan naprawy bilansu

Data: 2026-06-20. Gałąź: `claude/garmin-calorie-sync-issue-8cc6yb`.
Środowisko sesji: Claude Code on the web (klon repo, BEZ dostępu do prod-DB/Garmina/sekretów).

## 1. Problem wyjściowy
Bilans kaloryczny „wczoraj" błędny/nieaktualny: Garmin 3114 kcal vs Qbot 2678; potem także w `qbot.query`.

## 2. Korekta błędnej hipotezy (ważne)
Pierwsza próba „rekonsyliacji" (doliczanie kalorii jazdy z Karoo) była BŁĘDNA — Garmin już wlicza jazdę z Hammerheada do dziennego `totalKilocalories` (transfer HH→Garmin co 10 min, FIT przepisany manufacturer→Tacx). Doliczanie = podwójne liczenie. Cały ten kod cofnięty (`git reset --hard` do `3df7108`, force-push). Repo czyste.

## 3. Decyzje użytkownika (twarde wymagania)
- **Jedno źródło prawdy** dla spalonych/bilansu: `qbot_v2.energy_daily` przez `ReportDataProvider`. I raport, i `qbot.query` czytają stąd.
- **kcal_out = 100% dziennego totalu Garmina** = `total_kcal` (= `active_kcal` + `resting_kcal`). NIGDY nie doliczać kalorii pojedynczych aktywności/treningu.
- **Connectory qbot_v2 nie chodzą** (nie ma ich w udokumentowanym cronie) → trzeba zaplanować.
- **Korekta WSZYSTKICH connectorów**, dodanie **OpenWeatherMap**, weryfikacja zapisu w BD źródło po źródle.

## 4. Audyt connectorów (źródło → dane → kierunek → zapis → tryb)
| Connector | Dane | Kier. | Ląduje w | Tryb |
|---|---|---|---|---|
| Garmin (energy/sleep/training/body) | energia, sen, wellness, waga, treningi | READ (+upload via HH) | `qbot_v2.energy_daily/sleep_daily/wellness_daily/body_measurements/training_sessions` | connectory **nie w cronie** + on-demand |
| Intervals.icu | wellness, aktywności, sprzęt, komentarze | READ + WRITE (PUT komentarz) | `qbot_wellness_daily`, `qbot_wellness_notes`, `qbot_nutrition_daily` | on-demand + import |
| Cronometer | nutrition (kcal/makra) | READ | `qbot_nutrition_daily`; intervals comment | cron `0 */2` (sync_nutrition) |
| Xert | FTP/W'/forma/load | READ | `qbot_v2.xert_profile_snapshots` | cron 00:15 (docstring; brak w repo) |
| Hammerhead/Karoo | aktywności + FIT | READ HH → WRITE Garmin | `outgoing/*`, `state/*.json`, upload Garmin | root cron `*/10` |
| Withings | skład ciała | READ | `qbot_v2.body_daily` | ❌ DEPRECATED |
| RideWithGPS | trasy/GPX | READ (+create) | `route_artifacts/route_parse_results/route_surface_*` + artifacts | on-demand + cache |
| Pogoda (Open-Meteo) | opady/wiatr/temp | READ | **tylko cache** `data/daily_external_cache.json` | on-demand |
| Google Places / OSM-Overpass | POI | READ | artifacts JSON (`route_logistics/*`) | on-demand |
| Telegram / Gmail | I/O | READ+WRITE | transport; crony `*/2`, `*/10` | webhook/cron |
| LLM (OpenAI/DeepSeek/Anthropic) | intencja/odpowiedź | — | logi observability | per query |
| HikConnect/Gate | brama (poza fitness) | READ(+unlock) | capability read-only | on-demand |

Poza tym (brak integracji): Strava (tylko gear), Microsoft 365/Outlook (NIE zaimplementowane), Google Calendar (lokalny Postgres), OpenRouter (fallback LLM).

## 5. Weryfikacja zapisu w BD — co utrwalamy vs gubimy
- **Energia (cron)** → `qbot_v2.energy_daily`: resting/active/total_kcal, steps. OK.
- **Wellness (cron, w energii)** → `qbot_v2.wellness_daily`: RHR, body battery, stress, spo2, oddech. **Gap:** `hrv_ms`, `weight_kg`, sleep_*, mood/fatigue/readiness — kolumny puste.
- **Sen (cron)** → `qbot_v2.sleep_daily`: czas, fazy, score, hrv, RHR. **Gap:** `sleep_quality`, spo2 (tylko on-demand).
- **Treningi/Ciało (cron)** → `qbot_v2.training_sessions`/`body_measurements`: pełnia. OK.
- **Energia on-demand** → `public.daily_energy_expenditure`: NIE odświeża (cementuje) + INNA tabela niż cron.
- **Wellness/sen on-demand** → `public.qbot_wellness_daily`/`qbot_sleep_daily` (LEGACY).
- **Pogoda:** brak zapisu do BD. **OpenWeatherMap: nieobecny** (tylko env).

## 6. Trzy strukturalne ustalenia
1. **Split-brain zapisu:** cron pisze do `qbot_v2.*`, on-demand do legacy `public.*`. Provider czyta `qbot_v2.*` → fallback legacy. Gdy cron nie chodzi, `qbot_v2.*` puste.
2. **Brak wersjonowania schematu:** kanoniczne `qbot_v2.*` health (energy/sleep/wellness/training/body/xert/nutrition_daily_summary) NIE mają `CREATE TABLE` w `sql/` — schemat = lista kolumn INSERT.
3. **Energia/bilans = 3 ścieżki** (intervals comment / `daily_energy_expenditure` / `qbot_v2.energy_daily`); `ensure_daily_energy_expenditure` nie odświeża istniejących wierszy.

## 7. Plan naprawy bilansu (ujednolicenie na qbot_v2.energy_daily)
- `daily_report.py`: helper `_balance_series(df,dt)` — kcal_out z `qbot_v2.energy_daily.total_kcal`, kcal_in z nutrition; przeliczyć `balance_yest`/`balance_7d`/`bilans_historia_7d`; usunąć błąd 590-593.
- `qbot_query_planner.py`: energy join → `qbot_v2.energy_daily` (mapowanie total/active/resting_kcal, aliasy `..._out`).
- `qbot_energy_store.py`: nowy `ensure_fresh_energy()` → `qbot_v2.energy_daily`, get_user_summary, refresh dla partial/nieświeżych (dziś/wczoraj), naprawa „existing → nigdy nie odświeża".
- `qbot_query_router.py`: 949-950 → `ensure_fresh_energy`.
- `qbot_report_data_provider.py`: wpiąć `ensure_fresh_energy(ds/yds)` przed SELECT energy.
- Cron (prod): zaplanować 4 connectory (energy „finalize wczoraj" 05-08 + dziś `0 */2 9-23`; sleep 05-09; training 09-23; body 06:30). Uwaga TZ (connector liczy okno po UTC).
- Zachować: intervals comment (podgląd), `daily_energy_expenditure` (read-only fallback).

## 8. Szersza korekta (do domknięcia)
- Usunąć split-brain: ścieżka on-demand też do `qbot_v2.*`.
- Dodać connector **OpenWeatherMap** (równolegle/fallback do Open-Meteo); decyzja czy pogodę utrwalać w BD.
- Wersjonować schemat `qbot_v2.*` w `sql/`.
- Zaplanować Xert snapshot w cronie.

## 9. Weryfikacja na prodzie (sandbox nie ma dostępu)
Powód braku dostępu: sesja web = efemeryczny kontener z samym klonem repo; brak prod-DB/sekretów/tokenów/`/opt/qbot/app`. DesktopCommander w tej sesji niedostępny — działa tylko w sesji Claude Desktop (i tylko na maszynie z SSH do prod-a).

```bash
ssh PROD 'crontab -l'; ssh PROD 'sudo crontab -l'
ssh PROD 'psql -U qbot -d qbot -At -c "
SELECT '\''energy'\'',count(*),max(date) FROM qbot_v2.energy_daily
UNION ALL SELECT '\''sleep'\'',count(*),max(date) FROM qbot_v2.sleep_daily
UNION ALL SELECT '\''wellness'\'',count(*),max(date) FROM qbot_v2.wellness_daily
UNION ALL SELECT '\''training'\'',count(*),max(date) FROM qbot_v2.training_sessions
UNION ALL SELECT '\''body'\'',count(*),max(date) FROM qbot_v2.body_measurements
UNION ALL SELECT '\''xert'\'',count(*),max(date) FROM qbot_v2.xert_profile_snapshots;"'
ssh PROD 'psql -U qbot -d qbot -At -c "
SELECT '\''leg_energy'\'',count(*),max(date) FROM public.daily_energy_expenditure
UNION ALL SELECT '\''leg_wellness'\'',count(*),max(date) FROM public.qbot_wellness_daily
UNION ALL SELECT '\''leg_sleep'\'',count(*),max(date) FROM public.qbot_sleep_daily
UNION ALL SELECT '\''leg_nutrition'\'',count(*),max(date) FROM public.qbot_nutrition_daily;"'
```

## 10. Następne kroki
1. Przełączyć się na sesję Claude Desktop z DesktopCommander (maszyna z SSH do prod-a) i odpalić powyższe.
2. Na podstawie wyników domknąć plan korekty wszystkich connectorów.
3. Wdrożyć naprawę bilansu (sekcja 7) na gałęzi `claude/garmin-calorie-sync-issue-8cc6yb`.
