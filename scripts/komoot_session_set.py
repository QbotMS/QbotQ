#!/usr/bin/env python3
"""Wgranie swiezej sesji Komoot z terminala (awaryjnie - normalnie robi to strona).

Strona: https://albert.cytr.us/komoot-dostep (za logowaniem QBota).

Uzycie:
    .venv/bin/python3 scripts/komoot_session_set.py <plik-z-cookie>
    .venv/bin/python3 scripts/komoot_session_set.py -        (czyta ze stdin)
    .venv/bin/python3 scripts/komoot_session_set.py --status (tylko sprawdzenie)

Cala logika siedzi w komoot_session_admin - tu jest tylko obsluga wejscia.
Zadna wartosc ciasteczka nie jest wypisywana ani logowana.
"""
from __future__ import annotations
import sys

sys.path.insert(0, "/opt/qbot/app")
import komoot_session_admin as A


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 2
    arg = sys.argv[1]

    if arg == "--status":
        st = A.status()
        print(("ZYWA: " if st["alive"] else "MARTWA: ") + st["detail"])
        last = A.last_seen_tour()
        if last:
            print("Ostatnia wykryta trasa: %s (%s, %s)" % (last["name"], last["date"], last["status"]))
        return 0 if st["alive"] else 1

    raw = sys.stdin.read() if arg == "-" else open(arg, encoding="utf-8").read()
    try:
        res = A.store_session(raw)
    except A.SessionInputError as e:
        print("BLAD wejscia: %s" % e)
        return 1
    except A.SessionRejected as e:
        print("BLAD: API Komoota odrzucilo te ciasteczka: %s" % e)
        return 1
    print("TEST OK - API zwrocilo %d tras" % res["tours"])
    print("ZAPISANO sesje%s. Watcher wykryje nowe trasy przy najblizszym przebiegu."
          % (" (stara w .bak)" if res["backup"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
