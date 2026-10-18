#!/usr/bin/env python3
"""WIKI-QBOT -- przebieg 6 (18.10.2026): dzial STRAZNICY + audyt kompletnosci (czego wiki nie opisuje).
Powod: Michal zauwazyl brak strazników -- plan dzialow byl ulozony wg stron, a straznicy dzialaja w tle bez wlasnej strony.
Czeka na koniec przebiegu 5 (status5.json done). Potem indeks, commit docs/wiki, Telegram. Status: status6.json"""
from __future__ import annotations
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/opt/qbot/app/scripts")
import runner as R
import pass2 as P
import pass5 as P5

R.STATUS = f"{R.OUT}/status6.json"

STAGES6 = [
 ("S_straznicy", """ETAP: NOWY DZIAL "straznicy" (katalog straznicy/, dzial w metaznacznikach: straznicy).
Strazniki/bezpieczniki/watchdogi QBota dzialaja w tle i nie maja wlasnej strony, dlatego wczesniej je pominieto. Znajdz WSZYSTKIE w kodzie
(szukaj: guard, straznik, strażnik, watchdog, bezpiecznik, kwarantann, sanity, alert, destrukc) -- znane na start:
fitmodel/power_meter_guard.py (straznik miernika mocy, P@HR), fitmodel/load_guard.py (straznik obciazenia: XSS z mocy vs z tetna),
fitmodel/real_load_guard.py (straznik korekty ciala), fitmodel/modelq_guard.py (bezpieczniki ModelQ), scripts/garmin_watch.py (straznik Garmina),
scripts/nutrition_watchdog.py (straznik zywienia), straznik destrukcji (agent_runtime / ROUTE_STORE.md), straznik importu (qbot_status_checks.py),
kwarantanna jazd (miernik), plus kazdy inny, ktory znajdziesz. Dla kazdego: harmonogram (kiedy sie uruchamia -- timery systemd/cron/daily_job),
co sprawdza (progi dokladnie z kodu), co robi gdy wykryje problem (Telegram? dzwonek? blokada? nic nie zmienia?), przyklad PRAWDZIWEGO alertu
z bazy/logow jesli istnieje, historia (DECISIONS.md: dlaczego powstal, co zastapil -- np. load_guard zastapil alerty power_meter_guard),
jak reagowac na alert. straznicy/index.md: tabela wszystkich strazników (nazwa, co pilnuje, kiedy, skutek) + diagram.
Dopisz dzial do README.md, mapa-serwisu.md i zaleznosci.md; terminy do slowniczek.md; dotychczasowe wzmianki (modelq/bezpieczniki.md,
system/bezpieczniki.md, garaz/sprzet.md) zlinkuj do nowych hasel zamiast powielac."""),
 ("S_audyt", """ETAP: AUDYT KOMPLETNOSCI WIKI -- znajdz, czego wiki NIE opisuje (tak jak pominieto strazników).
Zrob inwentarz z kodu (skrypt w _work/): (1) wszystkie automaty: timery systemd qbot* (pliki /etc/systemd/system/qbot*.timer i .service -- odczyt),
crontab (/var/spool/cron/crontabs/* jesli czytelne), harmonogramy w kodzie (daily_job, schedulery); (2) wszystkie miejsca wysylajace Telegram
(send(, sendMessage, notify); (3) wszystkie endpointy /api/ w qbot_web.py i qbot_api.py; (4) wszystkie strony i zakladki w /opt/qbot/web/public;
(5) narzedzia Alberta (qbot3/tool_registry.py); (6) tabele qbot_v2 (information_schema). Porownaj z _indeks.json (pola tytul/tekst/zrodla_kodu).
Zapisz audyt-kompletnosci.md: tabela "element -> haslo wiki albo BRAK". Dla kazdego BRAKU, ktory uzytkownik widzi lub ktory wysyla mu
wiadomosci (automat, alert, strona, zakladka, liczba) -- NAPISZ haslo w odpowiednim dziale wg szablonu. Czysto techniczne elementy (tabele
pomocnicze, endpointy wewnetrzne) wystarczy wymienic w system/strony-www.md lub system/automaty.md. Na koniec w _RAPORT.md: ile brakow
znaleziono, ile hasel dopisano, co zostalo."""),
]


def main() -> int:
    t_wait = time.time()
    while time.time() - t_wait < 8 * 3600:
        try:
            if json.load(open(f"{R.OUT}/status5.json")).get("done"):
                break
        except Exception:
            pass
        time.sleep(60)
    from dev_fetch import get_auth
    users, sign, make = get_auth()
    cookie, _ = make(sorted(users)[0], sign)
    st = {"start": R.now(), "stages": {}, "done": False}
    R.save_status(st)
    R.log("PASS6 START")
    base_dirty = R.dirty_outside_wiki()
    fails = []
    for name, prompt in STAGES6:
        R.worklock()
        st["stages"][name] = {"start": R.now(), "status": "w toku"}
        R.save_status(st)
        env = dict(os.environ)
        env["PGOPTIONS"] = "-c default_transaction_read_only=on -c statement_timeout=60000"
        env["QBOT_SESSION"] = cookie
        cmd = ["codex", "exec", "--skip-git-repo-check", "-C", R.WIKI, "-o", f"{R.OUT}/{name}.last.txt",
               "-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=true",
               "--", R.COMMON + P.EXTRA + P5.WEB + "\n\n" + prompt]
        t0 = time.time()
        with open(f"{R.OUT}/{name}.log", "w") as lf:
            try:
                rc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    timeout=80 * 60, env=env, cwd=R.WIKI).returncode
            except subprocess.TimeoutExpired:
                rc = 124
        res = "OK" if rc == 0 else ("LIMIT CZASU" if rc == 124 else f"BLAD {rc}")
        st["stages"][name].update({"end": R.now(), "min": round((time.time() - t0) / 60), "status": res})
        if rc != 0:
            fails.append(name)
        nd = R.dirty_outside_wiki() - base_dirty
        if nd:
            st["stages"][name]["UWAGA_zmiany_poza_wiki"] = sorted(nd)[:30]
            base_dirty |= nd
        R.save_status(st)
        R.log(f"{name}: {res}")
    r = subprocess.run([R.PY, f"{R.APP}/scripts/wiki_bg/build_index.py"], capture_output=True, text=True, timeout=300, cwd=R.APP)
    st["stages"]["indeks"] = {"status": "OK" if r.returncode == 0 else f"BLAD {r.returncode}", "info": (r.stdout or r.stderr)[-200:]}
    G = ["git", "-c", f"safe.directory={R.APP}", "-C", R.APP]
    subprocess.run(G + ["add", "--", "docs/wiki"], capture_output=True)
    subprocess.run(G + ["reset", "-q", "--", "docs/wiki/_work"], capture_output=True)
    c = subprocess.run(["runuser", "--preserve-environment", "-u", "qbot", "--"] + G + ["-c", "user.name=qbot", "-c", "user.email=qbot@olga181.mikrus.xyz",
                       "commit", "-m", "WIKI QBot: dzial Straznicy + audyt kompletnosci"], capture_output=True, text=True)
    if c.returncode == 0:
        subprocess.run(G + ["push"], capture_output=True)
    st.update({"done": True, "end": R.now()})
    R.save_status(st)
    subprocess.run([R.PY, f"{R.APP}/scripts/worklock.py", "release", "--who", "wiki-bg"], cwd=R.APP, capture_output=True, timeout=30)
    n = len([f for f in os.listdir(f"{R.WIKI}/straznicy") if f.endswith(".md")]) if os.path.isdir(f"{R.WIKI}/straznicy") else 0
    R.tg(f"📘 WIKI QBot — Strażnicy + audyt kompletności gotowe ({R.now()}). Haseł o strażnikach: {n}"
         + (f"; problemy: {', '.join(fails)}" if fails else "") + ".\nBraki i co dopisano: docs/wiki/audyt-kompletnosci.md\nhttps://albert.cytr.us/wiki.html?p=straznicy/index.md")
    R.log("PASS6 KONIEC")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa
        R.log(f"PASS6 AWARIA {e!r}")
        R.tg(f"⚠️ WIKI QBot przebieg 6: awaria {e!r}"[:400])
        raise
