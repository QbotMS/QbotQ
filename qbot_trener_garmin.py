#!/usr/bin/env python3
"""TRENER -> Garmin Connect: wysylka sesji silowej z planu na zegarek (trening + kalendarz).

Zrodlo: qbot_v2.trainer_workout (sport='sila') -> data.exercises/blocks/warmup/rounds/text.
Kody cwiczen: qbot_v2.trainer_exercise.garmin_kod (katalog qbot_v2.garmin_exercise).
Struktura na zegarku:
  Rozgrzewka (kroki na powtorzenia) -> dla kazdego bloku: powtorzenie N rund
  [cwiczenie X s (z ciezarem bloku) + przerwa; po ostatnim cwiczeniu przerwa miedzy rundami].
  Cwiczenia "na strone" = dwa kroki (strona 1 / strona 2).
Idempotentnie: ta sama sesja (sig) nie jest wysylana drugi raz; zmieniona -> stary trening
usuwany z Garmina, nowy wgrywany i wpisywany w kalendarz. Stan: qbot_v2.trainer_garmin_push.

CLI: .venv/bin/python3 qbot_trener_garmin.py --day RRRR-MM-DD [--user admin] [--dry-run] [--force]
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from typing import Any

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from garminconnect.workout import (  # noqa: E402
    StrengthWorkout,
    WorkoutSegment,
    create_repeat_group,
    create_strength_exercise_step,
    create_strength_rest_step,
    create_strength_timed_step,
)

APP = "/opt/qbot/app"
SPORT = "sila"


def _db():
    from fitmodel.api import _db_connect
    return _db_connect()


def _ensure_table(cur) -> None:
    cur.execute(open(f"{APP}/sql/trainer_v13.sql", encoding="utf-8").read())


def _secs(dose: str) -> int | None:
    m = re.search(r"(\d+)\s*s\b", dose or "")
    return int(m.group(1)) if m else None


def _reps(dose: str) -> int:
    nums = [int(x) for x in re.findall(r"\d+", dose or "")]
    if not nums:
        return 10
    if "+" in dose and len(nums) >= 2:
        return nums[0] + nums[1]
    return nums[0]


def _per_side(dose: str) -> bool:
    d = (dose or "").lower()
    return "stron" in d or "nog" in d.replace("ę", "e")


def _timing(text: str) -> tuple[int, int]:
    """(przerwa po cwiczeniu s, przerwa miedzy rundami s) z opisu sesji; zapas 20/60."""
    rest = 20
    rnd = 60
    m = re.search(r"/\s*(\d+)\s*s\s*przerwy", text or "")
    if m:
        rest = int(m.group(1))
    m = re.search(r"mi[eę]dzy rundami\s*(\d+)\s*(min|s)", text or "")
    if m:
        rnd = int(m.group(1)) * (60 if m.group(2) == "min" else 1)
    return rest, rnd


def _split(kod: str) -> tuple[str, str]:
    # nazwa cwiczenia moze rownac sie kategorii (PLANK/PLANK, PUSH_UP/PUSH_UP) -- wysylamy zawsze obie
    cat, ex = kod.split("/", 1)
    return cat, ex


def _desc(s: str) -> str:
    return s[:100]


def load_session(cur, user: str, day: str) -> dict[str, Any] | None:
    cur.execute(
        "SELECT data FROM qbot_v2.trainer_workout WHERE username=%s AND day=%s AND sport=%s",
        (user, day, SPORT),
    )
    r = cur.fetchone()
    return r[0] if r else None


def build(cur, data: dict[str, Any], day: str) -> tuple[dict[str, Any], list[str], str]:
    """Zwraca (dto treningu, ostrzezenia, podpis sesji)."""
    keys = [e["key"] for e in data.get("exercises", [])] + [w["key"] for w in data.get("warmup", [])]
    cur.execute("SELECT key, garmin_kod FROM qbot_v2.trainer_exercise WHERE key = ANY(%s)", (keys,))
    kod = dict(cur.fetchall())
    warn: list[str] = []
    rounds = int(data.get("rounds") or 1)
    rest, rest_round = _timing(data.get("text", ""))
    order = 0

    def nxt() -> int:
        nonlocal order
        order += 1
        return order

    steps: list[Any] = []
    # rozgrzewka: kroki na powtorzenia, typ "warmup"
    for w in data.get("warmup", []):
        k = kod.get(w["key"])
        if not k:
            warn.append(f"rozgrzewka bez kodu Garmin pominieta: {w['name']}")
            continue
        cat, ex = _split(k)
        st = create_strength_exercise_step(cat, nxt(), _reps(w.get("dose", "")), exercise_name=ex,
                                           description=_desc(f"{w['name']} · {w.get('dose', '')}"))
        st.stepType = {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1}
        steps.append(st)

    ex_by_n = {e["n"]: e for e in data.get("exercises", [])}
    for b in data.get("blocks", []):
        kg = b.get("kg") or None
        inner: list[Any] = []
        group_order = nxt()
        items = [ex_by_n[n] for n in b.get("items", []) if n in ex_by_n]
        for i, e in enumerate(items):
            k = kod.get(e["key"])
            if not k:
                raise RuntimeError(f"cwiczenie bez kodu Garmin w planie: {e['name']} ({e['key']})")
            cat, ex = _split(k)
            dose = e.get("dose", "")
            secs = _secs(dose)
            sides = 2 if _per_side(dose) else 1
            for s in range(sides):
                label = e["name"] + (f" · strona {s + 1}" if sides == 2 else "")
                if secs:
                    st = create_strength_timed_step(cat, nxt(), secs, exercise_name=ex, weight_kg=kg,
                                                    description=_desc(label))
                else:
                    st = create_strength_exercise_step(cat, nxt(), _reps(dose), exercise_name=ex, weight_kg=kg,
                                                       description=_desc(label))
                inner.append(st)
            last = i == len(items) - 1
            inner.append(create_strength_rest_step(rest_round if last else rest, nxt()))
        g = create_repeat_group(rounds, inner, group_order)
        steps.append(g)

    title = data.get("title") or "Siła"
    dd = f"{day[8:10]}.{day[5:7]}"
    name = f"QBot {dd} · {title}"[:80]
    est = int(float((data.get("_src") or {}).get("est_min") or 30) * 60)
    wk = StrengthWorkout(
        workoutName=name,
        estimatedDurationInSecs=est,
        workoutSegments=[WorkoutSegment(segmentOrder=1, sportType={"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5},
                                        workoutSteps=steps)],
        description=_desc("Plan z QBot Trener. " + (data.get("accent") and f"Akcent: {data['accent']}." or "")),
    )
    dto = wk.to_dict()
    sig = hashlib.sha1(json.dumps(dto, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    return dto, warn, sig


def push(user: str, day: str, dry: bool = False, force: bool = False) -> dict[str, Any]:
    con = _db()
    try:
        cur = con.cursor()
        _ensure_table(cur)
        con.commit()
        data = load_session(cur, user, day)
        if not data:
            return {"status": "brak", "info": f"brak sesji silowej {day}"}
        dto, warn, sig = build(cur, data, day)
        cur.execute("SELECT workout_id, sig, status FROM qbot_v2.trainer_garmin_push WHERE username=%s AND day=%s AND sport=%s",
                    (user, day, SPORT))
        prev = cur.fetchone()
        if dry:
            return {"status": "dry", "sig": sig, "warn": warn, "prev": prev, "dto": dto}
        if prev and prev[1] == sig and prev[2] == "ok" and not force:
            return {"status": "bez zmian", "workout_id": prev[0]}
        from garmin_auth import garmin_client
        g = garmin_client()
        if prev and prev[0]:
            try:
                g.delete_workout(prev[0])
            except Exception as exc:  # stary mogl zostac usuniety recznie
                warn.append(f"nie usunieto starego treningu {prev[0]}: {exc}")
        res = g.upload_workout(dto)
        wid = str((res or {}).get("workoutId") or "")
        if not wid:
            raise RuntimeError(f"Garmin nie zwrocil workoutId: {str(res)[:200]}")
        g.schedule_workout(wid, day)
        cur.execute(
            """INSERT INTO qbot_v2.trainer_garmin_push (username, day, sport, workout_id, sig, status, info, pushed_at)
               VALUES (%s,%s,%s,%s,%s,'ok',%s, now())
               ON CONFLICT (username, day, sport) DO UPDATE SET workout_id=EXCLUDED.workout_id, sig=EXCLUDED.sig,
                 status='ok', info=EXCLUDED.info, pushed_at=now()""",
            (user, day, SPORT, wid, sig, "; ".join(warn) or None),
        )
        con.commit()
        return {"status": "ok", "workout_id": wid, "warn": warn, "name": dto["workoutName"]}
    finally:
        con.close()


if __name__ == "__main__":
    a = sys.argv
    day = a[a.index("--day") + 1]
    user = a[a.index("--user") + 1] if "--user" in a else "admin"
    out = push(user, day, dry="--dry-run" in a, force="--force" in a)
    if out.get("dto") is not None:
        d = out.pop("dto")
        print(json.dumps(out, ensure_ascii=False, default=str))
        print(json.dumps(d, ensure_ascii=False)[:6000])
    else:
        print(json.dumps(out, ensure_ascii=False, default=str))
