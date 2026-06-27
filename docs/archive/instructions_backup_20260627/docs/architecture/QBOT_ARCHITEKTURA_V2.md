# QBot — architektura docelowa (v2)

Stan: 2026-06-15. Zastępuje: `QBOT_ARCHITEKTURA.md` (opis stanu sprzed przebudowy) i `QBOT_PRZEBUDOWA.md` (plan przebudowy, częściowo zrealizowany, częściowo zdezaktualizowany). **Ten dokument to jedyne źródło prawdy o architekturze QBot.**

---

## 1. Czym jest QBot

Osobisty asystent rowerowo-zdrowotny. Backend na VPS (mikrus, `olga181`), serwis `qbot-api` (uvicorn, port 8002). Dane w PostgreSQL (schemat `qbot_v2`) i artefaktach plikowych. Główny klient: Custom GPT (ChatGPT) przez MCP. Drugi kanał: SSH/CLI.

## 2. Architektura docelowa: Albert-first

### Zasada nadrzędna

**Albert (LLM z pętlą narzędziową) jest jedynym mózgiem systemu.** Dostaje zapytanie w języku naturalnym, sam wybiera narzędzia, sam czyta dane, sam pisze do bazy, sam zwraca wynik. GPT wystawia jedno narzędzie (`qbot.query`) i nie musi znać wewnętrznych mechanizmów.

```
Custom GPT
  │  qbot.query("dodaj popcorn 1100 kcal do wczoraj")
  ▼
Albert (mocny model: gemini-2.5-flash lub gpt-4.1-mini)
  │  tool_choice = required
  │  pełny zestaw narzędzi: nutrition, routes, calendar, wellness, artifacts
  │  pętla: plan → call tool → inspect result → next step → answer
  │  limit kroków: 10-15 (mocny model nie marnuje)
  │  sam pisze do bazy (nutrition_intake_add, calendar_event_add, ...)
  ▼
qbot.query zwraca gotową odpowiedź z wynikiem zapisu
  │
  ▼
Custom GPT wyświetla użytkownikowi
```

### Dlaczego tak

Poprzednia architektura opierała się na keyword routerze (~250 intentów, first-match) z Albertem jako fallbackiem-na-błędzie i osobnym Plannerem v2 dla tras. To generowało ciągłe problemy:

- Keyword router to ręcznie pisany parser języka naturalnego — każda nowa fraza, odmiana polska, kolizja wymaga ręcznej łatki. To praca, do której wymyślono LLM-y.
- First-match = wyrok. Dopasowany keyword kończy routing, nawet jeśli trafił źle.
- Albert jako fallback nie widzi sukcesów — łapie tylko to, czego keyword nie złapał.
- Planner v2 (mocny model) istniał osobno tylko dla tras, reszta domen miała słabego Alberta (flash-lite) lub nic.

Decyzja (2026-06-15): **odwrócenie priorytetów**. Albert z mocnym modelem jako primary, nie fallback. Keyword router opcjonalny jako tania optymalizacja, nie krytyczna ścieżka.

### Co to oznacza w praktyce

- **Jedno narzędzie dla GPT:** `qbot.query`. Zero `qbot.action_execute` w `tools/list` (Albert finalizuje zapisy sam, wewnątrz query).
- **Jeden model, jeden orchestrator:** Albert z pętlą narzędziową. Planner v2 znika jako osobny byt — jego narzędzia i kontrakty wchodzą do Alberta.
- **Keyword router = opcjonalna optymalizacja kosztowa:** może łapać trywialne odczyty (bilans dnia, help) deterministycznie za 0 zł i 5 ms. Ale jeśli nie złapie — Albert i tak obsłuży. Keyword NIE jest bramką wejściową, NIE blokuje Alberta, NIE decyduje o fallbackach.

## 3. Albert — szczegóły

### Konfiguracja

```bash
# .env.local
QGPT_MODEL=gemini-2.5-flash          # mocny model (był: gemini-2.5-flash-lite)
QBOT_ALBERT_MAX_STEPS=12             # limit kroków (był: 5)
QBOT3_ENABLED=1                      # tor qbot3 aktywny (jak jest)
QBOT_LLM_ORCHESTRATOR=1              # orchestrator włączony (jak jest)
```

### Narzędzia Alberta (zunifikowany tool registry)

Albert musi mieć dostęp do WSZYSTKICH narzędzi, nie podzbioru per domena:

**Żywienie (write):**
- `nutrition_intake_add` — zapis posiłku (data, nazwa, kcal, makra)
- `nutrition_intake_delete` — usunięcie wpisu
- `nutrition_intake_correct` — korekta wpisu
- `nutrition_day_summary` — bilans dnia
- `nutrition_write_resolve` — estymacja makr z opisu produktu

**Trasy (read + write):**
- `route_find` — wyszukiwanie trasy po nazwie/parametrach
- `route_fetch_gpx` — pobranie GPX (z sanity-check świeżości)
- `route_profile` — profil wysokości co N m
- `route_climbs` — lista podjazdów
- `route_surface` — analiza nawierzchni
- `route_poi_analyze` — POI per stage (water/food/attractions)
- `planning_fact_get` — odczyt faktów planowania
- `planning_fact_update` — edycja faktów planowania
- `stage_gpx_analyze` — analiza GPX etapu z sanity-check vs planning_facts

**Kalendarz/przypomnienia:**
- `calendar_event_add`, `calendar_event_update`, `calendar_event_cancel`
- `reminder_add`

**Wellness:**
- `garmin_diagnostics` — dane z Garmin Connect
- `xert_status` — metryki treningowe Xert

**Artefakty/dokumenty:**
- `artifact_get`, `artifact_put`
- `doc_append`, `doc_replace_section`, `doc_update`

**Narzędzia diagnostyczne:**
- `daily_report_status` — raport poranny

### Pętla Alberta

```python
# qbot3/agent_runtime.py — docelowy flow
def orchestrate_query(question, context):
    messages = [system_prompt, user_message(question)]
    for step in range(MAX_STEPS):
        response = llm.chat(messages, tools=ALL_TOOLS, tool_choice="required")
        if response.is_final_answer:
            return response.text
        tool_result = execute_tool(response.tool_call)
        messages.append(tool_result)
    return "Przekroczono limit kroków"
```

### Niezmienniki (kod, nie LLM)

Narzędzia Alberta zawierają wbudowane walidacje (nie polegamy na LLM):

- **Świeżość artefaktu:** `updated_at` artefaktu vs API → refetch gdy starszy.
- **Sanity-check:** dystans/przewyższenie z GPX vs metadane API (tolerancja 5%) → błąd, nie odpowiedź.
- **Idempotencja:** klucz deterministyczny, duplikaty odrzucane.
- **Stage-resolver:** stage=N → `planning_facts.route_stages` → route_id (deterministycznie, nie z LLM).

### Czego Albert NIE robi

- NIE generuje kodu / nie edytuje plików na serwerze.
- NIE commituje do git / nie restartuje serwisów.
- NIE odpowiada z pamięci — zawsze woła narzędzia.

## 4. MCP — warstwa klienta

Custom GPT łączy się na `https://qbot.cytr.us/mcp/` (Bearer token, JSON-RPC 2.0). Bridge (`/root/qbot-mcp/server.py`, port 20181) jest czystym proxy do `qbot-api:8002`.

### tools/list

Docelowo **jedno narzędzie:**

```json
{
  "name": "qbot.query",
  "description": "Wywołaj PRZED każdą odpowiedzią. Przekaż oryginalne pytanie użytkownika bez modyfikacji. Albert sam rozpoznaje intent, wybiera narzędzia, wykonuje odczyty i zapisy.",
  "inputSchema": {
    "properties": {
      "query": {"type": "string"},
      "context": {"type": "string"}
    },
    "required": ["query"]
  }
}
```

`qbot.action_execute` **nie jest potrzebny w tools/list** — Albert finalizuje zapisy sam. `action_execute` zostaje jako endpoint CLI/admin (np. ręczny wpis przez SSH), ale GPT go nie widzi i nie potrzebuje.

### Instrukcje Custom GPT

Uproszczone (Albert robi robotę):

```
[OBOWIĄZKOWE] Zawsze najpierw wywołaj qbot.query z oryginalnym pytaniem użytkownika.
NIE modyfikuj pytania. NIE odpowiadaj z własnej wiedzy.
Gdy qbot.query zwróci wynik — przedstaw go użytkownikowi.
Gdy qbot.query zwróci błąd — poinformuj użytkownika.
NIE próbuj samodzielnie wołać action_execute ani innych narzędzi.
Albert sam obsługuje zapisy, estymacje, trasy, kalendarz.
```

## 5. Dane

- **PostgreSQL `qbot_v2`:** `qbot_planning_facts` (etapy, mapowanie stage→route), `intake_logs`/`intake_items` (żywienie), `calendar_events`, `reminders`, artefakty.
- **Artefakty plikowe:** `/opt/qbot/artifacts/` (canonical, projects, exports). GPX: `/opt/qbot/artifacts/exports/rwgps/rwgps_<route_id>.gpx`.
- **Źródła zewnętrzne:** RWGPS, Google Places, OSM/Overpass, Garmin Connect, Xert, OWM.

## 6. Etap 4 — pętla samonaprawy (zrealizowane fundamenty)

Niezależne od routingu, działają już:

- **`qbot_v2.change_log`** — audit trail KAŻDEGO action_execute (kind, action_type, status, entity_ref, payload, result excerpt). Best-effort, nigdy nie psuje operacji.
- **`qbot_v2.incident_tickets`** — automatyczne tickety na ERROR i złamany niezmiennik (sanity-check). Capture: error, traceback, log_tail, env_snapshot.
- **`/incydenty`** — komenda listująca otwarte incydenty + gotowy-do-wklejenia prompt diagnostyczny do Terminus.
- **Dedup 6h** — identyczny incydent nie zalewa tabeli.

Następne kroki Etapu 4 (NIE zrealizowane): hook patchy do change_log (kind=patch), auto-propozycja agenta, human-in-the-loop apply.

## 7. Keyword router — rola docelowa

**Opcjonalna warstwa optymalizacji kosztowej**, nie krytyczna ścieżka. Może obsłużyć trywialne odczyty (bilans, help, profil etapu) tanio i szybko. Ale:

- NIE jest bramką wejściową — Albert jest primary.
- NIE blokuje Alberta — jeśli keyword nie złapie, Albert obsłuży.
- NIE decyduje o fallbackach/plannerach — nie ma fallbacków, jest Albert.
- NIE jest miejscem dodawania nowych fraz — nowe domeny wchodzą jako narzędzia Alberta, nie jako keywordy.

Docelowo keyword router może zniknąć całkowicie lub zostać zredukowany do ~20 trywialnych odczytów. Nie jest to priorytet — po upgrade Alberta keyword jest nieistotny.

## 8. Co znika

| Element | Status | Powód |
|---------|--------|-------|
| Planner v2 (`core/planner.py`, `plan_routes()`) | DO USUNIĘCIA | Narzędzia Plannera wchodzą do Alberta; osobny orchestrator tras niepotrzebny |
| `QBOT_DISABLE_ALBERT_FALLBACK` flaga | DO USUNIĘCIA | Albert jest primary, nie fallback — nie ma czego wyłączać |
| `qbot.action_execute` w tools/list GPT | DO USUNIĘCIA z tools/list | Albert finalizuje zapisy sam; endpoint zostaje dla CLI/admin |
| `is_route_domain_query()` / domena otwarta vs zamknięta | DO USUNIĘCIA | Nie ma podziału na domeny — Albert obsługuje wszystkie |
| `should_use_albert_fallback()` / `fallback_policy.py` | DO USUNIĘCIA | Albert nie jest fallbackiem |
| `_looks_like_meal_commit()` / `_looks_like_inline_meal_log()` | DO USUNIĘCIA | Keyword guardy niepotrzebne gdy Albert jest primary |
| ~250 intentów w INTENT_KEYWORDS | REDUKCJA do ~20 | Optymalizacja kosztowa, nie krytyczna ścieżka |

## 9. Plan wdrożenia (etapy, każdy zostawia system działający)

**Krok 1 — Upgrade modelu Alberta** (natychmiastowy efekt, jedna zmiana w .env.local):
- `QGPT_MODEL=gemini-2.5-flash` (z flash-lite)
- `MAX_STEPS` 5 → 12
- Test: estymacja + zapis posiłku end-to-end przez qbot.query

**Krok 2 — Albert = primary** (odwrócenie flow):
- Zapytanie idzie NAJPIERW do Alberta, keyword router opcjonalny pre-filter
- Usunięcie fallback_policy.py, flag QBOT_DISABLE_ALBERT_FALLBACK
- Usunięcie podziału na domeny otwarte/zamknięte
- Test: wszystkie dotychczasowe scenariusze (żywienie, trasy, kalendarz)

**Krok 3 — Zunifikowany tool registry:**
- Narzędzia Plannera v2 (stage-resolver, sanity-check, świeżość) → do tool registry Alberta
- Usunięcie `core/planner.py` / `plan_routes()`
- Test: scenariusze trasowe (profil etapu, POI, import GPX)

**Krok 4 — Uproszczenie MCP:**
- Usunięcie `qbot.action_execute` z tools/list (Albert finalizuje sam)
- Uproszczenie instrukcji Custom GPT
- Test: pełny cykl GPT → qbot.query → Albert → zapis → odpowiedź

**Krok 5 — Porządki:**
- Redukcja keyword routera do ~20 trywialnych intentów
- Usunięcie martwego kodu (guardy, fallbacki, planner)
- Aktualizacja /help

## 10. Infrastruktura (bez zmian)

- VPS: `olga181.mikrus.xyz`, port 10181, user `root`
- App: `/opt/qbot/app/`, venv: `.venv/bin/python3`
- Serwisy: `qbot-api.service` (8002), `qbot-mcp-bridge.service` (20181/public)
- Public MCP: `https://qbot.cytr.us/mcp/`
- Bridge: `/root/qbot-mcp/server.py` (czysty proxy do 8002)
- DB: PostgreSQL, schemat `qbot_v2`, env z `/etc/qbot/qbot-api.env` + `/opt/qbot/app/.env.local`
- Artefakty: `/opt/qbot/artifacts/`
- QExt2: osobne repo `github.com:QbotMS/QExt2`, niezależny system

## 11. Zasady pracy z kodem (bez zmian)

- Czytaj plik przed edycją; ustal dokładny string do podmiany.
- Jedna zmiana semantyczna na raz; `ast.parse()` przed zapisem; smoke test po `systemctl restart qbot-api`.
- Patche kopiowane przez `scp`, nie heredoc z polskimi znakami.
- Zmiana env w runtime nie wpływa na stałe module-level — restart serwisu.
- Backup timestampowany do `_bak_archive/` przed każdą edycją.

## 12. Kluczowe pliki (aktualne)

| Plik | Rola | Przyszłość |
|------|------|------------|
| `qbot3/agent_runtime.py` | Pętla Alberta (orchestrate_query) | **GŁÓWNY plik — tu siedzi logika** |
| `qbot3/llm/albert.py` | Runner modelu (Gemini) | Zostaje |
| `qbot3/tool_registry.py` | Narzędzia Alberta | **Rozszerzyć o narzędzia Plannera** |
| `qbot3/adapters/mcp_adapter.py` | Żywy MCP adapter (tor qbot3) | Upraszczać |
| `qbot3/safety.py` | Allowlista, walidacja | Zostaje |
| `core/change_log.py` | Audit trail | Zostaje |
| `core/incidents.py` | Tickety incydentów | Zostaje |
| `core/planner.py` | Planner v2 tras | **DO USUNIĘCIA (narzędzia → Albert)** |
| `qbot_query_handler.py` | Keyword router (~250 intentów) | **Redukcja do ~20 lub usunięcie** |
| `qbot_mcp_adapter.py` | MCP adapter (tor główny, NIEAKTYWNY) | Martwy kod gdy QBOT3_ENABLED=1 |
| `qbot3/fallback_policy.py` | Logika fallbacków | **DO USUNIĘCIA** |

## 13. Tor qbot3 vs tor główny (wyjaśnienie)

`qbot_api.py:1308` sprawdza `QBOT3_ENABLED`: gdy =1, cały ruch idzie przez `qbot3/adapters/mcp_adapter.py` → `qbot3/agent_runtime.py`. Tor główny (`qbot_mcp_adapter.py` + `qbot_query_handler.py`) jest **martwy na produkcji** — istnieje w kodzie, ale nie obsługuje żadnego ruchu. Wszelkie zmiany muszą iść w tor qbot3, nie w tor główny.

---

*Dokumenty zastąpione: QBOT_ARCHITEKTURA.md (opis stanu sprzed przebudowy — nieaktualny), QBOT_PRZEBUDOWA.md (plan przebudowy — częściowo zrealizowany, reszta zastąpiona przez Albert-first). RIDEPHOTO_QBOT_MODUL_SPEC.md pozostaje aktualny (niezależny od routingu).*
