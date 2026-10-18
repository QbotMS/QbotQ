#!/usr/bin/env python3
"""WIKI-QBOT -- runner w tle (zlecone 18.10.2026).

Pisze SZKICE hasel wiki do docs/wiki/ przy pomocy `codex exec` (etap po etapie).
- Kazdy etap = osobne wywolanie codexa, limit czasu, log w /opt/qbot/artifacts/wiki_bg/.
- Codex pisze TYLKO w docs/wiki (sandbox workspace-write, cwd=docs/wiki); baza tylko do odczytu (PGOPTIONS).
- Na koniec (albo przy awarii) jedna wiadomosc Telegram. Bez commitow -- szkice czekaja na przeglad Michala.
Uruchamianie: scripts/wiki_bg/launch.py (systemd-run, nie blokuje DEV MCP).
Status: /opt/qbot/artifacts/wiki_bg/status.json
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

APP = "/opt/qbot/app"
WIKI = f"{APP}/docs/wiki"
OUT = "/opt/qbot/artifacts/wiki_bg"
STATUS = f"{OUT}/status.json"
PY = f"{APP}/.venv/bin/python3"
STAGE_TIMEOUT = 50 * 60

sys.path.insert(0, APP)
os.environ.setdefault("QBOT3_ENABLED", "1")

COMMON = f"""Jestes autorem WIKI QBota -- dokumentacji "po ludzku" dla wlasciciela (hobbysta technologii, NIE programista).
Pracujesz w katalogu {WIKI} (to jest Twoj katalog roboczy). Kod i dokumentacja QBota: {APP} (tylko do CZYTANIA).
Statyczne strony www: /opt/qbot/web/public (tylko do czytania). Najpierw przeczytaj {APP}/docs/CONTEXT.md oraz {WIKI}/_szablon.md (jesli juz istnieje).

TWARDE ZASADY:
1. Piszesz WYLACZNIE pliki .md (i .svg na ilustracje) wewnatrz {WIKI}. NIE zmieniasz zadnego innego pliku, nie robisz git commit, nie restartujesz uslug.
2. Baza danych tylko do ODCZYTU (polaczenie: {PY} + `sys.path.insert(0,'{APP}'); os.environ['QBOT3_ENABLED']='1'; from fitmodel.api import _db_connect`). Zapytania krotkie (LIMIT, waskie zakresy dat), zadne nie dluzej niz 60 s. Skrypty pomocnicze trzymaj w {WIKI}/_work/ i nie uruchamiaj niczego ciezkiego (petli po plikach FIT, przeliczen sezonu).
3. ZASADY PRAWDY: piszesz tylko to, co sprawdziles w kodzie / bazie / dokumentach. Gdy dokument rozjezdza sie z kodem -- wygrywa kod i zaznacz rozjazd. Czego nie udalo sie potwierdzic -> oznacz w tekscie znacznikiem `> DO SPRAWDZENIA: ...` i dopisz do {WIKI}/_DO_SPRAWDZENIA.md. Zero zgadywania i "zgrubnych interpretacji". Pod kazdym haslem sekcja "Zrodla" (sciezki plikow, nazwy funkcji/tabel) -- male litery, na samym dole.
4. Jezyk: polski, prosto, krotkie zdania, bez zargonu (gdy termin konieczny -- wyjasnij i podlinkuj do slowniczek.md). Daty DD.MM.RRRR, wiatr w m/s, tydzien = pon-nd. ModelQ nie uzywa FTP -- mow o progu/TP/CP.
5. ILUSTRACJE: kazde haslo opisujace przeplyw/algorytm ma diagram Mermaid (```mermaid, flowchart LR/TD, polskie etykiety, max ~15 wezlow). Tam gdzie pomaga -- prosty wykres/schemat jako plik .svg w {WIKI}/img/ (czysty SVG, bez zewnetrznych zasobow). Przyklady liczbowe z PRAWDZIWYCH danych z bazy (podaj date).
6. Linki miedzy haslami: wzgledne linki markdown ([TP](../modelq/tp.md)). Kazde haslo ma sekcje "Powiazane hasla" i "Wplywa na / Zalezy od".
7. Na koniec etapu dopisz do {WIKI}/_RAPORT.md sekcje "## <nazwa etapu> -- <data godz>" : co powstalo (lista plikow), czego nie udalo sie sprawdzic, pytania do Michala (max 5). Krotko.
"""

STAGES = [
    ("E1_szkielet", """ETAP 1 -- SZKIELET WIKI.
Utworz: README.md (strona glowna: czym jest wiki, jak czytac, spis dzialow z linkami), _szablon.md (staly szablon hasla:
Co to jest (1-2 zdania) / Po co (jaka decyzje pomaga podjac) / Skad dane (zrodlo, jak czesto) / Jak liczone (prosto + przyklad na prawdziwych liczbach;
wzor opcjonalnie w <details>) / Gdzie to widac (strony, Albert, Telegram, Karoo) / Jak czytac (progi, kolory, co dobre/zle) /
Decyzje i historia (z docs/DECISIONS.md: dlaczego tak, a nie inaczej) / Ograniczenia i pulapki / Wplywa na / Zalezy od / Powiazane hasla / Zrodla),
_DO_SPRAWDZENIA.md, _RAPORT.md oraz katalogi dzialow (pusty index.md w kazdym): modelq, forma, raport-jazdy, trener, trasy, pogoda, zdrowie, garaz, qext2, albert, polaczenia, system.
Dzialy w README w tej kolejnosci. Nie pisz jeszcze hasel."""),
    ("E2_mapa_serwisu", """ETAP 2 -- MAPA SERWISU (plik mapa-serwisu.md + img/mapa-serwisu.svg).
Zinwentaryzuj NA ZYWO (z kodu, nie z pamieci): (a) strony www i menu (nav.js, pliki .html w /opt/qbot/web/public -- ktore sa w menu, ktore przekierowuja, zakladki kazdej strony);
(b) kanaly: Telegram, Albert (MCP/Telegram), Karoo/QExt2, Strava; (c) automaty: cron (crontab -l moze byc niedostepny -- szukaj w docs i kodzie: timery systemd qbot*, harmonogramy w kodzie), co i jak czesto sie uruchamia;
(d) zrodla danych zewnetrzne (Garmin, Hammerhead, Withings, RWGPS, Komoot, Strava, intervals.icu, Open-Meteo, radar, OSM, Google Places, Brokul...) -- co z kazdego bierzemy i jak czesto.
Wynik: tabela "Strona -> co pokazuje -> skad dane -> haslo wiki (link do przyszlego pliku)", tabela automatow, tabela zrodel, oraz diagram Mermaid calego serwisu (zrodla -> silniki -> strony/kanaly).
Kazdej pozycji przypisz dzial wiki. Na koncu lista WSZYSTKICH przyszlych hasel (plik + jednozdaniowy opis) -- to bedzie plan pisania; zapisz ja tez do _lista_hasel.md."""),
    ("E3_zaleznosci", """ETAP 3 -- MAPA WPLYWOW I ZALEZNOSCI (plik zaleznosci.md + img/zaleznosci.svg).
Opisz, co wplywa na co: lancuchy danych i obliczen miedzy modulami, sprawdzone w kodzie (importy, wywolania funkcji, tabele czytane/pisane).
Np. jazda z Garmina -> activity_record -> ModelQ (TP/HIE/PP, W'bal, XSS) -> obciazenie CTL/ATL/TSB -> Forma/gotowosc -> Trener (plan) -> QExt2 (Karoo) / raport z jazdy -> Strava opis; waga/sen/HRV -> gotowosc; pogoda -> analiza trasy, doradca ubioru, Trener; Garaz -> rower w raporcie...
Wynik: (1) macierz "modul A wplywa na modul B -- przez jaka liczbe/tabele", (2) kilka diagramow Mermaid (calosc + 4-5 najwazniejszych lancuchow), (3) sekcja "Liczby liczone w wiecej niz jednym miejscu" -- gdzie ten sam sygnal (np. swiezosc, TSB, W'bal) jest liczony lub uzyty kilkukrotnie i czy wyniki sa spojne (fakty z kodu, bez naprawiania), (4) sekcja "Pojedyncze punkty awarii" -- czego brak zatrzymuje inne moduly.
Uzupelnij tez slowniczek.md o wszystkie pojecia, ktore pojawily sie w mapie (definicja 1-2 zdania + link do hasla)."""),
]

MODULES = [
    ("modelq", "ModelQ: TP, HIE, PP, LTP, CP/W', W'bal, XSS, kalibracja/kotwice, Xert tylko jako sprawdzian",
     "docs/MODELQ.md, docs/MODELQ_PRZEGLAD.md, docs/PROGI_MODELQ.md, docs/PROJEKT_mpa_dwa_zasobniki.md, katalog fitmodel/, docs/DECISIONS.md"),
    ("forma", "Forma i Wellness: CTL/ATL/TSB (kanon swiezosci), status dnia, norma tetna 60 dni, trend, HRV, sen, Body Battery, gotowosc, waga",
     "docs/FORMA_UI_LAYOUT.md, docs/GARMIN_DANE.md, docs/SERCE.md, qbot_web.py (_build_forma_data, /api/forma/analyze), /opt/qbot/web/public/forma*.js"),
    ("raport-jazdy", "Raport z jazdy: NP, IF, W'bal Karoo vs ModelQ, przewyzszenie, nawierzchnia, plan vs wykonanie, analiza AI, opis Strava",
     "kod raportu jazdy (szukaj ride_report / rebuild_ride_reports.py), docs/STRAVA_PUBLISH.md, fit_ingest"),
    ("trener", "Trener: plan tygodnia, Sezon, okna/dostepnosc, planowane XSS, sila/wioslarz, bilans i tempo wagi, powiadomienia, trasy w treningu",
     "docs/TRENER.md, qbot_trener_*.py, /opt/qbot/web/public/trener.js, kalendarz3.js"),
    ("trasy", "Trasy: analiza trasy, nawierzchnia (lokalny OSM), podjazdy, POI/atrakcje, czas przejazdu v2, wykonalnosc, naprawa tras, store/wersje, potwierdzenia Telegram, planer wypraw",
     "docs/RAPORT_WEB.md, ROUTE_STORE.md, ROUTE_TIME_ESTIMATE_V2.md, PROJEKT_NAPRAWA_TRAS.md, OSM_LOCAL_SURFACE.md, PLANER_WYPRAW_ATRAKCJE.md, AUDYT_NAWIERZCHNIA.md, TELEGRAM_ROUTE_CONFIRM.md, Qbot_Route_Logistics.md"),
    ("pogoda", "Pogoda: wspolny silnik meteo, wiatr m/s, radar/opad, ostrzezenia, sprawdzalnosc, okno pogodowe, pogoda na trasie i dla QExt2",
     "docs/POGODA_*.md, METEO_ENGINE.md, PROJEKT_METEO.md"),
    ("zdrowie", "Zdrowie i Jedzenie: dziennik, cel kcal i bialko, okno 10-20, paliwo na rower, Brokul, Plan weekendu, suplementy, Serce, passa",
     "docs/PROJEKT_ODZYWIANIE.md, BROKUL.md, SUPLEMENTY.md, SERCE.md, kod qbot_food_*.py"),
    ("garaz", "Garaz: rowery, kola i opony, komponenty, rozpoznawanie roweru w jezdzie, Zakupy, doradca ubioru",
     "docs/GARAZ.md, ZAKUPY.md, GEAR_OBS.md, OUTFIT_ADVISOR_RULES.md, OUTFIT_FAVORITES.md"),
    ("qext2", "QExt2/Karoo -- TYLKO strona QBota: co QBot wysyla na Karoo i co odbiera (KOKPIT 2, pole dynamiczne, tryb AUTO, pacing, pogoda INFO, brama, pola FIT). QExt2 to osobny projekt -- kod w /opt/qbot/qext2_deploy czytaj tylko, by opisac dzialanie",
     "docs/QEXT2_CONFIG.md, endpointy /api/qext2*, fit_ingest (fitmodel_qext2_ride), /opt/qbot/qext2_deploy"),
    ("albert", "Albert: co umie, jak rozpoznaje pytania (routing), lista narzedzi i do czego sluza, pamiec, kanaly (Telegram, MCP), czego nie robi",
     "docs/architecture/QBOT_ARCHITEKTURA_QBOT3.md, qbot3/tool_registry.py, qbot3/llm/albert.py (_SYSTEM), qbot_query_handler, docs/QBOT3_TELEGRAM_TRANSPARENT_UI.md"),
    ("polaczenia", "Polaczenia i dane: Garmin, Hammerhead->Garmin (TACX), Withings->Garmin, Komoot, RWGPS, Strava, intervals.icu, Xert, harmonogram importow",
     "docs/GARMIN_DANE.md, STATUS.md, SETUP.md, STRAVA_PUBLISH.md"),
    ("system", "System: STATUS, Centrum powiadomien, logowanie/demo, audyt tygodniowy, kopie bazy, bezpieczniki, paleta UI, warstwa legacy",
     "docs/STATUS.md, NOTIF_CENTER.md, WEB_DEMO_AUTH.md, docs/audit/, LEGACY_USAGE.md, UI_PALETA.md"),
]

for slug, scope, src in MODULES:
    STAGES.append((f"H_{slug}", f"""ETAP HASLA -- DZIAL "{slug}".
Zakres dzialu: {scope}.
Zacznij od zrodel: {src} (+ kod, ktory te dokumenty opisuja; sprawdz, czy dokument jest aktualny).
Uzyj listy hasel z _lista_hasel.md dla tego dzialu (popraw ja, jesli czegos brakuje). Napisz:
- {slug}/index.md: przeglad dzialu prostym jezykiem (3-6 zdan), diagram Mermaid jak dzial dziala od danych do tego, co widzi Michal, lista hasel z opisem 1 zdania.
- po jednym pliku na haslo ({slug}/<haslo>.md) wg _szablon.md -- kazda liczba/funkcja/automat widoczny w serwisie dostaje haslo. Algorytmy wyjasniaj krok po kroku na prawdziwym przykladzie z bazy.
- sekcja "Wplywa na / Zalezy od" spojna z zaleznosci.md (jesli znajdziesz nowe powiazanie -- dopisz je tez do zaleznosci.md).
- nowe pojecia do slowniczek.md.
Gdy dzial jest duzy, najpierw zrob hasla najwazniejsze (te widoczne na stronach), na koniec poboczne; lepiej mniej hasel porzadnie niz wszystkie po lebkach -- reszte wpisz do _RAPORT.md jako "nie zdazono"."""))


def now() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M")


def save_status(st: dict) -> None:
    tmp = STATUS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATUS)


def tg(text: str) -> None:
    try:
        import qbot_trener_notify as N
        ok, info = N.send(text)
        log(f"telegram: {ok} {info}")
    except Exception as e:  # noqa
        log(f"telegram EXC {e}")


def log(msg: str) -> None:
    with open(f"{OUT}/runner.log", "a") as f:
        f.write(f"[{now()}] {msg}\n")


def worklock() -> None:
    subprocess.run([PY, f"{APP}/scripts/worklock.py", "claim", "--who", "wiki-bg", "--task",
                    "WIKI-QBOT szkice w tle (codex)", "--files", "docs/wiki/"],
                   cwd=APP, capture_output=True, timeout=30)


def codex(name: str, prompt: str, bypass: bool, timeout: int = STAGE_TIMEOUT) -> int:
    env = dict(os.environ)
    env["PGOPTIONS"] = "-c default_transaction_read_only=on -c statement_timeout=60000"
    cmd = ["codex", "exec", "--skip-git-repo-check", "-C", WIKI, "-o", f"{OUT}/{name}.last.txt"]
    if bypass:
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
    else:
        cmd += ["-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=true"]
    cmd.append(COMMON + "\n\n" + prompt)
    with open(f"{OUT}/{name}.log", "w") as lf:
        try:
            r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                               timeout=timeout, env=env, cwd=WIKI)
            return r.returncode
        except subprocess.TimeoutExpired:
            lf.write("\n### TIMEOUT\n")
            return 124


def dirty_outside_wiki() -> set[str]:
    r = subprocess.run(["git", "-c", f"safe.directory={APP}", "-C", APP, "status", "--porcelain"],
                       capture_output=True, text=True, timeout=60)
    return {ln[3:] for ln in r.stdout.splitlines() if not ln[3:].startswith("docs/wiki")}


def smoke(bypass: bool) -> bool:
    p = f"{WIKI}/_work/smoke.txt"
    if os.path.exists(p):
        os.remove(p)
    rc = codex("smoke_bypass" if bypass else "smoke",
               f"Test srodowiska. Utworz plik _work/smoke.txt zawierajacy pierwsza linie pliku {APP}/docs/CONTEXT.md "
               f"oraz wynik zapytania SQL `SELECT count(*) FROM qbot_v2.training_sessions` (polacz sie jak w zasadach). Nic wiecej.",
               bypass, timeout=8 * 60)
    txt = open(p).read() if os.path.exists(p) else ""
    ok = "QBot" in txt and re.search(r"\b\d{2,}\b", txt) is not None  # plik + odczyt z bazy
    log(f"smoke bypass={bypass} rc={rc} ok={ok} tresc={open(p).read()[:200] if os.path.exists(p) else '-'}")
    return ok


def main() -> int:
    os.makedirs(f"{WIKI}/_work", exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    st = {"start": now(), "stages": {}, "mode": None, "done": False}
    save_status(st)
    worklock()
    log("START")
    bypass = False
    if not smoke(False):
        if smoke(True):
            bypass = True
        else:
            st["mode"] = "BRAK"
            st["done"] = True
            save_status(st)
            tg("⚠️ WIKI QBot: zadanie w tle nie wystartowało — codex nie działa na serwerze (test środowiska). Szczegóły: /opt/qbot/artifacts/wiki_bg/runner.log")
            return 1
    st["mode"] = "bypass+guard" if bypass else "sandbox"
    base_dirty = dirty_outside_wiki()
    fails = []
    for name, prompt in STAGES:
        worklock()
        st["stages"][name] = {"start": now(), "status": "w toku"}
        save_status(st)
        t0 = time.time()
        rc = codex(name, prompt, bypass)
        mins = round((time.time() - t0) / 60)
        res = "OK" if rc == 0 else ("LIMIT CZASU" if rc == 124 else f"BLAD {rc}")
        st["stages"][name].update({"end": now(), "min": mins, "status": res})
        if rc != 0:
            fails.append(name)
        new_dirty = dirty_outside_wiki() - base_dirty
        if new_dirty:
            st["stages"][name]["UWAGA_zmiany_poza_wiki"] = sorted(new_dirty)[:30]
            log(f"UWAGA zmiany poza wiki po {name}: {sorted(new_dirty)[:30]}")
            base_dirty |= new_dirty
        save_status(st)
        log(f"{name}: {res} ({mins} min)")
    st["done"] = True
    st["end"] = now()
    save_status(st)
    subprocess.run([PY, f"{APP}/scripts/worklock.py", "release", "--who", "wiki-bg"], cwd=APP, capture_output=True, timeout=30)
    n = sum(len(fs) for _, _, fs in os.walk(WIKI)) if os.path.isdir(WIKI) else 0
    msg = (f"📘 WIKI QBot — szkice gotowe ({now()}).\n"
           f"Etapy: {len(STAGES) - len(fails)}/{len(STAGES)} OK" + (f"; problemy: {', '.join(fails)}" if fails else "") +
           f"\nPlików w docs/wiki: {n}. Raport: docs/wiki/_RAPORT.md, do sprawdzenia: docs/wiki/_DO_SPRAWDZENIA.md")
    if any("UWAGA_zmiany_poza_wiki" in v for v in st["stages"].values()):
        msg += "\n⚠️ Wykryto zmiany plików poza wiki — sprawdź status.json."
    tg(msg)
    log("KONIEC")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa
        log(f"AWARIA {e!r}")
        tg(f"⚠️ WIKI QBot: zadanie w tle przerwane awarią: {e!r}"[:400])
        raise
