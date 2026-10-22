#!/usr/bin/env python3
"""qext2_projekt.py -- ZMIANY PROJEKTOWANE QExt2 w symulatorze QBota (decyzja Michala 22.10.2026, sesja qext2proj-2210).

Po co: zmiany wygladu pol Karoo projektujemy i ogladamy NAJPIERW w symulatorze QBota (Garaz > QExt2 > Zmiany projektowane),
bez buildow testowych. Dopiero zaakceptowany projekt przenosimy do Kotlina QExt2 -> jeden build.

Slot projektu: /opt/qbot/web/public/qext2-sim/projekt/
  qext2-kokpit2.js, qext2-stats.js, qext2-makieta.js  -- kopia wersji bazowej, tu edytujemy projekt (port JS pol)
  projekt.json                                        -- baza, lista punktow (nr, tytul, opis, status), warianty do wyboru
Strona: /qext2-makieta.html?b=projekt (w Garazu przelacznik "Obecny build | Zmiany projektowane").
Warianty w kodzie projektu: (window.QV ? window.QV("klucz", "domyslny") : "domyslny") -> wybrany wariant (pigulki, bez przeladowania;
  w tescie dymnym node QV nie istnieje, stad zapis z zapasem).

Komendy (jako qbot, krotkie -- mozna przez dev_shell_exec):
  start [--base SHA7] [--force]   nowy projekt z bazy (domyslnie najnowszy build symulatora)
  status                          baza, punkty, zmienione pliki
  diff [PLIK]                     roznica projekt vs baza (material do przeniesienia do Kotlina)
  test                            test dymny projektu (node, wszystkie scenariusze) -- jak automat qext2_watch
  zrzut [--b projekt|SHA7] [--s N] [--v k:w,...]   strona w przegladarce (Playwright): bledy JS + czy ekrany sa narysowane;
                                  PNG w /opt/qbot/artifacts/qext2-projekt/
  zamknij [--build N]             po buildzie: archiwum projekt-archiwum/<data>/, slot wylaczony
  wdroz --sha SHA --build N [--src DIR]   wyglad buildu w symulatorze = projekt (bez portu AI), wpis w logu, automat pomija commit
"""
from __future__ import annotations

import argparse
import difflib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PUB = Path("/opt/qbot/web/public")
SIM = PUB / "qext2-sim"
PRJ = SIM / "projekt"
ARCH = SIM / "projekt-archiwum"
FILES = ["qext2-kokpit2.js", "qext2-stats.js", "qext2-makieta.js"]
META = PRJ / "projekt.json"
SHOTS = Path("/opt/qbot/artifacts/qext2-projekt")
BASE_URL = "http://127.0.0.1:30181"


def now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def builds() -> list[dict]:
    try:
        return json.loads((SIM / "builds.json").read_text(encoding="utf-8")).get("builds", [])
    except Exception:
        return []


def base_dir(sim_id: str) -> Path:
    return SIM / sim_id


def src_file(sim_id: str, name: str) -> Path:
    p = base_dir(sim_id) / name
    return p if p.exists() else PUB / name   # brak pliku w buildzie -> wersja glowna (jak na stronie)


def load_meta() -> dict | None:
    try:
        return json.loads(META.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_meta(m: dict) -> None:
    tmp = META.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(META)


def cmd_start(a) -> int:
    m = load_meta()
    if m and m.get("active") and not a.force:
        print(f"PROJEKT JUZ AKTYWNY (baza {m.get('base')}, start {m.get('started')}). Uzyj --force albo 'zamknij'.")
        return 2
    bs = builds()
    if a.base:
        b = next((x for x in bs if x.get("sha7") == a.base), None)
        if not b:
            print(f"Brak buildu {a.base} w builds.json"); return 1
    else:
        b = bs[0] if bs else None
    sim_id = (b or {}).get("sim_id") or (b or {}).get("sha7") or ""
    if not sim_id or not base_dir(sim_id).exists():
        print(f"Brak katalogu symulatora dla bazy ({sim_id!r})"); return 1
    PRJ.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        shutil.copyfile(src_file(sim_id, f), PRJ / f)
    label = (f"build {b['build']}" if b.get("build") else f"commit {b['sha7']}") + " · " + (b.get("subject") or "")[:60]
    save_meta({"active": True, "base": sim_id, "base_sha7": b.get("sha7"), "base_label": label, "started": now(),
               "title": a.title or "Zmiany projektowane", "points": [], "variants": []})
    print(f"OK projekt z bazy {sim_id} ({label}) -> {PRJ}")
    return 0


def cmd_status(a) -> int:
    m = load_meta()
    if not m:
        print("Brak projektu."); return 0
    print(f"aktywny={m.get('active')} baza={m.get('base')} start={m.get('started')} :: {m.get('base_label')}")
    for p in m.get("points", []):
        print(f"  {p.get('nr'):>3} [{p.get('status', '?')}] {p.get('title')}")
    for v in m.get("variants", []):
        print(f"  wariant {v.get('key')}: {[o.get('id') for o in v.get('options', [])]} domyslny={v.get('default')}")
    for f in FILES:
        a1 = src_file(m["base"], f).read_text(encoding="utf-8"); b1 = (PRJ / f).read_text(encoding="utf-8")
        n = sum(1 for l in difflib.unified_diff(a1.splitlines(), b1.splitlines(), lineterm="") if l[:1] in "+-" and l[:3] not in ("+++", "---"))
        print(f"  {f}: {'bez zmian' if n == 0 else str(n) + ' zmienionych linii'}")
    return 0


def cmd_diff(a) -> int:
    m = load_meta()
    if not m:
        print("Brak projektu."); return 1
    for f in ([a.plik] if a.plik else FILES):
        a1 = src_file(m["base"], f).read_text(encoding="utf-8").splitlines()
        b1 = (PRJ / f).read_text(encoding="utf-8").splitlines()
        for l in difflib.unified_diff(a1, b1, f"baza/{f}", f"projekt/{f}", lineterm="", n=2):
            print(l)
    return 0


def cmd_test(a) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import qext2_watch  # test dymny automatu (node: wszystkie scenariusze, trzy ekrany)
    ok, msg = qext2_watch.smoke(PRJ)
    print(("OK " if ok else "BLAD ") + str(msg))
    return 0 if ok else 1


CANVAS_JS = """() => Array.from(document.querySelectorAll('canvas')).map(c => {
  try { const x = c.getContext('2d'), d = x.getImageData(0, 0, c.width, c.height).data; let n = 0, t = 0;
    for (let i = 0; i < d.length; i += 64) { t++; if (d[i] + d[i+1] + d[i+2] > 90) n++; }
    return c.id + ' ' + c.width + 'x' + c.height + ' jasne=' + Math.round(100 * n / Math.max(1, t)) + '%'; }
  catch (e) { return c.id + ' blad ' + e; } })"""


def cmd_shot(a) -> int:
    sys.path.insert(0, "/opt/qbot/app"); sys.path.insert(0, str(Path(__file__).resolve().parent))
    from dev_fetch import get_auth
    from playwright.sync_api import sync_playwright
    users, sign, make = get_auth()
    cookie, _ = make(sorted(users)[0], sign)
    q = [f"b={a.b}"] + ([f"s={a.s}"] if a.s is not None else []) + ([f"v={a.v}"] if a.v else [])
    url = f"{BASE_URL}/qext2-makieta.html?" + "&".join(q)
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = SHOTS / (f"{a.b}" + (f"_s{a.s}" if a.s is not None else "") + ".png")
    errs: list[str] = []
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(viewport={"width": 1760, "height": 1100}, device_scale_factor=1)
        ctx.add_cookies([{"name": "qbot_session", "value": cookie, "url": BASE_URL}])
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errs.append("JS: " + str(e)))
        pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)
        pg.goto(url, wait_until="networkidle", timeout=45000)
        pg.wait_for_timeout(a.wait)
        info = pg.evaluate(CANVAS_JS)
        mode = pg.evaluate("() => { const m = document.getElementById('mode'); return m ? m.innerText.replace(/\\n/g, ' | ') : '' }")
        pts = pg.evaluate("() => document.querySelectorAll('#prj .pt').length")
        ev = pg.evaluate("() => JSON.stringify(" + a.eval + ")") if a.eval else None
        pg.screenshot(path=str(out), full_page=True)
        br.close()
    print(f"URL {url}\nprzelacznik: {mode or '(brak)'}\npunkty projektu: {pts}")
    for i in info:
        print("  " + i)
    print("bledy: " + ("brak" if not errs else ""))
    for e in errs[:20]:
        print("  " + e)
    if ev is not None:
        print("eval: " + str(ev)[:1500])
    print(f"zrzut: {out}")
    return 1 if any(e.startswith("JS:") for e in errs) else 0


def cmd_close(a) -> int:
    m = load_meta()
    if not m or not m.get("active"):
        print("Brak aktywnego projektu."); return 0
    dst = ARCH / datetime.now().strftime("%Y%m%d-%H%M")
    shutil.copytree(PRJ, dst)
    m.update({"active": False, "closed": now(), "build": a.build, "archive": str(dst)})
    save_meta(m)
    (dst / "projekt.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK projekt zamkniety, archiwum {dst}")
    return 0


def cmd_wdroz(a) -> int:
    """Po buildzie z projektu: wyglad tego buildu w symulatorze = zaakceptowany projekt (bez portu AI automatu).
    Kopiuje pliki projektu (albo archiwum) do qext2-sim/<sha7>/, dopisuje build do logu (builds.json + stan automatu)
    i ustawia 'last' automatu na ten commit, zeby qext2_watch go nie portowal (port AI duzych zmian bywa przerywany)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import qext2_watch as W
    import fcntl
    W.LOCK.parent.mkdir(parents=True, exist_ok=True)
    lf = open(W.LOCK, "w")
    try:
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)   # ta sama blokada co automat (plik zostaje, liczy sie flock)
    except OSError:
        print(f"Automat qext2_watch wlasnie pracuje ({W.LOCK}) -- sprobuj za chwile."); return 2
    src = Path(a.src) if a.src else (PRJ if (load_meta() or {}).get("active") else sorted(ARCH.iterdir())[-1])
    ci = W.commit_info(a.sha)
    ci.pop("diff", None); ci.pop("body", None)
    dst = SIM / ci["sha7"]
    dst.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        shutil.copyfile(src / f, dst / f)
    ok, msg = W.smoke(dst)
    if not ok:
        print("BLAD test symulatora: " + msg); return 1
    entry = dict(ci, build=a.build, opis=a.opis or ci["subject"], render=True, sim="ok", sim_id=ci["sha7"],
                 uwagi=f"wyglad = zaakceptowany projekt z symulatora ({src.name}), bez portu AI | {msg}")
    st = W.load_state()
    st["builds"] = [b for b in st.get("builds", []) if b.get("sha") != ci["sha"]] + [entry]
    st["last"] = ci["sha"]
    W.save_json(W.STATE, st)
    bj = json.loads((SIM / "builds.json").read_text(encoding="utf-8"))
    bj["builds"] = [entry] + [b for b in bj.get("builds", []) if b.get("sha") != ci["sha"]]
    bj["checked"] = now()
    W.save_json(SIM / "builds.json", bj)
    print(f"OK {ci['sha7']} (build {a.build}) w symulatorze z {src} ; automat ustawiony na ten commit")
    return 0


def main() -> int:
    import getpass
    if getpass.getuser() == "root":
        print("Nie uruchamiaj jako root (pliki qext2-sim musza nalezec do qbot)."); return 1
    ap = argparse.ArgumentParser(description="ZMIANY PROJEKTOWANE QExt2 w symulatorze QBota")
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("start"); s.add_argument("--base"); s.add_argument("--force", action="store_true"); s.add_argument("--title")
    sp.add_parser("status")
    d = sp.add_parser("diff"); d.add_argument("plik", nargs="?")
    sp.add_parser("test")
    z = sp.add_parser("zrzut"); z.add_argument("--b", default="projekt"); z.add_argument("--s", type=int); z.add_argument("--v")
    z.add_argument("--wait", type=int, default=5000); z.add_argument("--eval", help="wyrazenie JS do sprawdzenia na stronie (np. window.__QEXT2_SIM.navData())")
    c = sp.add_parser("zamknij"); c.add_argument("--build")
    wd = sp.add_parser("wdroz"); wd.add_argument("--sha", required=True); wd.add_argument("--build", type=int); wd.add_argument("--src"); wd.add_argument("--opis")
    a = ap.parse_args()
    return {"start": cmd_start, "status": cmd_status, "diff": cmd_diff, "test": cmd_test, "zrzut": cmd_shot,
            "zamknij": cmd_close, "wdroz": cmd_wdroz}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
