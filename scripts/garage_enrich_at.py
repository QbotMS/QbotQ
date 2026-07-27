"""garage_enrich_at.py - odpalacz runu wzbogacania o zadanej godzinie.

Czeka do wskazanego momentu (czas serwera = Europe/Warsaw), po czym uruchamia
garage_enrich.py. Uzywany zamiast crona, bo do crona/systemd potrzeba roota,
a ten kanal go nie ma. Proces jest odlaczony, wiec przezywa koniec sesji.

Stan zapisuje w /opt/qbot/app/docs/audit/enrich_trigger.json - dzieki temu
widac, czy trigger czeka, i mozna go ubic po PID.
"""
import datetime
import json
import os
import subprocess
import sys
import time

STAN = "/opt/qbot/app/docs/audit/enrich_trigger.json"
LOG = "/opt/qbot/app/docs/audit/enrich_run.log"
PY = "/opt/qbot/app/.venv/bin/python3"
WORKER = "/opt/qbot/app/scripts/garage_enrich.py"


def zapisz_stan(**kw):
    os.makedirs(os.path.dirname(STAN), exist_ok=True)
    dane = {"pid": os.getpid(), "zapisano": datetime.datetime.now().isoformat(timespec="seconds")}
    dane.update(kw)
    with open(STAN, "w", encoding="utf-8") as f:
        json.dump(dane, f, ensure_ascii=False, indent=1)


def main():
    # argument: "2026-07-28 02:00"
    cel_txt = sys.argv[1] if len(sys.argv) > 1 else "2026-07-28 02:00"
    cel = datetime.datetime.strptime(cel_txt, "%Y-%m-%d %H:%M")
    zapisz_stan(stan="czeka", cel=cel.isoformat(timespec="minutes"))

    while True:
        teraz = datetime.datetime.now()
        zostalo = (cel - teraz).total_seconds()
        if zostalo <= 0:
            break
        time.sleep(min(300, zostalo))      # budzik co 5 min, odporny na drobne przesuniecia

    zapisz_stan(stan="uruchomiony", cel=cel.isoformat(timespec="minutes"),
                start=datetime.datetime.now().isoformat(timespec="seconds"))
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("\n==== start %s ====\n" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        f.flush()
        rc = subprocess.call([PY, WORKER], stdout=f, stderr=subprocess.STDOUT,
                             cwd="/opt/qbot/app")
    zapisz_stan(stan="zakonczony", cel=cel.isoformat(timespec="minutes"),
                koniec=datetime.datetime.now().isoformat(timespec="seconds"), kod_wyjscia=rc)


if __name__ == "__main__":
    main()
