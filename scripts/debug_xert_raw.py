#!/usr/bin/env python3
"""debug_xert_raw.py — Diagnostyka surowej odpowiedzi Xert API.

Usage:
    .venv/bin/python3 scripts/debug_xert_raw.py
    .venv/bin/python3 scripts/debug_xert_raw.py --save-raw  (zapisze pełny payload do pliku)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))


def redact(s: str) -> str:
    """Redact sensitive values: tokens, passwords, bearer, secrets."""
    import re
    s = re.sub(r'(?i)(bearer|access_token|refresh_token|password|secret|authorization)\s*[:=]\s*\S+',
               r'\1: ***REDACTED***', s)
    s = re.sub(r'(?i)(xert_public|xert_private)\s+[\w-]+', r'\1 ***REDACTED***', s)
    return s


def main():
    p = argparse.ArgumentParser(description="Xert API raw response diagnostic")
    p.add_argument("--save-raw", action="store_true", help="Save full payload to file")
    args = p.parse_args()

    import httpx

    email = os.getenv("XERT_EMAIL", "").strip()
    pwd = os.getenv("XERT_PASSWORD", "").strip()
    if not email or not pwd:
        print("ERROR: XERT_EMAIL or XERT_PASSWORD not set")
        sys.exit(1)

    print("=" * 70)
    print("Xert API Raw Response Diagnostic")
    print("=" * 70)

    # Step 1: OAuth token
    print("\n[1/2] OAuth token request...")
    print(f"  POST https://www.xertonline.com/oauth/token")
    print(f"  auth: xert_public / xert_public (client credentials)")

    with httpx.Client(timeout=5.0, trust_env=False) as client:
        token_resp = client.post(
            "https://www.xertonline.com/oauth/token",
            auth=("xert_public", "xert_public"),
            data={
                "grant_type": "password",
                "username": email,
                "password": pwd,
            },
        )
        print(f"  HTTP status: {token_resp.status_code}")
        if token_resp.status_code != 200:
            print(f"  ERROR: token request failed")
            print(f"  Response: {redact(token_resp.text[:500])}")
            sys.exit(1)

        token_data = token_resp.json()
        token = token_data.get("access_token")
        print(f"  access_token: {'***' + token[-8:] if token else 'NONE'}")
        print(f"  token_type:   {token_data.get('token_type', 'N/A')}")

        # Step 2: Training data
        print("\n[2/2] Training data request...")
        print(f"  GET https://www.xertonline.com/oauth/training")
        print(f"  Authorization: Bearer ***")

        training_resp = client.get(
            "https://www.xertonline.com/oauth/training",
            headers={"Authorization": f"Bearer {token}"},
        )
        print(f"  HTTP status: {training_resp.status_code}")
        if training_resp.status_code != 200:
            print(f"  ERROR: training request failed")
            sys.exit(1)

        raw_data = training_resp.json()

    # Analyze response structure
    print("\n" + "=" * 70)
    print("RAW RESPONSE ANALYSIS")
    print("=" * 70)

    def _describe(obj, path="", depth=0, max_depth=4):
        if depth > max_depth:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                vtype = type(v).__name__
                if isinstance(v, dict):
                    print(f"  {path}.{k} [{vtype}] ({len(v)} keys)")
                    _describe(v, f"{path}.{k}", depth + 1, max_depth)
                elif isinstance(v, list):
                    print(f"  {path}.{k} [{vtype}] len={len(v)}" + (f"  sample: {v[0] if v else '[]'}" if depth < 2 else ""))
                else:
                    val_str = str(v)[:80] if isinstance(v, (str, int, float)) else str(v)
                    if isinstance(v, str) and len(v) > 80:
                        val_str = v[:80] + "..."
                    print(f"  {path}.{k} = {val_str}  [{vtype}]")
        elif isinstance(obj, list) and len(obj) > 0:
            print(f"  {path} [{type(obj).__name__}] len={len(obj)}  first_type={type(obj[0]).__name__}")

    top_keys = list(raw_data.keys())
    print(f"\nTop-level keys ({len(top_keys)}):")
    for k in top_keys:
        v = raw_data[k]
        vtype = type(v).__name__
        if isinstance(v, dict):
            print(f"  {k} [{vtype}] ({len(v)} sub-keys)")
        elif isinstance(v, list):
            print(f"  {k} [{vtype}] len={len(v)}")
        else:
            print(f"  {k} [{vtype}] = {str(v)[:60]}")

    print(f"\nFull structure (max depth 4):")
    _describe(raw_data, "root")

    # Check specific fields user asked about
    print("\n" + "=" * 70)
    print("FIELD CHECK — wymagane przez użytkownika")
    print("=" * 70)

    advice = raw_data.get("advice", {})
    sig = advice.get("signature", {})
    hp = advice.get("health_profile", {})
    rl = advice.get("recovery", {})
    fitness = advice.get("fitness_signature", {})
    freshness_status = advice.get("freshness_status", {})
    today = advice.get("today", {})

    checks = {
        "ftp / threshold / threshold_power": sig.get("ftp"),
        "ltp": sig.get("ltp"),
        "hie / w_prime": sig.get("atc"),
        "peak_power": hp.get("peak_power"),
        "training_load": rl.get("training_load"),
        "recovery_load": rl.get("recovery_load"),
        "form / form_ratio": fitness.get("form_ratio"),
        "freshness": freshness_status.get("freshness"),
        "fatigue": freshness_status.get("fatigue"),
        "strain": freshness_status.get("strain"),
        "difficulty": today.get("difficulty"),
        "xss": training_resp.headers.get("x-xss", "N/A (header not found)"),
        "specificity": None,
        "athlete_type": advice.get("athlete_type"),
        "signature": "present" if sig else "missing",
        "power_curve": "present" if advice.get("power_curve") else "missing",
        "last_activity": advice.get("last_activity"),
        "status / freshness_status": freshness_status.get("status"),
    }

    for field, val in checks.items():
        if val is not None and val != "missing":
            print(f"  ✅ {field:35s} = {str(val)[:60]}")
        elif val == "present":
            print(f"  ✅ {field:35s} present ({len(advice.get('signature',{}))} keys in signature)")
        elif val == "missing":
            print(f"  ❌ {field:35s} NOT AVAILABLE")
        else:
            print(f"  ❌ {field:35s} null/None")

    # Current mapping
    print(f"\nCurrent 3-field mapping (in _xert_sync_fetch):")
    print(f"  ftp_watts    ← signature.ftp          = {sig.get('ftp')}")
    print(f"  ltp_watts    ← signature.ltp          = {sig.get('ltp')}")
    print(f"  w_prime_kj   ← signature.atc / 1000   = {sig.get('atc')} → {round(sig.get('atc',0)/1000, 1) if sig.get('atc') else None} kJ")

    # Recommended expanded mapping
    print(f"\n--- RECOMMENDED EXPANDED MAPPING ---")
    print(f"All fields above that are available SHOULD be saved to DB.")
    print(f"The qbot_v2.xert_profile_snapshots table ALREADY HAS columns for:")
    print(f"  peak_power_w, training_load, recovery_load, form_ratio,")
    print(f"  ts_rating, freshness, fatigue, strain, difficulty, raw_json")

    # Check additional available fields
    print(f"\n--- ADDITIONAL AVAILABLE DATA ---")
    if "athlete_type" in advice:
        print(f"  athlete_type: {advice['athlete_type']}")
    if "training_load" in rl:
        print(f"  recovery.training_load: {rl['training_load']}")
    if "recovery_load" in rl:
        print(f"  recovery.recovery_load: {rl['recovery_load']}")
    la = advice.get("last_activity")
    if la:
        print(f"  last_activity: {json.dumps(la, ensure_ascii=False)[:200]}")

    # Save raw payload if requested
    if args.save_raw:
        out_path = Path("/opt/qbot/artifacts/xert_raw_diagnostic.json")
        sanitized = json.loads(redact(json.dumps(raw_data, default=str)))
        with open(out_path, "w") as f:
            json.dump(sanitized, f, ensure_ascii=False, indent=2)
        print(f"\nFull sanitized payload saved to: {out_path}")
        print(f"  Size: {out_path.stat().st_size} bytes")

    print("\nDone.")


if __name__ == "__main__":
    main()
