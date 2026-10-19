# Aktualizacje (SETUP > Połączenia > Aktualizacje)

Od 2026-10-19 (sesja aktualizacje-1910). Strona tylko **informuje** — niczego nie instaluje.

## Co pokazuje
- **System Ubuntu** (apt: Ubuntu + nodesource/Node.js + cloudflared): oczekujące pakiety, w tym poprawki bezpieczeństwa,
  czy wymagany restart (`/var/run/reboot-required`), czy działa automat `unattended-upgrades` i kiedy ostatnio.
- **Biblioteki Python** w 4 środowiskach: QBot (`/opt/qbot/app/.venv`), mosty MCP (`/root/qbot-mcp/venv`), Q365, Cronometer.
  Nieaktualne (`pip list --outdated`) + **znane luki** z bazy OSV.dev (api.osv.dev, ekosystem PyPI), z wersją, która je poprawia.
- Ta sama biblioteka w kilku środowiskach = jedna pozycja (z listą środowisk i wersji).

## Ocena
- **pilne** — znana luka w bibliotece sieciowej/bezpieczeństwa (lista `KEY_LIBS` w skrypcie: starlette, fastapi, uvicorn, mcp,
  cryptography, PyJWT, python-multipart, urllib3, requests, httpx, anyio, pillow, …); poprawka bezpieczeństwa systemu czeka > 2 dni;
  restart wymagany > 7 dni.
- **zalecane** — luka w bibliotece pomocniczej (pip, setuptools, Pygments, …), zwykła aktualizacja systemu, świeża poprawka bezpieczeństwa.
- **może poczekać** — nowsza wersja bez znanej luki.
- W zakładce **Status** wiersz „Aktualizacje”: żółty przy pozycjach pilnych (zaległość to nie awaria, więc nigdy czerwony).

## Generator promptu dla Claude
Przycisk **„Kopiuj prompt dla Claude”** kopiuje do schowka gotowe zadanie do wklejenia w nowej rozmowie w projekcie QBot:
start od CONTEXT.md → **1. TEST** (kandydat w osobnym venv, pip check, testy) → **2. ROZPATRZENIE** (czy luka dotyczy użycia w QBot,
changelog, ograniczenia zależności) → **3. PROPOZYCJA** (kolejność, docelowe wersje, plan cofnięcia, weryfikacja) — z zakazem instalacji
na produkcji bez zgody. Pełna lista pozycji w prompcie (także „może poczekać”). Podgląd tekstu pod listą.

## Jak działa
- `scripts/updates_check.py` (root): `apt-get update` + `apt list --upgradable`, pip w każdym venv (jako właściciel venv), OSV querybatch
  + szczegóły luk. Wynik: `state/updates.json` (644, qbot). Czas ok. 2–3 min.
- Uruchamianie: `qbot-updates-check.timer` codziennie 05:15 (Persistent) oraz na żądanie: przycisk „Sprawdź teraz” →
  `POST /api/setup/updates/refresh` zapisuje `state/updates.request` → `qbot-updates-check.path` (root) startuje usługę
  (strona web działa jako qbot i nie może sama uruchomić zadania roota).
- API: `GET /api/setup/updates` (qbot_status_api.py, tylko właściciel). Strona: `/opt/qbot/web/public/aktualizacje.html` (ramka w setup.html).
- `first_seen` w JSON: od kiedy pozycja systemowa czeka (do oceny „> 2 dni”).

## Obsługa
```bash
ssh q systemctl start --no-block qbot-updates-check     # sprawdź teraz
ssh q journalctl -u qbot-updates-check -n 20 --no-pager
ssh q systemctl list-timers qbot-updates-check.timer
```

## Jak wdrażać aktualizacje bibliotek (metoda sprawdzona 19.10.2026)
Narzędzia: `/opt/qbot/artifacts/upd-1910/` — `helper.py` (lista docelowych wersji + wymuszone zależności + usuwane pakiety),
`run_test.sh [srodowiska]` (TEST w osobnych venv, nic nie rusza na produkcji), `deploy.sh` (WDROŻENIE, tylko po zgodzie Michała).
Oba uruchamiane jako root w tle (`ssh q 'nohup bash … > log 2>&1 &'`), nie przez dev_shell_exec.
1. TEST: zapis `pip freeze --all` → kandydat (najmniejszy skok usuwający luki, bez zmiany głównej wersji bez potrzeby) → nowy venv →
   `pip check` → importy usług stary vs nowy venv → testy QBota stary vs nowy (wynik musi być identyczny).
2. Konflikty zależności sprawdzać od razu dla całej listy (metadane PyPI), nie po jednym na przebieg.
3. WDROŻENIE: kolejność mosty MCP → QBot → Cronometer → Q365; restart tylko działających usług danego venv (wykrywane z ExecStart,
   bez zadań oneshot); przy błędzie automatyczne cofnięcie środowiska z `<env>.freeze.before.txt` i stop.

## Historia wdrożeń
### 19.10.2026 — wszystkie 13 pilnych + zalecane (sesja aktualizacje-1910)
- Wersje: anyio 4.14.2, cryptography 50.0.2, mcp 1.30.0 (zostaje 1.x), PyJWT 2.15.1, python-multipart 0.0.32, starlette 1.3.1,
  urllib3 2.8.0, pillow 12.3.0, aiohttp 3.14.5, requests 2.33.1, garminconnect 0.3.19, idna 3.15, multidict 6.9.1;
  zalecane: pip 26.2.1, pydantic-settings 2.14.2, python-dotenv 1.2.4, setuptools 83.0.0, fsspec 2026.6.0, GitPython 3.1.62,
  Pygments 2.20.0, soupsieve 2.9.0 (najpierw 2.8.4 - za malo, dwie luki poprawione dopiero w 2.9.0; dobite 19.10 wieczorem).
- Wymuszone przez zależności: QBot — fastapi 0.128.8 → 0.133.1 (0.128 blokował Starlette 1.x; `@app.on_event` nadal działa),
  yarl 1.25.1 (aiohttp), uvicorn 0.31.1 (mcp), scipy 1.15.3 → 1.16.3 (stary scipy nie obsługiwał numpy 2.5 — konflikt był
  już na produkcji); Q365 — msal 1.31 → 1.37.0 (blokował cryptography 50).
- Usunięte z venv QBota: **aider-chat, litellm, diskcache** — aplikacja ich nie używa, a aider przypinał dokładnie dziurawe wersje.
- Wynik: testy QBota 1022 OK stary i nowy venv; pip check czysty we wszystkich 4 środowiskach; po restarcie usługi aktywne,
  strona Start 200, MCP (Claude → QBot) odpowiada.
- Cofnięcie: `<venv>/bin/python -m pip install -r /opt/qbot/artifacts/upd-1910/<env>.freeze.before.txt` + restart usług
  (env: qbot, mosty, cronometer, q365).
