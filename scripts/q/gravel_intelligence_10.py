#!/usr/bin/env python3
"""gravel_intelligence_10.py — Gravel Intelligence 1.0 consolidated module.

Three stable commands with standard JSON response contract:

1. analyze_route(route_id)  → G1+G10+G11+G13 → briefing + decisions
2. build_safe_gpx(route_id)  → G15 → safe_import.gpx with warnings
3. review_package(route_id)  → G14G → review MD + GeoJSON + JSON

Output unified under /opt/qbot/artifacts/gravel/<route_id>/
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path("/opt/qbot/app/scripts")
ARTIFACTS = Path("/opt/qbot/artifacts")
GRAVEL_DIR = ARTIFACTS / "gravel"


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    else:
        path.write_text(str(data), encoding="utf-8")


def _run_py(script: str, *args: str, timeout: int = 300) -> dict:
    """Run a Python script with args, return success/error."""
    cmd = [sys.executable, str(SCRIPTS / script)] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(SCRIPTS))
        return {"ok": r.returncode == 0, "stdout": r.stdout[-2000:], "stderr": r.stderr[-2000:], "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timeout after {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _result(ok: bool, status: str, route_id: str, mode: str, **kw) -> dict:
    return {
        "ok": ok,
        "status": status,
        "route_id": route_id,
        "mode": mode,
        "generated_at": _iso(),
        "generator": "gravel_intelligence_10",
        **kw,
    }


def _ensure_gravel_dir(route_id: str) -> Path:
    d = GRAVEL_DIR / route_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _copy(src: Path, dst: Path) -> None:
    if src.exists():
        shutil.copy2(str(src), str(dst))


# ── 1. analyze_route ─────────────────────────────────────────────────────

def analyze_route(route_id: str) -> dict:
    """Run full route analysis: G10 + G11 + G13 → briefing + decisions.

    Returns standard JSON contract.
    """
    out = _ensure_gravel_dir(route_id)
    rid = str(route_id)

    print(f"  [analyze] G10 surface scoring...", end=" ", flush=True)
    r = _run_py("g10_osm_cascade_scoring.py", "--route-id", rid)
    if not r["ok"]:
        return _result(False, "G10_FAILED", rid, "analyze", errors=[r.get("stderr", r.get("error", "G10 error"))][:1])

    # Copy G10 output
    for f in [f"g10_surface_{rid}.json", f"g10_surface_{rid}.md"]:
        _copy(ARTIFACTS / "surface" / f, out / f)
    g10 = _read_json(ARTIFACTS / "surface" / f"g10_surface_{rid}.json")

    print(f"G11 weather...", end=" ", flush=True)
    r = _run_py("g11_weather_modifier.py", "--route-id", rid)
    if not r["ok"]:
        print("(G11 optional, continuing)")

    for f in [f"g11_weather_surface_{rid}.json", f"g11_weather_surface_{rid}.md"]:
        _copy(ARTIFACTS / "surface" / f, out / f)

    print(f"G13 risk briefing...", end=" ", flush=True)
    r = _run_py("g13_risk_briefing.py", "--route-id", rid, "--mode", "build")  # G13 does have --mode
    if not r["ok"]:
        return _result(False, "G13_FAILED", rid, "analyze", errors=[r.get("stderr", r.get("error", "G13 error"))][:1])

    for f in [f"review_briefing_{rid}.json", f"review_briefing_{rid}.md", f"review_decisions_{rid}.json"]:
        _copy(ARTIFACTS / "review" / f, out / f)

    print("OK")

    briefing = _read_json(ARTIFACTS / "review" / f"review_briefing_{rid}.json")
    decisions = _read_json(ARTIFACTS / "review" / f"review_decisions_{rid}.json")

    problems = briefing.get("problems", []) if briefing else []
    warning_count = sum(1 for p in problems if p.get("suggested_default_decision") == "ACCEPT_WARNING")
    review_count = sum(1 for p in problems if p.get("suggested_default_decision") in ("REVIEW", "OMIT"))
    manual_count = sum(1 for p in problems if p.get("manual_override_applied"))

    risk = {
        "total_problems": len(problems),
        "accepted_warnings": warning_count,
        "review_required": review_count,
        "manual_overrides": manual_count,
        "dominant_surface": (g10 or {}).get("dominant_surface", "unknown"),
        "coverage_pct": (g10 or {}).get("coverage_pct", 0),
    }

    return _result(True, "ANALYZED", rid, "analyze",
                   input={"route_id": rid},
                   risk=risk,
                   artifacts={
                       "briefing": str(out / f"review_briefing_{rid}.json"),
                       "decisions": str(out / f"review_decisions_{rid}.json"),
                       "g10_surface": str(out / f"g10_surface_{rid}.json"),
                       "g11_weather": str(out / f"g11_weather_surface_{rid}.json") if (out / f"g11_weather_surface_{rid}.json").exists() else None,
                   },
                   next_action="gravel_build_safe_gpx")


# ── 2. build_safe_gpx ────────────────────────────────────────────────────

def build_safe_gpx(route_id: str) -> dict:
    """Build safe-import GPX: original trk + ACCEPT_WARNING waypoints only.

    Requires analyze_route to have run first (G13 briefing + decisions).
    """
    out = _ensure_gravel_dir(route_id)
    rid = str(route_id)

    print(f"  [safe_gpx] G15 combined GPX...", end=" ", flush=True)
    r = _run_py("g15_build_combined_poi_warnings_gpx.py", "--route-id", rid)
    if not r["ok"]:
        return _result(False, "G15_FAILED", rid, "safe_gpx", errors=[r.get("stderr", r.get("error", "G15 error"))][:1])

    # Copy combined outputs to unified dir
    for f in [f"combined_import_{rid}.gpx", f"combined_import_{rid}.md", f"combined_import_{rid}_summary.json"]:
        _copy(ARTIFACTS / "combined" / f, out / f)

    summary = _read_json(ARTIFACTS / "combined" / f"combined_import_{rid}_summary.json")
    print("OK")

    return _result(True, "SAFE_IMPORT_GPX", rid, "safe_gpx",
                   input={"route_id": rid, "mode": "safe_import"},
                   risk={
                       "warning_wpt_count": (summary or {}).get("warning_wpt_count", 0),
                       "poi_wpt_count": (summary or {}).get("poi_wpt_count", 0),
                       "total_wpt_count": (summary or {}).get("total_wpt_count", 0),
                       "geometry_modified": False,
                   },
                   artifacts={
                       "safe_import_gpx": str(out / f"combined_import_{rid}.gpx"),
                       "summary_md": str(out / f"combined_import_{rid}.md"),
                       "debug_json": str(out / f"combined_import_{rid}_summary.json"),
                       "output_trkpt_count": (summary or {}).get("output_trkpt_count", 0),
                       "original_trkpt_count": (summary or {}).get("original_trkpt_count", 0),
                   },
                   next_action="gravel_review_package")


# ── 3. review_package ────────────────────────────────────────────────────

def review_package(route_id: str) -> dict:
    """Build review package: MD + GeoJSON + JSON with standard contract.

    Requires analyze_route to have run (G13 briefing).
    If no candidate route exists, returns UNAVAILABLE gracefully.
    """
    out = _ensure_gravel_dir(route_id)
    rid = str(route_id)

    # Check if candidate route data exists
    csum = _read_json(ARTIFACTS / "reroute" / f"candidate_route_{rid}_g14f_fixed_summary.json")
    if csum is None:
        # Try G14E candidate
        csum = _read_json(ARTIFACTS / "reroute" / f"candidate_route_{rid}_summary.json")

    if csum is None:
        print(f"  [review] No candidate route data for {rid} — skipping")
        return _result(True, "UNAVAILABLE", rid, "review_package",
                       input={"route_id": rid},
                       risk={},
                       artifacts={"note": "Candidate route not built. Run gravel_analyze_route + full G14 pipeline first."},
                       next_action="gravel_analyze_route")

    print(f"  [review] G14G review package...", end=" ", flush=True)
    r = _run_py("g14g_candidate_review_package.py", "--route-id", rid)
    if not r["ok"]:
        return _result(False, "G14G_FAILED", rid, "review_package", errors=[r.get("stderr", r.get("error", "G14G error"))][:1])

    # Copy review package to unified dir
    for f in [f"review_package_{rid}.md", f"review_package_{rid}.json", f"review_package_{rid}.geojson"]:
        _copy(ARTIFACTS / "reroute" / f, out / f)

    pkg = _read_json(ARTIFACTS / "reroute" / f"review_package_{rid}.json")
    print("OK")

    return _result(True, "REVIEW_PACKAGE", rid, "review_package",
                   input={"route_id": rid},
                   risk={
                       "applied_replacements": (pkg or {}).get("applied_replacements", 0),
                       "skipped_replacements": (pkg or {}).get("skipped_replacements", 0),
                       "candidate_suspicious": (pkg or {}).get("suspicious", False),
                   },
                   artifacts={
                       "review_md": str(out / f"review_package_{rid}.md") if (out / f"review_package_{rid}.md").exists() else None,
                       "review_json": str(out / f"review_package_{rid}.json") if (out / f"review_package_{rid}.json").exists() else None,
                       "review_geojson": str(out / f"review_package_{rid}.geojson") if (out / f"review_package_{rid}.geojson").exists() else None,
                       "candidate_gpx": (pkg or {}).get("candidate_gpx_path", None),
                   },
                   next_action="manual_review")


# ── CLI ───────────────────────────────────────────────────────────────────

COMMANDS = {"analyze_route": analyze_route, "build_safe_gpx": build_safe_gpx, "review_package": review_package}


def main():
    import argparse
    from pathlib import Path
    # Detect command from script name or arg
    script = Path(sys.argv[0]).stem
    default_cmd = None
    for cmd in COMMANDS:
        if cmd.replace("_", "") in script.replace("gravel", "").replace("_", "").replace("-", ""):
            default_cmd = cmd
            break

    p = argparse.ArgumentParser(description="Gravel Intelligence 1.0")
    p.add_argument("command", nargs="?", default=default_cmd, choices=list(COMMANDS.keys()),
                    help=f"Command (default: {default_cmd or 'analyze_route'})")
    p.add_argument("--route-id", required=True)
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = p.parse_args()
    cmd = args.command or default_cmd or "analyze_route"

    print("=" * 70)
    print(f"Gravel Intelligence 1.0 — {cmd}")
    print("=" * 70)
    print(f"  Route ID: {args.route_id}")
    print()

    fn = COMMANDS[cmd]
    result = fn(args.route_id)

    # Save unified debug.json
    out_dir = GRAVEL_DIR / args.route_id
    out_dir.mkdir(parents=True, exist_ok=True)
    _write(out_dir / "debug.json", result)

    print()
    if args.pretty:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        ok = "✅" if result["ok"] else "❌"
        print(f"  {ok} status={result['status']}")
        print(f"  route_id={result['route_id']}")

        if "risk" in result:
            risk = result["risk"]
            print(f"  risk: {json.dumps(risk, ensure_ascii=False)}")
        if "artifacts" in result:
            arts = {k: v for k, v in result["artifacts"].items() if v is not None}
            print(f"  artifacts: {json.dumps(arts, ensure_ascii=False)}")
        if "next_action" in result:
            print(f"  next: {result['next_action']}")
        errors = result.get("errors", [])
        if errors:
            for e in errors:
                print(f"  error: {e}")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
