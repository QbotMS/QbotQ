"""QBot: globalne wyciszenie logowania adresow zapytan HTTP (sesja klucze-1910, 19.10.2026).

Instalowany jako modul qbot_logguard.py + plik qbot_logguard.pth (linia 'import qbot_logguard') w
/opt/qbot/app/.venv/lib/python3.12/site-packages/ - Python wykonuje .pth przy starcie KAZDEGO procesu z tego
srodowiska (qbot-api, qbot-web, cron, skrypty). sitecustomize.py NIE dziala: Ubuntu ma wlasny systemowy,
ktory ma pierwszenstwo (test 19.10). Zrodlo w repo: /opt/qbot/app/config/qbot_logguard.py
(po przebudowie .venv: scripts/install_logguard.py).

Powod: biblioteki HTTP (httpx/httpcore, urllib3) loguja na poziomie INFO/DEBUG pelny adres zapytania.
Adres wysylki na Telegram zawiera token bota (api.telegram.org/bot<TOKEN>/...), wiec token trafial do logow
(najstarszy slad 26.05.2026; import tras Komoot, potwierdzenia przeliczenia, skrypty naprawy tras i OSM).
Ostrzezenia i bledy tych bibliotek zostaja (poziom WARNING).
Dodatkowo filtr maskujacy token w kazdym rekordzie logu, na wypadek innej sciezki (np. tekst wyjatku).
"""
import logging as _logging
import re as _re

for _name in ("httpx", "httpcore", "urllib3", "requests"):
    _logging.getLogger(_name).setLevel(_logging.WARNING)

_TOKEN_RE = _re.compile(r"(bot\d{6,}):[A-Za-z0-9_-]{20,}")


class _QbotTokenMask(_logging.Filter):
    def filter(self, record):
        try:
            msg = record.getMessage()
            if "bot" in msg and _TOKEN_RE.search(msg):
                record.msg = _TOKEN_RE.sub(r"\1:***", msg)
                record.args = ()
        except Exception:
            pass
        return True


_orig_handle = _logging.Handler.handle


def _handle(self, record, _f=_QbotTokenMask()):
    _f.filter(record)
    return _orig_handle(self, record)


_logging.Handler.handle = _handle
