"""TRENER - sila z BAZY CWICZEN, ulozona w BLOKI CIEZARU (2026-10-03).

Zastepuje stary obwod z qbot_trener_workouts (BASE/EXTRA) dla przyszlych sesji silowych. Zasady (decyzja uzytkownika):
- partie w kazdym treningu: nogi, tyl ciala, plecy, klatka, barki, brzuch + akcent dnia (rotacja ACCENTS jak dotad,
  1-2 dodatkowe cwiczenia; ramiona w akcencie "klatka + ramiona"); "bez ..." (opts.skip_groups) usuwa partie;
- wybor: ~70% podstawowe (P, losowane wg gwiazdek 3:2:1 -> wagi 6:3:1), ~30% rotacyjne (R); akcent najpierw R;
  nigdy: pomijaj (X), bez grafiki, srednia ocen sesji <= 2, to samo co w poprzednim treningu; R tez nie z ostatnich 3;
  poziom: minimum (cut) = tylko 1, okresy bz/bd do 3, inne do 2; brzuch tylko bez hantli (blok koncowy);
- bloki: C (10-12 kg) -> S (6-8 kg) -> L (2-4 kg), maks. 2 zmiany ciezaru (3. klasa -> wymiana cwiczenia na inne z tej
  partii w klasie istniejacego bloku); cwiczenia bez hantli wpychane do blokow z ciezarem (przerwa od ciezaru),
  brzuch na koniec; w bloku przeplot gora / dol;
- ciezar bloku: Twoje zapisane kg (trainer_exercise_user.weight_kg) albo domyslne C 10 / S 6 / L 3;
- zestaw ZAPISANY w qbot_v2.trainer_workout (username, day, sport) z podpisem (okres, czas, minimum, pominiete partie):
  nie zmienia sie przy odswiezaniu / Telegramie / Albercie; losuje sie od nowa tylko gdy podpis sie zmieni.
Czesci czyste (choose, build_blocks, render) testowane w tests/test_trener_sila.py.
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from datetime import date

import qbot_trener_workouts as TW

VERSION = "baza1"
GLABEL = {"nogi": "nogi", "tyl": "tył ciała", "plecy": "plecy", "klatka": "klatka", "barki": "barki", "ramiona": "ramiona", "core": "brzuch"}
BASE_GROUPS = ["nogi", "tyl", "plecy", "klatka", "barki", "core"]
ACC_GROUPS = {"klatka + ramiona": ["klatka", "ramiona"], "plecy": ["plecy", "plecy"], "nogi": ["nogi", "tyl"], "brzuch": ["core", "core"]}
SKIP_MAP = {"nogi": {"nogi", "tyl"}, "klatka": {"klatka"}, "ramiona": {"ramiona"}, "plecy": {"plecy"}, "barki": {"barki"}, "brzuch": {"core"}}
LOWER = {"nogi", "tyl"}
P_SHARE = 0.7
PRIO_W = {3: 6, 2: 3, 1: 1, 0: 1}
DEF_KG = {"C": 10, "S": 6, "L": 3}
CLS_ORDER = ["C", "S", "L"]
CLS_TXT = {"C": "ciężko", "S": "średnio", "L": "lekko"}


def accent_for(n: int, skipped: set) -> str | None:
    for k in range(len(TW.ACCENTS)):
        a = TW.ACCENTS[(n + k) % len(TW.ACCENTS)]
        if not set(ACC_GROUPS[a]) <= skipped:
            return a
    return None


def _wchoice(rng, items, weights):
    tot = sum(weights)
    r = rng.random() * tot
    for it, w in zip(items, weights):
        r -= w
        if r <= 0:
            return it
    return items[-1]


def choose(pool: list, hist: list, *, n: int, phase: str | None, cut: bool, dur_min: int, skip: list | None,
           bad: set | None = None, seed: str = "") -> dict:
    """pool: [{key,name,grp,level,wclass,tier,prio,img,dose}], hist: [[keys] ostatnich treningow, najnowszy pierwszy]."""
    rng = random.Random(int(hashlib.sha1(seed.encode()).hexdigest()[:12], 16))
    skip = TW.clean_skip(skip)
    skipped = set().union(*[SKIP_MAP.get(g, set()) for g in skip]) if skip else set()
    maxlvl = 1 if cut else (3 if phase in ("bz", "bd") else 2)
    last = set(hist[0]) if hist else set()
    recent = set(k for h in hist[:3] for k in h)
    bad = bad or set()
    used: set = set()

    def ok(x, g, tiers, strict=True, classes=None):
        if x["grp"] != g or not x.get("img") or x["tier"] not in tiers or x["tier"] == "X" or x["key"] in used or x["key"] in bad:
            return False
        if x["level"] > maxlvl or (g == "core" and x["wclass"] != "0"):
            return False
        if classes is not None and x["wclass"] not in classes:
            return False
        if strict and (x["key"] in last or (x["tier"] == "R" and x["key"] in recent)):
            return False
        return True

    def pick(g, prefer, classes=None):
        order = [prefer, "R" if prefer == "P" else "P"]
        for strict in (True, False):
            for t in order:
                cs = [x for x in pool if ok(x, g, {t}, strict, classes)]
                if cs:
                    return _wchoice(rng, cs, [PRIO_W.get(x.get("prio") or 0, 1) if t == "P" else 1 for x in cs])
        return None

    accent = accent_for(n, skipped)
    slots = [(g, False) for g in BASE_GROUPS if g not in skipped]
    if accent and dur_min >= 30:
        slots += [(g, True) for g in ACC_GROUPS[accent] if g not in skipped]
    chosen = []
    for g, acc in slots:
        x = pick(g, "R" if acc else ("P" if rng.random() < P_SHARE else "R"))
        if x:
            used.add(x["key"]); chosen.append(dict(x, accent=acc))
    # maks. 2 klasy ciezaru (C/S/L); trzecia -> wymiana na cwiczenie z klasy istniejacego bloku
    for _ in range(6):
        cnt = Counter(x["wclass"] for x in chosen if x["wclass"] != "0")
        if len(cnt) <= 2:
            break
        keep = [c for c, _ in sorted(cnt.items(), key=lambda kv: (-kv[1], CLS_ORDER.index(kv[0])))[:2]]
        drop = [c for c in cnt if c not in keep][0]
        changed = False
        for i, x in enumerate(chosen):
            if x["wclass"] != drop:
                continue
            used.discard(x["key"])
            y = pick(x["grp"], x["tier"] if x["tier"] in ("P", "R") else "P", classes=set(keep) | {"0"})
            if y:
                used.add(y["key"]); chosen[i] = dict(y, accent=x["accent"]); changed = True
            else:
                used.add(x["key"])
        if not changed:
            break
    return {"accent": accent, "skip": skip, "chosen": chosen}


def _interleave(items: list) -> list:
    lo = [x for x in items if x["grp"] in LOWER]
    up = [x for x in items if x["grp"] not in LOWER]
    a, b = (lo, up) if len(lo) >= len(up) else (up, lo)
    out = []
    for i in range(max(len(a), len(b))):
        if i < len(a): out.append(a[i])
        if i < len(b): out.append(b[i])
    return out


def build_blocks(chosen: list, weights: dict | None = None) -> list:
    """[{wclass, kg, items}] - bloki z ciezarem C->S->L, bez hantli rozdzielone, brzuch na koniec."""
    weights = weights or {}
    blocks = []
    for c in CLS_ORDER:
        items = [x for x in chosen if x["wclass"] == c]
        if items:
            kgs = [weights[x["key"]] for x in items if weights.get(x["key"])]
            kg = round(sum(kgs) / len(kgs)) if kgs else DEF_KG[c]
            blocks.append({"wclass": c, "kg": kg, "items": items})
    free = [x for x in chosen if x["wclass"] == "0" and x["grp"] != "core"]
    core = [x for x in chosen if x["wclass"] == "0" and x["grp"] == "core"]
    for x in free:
        if blocks:
            min(blocks, key=lambda b: len(b["items"]))["items"].append(x)
        else:
            core.insert(0, x)
    for b in blocks:
        b["items"] = _interleave(b["items"])
    if core:
        blocks.append({"wclass": "0", "kg": 0, "items": core})
    return blocks


def render(choice: dict, blocks: list, warmup: list, phase: str | None, cut: bool) -> dict:
    phase = phase if phase in TW.DOSE else "bz"
    rounds, work, rest, note = TW.DOSE[phase]
    if cut:
        rounds, note = 1, "wersja minimum: jedna runda każdego bloku, łatwiejsze ćwiczenia"
    acc, skip = choice["accent"], choice["skip"]
    timed = "s pracy" in work   # okres na czas (np. rt: 40 s pracy) -> przy cwiczeniu czas zamiast powtorzen
    t_work = work.split(" pracy")[0] if timed else None
    letters = "ABCDE"
    ex, lines = [], []
    bez = (" (bez: " + ", ".join(skip) + ")") if skip else ""
    lines.append(f"Siła w blokach{bez} · akcent: {acc or '—'} · {rounds} × każdy blok · {work} · przerwa między rundami {rest}")
    if warmup:
        lines.append("Rozgrzewka 5′: " + " · ".join(f"{w['name']} {w.get('dose') or ''}".strip() for w in warmup) + ".")
    num, prev_kg = 0, None
    out_blocks = []
    for bi, b in enumerate(blocks):
        L = letters[bi] if bi < len(letters) else str(bi + 1)
        if b["wclass"] == "0":
            head = f"BLOK {L} · bez hantli"
        else:
            if prev_kg is not None and prev_kg != b["kg"]:
                lines.append(f"↔ Zmiana obciążenia: {prev_kg} → {b['kg']} kg")
            head = f"BLOK {L} · hantle ok. {b['kg']} kg ({CLS_TXT[b['wclass']]})"
            prev_kg = b["kg"]
        idx = []
        lines.append(head)
        for x in b["items"]:
            num += 1
            dose = x.get("dose") or ""
            if timed and not dose.rstrip().endswith("s") and " s " not in dose and "s /" not in dose:
                dose = t_work + (" (na stronę)" if "stron" in dose or "nog" in dose else "")
            e = {"n": num, "key": x["key"], "name": x["name"], "group": GLABEL.get(x["grp"], x["grp"]), "dose": dose,
                 "tier": x.get("tier"), "accent": bool(x.get("accent")), "wclass": x["wclass"], "block": L,
                 "img": f"/cwiczenia/{x['key']}_m.webp", "img_full": f"/cwiczenia/{x['key']}.webp", "swapped": False}
            ex.append(e); idx.append(num)
            lines.append(f"{num}. {x['name']} — {dose} ({e['group']}){' ➕' if e['accent'] else ''}")
        out_blocks.append({"letter": L, "wclass": b["wclass"], "kg": b["kg"], "head": head, "items": idx})
    if skip:
        lines.append("Pominięte na Twoją prośbę: " + ", ".join(skip) + ".")
    lines.append(f"Uwaga: {note}. Ciężar tak, żeby zostały 2–3 powtórzenia w zapasie; ból stawu = przerwij ćwiczenie.")
    return {"title": f"Siła w blokach{bez} — akcent {acc or 'brak'}", "accent": acc, "rounds": rounds, "exercises": ex,
            "blocks": out_blocks, "warmup": warmup, "skip": skip, "engine": VERSION, "text": "\n".join(lines)}


# ---------------- baza danych ----------------
def load_pool(c, user: str) -> tuple[list, dict]:
    import qbot_trener_exercises as X
    rows = X.list_db(c, user)
    c.execute("SELECT key, weight_kg FROM qbot_v2.trainer_exercise_user WHERE username=%s AND weight_kg IS NOT NULL", (user,))
    w = {r["key"]: float(r["weight_kg"]) for r in c.fetchall()}
    pool = [{"key": r["key"], "name": r["name"], "grp": r["grp"], "level": r["level"], "wclass": r["wclass"], "tier": r["tier"],
             "prio": r["prio"], "img": bool(r.get("img")), "dose": r.get("dose"), "warmup": r.get("warmup")} for r in rows]
    return pool, w


def warmup_for(pool: list, skipped: set, seed: str) -> list:
    rng = random.Random(int(hashlib.sha1(("wu" + seed).encode()).hexdigest()[:12], 16))
    wu = [x for x in pool if x["grp"] == "rozgrzewka" and x["tier"] != "X" and x.get("img")]
    if "nogi" in skipped:
        wu = [x for x in wu if x["key"] not in ("bodyweight_squat", "leg_swings", "hip_flexor_stretch")]
    base = [x for x in wu if x["tier"] == "P"]
    rot = [x for x in wu if x["tier"] == "R"]
    out = base[:4] + ([rng.choice(rot)] if rot and len(base) < 5 else [])
    return [{"key": x["key"], "name": x["name"], "dose": x.get("dose")} for x in out]


def _sig(s: dict, phase, skip: list) -> str:
    return f"{VERSION}|{phase}|{s['dur_min']}|{int(bool(s.get('cut')))}|{','.join(skip)}"


def workout_for(c, user: str, s: dict, phase, prefs: dict | None = None) -> dict | None:
    """Szczegoly sesji silowej z bazy. Zapisany zestaw -> ten sam; nowy podpis (przyszla sesja w planie) -> losuj i zapisz.
    Sesja miniona bez zapisu -> None (wywolujacy pokaze stary zestaw)."""
    opts = s.get("opts") if isinstance(s.get("opts"), dict) else {}
    skip = TW.clean_skip((opts or {}).get("skip_groups"))
    day = s["day"] if isinstance(s["day"], date) else date.fromisoformat(str(s["day"])[:10])
    sig = _sig(s, phase, skip)
    c.execute("SELECT sig, data FROM qbot_v2.trainer_workout WHERE username=%s AND day=%s AND sport='sila'", (user, day))
    row = c.fetchone()
    data = row["data"] if row else None
    if isinstance(data, str):
        data = json.loads(data)
    future_plan = s.get("status") == "plan" and day >= date.today()
    if row and (row["sig"] == sig or not future_plan):
        return data
    if not future_plan:
        return None
    pool, weights = load_pool(c, user)
    c.execute("SELECT data FROM qbot_v2.trainer_workout WHERE username=%s AND sport='sila' AND day < %s ORDER BY day DESC LIMIT 3", (user, day))
    hist = []
    for r in c.fetchall():
        d = r["data"] if not isinstance(r["data"], str) else json.loads(r["data"])
        hist.append([e["key"] for e in (d or {}).get("exercises", [])])
    if prefs is None:
        import qbot_trener_ratings as TR
        prefs = TR.exercise_prefs(c, user)
    names_bad = {k for k, v in (prefs or {}).items() if v <= TW.BAD_AVG}
    bad = {x["key"] for x in pool if x["name"] in names_bad}
    n = TW.strength_index(c, user, s)
    seed = f"{user}|{day.isoformat()}|{sig}"
    ch = choose(pool, hist, n=n, phase=phase, cut=bool(s.get("cut")), dur_min=s["dur_min"], skip=skip, bad=bad, seed=seed)
    skipped = set().union(*[SKIP_MAP.get(g, set()) for g in skip]) if skip else set()
    wu = warmup_for(pool, skipped, seed)
    out = render(ch, build_blocks(ch["chosen"], weights), wu, phase, bool(s.get("cut")))
    out["_src"] = {"chosen": ch["chosen"], "accent": ch["accent"], "skip": ch["skip"], "warmup": wu, "phase": phase, "cut": bool(s.get("cut"))}
    c.execute("INSERT INTO qbot_v2.trainer_workout (username, day, sport, sig, data) VALUES (%s,%s,'sila',%s,%s::jsonb) "
              "ON CONFLICT (username, day, sport) DO UPDATE SET sig=EXCLUDED.sig, data=EXCLUDED.data, updated_at=now()",
              (user, day, sig, json.dumps(out, ensure_ascii=False)))
    return out
