#!/usr/bin/env python3
"""g7b_gravel_batch_process.py — G7B Batch runner dla Gravel Intelligence pipeline.

Dla wielu route_id uruchamia: export GPX → G1 surface → G2 risk → G3/G6 gravel import.
Generuje zbiorczy raport MD/JSON.

Usage:
    python scripts/g7b_gravel_batch_process.py \\
        --routes 55395119,55395120,55395123 \\
        --project-id tuscany_2026 \\
        --mode build

Options:
    --routes         Comma-separated route IDs (required)
    --project-id     Optional project label
    --mode           dry-run|build (default: build)
    --force          Re-run even if cache/artifacts exist (default: false)
    --skip-existing  Skip routes with existing G3 output (default: true)
    --max-warnings   Max warnings per route (default: 6)
    --output-dir     Artifacts output dir (default: /opt/qbot/artifacts/gravel)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
SCRIPTS_DIR = APP_DIR / "scripts"
ARTIFACTS_DIR = Path("/opt/qbot/artifacts")
GRAVEL_DIR = ARTIFACTS_DIR / "gravel"
EXPORTS_DIR = ARTIFACTS_DIR / "exports" / "rwgps"
SURFACE_DIR = ARTIFACTS_DIR / "surface"

PYTHON = APP_DIR / ".venv" / "bin" / "python"
if not PYTHON.exists():
    alt = APP_DIR / "cronometer-venv" / "bin" / "python"
    PYTHON = alt if alt.exists() else Path("python3")


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="G7B Batch Processing dla Gravel Intelligence")
    p.add_argument("--routes", required=True, help="Comma-separated route_ids")
    p.add_argument("--project-id", default="", help="Optional project label")
    p.add_argument("--mode", choices=["dry-run", "build"], default="build")
    p.add_argument("--force", action="store_true", default=False)
    p.add_argument("--skip-existing", default="true", choices=["true", "false"],
                   help="Skip routes with existing G3 output (default: true)")
    p.add_argument("--max-warnings", type=int, default=6)
    p.add_argument("--output-dir", default=str(GRAVEL_DIR))
    return p.parse_args()


def _get(d: dict | None, key: str, default=None):
    return d.get(key, default) if d else default


def _read_json(path: Path) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _run_script(script_name: str, args: list[str], timeout: int = 300) -> tuple[int, str, str]:
    cmd = [str(PYTHON), str(SCRIPTS_DIR / script_name)] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(APP_DIR))
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except Exception as e:
        return -1, "", str(e)


def _ensure_gpx(route_id: str) -> dict:
    gpx_path = EXPORTS_DIR / f"rwgps_{route_id}.gpx"
    if gpx_path.exists():
        route_name = None
        g1 = _read_json(SURFACE_DIR / f"surface_{route_id}.json")
        if g1:
            route_name = g1.get("route_name")
        return {"ok": True, "status": "cached", "gpx_path": str(gpx_path),
                "route_name": route_name}

    sys.path.insert(0, str(APP_DIR))
    try:
        from tools.rwgps.client import export_route_to_artifact
        result = export_route_to_artifact(route_id, fmt="gpx")
        return {
            "ok": result.get("ok", False),
            "status": "exported" if result.get("ok") else "failed",
            "gpx_path": result.get("artifact_path", str(gpx_path)),
            "route_name": result.get("route_name"),
            "point_count": result.get("point_count"),
            "distance_km": result.get("distance_km"),
        }
    except Exception as e:
        return {"ok": False, "status": "error", "error": str(e), "gpx_path": str(gpx_path)}


def _process_one_route(
    route_id: str,
    mode: str = "build",
    force: bool = False,
    skip_existing: bool = True,
    max_warnings: int = 6,
) -> dict:
    status: dict = {
        "route_id": route_id,
        "route_name": None,
        "gpx_export_ok": False,
        "g1_ok": False,
        "g2_ok": False,
        "g3_ok": False,
        "trkpt_count": None,
        "wpt_count": None,
        "warning_count": None,
        "surface_confidence": None,
        "unknown_pct": None,
        "total_risk_km": None,
        "high_risk_km": None,
        "output_gpx_path": None,
        "output_md_path": None,
        "output_summary_path": None,
        "error": None,
        "pipeline_status": "pending",
    }

    g3_gpx = GRAVEL_DIR / f"gravel_import_{route_id}.gpx"
    g3_summary_path = GRAVEL_DIR / f"gravel_import_{route_id}_summary.json"
    g3_md_path = GRAVEL_DIR / f"gravel_import_{route_id}.md"

    # Skip-existing check
    if skip_existing and not force:
        existing = _read_json(g3_summary_path)
        if existing and existing.get("ok") and g3_gpx.exists():
            wlist = existing.get("warnings_in_gpx_list") or []
            if isinstance(wlist, int):
                wlist = []
            # Also read G1/G2 data for enriched fields
            g1_data = _read_json(SURFACE_DIR / f"surface_{route_id}.json")
            g2_data = _read_json(SURFACE_DIR / f"risk_segments_{route_id}.json")
            status.update({
                "gpx_export_ok": True,
                "g1_ok": True,
                "g2_ok": True,
                "g3_ok": True,
                "trkpt_count": existing.get("trkpt_count"),
                "wpt_count": existing.get("wpt_count"),
                "warning_count": len(wlist),
                "output_gpx_path": existing.get("output_gpx_path"),
                "output_md_path": existing.get("output_md_path"),
                "output_summary_path": str(g3_summary_path),
                "pipeline_status": "skipped",
                "surface_confidence": _get(g1_data, "confidence") or existing.get("surface_confidence"),
                "unknown_pct": _get(g1_data, "unknown_pct") or existing.get("unknown_pct"),
                "total_risk_km": _get(g2_data, "total_risk_km") or existing.get("total_risk_km"),
                "high_risk_km": _get(g2_data, "high_risk_km") or existing.get("high_risk_km"),
                "route_name": existing.get("route_name") or _get(g1_data, "route_name") or status["route_name"],
            })
            return status

    try:
        # ── G0: GPX export ────────────────────────────────────────────────
        export = _ensure_gpx(route_id)
        status["gpx_export_ok"] = export.get("ok", False)
        if export.get("route_name"):
            status["route_name"] = export["route_name"]

        if not export.get("ok"):
            status["error"] = f"GPX export failed: {export.get('error', 'unknown')}"
            status["pipeline_status"] = "error"
            return status

        # ── G1: Surface analysis ──────────────────────────────────────────
        g1_args = ["--route-id", str(route_id)]
        if force:
            g1_args.append("--force")
        rc, _, stderr = _run_script("g1_analyze_surface.py", g1_args, timeout=300)
        if rc != 0:
            status["error"] = f"G1 failed (rc={rc}): {stderr[:500]}"
            status["pipeline_status"] = "error"
            return status

        g1_data = _read_json(SURFACE_DIR / f"surface_{route_id}.json")
        if g1_data and g1_data.get("ok"):
            status["g1_ok"] = True
            status["trkpt_count"] = g1_data.get("point_count")
            status["surface_confidence"] = g1_data.get("confidence")
            status["unknown_pct"] = g1_data.get("unknown_pct")
            if not status["route_name"]:
                status["route_name"] = g1_data.get("route_name")
        else:
            status["error"] = "G1 output invalid"
            status["pipeline_status"] = "error"
            return status

        # ── G2: Risk detection ────────────────────────────────────────────
        g2_args = ["--route-id", str(route_id)]
        if force:
            g2_args.append("--force")
        rc, _, stderr = _run_script("g2_detect_risks.py", g2_args, timeout=300)
        if rc != 0:
            status["error"] = f"G2 failed (rc={rc}): {stderr[:500]}"
            status["pipeline_status"] = "error"
            return status

        g2_data = _read_json(SURFACE_DIR / f"risk_segments_{route_id}.json")
        if g2_data and g2_data.get("ok"):
            status["g2_ok"] = True
            status["total_risk_km"] = g2_data.get("total_risk_km")
            status["high_risk_km"] = g2_data.get("high_risk_km")
        else:
            status["error"] = "G2 output invalid"
            status["pipeline_status"] = "error"
            return status

        # ── G3: Build gravel import GPX (G6 mode default) ─────────────────
        g3_mode = "build" if mode == "build" else "dry-run"
        g3_args = ["--route-id", str(route_id), "--mode", g3_mode,
                   "--max-warnings", str(max_warnings)]
        rc, _, stderr = _run_script("g3_build_gravel_import_gpx.py", g3_args, timeout=120)
        if rc != 0:
            status["error"] = f"G3 failed (rc={rc}): {stderr[:500]}"
            status["pipeline_status"] = "error"
            return status

        g3_data = _read_json(g3_summary_path)
        if g3_data and g3_data.get("ok"):
            status["g3_ok"] = True
            status["trkpt_count"] = g3_data.get("trkpt_count") or status["trkpt_count"]
            status["wpt_count"] = g3_data.get("wpt_count")
            wlist = g3_data.get("warnings_in_gpx_list") or []
            if isinstance(wlist, int):
                wlist = []
            status["warning_count"] = len(wlist)
            status["output_gpx_path"] = g3_data.get("output_gpx_path")
            status["output_md_path"] = g3_data.get("output_md_path")
            status["output_summary_path"] = str(g3_summary_path)
            if not status["route_name"] and g3_data.get("route_name"):
                status["route_name"] = g3_data["route_name"]
            status["pipeline_status"] = "ok"
        else:
            status["error"] = "G3 output invalid"
            status["pipeline_status"] = "error"

    except Exception as e:
        status["error"] = f"Unexpected: {e}"
        status["pipeline_status"] = "error"

    return status


def _generate_batch_report(
    statuses: list[dict],
    args: argparse.Namespace,
    batch_id: str,
    elapsed_s: float,
) -> tuple[dict, str]:
    succeeded = sum(1 for s in statuses if s.get("pipeline_status") == "ok")
    skipped = sum(1 for s in statuses if s.get("pipeline_status") == "skipped")
    failed = sum(1 for s in statuses if s.get("pipeline_status") == "error")

    routes_out = []
    for s in statuses:
        routes_out.append({
            "route_id": s["route_id"],
            "route_name": s.get("route_name"),
            "pipeline_status": s.get("pipeline_status", "unknown"),
            "gpx_export_ok": s.get("gpx_export_ok", False),
            "g1_ok": s.get("g1_ok", False),
            "g2_ok": s.get("g2_ok", False),
            "g3_ok": s.get("g3_ok", False),
            "trkpt_count": s.get("trkpt_count"),
            "wpt_count": s.get("wpt_count"),
            "warning_count": s.get("warning_count"),
            "surface_confidence": s.get("surface_confidence"),
            "unknown_pct": s.get("unknown_pct"),
            "total_risk_km": s.get("total_risk_km"),
            "high_risk_km": s.get("high_risk_km"),
            "output_gpx_path": s.get("output_gpx_path"),
            "output_md_path": s.get("output_md_path"),
            "output_summary_path": s.get("output_summary_path"),
            "error": s.get("error"),
        })

    report_json = {
        "meta": {
            "batch_id": batch_id,
            "generated_at": _iso_now(),
            "project_id": args.project_id,
            "mode": args.mode,
            "force": args.force,
            "skip_existing": args.skip_existing,
            "max_warnings": args.max_warnings,
            "output_dir": args.output_dir,
            "total_routes": len(statuses),
            "succeeded": succeeded,
            "skipped": skipped,
            "failed": failed,
            "elapsed_s": round(elapsed_s, 1),
            "generator": "g7b_gravel_batch_process.py",
        },
        "routes": routes_out,
    }

    # ── Markdown report ────────────────────────────────────────────────
    lines = [
        f"# Batch Gravel Intelligence Report",
        f"",
        f"**Batch ID:** {batch_id}",
        f"**Generated:** {_iso_now()}",
        f"**Project:** {args.project_id or '(none)'}",
        f"**Mode:** {args.mode}",
        f"**Total routes:** {len(statuses)} | **OK:** {succeeded} | **Skipped:** {skipped} | **Failed:** {failed}",
        f"**Elapsed:** {elapsed_s:.0f}s",
        f"",
        f"## Route Table",
        f"",
        f"| route_id | name | confidence | unknown % | risk km | high risk km | warnings | GPX | status |",
        f"|---|---|---|---|---|---|---|---|---|",
    ]

    for s in statuses:
        rid = s["route_id"]
        name = (s.get("route_name") or "")[:40]
        conf = s.get("surface_confidence") or "-"
        unk = f"{s.get('unknown_pct','-'):.1f}" if isinstance(s.get("unknown_pct"), (int, float)) else "-"
        risk = f"{s.get('total_risk_km','-'):.1f}" if isinstance(s.get("total_risk_km"), (int, float)) else "-"
        hrisk = f"{s.get('high_risk_km','-'):.1f}" if isinstance(s.get("high_risk_km"), (int, float)) else "-"
        wcnt = s.get("warning_count") or "-"
        gpx_link = Path(s.get("output_gpx_path", "")).name if s.get("output_gpx_path") else "-"
        st = s.get("pipeline_status", "error").upper()
        lines.append(f"| {rid} | {name} | {conf} | {unk} | {risk} | {hrisk} | {wcnt} | {gpx_link} | {st} |")

    # ── Per-route details ──────────────────────────────────────────────
    lines.extend(["", "## Route Details", ""])
    for s in statuses:
        lines.append(f"### {s['route_id']} — {s.get('route_name') or '(no name)'}")
        lines.append(f"")
        lines.append(f"- **Status:** {s.get('pipeline_status', 'unknown').upper()}")
        lines.append(f"- **GPX export:** {'OK' if s.get('gpx_export_ok') else 'FAIL'}")
        lines.append(f"- **G1 surface:** {'OK' if s.get('g1_ok') else 'FAIL'}")
        lines.append(f"- **G2 risks:** {'OK' if s.get('g2_ok') else 'FAIL'}")
        lines.append(f"- **G3 import:** {'OK' if s.get('g3_ok') else 'FAIL'}")
        if s.get("surface_confidence"):
            lines.append(f"- **Confidence:** {s['surface_confidence']}")
        if s.get("unknown_pct") is not None:
            lines.append(f"- **Unknown surface:** {s['unknown_pct']:.1f}%")
        if s.get("total_risk_km") is not None:
            lines.append(f"- **Total risk km:** {s['total_risk_km']:.2f}")
        if s.get("high_risk_km") is not None:
            lines.append(f"- **High risk km:** {s['high_risk_km']:.2f}")
        if s.get("warning_count") is not None:
            lines.append(f"- **Warnings:** {s['warning_count']}")
        if s.get("trkpt_count"):
            lines.append(f"- **Track points:** {s['trkpt_count']}")
        if s.get("wpt_count") is not None:
            lines.append(f"- **Waypoints:** {s['wpt_count']}")
        if s.get("output_gpx_path"):
            lines.append(f"- **GPX:** `{s['output_gpx_path']}`")
        if s.get("output_md_path"):
            lines.append(f"- **MD:** `{s['output_md_path']}`")
        if s.get("error"):
            lines.append(f"- **Error:** {s['error']}")
        lines.append("")

    # ── SCP commands ───────────────────────────────────────────────────
    gpx_files = [s.get("output_gpx_path") for s in statuses
                 if s.get("output_gpx_path") and s.get("pipeline_status") in ("ok", "skipped")]
    if gpx_files:
        lines.extend(["", "## SCP Commands", "", "```bash"])
        for gf in sorted(gpx_files):
            lines.append(f"scp q@qbot:{gf} .")
        lines.append("```")

    report_md = "\n".join(lines)
    return report_json, report_md


def _print_scp_summary(statuses: list[dict]):
    gpx_files = sorted(set(
        s["output_gpx_path"] for s in statuses
        if s.get("output_gpx_path") and s.get("pipeline_status") in ("ok", "skipped")
    ))
    md_files = sorted(set(
        s["output_md_path"] for s in statuses
        if s.get("output_md_path") and s.get("pipeline_status") in ("ok", "skipped")
    ))
    summary_files = sorted(set(
        s["output_summary_path"] for s in statuses
        if s.get("output_summary_path") and s.get("pipeline_status") in ("ok", "skipped")
    ))

    if not gpx_files:
        print("\n─── No GPX files to download ───")
        return

    print("\n" + "=" * 70)
    print("SCP — pobierz wszystkie pliki GPX na Maca (alias q):")
    print("=" * 70)
    for gf in gpx_files:
        print(f"  scp q@qbot:{gf} .")

    print("\nPobierz też MD i summary:")
    for mf in md_files:
        print(f"  scp q@qbot:{mf} .")
    for sf in summary_files:
        print(f"  scp q@qbot:{sf} .")

    print("\nLub wszystkie naraz (katalog):")
    print(f"  scp q@qbot:{GRAVEL_DIR / 'gravel_import_*'} .")
    print("=" * 70)


def main():
    args = _parse_args()

    route_ids = [r.strip() for r in args.routes.split(",") if r.strip()]
    if not route_ids:
        print("ERROR: --routes is empty")
        sys.exit(1)

    skip = args.skip_existing.lower() == "true"
    batch_id = f"gravel_intelligence_{_timestamp()}"
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'='*70}")
    print(f"G7B Gravel Intelligence Batch")
    print(f"{'='*70}")
    print(f"Batch ID:     {batch_id}")
    print(f"Project:      {args.project_id or '(none)'}")
    print(f"Mode:         {args.mode}")
    print(f"Force:        {args.force}")
    print(f"Skip existing: {skip}")
    print(f"Max warnings: {args.max_warnings}")
    print(f"Routes:       {len(route_ids)} — {', '.join(route_ids)}")
    print(f"{'='*70}\n")

    # ── Pre-export all GPX ─────────────────────────────────────────────
    print("[G0] Pre-export GPX...")
    for rid in route_ids:
        exp = _ensure_gpx(rid)
        flag = "✓" if exp.get("ok") else "✗"
        nm = (exp.get("route_name") or "")[:60]
        print(f"  {flag} {rid} — {nm}")

    # ── Process each route ────────────────────────────────────────────
    statuses: list[dict] = []
    t0 = time.time()
    for idx, rid in enumerate(route_ids, 1):
        print(f"\n[{idx}/{len(route_ids)}] Processing {rid}...")
        st = _process_one_route(
            route_id=rid,
            mode=args.mode,
            force=args.force,
            skip_existing=skip,
            max_warnings=args.max_warnings,
        )
        ps = st.get("pipeline_status", "error")
        nm = (st.get("route_name") or "")[:60]
        icon = {"ok": "✓", "skipped": "⏭", "error": "✗"}.get(ps, "?")
        print(f"  {icon} {rid} — {nm} — {ps.upper()}")
        if ps == "error" and st.get("error"):
            print(f"    Error: {st['error']}")
        statuses.append(st)

    elapsed = time.time() - t0

    # ── Generate reports ──────────────────────────────────────────────
    report_json, report_md = _generate_batch_report(statuses, args, batch_id, elapsed)

    json_path = output_dir / f"batch_{batch_id}.json"
    md_path = output_dir / f"batch_{batch_id}.md"

    with open(json_path, "w") as f:
        json.dump(report_json, f, ensure_ascii=False, indent=2, default=str)
    with open(md_path, "w") as f:
        f.write(report_md)

    # ── Summary ───────────────────────────────────────────────────────
    ok = sum(1 for s in statuses if s.get("pipeline_status") == "ok")
    skipped = sum(1 for s in statuses if s.get("pipeline_status") == "skipped")
    failed = sum(1 for s in statuses if s.get("pipeline_status") == "error")

    print(f"\n{'='*70}")
    print(f"BATCH COMPLETE")
    print(f"{'='*70}")
    print(f"  OK:      {ok}")
    print(f"  Skipped: {skipped}")
    print(f"  Failed:  {failed}")
    print(f"  Elapsed: {elapsed:.0f}s")
    print(f"  JSON:    {json_path}")
    print(f"  MD:      {md_path}")
    print(f"{'='*70}")

    _print_scp_summary(statuses)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
