#!/usr/bin/env python3
"""Backfill biegow (SRAM AXS) do qbot_v2.activity_record z plikow FIT na dysku.

Zrodlo prawdy: eventy front_gear_change / rear_gear_change w FIT - niosa liczbe
zebow wprost (front_gear / rear_gear). Fill-forward po czasie; przed pierwszym
eventem biegi = NULL (event opisuje NOWY bieg, stanu sprzed nie znamy).

Uzycie:
  .venv/bin/python3 scripts/backfill_gears.py --since 2026-01-01 [--only EXTERNAL_ID] [--dry]
"""
import argparse
import os
import sys

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from fitparse import FitFile  # noqa: E402
import fitparse.records as _fr  # noqa: E402
import fitparse.base as _fb  # noqa: E402
from fitmodel.api import _db_connect  # noqa: E402

# Nieznane pola developerskie w FIT nie moga wywracac parsera
# (ta sama lata co w qbot_activity_ingest._safe_get_dev_type)
_BYTE_BT = next((bt for bt in _fr.BASE_TYPES.values() if getattr(bt, "size", None) == 1), None)
_ORIG_GET_DEV_TYPE = _fb.get_dev_type


def _safe_get_dev_type(dev_data_index, field_def_num):
    try:
        return _ORIG_GET_DEV_TYPE(dev_data_index, field_def_num)
    except Exception:
        return _fr.DevField(
            dev_data_index=dev_data_index, def_num=field_def_num, type=_BYTE_BT,
            name="unknown_dev_%s_%s" % (dev_data_index, field_def_num),
            units=None, native_field_num=None,
        )


_fb.get_dev_type = _safe_get_dev_type


def gear_events(fit_path):
    out = []
    ff = FitFile(fit_path)
    for m in ff.get_messages("event"):
        d = {f.name: f.value for f in m}
        if d.get("event") in ("front_gear_change", "rear_gear_change"):
            ts = d.get("timestamp")
            if ts is not None:
                def _i(k):
                    v = d.get(k)
                    return int(v) if v is not None else None
                out.append((ts, _i("front_gear"), _i("rear_gear"),
                            _i("front_gear_num"), _i("rear_gear_num")))
    out.sort(key=lambda g: g[0])
    return out


def backfill_one(cur, aid, fit_path, dry=False):
    if not fit_path or not os.path.exists(fit_path):
        return "BRAK_FIT", 0, 0
    gears = gear_events(fit_path)
    if not gears:
        return "BEZ_BIEGOW", 0, 0
    # interwaly [ts_od, ts_do) ze stalym biegiem; ostatni bez konca
    n_upd = 0
    for i, (ts, fg, rg, fn, rn) in enumerate(gears):
        ts_to = gears[i + 1][0] if i + 1 < len(gears) else None
        if dry:
            continue
        if ts_to is not None:
            cur.execute(
                "UPDATE qbot_v2.activity_record SET gear_front_t=%s, gear_rear_t=%s, "
                "gear_front_num=%s, gear_rear_num=%s "
                "WHERE external_id=%s AND ts >= %s AND ts < %s",
                (fg, rg, fn, rn, aid, ts, ts_to))
        else:
            cur.execute(
                "UPDATE qbot_v2.activity_record SET gear_front_t=%s, gear_rear_t=%s, "
                "gear_front_num=%s, gear_rear_num=%s "
                "WHERE external_id=%s AND ts >= %s",
                (fg, rg, fn, rn, aid, ts))
        n_upd += cur.rowcount
    return "OK", len(gears), n_upd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-01-01")
    ap.add_argument("--only", default=None)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    with _db_connect() as conn:
        cur = conn.cursor()
        if args.only:
            cur.execute("SELECT external_id, fit_path FROM qbot_v2.activity_fit_raw "
                        "WHERE external_id=%s", (args.only,))
        else:
            cur.execute("SELECT external_id, fit_path FROM qbot_v2.activity_fit_raw "
                        "WHERE started_at >= %s ORDER BY started_at", (args.since,))
        rides = cur.fetchall()
        print("jazd do przerobienia: %d (since %s)" % (len(rides), args.since))
        stat = {}
        for aid, fit_path in rides:
            try:
                st, n_ev, n_upd = backfill_one(cur, aid, fit_path, dry=args.dry)
            except Exception as e:
                conn.rollback()
                st, n_ev, n_upd = "BLAD:%s" % type(e).__name__, 0, 0
            stat[st] = stat.get(st, 0) + 1
            print("  %s  %-10s eventy=%-4d rekordy_upd=%d" % (aid, st, n_ev, n_upd))
            if not args.dry:
                conn.commit()
        print("PODSUMOWANIE:", stat)


if __name__ == "__main__":
    main()
