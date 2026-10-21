#!/usr/bin/env python3
"""Ponowne logowanie QBota do Garmina z kodem MFA (21.10.2026).

Kiedy: dzwonek / Status pokazuje "Garmin: zaloguj QBota ponownie".
Jak (w Terminalu na Macu, jedna komenda, pyta o kod z maila/aplikacji Garmin):
    ssh -t q 'runuser -u qbot -- /opt/qbot/app/.venv/bin/python3 /opt/qbot/app/scripts/garmin_login.py'
Zapisuje nowe tokeny (.garmin_tokens) i zdejmuje wstrzymanie importu (state/garmin_auth_block.json).
Hasla ani tokenow nie wypisuje.
"""
import sys

sys.path.insert(0, "/opt/qbot/app")

from garmin_auth import relogin_interactive  # noqa: E402

if __name__ == "__main__":
    try:
        relogin_interactive()
    except Exception as e:
        print(f"NIE UDALO SIE: {type(e).__name__}: {str(e)[:200]}")
        sys.exit(1)
    print("OK: QBot zalogowany do Garmina, import wznowi sie przy najblizszym sprawdzeniu (do 10 min).")
