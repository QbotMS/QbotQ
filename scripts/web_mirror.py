"""Lustro kodu stron (statyki) w repo (2026-10-04, decyzja uzytkownika; 2026-10-07: + katalog /landing):
    /opt/qbot/web/public  -> /opt/qbot/app/web_public   (strony po zalogowaniu)
    /opt/qbot/web/landing -> /opt/qbot/app/web_landing  (publiczne pliki strony logowania, np. hasla.js; zdjecia/film NIE)

Strony dzialaja dalej prosto z /opt/qbot/web/... (zywe od razu, bez restartu) - lustro daje im HISTORIE w git i KOPIE
na GitHubie. Uruchom PRZED KAZDYM COMMITEM, potem dodaj web_public/ i web_landing/ do commita:
    .venv/bin/python3 scripts/web_mirror.py           # synchronizacja + raport zmian
    .venv/bin/python3 scripts/web_mirror.py --check   # tylko sprawdzenie (kod 1, gdy lustro nieaktualne)
Bierze: .html .js .css .svg .ico oraz male .json (< 200 KB). Pomija: katalogi danych i obrazow (data, reports, gear, strava,
vendor, .git), grafiki i media (jpg/png/webp/pdf/mp4), kopie (*.bak*), pliki robocze (*.tmp_new, _*), wygenerowane mapy (map_*),
pliki > 500 KB.
Plik usuniety ze stron -> usuwany z lustra. Odtworzenie: skopiuj plik z web_public/ (web_landing/) do /opt/qbot/web/public/ (landing/).
Stare lokalne repo git z web/public (lipiec 2026) usuniete 2026-10-04, archiwum: /opt/qbot/data/archive/web_public_git_2026-07.tar.gz.
"""
from __future__ import annotations

import os
import shutil
import sys

PAIRS = (
    ("/opt/qbot/web/public", "/opt/qbot/app/web_public"),
    ("/opt/qbot/web/landing", "/opt/qbot/app/web_landing"),
)
EXT = {".html", ".js", ".css", ".svg", ".ico"}
SKIP_DIRS = {".git", "data", "reports", "gear", "strava", "vendor"}
MAX_BYTES = 500_000
MAX_JSON = 200_000


def wanted(rel: str, size: int) -> bool:
    parts = rel.split("/")
    name = parts[-1]
    if parts[0] in SKIP_DIRS or name.startswith(("_", "map_")) or ".bak" in name or name.endswith(".tmp_new"):
        return False
    ext = os.path.splitext(name)[1].lower()
    if ext == ".json":
        return size < MAX_JSON
    return ext in EXT and size < MAX_BYTES


def scan(root: str, filt: bool) -> dict:
    out = {}
    if not os.path.isdir(root):
        return out
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not (os.path.relpath(os.path.join(dp, d), root).split("/")[0] in SKIP_DIRS)]
        for f in fn:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root)
            size = os.path.getsize(p)
            if not filt or wanted(rel, size):
                out[rel] = p
    return out


def same(a: str, b: str) -> bool:
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def sync(SRC: str, DST: str, check: bool) -> bool:
    """Zwraca True, gdy lustro bylo nieaktualne."""
    src, dst = scan(SRC, True), scan(DST, False)
    new = sorted(r for r in src if r not in dst)
    chg = sorted(r for r in src if r in dst and not same(src[r], dst[r]))
    gone = sorted(r for r in dst if r not in src)
    if check:
        print(f"lustro {DST}: nowe {len(new)}, zmienione {len(chg)}, do usuniecia {len(gone)}")
        return bool(new or chg or gone)
    for r in new + chg:
        t = os.path.join(DST, r)
        os.makedirs(os.path.dirname(t), exist_ok=True)
        shutil.copy2(src[r], t)
    for r in gone:
        os.remove(dst[r])
    if os.path.isdir(DST):
        for dp, dn, fn in sorted(os.walk(DST, topdown=False)):
            if dp != DST and not os.listdir(dp):
                os.rmdir(dp)
    print(f"lustro {SRC} -> {DST}: plikow {len(src)} | nowe {len(new)}, zmienione {len(chg)}, usuniete {len(gone)}")
    for tag, lst in (("+", new), ("~", chg), ("-", gone)):
        for r in lst[:40]:
            print(f"  {tag} {r}")
        if len(lst) > 40:
            print(f"  … i {len(lst) - 40} wiecej")
    return bool(new or chg or gone)


def main(check: bool = False) -> int:
    stale = [sync(s, d, check) for s, d in PAIRS]
    return 1 if (check and any(stale)) else 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
