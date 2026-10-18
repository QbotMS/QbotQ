#!/usr/bin/env python3
"""WIKI-QBOT -- przebieg 2 (pogłębienie), w tle. Uzywa funkcji z runner.py (codex, log, tg, status).
Kolejnosc: zrzuty ekranow -> domkniecie _DO_SPRAWDZENIA -> poglebienie dzialow (ze zrzutami) -> kontrola spojnosci.
Status: /opt/qbot/artifacts/wiki_bg/status2.json"""
from __future__ import annotations
import glob, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runner as R

R.STATUS = f"{R.OUT}/status2.json"
SHOTS = f"{R.WIKI}/img/ekrany"

EXTRA = f"""
ZASADY PRZEBIEGU 2 (POGLEBIENIE) -- dodatkowo do powyzszych:
A. Czytelnik to hobbysta, nie programista. W tresci glownej hasla NIE uzywaj nazw kolumn, tabel, funkcji ani plikow --
   te sa tylko w sekcji "Zrodla" na dole. Kazdy skrot/termin (CTL, ATL, TSB, W', NP, IF, XSS, TP...) przy pierwszym uzyciu
   w hasle: krotkie wyjasnienie w nawiasie + link do slowniczek.md.
B. "Jak liczone": krok po kroku, numerowane kroki, kazdy krok na PRAWDZIWYCH liczbach z bazy (z data), tak by dalo sie
   to przeliczyc na kartce. Wzor tylko w <details><summary>Wzor</summary>...</details>.
C. "Po co" i "Jak czytac": konkretne sytuacje z jazdy/dnia ("jesli rano widzisz X, to znaczy Y, rozsadnie jest Z"), progi i kolory dokladnie jak w kodzie.
D. ILUSTRACJE: w kazdym hasle co najmniej jedna ilustracja: diagram Mermaid przeplywu ORAZ, gdzie to ma sens, zrzut ekranu z
   img/ekrany/ (obraz: ![opis](../img/ekrany/plik.png); indeks zrzutow: img/ekrany/indeks.md; zalaczone obrazy to te zrzuty --
   opisz co na nich jest i gdzie szukac danej liczby). Dla algorytmow liczbowych dodaj prosty wykres SVG w img/ (z prawdziwych danych).
E. Rozbuduj hasla do realnej glebokosci (typowo 4-10 KB). Nie powtarzaj tresci miedzy haslami -- linkuj.
F. Daty/godziny w _RAPORT.md bierz z polecenia `date '+%d.%m.%Y %H:%M'`, nie wymyslaj.
G. Strony www mozesz sprawdzic zalogowany: {R.PY} {R.APP}/scripts/dev_fetch.py /strona.html --grep TEKST (tylko odczyt).
"""

DEPTH_SCREENS = {
    "modelq": ["mq2", "forma"], "forma": ["forma", "dashboard"], "raport-jazdy": ["raport-jazdy"],
    "trener": ["trening"], "trasy": ["raport-trasy", "naprawa-trasy", "planer-wyprawy", "raport-dzien"],
    "pogoda": ["pogoda", "pogoda-wyprawy"], "zdrowie": ["zdrowie"], "garaz": ["garaz"],
    "qext2": ["setup"], "albert": ["index"], "polaczenia": ["status", "strava"], "system": ["status", "setup", "index"],
}


def images_for(slug: str) -> list[str]:
    out = []
    for pre in DEPTH_SCREENS.get(slug, []):
        out += sorted(glob.glob(f"{SHOTS}/{pre}.png")) + sorted(glob.glob(f"{SHOTS}/{pre}__*.png"))
    return [p for p in out if not p.endswith("__mobile.png")][:8]


def codex2(name: str, prompt: str, images: list[str] | None = None) -> int:
    env = dict(os.environ)
    env["PGOPTIONS"] = "-c default_transaction_read_only=on -c statement_timeout=60000"
    cmd = ["codex", "exec", "--skip-git-repo-check", "-C", R.WIKI, "-o", f"{R.OUT}/{name}.last.txt",
           "-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=true"]
    for im in images or []:
        cmd += ["-i", im]
    cmd += ["--", R.COMMON + EXTRA + "\n\n" + prompt]
    with open(f"{R.OUT}/{name}.log", "w") as lf:
        try:
            return subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  timeout=R.STAGE_TIMEOUT, env=env, cwd=R.WIKI).returncode
        except subprocess.TimeoutExpired:
            lf.write("\n### TIMEOUT\n")
            return 124


STAGES2 = [("P0_do_sprawdzenia", None, """ETAP P0 -- DOMKNIECIE _DO_SPRAWDZENIA.md.
Przejdz przez KAZDA pozycje w _DO_SPRAWDZENIA.md. Sprawdz ja w kodzie, bazie (tylko odczyt), crontab/timery (odczyt plikow),
zalogowanym dev_fetch lub na zrzutach w img/ekrany/. Potwierdzone -> popraw haslo, usun znacznik DO SPRAWDZENIA, pozycje przenies
do sekcji "## Wyjasnione" z jednym zdaniem wyniku. Nie do sprawdzenia bez Michala -> zostaw w sekcji "## Pytania do Michala" jako
proste pytanie TAK/NIE albo z wyborem. Dopisz w _RAPORT.md ile wyjasniono / ile zostalo.""")]
for slug, scope, _src in R.MODULES:
    STAGES2.append((f"P_{slug}", slug, f"""ETAP POGLEBIENIE -- DZIAL "{slug}" ({scope}).
Przeczytaj istniejace {slug}/*.md, slowniczek.md, zaleznosci.md, mapa-serwisu.md, _lista_hasel.md. Kazde haslo dzialu
przepisz/rozbuduj wg ZASAD PRZEBIEGU 2 (A-G). Dopisz brakujace hasla z _lista_hasel.md i te oznaczone w _RAPORT.md jako
"nie zdazono" dla tego dzialu (kazda liczba/kafelek/wykres/zakladka widoczna na zrzutach tego dzialu ma miec haslo).
{slug}/index.md: przeglad dzialu dla laika + diagram calego dzialu + zrzut glownej strony + tabela "co widzisz na ekranie -> haslo".
Na koniec zaktualizuj zaleznosci.md i slowniczek.md o nowe rzeczy."""))
STAGES2.append(("P_spojnosc", None, """ETAP KONCOWY -- SPOJNOSC.
1) Sprawdz wszystkie linki wzgledne w wiki (skrypt w _work/): zepsute popraw. 2) Kazdy termin ze slowniczka ma definicje i link do hasla;
hasla bez linku z indeksu dzialu dopisz. 3) README.md: aktualny spis z liczba hasel w dziale, link do mapa-serwisu.md, zaleznosci.md,
slowniczek.md, img/ekrany/indeks.md. 4) Te same liczby opisane w kilku hasłach (np. TSB, W'bal, XSS) -- sprawdz, czy opisy sa zgodne
miedzy soba i z kodem; rozbieznosci opisz w zaleznosci.md (sekcja liczone w wielu miejscach) bez naprawiania kodu.
5) W _RAPORT.md: podsumowanie przebiegu 2 (liczba hasel, srednia dlugosc, lista pytan do Michala zebranych ze wszystkich etapow)."""))


def main() -> int:
    st = {"start": R.now(), "stages": {}, "done": False}
    R.save_status(st)
    R.worklock()
    R.log("PASS2 START")
    t0 = time.time()
    with open(f"{R.OUT}/screens.log", "w") as lf:
        try:
            rc = subprocess.run([R.PY, f"{R.APP}/scripts/wiki_bg/screens.py"], stdout=lf, stderr=subprocess.STDOUT,
                                timeout=40 * 60, cwd=R.APP).returncode
        except subprocess.TimeoutExpired:
            rc = 124
    n_png = len(glob.glob(f"{SHOTS}/*.png"))
    st["stages"]["zrzuty"] = {"status": "OK" if rc == 0 else f"BLAD {rc}", "png": n_png, "min": round((time.time() - t0) / 60)}
    R.save_status(st)
    R.log(f"zrzuty rc={rc} png={n_png}")
    fails = [] if rc == 0 else ["zrzuty"]
    base_dirty = R.dirty_outside_wiki()
    for name, slug, prompt in STAGES2:
        R.worklock()
        st["stages"][name] = {"start": R.now(), "status": "w toku"}
        R.save_status(st)
        t0 = time.time()
        rc = codex2(name, prompt, images_for(slug) if slug else None)
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
    st.update({"done": True, "end": R.now()})
    R.save_status(st)
    subprocess.run([R.PY, f"{R.APP}/scripts/worklock.py", "release", "--who", "wiki-bg"], cwd=R.APP, capture_output=True, timeout=30)
    md = [os.path.join(d, f) for d, _, fs in os.walk(R.WIKI) for f in fs if f.endswith(".md") and "/_work" not in d]
    kb = sum(os.path.getsize(p) for p in md) / 1024
    msg = (f"📘 WIKI QBot — przebieg 2 gotowy ({R.now()}).\n"
           f"Etapy OK: {len(STAGES2) + 1 - len(fails)}/{len(STAGES2) + 1}" + (f"; problemy: {', '.join(fails)}" if fails else "") +
           f"\nHasła/pliki .md: {len(md)} ({kb:.0f} KB), zrzuty: {n_png}.\nPytania do Ciebie: docs/wiki/_DO_SPRAWDZENIA.md")
    if any("UWAGA_zmiany_poza_wiki" in v for v in st["stages"].values()):
        msg += "\n⚠️ Zmiany plików poza wiki — sprawdź status2.json."
    R.tg(msg)
    R.log("PASS2 KONIEC")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa
        R.log(f"PASS2 AWARIA {e!r}")
        R.tg(f"⚠️ WIKI QBot przebieg 2: awaria {e!r}"[:400])
        raise
