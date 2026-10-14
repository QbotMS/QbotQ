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
- ZMIANY UZYTKOWNIKA (2026-10-09, modify): 'Inny zestaw' (reroll) = nowe losowanie calosci (licznik w ziarnie),
  'Zamien' (swap) = wymiana wskazanych cwiczen na inne z tej samej partii (reszta zostaje) + zakaz ich w tej sesji.
  Stan w data['_mod'] = {ban: [klucze], reroll: N}; przezywa zmiane podpisu (np. czasu). Cwiczenie oznaczone pozniej
  'Pomijaj' (X) albo bez grafiki znika z zapisanych PRZYSZLYCH zestawow samo (wymiana przy najblizszym odczycie).
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
# 2026-10-09: RODZINY = odmiany tego samego ruchu; w jednym treningu najwyzej jedna z rodziny (np. jedna deska).
_FAM_SRC = {
    "deska": "plank_forearm plank_shoulder_tap side_plank side_plank_hip_dip copenhagen_plank_short bear_hold",
    "dead_bug": "dead_bug dead_bug_db",
    "unoszenie_nog": "lying_leg_raise_bench reverse_crunch hollow_hold",
    "pompki": "pushup pushup_feet_elevated pushup_incline pushup_knees pushup_wide diamond_pushup pike_pushup",
    "wyciskanie_lezac": "bench_press_db bench_press_neutral_db floor_press_db",
    "wyciskanie_nad_glowe": "shoulder_press_seated_db shoulder_press_standing_db arnold_press_db",
    "wioslowanie": "row_one_arm_db row_one_arm_pause_db bent_over_row_db chest_supported_row_db renegade_row_db",
    "wioslowanie_guma": "band_row_one_arm band_row_seated",
    "przysiad": "goblet_squat_db goblet_squat_pause_db heel_elevated_squat_db band_squat",
    "wykrok": "split_squat_db bulgarian_split_squat_db reverse_lunge_db walking_lunge_db lateral_lunge_db",
    "martwy_ciag": "rdl_db kickstand_rdl_db single_leg_rdl_db sumo_deadlift_db good_morning_db",
    "most": "hip_thrust_db glute_bridge_db single_leg_glute_bridge single_leg_hip_thrust glute_bridge_march",
    "lydki": "calf_raise_db single_leg_calf_raise",
    "unoszenie_ramion": "lateral_raise_db front_raise_db",
    "tyl_barku": "reverse_fly_db prone_t_raise_db band_pull_apart",
    "uginanie": "bicep_curl_db hammer_curl_db band_curl",
    "triceps": "skull_crusher_db overhead_triceps_ext_db triceps_kickback_db bench_dips",
    "spacer": "farmer_carry_db suitcase_carry_db",
}
FAMILY = {k: f for f, ks in _FAM_SRC.items() for k in ks.split()}


def fam(key: str) -> str:
    return FAMILY.get(key, key)


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


# ---- UKLAD 3 RUND (2026-10-09, decyzja Michala) ----
# H = ciezkie hantle (klasa C, zapas S), L = lzejsze hantle (klasa L, zapas S), B = bez hantli; kazda runda 2-3 cwiczenia.
# Liczba cwiczen (i w ostatecznosci rund) tak, zeby trening zmiescil sie w zalozonym czasie (est_minutes).
BLOCK_ORDER = {"H": ["plecy", "klatka", "nogi", "tyl", "barki"],
               "L": ["barki", "ramiona", "plecy", "klatka", "tyl", "nogi"],
               "B": ["core", "plecy", "tyl", "nogi", "barki", "klatka", "ramiona"]}
HOME = {"plecy": "HLB", "klatka": "HBL", "nogi": "HB", "tyl": "BH", "barki": "LBH", "ramiona": "LB", "core": "B"}
# kolejnosc pokrycia partii = waznosc (przy braku czasu wypada najpierw koniec listy)
COVER_PRIO = ["plecy", "klatka", "nogi", "tyl", "core", "barki", "ramiona"]
ACC_HOME = {"klatka + ramiona": [("klatka", "H"), ("ramiona", "L")], "plecy": [("plecy", "H"), ("plecy", "L")],
            "nogi": [("nogi", "H"), ("tyl", "B")], "brzuch": [("core", "B"), ("core", "B")]}
PER_BLOCK = (2, 3)
WARMUP_MIN, SWITCH_MIN = 5, 1


def _rest_min(phase) -> float:
    import re
    txt = TW.DOSE.get(phase if phase in TW.DOSE else "bz")[2]
    nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:,\d+)?", txt)]
    return (sum(nums) / len(nums)) if nums else 1.0


def ex_minutes(x: dict) -> float:
    """Czas jednej serii z przejsciem: ~1 min; na strone / na noge ~1,5 min."""
    d = str(x.get("dose") or "")
    return 1.5 if ("stron" in d or "nog" in d) else 1.0


def est_minutes(blocks: list, rounds: int, phase) -> float:
    """blocks: [[cwiczenia bloku], ...]. Rozgrzewka + rundy x serie + przerwy miedzy rundami + zmiany ciezaru."""
    rest = _rest_min(phase)
    t = WARMUP_MIN + max(0, len(blocks) - 1) * SWITCH_MIN
    for b in blocks:
        t += rounds * sum(ex_minutes(x) for x in b) + max(0, rounds - 1) * rest
    return round(t, 1)


def choose(pool: list, hist: list, *, n: int, phase: str | None, cut: bool, dur_min: int, skip: list | None,
           bad: set | None = None, seed: str = "") -> dict:
    """Uklad 3 rund: H (ciezkie) -> L (lzejsze) -> B (bez hantli), po 2-3 cwiczenia, dopasowany do dur_min.
    pool: [{key,name,grp,level,wclass,tier,prio,img,dose}], hist: [[keys] ostatnich treningow, najnowszy pierwszy]."""
    rng = random.Random(int(hashlib.sha1(seed.encode()).hexdigest()[:12], 16))
    skip = TW.clean_skip(skip)
    skipped = set().union(*[SKIP_MAP.get(g, set()) for g in skip]) if skip else set()
    maxlvl = 1 if cut else (3 if phase in ("bz", "bd") else 2)
    last = set(hist[0]) if hist else set()
    recent = set(k for h in hist[:3] for k in h)
    bad = bad or set()
    used: set = set()
    groups = [g for g in BASE_GROUPS if g not in skipped]

    def ok(x, g, cls, strict, famrule):
        if x["grp"] != g or not x.get("img") or x["tier"] == "X" or x["key"] in used or x["key"] in bad:
            return False
        if x["wclass"] != cls or x["level"] > maxlvl or (g == "core" and x["wclass"] != "0"):
            return False
        if famrule and fam(x["key"]) in {fam(k) for k in used}:
            return False
        if strict and (x["key"] in last or (x["tier"] == "R" and x["key"] in recent)):
            return False
        return True

    def pick(g, cls, prefer):
        order = [prefer, "R" if prefer == "P" else "P"]
        for famrule in (True, False):
            for strict in (True, False):
                for t in order:
                    cs = [x for x in pool if x["tier"] == t and ok(x, g, cls, strict, famrule)]
                    if cs:
                        return _wchoice(rng, cs, [PRIO_W.get(x.get("prio") or 0, 1) if t == "P" else 1 for x in cs])
        return None

    def avail(cls):
        return len({x["key"] for g in groups for x in pool if ok(x, g, cls, False, False)})

    # klasy rund: H = C (zapas S), L = L (zapas S, ale inna niz H), B = bez hantli
    cls = {"H": "C" if avail("C") >= 2 else ("S" if avail("S") >= 2 else None)}
    cls["L"] = "L" if avail("L") >= 2 else ("S" if cls["H"] != "S" and avail("S") >= 2 else None)
    cls["B"] = "0"
    blocks = {b: [] for b in "HLB"}
    covered: set = set()

    def add(b, g, prefer, acc, stage):
        if cls.get(b) is None or len(blocks[b]) >= PER_BLOCK[1] or g in skipped:
            return False
        x = pick(g, cls[b], prefer)
        if not x:
            return False
        used.add(x["key"]); covered.add(g)
        blocks[b].append(dict(x, accent=acc, _stage=stage))
        return True

    accent = accent_for(n, skipped)
    if accent and dur_min >= 30:                           # 1) akcent dnia (najpierw rotacyjne)
        for g, home in ACC_HOME[accent]:
            if g in skipped:
                continue
            for b in home + "".join(h for h in "HLB" if h != home):
                if (g == "core" and b != "B") or not add(b, g, "R", True, 0):
                    continue
                break
    for pi, g in enumerate([g for g in COVER_PRIO if g in groups]):   # 2) kazda partia co najmniej raz (wg waznosci)
        if g in covered:
            continue
        for b in HOME[g]:
            if add(b, g, "P" if rng.random() < P_SHARE else "R", False, 1 + pi / 10):
                break
    for b in "HLB":                                        # 3) dopelnienie rund do 3 cwiczen
        cnt_g = Counter(x["grp"] for bb in "HLB" for x in blocks[bb])
        for g in sorted(BLOCK_ORDER[b], key=lambda g: cnt_g[g]):   # najpierw partie najrzadsze (rownowaga pchanie / ciagniecie)
            if len(blocks[b]) >= PER_BLOCK[1]:
                break
            if g in skipped or any(x["grp"] == g for x in blocks[b]):
                continue
            add(b, g, "P" if rng.random() < P_SHARE else "R", False, 2)
    for b in "HLB":                                        # runda z 1 cwiczeniem -> dobierz drugie albo runda wypada
        if len(blocks[b]) == 1:
            for g in BLOCK_ORDER[b]:
                if add(b, g, "P", False, 2):
                    break
        if len(blocks[b]) == 1:
            used.discard(blocks[b][0]["key"]); blocks[b] = []

    # 4) dopasowanie do czasu: najpierw zbedne cwiczenia (dopelnienie, potem pokrycie partii), potem rundy
    rounds = 1 if cut else TW.DOSE.get(phase if phase in TW.DOSE else "bz")[0]
    lst = lambda: [blocks[b] for b in "HLB" if blocks[b]]
    while est_minutes(lst(), rounds, phase) > dur_min:
        cand = [(x["_stage"], len(blocks[b]), b, i) for b in "HLB" for i, x in enumerate(blocks[b])
                if len(blocks[b]) > PER_BLOCK[0] and x["_stage"] > 0]
        if cand:
            _st, _ln, b, i = max(cand)
            used.discard(blocks[b][i]["key"]); blocks[b].pop(i)
        elif rounds > 1:
            rounds -= 1
        else:
            break
    if not cut:   # zapas czasu przy pelnych rundach -> 1 runda wiecej (maks. 4)
        while rounds < 4 and est_minutes(lst(), rounds + 1, phase) <= dur_min and all(len(b) >= 3 for b in lst()):
            rounds += 1
    chosen = [{k: v for k, v in x.items() if k != "_stage"} for b in "HLB" for x in blocks[b]]
    return {"accent": accent, "skip": skip, "chosen": chosen, "rounds": rounds,
            "est_min": est_minutes(lst(), rounds, phase)}


def fix_lone(pool: list, chosen: list, *, ban=frozenset(), last=frozenset(), maxlvl: int = 3, seed: str = "") -> tuple:
    """Kazda klasa ciezaru (C/S/L i bez hantli '0') ma 0 albo >= 2 cwiczenia - bo klasa = blok. Samotne cwiczenie
    z hantlami -> ta sama partia w klasie innego bloku (albo bez hantli); gdy sie nie da -> inne cwiczenie z liczniejszego
    bloku przechodzi do jego klasy. Samotne bez hantli -> cwiczenie z liczniejszego bloku z hantlami zamieniane na wersje
    bez hantli (ta sama partia). Nie tworzy 3. klasy z hantlami. Zwraca (chosen, [(stara, nowa, klucz_nowej)])."""
    rng = random.Random(int(hashlib.sha1(("lone" + seed).encode()).hexdigest()[:12], 16))
    chosen, changed = list(chosen), []

    def swap(i, classes):
        x = chosen[i]
        used = {y["key"] for y in chosen}
        fams_ = {fam(y["key"]) for j, y in enumerate(chosen) if j != i}
        for strict in (True, False):
            cs = [p for p in pool if p["grp"] == x["grp"] and p.get("img") and p["tier"] != "X" and p["key"] not in used
                  and p["key"] not in ban and p["level"] <= maxlvl and (x["grp"] != "core" or p["wclass"] == "0")
                  and p["wclass"] in classes and fam(p["key"]) not in fams_ and (not strict or p["key"] not in last)]
            if cs:
                y = _wchoice(rng, cs, [PRIO_W.get(p.get("prio") or 0, 1) if p["tier"] == "P" else 1 for p in cs])
                chosen[i] = dict(y, accent=bool(x.get("accent")))
                changed.append((x["name"], y["name"], y["key"]))
                return True
        return False

    for _ in range(6):
        cnt = Counter(x["wclass"] for x in chosen)
        lone = [c for c, v in cnt.items() if v == 1]
        if not lone or len(cnt) < 2:
            break
        c1, done = lone[0], False
        if c1 != "0":
            i = next(j for j, x in enumerate(chosen) if x["wclass"] == c1)
            done = swap(i, set(cnt) - {c1})
            if not done:
                for j, y in enumerate(chosen):
                    if y["wclass"] != c1 and cnt[y["wclass"]] >= 3 and swap(j, {c1}):
                        done = True; break
        else:
            for j, y in enumerate(chosen):
                if y["wclass"] != "0" and cnt[y["wclass"]] >= 3 and swap(j, {"0"}):
                    done = True; break
            if not done:
                i = next(j for j, x in enumerate(chosen) if x["wclass"] == "0")
                if chosen[i]["grp"] != "core":
                    done = swap(i, set(cnt) - {"0"})
        if not done:
            break
    return chosen, changed


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
    """[{wclass, kg, items}] - bloki z ciezarem C->S->L, na koncu blok bez hantli."""
    weights = weights or {}
    blocks = []
    for c in CLS_ORDER:
        items = [x for x in chosen if x["wclass"] == c]
        if items:
            kgs = [weights[x["key"]] for x in items if weights.get(x["key"])]
            kg = round(sum(kgs) / len(kgs)) if kgs else DEF_KG[c]
            blocks.append({"wclass": c, "kg": kg, "items": items})
    # 2026-10-09 (decyzja uzytkownika): cwiczenia BEZ HANTLI nigdy w bloku z hantlami - wszystkie w bloku bez hantli
    # na koncu (inne partie przed brzuchem). Liczebnosc blokow pilnuje fix_lone (zaden blok z 1 cwiczeniem).
    free = [x for x in chosen if x["wclass"] == "0" and x["grp"] != "core"]
    core = [x for x in chosen if x["wclass"] == "0" and x["grp"] == "core"]
    for b in blocks:
        b["items"] = _spread(_interleave(b["items"]))
    if free or core:
        blocks.append({"wclass": "0", "kg": 0, "items": _spread(free + core)})
    return blocks


def _spread(items: list) -> list:
    """Ta sama partia nie stoi jedna po drugiej, gdy da sie to rozdzielic (zachlannie, stabilnie)."""
    rest, out = list(items), []
    while rest:
        prev = out[-1]["grp"] if out else None
        cnt = Counter(x["grp"] for x in rest)
        cand = [k for k, x in enumerate(rest) if x["grp"] != prev] or [0]
        j = min(cand, key=lambda k: (-cnt[rest[k]["grp"]], k))   # najpierw partia z najwieksza reszta
        out.append(rest.pop(j))
    return out


def render(choice: dict, blocks: list, warmup: list, phase: str | None, cut: bool) -> dict:
    phase = phase if phase in TW.DOSE else "bz"
    rounds, work, rest, note = TW.DOSE[phase]
    if choice.get("rounds"):   # 2026-10-09: rundy z ukladu dopasowanego do czasu
        rounds = int(choice["rounds"])
    if cut:
        rounds, note = 1, "wersja minimum: jedna runda każdego bloku, łatwiejsze ćwiczenia"
    acc, skip = choice["accent"], choice["skip"]
    timed = "s pracy" in work   # okres na czas (np. rt: 40 s pracy) -> przy cwiczeniu czas zamiast powtorzen
    t_work = work.split(" pracy")[0] if timed else None
    letters = "ABCDE"
    ex, lines = [], []
    bez = (" (bez: " + ", ".join(skip) + ")") if skip else ""
    lines.append(f"Siła w blokach{bez} · akcent: {acc or '—'} · {rounds} × każdy blok · {work} · przerwa między rundami {rest}"
                 + (f" · razem ok. {round(choice['est_min'])} min" if choice.get("est_min") else ""))
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
    mod = ((data or {}).get("_mod") or {}) if row else {}
    if row and (row["sig"] == sig or not future_plan):
        if future_plan and data and "_src" in data:
            data = _fix_excluded(c, user, day, row["sig"], data)
        return data
    if not future_plan:
        return None
    return _draw(c, user, s, phase, prefs, sig, mod)


def _hist(c, user: str, day: date) -> list:
    c.execute("SELECT data FROM qbot_v2.trainer_workout WHERE username=%s AND sport='sila' AND day < %s ORDER BY day DESC LIMIT 3", (user, day))
    hist = []
    for r in c.fetchall():
        d = r["data"] if not isinstance(r["data"], str) else json.loads(r["data"])
        hist.append([e["key"] for e in (d or {}).get("exercises", [])])
    return hist


def _save(c, user: str, day: date, sig: str, out: dict) -> None:
    c.execute("INSERT INTO qbot_v2.trainer_workout (username, day, sport, sig, data) VALUES (%s,%s,'sila',%s,%s::jsonb) "
              "ON CONFLICT (username, day, sport) DO UPDATE SET sig=EXCLUDED.sig, data=EXCLUDED.data, updated_at=now()",
              (user, day, sig, json.dumps(out, ensure_ascii=False)))


def _draw(c, user: str, s: dict, phase, prefs, sig: str, mod: dict, avoid: list | None = None) -> dict:
    """Pelne losowanie zestawu (ziarno + licznik 'Inny zestaw'; zakazane w tej sesji = mod.ban)."""
    opts = s.get("opts") if isinstance(s.get("opts"), dict) else {}
    skip = TW.clean_skip((opts or {}).get("skip_groups"))
    day = s["day"] if isinstance(s["day"], date) else date.fromisoformat(str(s["day"])[:10])
    pool, weights = load_pool(c, user)
    hist = _hist(c, user, day)
    if avoid:   # 'Inny zestaw': obecny zestaw traktowany jak poprzedni trening (unikany, gdy jest zastepstwo)
        hist = [list(avoid)] + hist
    if prefs is None:
        import qbot_trener_ratings as TR
        prefs = TR.exercise_prefs(c, user)
    names_bad = {k for k, v in (prefs or {}).items() if v <= TW.BAD_AVG}
    bad = {x["key"] for x in pool if x["name"] in names_bad} | set(mod.get("ban") or [])
    n = TW.strength_index(c, user, s)
    rr = int(mod.get("reroll") or 0)
    seed = f"{user}|{day.isoformat()}|{sig}" + (f"|r{rr}" if rr else "")
    ch = choose(pool, hist, n=n, phase=phase, cut=bool(s.get("cut")), dur_min=s["dur_min"], skip=skip, bad=bad, seed=seed)
    skipped = set().union(*[SKIP_MAP.get(g, set()) for g in skip]) if skip else set()
    wu = warmup_for(pool, skipped, seed)
    out = render(ch, build_blocks(ch["chosen"], weights), wu, phase, bool(s.get("cut")))
    out["_src"] = {"chosen": ch["chosen"], "accent": ch["accent"], "skip": ch["skip"], "warmup": wu, "phase": phase, "cut": bool(s.get("cut")),
                   "rounds": ch.get("rounds"), "est_min": ch.get("est_min")}
    if mod:
        out["_mod"] = mod
    _save(c, user, day, sig, out)
    return out


def replace_keys(pool: list, chosen: list, drop: set, ban: set, hist: list, *, phase, cut: bool, seed: str) -> tuple:
    """Wymienia cwiczenia z 'drop' na inne z tej samej partii; reszta zestawu zostaje. Kolejnosc wyboru: ta sama klasa
    ciezaru -> klasy juz w treningu (bez 3. bloku) -> dowolna; najpierw nie z poprzedniego treningu. Zwraca
    (nowy_chosen, [(stara_nazwa, nowa_nazwa)], [nazwy bez zastepstwa - wypadaja])."""
    rng = random.Random(int(hashlib.sha1(("sw" + seed).encode()).hexdigest()[:12], 16))
    maxlvl = 1 if cut else (3 if phase in ("bz", "bd") else 2)
    last = set(hist[0]) if hist else set()
    used = {x["key"] for x in chosen}
    present = {x["wclass"] for x in chosen if x["wclass"] != "0" and x["key"] not in drop}
    out, pairs, missing = [], [], []
    fams = {fam(y["key"]) for y in chosen if y["key"] not in drop}
    for x in chosen:
        if x["key"] not in drop:
            out.append(x)
            continue
        g = x["grp"]

        def cands(strict, cls, famrule=True):
            return [p for p in pool if p["grp"] == g and p.get("img") and p["tier"] != "X" and p["key"] not in used
                    and p["key"] not in ban and p["key"] not in drop and p["level"] <= maxlvl
                    and (g != "core" or p["wclass"] == "0") and (cls is None or p["wclass"] in cls)
                    and (not strict or p["key"] not in last) and (not famrule or fam(p["key"]) not in fams)]
        cs = []
        for famrule in (True, False):
            for cls in ({x["wclass"]}, present | {"0"}, None):
                for strict in (True, False):
                    cs = cands(strict, cls, famrule)
                    if cs:
                        break
                if cs:
                    break
            if cs:
                break
        if not cs:
            missing.append(x["name"])
            continue
        y = _wchoice(rng, cs, [PRIO_W.get(p.get("prio") or 0, 1) if p["tier"] == "P" else 1 for p in cs])
        used.add(y["key"]); fams.add(fam(y["key"]))
        if y["wclass"] != "0":
            present.add(y["wclass"])
        out.append(dict(y, accent=bool(x.get("accent"))))
        pairs.append((x["name"], y["name"]))
    return out, pairs, missing


def _rebuild(c, user: str, day: date, sig: str, data: dict, chosen: list, mod: dict, new_keys: set) -> dict:
    src = data["_src"]
    pool, _w0 = load_pool(c, user)
    hist = _hist(c, user, day)
    chosen, fx = fix_lone(pool, chosen, ban=set(mod.get("ban") or []), last=set(hist[0]) if hist else set(),
                          maxlvl=1 if src["cut"] else (3 if src["phase"] in ("bz", "bd") else 2), seed=f"{user}|{str(day)[:10]}|fix")
    new_keys = set(new_keys) | {k for _a, _b, k in fx}
    c.execute("SELECT key, weight_kg FROM qbot_v2.trainer_exercise_user WHERE username=%s AND weight_kg IS NOT NULL", (user,))
    w = {r["key"]: float(r["weight_kg"]) for r in c.fetchall()}
    ch = {"accent": src["accent"], "skip": src["skip"], "chosen": chosen, "rounds": src.get("rounds"), "est_min": src.get("est_min")}
    out = render(ch, build_blocks(chosen, w), src["warmup"], src["phase"], src["cut"])
    for e in out["exercises"]:
        e["swapped"] = e["key"] in new_keys
    out["_src"] = dict(src, chosen=chosen)
    if mod:
        out["_mod"] = mod
    _save(c, user, day, sig, out)
    return out


def _fix_excluded(c, user: str, day: date, sig: str, data: dict) -> dict:
    """Zapisany przyszly zestaw zawiera cwiczenie, ktore teraz jest 'Pomijaj' / bez grafiki -> wymien tylko je."""
    pool, _w = load_pool(c, user)
    by = {x["key"]: x for x in pool}
    chosen = data["_src"]["chosen"]
    drop = {x["key"] for x in chosen if x["key"] not in by or by[x["key"]]["tier"] == "X" or not by[x["key"]].get("img")}
    if not drop:
        return data
    mod = dict(data.get("_mod") or {})
    new, pairs, _miss = replace_keys(pool, chosen, drop, set(mod.get("ban") or []), _hist(c, user, day),
                                     phase=data["_src"]["phase"], cut=data["_src"]["cut"], seed=f"{user}|{day.isoformat()}|fix")
    return _rebuild(c, user, day, sig, data, new, mod, {k for k in (x["key"] for x in new)} - {x["key"] for x in chosen})


class ModifyError(Exception):
    pass


def saved(c, user: str, day) -> dict | None:
    """Zapisany wiersz zestawu (do cofania zmian AI): {day, sig, data} albo None."""
    c.execute("SELECT sig, data FROM qbot_v2.trainer_workout WHERE username=%s AND day=%s AND sport='sila'", (user, day))
    r = c.fetchone()
    if not r:
        return None
    d = r["data"] if not isinstance(r["data"], str) else json.loads(r["data"])
    return {"day": str(day)[:10], "sig": r["sig"], "data": d}


def modify(c, user: str, sid: int, action: str, keys: list | None = None) -> dict:
    """Zmiana zestawu przyszlej sesji silowej przez uzytkownika.
    action='reroll' -> cale nowe losowanie; action='swap', keys=[...] -> wymiana tylko tych cwiczen."""
    c.execute("SELECT * FROM qbot_v2.trainer_session WHERE id=%s AND username=%s", (sid, user))
    s = c.fetchone()
    if not s or s["sport"] != "sila":
        raise ModifyError("nie ma takiej sesji siłowej")
    s = dict(s)
    day = s["day"] if isinstance(s["day"], date) else date.fromisoformat(str(s["day"])[:10])
    if s.get("status") != "plan" or day < date.today():
        raise ModifyError("zmieniać można tylko zaplanowany trening od dziś")
    sv = saved(c, user, day)
    data = sv["data"] if sv else None
    if not data or "_src" not in data:
        raise ModifyError("ten trening nie ma jeszcze zestawu z bazy — otwórz go raz w planie")
    mod = dict(data.get("_mod") or {})
    if action == "reroll":
        mod["reroll"] = int(mod.get("reroll") or 0) + 1
        out = _draw(c, user, s, data["_src"]["phase"], None, sv["sig"], mod,
                    avoid=[x["key"] for x in data["_src"]["chosen"]])
        old = {x["key"] for x in data["_src"]["chosen"]}
        return {"ok": True, "action": "reroll", "same": sorted(old & {e["key"] for e in out["exercises"]}),
                "text": out["text"]}
    if action == "swap":
        chosen = data["_src"]["chosen"]
        have = {x["key"] for x in chosen}
        drop = {str(k) for k in (keys or [])} & have
        if not drop:
            raise ModifyError("nie wskazano ćwiczenia z tego treningu")
        mod["ban"] = sorted(set(mod.get("ban") or []) | drop)
        pool, _w = load_pool(c, user)
        new, pairs, missing = replace_keys(pool, chosen, drop, set(mod["ban"]), _hist(c, user, day),
                                           phase=data["_src"]["phase"], cut=data["_src"]["cut"],
                                           seed=f"{user}|{day.isoformat()}|sw{len(mod['ban'])}")
        out = _rebuild(c, user, day, sv["sig"], data, new, mod, {x["key"] for x in new} - have)
        return {"ok": True, "action": "swap", "pairs": pairs, "missing": missing, "text": out["text"]}
    raise ModifyError("nieznana zmiana")


# ---------------- ocena AI zestawu (2026-10-09) ----------------
REVIEW_SYSTEM = """Jesteś trenerem siłowym. Dostajesz JEDEN trening siłowy (bloki ciężaru, ćwiczenia z partią i dawką, okres,
czas, pominięte partie, akcent dnia). Oceń krótko, prosto, po polsku, czy trening jest SPÓJNY: czy nie dubluje tego samego
ruchu (np. dwie deski, dwa wyciskania), czy ta sama partia nie idzie dwa razy z rzędu bez potrzeby, czy blok nie ma tylko
jednego ćwiczenia, czy ciało jest w miarę zrównoważone (pchanie / ciągnięcie, przód / tył) w granicach pominiętych partii,
Ćwiczenia z "akcent": true to CELOWE dodatkowe ćwiczenia na partię akcentu dnia — to nie jest dublowanie partii
(dublowaniem jest dopiero ten sam RUCH, np. dwa rodzaje pompek). Nie oceniaj akcentu, pominiętych partii, liczby rund
ani czasu treningu — wynikają z okresu sezonu i decyzji użytkownika.
Odpowiedz WYŁĄCZNIE JSON: {"ok": true|false, "werdykt": "1 zdanie", "uwagi": ["maks. 3 krótkie, konkretne"]}"""


def _review_key(data: dict) -> str:
    return "v2" + hashlib.sha1("|".join(e["key"] + str(e.get("block")) for e in data.get("exercises", [])).encode()).hexdigest()[:12]


def review(c, user: str, sid: int, llm=None) -> dict:
    """Ocena AI zapisanego zestawu sesji; wynik w data['_review'] (wazny dopoki zestaw ten sam)."""
    c.execute("SELECT * FROM qbot_v2.trainer_session WHERE id=%s AND username=%s", (sid, user))
    s = c.fetchone()
    if not s or s["sport"] != "sila":
        raise ModifyError("nie ma takiej sesji siłowej")
    sv = saved(c, user, s["day"])
    if not sv or not sv["data"]:
        raise ModifyError("brak zapisanego zestawu")
    data = sv["data"]
    rk = _review_key(data)
    old = data.get("_review") or {}
    if old.get("key") == rk:
        return old
    inp = {"okres": (data.get("_src") or {}).get("phase"), "czas_min": s["dur_min"], "rundy": data.get("rounds"),
           "akcent": data.get("accent"), "pominiete_partie": data.get("skip") or [],
           "bloki": [{"blok": b["letter"], "ciezar": ("bez hantli" if b["wclass"] == "0" else f"{b['kg']} kg"),
                      "cwiczenia": [{"nazwa": e["name"], "partia": e["group"], "dawka": e.get("dose"), "akcent": bool(e.get("accent"))}
                                    for e in data["exercises"] if e["n"] in b["items"]]} for b in data.get("blocks", [])]}
    if llm is None:
        from qgpt_client import qgpt_json as llm
    try:
        raw = llm(json.dumps(inp, ensure_ascii=False), system=REVIEW_SYSTEM, max_tokens=500)
    except Exception as e:
        return {"key": rk, "ok": None, "werdykt": f"Ocena AI niedostępna ({str(e)[:80]}).", "uwagi": []}
    raw = raw if isinstance(raw, dict) else {}
    out = {"key": rk, "ok": raw.get("ok") if isinstance(raw.get("ok"), bool) else None,
           "werdykt": str(raw.get("werdykt") or "")[:300],
           "uwagi": [str(u)[:200] for u in (raw.get("uwagi") or []) if str(u).strip()][:3]}
    data["_review"] = out
    c.execute("UPDATE qbot_v2.trainer_workout SET data=%s::jsonb WHERE username=%s AND day=%s AND sport='sila'",
              (json.dumps(data, ensure_ascii=False), user, s["day"]))
    return out
