"""Wymiana klucza (tokenu) bota Telegram QBota (@q_rowerowy_bot). Sesja klucze-1910, 19.10.2026.

Uzycie (na serwerze jako root, interaktywnie - klucz wpisujesz ukryty, nie trafia do logow ani historii):
    /opt/qbot/app/.venv/bin/python3 /opt/qbot/app/scripts/telegram_wymiana_klucza.py

Kroki: (1) nowy klucz z klawiatury (ukryty) -> (2) getMe: musi byc ten sam bot -> (3) kopie zapasowe plikow
ustawien (prawa 600) -> (4) podmiana TELEGRAM_TOKEN / TELEGRAM_BOT_TOKEN -> (5) restart serwisow QBota ->
(6) wiadomosc testowa nowym kluczem. Klucz NIGDY nie jest wypisywany. Bot dziala bez webhooka (getUpdates).
Pliki z kluczem (audyt 19.10): /opt/qbot/app/.env, .env.local (2 zmienne), .env.local.tmp.
"""
from __future__ import annotations

import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

BOT_USERNAME = "q_rowerowy_bot"
FILES = ["/opt/qbot/app/.env", "/opt/qbot/app/.env.local", "/opt/qbot/app/.env.local.tmp"]
VARS = ("TELEGRAM_TOKEN", "TELEGRAM_BOT_TOKEN")
SERVICES = ["qbot-api", "qbot-web", "qbot-qlab-server", "q-bot"]
KEY_RE = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{30,}$")


def tg(key: str, method: str, data: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{key}/{method}"
    body = urllib.parse.urlencode(data).encode() if data else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=20) as r:
            return json.loads(r.read())
    except Exception as exc:  # nie wypisujemy URL (zawiera klucz)
        return {"ok": False, "description": type(exc).__name__}


def chat_id() -> str | None:
    for p in FILES:
        try:
            for line in open(p, encoding="utf-8"):
                m = re.match(r"^\s*(?:export\s+)?TELEGRAM_CHAT_ID\s*=\s*['\"]?([-0-9]+)", line)
                if m:
                    return m.group(1)
        except OSError:
            continue
    return None


def main() -> int:
    if os.geteuid() != 0:
        print("Uruchom jako root (pliki ustawien i restart serwisow).")
        return 2
    new = getpass.getpass("Wklej NOWY token z BotFather (nie bedzie widoczny) i Enter: ").strip()
    if not KEY_RE.match(new):
        print("To nie wyglada na token Telegrama (format 123456789:ABC...). Nic nie zmieniono.")
        return 1
    me = tg(new, "getMe")
    if not me.get("ok"):
        print(f"Telegram odrzucil nowy token ({me.get('description')}). Nic nie zmieniono.")
        return 1
    if me["result"].get("username") != BOT_USERNAME:
        print(f"Token nalezy do innego bota (@{me['result'].get('username')}), oczekiwano @{BOT_USERNAME}. Nic nie zmieniono.")
        return 1
    print(f"OK: token nalezy do @{BOT_USERNAME}.")
    ts = time.strftime("%Y%m%d_%H%M%S")
    changed = []
    for p in FILES:
        if not os.path.exists(p):
            continue
        txt = open(p, encoding="utf-8").read()
        out, n = [], 0
        for line in txt.splitlines(keepends=True):
            m = re.match(r"^(\s*(?:export\s+)?(" + "|".join(VARS) + r")\s*=\s*)(['\"]?)([^'\"\n]*)(['\"]?)(\s*)$", line)
            if m:
                line = f"{m.group(1)}{m.group(3)}{new}{m.group(5)}{m.group(6)}"
                n += 1
            out.append(line)
        if n:
            st = os.stat(p)
            bak = f"{p}.bak.tg.{ts}"
            shutil.copy2(p, bak)
            os.chmod(bak, 0o600)
            tmp = p + ".tmp_rot"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write("".join(out))
            os.chown(tmp, st.st_uid, st.st_gid)
            os.chmod(tmp, st.st_mode & 0o7777)
            os.replace(tmp, p)
            changed.append(f"{p} ({n} zmienne)")
    print("Podmieniono:", "; ".join(changed) if changed else "nic")
    for s in SERVICES:
        r = subprocess.run(["systemctl", "restart", "--no-block", s], capture_output=True, text=True)
        print(f"restart {s}: {'zlecony' if r.returncode == 0 else 'BLAD ' + r.stderr.strip()[:120]}")
    cid = chat_id()
    if cid:
        r = tg(new, "sendMessage", {"chat_id": cid, "text": "QBot: nowy token bota działa ✅ (wymiana 19.10.2026)"})
        print("Wiadomosc testowa:", "wyslana - sprawdz Telegram" if r.get("ok") else f"BLAD {r.get('description')}")
    print("Gotowe. Stary token w kopiach *.bak.tg.* jest juz uniewazniony (BotFather).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
