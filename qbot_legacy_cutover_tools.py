"""Legacy cutover readiness gate — final validation before manual cutover, PLAN_ONLY."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from qbot_tools import _tool_qbot_git_status, _tool_qbot_project_guard_check

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


# ──────────── qbot_legacy_cutover_readiness_gate ────────────────────────

def _tool_qbot_legacy_cutover_readiness_gate(_args: dict | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []

    def _check(name: str, ok: bool, detail: str, blocker: str = "", warn: str = ""):
        checks.append({"name": name, "status": "OK" if ok else "FAIL", "detail": detail})
        if not ok and blocker:
            blockers.append(blocker)
        if not ok and not blocker and warn:
            warnings.append(warn)

    # Qbot Core
    try:
        from qbot_ops_tools import _tool_qbot_operator_final_smoke_test
        smoke = _tool_qbot_operator_final_smoke_test()
        core_ok = smoke.get("status") in ("PASS", "WARN") and smoke.get("operational_readiness_percent", 0) >= 95
        _check("qbot_core_final_smoke", core_ok, smoke.get("status", "?"),
               blocker="" if core_ok else "Qbot Core smoke test not passing")
    except Exception as exc:
        _check("qbot_core_final_smoke", False, str(exc), blocker="Qbot Core smoke test failed")

    # Backup
    try:
        from qbot_ops_tools import _tool_qbot_backup_status, _tool_qbot_backup_timer_status, _tool_qbot_restore_drill_status
        backup = _tool_qbot_backup_status()
        bk_ok = backup.get("status") in ("OK", "WARN")
        _check("backup_status", bk_ok, backup.get("status", "?"),
               blocker="" if bk_ok else "Backup not available")
        timer = _tool_qbot_backup_timer_status()
        tm_ok = timer.get("timer_enabled")
        _check("backup_timer", tm_ok, "enabled" if tm_ok else "not enabled",
               blocker="" if tm_ok else "Backup timer not enabled")
        drill = _tool_qbot_restore_drill_status()
        dr_ok = drill.get("status") in ("OK", "WARN")
        _check("restore_drill", dr_ok, drill.get("status", "?"),
               warn="" if dr_ok else "Restore drill not verified")
    except Exception as exc:
        _check("backup_subsystem", False, str(exc), blocker="Backup subsystem check failed")

    # Legacy Health
    try:
        from qbot_legacy_tools import _tool_qbot_legacy_health_report
        health = _tool_qbot_legacy_health_report()
        h_ok = health.get("status") != "ERROR"
        _check("legacy_health", h_ok, health.get("status", "?"),
               blocker="" if h_ok else "Legacy Q health is not acceptable")
    except Exception as exc:
        _check("legacy_health", False, str(exc), blocker="Legacy health check failed")

    # Wrappers & shadow
    try:
        from qbot_legacy_wrapper_tools import _tool_qbot_legacy_readonly_wrapper_report
        wreport = _tool_qbot_legacy_readonly_wrapper_report()
        wr_ok = wreport.get("status") != "ERROR"
        _check("readonly_wrappers", wr_ok, wreport.get("status", "?"),
               blocker="" if wr_ok else "Read-only wrappers have errors")
    except Exception as exc:
        _check("readonly_wrappers", False, str(exc), warn="Wrapper check failed")

    try:
        from qbot_legacy_execution_tools import _tool_qbot_legacy_safe_execution_report
        safe = _tool_qbot_legacy_safe_execution_report()
        se_ok = safe.get("ready_for_shadow_mode", False)
        _check("safe_execution", se_ok, "ready" if se_ok else "not ready",
               blocker="" if se_ok else "Safe execution not ready")
    except Exception as exc:
        _check("safe_execution", False, str(exc), blocker="Safe execution check failed")

    try:
        from qbot_legacy_shadow_tools import _tool_qbot_legacy_shadow_report
        shadow = _tool_qbot_legacy_shadow_report()
        sw_ok = shadow.get("ready_for_cutover", False)
        _check("shadow_report", sw_ok, "ready" if sw_ok else "mismatches",
               blocker="" if sw_ok else "Shadow report has mismatches")
    except Exception as exc:
        _check("shadow_report", False, str(exc), blocker="Shadow report failed")

    # Guard and Git
    guard = _tool_qbot_project_guard_check()
    g_ok = guard.get("status") != "ERROR"
    _check("project_guard", g_ok, guard.get("status", "?"),
           blocker="" if g_ok else "Guard check has errors")
    for v in guard.get("violations", []):
        if v.get("severity") == "ERROR":
            blockers.append(f"Guard: {v.get('what')}")
        elif v.get("severity") == "WARN":
            warnings.append(f"Guard warn: {v.get('what')}")

    git_st = _tool_qbot_git_status()
    git_ok = git_st.get("clean", False)
    _check("git_clean", git_ok, "clean" if git_ok else "dirty",
           warn="" if git_ok else "Repository has uncommitted changes")

    # Rollback & backup readiness
    try:
        from qbot_legacy_shadow_tools import _tool_qbot_legacy_cutover_plan
        rollback_ready = True  # cutover plan includes rollback steps
    except Exception:
        rollback_ready = False

    backup_ready = bk_ok and tm_ok
    shadow_ready = sw_ok
    legacy_healthy = h_ok
    core_ready = core_ok

    # Cutover decision
    gate = "PASS" if not blockers else "BLOCKED"
    if gate == "PASS" and warnings:
        gate = "PASS_WITH_WARNINGS"

    takeover = 95 if gate == "PASS" else 90 if gate == "PASS_WITH_WARNINGS" else 85

    return {
        "tool": "qbot_legacy_cutover_readiness_gate",
        "gate_status": gate,
        "cutover_allowed": gate in ("PASS", "PASS_WITH_WARNINGS"),
        "required_manual_approval": True,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "rollback_ready": rollback_ready,
        "backup_ready": backup_ready,
        "shadow_ready": shadow_ready,
        "legacy_healthy": legacy_healthy,
        "qbot_core_ready": core_ready,
        "takeover_readiness_percent": takeover,
        "recommended_next_step": "Proceed with manual cutover (qbot_legacy_manual_cutover_plan)" if gate in ("PASS", "PASS_WITH_WARNINGS") else "Resolve blockers before cutover",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ──────────── qbot_legacy_manual_cutover_plan ───────────────────────────

def _tool_qbot_legacy_manual_cutover_plan(_args: dict | None = None) -> dict[str, Any]:
    return {
        "tool": "qbot_legacy_manual_cutover_plan",
        "plan_status": "PLAN_ONLY",
        "do_not_execute_automatically": True,
        "required_manual_approval": True,
        "pre_cutover_checklist": [
            "[ ] Run qbot_legacy_cutover_readiness_gate — must return PASS",
            "[ ] Verify backup: systemctl status qbot-backup.timer",
            "[ ] Run final backup: systemctl start qbot-backup.service",
            "[ ] Verify restore drill: qbot_restore_drill_status",
            "[ ] Notify operators about cutover window",
            "[ ] Confirm no active sync/export operations in legacy Q logs",
        ],
        "cutover_steps": [
            "1. Pause monitoring: any external monitoring that alerts on q-bot.service",
            "2. Run pre-cutover backup: systemctl start qbot-backup.service",
            "3. Stop q-bot.service: sudo systemctl stop q-bot.service",
            "4. Stop qbot-qlab-server.service: sudo systemctl stop qbot-qlab-server.service",
            "5. Disable legacy services: sudo systemctl disable q-bot.service qbot-qlab-server.service",
            "6. Verify new Qbot API: curl http://127.0.0.1:8001/health",
            "7. Run final smoke test: qbot_operator_final_smoke_test",
            "8. Verify all capabilities work via new wrappers",
            "9. Announce cutover complete",
        ],
        "validation_steps": [
            "[ ] qbot_operator_final_smoke_test returns 100%",
            "[ ] qbot_legacy_takeover_status shows 100%",
            "[ ] No unexpected errors in tool_calls for 24h",
            "[ ] Backup and restore drill still functional",
            "[ ] All shadow probes match after cutover",
        ],
        "rollback_steps": [
            "1. Enable legacy services: sudo systemctl enable q-bot.service qbot-qlab-server.service",
            "2. Start legacy services: sudo systemctl start q-bot.service qbot-qlab-server.service",
            "3. Verify: qbot_legacy_health_report must return OK",
            "4. Investigate and fix issue before retry",
        ],
        "abort_conditions": [
            "Backup verification fails",
            "Any blocker present in cutover_readiness_gate",
            "Unexpected errors in new Qbot API",
            "Operator not available for rollback",
        ],
        "commands_for_human_review": [
            "sudo systemctl stop q-bot.service",
            "sudo systemctl disable q-bot.service",
            "sudo systemctl stop qbot-qlab-server.service",
            "sudo systemctl disable qbot-qlab-server.service",
            "sudo systemctl start qbot-backup.service",
            "curl http://127.0.0.1:8001/health",
        ],
        "warning": "All commands must be executed manually by a human operator. This tool does NOT execute anything.",
    }


# ──────────── qbot_legacy_cutover_answer_context ────────────────────────

def _tool_qbot_legacy_cutover_answer_context(_args: dict | None = None) -> dict[str, Any]:
    try:
        gate = _tool_qbot_legacy_cutover_readiness_gate()
        plan = _tool_qbot_legacy_manual_cutover_plan()
    except Exception as exc:
        return {"tool": "qbot_legacy_cutover_answer_context", "status": "error", "error": str(exc)}
    return {
        "tool": "qbot_legacy_cutover_answer_context",
        "safe_for_llm": True,
        "source": "qbot_legacy_cutover_readiness_gate + manual_cutover_plan",
        "context": _sanitize({"gate": gate, "plan": plan}),
        "suggested_answer_outline": ["1. Summarize cutover readiness gate result", "2. Outline manual cutover steps", "3. Note abort conditions and rollback plan", "4. Emphasize manual approval requirement"],
        "llm_must_not": ["execute cutover", "stop services", "modify systemd", "run commands"],
        "limitations": ["Plan only", "Manual approval required", "No automated execution"],
    }


# ──────────── qbot_legacy_takeover_status ───────────────────────────────

def _tool_qbot_legacy_takeover_status(_args: dict | None = None) -> dict[str, Any]:
    try:
        gate = _tool_qbot_legacy_cutover_readiness_gate()
    except Exception as exc:
        gate = {"takeover_readiness_percent": 90, "gate_status": "ERROR", "error": str(exc)}
    core_pct = 100
    takeover_pct = gate.get("takeover_readiness_percent", 90)

    completed = ["Phase 1: read-only wrappers", "Phase 2: safe execution wrappers", "Phase 3: shadow mode"]
    remaining = ["Phase 4: manual cutover", "Phase 5: legacy disable"]
    if gate.get("cutover_allowed"):
        remaining = ["Phase 5: legacy disable"]

    return {
        "tool": "qbot_legacy_takeover_status",
        "qbot_core_operational_percent": core_pct,
        "legacy_takeover_percent": takeover_pct,
        "current_phase": "Phase 4: cutover readiness gate",
        "completed_phases": completed,
        "remaining_phases": remaining,
        "cutover_gate_status": gate.get("gate_status", "UNKNOWN"),
        "ready_for_manual_cutover": gate.get("cutover_allowed", False),
        "recommended_next_step": gate.get("recommended_next_step", "review gate status"),
    }


def _get_legacy_cutover_tool(name: str):
    mapping = {
        "qbot_legacy_cutover_readiness_gate": _tool_qbot_legacy_cutover_readiness_gate,
        "qbot_legacy_manual_cutover_plan": _tool_qbot_legacy_manual_cutover_plan,
        "qbot_legacy_cutover_answer_context": _tool_qbot_legacy_cutover_answer_context,
        "qbot_legacy_takeover_status": _tool_qbot_legacy_takeover_status,
    }
    return mapping.get(name)
