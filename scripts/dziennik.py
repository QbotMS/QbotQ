#!/usr/bin/env python3
"""Dziennik zmian QBota (decyzja Michala 18.10.2026): co ktora sesja zrobila kazdego dnia.

Zrodla zdarzen (zapisywane same):
  - worklock.py claim/release  -> 'praca' (kto, nad czym, pliki, od-do)       [scripts/worklock.py wola log_event]
  - git post-commit hook        -> 'commit' (hash, opis, pliki, Sesja: z dopisku) [.git/hooks/post-commit]
  - zadania w tle               -> 'tlo' (np. przebiegi wiki, nocna aktualizacja)
Zdarzenia: docs/dziennik/zdarzenia/RRRR-MM-DD.jsonl (data = dzien zdarzenia).
Widok: docs/wiki/dziennik/RRRR-MM-DD.md (+ index.md) -> Wiki > Dziennik. Buduje: `dziennik.py build [--date RRRR-MM-DD]` (noc 23:50).

Prace rozlozone na dni: kazdy dzien pokazuje to, co sie w nim WYDARZYLO (zajecie plikow, commit, praca w tle).
Commit zrobiony nastepnego dnia trafia do dnia commitu z dopiskiem "praca od DD.MM" (pierwsze zajecie plikow przez te sesje).
Zmiany niezacommitowane: plik zmieniony tego dnia, a nie w zadnym commicie -> sekcja "Niezapisane w git" (sesja z worklock, jesli znana).

Uzycie:
  dziennik.py log --sesja NAZWA --typ tlo --opis "..." [--pliki a b]
  dziennik.py commit            (z hooka post-commit)
  dziennik.py build [--date RRRR-MM-DD]
"""
from __future__ import annotations
import argparse, glob, json, os, re, subprocess, sys
from datetime import datetime, date, timedelta

APP = "/opt/qbot/app"
EV = f"{APP}/docs/dziennik/zdarzenia"
OUT = f"{APP}/docs/wiki/dziennik"
G = ["git", "-c", f"safe.directory={APP}", "-C", APP]


def log_event(typ: str, sesja: str, opis: str = "", pliki=None, **extra) -> None:
    """Dopisz zdarzenie do dziennika dnia. Nigdy nie rzuca wyjatku (dziennik nie moze psuc pracy)."""
    try:
        os.makedirs(EV, exist_ok=True)
        now = datetime.now()
        rec = {"t": now.strftime("%H:%M:%S"), "typ": typ, "sesja": sesja or "?", "opis": opis, "pliki": list(pliki or [])}
        rec.update(extra)
        fp = f"{EV}/{now:%Y-%m-%d}.jsonl"
        with open(fp, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        try:  # zapisuja i root (worklock, noc), i qbot (hook commita) -> plik wspolny
            os.chmod(fp, 0o666)
        except Exception:
            pass
    except Exception:
        pass


def _git(*a) -> str:
    return subprocess.run(G + list(a), capture_output=True, text=True).stdout


def _sesja_z_opisu(msg: str) -> str | None:
    m = re.search(r"^Sesja:\s*(\S+)", msg, re.M)
    return m.group(1) if m else None


def _kto_trzyma(pliki) -> str | None:
    try:
        st = json.load(open(f"{APP}/.worklock.json"))
        claims = st if isinstance(st, list) else st.get("claims", st)
        for c in (claims.values() if isinstance(claims, dict) else claims):
            fs = c.get("files", []) if isinstance(c, dict) else []
            if any(any(p.endswith(f.lstrip("/").replace("opt/qbot/app/", "")) or f.endswith(p) for f in fs) for p in pliki):
                return c.get("who")
    except Exception:
        pass
    return None


def cmd_commit(_a) -> None:
    h = _git("rev-parse", "HEAD").strip()
    msg = _git("log", "-1", "--format=%B").strip()
    pliki = [p for p in _git("show", "--name-only", "--format=", "HEAD").splitlines() if p]
    sesja = _sesja_z_opisu(msg) or _kto_trzyma(pliki) or "bez-nazwy"
    log_event("commit", sesja, msg.splitlines()[0] if msg else "", pliki, hash=h[:9])


def _events(d: date) -> list[dict]:
    p = f"{EV}/{d:%Y-%m-%d}.jsonl"
    if not os.path.exists(p):
        return []
    out = []
    for ln in open(p, encoding="utf-8"):
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out


def _pierwszy_dzien(sesja: str, d: date, wstecz: int = 14) -> date:
    first = d
    for i in range(1, wstecz + 1):
        dd = d - timedelta(days=i)
        if any(e.get("sesja") == sesja for e in _events(dd)):
            first = dd
    return first


def _pl(n: int, one: str, few: str, many: str) -> str:
    """Polska odmiana: 1 commit, 2 commity, 5 commitow."""
    if n == 1:
        return f"{n} {one}"
    return f"{n} {few}" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else f"{n} {many}"


def build(d: date) -> str:
    ev = _events(d)
    # commity z git (takze te zrobione bez hooka)
    known = {e.get("hash") for e in ev if e.get("typ") == "commit"}
    raw = _git("log", f"--since={d:%Y-%m-%d} 00:00", f"--until={d:%Y-%m-%d} 23:59:59", "--format=%H%x1f%ad%x1f%B%x1e", "--date=format:%H:%M:%S")
    for chunk in raw.split("\x1e"):
        if not chunk.strip():
            continue
        h, t, body = (chunk.strip("\n").split("\x1f") + ["", ""])[:3]
        if h[:9] in known:
            continue
        pliki = [p for p in _git("show", "--name-only", "--format=", h).splitlines() if p]
        ev.append({"t": t, "typ": "commit", "sesja": _sesja_z_opisu(body) or "bez-nazwy", "opis": body.strip().splitlines()[0] if body.strip() else "", "pliki": pliki, "hash": h[:9]})
    # zmiany niezacommitowane, zmienione tego dnia
    commited = {p for e in ev if e.get("typ") == "commit" for p in e.get("pliki", [])}
    dirty = []
    for ln in _git("status", "--porcelain").splitlines():
        p = ln[3:].strip()
        fp = os.path.join(APP, p)
        if p.startswith(("docs/dziennik/", "docs/wiki/_work")) or ".bak" in p or os.path.basename(p).startswith("_tmp") or not os.path.isfile(fp):
            continue
        if datetime.fromtimestamp(os.path.getmtime(fp)).date() == d and p not in commited:
            dirty.append(p)
    ev.sort(key=lambda e: e.get("t", ""))
    sesje: dict[str, list] = {}
    for e in ev:
        sesje.setdefault(e.get("sesja", "?"), []).append(e)
    TYP = {"claim": "zaczyna", "release": "kończy", "commit": "commit", "tlo": "w tle", "wiki": "wiki"}

    def _zakres(es):
        tasks = []
        for e in es:   # temat pracy: z worklock (task), a gdy brak -- z opisow commitow / prac w tle
            t = (e.get("opis") or "").strip()
            if e.get("typ") == "claim" and t and t not in tasks:
                tasks.append(t)
        if not tasks:
            for e in es:
                t = re.sub(r"\s+", " ", (e.get("opis") or "").strip())
                if e.get("typ") in ("commit", "tlo") and t and t not in tasks:
                    tasks.append(t[:110] + ("…" if len(t) > 110 else ""))
        return tasks

    rows = []
    for s_, es in sesje.items():
        ts = [e.get("t", "")[:5] for e in es if e.get("t")]
        nc = sum(1 for e in es if e.get("typ") == "commit")
        npl = len({x for e in es for x in e.get("pliki", [])})
        od = _pierwszy_dzien(s_, d)
        rows.append({"sesja": s_, "zakres": _zakres(es), "od_do": (f"{min(ts)}–{max(ts)}" if ts else ""),
                     "praca_od": (f"{od:%d.%m}" if od != d else ""), "commity": nc, "pliki": npl, "es": es})

    os.makedirs(OUT, exist_ok=True)
    path = f"{OUT}/{d:%Y-%m-%d}.md"
    old = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    m = re.search(r"<!-- PODSUMOWANIE -->\n(.*?)\n(?=## |Brak |<details|_Brak)", old, re.S)   # podsumowanie z nocy zostaje
    podsum = m.group(1).strip() if m else ""
    ncom = sum(r["commity"] for r in rows)

    # ── POZIOM 2: strona dnia = rejestr ruchow ──
    L = ["---", f"tytul: Dziennik {d:%d.%m.%Y}", "dzial: dziennik", "typ: dziennik",
         f"opis: Rejestr ruchow {d:%d.%m.%Y} -- {_pl(len(rows), 'sesja', 'sesje', 'sesji')}, {_pl(ncom, 'commit', 'commity', 'commitow')}.",
         "tagi: [dziennik, zmiany, sesje]", "synonimy: [changelog, log zmian, historia zmian, co zrobiono]",
         f"aktualizacja: {datetime.now():%d.%m.%Y}", "---", "", f"# Dziennik {d:%d.%m.%Y} — rejestr ruchów", "",
         "[← Dziennik zmian: wszystkie dni, zakresy prac](index.md)", "", "<!-- PODSUMOWANIE -->"]
    if podsum:
        L.append(podsum)
    L.append("")
    if not rows and not dirty:
        L.append("_Brak zarejestrowanych zmian._")
    for r in rows:
        zak = "; ".join(r["zakres"]) or "—"
        L += [f"## {r['sesja']}", "",
              f"**{zak}** · {r['od_do']}" + (f" (praca od {r['praca_od']})" if r["praca_od"] else "") +
              f" · {_pl(r['commity'], 'commit', 'commity', 'commitów')}, {_pl(r['pliki'], 'plik', 'pliki', 'plików')}", ""]
        for e in r["es"]:
            pl = e.get("pliki", [])
            pls = (" — " + ", ".join(f"`{x}`" for x in pl[:6]) + (f" (+{len(pl) - 6})" if len(pl) > 6 else "")) if pl else ""
            hs = f" `{e['hash']}`" if e.get("hash") else ""
            opis = e.get("opis", "") or ""
            L.append(f"- {e.get('t', '')[:5]} **{TYP.get(e.get('typ'), e.get('typ'))}**{hs}" + (f": {opis}" if opis else "") + pls)
        L.append("")
    if dirty:
        L += ["## Niezapisane w git (zmienione tego dnia)", ""]
        for x in dirty:
            k = _kto_trzyma([x])
            L.append(f"- `{x}`" + (f" — sesja {k}" if k else ""))
        L.append("")
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")

    # podsumowanie dnia do spisu (poziom 1)
    sj = f"{OUT}/_dni.json"
    try:
        dni = json.load(open(sj, encoding="utf-8"))
    except Exception:
        dni = {}
    dni[f"{d:%Y-%m-%d}"] = {"podsumowanie": podsum, "dirty": len(dirty),
                            "wiersze": [{k: v for k, v in r.items() if k != "es"} for r in rows]}
    json.dump(dni, open(sj, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ── POZIOM 1: 'Dziennik zmian' = dzien po dniu, tabela zakresow prac ──
    idx = ["---", "tytul: Dziennik zmian", "dzial: dziennik", "typ: przeglad",
           "opis: Dzien po dniu: zakresy prac w QBocie (kto, co, kiedy); szczegolowy rejestr ruchow po wejsciu w dzien.",
           "tagi: [dziennik, changelog, sesje]", "synonimy: [log zmian, historia zmian, changelog, co zrobiono]",
           f"aktualizacja: {datetime.now():%d.%m.%Y}", "---", "", "# Dziennik zmian", "",
           "Dzień po dniu: **co faktycznie robiono**. Kliknij datę, żeby zobaczyć pełny rejestr ruchów tego dnia "
           "(każde zajęcie plików, commit i praca w tle). Zbiera się samo; o 23:50 dopisywane jest podsumowanie dnia.", ""]
    for day in sorted(dni, reverse=True):
        info = dni[day]
        dd = datetime.strptime(day, "%Y-%m-%d")
        ws = info.get("wiersze", [])
        idx += [f"## [{dd:%d.%m.%Y}]({day}.md)", ""]
        if info.get("podsumowanie"):
            first = re.split(r"\n\s*\n", info["podsumowanie"])[0].strip()
            idx += [first, ""]
        if ws:
            idx += ["| Sesja | Co robiono | Godziny | Zmiany |", "|---|---|---|---|"]
            for w in ws:
                zak = "; ".join(w["zakres"][:3]) + (f" (+{len(w['zakres']) - 3})" if len(w["zakres"]) > 3 else "") if w["zakres"] else "—"
                godz = w["od_do"] + (f" (od {w['praca_od']})" if w["praca_od"] else "")
                idx.append(f"| {w['sesja']} | {zak.replace('|', '/')} | {godz} | "
                           f"{_pl(w['commity'], 'commit', 'commity', 'commitów')}, {_pl(w['pliki'], 'plik', 'pliki', 'plików')} |")
            idx.append("")
        else:
            idx += ["_Brak zarejestrowanych zmian._", ""]
        idx += [f"[Rejestr ruchów {dd:%d.%m} →]({day}.md)", ""]
    open(f"{OUT}/index.md", "w", encoding="utf-8").write("\n".join(idx) + "\n")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    l = sp.add_parser("log"); l.add_argument("--sesja", required=True); l.add_argument("--typ", default="tlo"); l.add_argument("--opis", default=""); l.add_argument("--pliki", nargs="*", default=[])
    sp.add_parser("commit")
    b = sp.add_parser("build"); b.add_argument("--date")
    a = ap.parse_args()
    if a.cmd == "log":
        log_event(a.typ, a.sesja, a.opis, a.pliki)
    elif a.cmd == "commit":
        cmd_commit(a)
    else:
        d = datetime.strptime(a.date, "%Y-%m-%d").date() if a.date else date.today()
        print(build(d))


if __name__ == "__main__":
    main()
