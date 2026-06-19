# QBot — architektura i opis działania

*Stan na czerwiec 2026. Dokument zrekonstruowany z kodu na `/opt/qbot/app` oraz z weryfikacji wykonanych w trakcie pracy nad narzędziem profilu. Część szczegółów wewnętrznych jest potwierdzona wprost (grepy), część opisana na poziomie projektowym.*

## 1. Czym jest QBot

QBot to osobisty asystent rowerowo-zdrowotny. Backend działa jako usługa systemd `qbot-api` na VPS (mikrus, `olga181`), w katalogu `/opt/qbot/app`, na własnym venv (`.venv`). Konfiguracja idzie przez `qbot_config.py` (`load_dotenv(override=True)`) oraz env w `/etc/qbot/`. Dane trzymane są w Postgresie (schemat `qbot_v2`) i w artefaktach plikowych na dysku.

Głównym klientem jest Custom GPT (ChatGPT) podpięty przez MCP. Drugim kanałem jest dostęp administracyjny przez SSH/CLI.

## 2. Obraz wysokopoziomowy

QBot jest **hybrydą**, nie czystym serwerem MCP wystawiającym dane do LLM. Większość zapytań obsługuje deterministyczny keyword-router (bez LLM — tanio i przewidywalnie). Pytania analityczne lecą do osobnego orchestratora LLM (Albert / Gemini). Przepływ:

```
Klient (Custom GPT / CLI)
        │  HTTP + Bearer
        ▼
   MCP  ──┬──  /mcp/        (query: odczyt/analiza → routing intencji)
          └──  /mcp/action  (action_execute: operacje z allowlisty)
        │
        ▼
   Routing → handler / narzędzie
        │
        ▼
   Dane: Postgres (qbot_v2) · artefakty · RWGPS · Google Places · OSM/Overpass
        │
        ▼
   _envelope → JSON z powrotem do klienta
```

Powód takiej konstrukcji: keyword-router rozwiązuje ~250 intentów bez round-tripa do modelu, serwer pre-filtruje dane (np. POI po `section_filter`) zamiast wrzucać LLM-owi surowe bloby, a granica zapisu jest pilnowana przez allowlistę. Cena: kruchość routingu (kolizje fraz, `multi_intent`).

## 3. Wejście — warstwa MCP

Custom GPT łączy się pod `https://qbot.cytr.us/mcp/` z autoryzacją Bearer. Wystawione są dwa endpointy:

- **`/mcp/` (query)** — zapytania w języku naturalnym; trafiają do routera intencji. Tędy idą odczyty i analizy.
- **`/mcp/action` (action_execute)** — wykonanie operacji o nazwie z allowlisty, z jawnym payloadem. Tędy idą operacje (w tym read-only akcje narzędziowe).

Instrukcje sterujące zachowaniem GPT są w `QBOT_GPT_INSTRUKCJE_v3.md` (po stronie konfiguracji GPT).

## 4. Routing zapytań — `qbot_query_handler.py`

To główny keyword-router (~250 intentów).

- `_resolve_intent(question)` — dopasowanie **first-match** po liście `INTENT_KEYWORDS`. Kolejność ma znaczenie: frazy wielowyrazowe muszą stać przed pojedynczymi słowami, żeby szersze frazy nie przechwyciły węższych zapytań.
- `_detect_domains(question)` — klasyfikacja domen zapytania; gdy pasuje więcej niż jedna, powstaje `multi_intent`. To miejsce bywa źródłem błędnego routingu (zapytanie łapane jako `multi_intent` zamiast konkretnej intencji).
- Handlery intencji zwracają `_envelope(...)` — ustandaryzowaną kopertę odpowiedzi (status `OK`/`PARTIAL`/`ERROR`, `data`, `sources_used`).

Obok działa `qbot_query_router.py` — dodatkowa warstwa routingu i budowania „draftów" akcji (np. produkuje capability/draft dla importu GPX).

## 5. Analityczny fallback — Albert (`qbot3/`)

Pytania, których nie obsłuży keyword-router, a które wymagają rozumowania (wzorce: `najlepszy`, `porównaj`, `ile łącznie`, `średni`, `delta`, `czy mój X lepszy`), trafiają do Alberta — orchestratora LLM opartego o Gemini.

- `qbot3/agent_runtime.py` — orkiestracja.
- `qbot3/llm/albert.py` — runner; dla Gemini wymusza `tool_choice='required'` (a nie `'auto'`, bo autowybór narzędzia jest zawodny).
- Model: `QGPT_MODEL=gemini-2.5-flash-lite` (z `.env.local`).

## 6. Wykonanie operacji — action_execute (`qbot_mcp_adapter.py`)

Unified executor wystawiony jako narzędzie `qbot.action_execute`. Schemat wejścia: `action_type` (enum dozwolonych operacji), `payload_json`, `idempotency_key`, `confirm`, `dry_run`, `source`.

Warstwa bezpieczeństwa:

- `_ACTION_EXECUTE_ALLOWLIST` — zbiór dozwolonych `action_type`. Bramka odrzuca wszystko spoza niej, niezależnie od tego, że handler/enum istnieją.
- `_ACTION_REQUIRED_PAYLOAD_FIELDS` — wymagane pola payloadu per akcja.
- `confirm=true` wymagane do zapisu; `dry_run=true` waliduje bez zapisu (zwraca `DRY_RUN`); `idempotency_key` chroni przed duplikatami.
- `_handle_action_execute` dispatchuje do `_action_exec_<akcja>`. `safety_class = WRITE_ONLY_ALLOWLIST`. Akcje read-only (np. profil trasy, analiza POI) zwracają `execution_mode=read_only`, `write_committed=False`.

## 7. Dwa podsystemy (istotne dla zrozumienia całości)

QBot ma faktycznie **dwa tory wykonawcze**, każdy spójny u siebie:

1. **Tor główny (GPT-facing):** `qbot_mcp_adapter.py` + `qbot_query_handler.py` + `qbot_route_tools.py` + `qbot_tool_registry.py` + `qbot_capabilities.py`.
2. **Tor `qbot3/` (Albert):** własny `agent_runtime.py`, `llm/albert.py`, `adapters/mcp_adapter.py`, `tool_registry.py`, `safety.py`.

Te tory potrafią nazywać tę samą operację różnie — np. import GPX to `rwgps_gpx_import` w torze głównym, a `rwgps_route_import_gpx` w `qbot3`. Każdy jest wewnętrznie spójny, ale rozjazd nazw to dług: zaboli, jeśli kiedyś tory zaczną się mostkować.

## 8. Narzędzia (`tools/`)

- **Trasy RWGPS:** import GPX (`rwgps_gpx_import`), eksport GPX (`rwgps_route_export_gpx`), analiza nawierzchni (`rwgps_route_surface_analyze`), podjazdy (`route_climbs`), profil wysokości co N m (`rwgps_route_profile_sample`), analiza POI (`route_poi_analyze`).
- **POI:** `tools/trip_attractions.py` — POI z `section_filter` (food / water / attractions); `tools/rwgps/google_places.py` — wzbogacanie z Google Places.
- **Odżywianie:** log posiłków (add/delete/correct), bilans dzienny.
- **Kalendarz:** przypomnienia i wydarzenia (`qcal_*`).
- **Dokumenty i artefakty:** `qbot_doc_append` / `qbot_doc_replace_section` / `qbot_doc_update`, `qbot_artifact_put` / `qbot_artifact_get`.

## 9. Dane

- **Postgres `qbot_v2`:** `qbot_planning_facts` (rekordy id 5–11 = etapy 1–7 Toskanii). `fact_json` zawiera: `water` (OSM drinking water), `food` (Google Places, bufor 2 km), `attractions` (OSM), `attractions_google` (Google Places, bufor 4 km). Mapowanie etapu na `route_id` robi `_resolve_stage_route_id(stage_n, project_id)`.
- **Artefakty:** ścieżki `canonical/{project_id}/...`; eksporty GPX w `/opt/qbot/artifacts/exports/rwgps/rwgps_<route_id>.gpx`. Uwaga: `qbot_artifact_get` blokuje odczyt rozszerzenia `.gpx` — narzędzia, które potrzebują surowego GPX, czytają plik z dysku bezpośrednio (omijając tę blokadę).
- **Źródła zewnętrzne:** RWGPS (trasy, GPX), Google Places (POI), OSM/Overpass (woda, atrakcje, nawierzchnia).

## 10. Przykładowy przepływ end-to-end

Zapytanie `profil etapu 5 km 21.48-24.55`:

1. GPT wysyła je na `/mcp/` (query).
2. `_resolve_intent` → intencja `rwgps_route_profile_sample` (fraza wstawiona przed `route_climbs`, żeby `podjazdy` jej nie przechwyciło).
3. Parser handlera: `etapu 5` → `_resolve_stage_route_id(5)` → `55395124`; zakres `km 21.48–24.55`; `sample_m` domyślnie 100. (Numer etapu jest kluczem lookupu, nigdy nie trafia jako `route_id` wprost; km i „co N m" są wykluczone z parsowania `route_id`.)
4. Narzędzie czyta GPX z dysku (lub, gdy go nie ma, robi fallback przez eksport RWGPS i normalizuje ścieżkę z metadanych).
5. Liczy profil co 100 m: dystans narastający, interpolacja wysokości na granicach segmentów, przewyższenie, średnie i wygładzone maksymalne nachylenie.
6. Zwraca `_envelope` z `summary` + 31 segmentami; serializacja do JSON wraca do GPT.

Ta sama operacja jawnie: `action_execute` z `action_type=rwgps_route_profile_sample` i payloadem `{route_id, km_from, km_to, sample_m}`.

## 11. Znane kruche miejsca i dług techniczny

- **Routing first-match + `multi_intent`** — łatwo o kolizje fraz i przechwytywanie (np. POI etapu 2 łapane jako `multi_intent` zamiast `route_poi_analyze`). Każdy nowy intent wymaga uwagi na kolejność.
- **Rozjazd nazw importu GPX** między torem głównym (`rwgps_gpx_import`) a `qbot3` (`rwgps_route_import_gpx`).
- **Łatki `patch_*.py` w katalogu prod** (`patch_detect_domains.py`, `patch_domain_exit.py`, `patch_p2_final.py`) — ślad wcześniejszych operacji na `_detect_domains`; do sprzątnięcia.
- **`_resolve_stage_route_id` wpięty tylko w handler profilu** — `route_poi_analyze` mógłby reużyć tego samego resolvera (otwarty TODO; ten sam problem co „podpięcie route_id z planning_facts").
- **Max grade wygładzany po liczbie punktów, nie po dystansie** — wynik zależny od gęstości punktów GPX; przy trasach o innej gęstości warto skontrolować.
- **Krucha wyszukiwarka artefaktów po nazwach** — pewne trafienie daje dopiero ogólne zapytanie typu „artefakty canonical <projekt>".
- **Otwarte TODO:** `rwgps_poi_fetch_google` jako akcja, pełny audyt allowlisty vs schemat GPT (częściowo zrobiony), `artifact_move_shelf`, `planning_fact_update`.

## 12. Zasady pracy z kodem (operacyjne)

- Czytaj plik przed edycją; ustal dokładny string do podmiany.
- Jedna zmiana semantyczna na raz; `ast.parse()` przed zapisem; smoke test po `systemctl restart qbot-api`.
- Patche kopiowane przez `scp`, nie edycja przez heredoc z polskimi znakami.
- Zmiana env w runtime nie wpływa na stałe module-level — restart serwisu.
- Przy złym routingu: sprawdź `_resolve_intent(q)` i kolejność w `INTENT_KEYWORDS`, oraz czy `_detect_domains` nie łapie jako `multi_intent`.
