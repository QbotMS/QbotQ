#!/usr/bin/env python3
"""WIKI -- przebieg 7 (19.10.2026): decyzje Michala do wiki + porzadek w pytaniach. Potem indeks, commit, Telegram."""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, "/opt/qbot/app/scripts")
import runner as R
import nightly as N
import dziennik as DZ
R.STATUS = f"{R.OUT}/status7.json"
PROMPT = """ZADANIE 19.10.2026 -- decyzje Michala (DECISIONS 19.10) do wiki:
1) Bialko: JEDEN cel 160 g wszedzie (wczesniej piatkowa wiadomosc weekendowa podawala 150 g; od 19.10 tez 160 -- qbot_food_plan.PROTEIN_G = PROTEIN_TARGET).
   Popraw zdrowie/bialko.md, zdrowie/weekend.md i inne hasla z "150 g" bialka; w "Decyzje i historia" wpis z data.
2) Paliwo na rower: od 19.10 liczone z FAKTYCZNEGO czasu jazdy (training_sessions.duration_s), gdy jazda juz jest; plan z Kalendarza tylko gdy jazdy brak.
   Przyklad 18.10: 146,9 min -> 80 g (wczesniej liczone ze 163 min z Kalendarza). Popraw zdrowie/paliwo-rower.md (+ inne hasla o paliwie), kroki na tych liczbach.
3) Polacz haslo polaczenia/hammerhead-garmin.md z polaczenia/garmin.md (sekcja "Hammerhead/Karoo -> Garmin (TACX)"), usun hammerhead-garmin.md,
   popraw wszystkie linki do niego w calej wiki (grep), synonimy hammerhead/karoo/tacx dopisz do metaznacznikow garmin.md, popraw polaczenia/index.md.
4) _DO_SPRAWDZENIA.md: w "## Pytania do Michala" zostaw TYLKO prawdziwe decyzje. Trzy powyzsze przenies do "## Wyjasnione" (z decyzja i data).
   "Telegram -> Albert" zostaw jako pytanie (czeka w TODO [TELEGRAM-ALBERT]). Wszystkie pozostale linie (opisy ograniczen, "nie potwierdzono", "czy mozna
   potwierdzic", prosby o weryfikacje) przenies do nowej sekcji "## Ograniczenia weryfikacji" -- to nie sa pytania do Michala.
Kod sprawdz na zywo (git -C /opt/qbot/app show HEAD~0 -- qbot_food_plan.py, oraz biezacy plik)."""
def main():
    from dev_fetch import get_auth
    u, s, mk = get_auth(); cookie, _ = mk(sorted(u)[0], s)
    st = {"start": R.now(), "done": False}; R.save_status(st)
    rc = N.codex("P7_decyzje", PROMPT, cookie)
    subprocess.run([R.PY, f"{R.APP}/scripts/wiki_bg/build_index.py"], capture_output=True, timeout=300, cwd=R.APP)
    G = ["git", "-c", f"safe.directory={R.APP}", "-C", R.APP]
    subprocess.run(G + ["add", "-A", "--", "docs/wiki"], capture_output=True)
    subprocess.run(G + ["reset", "-q", "--", "docs/wiki/_work"], capture_output=True)
    c = subprocess.run(["runuser", "--preserve-environment", "-u", "qbot", "--"] + G + ["-c", "user.name=qbot", "-c", "user.email=qbot@olga181.mikrus.xyz",
        "commit", "-m", "Wiki: decyzje 19.10 (bialko 160, paliwo z czasu jazdy, Hammerhead w hasle Garmin), porzadek w pytaniach\n\nSesja: wiki-1910"], capture_output=True, text=True)
    if c.returncode == 0: subprocess.run(G + ["push"], capture_output=True)
    DZ.log_event("tlo", "wiki-1910", "wiki: decyzje 19.10 + porzadek w pytaniach (codex rc=%s)" % rc)
    st.update({"done": True, "end": R.now(), "codex": rc, "commit": c.returncode}); R.save_status(st)
    R.tg(("📘 Wiki: decyzje z 19.10 wpisane, Hammerhead połączony z hasłem Garmin, pytania uporządkowane." if rc == 0 else f"⚠️ Wiki przebieg 7: problem (rc {rc})."))
if __name__ == "__main__":
    main()
