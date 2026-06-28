# QBOT_RUNTIME_INVENTORY.md — Runtime Inventory

Stan: 2026-05-29  
QBot3/Albert MVP aktywny. QBot2 nieruszony.

---

## A. QBot3 Core

| Komponent | Technologia | Status |
|---|---|---|
| Agent Runtime | `qbot3/agent_runtime.py` | aktywny |
| LLM Provider Interface | `qbot3/llm/base.py` | 3 provider: openai (prod), deepseek (dev), mock (test) |
| Tool Registry | `qbot3/tool_registry.py` | 38 tool descriptions |
| Capability Registry | `qbot3/capabilities/` | 3 active capabilities |
| Plan Validator | `qbot3/plan_validator.py` | CAPABILITY_MISSING support |
| Safety | `qbot3/safety.py` | allowlista, idempotency, audit |
| Memory | `qbot3/memory.py` | JSONL-based |
| Observability | `qbot3/observability.py` | request_id, timer, JSONL log |
| Error Taxonomy | `qbot3/errors.py` | 16 kodów |
| MCP Adapter | `qbot3/adapters/mcp_adapter.py` | 2 publiczne toole |
| Public MCP tools | `qbot.query`, `qbot.action_execute` | tylko te 2 |

### Pre-routed domeny (deterministic pre-router)

| Domeny | Intent | Capability |
|---|---|---|
| daily report, email pipeline, report status | `daily_report_status` | `daily_report_status` |
| gate, furtka, HikConnect, unlock | `gate_status` | `gate_status` |
| hammerhead, garmin sync, transfer, Karoo | `hammerhead_sync_status` | `hammerhead_sync_status` |
| garmin import, ostatni import | `garmin_sync_status` | (tool_registry) |

---

## B. External Q Services / Workflows

### B1. Gate / HikConnect

**Typ**: External Q workflow (osobna usługa systemd, nie core QBot3)

**Produkcyjna ścieżka**:
```
https://qbot.cytr.us/gate/open  (z X-Gate-Token)
  -> Cloudflare DNS
    -> nginx :20181 (qbot.cytr.us)
      -> proxy_pass http://127.0.0.1:8899/gate/open
        -> qbot-qlab-server.service (FastAPI, port 8899)
          -> gate_hikconnect.py
            -> POST https://api.hik-connect.com/v3/users/login/v2
            -> GET/PUT /v3/devconfig/v1/call/{device}/{channel}/remote/unlock
```

**Pliki**:
| Plik | Rola |
|---|---|
| `gate_hikconnect.py` | HikConnect cloud client |
| `qbot_qlab_server.py` | FastAPI server z `/gate/open`, `/gate/status`, `/health` |
| `qbot-qlab-server.service` (systemd) | Uruchamia qbot_qlab_server.py na :8899 |
| Nginx `sites-enabled/q365` | Reverse proxy dla `/gate/*` |

**Historia**: Ngrok był pierwszym/testowym tunelem (`ankle-wool-undusted.ngrok-free.dev`). Produkcja od dawna przez domenę `qbot.cytr.us`. Ngrok (`ngrok-qbot.service`) jest nieaktywny.

**QBot3 adapter**: `gate_status` capability — tylko odczyt `/gate/status`. Nigdy nie woła `/gate/open`. Nie wykonuje unlocku.

**Credentials** (zmienne env):
- `HIKCONNECT_ACCOUNT`, `HIKCONNECT_PASSWORD` — login do HikConnect cloud
- `GATE_TOKEN` — token uwierzytelniający dla `/gate/open`
- `GATE_DEVICE_SERIAL`, `GATE_LOCK_CHANNEL`, `GATE_LOCK_INDEX` — konfiguracja urządzenia
- `GATE_RATE_LIMIT_SEC` — limit szybkości (15s w .env, 60s w .env.local)

Wszystkie credentials i ścieżki pozostają bez zmian. QBot3 nie modyfikuje ich.

---

### B2. Hammerhead/Karoo → Garmin Activity Transfer

**Typ**: External Q workflow (cron, nie core QBot3)

**Wyzwalacz**: Cron co 10 minut:
```
*/10 * * * * /opt/qbot/app/scripts/run_hammerhead_garmin_sync.sh
*/10 * * * * /opt/qbot/app/scripts/run_hammerhead_garmin_sync_profile.sh michal
*/10 * * * * /opt/qbot/app/scripts/run_hammerhead_garmin_sync_profile.sh user2 (pusty)
*/10 * * * * /opt/qbot/app/scripts/run_hammerhead_garmin_sync_profile.sh user3 (pusty)
```

**Przepływ**:
```
cron -> run_hammerhead_garmin_sync_profile.sh
  -> source config/profiles/michal.env
  -> qbot-hammerhead-sync --profile michal --upload
    -> hammerhead_auth.py (JWT token refresh)
    -> GET Hammerhead API -> list activities
    -> dedup (state/michal_processed_hammerhead_activities.json)
    -> download FIT
    -> qbot-fit-rewrite (manufacturer hammerhead -> Tacx)
    -> strict validation
    -> garmin_auth.py -> upload_activity() -> Garmin Connect
```

**Pliki**:
| Plik | Rola |
|---|---|
| `qbot-hammerhead-sync` | Główny orchestrator transferu (649 linii) |
| `hammerhead_auth.py` | Zarządzanie tokenem JWT Hammerhead |
| `garmin_auth.py` | Autentykacja i upload do Garmin Connect |
| `qbot-fit-rewrite` | Przepisanie FIT: manufacturer hammerhead → Tacx |
| `scripts/run_hammerhead_garmin_sync*.sh` | Cron entrypointy |
| `config/profiles/michal.env` | Konfiguracja profilu |
| `state/*_processed_hammerhead_activities.json` | Stan dedupu |
| `outgoing/michal/` | Pliki FIT, proxy, raporty |

**Stan obecny**: 11/16 aktywności przesłanych. Ostatnie 5 failed — Garmin auth issue (niezależne od QBot3).

**QBot3 adapter**: `hammerhead_sync_status` capability — tylko odczyt configu, stanu dedupu, logów. Nigdy nie woła `--upload`. `dry_run_supported=true`.

**Credentials** (zmienne env):
- `HAMMERHEAD_REFRESH_TOKEN`, `HAMMERHEAD_TOKENSTORE` — token Hammerhead
- `GARMIN_TOKENSTORE` — token Garmin (katalog chroniony: `drwx------ root root`)
- `QBOT_GARMIN_SYNC_MODE=upload` — wymagany do działania cron'a

Wszystkie credentials, tokeny, ścieżki i crony pozostają bez zmian.

---

## C. Adapters / Status / Control (Używane przez QBot3)

| Adapter | Typ | Obserwuje | Bezpieczeństwo |
|---|---|---|---|
| `daily_report_status` | capability (READ_ONLY_FILE) | daily_report_sent.json, daily_report.log | tylko odczyt |
| `gate_status` | capability (READ_ONLY_API) | /gate/status endpoint | tylko odczyt, nigdy /gate/open |
| `hammerhead_sync_status` | capability (READ_ONLY_FILE) | config, state, log | tylko odczyt, nigdy --upload |

Żaden adapter nie wykonuje akcji produkcyjnych. Są to cienkie warstwy do obserwacji i diagnostyki.

---

## D. Albert's Workspace — autonomia capability lifecycle

Gdy Albert rozpoznaje intencję, ale nie ma pasującej active capability:
1. **PROPOSE** — tworzy proposal w `workspace/proposals/`
2. **DRAFT** — generuje manifest + test skeleton w `workspace/drafts/`
3. **TEST** — uruchamia harness, sprawdza schema, secrets, side effects
4. **ACTIVATE** — promuje do active po przejściu testów
5. **REPORT** — dokumentuje w `workspace/reports/`

### Struktura

```
qbot3/workspace/
├── __init__.py          # workspace lifecycle API
├── proposals/           # CAPABILITY_MISSING → proposal.json
├── drafts/              # wygenerowane capability .py
├── tests/               # wygenerowane test .py
├── activation/          # logi promocji (promote → active)
└── reports/             # raporty z testów i aktywacji
```

### Safety classes rozszerzone

| Klasa | Auto-build | Przykład |
|---|---|---|
| `READ_ONLY_CONFIG` | ✅ | llm_status (env vars, masked) |
| `READ_ONLY_FILE` | ✅ | daily_report_status |
| `READ_ONLY_DB` | ✅ | garmin_sync_status |
| `READ_ONLY_HTTP_STATUS` | ✅ | gate_status |
| `WRITE_DRAFT` | ❌ | nutrition_log_add (proposal only) |
| `WRITE_EXECUTE` | ❌ | wymaga confirm |
| `DESTRUCTIVE_BLOCKED` | ❌ | delete, raw SQL |

### Życie capability lifecycle

```
proposed → draft → tested → active → disabled
```

- `proposed`: planner wie, że capability brakuje; proposal w workspace
- `draft`: wygenerowany manifest + test skeleton; nieużywane w qbot.query
- `tested`: przeszło harness; gotowe do aktywacji
- `active`: używane przez qbot.query
- `disabled`: wyłączone, nieużywane

### Domain-tool mismatch detection

Plan validator wykrywa gdy LLM wybiera generic tools (system_logs_recent, system_env_status) zamiast dedykowanych domenowych. Wtedy zwraca CAPABILITY_MISSING z propozycją zamiast cichego użycia złego narzędzia.

---

## D. Docelowy Centralny Q Secrets Store

### Problem

Obecnie sekrety są rozrzucone:

| Workflow | Lokalizacja | Owner | Problem |
|---|---|---|---|
| Garmin tokens | `/opt/qbot/app/.garmin_tokens/*/` | root/qbot | Wiąże sekrety z katalogiem QBot |
| Hammerhead tokens | `/opt/qbot/app/.hammerhead_tokens/` | qbot/qbot | Wiąże sekrety z katalogiem QBot |
| HikConnect | `.env` + `.env.local` (zmienne env) | root/qbot | Sekrety w plikach env w /opt/qbot/app/ |
| Telegram token | `.env.local` | root/qbot | Sekrety w plikach env w /opt/qbot/app/ |
| Profile configs | `config/profiles/michal.env` | root/root | Zawiera refresh tokeny |

To utrudnia odseparowanie workflow (gate, hammerhead, QBot3) — wszystkie muszą współdzielić ten sam katalog i usera.

### Docelowa architektura: `/opt/q/secrets/`

```
/opt/q/secrets/
├── garmin/
│   ├── michal          (plik z tokenem, 640)
│   └── legacy -> /opt/qbot/app/.garmin_tokens/   (symlink na czas migracji)
├── hammerhead/
│   ├── michal          (plik z refresh tokenem, 640)
│   └── legacy -> /opt/qbot/app/.hammerhead_tokens/
├── hikconnect/
│   ├── account         (plik z loginem, 600)
│   ├── password        (plik z hasłem, 600)
│   └── gate_token      (plik z GATE_TOKEN, 600)
├── telegram/
│   └── bot_token       (plik z TELEGRAM_BOT_TOKEN, 600)
└── README.md           (opis struktury i zasad)
```

### Model ownera/grupy

```
/opt/q/                 root:qsvc   755
/opt/q/secrets/         root:qsecrets  750
/opt/q/secrets/garmin/  root:qsecrets  750
/opt/q/secrets/garmin/michal  root:qsecrets  640
```

| Obiekt | Wartość |
|---|---|
| Katalog główny | `/opt/q/` owner `root:qsvc`, mode 755 |
| Secrets root | `/opt/q/secrets/` owner `root:qsecrets`, mode 750 |
| Katalogi per-service | owner `root:qsecrets`, mode 750 |
| Pliki z sekretami | owner `root:qsecrets`, mode 640 |
| Pliki czytelne dla grupy | mode 640 = owner rw, group r, other — nic |

### Model dostępu

Procesy dostają dostęp przez grupę `qsecrets`, nie przez `root`:

| Proces | Grupa | Czyta |
|---|---|---|
| `qbot-api.service` (user qbot) | qbot + qsecrets | garmin (tylko status), hammerhead (tylko status) |
| `qbot-hammerhead-sync` (user root) | root + qsecrets | garmin, hammerhead (pełny dostęp) |
| `qbot-qlab-server.service` (user qbot) | qbot + qsecrets | hikconnect (login + hasło) |
| Admin/opiekun | — | wszystkie |

### Sposób odczytu

Workflow czytają sekrety przez zmienne env lub bezpośrednio z pliku:

```bash
# Przykład: bash profile
GARMIN_TOKENSTORE=/opt/q/secrets/garmin
HAMMERHEAD_TOKENSTORE=/opt/q/secrets/hammerhead/michal
HIKCONNECT_ACCOUNT_FILE=/opt/q/secrets/hikconnect/account
HIKCONNECT_PASSWORD_FILE=/opt/q/secrets/hikconnect/password
```

```python
# Przykład: Python
def read_secret(path: str) -> str:
    return Path(path).read_text().strip()

os.environ["HIKCONNECT_ACCOUNT"] = read_secret("/opt/q/secrets/hikconnect/account")
```

### Kompatybilność wsteczna

- Stare ścieżki (`/opt/qbot/app/.garmin_tokens/`) pozostają jako **symlinki** do `/opt/q/secrets/` na czas migracji
- Proces, który nie został jeszcze przekonfigurowany, dalej działa przez starą ścieżkę
- Nowe procesy czytają z `/opt/q/secrets/` przez zmienne env
- Flaga `QBOT3_SECRETS_STORE=/opt/q/secrets` przełącza QBot3 na nową ścieżkę

### Plan migracji (do wykonania po zatwierdzeniu)

1. **Przygotowanie struktury** (bez sekretów):
   ```bash
   mkdir -p /opt/q/secrets/{garmin,hammerhead,hikconnect,telegram}
   chown root:qsecrets /opt/q/secrets /opt/q/secrets/*
   chmod 750 /opt/q/secrets /opt/q/secrets/*
   ```

2. **Dodanie grupy `qsecrets`**:
   ```bash
   groupadd --system qsecrets
   usermod -aG qsecrets qbot
   ```

3. **Symlinki dla starej ścieżki**:
   ```bash
   ln -s /opt/q/secrets/garmin /opt/qbot/app/.garmin_tokens
   ln -s /opt/q/secrets/hammerhead /opt/qbot/app/.hammerhead_tokens
   ```

4. **Kopiowanie sekretów** (tylko po zatwierdzeniu MS):
   ```bash
   cp /opt/qbot/app/.garmin_tokens/michal/garmin_tokens.json /opt/q/secrets/garmin/michal_tokens
   ```

5. **Aktualizacja zmiennych env w profilach**:
   - `config/profiles/michal.env`: `GARMIN_TOKENSTORE=/opt/q/secrets/garmin`
   - `config/profiles/michal.env`: `HAMMERHEAD_TOKENSTORE=/opt/q/secrets/hammerhead/michal`
   - `.env.local`: `HIKCONNECT_ACCOUNT` → `HIKCONNECT_ACCOUNT_FILE`

6. **Aktualizacja QBot3 adapterów**: zmiana ścieżek odczytu w capability

7. **Test regresyjny**: smoke, gate status, hammerhead dry-run

8. **Usunięcie starych plików** po potwierdzeniu, że wszystko działa

### Secrets migration: DUPLICATE → SWITCH → VERIFY → CLEANUP

**Stan obecny: DUPLICATE COMPLETE** (2026-05-29)

Stare ścieżki nietknięte. Nowy store istnieje obok. Żaden workflow nie został przełączony.

#### Struktura `/opt/q/secrets/`

```
/opt/q/secrets/          root:qsecrets  750
├── garmin/              root:qsecrets  750
│   ├── legacy_tokens.json        640  (kopia z .garmin_tokens/garmin_tokens.json)
│   └── michal_tokens.json        640  (kopia z .garmin_tokens/michal/garmin_tokens.json)
├── hammerhead/          root:qsecrets  750
│   ├── legacy_tokens.json        640  (kopia z .hammerhead_tokens/hammerhead_tokens.json)
│   └── michal_tokens.json        640  (kopia z .hammerhead_tokens/michal.json)
├── hikconnect/          root:qsecrets  750
│   └── env_reference              640  (kopia .env dla HIKCONNECT/GATE vars)
├── telegram/            root:qsecrets  750
│   └── bot_token                  640  (kopia TELEGRAM_BOT_TOKEN z .env.local)
├── rwgps/               root:qsecrets  750
│   └── env_reference              640  (kopia RWGPS vars z .env)
├── xert/                root:qsecrets  750
│   └── env_reference              640  (kopia XERT vars z .env)
```

#### Preferencja źródła

Flaga środowiskowa: `Q_SECRETS_STORE` lub `QBOT3_SECRETS_STORE` (domyślnie `/opt/q/secrets`).

Logika (`qbot3/secrets_reader.py`):
```
1. jeśli plik istnieje w Q_SECRETS_STORE → użyj
2. jeśli nie → fallback do legacy path (/opt/qbot/app/.garmin_tokens/ itd.)
3. jeśli i tam nie ma → zwróć None
```

#### Status przełączenia per workflow

| Workflow | Stara ścieżka | Nowa ścieżka | Fallback | Status |
|---|---|---|---|---|
| **Garmin tokens** | `/opt/qbot/app/.garmin_tokens/` | `/opt/q/secrets/garmin/` | old path intact | DUPLICATED (not switched) |
| **Hammerhead tokens** | `/opt/qbot/app/.hammerhead_tokens/` | `/opt/q/secrets/hammerhead/` | old path intact | DUPLICATED (not switched) |
| **HikConnect / Gate** | `.env` / `.env.local` (env vars) | `/opt/q/secrets/hikconnect/` | old path intact | DUPLICATED (not switched) |
| **Telegram** | `.env.local` (env var) | `/opt/q/secrets/telegram/` | old path intact | DUPLICATED (not switched) |
| **RWGPS** | `.env` (env vars) | `/opt/q/secrets/rwgps/` | old path intact | DUPLICATED (not switched) |
| **Xert** | `.env` (env vars) | `/opt/q/secrets/xert/` | old path intact | DUPLICATED (not switched) |

#### Plan przełączania (SWITCH phase — do wykonania po zatwierdzeniu)

| Krok | Workflow | Test |
|---|---|---|
| A | QBot3 read-only status checks (garmin, hammerhead) | `qbot.query` status — czyta z `/opt/q/secrets/` |
| B | Hammerhead/Garmin dry-run | `--dry-run` bez uploadu |
| C | Gate status | `qbot.query` gate status przez nowy store |
| D | Realne akcje | po osobnej zgodzie |

#### Zasady

- Żadne sekrety nie są przechowywane w repo git
- Pliki env (`.env`, `.env.local`) nie zawierają sekretów — tylko ścieżki do `/opt/q/secrets/`
- Procesy dostają dostęp przez grupę `qsecrets`, a nie przez `root`
- Logi nie zawierają sekretów (istniejące redakcje w `gate_hikconnect.py` pozostają)
- QBot3 capability czytają tylko to, co konieczne do statusu — nie pełne tokeny
