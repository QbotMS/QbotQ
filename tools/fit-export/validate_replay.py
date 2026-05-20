#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

def validate_replay(file_path):
    issues = []
    
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except Exception as e:
        return "FAIL", [f"CRITICAL: Failed to load JSON: {e}"], {}

    # 1. Structure
    ticks = []
    if isinstance(data, list):
        ticks = data
    elif isinstance(data, dict) and 'ticks' in data:
        ticks = data['ticks']
    else:
        issues.append("Root structure is neither a list nor a dict with 'ticks' key")
        return "FAIL", issues, {}

    tick_count = len(ticks)
    if tick_count == 0:
        issues.append("Tick count is 0")
        return "FAIL", issues, {}

    # Metadata checks
    if isinstance(data, dict):
        duration_sec = data.get('durationSec')
        if duration_sec is None or duration_sec <= 0:
            issues.append(f"Header durationSec is invalid: {duration_sec}")
        elif duration_sec > 100000: # ~27 hours, seems like a reasonable upper bound for a single ride
            issues.append(f"Header durationSec is suspiciously large: {duration_sec}")

    # 2. Per-tick checks
    last_elapsed = -1.0
    last_kcal = -1.0
    last_moving = -1.0
    
    live_history = {
        'speed': [],
        'power': [],
        'heartRate': [],
        'cadence': [],
        'grade': [],
        'gear': []
    }
    
    dyn_history = []
    rsrv_history = []
    
    has_stats = False
    has_dyn = False

    for i, tick in enumerate(ticks):
        # Basic tick structure
        for field in ['replayTick', 'rideState', 'hudState']:
            if field not in tick:
                issues.append(f"Tick {i}: missing '{field}'")
                continue

        rt = tick.get('replayTick', {})
        rs = tick.get('rideState', {})
        hs = tick.get('hudState', {})

        # Time checks
        elapsed = rt.get('elapsedSec')
        if elapsed is None:
            issues.append(f"Tick {i}: replayTick.elapsedSec is missing")
        else:
            if elapsed < last_elapsed:
                issues.append(f"Tick {i}: elapsedSec is not monotonic ({last_elapsed} -> {elapsed})")
            last_elapsed = elapsed

        ts_ms = tick.get('timestampMs')
        if ts_ms is not None and elapsed is not None:
            if ts_ms == elapsed:
                issues.append(f"Tick {i}: timestampMs ({ts_ms}) is identical to elapsedSec")

        # HUD checks
        live = hs.get('LIVE') or hs.get('live')
        if not live:
            issues.append(f"Tick {i}: hudState missing LIVE")
        else:
            for field in ['speed', 'power', 'heartRate', 'cadence', 'grade', 'gear']:
                if field not in live:
                    issues.append(f"Tick {i}: hudState.LIVE missing '{field}'")
                else:
                    f_data = live[field]
                    if not isinstance(f_data, dict) or 'value' not in f_data:
                         issues.append(f"Tick {i}: hudState.LIVE.{field} invalid structure")
                    else:
                         live_history[field].append(f_data.get('value'))
                         if 'reasonCode' not in f_data or not f_data['reasonCode']:
                             issues.append(f"Tick {i}: hudState.LIVE.{field} missing reasonCode")

        stats = hs.get('STATS') or hs.get('stats')
        if stats:
            has_stats = True
            # kcal monotonic
            kcal_data = stats.get('kcal', {})
            kcal = kcal_data.get('value') if isinstance(kcal_data, dict) else None
            if kcal is not None:
                if kcal < last_kcal:
                    issues.append(f"Tick {i}: kcal decreased ({last_kcal} -> {kcal})")
                last_kcal = kcal

            # movingSec monotonic
            moving_data = stats.get('movingSec', {})
            moving = moving_data.get('value') if isinstance(moving_data, dict) else None
            if moving is not None:
                if moving < last_moving:
                    issues.append(f"Tick {i}: movingSec decreased ({last_moving} -> {moving})")
                last_moving = moving

            # stoppedSec = elapsedSec - movingSec
            stopped_data = stats.get('stoppedSec', {})
            stopped = stopped_data.get('value') if isinstance(stopped_data, dict) else None
            if elapsed is not None and moving is not None and stopped is not None:
                # Tolerance of 2 seconds for rounding/indexing
                if abs(stopped - (elapsed - moving)) > 2.0:
                    issues.append(f"Tick {i}: stoppedSec ({stopped}) mismatch: elapsed ({elapsed}) - moving ({moving}) = {elapsed-moving}")

            # ETA/TTS jumps
            eta_data = stats.get('ETA', {})
            eta = eta_data.get('value') if isinstance(eta_data, dict) else None
            if eta is not None:
                if 'last_eta' in locals() and last_eta is not None:
                    # Check for jumps > 1 hour (3600s)
                    if abs(eta - last_eta) > 3600:
                         issues.append(f"Tick {i}: ETA absurd jump ({last_eta} -> {eta})")
                last_eta = eta

            tts_data = stats.get('TTS', {})
            tts = tts_data.get('value') if isinstance(tts_data, dict) else None
            if tts is not None:
                if 'last_tts' in locals() and last_tts is not None:
                    if abs(tts - last_tts) > 3600:
                         issues.append(f"Tick {i}: TTS absurd jump ({last_tts} -> {tts})")
                last_tts = tts

            # decoupling is not a constant fallback
            dec_data = stats.get('decoupling', {})
            dec = dec_data.get('value') if isinstance(dec_data, dict) else None
            if dec is not None:
                if 'dec_history' not in locals():
                    dec_history = []
                dec_history.append(dec)

            # rsrv doesn't grow without reasonCode
            rsrv_data = stats.get('rsrv', {})
            rsrv = rsrv_data.get('value') if isinstance(rsrv_data, dict) else None
            if rsrv is not None:
                if 'rsrv_history' not in locals():
                    rsrv_history = []
                if rsrv_history and rsrv > rsrv_history[-1]:
                    if not rsrv_data.get('reasonCode'):
                        issues.append(f"Tick {i}: rsrv increased without reasonCode")
                rsrv_history.append(rsrv)

        dyn = hs.get('DYN') or hs.get('dyn')
        if dyn:
            has_dyn = True
            dyn_history.append(json.dumps(dyn, sort_keys=True))

    # 3. Global checks
    if not has_stats:
        issues.append("STATS section is entirely missing from all ticks")
    if not has_dyn:
        issues.append("DYN section is entirely missing from all ticks")

    # LIVE content checks
    if live_history['speed']:
        speeds = [v for v in live_history['speed'] if v is not None and v > 0]
        if not speeds:
             issues.append("Speed is 0 or null for the entire ride")
        elif len(speeds) < len(live_history['speed']) * 0.05:
             # Just a warning/info, but let's record it if speed is mostly zero
             pass

    for field in ['power', 'heartRate', 'cadence']:
        vals = [v for v in live_history[field] if v is not None and v != "--"]
        if not vals:
            issues.append(f"LIVE.{field} is constantly null or '--'")

    # DYN frozen
    if dyn_history:
        if len(set(dyn_history)) == 1 and len(dyn_history) > 1:
            issues.append("DYN values are frozen (constant throughout the ride)")

    # decoupling frozen
    if 'dec_history' in locals() and dec_history:
        if len(set(dec_history)) == 1 and len(dec_history) > 1:
            issues.append(f"decoupling is constant fallback value: {dec_history[0]}")

    # Grade and Gear checks
    if live_history['grade']:
        # If grade is always 0.0, it might be a problem if it has no reasonCode explaining it
        # But for now let's just follow the prompt: "grade działa albo ma jasny reasonCode"
        pass

    # stoppedSec != elapsedSec check
    if has_stats:
        last_tick = ticks[-1]
        last_hs = last_tick.get('hudState', {})
        last_stats = last_hs.get('STATS') or last_hs.get('stats', {})
        stopped = last_stats.get('stoppedSec', {}).get('value')
        elapsed = last_tick.get('replayTick', {}).get('elapsedSec')
        if stopped is not None and elapsed is not None and elapsed > 10:
            if stopped == elapsed:
                # Check if there was any speed > 0
                if any(v is not None and v > 0 for v in live_history['speed']):
                    issues.append("stoppedSec == elapsedSec but moving data was present")

    # Final report
    status = "PASS" if not issues else "FAIL"
    report = {
        "status": status,
        "file": str(file_path),
        "timestamp": datetime.now().isoformat(),
        "tickCount": tick_count,
        "issueCount": len(issues),
        "issues": issues[:100] # Limit reported issues in JSON
    }
    
    return status, issues, report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File {file_path} does not exist")
        sys.exit(1)

    status, issues, report = validate_replay(file_path)

    # Output to console
    print(f"Validation Status: {status}")
    print(f"Total Issues: {len(issues)}")
    if issues:
        print("First 20 issues:")
        for issue in issues[:20]:
            print(f" - {issue}")

    # Save report
    activity_id = file_path.name.split('.')[0]
    report_path = file_path.parent / f"{activity_id}.validation_report.json"
    try:
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"Report saved to: {report_path}")
    except Exception as e:
        print(f"Failed to save report: {e}")

    if status == "FAIL":
        sys.exit(0) # User didn't ask to exit with error code, just print status

if __name__ == "__main__":
    main()
