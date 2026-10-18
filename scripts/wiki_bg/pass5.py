#!/usr/bin/env python3
"""WIKI-QBOT -- przebieg 5 (18.10.2026): poglebienie hasel + domkniecie _DO_SPRAWDZENIA.
Nowosc vs przebieg 2: codex dostaje zalogowane ciasteczko serwisu w zmiennej QBOT_SESSION (tylko w pamieci procesu, nigdy do pliku),
wiec sam sprawdza strony po zalogowaniu (curl). Na koniec: indeks (build_index.py), commit tylko docs/wiki, Telegram.
Status: /opt/qbot/artifacts/wiki_bg/status5.json"""
from __future__ import annotations
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/opt/qbot/app/scripts")
import runner as R
import pass2 as P

R.STATUS = f"{R.OUT}/status5.json"

WEB = """
DOSTEP DO STRON PO ZALOGOWANIU: zmienna srodowiskowa QBOT_SESSION zawiera ciasteczko sesji. Uzywaj:
  curl -s -b "qbot_session=$QBOT_SESSION" http://127.0.0.1:30181/<strona albo /api/...>
NIGDY nie wypisuj wartosci ciasteczka, nie zapisuj go do pliku ani do wiki. Tylko odczyt (GET). Zadnych POST/PUT/DELETE.
"""

RULES5 = """
ZASADY PRZEBIEGU 5:
- Najpierw z _DO_SPRAWDZENIA.md wez pozycje swojego dzialu i SAM je sprawdz (baza tylko do odczytu, curl z ciasteczkiem, kod, API).
  Wyjasnione -> popraw haslo i przenies pozycje do "## Wyjasnione" (1 zdanie wyniku). W "## Pytania do Michala" zostaw TYLKO
  prawdziwe decyzje, ktorych nie da sie sprawdzic w danych (np. "czy funkcja X ma dzialac tak czy inaczej"), jako pytanie TAK/NIE.
  Braki dostepu, rzeczy "nie sprawdzono", prosby o zrzuty -- to NIE sa pytania do Michala; sprawdz albo opisz jako ograniczenie w hasle.
- Rozbieznosci liczb (np. zaokraglenia, roznice miedzy ekranami) wyjasnij na niezaokraglonych danych; jesli to blad serwisu -- dopisz do
  _RAPORT.md w sekcji "Mozliwe bledy serwisu" (nie naprawiaj kodu).
- Potem poglebiaj hasla dzialu wg zasad A-G (cel 4-10 KB na haslo, kroki na prawdziwych liczbach). Metaznaczniki (blok --- na gorze) zachowaj
  i zaktualizuj (aktualizacja = dzisiejsza data z `date`).
"""


def main() -> int:
    from dev_fetch import get_auth
    users, sign, make = get_auth()
    cookie, _ = make(sorted(users)[0], sign)
    st = {"start": R.now(), "stages": {}, "done": False}
    R.save_status(st)
    R.log("PASS5 START")
    base_dirty = R.dirty_outside_wiki()
    fails = []
    for slug, scope, src in R.MODULES:
        R.worklock()
        name = f"Q_{slug}"
        st["stages"][name] = {"start": R.now(), "status": "w toku"}
        R.save_status(st)
        prompt = (f'ETAP PRZEBIEG 5 -- DZIAL "{slug}" ({scope}). Zrodla: {src}.\n'
                  f"Przeczytaj {slug}/*.md, _DO_SPRAWDZENIA.md, slowniczek.md, zaleznosci.md." + RULES5 + WEB)
        env = dict(os.environ)
        env["PGOPTIONS"] = "-c default_transaction_read_only=on -c statement_timeout=60000"
        env["QBOT_SESSION"] = cookie
        cmd = ["codex", "exec", "--skip-git-repo-check", "-C", R.WIKI, "-o", f"{R.OUT}/{name}.last.txt",
               "-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=true"]
        for im in P.images_for(slug):
            cmd += ["-i", im]
        cmd += ["--", R.COMMON + P.EXTRA + "\n\n" + prompt]
        t0 = time.time()
        with open(f"{R.OUT}/{name}.log", "w") as lf:
            try:
                rc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    timeout=R.STAGE_TIMEOUT, env=env, cwd=R.WIKI).returncode
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
    # commit tylko tresci wiki (bez _work)
    G = ["git", "-c", f"safe.directory={R.APP}", "-C", R.APP]
    subprocess.run(G + ["add", "--", "docs/wiki"], capture_output=True)
    subprocess.run(G + ["reset", "-q", "--", "docs/wiki/_work"], capture_output=True)
    c = subprocess.run(["runuser", "--preserve-environment", "-u", "qbot", "--"] + G + ["-c", "user.name=qbot", "-c", "user.email=qbot@olga181.mikrus.xyz",
                       "commit", "-m", "WIKI QBot: przebieg 5 -- poglebienie hasel, domkniecie _DO_SPRAWDZENIA"], capture_output=True, text=True)
    pushed = c.returncode == 0 and subprocess.run(G + ["push"], capture_output=True).returncode == 0
    st["stages"]["git"] = {"commit": c.returncode, "push": pushed}
    st.update({"done": True, "end": R.now()})
    R.save_status(st)
    subprocess.run([R.PY, f"{R.APP}/scripts/worklock.py", "release", "--who", "wiki-bg"], cwd=R.APP, capture_output=True, timeout=30)
    md = [os.path.join(d, f) for d, _, fs in os.walk(R.WIKI) for f in fs if f.endswith(".md") and "/_work" not in d and not f.startswith("_")]
    big = sum(1 for p in md if os.path.getsize(p) > 4096)
    q = open(f"{R.WIKI}/_DO_SPRAWDZENIA.md", encoding="utf-8").read()
    q = q.split("## Pytania do Micha", 1)[1].split("\n## ", 1)[0] if "## Pytania do Micha" in q else ""
    nq = sum(1 for ln in q.splitlines() if ln.strip().startswith("- "))
    msg = (f"📘 WIKI QBot — przebieg 5 gotowy ({R.now()}). Etapy OK: {len(R.MODULES) - len(fails)}/{len(R.MODULES)}"
           + (f"; problemy: {', '.join(fails)}" if fails else "") +
           f"\nHasła >4 KB: {big}/{len(md)}. Pytania do Ciebie: {nq}.\nhttps://albert.cytr.us/wiki.html")
    if any("UWAGA_zmiany_poza_wiki" in v for v in st["stages"].values()):
        msg += "\n⚠️ Zmiany plików poza wiki — sprawdź status5.json."
    R.tg(msg)
    R.log("PASS5 KONIEC")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa
        R.log(f"PASS5 AWARIA {e!r}")
        R.tg(f"⚠️ WIKI QBot przebieg 5: awaria {e!r}"[:400])
        raise
