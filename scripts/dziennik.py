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
    L = ["---", f"tytul: Dziennik {d:%d.%m.%Y}", "dzial: dziennik", "typ: dziennik",
         f"opis: Co zmieniono w QBocie {d:%d.%m.%Y} -- {len(sesje)} sesji, {sum(1 for e in ev if e.get('typ') == 'commit')} commitow.",
         "tagi: [dziennik, zmiany, sesje]", "synonimy: [changelog, log zmian, historia zmian, co zrobiono]",
         f"aktualizacja: {datetime.now():%d.%m.%Y}", "---", "", f"# Dziennik {d:%d.%m.%Y}", "",
         "<!-- PODSUMOWANIE -->", ""]
    if not ev and not dirty:
        L.append("Brak zarejestrowanych zmian.")
    # ── POZIOM 1: zakresy prac (decyzja Michala 19.10.2026) -- jedna linia na sesje: co robiono, kiedy, ile zmian ──
    TYP = {"claim": "zaczyna", "release": "kończy", "commit": "commit", "tlo": "w tle", "wiki": "wiki"}

    def _zakres(s, es):
        tasks = []
        for e in es:   # temat pracy z worklock (task) albo opisy commitow
            t = (e.get("opis") or "").strip()
            if e.get("typ") == "claim" and t and t not in tasks:
                tasks.append(t)
        if not tasks:
            for e in es:
                t = re.sub(r"\s+", " ", (e.get("opis") or "").strip())
                if e.get("typ") in ("commit", "tlo") and t and t not in tasks:
                    tasks.append(t[:110] + ("…" if len(t) > 110 else ""))
        return "; ".join(tasks[:4]) + (f" (+{len(tasks) - 4})" if len(tasks) > 4 else "") or "—"

    rows = []
    for s, es in sesje.items():
        ts = [e.get("t", "")[:5] for e in es if e.get("t")]
        nc = sum(1 for e in es if e.get("typ") == "commit")
        npl = len({p for e in es for p in e.get("pliki", [])})
        od = _pierwszy_dzien(s, d)
        rows.append((s, es, ts, nc, npl, od))
    if rows:
        L += ["## Zakresy prac", "", "| Sesja | Co robiono | Godziny | Zmiany |", "|---|---|---|---|"]
        for s, es, ts, nc, npl, od in rows:
            godz = (f"{min(ts)}–{max(ts)}" if ts else "") + (f" (praca od {od:%d.%m})" if od != d else "")
            L.append(f"| [{s}](#sesja-{re.sub(r'[^a-z0-9]+', '-', s.lower())}) | {_zakres(s, es).replace('|', '/')} | {godz} | "
                     f"{_pl(nc, 'commit', 'commity', 'commitów')}, {_pl(npl, 'plik', 'pliki', 'plików')} |")
        L.append("")
        # ── POZIOM 2: dokladny rejestr ruchow, zwiniety pod kazda sesja ──
        L += ["## Rejestr ruchów", ""]
        for s, es, ts, nc, npl, od in rows:
            L += [f'<details id="sesja-{re.sub(r"[^a-z0-9]+", "-", s.lower())}"><summary><b>{s}</b> — {_pl(len(es), "zdarzenie", "zdarzenia", "zdarzeń")}, '
                  f'{_pl(nc, "commit", "commity", "commitów")}</summary>', ""]
            for e in es:
                pl = e.get("pliki", [])
                pls = (" — " + ", ".join(f"`{x}`" for x in pl[:6]) + (f" (+{len(pl) - 6})" if len(pl) > 6 else "")) if pl else ""
                hs = f" `{e['hash']}`" if e.get("hash") else ""
                L.append(f"- {e.get('t', '')[:5]} **{TYP.get(e.get('typ'), e.get('typ'))}**{hs}: {e.get('opis', '')}{pls}")
            L += ["", "</details>", ""]
    if dirty:
        L += ["## Niezapisane w git (zmienione dzis)", ""]
        for p in dirty:
            L.append(f"- `{p}`" + (f" — sesja {_kto_trzyma([p])}" if _kto_trzyma([p]) else ""))
        L.append("")
    os.makedirs(OUT, exist_ok=True)
    path = f"{OUT}/{d:%Y-%m-%d}.md"
    old = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    m = re.search(r"<!-- PODSUMOWANIE -->\n(.*?)\n(?=## |Brak |<details)", old, re.S)  # zachowaj napisane wczesniej podsumowanie
    txt = "\n".join(L)
    if m and m.group(1).strip():
        txt = txt.replace("<!-- PODSUMOWANIE -->\n", "<!-- PODSUMOWANIE -->\n" + m.group(1).strip() + "\n", 1)
    open(path, "w", encoding="utf-8").write(txt + "\n")
    # spis dni
    days = sorted((os.path.basename(x)[:-3] for x in glob.glob(f"{OUT}/20*.md")), reverse=True)
    idx = ["---", "tytul: Dziennik zmian", "dzial: dziennik", "typ: przeglad",
           "opis: Dzien po dniu, co ktora sesja zmienila w QBocie (zbiera sie samo: worklock, commity, prace w tle).",
           "tagi: [dziennik, changelog, sesje]", "synonimy: [log zmian, historia zmian, changelog]", f"aktualizacja: {datetime.now():%d.%m.%Y}",
           "---", "", "# Dziennik zmian", "",
           "Zbiera sie sam: kazda sesja przy pracy zajmuje pliki (worklock) i podpisuje commity dopiskiem `Sesja: nazwa`. "
           "Noca (23:50) dzien jest porzadkowany, dopisywane jest podsumowanie, a hasla wiki opisujace zmieniony kod sa aktualizowane.", ""]
    for x in days:
        dd = datetime.strptime(x, "%Y-%m-%d")
        idx.append(f"- [{dd:%d.%m.%Y}]({x}.md)")
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
