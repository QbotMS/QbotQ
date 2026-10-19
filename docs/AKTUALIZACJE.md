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
