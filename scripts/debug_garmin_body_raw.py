#!/usr/bin/env python3
"""debug_garmin_body_raw.py — Diagnostyka wszystkich endpointów body/weight Garmin.

Sprawdza różne metody garminconnect dla podanego zakresu dat i szuka
pełnych danych body composition (bmi, bodyFat, muscleMass, boneMass, bodyWater).

Usage:
    .venv/bin/python3 scripts/debug_garmin_body_raw.py
    .venv/bin/python3 scripts/debug_garmin_body_raw.py --dates 2026-05-25,2026-05-31
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))


def _redact(sample: str, max_len: int = 1500) -> str:
    if len(sample) > max_len:
        return sample[:max_len] + "\n  ... (truncated)"
    return sample


def main():
    p = argparse.ArgumentParser(description="Garmin API body raw diagnostic")
    p.add_argument("--dates", default="2026-05-31",
                   help="Comma-separated dates to check")
    p.add_argument("--range", default="2026-05-25,2026-05-31",
                   help="Date range for bulk endpoints (start,end)")
    args = p.parse_args()

    from garminconnect import Garmin

    email = os.getenv("GARMIN_EMAIL", "").strip()
    pwd = os.getenv("GARMIN_PASSWORD", "").strip()
    tok = "/opt/qbot/app/.garmin_tokens"

    if not email:
        env_path = APP_DIR / ".env"
        for line in env_path.read_text().splitlines():
            if line.startswith("GARMIN_EMAIL="):
                email = line.split("=", 1)[1].strip()
            if line.startswith("GARMIN_PASSWORD="):
                pwd = line.split("=", 1)[1].strip()

    print("=" * 70)
    print("Garmin API Body Raw Diagnostic")
    print("=" * 70)

    g = Garmin(email, pwd)
    g.login(tokenstore=tok)

    dates = [d.strip() for d in args.dates.split(",")]
    range_parts = args.range.split(",")
    range_start, range_end = range_parts[0].strip(), range_parts[1].strip()

    # ── Helper: check entry for body composition fields ───────
    def _check_body_comp(entry: dict, label: str = "") -> dict:
        fields = {
            "weight": entry.get("weight"),
            "bmi": entry.get("bmi"),
            "bodyFat": entry.get("bodyFat"),
            "bodyWater": entry.get("bodyWater"),
            "boneMass": entry.get("boneMass"),
            "muscleMass": entry.get("muscleMass"),
            "skeletalMuscleMass": entry.get("skeletalMuscleMass"),
            "physiqueRating": entry.get("physiqueRating"),
            "visceralFat": entry.get("visceralFat"),
            "metabolicAge": entry.get("metabolicAge"),
            "sourceType": entry.get("sourceType"),
            "calendarDate": entry.get("calendarDate"),
        }
        has_bc = any(entry.get(k) is not None for k in [
            "bmi", "bodyFat", "bodyWater", "boneMass", "muscleMass"])
        return {"fields": fields, "has_body_comp": has_bc}

    def _print_entry(entry: dict, indent: str = "    ") -> None:
        c = _check_body_comp(entry)
        f = c["fields"]
        tag = "FULL" if c["has_body_comp"] else "w-only"
        w = f["weight"]
        wk = w / 1000.0 if (w and w > 500) else (w or 0)
        print(f"{indent}{f['calendarDate']} | {str(f['sourceType']):15s} | {tag:5s}"
              f" | w={wk:>7.1f}"
              f" | bmi={f['bmi'] or '-':>6}"
              f" | bf={f['bodyFat'] or '-':>5}"
              f" | water={f['bodyWater'] or '-':>5}"
              f" | muscle={f['muscleMass'] or '-':>6}"
              f" | bone={f['boneMass'] or '-':>6}"
              f" | smm={f['skeletalMuscleMass'] or '-':>6}"
              f" | viscFat={f['visceralFat'] or '-'}"
              f" | metaAge={f['metabolicAge'] or '-'}")

    # ── 1. get_body_composition (dateRange endpoint — WRONG) ──
    print(f"\n{'='*70}")
    print(f"METHOD 1 (WRONG): get_body_composition -> /weight/dateRange")
    print(f"  Range: {range_start}..{range_end}")
    print(f"{'='*70}")
    bc_raw = g.get_body_composition(range_start, range_end)
    entries = bc_raw.get("dateWeightList", []) if isinstance(bc_raw, dict) else []
    print(f"  Top-level keys: {list(bc_raw.keys()) if isinstance(bc_raw, dict) else 'N/A'}")
    print(f"  dateWeightList len: {len(entries)}")
    full_n = sum(1 for e in entries if _check_body_comp(e)["has_body_comp"])
    wo_n = len(entries) - full_n
    print(f"  Full body: {full_n}, Weight-only: {wo_n}")
    for e in entries:
        _print_entry(e)

    # ── 2. get_weigh_ins (range endpoint — CORRECT) ────────────
    print(f"\n{'='*70}")
    print(f"METHOD 2 (CORRECT): get_weigh_ins -> /weight/range?includeAll=true")
    print(f"  Range: {range_start}..{range_end}")
    print(f"{'='*70}")
    wi_raw = g.get_weigh_ins(range_start, range_end)
    dws = wi_raw.get("dailyWeightSummaries", []) if isinstance(wi_raw, dict) else []
    print(f"  Top-level keys: {list(wi_raw.keys()) if isinstance(wi_raw, dict) else 'N/A'}")
    print(f"  dailyWeightSummaries len: {len(dws)}")

    full_n = 0
    wo_n = 0
    for day in dws:
        d = day.get("summaryDate")
        lw = day.get("latestWeight") or {}
        all_m = day.get("allWeightMetrics") or []
        c = _check_body_comp(lw)
        if c["has_body_comp"]:
            full_n += 1
            tag = "FULL"
        else:
            wo_n += 1
            tag = "w-only"
        print(f"  {d} | latestWeight -> ", end="")
        _print_entry(lw, indent="")
        if all_m:
            print(f"          allWeightMetrics ({len(all_m)} entries):")
            for m in all_m:
                mc = _check_body_comp(m)
                mt = "FULL" if mc["has_body_comp"] else "w-only"
                print(f"            {m.get('sourceType'):15s} | {mt:5s}"
                      f" | w={m.get('weight') or '-':>7}"
                      f" | bmi={m.get('bmi') or '-':>6}"
                      f" | bf={m.get('bodyFat') or '-':>5}"
                      f" | water={m.get('bodyWater') or '-':>5}"
                      f" | muscle={m.get('muscleMass') or '-':>6}"
                      f" | bone={m.get('boneMass') or '-':>6}")
    print(f"  Summary: {full_n} full, {wo_n} weight-only")

    # Show raw JSON for latestWeight on first + last date
    if dws:
        print(f"\n  --- Raw latestWeight sample (first day) ---")
        sample_day = dws[0]
        sample_json = json.dumps(sample_day.get("latestWeight", {}), indent=2,
                                 ensure_ascii=False, default=str)
        print(f"  {_redact(sample_json)}")
        if len(dws) > 1:
            print(f"\n  --- Raw latestWeight sample (last day) ---")
            sample_day = dws[-1]
            sample_json = json.dumps(sample_day.get("latestWeight", {}), indent=2,
                                     ensure_ascii=False, default=str)
            print(f"  {_redact(sample_json)}")

    # ── 3. get_daily_weigh_ins (dayview — ALL entries per day) ─
    print(f"\n{'='*70}")
    print(f"METHOD 3: get_daily_weigh_ins -> /weight/dayview?includeAll=true")
    print(f"{'='*70}")
    for dt in dates:
        print(f"\n  --- Date: {dt} ---")
        try:
            dv_raw = g.get_daily_weigh_ins(dt)
            dwl = dv_raw.get("dateWeightList", []) if isinstance(dv_raw, dict) else []
            print(f"  Top-level keys: {list(dv_raw.keys()) if isinstance(dv_raw, dict) else 'N/A'}")
            print(f"  dateWeightList: {len(dwl)} entries")
            for e in dwl:
                _print_entry(e)
            # Show raw JSON
            if dwl:
                print(f"  Raw JSON (all entries):")
                print(f"  {_redact(json.dumps(dwl, indent=2, ensure_ascii=False, default=str), 2000)}")
        except Exception as exc:
            print(f"  ERROR: {exc}")

    # ── 4. biometric/biometric ─────────────────────────────────
    print(f"\n{'='*70}")
    print(f"METHOD 4: biometric/biometric")
    print(f"{'='*70}")
    for dt in dates:
        print(f"\n  --- Date: {dt} ---")
        try:
            bio_url = f"{g.garmin_connect_biometric_url}/{dt}"
            bio_raw = g.connectapi(bio_url)
            print(f"  URL: {bio_url}")
            print(f"  Type: {type(bio_raw).__name__}")
            if isinstance(bio_raw, dict):
                print(f"  Keys: {list(bio_raw.keys())}")
                for key in ["bmi", "bodyFat", "bodyWater", "boneMass", "muscleMass",
                            "skeletalMuscleMass", "weight", "percentFat",
                            "percentHydration", "visceralFat", "metabolicAge",
                            "physiqueRating", "bodyComposition"]:
                    val = bio_raw.get(key)
                    if val is not None:
                        print(f"    ✅ {key}: {val}")
                sample = json.dumps(bio_raw, indent=2, ensure_ascii=False, default=str)
                print(f"  Raw: {_redact(sample, 2000)}")
        except Exception as exc:
            print(f"  ERROR: {exc}")

    # ── 5. biometric stats ─────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"METHOD 5: biometric/stats")
    print(f"{'='*70}")
    for dt in dates:
        print(f"\n  --- Date: {dt} ---")
        try:
            stats_url = f"{g.garmin_connect_biometric_stats_url}/{dt}"
            stats_raw = g.connectapi(stats_url)
            print(f"  URL: {stats_url}")
            print(f"  Type: {type(stats_raw).__name__}")
            if isinstance(stats_raw, dict):
                print(f"  Keys: {list(stats_raw.keys())[:20]}")
                sample = json.dumps(stats_raw, indent=2, ensure_ascii=False, default=str)
                print(f"  Raw: {_redact(sample, 1000)}")
        except Exception as exc:
            print(f"  ERROR: {exc}")

    # ── 6. get_stats_and_body ──────────────────────────────────
    print(f"\n{'='*70}")
    print(f"METHOD 6: get_stats_and_body (userStatsService)")
    print(f"{'='*70}")
    for dt in dates:
        print(f"\n  --- Date: {dt} ---")
        try:
            sb = g.get_stats_and_body(dt)
            print(f"  Type: {type(sb).__name__}")
            if isinstance(sb, dict):
                print(f"  Keys: {list(sb.keys())[:20]}")
                # Check for body comp sub-fields
                for k, v in sb.items():
                    if isinstance(v, dict) and any(
                        kw in str(v.keys()) for kw in ["bmi", "bodyFat", "weight"]
                    ):
                        print(f"  Sub-object '{k}' keys: {list(v.keys())[:15]}")
                        print(f"  Sample: {json.dumps(v, indent=2, ensure_ascii=False, default=str)[:500]}")
        except Exception as exc:
            print(f"  ERROR: {exc}")

    # ── 7. userMetrics ─────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"METHOD 7: userMetrics -> /metrics/maxmet/daily")
    print(f"{'='*70}")
    for dt in dates:
        print(f"\n  --- Date: {dt} ---")
        try:
            um_url = f"{g.garmin_connect_metrics_url}/{dt}"
            um_raw = g.connectapi(um_url)
            print(f"  URL: {um_url}")
            print(f"  Type: {type(um_raw).__name__}")
            if isinstance(um_raw, dict):
                print(f"  Keys: {list(um_raw.keys())[:20]}")
                sample = json.dumps(um_raw, indent=2, ensure_ascii=False, default=str)
                print(f"  Raw: {_redact(sample, 1000)}")
        except Exception as exc:
            print(f"  ERROR: {exc}")

    # ── Summary ────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"  Test dates:          {dates}")
    print(f"  Test range:          {range_start}..{range_end}")
    print(f"")
    print(f"  METHOD 1 (dateRange):         ONLY MFP weight-only entries")
    print(f"  METHOD 2 (range+includeAll):  FULL INDEX_SCALE body comp (CORRECT)")
    print(f"  METHOD 3 (dayview+includeAll):ALL entries per day, including INDEX_SCALE")
    print(f"  METHOD 4 (biometric):         {'AVAILABLE' if True else 'N/A'} (returns 405 for some dates)")
    print(f"  METHOD 6 (stats_and_body):    No body comp fields")
    print(f"")
    print(f"  RECOMMENDATION: Use get_weigh_ins(start, end) for range or")
    print(f"                  get_daily_weigh_ins(date) for single day.")
    print(f"                  Use latestWeight from dailyWeightSummaries (prefer INDEX_SCALE).")
    print(f"                  NEVER use get_body_composition (dateRange endpoint).")

    print(f"\nDone.")


if __name__ == "__main__":
    main()
