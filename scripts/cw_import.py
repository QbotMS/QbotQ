"""Import paczki grafik cwiczen (ZIP z ChatGPT) do bazy TRENERA.

Uzycie: .venv/bin/python3 scripts/cw_import.py /opt/qbot/data/cwiczenia/src/batchN.zip N [--skip key1,key2]
- --skip: grafiki odrzucone przy przegladzie (np. zla technika) - nie wchodza do bazy, raport jako ODRZUCONE,
- sprawdza, ze nazwy plikow (<key>.png) sa w katalogu i naleza do paczki N (obce / brakujace -> raport, obce pomijane),
- zapisuje /opt/qbot/web/public/cwiczenia/<key>.webp (1536 px) + <key>_m.webp (768 px); zmieniona grafika -> nowa wersja,
  stara do /opt/qbot/data/cwiczenia/old/, bez zmian (ta sama suma) -> pomijana,
- manifest.json (w, h, kb, sha1, batch, v),
- dopisuje do tabeli trainer_exercise teksty (kroki, dobrze, blad) z qbot_trener_exercises.TEXTS dla kluczy paczki.
Dok.: docs/TRENER.md "Baza ćwiczeń".
"""
import hashlib
import io
import json
import os
import shutil
import sys
import zipfile

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
from PIL import Image  # noqa: E402

import qbot_trener_exercises as X  # noqa: E402

OUT = X.IMG_DIR
OLD = "/opt/qbot/data/cwiczenia/old"


def main(src: str, batch: int, skip: set | None = None) -> int:
    skip = skip or set()
    os.makedirs(OUT, exist_ok=True); os.makedirs(OLD, exist_ok=True)
    want = {r["key"] for r in X.rows() if r["batch"] == batch}
    known = {r[0] for r in X.CATALOG}
    mp = os.path.join(OUT, "manifest.json")
    man = json.load(open(mp)) if os.path.exists(mp) else {}
    got, new, upd, same, foreign = set(), [], [], [], []
    with zipfile.ZipFile(src) as z:
        for n in z.namelist():
            base = os.path.basename(n)
            if not base.lower().endswith(".png") or base.startswith("._"):
                continue
            key = base[:-4]
            if key not in known:
                foreign.append(base); continue
            if key not in want:
                foreign.append(base + " (inna paczka)")
            if key in skip:
                continue
            raw = z.read(n)
            sha = hashlib.sha1(raw).hexdigest()[:12]
            got.add(key)
            prev = man.get(key)
            if prev and prev.get("sha1") == sha:
                same.append(key); continue
            ver = (prev.get("v", 1) + 1) if prev else 1
            if prev:
                for suf in ("", "_m"):
                    f = f"{OUT}/{key}{suf}.webp"
                    if os.path.exists(f):
                        shutil.move(f, f"{OLD}/{key}{suf}.v{ver - 1}.webp")
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            if im.size != (1536, 1024):
                print("UWAGA rozmiar", key, im.size)
            im.save(f"{OUT}/{key}.webp", "WEBP", quality=82, method=6)
            im.resize((768, round(768 * im.height / im.width)), Image.LANCZOS).save(f"{OUT}/{key}_m.webp", "WEBP", quality=80, method=6)
            man[key] = {"w": im.width, "h": im.height, "kb": os.path.getsize(f"{OUT}/{key}.webp") // 1024,
                        "kb_m": os.path.getsize(f"{OUT}/{key}_m.webp") // 1024, "sha1": sha, "batch": X.batch_of(key), "v": ver}
            (upd if prev else new).append(f"{key} v{ver}")
    json.dump(man, open(mp, "w"), indent=1)
    from fitmodel.api import _db_connect
    from psycopg.rows import dict_row
    conn = _db_connect(); conn.row_factory = dict_row; c = conn.cursor()
    nt = 0
    for k in sorted(got):
        t = X.TEXTS.get(k)
        if t:
            c.execute("UPDATE qbot_v2.trainer_exercise SET steps=%s::jsonb, ok=%s, bad=%s, updated_at=now() WHERE key=%s",
                      (json.dumps(t[0], ensure_ascii=False), t[1], t[2], k)); nt += c.rowcount
    conn.commit(); conn.close()
    print(f"paczka {batch}: nowe {len(new)}, zmienione {len(upd)}, bez zmian {len(same)}, teksty {nt}")
    for x in new + upd:
        print("  +", x)
    if skip:
        print("ODRZUCONE (do poprawki):", ", ".join(sorted(skip)))
    missing = sorted(k for k in want - got - skip if k not in man)   # juz w bazie (np. ZIP z sama poprawka) = nie brakuje
    if missing:
        print("BRAKUJE w ZIP:", ", ".join(missing))
    if foreign:
        print("POMINIETE / obce:", ", ".join(foreign))
    print("w bazie grafik:", len(man), "/", len(known))
    return 0 if not missing else 1


if __name__ == "__main__":
    sk = set()
    if "--skip" in sys.argv:
        sk = {x.strip() for x in sys.argv[sys.argv.index("--skip") + 1].split(",") if x.strip()}
    sys.exit(main(sys.argv[1], int(sys.argv[2]), sk))
