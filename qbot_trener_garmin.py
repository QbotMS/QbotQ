"""TRENER - Etap 5: wysylka sesji planu do Garmin Connect (trening + wpis w kalendarzu Garmina na dzien sesji).

Uzywa istniejacej autoryzacji (garmin_auth.garmin_client) i audytu/idempotencji z qbot_garmin_workouts
(tabela garmin_workout_write_audit). Klucz idempotencji zalezy od tresci sesji (dzien, sport, czas, strefa),
wiec zmieniona sesja wysyla sie jako nowy trening, a ta sama - nie dubluje sie.
Rower: rozgrzewka 10' / blok glowny z zakresem mocy (W) ze strefy i FTP / schlodzenie 5'. Pozostale: jeden blok czasowy.
"""
from __future__ import annotations

import hashlib
from typing import Any

SPORT = {
    "rower": {"sportTypeId": 2, "sportTypeKey": "cycling", "displayOrder": 2},
    "sila": {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5},
    "joga": {"sportTypeId": 7, "sportTypeKey": "yoga", "displayOrder": 8},
    "wiosl": {"sportTypeId": 3, "sportTypeKey": "other", "displayOrder": 3},
}
ZONE_PCT = {1: (0.45, 0.55), 2: (0.56, 0.75), 3: (0.76, 0.90), 4: (0.91, 1.05)}
_TIME = {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True}
_NO_T = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
_PWR_T = {"workoutTargetTypeId": 2, "workoutTargetTypeKey": "power.zone", "displayOrder": 2}
_STEP = {"warmup": {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1},
         "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2},
         "interval": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3}}


def _step(order: int, kind: str, secs: int, target: dict | None = None, lo: float | None = None, hi: float | None = None, desc: str | None = None) -> dict:
    s = {"type": "ExecutableStepDTO", "stepOrder": order, "stepType": dict(_STEP[kind]), "endCondition": dict(_TIME),
         "endConditionValue": float(secs), "targetType": dict(target or _NO_T)}
    if lo is not None and hi is not None:
        s["targetValueOne"], s["targetValueTwo"] = float(lo), float(hi)
    if desc:
        s["description"] = desc[:200]
    return s


def build_dto(s: dict, ftp_w: float | None) -> dict:
    sport = s["sport"]
    dur = int(s["dur_min"]) * 60
    st = SPORT[sport]
    name = f"Trener: {s['name']} {s['dur_min']}′"[:60]
    desc = (s.get("note") or "") + f" · QBot Trener {s['day']}"
    if sport == "rower":
        z = int(s.get("zone") or 2)
        lo, hi = ZONE_PCT.get(z, ZONE_PCT[2])
        wu, cd = (600, 300) if dur >= 45 * 60 else (300, 180)
        main = max(300, dur - wu - cd)
        steps = [_step(1, "warmup", wu, desc="spokojnie")]
        if ftp_w:
            steps.append(_step(2, "interval", main, _PWR_T, round(lo * ftp_w), round(hi * ftp_w), f"Z{z}: {round(lo * ftp_w)}–{round(hi * ftp_w)} W"))
        else:
            steps.append(_step(2, "interval", main, desc=f"strefa Z{z}"))
        steps.append(_step(3, "cooldown", cd))
    else:
        steps = [_step(1, "interval", dur, desc=s["name"])]
    return {"workoutName": name, "sportType": dict(st), "estimatedDurationInSecs": dur, "description": desc.strip(" ·")[:500],
            "workoutSegments": [{"segmentOrder": 1, "sportType": dict(st), "workoutSteps": steps}]}


def idem_key(s: dict) -> str:
    raw = f"{s['id']}|{s['day']}|{s['sport']}|{s['dur_min']}|{s.get('zone')}|{s.get('start_time')}|{s['name']}"
    return "trener-" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def push(s: dict, ftp_w: float | None, dry_run: bool = False) -> dict[str, Any]:
    dto = build_dto(s, ftp_w)
    key = idem_key(s)
    if dry_run:
        return {"status": "DRY_RUN_OK", "payload": dto, "idempotency_key": key}
    from qbot_garmin_workouts import audit_lookup, audit_record, _extract_workout_id, _find_workout_by_name
    ex = audit_lookup(key)
    if ex and ex.get("status") == "SUCCESS":
        return {"status": "DUPLICATE", "workoutId": ex.get("workout_id"), "idempotency_key": key}
    audit_record(idempotency_key=key, action_type="trener_workout_push", workout_name=dto["workoutName"], workout_id=None,
                 status="PENDING", verified=False, payload=dto, result={"status": "pending"}, source="qbot_trener")
    try:
        from garmin_auth import garmin_client
        cl = garmin_client()
        res = cl.upload_workout(dto)
        wid = _extract_workout_id(res) or _find_workout_by_name(cl, dto["workoutName"])
        if not wid:
            raise RuntimeError("Garmin nie zwrócił workoutId")
        sched = cl.schedule_workout(wid, str(s["day"]))
        audit_record(idempotency_key=key, action_type="trener_workout_push", workout_name=dto["workoutName"], workout_id=str(wid),
                     status="SUCCESS", verified=True, payload=dto, result={"upload": str(res)[:500], "schedule": str(sched)[:300]}, source="qbot_trener")
        return {"status": "success", "workoutId": str(wid), "scheduled": str(s["day"]), "idempotency_key": key}
    except Exception as e:
        err = str(e)[:400]
        try:
            audit_record(idempotency_key=key, action_type="trener_workout_push", workout_name=dto["workoutName"], workout_id=None,
                         status="ERROR", verified=False, payload=dto, result={"error": err}, source="qbot_trener")
        except Exception:
            pass
        return {"status": "ERROR", "error": err, "idempotency_key": key}
