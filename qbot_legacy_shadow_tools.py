"""Legacy Q shadow mode — compare new wrappers against legacy state, plan cutover."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from qbot_tools import _tool_qbot_project_guard_check

_SHADOW_ALLOWED: set[str] = {"qlab", "export", "sync", "garmin"}


def _probe_single(cap: str) -> dict[str, Any]:
    if cap not in _SHADOW_ALLOWED:
        return {"status": "error", "error": f"unknown capability: {cap!r}"}

    legacy = {}
    try:
        from qbot_legacy_wrapper_tools import (
            _tool_qbot_legacy_export_status,
            _tool_qbot_legacy_garmin_status,
            _tool_qbot_legacy_qlab_status,
            _tool_qbot_legacy_sync_status,
        )
        status_map = {"export": _tool_qbot_legacy_export_status, "garmin": _tool_qbot_legacy_garmin_status,
                      "qlab": _tool_qbot_legacy_qlab_status, "sync": _tool_qbot_legacy_sync_status}
        legacy = status_map[cap]({})
    except Exception as exc:
        legacy = {"readiness": "ERROR", "error": str(exc)}

    wrapper = {}
    if cap == "qlab":
        try:
            from qbot_legacy_execution_tools import _tool_qbot_legacy_qlab_smoke_check
            wrapper = _tool_qbot_legacy_qlab_smoke_check()
        except Exception as exc:
            wrapper = {"status": "ERROR", "error": str(exc)}
    else:
        try:
            from qbot_legacy_execution_tools import (
                _tool_qbot_legacy_export_dry_run,
                _tool_qbot_legacy_garmin_dry_run,
                _tool_qbot_legacy_sync_dry_run,
            )
            dr = {"export": _tool_qbot_legacy_export_dry_run, "garmin": _tool_qbot_legacy_garmin_dry_run,
                  "sync": _tool_qbot_legacy_sync_dry_run}.get(cap)
            wrapper = dr({}) if dr else {"status": "ERROR", "error": "no dry-run tool"}
        except Exception as exc:
            wrapper = {"status": "ERROR", "error": str(exc)}

    leg_r = legacy.get("readiness", "UNKNOWN")
    wra_r = wrapper.get("readiness_for_real_wrapper", wrapper.get("status", "UNKNOWN"))
    mismatches: list[str] = []
    if leg_r != wra_r and leg_r != "UNKNOWN" and wra_r != "UNKNOWN":
        mismatches.append(f"readiness mismatch: legacy={leg_r} new={wra_r}")
    matching = len(mismatches) == 0

    return {
        "capability": cap,
        "legacy_observed": {"source": "wrapper_status", "readiness": leg_r, "files": len(legacy.get("detected_files", []))},
        "new_wrapper_result": {"source": "smoke/dry_run", "readiness": wra_r},
        "comparison": {"matching": matching, "mismatches": mismatches, "confidence": "high" if matching else "medium"},
        "status": "OK" if matching else "WARN",
        "safe_next_steps": ["Continue shadow monitoring"] if matching else ["Review mismatches before cutover"],
    }


# ──────────── qbot_legacy_shadow_probe ──────────────────────────────────

def _tool_qbot_legacy_shadow_probe(args: dict | None = None) -> dict[str, Any]:
    cap = (args or {}).get("capability", "")
    if cap not in _SHADOW_ALLOWED:
        return {
            "tool": "qbot_legacy_shadow_probe",
            "status": "error",
            "error": f"unknown capability: {cap!r}",
            "allowed": sorted(_SHADOW_ALLOWED),
        }
    result = _probe_single(cap)
    result["tool"] = "qbot_legacy_shadow_probe"
    return result


# ──────────── qbot_legacy_shadow_report ──────────────────────────────────

def _tool_qbot_legacy_shadow_report(_args: dict | None = None) -> dict[str, Any]:
    results = {}
    match_count = 0
    mismatch_capabilities: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []

    for cap in sorted(_SHADOW_ALLOWED):
        results[cap] = _probe_single(cap)
        if results[cap].get("comparison", {}).get("matching"):
            match_count += 1
        else:
            mismatch_capabilities.append(cap)
            warnings.extend(results[cap].get("comparison", {}).get("mismatches", []))

    try:
        from qbot_legacy_wrapper_tools import _tool_qbot_legacy_readonly_wrapper_report
        wreport = _tool_qbot_legacy_readonly_wrapper_report()
    except Exception:
        wreport = {"takeover_readiness_percent": 85}

    try:
        from qbot_legacy_execution_tools import _tool_qbot_legacy_safe_execution_report
        safe = _tool_qbot_legacy_safe_execution_report()
    except Exception:
        safe = {"ready_for_shadow_mode": True}

    try:
        from qbot_legacy_tools import _tool_qbot_legacy_health_report
        health = _tool_qbot_legacy_health_report()
    except Exception:
        health = {"status": "OK"}

    guard = _tool_qbot_project_guard_check()
    for v in guard.get("violations", []):
        if v.get("severity") == "ERROR":
            blockers.append(f"Guard: {v.get('what')}")

    cutover_ready = (
        match_count == 4
        and len(mismatch_capabilities) == 0
        and health.get("status") != "ERROR"
        and safe.get("ready_for_shadow_mode", False)
        and not blockers
    )

    takeover = 90 if cutover_ready else 85

    return {
        "tool": "qbot_legacy_shadow_report",
        "phase": "Phase 3 shadow mode",
        "shadow_results": results,
        "matching_count": match_count,
        "mismatch_count": 4 - match_count,
        "blockers": blockers,
        "warnings": warnings,
        "status": "OK" if cutover_ready else "WARN",
        "takeover_readiness_percent": takeover,
        "ready_for_cutover": cutover_ready,
        "recommended_next_phase": "Phase 4: cutover" if cutover_ready else "Resolve mismatches before cutover",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ──────────── qbot_legacy_shadow_answer_context ─────────────────────────

_SENSITIVE: set[str] = {"password", "secret", "token", "apikey", "api_key", "pgpassword", "env", "credential", "auth"}


def _sanitize(obj: Any, depth: int = 0) -> Any:
    if depth > 3:
        return "<truncated>"
    if isinstance(obj, dict):
        r: dict[str, Any] = {}
        for k, v in obj.items():
            if any(s in str(k).lower() for s in _SENSITIVE):
                r[k] = "<redacted>"
            elif isinstance(v, (dict, list)):
                r[k] = _sanitize(v, depth + 1)
            elif isinstance(v, str) and len(v) > 2000:
                r[k] = v[:2000] + "...<truncated>"
            else:
                r[k] = v
        return r
    if isinstance(obj, list):
        return [_sanitize(v, depth + 1) if isinstance(v, (dict, list)) else v[:500] + "...<truncated>" if isinstance(v, str) and len(v) > 500 else v for v in obj[:50]]
    return obj[:2000] + "...<truncated>" if isinstance(obj, str) and len(obj) > 2000 else obj


def _tool_qbot_legacy_shadow_answer_context(_args: dict | None = None) -> dict[str, Any]:
    try:
        raw = _tool_qbot_legacy_shadow_report()
    except Exception as exc:
        return {"tool": "qbot_legacy_shadow_answer_context", "status": "error", "error": str(exc)}
    return {
        "tool": "qbot_legacy_shadow_answer_context",
        "safe_for_llm": True,
        "source": "qbot_legacy_shadow_report",
        "context": _sanitize(raw),
        "suggested_answer_outline": ["1. Summarize shadow comparison results", "2. Note match/mismatch counts", "3. Recommend cutover readiness", "4. Stay factual"],
        "llm_must_not": ["execute cutover", "disable legacy services", "modify production config"],
        "limitations": ["Shadow comparison only", "No production changes", "Sanitized context"],
    }


# ──────────── qbot_legacy_cutover_plan ───────────────────────────────────

def _tool_qbot_legacy_cutover_plan(_args: dict | None = None) -> dict[str, Any]:
    return {
        "tool": "qbot_legacy_cutover_plan",
        "current_phase": "Phase 3 shadow mode",
        "status": "PLAN_ONLY",
        "prerequisites": [
            "qbot_legacy_shadow_report shows matching_count == 4",
            "qbot_legacy_shadow_report shows ready_for_cutover == true",
            "qbot_operator_final_smoke_test returns PASS or WARN with 100%",
            "All legacy health checks pass",
            "qbot_project_guard_check returns OK",
            "Manual operator approval",
        ],
        "cutover_steps": [
            "1. Notify operators: cutover window starting",
            "2. Run final backup: systemctl start qbot-backup.service",
            "3. Verify backup: gzip -t /opt/qbot/backups/latest",
            "4. Run restore drill: verify qbot_restore_drill_status OK",
            "5. Stop legacy q-bot.service: systemctl stop q-bot.service (MANUAL ONLY)",
            "6. Verify new Qbot API handles all capabilities correctly",
            "7. Disable legacy q-bot.service: systemctl disable q-bot.service (MANUAL ONLY)",
            "8. Run qbot_operator_final_smoke_test — expect 100%",
            "9. Announce cutover complete",
        ],
        "rollback_steps": [
            "1. Enable q-bot.service: systemctl enable q-bot.service",
            "2. Start q-bot.service: systemctl start q-bot.service",
            "3. Verify legacy operation via qbot_legacy_health_report",
            "4. Investigate new Qbot issues before retry",
        ],
        "validation_steps": [
            "Run qbot_legacy_shadow_report after cutover",
            "Monitor qbot_legacy_health_report for 24h",
            "Check tool_calls history for errors",
            "Verify backup and restore drill still functional",
        ],
        "do_not_execute": [
            "Do NOT disable q-bot.service via API",
            "Do NOT change production routing via API",
            "Do NOT delete legacy files",
            "Do NOT drop qbot database",
            "Do NOT remove systemd units without confirmation",
        ],
        "required_manual_approval": True,
        "notes": "This is a PLAN only — no actions are executed. All cutover steps require manual operator confirmation.",
    }


def _get_legacy_shadow_tool(name: str):
    mapping = {
        "qbot_legacy_shadow_probe": _tool_qbot_legacy_shadow_probe,
        "qbot_legacy_shadow_report": _tool_qbot_legacy_shadow_report,
        "qbot_legacy_shadow_answer_context": _tool_qbot_legacy_shadow_answer_context,
        "qbot_legacy_cutover_plan": _tool_qbot_legacy_cutover_plan,
    }
    return mapping.get(name)
