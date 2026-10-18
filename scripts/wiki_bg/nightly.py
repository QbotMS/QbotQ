#!/usr/bin/env python3
"""Nocna obsluga wiki + dziennika (timer qbot-wiki-nightly, 23:50). Decyzja Michala 18.10.2026: w pelni automatycznie, tylko w Wiki.

1. Dziennik dnia (scripts/dziennik.py build).
2. Hasla wiki opisujace kod zmieniony dzis (scripts/wiki_bg/wiki_check.py) -> codex je aktualizuje wg zmian z gita;
   kod bez hasla, ktory widzi uzytkownik -> nowe haslo; do dziennika -> krotkie podsumowanie dnia po ludzku.
3. W poniedzialki dodatkowo audyt kompletnosci (jak przebieg 6).
4. Indeks wiki, commit docs/wiki + docs/dziennik (Sesja: wiki-noc), push, wpis do dziennika.
Telegram TYLKO przy awarii. Gdy trwa inny przebieg wiki (status*.json done=false) -- krok 2-3 pomijany, dziennik i tak powstaje."""
from __future__ import annotations
import glob, json, os, subprocess, sys, time
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/opt/qbot/app/scripts")
import runner as R
import pass2 as P
import pass5 as P5
import pass6 as P6
import dziennik as DZ

R.STATUS = f"{R.OUT}/status_noc.json"
SESJA = "wiki-noc"


def busy() -> bool:
    for f in glob.glob(f"{R.OUT}/status*.json"):
        if f.endswith("status_noc.json"):
            continue
        try:
            if not json.load(open(f)).get("done", True):
                return True
        except Exception:
            pass
    return False


def codex(name: str, prompt: str, cookie: str) -> int:
    env = dict(os.environ)
    env["PGOPTIONS"] = "-c default_transaction_read_only=on -c statement_timeout=60000"
    env["QBOT_SESSION"] = cookie
    cmd = ["codex", "exec", "--skip-git-repo-check", "-C", R.WIKI, "-o", f"{R.OUT}/{name}.last.txt",
           "-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=true",
           "--", R.COMMON + P.EXTRA + P5.WEB + "\n\n" + prompt]
    with open(f"{R.OUT}/{name}.log", "w") as lf:
        try:
            return subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  timeout=90 * 60, env=env, cwd=R.WIKI).returncode
        except subprocess.TimeoutExpired:
            return 124


def main() -> int:
    d = date.today()
    st = {"start": R.now(), "stages": {}, "done": False}
    R.save_status(st)
    dz = DZ.build(d)
    st["stages"]["dziennik"] = dz
    fails = []
    if busy():
        st["stages"]["wiki"] = "pominiete -- trwa inny przebieg wiki"
    else:
        chk = json.loads(subprocess.run([R.PY, f"{R.APP}/scripts/wiki_bg/wiki_check.py", "--date", f"{d:%Y-%m-%d}"],
                                        capture_output=True, text=True, cwd=R.APP).stdout or "{}")
        todo = chk.get("hasla_do_aktualizacji", {})
        bez = [p for p in chk.get("kod_bez_hasla", []) if not p.startswith(("scripts/wiki_bg/", "archive/", "sql/"))]
        st["stages"]["do_aktualizacji"] = {"hasla": len(todo), "kod_bez_hasla": len(bez)}
        from dev_fetch import get_auth
        users, sign, make = get_auth()
        cookie, _ = make(sorted(users)[0], sign)
        rel = os.path.relpath(dz, R.WIKI)
        prompt = (f"NOCNA AKTUALIZACJA WIKI {d:%d.%m.%Y}.\n"
                  f"1) Hasla do aktualizacji (haslo <- zmieniony dzis kod): {json.dumps(todo, ensure_ascii=False)}\n"
                  f"   Dla kazdego: zobacz, co sie zmienilo (git -C {R.APP} log -p --since='{d:%Y-%m-%d} 00:00' -- <plik>; niezacommitowane: git diff -- <plik>),"
                  f" popraw tresc hasla, metaznaczniki i 'Decyzje i historia' (data + co sie zmienilo). Jesli zmiana nie dotyczy opisu -- tylko aktualizacja daty.\n"
                  f"2) Kod zmieniony dzis bez zadnego hasla: {json.dumps(bez, ensure_ascii=False)}\n"
                  f"   Jesli to cos, co uzytkownik widzi albo co do niego pisze (strona, zakladka, liczba, alert, automat, straznik) -- dopisz haslo albo uzupelnij"
                  f" istniejace (i dopisz plik do jego zrodla_kodu). Czysto techniczne -- pomin.\n"
                  f"3) W pliku {rel} zastap linie '<!-- PODSUMOWANIE -->' blokiem: '<!-- PODSUMOWANIE -->' + 3-6 zdan po ludzku, co dzis zmieniono w QBocie"
                  f" (wg sesji; bez nazw plikow), i liste 'Wiki: zaktualizowano ...' z linkami do poprawionych hasel. Nie zmieniaj reszty dziennika.\n")
        if d.weekday() == 0:
            prompt += "\n4) PONIEDZIALEK -- dodatkowo:\n" + P6.STAGES6[1][1]
        rc = codex("NOC_" + f"{d:%Y%m%d}", prompt, cookie)
        st["stages"]["codex"] = "OK" if rc == 0 else f"BLAD {rc}"
        if rc != 0:
            fails.append("codex")
        subprocess.run([R.PY, f"{R.APP}/scripts/wiki_bg/build_index.py"], capture_output=True, text=True, timeout=300, cwd=R.APP)
    G = ["git", "-c", f"safe.directory={R.APP}", "-C", R.APP]
    subprocess.run(G + ["add", "--", "docs/wiki", "docs/dziennik"], capture_output=True)
    subprocess.run(G + ["reset", "-q", "--", "docs/wiki/_work"], capture_output=True)
    c = subprocess.run(["runuser", "--preserve-environment", "-u", "qbot", "--"] + G + ["-c", "user.name=qbot", "-c", "user.email=qbot@olga181.mikrus.xyz",
                       "commit", "-m", f"Wiki + dziennik {d:%d.%m.%Y} (noc)\n\nSesja: {SESJA}"], capture_output=True, text=True)
    if c.returncode == 0 and subprocess.run(G + ["push"], capture_output=True).returncode != 0:
        fails.append("push")
    DZ.log_event("tlo", SESJA, "nocna aktualizacja wiki i dziennika" + (f" -- problemy: {', '.join(fails)}" if fails else ""))
    DZ.build(d)  # dopisz wpis 'w tle' do widoku dnia (podsumowanie zostaje)
    st.update({"done": True, "end": R.now(), "fails": fails})
    R.save_status(st)
    if fails:
        R.tg(f"⚠️ Nocna aktualizacja wiki {d:%d.%m}: problemy ({', '.join(fails)}). Szczegóły: /opt/qbot/artifacts/wiki_bg/status_noc.json")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa
        R.log(f"NOC AWARIA {e!r}")
        R.tg(f"⚠️ Nocna aktualizacja wiki: awaria {e!r}"[:400])
        raise
