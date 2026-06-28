# QBOT_KNOWHOW.md — Know-how QBot

Wersja: 2.0
Data: 2026-06-02
Status: zatwierdzony przez MS

---

## 1. Mapa usług i portów

| Usługa | Port | Opis |
|---|---|---|
| `qbot-api.service` (uvicorn) | 8002 | FastAPI — MCP endpoint, Telegram webhook, API |
| `qbot-mcp-bridge.service` | 8000 | MCP SSE bridge dla ChatGPT |
| `qbot-qlab-server.service` | 8899 | QLab/Gate HTTP server |
| `q365.service` | 8001 | osobna ścieżka produkcyjna |
| `nginx` | 80/443 | reverse proxy: qbot.cytr.us |

### nginx routing

```
/mcp/                              → 127.0.0.1:8002/mcp/
/telegram/webhook/{secret}         → 127.0.0.1:8002/telegram/webhook/
/ride-readiness                    → 127.0.0.1:8002/ride-readiness
/gate/open, /gate/status           → 127.0.0.1:8899
```

---

## 2. Mapa plików

### Core runtime

```
qbot_api.py                  FastAPI app, MCP endpoints, Telegram webhook
qbot_mcp_adapter.py          MCP tool dispatch, safety, auth
qbot_query_handler.py        Deterministic intent router (36 handlers, ~50 intents)
qbot_nutrition_db.py          Nutrition CRUD (meal_logs, intake_logs, templates, plans, daily_summary)
qbot_nutrition_tools.py       MCP wrappers for nutrition DB
qbot_nutrition_parser.py      Natural language → structured intake
qbot_health_db.py             Body, sleep, wellness, energy, training readers
qbot_calendar_core.py         Event/reminder CRUD, snapshot builder
qbot_qcal_telegram.py         Telegram gateway, InlineKeyboard confirm
```

### QBot3 / Albert (selektywny)

```
qbot3/
├── agent_runtime.py          Albert orchestrator (LLM plan → tools → answer)
├── context_builder.py        Context selector
├── safety.py                 Allowlist, idempotency, audit
├── tool_registry.py          35 capability definitions
├── connectors/
│   ├── import_garmin_sleep.py
│   ├── import_garmin_energy.py
│   ├── import_garmin_training.py
│   └── import_garmin_body.py
└── llm/
    ├── openai_provider.py
    ├── deepseek_provider.py
    └── mock_provider.py
```

### Trasy / RWGPS

```
app/tools/rwgps/
├── route_workflow.py         Fetch → process → upload workflow
├── climbs.py                 Climb detection (min 100m, 5m gain, 1%)
├── rwgps_poi_push.py         POI selekcja → Google verify → RWGPS push
└── route_feasibility.py      Ocena wykonalności trasy
```

### Raporty

```
event_morning_report.py       Raport poranny: forma + pogoda OWM + podjazdy + HTML email
```

---

## 3. Baza danych — schema qbot_v2

### Nutrition

| Tabela | Opis |
|---|---|
| `intake_logs` | Główne logi posiłków (date, eaten_at, meal_type, note, source) |
| `intake_items` | Składniki posiłku (kcal, protein_g, carbs_g, fat_g, fiber_g) |
| `meal_logs` + `meal_log_items` | Legacy mirror (dual-write z meal_log_create) |
| `food_items` | Baza produktów z makro per 100g |
| `meal_templates` | Szablony posiłków (nazwa, makro, serving_label) |
| `nutrition_daily_summary` | Computed: suma makro per day |
| `nutrition_day_plans` + `nutrition_day_plan_meals` | Planowane posiłki |
| `hydration_events` | Nawadnianie |
| `fueling_events` | On-bike fueling (gele) — NIE regular meals |

CHECK constraints na `intake_items` i `meal_log_items`: non-negative macros.

### Body / Health

| Tabela | Opis |
|---|---|
| `body_measurements` | Garmin Index Scale: waga, body fat, muscle, bone, water, BMI |
| `daily_summary` | Garmin: intake_kcal, expenditure_total, balance_kcal |
| `sleep_daily` | Garmin: czas snu, fazy, score |
| `energy_daily` | Garmin: BMR, active kcal, steps |
| `wellness_daily` | Garmin: HRV, body battery, resting HR, stress |
| `training_sessions` | Garmin/Hammerhead: sesje treningowe |
| `xert_profile_snapshots` | Xert: FTP, LTP, W', freshness, fatigue |

### System

| Tabela | Opis |
|---|---|
| `days` | Kalendarz dni |
| `tool_calls` | Audit tool calls |
| `qbot_memory` | Pamięć międzysesyjna |
| `qbot_artifacts` | Zarejestrowane artefakty |
| `qbot_planning_facts` | Planning facts |
| `route_artifacts` | Metadane tras RWGPS |

---

## 4. Cron jobs

```
*/15 5-8    import_garmin_sleep.py       Sen z Garmin
*/15 5-8    import_garmin_energy.py      Energia wczoraj z Garmin
*/15 9-23   import_garmin_training.py    Treningi z Garmin
0 9-23/2    import_garmin_energy.py      Energia dziś (partial) z Garmin
30 7        import_garmin_body.py        Body composition z Garmin (--days 3)
*/10        hammerhead_garmin_sync        Sync aktywności Hammerhead → Garmin
* * * * *   reminder_daemon.py           Daemon przypomnień
3 17        prune_qbot_artifacts.py      Czyszczenie starych artefaktów
```

---

## 5. Procedury diagnostyczne

### 5.1 Sprawdzenie serwisów
```bash
systemctl status qbot-api qbot-mcp-bridge qbot-qlab-server
ss -tlnp | grep -E '800[0-9]|889'
```

### 5.2 Weryfikacja MCP tools
```bash
curl -s -X POST http://127.0.0.1:8002/mcp/ \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 -m json.tool
```

### 5.3 Nutrition: weryfikacja zapisu
```bash
source /etc/qbot/qbot-api.env
PGPASSWORD=$PGPASSWORD psql -h 127.0.0.1 -U qbot -d qbot -c \
  "SELECT id, date, meal_type, note FROM qbot_v2.intake_logs ORDER BY id DESC LIMIT 5"
```

### 5.4 Nutrition: recompute daily summary
```bash
cd /opt/qbot/app && .venv/bin/python3 -c "
from qbot_nutrition_db import daily_summary_compute
s = daily_summary_compute('2026-06-01')
print(s)
"
```

### 5.5 Telegram webhook
```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getWebhookInfo" | jq .
```

### 5.6 Garmin connector status
```bash
source /etc/qbot/qbot-api.env
PGPASSWORD=$PGPASSWORD psql -h 127.0.0.1 -U qbot -d qbot -c "
  SELECT 'sleep' as t, count(*), max(date) FROM qbot_v2.sleep_daily
  UNION ALL SELECT 'energy', count(*), max(date)::text FROM qbot_v2.energy_daily
  UNION ALL SELECT 'training', count(*), max(started_at::date)::text FROM qbot_v2.training_sessions
  UNION ALL SELECT 'body', count(*), max(date)::text FROM qbot_v2.body_measurements
  UNION ALL SELECT 'wellness', count(*), max(date)::text FROM qbot_v2.wellness_daily
"
```

---

## 6. Historia napraw

### 2026-06-02 — Naprawione 3 bugi nutrition (audyt OpenAI)

**Bug 1: Ciabatta — podwojone W/fiber w itemach**
Items 43 (serek) i 44 (serrano) miały skopiowane carbs/fiber z ciabatty.
Fix: UPDATE w DB + recompute daily_summary.
Prewencja: `_validate_and_fix_meal_items()` — duplicate field detection.

**Bug 2: Miód — białko/tłuszcz z Wiejskiego HP**
Item 41 (miód) miał P=28 T=6 skopiowane z sąsiedniego itemu.
Fix: UPDATE w DB (P=0, T=0).
Prewencja: sugar-type keyword detection zeruje P/T > 2g.

**Bug 3: nutrition_range balance niespójny**
Balance brało `daily_summary.balance_kcal` (Garmin) ale intake z `nutrition_daily_summary.kcal_total` (QBot).
Fix: balance = QBot_intake - expenditure. Fallback do Garmin balance tylko gdy brak QBot intake.

**Nowe zabezpieczenia:**
- `_validate_and_fix_meal_items()` na OBU ścieżkach zapisu (meal_log_create + intake_log_create)
- DB CHECK constraints: non-negative macros
- Cross-item duplicate detection + auto-fix
- Macro-kcal ratio > 2.0 → auto-scaling proporcjonalne

### 2026-06-02 — Multi-intent queries (P2)

Dodano `_detect_domains()` + `_handle_multi_intent()` — zapytania cross-domain (np. "body composition + bilans kaloryczny za 14 dni") wywołują wiele handlerów i scalają odpowiedzi.

### 2026-06-01 — Naprawione P0 z audytu OpenAI

- P0.1: Date resolver obsługuje `01.06.2026`, `1 czerwca 2026`, `wczoraj`
- P0.2: `meal_logs` keyword dodany do `nutrition_intake_logs_list`
- P0.3: `nutrition_range.balance` liczy fallback `intake - expenditure` gdy `balance_kcal` null

### 2026-05-29–06-01 — Nowe capability

- Route workflow (fetch/upload/list)
- Climbs analyzer
- POI pipeline (OSM → Google Places → RWGPS)
- Morning event report (pogoda OWM strefowo + podjazdy + HTML)
- Daily report: nutrition + activity z WCZORAJ
- Trip stages/attractions/route generation
- Tile analysis (statshunters)
- Route feasibility
- Xert live fetch + status
- Garage status + search
- Artifact search + read
- Memories search
- Help command

### 2026-05-28 — QBot3/Albert MVP cutover

LLM orchestrator uruchomiony selektywnie. Deterministyczny query handler pozostaje główną ścieżką.
Szczegóły: patrz QBOT_BIBLE v1.1 sekcja 14 (zachowana jako archiwum).

---

## 7. Znane ograniczenia

- Fueling events + meals: jeśli ten sam posiłek jest w intake_items I fueling_events, carbs liczone podwójnie w daily_summary_compute
- Nutrition template matching: alias engine, nie pełny NLP
- Walidacja sumy itemów vs total posiłku: brak (każdy item walidowany osobno)
- QBot3 Albert: selektywny, nie główna ścieżka
- Telegram conversation context: niezweryfikowane czy LLM dostaje ostatnie N turnów

### 2026-06-02 — Naprawione G1/G2/G3/H2/H3 (routes and trip)

**G1: route_workflow_list — brak route_id w tekscie**
Fix: dodano route_id do kazdej linii wynikowej.

**G2/G3: hardcoded route_id 55257604 (Tuscany Trail pelna)**
Faktyczne etapy Toskanii 2026: 55395117-55395129 w qbot_planning_facts.
Fix: _resolve_tuscany_route_id() lookupuje z DB. Wspiera hint etapu.

**H2: poi_stage_detail format**
Stary kod nie obslugiwat struktury {attractions,water,food,shop}.
Fix: _format_poi_items() z per-sekcja labelami.

**H3: Attraction osm_id jako nazwa**
Fix: _readable_poi_name() wyciaga name= z source_tags.

### 2026-06-02 — Naprawione P0/P1 z testu regresyjnego OpenAI

**P0-1: feasibility.py linia 87 — indentation error**
Brakujące def get_weather(lat, lon, start_hour=8). Fix: dodano nagłówek funkcji.

**P0-2: routing — toskania/tuscany w trips_status pochłaniało 6 intentów**
Symptom: etap 4 toskania, atrakcje toskania, artefakty tuscany → trips_status.
Fix: usunieto toskania/tuscany z trips_status. Dodano do trip_stages.
artifact_search/artifact_read przeniesiony PRZED trips_status w INTENT_KEYWORDS.
Dodano canonical/wip/shelf do artifact_search keywords.
Dodano kasków/rękawiczek/deklinacje do garage_search.

**P1-1: body_comp ignorował day_str — zawsze zwracał latest**
Fix: gdy req_date < today: SQL z WHERE date <= req_date zamiast LIMIT 1 z widoku latest.

**P1-2: body_measurements_range i weight_trend — 14 dni zamiast miesiąca**
Fix: słowne mappingi: miesiąc→30, tydzień→7, kwartał→90. Weight_trend default 14→30.

**P1-3: tile_analysis status OK przy 401 Unauthorized**
Fix: check na 401/Unauthorized w tile_error → status_override=ERROR.

**P1-4: multi-intent domain signals — xert i trip dodane**
Fix: DOMAIN_SIGNALS += xert/trip. DOMAIN_TO_HANDLER: nutrition→daily_balance, body→body_comp.

### 2026-06-02 — Naprawione P2 (jakość odpowiedzi)

**P2-1: nutrition_range — tabela per-day**
Dodano tabelę Data|Kcal|B|W|T|Bilans pod podsumowaniem kumulatywnym.

**P2-2: climbs — agregacja mikro-segmentów**
MIN_GRADE 1%→2%, MIN_LENGTH 100m→300m, MIN_ELEV 5m→10m.
Gap-fill: segmenty przedzielone <80m płaszczyzny są scalane.

**P2-3: nutrition_status — format czytelny**
Zamiast str(dict): sekcja z emoji i wyrównaniem kolumn.

**P2-4: daily_report — rzeczywisty raport zamiast diagnostyki**
Nowa funkcja _handle_daily_report: sen + wellness + energia + treningi + nutrition.
Diagnostyka nadal dostępna pod intent report_diagnostic (dlaczego raport pusty?).
SQL dopasowany do schematu: duration_min, score, body_battery_start/end,
resting_kcal, activity_name, duration_s.

### 2026-06-02 — Naprawione z drugiego retesetu OpenAI

**feasibility.py: get_form/get_route/aliasy stałych**
Brakujące def get_form (alias _get_form_data), def get_route (fetch RWGPS + GPX),
aliasy BASE_SPEED/ELEV_PENALTY/KCAL_BASE/KCAL_HARD/HRV_OK/HRV_RISKY, def _rwgps_env.
_rwgps_env czyta z env vars + fallback na pliki .env/.env.local//etc/qbot/qbot-api.env.

**multi-intent: brakujące handlery**
Dodano: daily_balance, body_comp, xert_status, trip_stages, weight_lookup.
DOMAIN_TO_HANDLER: nutrition->daily_balance, body->body_comp.
Etykiety: xert->FORMA(XERT), trip->TRASA/ETAP.

**garage routing: garaz vs garazu**
garaz jest substring garazu wiec substring matcher zawsze matchowal garage_status.
Fix: garaz/garage przeniesione do garage_search. garage_status triggeruje przez
rower/sprzet/wyposazenie/status garazu.
GARAGE_ALIASES: kasków/kasku->helmet+headwear, rekawiczek->gloves.

**nutrition_status: ? zamiast liczb**
chr(39) w f-string dawało dosłowne chr(39) zamiast apostrofu.
Fix: przypisanie do zmiennych przed f-stringiem.

**artifact_search canonical: shelf filter zamiast text search**
Gdy shelf_filter wykryty i brak search_term: search_term pozostaje pusty.
SQL: like = % gdy search_term pusty (szuka wszystkiego w shelf).

### 2026-06-02 — Naprawione z testu v3 OpenAI

**rekąwiczki? — strip punctuation**
Znak zapytania w tokenie blokował alias. Fix: re.sub non-word chars przed split.

**ride_report — ostatnia jazda globalnie**
Szukało tylko dziś/wczoraj. Fix: ORDER BY date DESC LIMIT 5 bez WHERE date.

**POI trip_hint PL→EN**
toskani nie matchowało Tuscany w tytulach DB. Fix: _TRIP_HINT_MAP toskani→tuscany.

**artifact_search canonical shelf**
Extractor wyciągał 'canonical tuscany' jako search_term.
Fix: canonical/wip/export dodane do noise words w extractorze.
Shelf detection przed last-resort — pozostale slowa = project hint.

**memories fallback do planning_facts**
Gdy memories puste: szukaj w qbot_v2.qbot_planning_facts.
PL→EN mapping (toskania→tuscany) + strip punctuation z search_term.

**garage_search helmet-first**
kasków dawalo helmet+headwear razem.
Fix: gdy expanded_terms zawiera 'helmet' i sa wyniki Helmet, filtruj do Helmet only.

### 2026-06-02 — Naprawione R5/N1/R6 (test v4)

**R5: etapie/etapu nie matchowalo regex etap\s+(\d+)**
Fix: regex zmieniony na etap[uie]*\s*(\d+).

**N1: per_day zawieralo intake_kcal z daily_summary (Garmin)**
entry.update(dse) wrzucalo intake_kcal=2725 obok kcal_total=2525.
Fix: kopiuj tylko expenditure_total i balance_kcal z dse, nie caly dict.

**R6: artifact canonical shelf — Method 1 ignorowalo shelf filter**
search_artifacts() nie obsluguje shelf. Gdy shelf_filter ustawiony:
store_unavailable=True -> wymuszenie Method 2 (SQL z shelf clause).
Shelf clause uzywa relatywnej sciezki (canonical/%) zamiast absolutnej.
Polka display: startswith check dla relatywnych sciezek.

### 2026-06-02 — Naprawione P1/P2/P3/P4 (test v5)

**P1: trip_attractions section filter (woda/atrakcje)**
Nowe: _SECTION_KW mapa slow -> sekcji POI (water/food/attractions/accommodation/bike_shop).
_detect_section_filter() wykrywa sekcje z pytania.
Gdy wykryta: format_poi_record dostaje tylko jedna sekcje zamiast calego dict.
Wynik: woda pitna etap 1 -> tylko 2 punkty water.

**P2: route_climbs resolved_route_id w odpowiedzi**
Pierwsza linia answeru: Trasa: <route_id>.
data zawiera resolved_route_id i km_from.

**P3: wellness_day jawny komunikat gdy HRV null**
Gdy hrv_ms is None i pytanie zawiera hrv:
HRV: brak danych dla <date> (null w Garmin).
_handle_wellness_day przyjmuje opcjonalny param question.

**P4: artefakty tuscanyt - archiwizacja starych**
27 artefaktow ze starym route_id 55257604 i starymi raportami
przeniesiono do status=archived w qbot_v2.artifacts.

### 2026-06-02 — Naprawione z testu v7

**C1: normalizacja wejscia**
_normalize_question(): etap4->etap 4, stage3->stage 3, 30d->30 dni.
Wywolywane na poczatku handle_query przed routingiem.

**C4: stage N (angielski) w _resolve_tuscany_route_id**
Regex zmieniony na (?:etap|stage)\s*(\d+) — obsługuje obie wersje.

**C5: Nd pattern w weight_trend**
Regex (\d+)\s*(?:dni|d) zamiast tylko dni.

**E1/E3/E4: write-intent routing**
Nowe intenty: write_meal (ACTION_REQUIRED), write_delete_unsupported (BLOCKED),
write_planning_unsupported (BLOCKED), write_weight_unsupported (BLOCKED).
Keywords PRZED daily_balance żeby nie wpaść w odczyt.

**D: kontekst sekwencyjny — pytaj zamiast zgadywać**
trip_attractions: gdy brak stage_n i brak trip_hint i pytanie zawiera
slow kontekstowych (tam, ten etap, na nim...) -> prośba o doprecyzowanie.
unrecognized handler: krótkie pytania (<=4 słowa) lub kontekstowe -> prośba.

### 2026-06-02 — Naprawione z testu v9

**1.4: noc z X na Y -> data Y**
_parse_date_from_question: regex noc[y]? z D1 na D2 miesiac -> date(D2, miesiac).

**2.4: woda/punkty wody na etapie N**
trip_attractions keywords: punkty wody, woda na etapie, ile punktow wody.

**4.4: db_access_blocked**
Nowy intent db_access_blocked z keywords: qbot_v2., administrator systemu,
dostep do tabeli, select *, drop table itp. Status BLOCKED.

**5.2: weight_lookup respects date**
Stare daty: SELECT WHERE date <= req_date ORDER BY date DESC LIMIT 1.
Brak pomiaru -> brak danych zamiast fallback na latest.
Ostrzezenie gdy znaleziony pomiar jest z innej daty niz zapytana.

### 2026-06-02 — Rozszerzony keyword router (z testu v9)

**2.1/2.2: trip_summary — nowy intent**
Keywords: suma etapow, lacznie etapy, najdluzszy etap, ktory etap jest najdluzszy itp.
Handler _handle_trip_summary: liczy total_km, najdluzszy, najkrotszy, lista etapow.
_handle_trip_stages deleguje do trip_summary gdy wykryje slowa agregujace.

**2.3: feasibility — _resolve_tuscany_route_id zamiast hardcoded 55257604**
Ostatni hardcoded 55257604 w _handle_route_feasibility zamieniony na resolver.

**1.4: noc z X na Y**
_parse_date_from_question: regex noc[y]? z D1 na D2 miesiac -> data D2.

**2.4: punkty wody na etapie N**
trip_attractions keywords: punkty wody, woda na etapie, ile punktow wody.

**4.4: db_access_blocked**
Nowy intent z keywords SQL/admin: qbot_v2., administrator systemu itp.

**5.2: weight_lookup historyczny**
Stare daty: WHERE date <= req_date zamiast latest.

### 2026-06-02 — Analytical fallback (Albert/Gemini)

Pytania agregujące/porównujące → Albert przez Gemini 2.5 Flash Lite.
Trigger: _ANALYTICAL_WORDS w handle_query przed multi-intent.
Gemini wymaga tool_choice='required' na pierwszym kroku (auto nie działa).
Config: .env.local QGPT_BASE_URL=Gemini, qbot_config load_dotenv override=True.
albert.py: run() przyjmuje override_api_key/base_url/model.
Exempt intents: trip_summary, route_*, report_*, artifact_*, write_*, db_access_blocked.

## TODO — action_execute rozszerzenie (sesja 2026-06-02)

### Kontekst
Akcje które teraz robi się przez terminal powinny być dostępne przez qbot.action_execute
żeby GPT mógł je wywołać samodzielnie przez MCP.

### Lista do zrobienia

1. **rwgps_gpx_fetch** — pobierz GPX z RWGPS do artefaktów
   - payload: {route_id, shelf='canonical', project_id}
   - pobiera .gpx z RWGPS API i rejestruje w qbot_v2.artifacts
   - przykład użycia: 'pobierz GPX etapów toskanii do canonical'

2. **rwgps_routes_list** — lista tras z RWGPS dla danego okresu
   - payload: {days=7, project='tuscany'}
   - odpytuje RWGPS API i zwraca listę tras z linkami
   - teraz zrobione przez _handle_rwgps_recent_routes w query (read-only)

3. **artifact_move_shelf** — przenieś artefakt między półkami
   - payload: {artifact_id, from_shelf, to_shelf}
   - zmienia file_path i kopiuje plik

4. **planning_fact_update** — zaktualizuj istniejący fact (np. route_id w stages)
   - payload: {fact_id, path, value}
   - teraz robi się przez SQL bezpośrednio

5. **nutrition_daily_summary_recompute** — przelicz dzienne podsumowanie
   - payload: {date}
   - teraz robi się przez SQL w nutrition_log_correct/delete

### Szerszy zakres
Przejrzeć wszystkie _action_exec_* i upewnić się że:
- są w allowliście action_execute
- mają poprawne payload_fields w _ACTION_REQUIRED_PAYLOAD_FIELDS
- są opisane w system prompt Custom GPT

### 2026-06-02 — Google Places POI dla etapów Toskanii

Załadowano Google Places food/shop POI dla wszystkich 7 etapów.
Bufor: 2000m od trasy. Krok próbkowania: co 8km.
Łańcuchy (McDonald, KFC, Starbucks itp.) odfiltrowane.

Wyniki: etap1=57, etap2=85, etap3=65, etap4=39, etap5=25, etap6=58, etap7=79

Dane zapisane w qbot_v2.qbot_planning_facts (id 5-11), pole fact_json.food.

Zapytanie: qbot.query 'jedzenie etap N toskania' → trip_attractions z section_filter=food

## TODO — rwgps_poi_fetch_google jako action_execute

Dodać action_type=rwgps_poi_fetch_google do allowlisty action_execute.
Payload: {stage, route_id, project_id, buffer_m}.
Handler: pobiera GPX z artifacts/canonical, odpytuje Google Places co 8km,
zapisuje do planning_facts.fact_json.food, zwraca count POI.
