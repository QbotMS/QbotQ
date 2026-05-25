"""Legacy Q capability inventory — read-only file scanning and migration planning."""
from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qbot_tools import _tool_qbot_git_status, _tool_qbot_project_guard_check

_PROJECT_ROOT: Path = Path("/opt/qbot/app")
_SKIP_DIRS: set[str] = {".git", ".venv", "__pycache__", ".pytest_cache", "logs", "outgoing", "backups", "node_modules"}
_SKIP_FILES: set[str] = {".env.local", ".env", ".garmin_tokens.json", ".garmin_session.pkl"}
_MAX_FILE_SIZE: int = 300_000
_MAX_FILES: int = 300

_CATEGORY_MAP: dict[str, str] = {
    ".py": "python", ".sh": "shell", ".bash": "shell",
    ".yml": "config", ".yaml": "config", ".json": "config", ".toml": "config",
    ".env": "config", ".example": "config",
    ".md": "docs", ".rst": "docs", ".txt": "docs",
    ".service": "systemd", ".timer": "systemd",
    ".sql": "sql", ".dump": "sql",
    ".cfg": "config", ".ini": "config",
}


def _file_category(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _CATEGORY_MAP:
        return _CATEGORY_MAP[suffix]
    name = path.name.lower()
    if name in ("dockerfile", "makefile", "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
        return "config"
    return "other"


_CAPABILITY_KEYWORDS: dict[str, list[str]] = {
    "qlab": ["qlab", "q-lab", "qlab_server"],
    "report": ["report", "daily_report", "weekly", "ride_report", "status_report"],
    "ride": ["ride", "cycling", "bike", "route"],
    "gpx": ["gpx", ".gpx", "parse_gpx"],
    "fit": ["fit", ".fit", "fit_export", "fit_rewrite", "fit_parse"],
    "karoo": ["karoo", "hammerhead"],
    "qext": ["qext", "external", "q-external"],
    "backup": ["backup", "dump", "pg_dump", "restore"],
    "export": ["export", "sync", "push", "upload"],
    "sync": ["sync", "synchronize", "syncing"],
    "schedule": ["schedule", "cron", "timer", "scheduled", "daily", "periodic"],
    "email": ["email", "mail", "smtp", "send_mail"],
    "telegram": ["telegram", "bot", "chat"],
    "api": ["api", "endpoint", "routes", "router", "fastapi", "flask"],
    "service": ["service", "systemd", "daemon"],
    "status": ["status", "health", "monitor", "check"],
    "garmin": ["garmin", "garmin_connect", "garmin_auth"],
}


def _scan_file(path: Path) -> list[str]:
    """Return list of capability keywords found in file."""
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size > _MAX_FILE_SIZE:
        return []
    if path.name in _SKIP_FILES:
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    found: set[str] = set()
    cl = content.lower()
    for cap, keywords in _CAPABILITY_KEYWORDS.items():
        for kw in keywords:
            if kw in cl:
                found.add(cap)
                break
    return sorted(found)


# ──────────── qbot_legacy_file_inventory ────────────────────────────────

def _tool_qbot_legacy_file_inventory(_args: dict | None = None) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    try:
        for p in sorted(_PROJECT_ROOT.rglob("*")):
            if any(skip in p.parts for skip in _SKIP_DIRS):
                continue
            if p.name in _SKIP_FILES:
                continue
            if not p.is_file():
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            rel = p.relative_to(_PROJECT_ROOT).as_posix()
            files.append({
                "path": rel,
                "size_bytes": st.st_size,
                "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                "category": _file_category(p),
            })
            if len(files) >= _MAX_FILES:
                files.append({"path": "...", "size_bytes": -1, "modified_at": "truncated", "category": "truncated"})
                break
    except Exception as exc:
        return {"tool": "qbot_legacy_file_inventory", "status": "error", "error": str(exc)}

    return {
        "tool": "qbot_legacy_file_inventory",
        "root": str(_PROJECT_ROOT),
        "total_files": len(files),
        "files": files,
        "status": "OK",
    }


# ──────────── qbot_legacy_entrypoint_inventory ──────────────────────────

def _tool_qbot_legacy_entrypoint_inventory(_args: dict | None = None) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []

    try:
        proc = subprocess.run(
            ["systemctl", "show", "q-bot.service",
             "--property=ExecStart,WorkingDirectory,User"],
            capture_output=True, text=True, timeout=5,
        )
        props = {}
        for line in proc.stdout.strip().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                props[k] = v
        if props:
            candidates.append({
                "type": "systemd_service",
                "name": "q-bot.service",
                "exec_start": props.get("ExecStart", "unknown"),
                "working_directory": props.get("WorkingDirectory", "unknown"),
                "user": props.get("User", "unknown"),
                "confidence": "high",
            })
    except Exception:
        candidates.append({"type": "systemd_service", "name": "q-bot.service",
                          "exec_start": "unknown", "working_directory": "unknown",
                          "user": "unknown", "confidence": "low"})

    try:
        for p in sorted(_PROJECT_ROOT.rglob("*")):
            if any(skip in p.parts for skip in _SKIP_DIRS):
                continue
            if p.name in _SKIP_FILES:
                continue
            if not p.is_file():
                continue
            suffix = p.suffix.lower()
            name = p.name.lower()
            entry_type = None
            confidence = "medium"
            if suffix == ".py" and (name.startswith("qbot") or name.endswith("_server.py") or name in ("main.py", "app.py")):
                entry_type = "python_module"
                confidence = "high" if "main" in name else "medium"
            elif suffix == ".sh":
                entry_type = "shell_script"
                confidence = "medium"
            if entry_type:
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")[:200_000]
                except Exception:
                    content = ""
                has_shebang = "#!/" in content[:100] if suffix == ".sh" else False
                has_main = 'if __name__ == "__main__"' in content if suffix == ".py" else False
                rel = p.relative_to(_PROJECT_ROOT).as_posix()
                candidates.append({
                    "type": entry_type,
                    "path": rel,
                    "has_shebang": has_shebang,
                    "has_main_block": has_main,
                    "confidence": "high" if has_shebang else confidence,
                })
    except Exception as exc:
        candidates.append({"type": "error", "error": str(exc)})

    return {
        "tool": "qbot_legacy_entrypoint_inventory",
        "service_entrypoint": candidates[0] if candidates and candidates[0].get("type") == "systemd_service" else None,
        "candidate_entrypoints": candidates,
        "confidence": "medium",
        "notes": "Read-only scan; no entrypoints were executed",
        "status": "OK",
    }


# ──────────── qbot_legacy_capability_scan ───────────────────────────────

def _tool_qbot_legacy_capability_scan(_args: dict | None = None) -> dict[str, Any]:
    capabilities: dict[str, dict[str, Any]] = {}

    for p in sorted(_PROJECT_ROOT.rglob("*")):
        if any(skip in p.parts for skip in _SKIP_DIRS):
            continue
        if p.name in _SKIP_FILES:
            continue
        if not p.is_file():
            continue
        rel = p.relative_to(_PROJECT_ROOT).as_posix()
        try:
            found = _scan_file(p)
        except Exception:
            continue
        for cap in found:
            if cap not in capabilities:
                capabilities[cap] = {
                    "capability": cap,
                    "evidence": [],
                    "file_count": 0,
                }
            capabilities[cap]["file_count"] += 1
            if len(capabilities[cap]["evidence"]) < 5:
                capabilities[cap]["evidence"].append({
                    "file": rel,
                    "short_excerpt": f"keyword match: {cap}",
                })

    detected = list(capabilities.values())
    high_priority = ["qlab", "garmin", "sync", "export"]
    mid_priority = ["report", "ride", "schedule", "email", "telegram", "api"]
    low_priority = ["backup", "status", "fit", "gpx", "karoo", "qext", "service"]

    result = []
    for d in detected:
        cap = d["capability"]
        if cap in high_priority:
            priority = "high"
        elif cap in mid_priority:
            priority = "medium"
        else:
            priority = "low"
        result.append({**d, "migration_priority": priority,
                       "confidence": "high" if d["file_count"] >= 3 else "medium" if d["file_count"] >= 2 else "low"})
    result.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["migration_priority"]])

    return {
        "tool": "qbot_legacy_capability_scan",
        "detected_capabilities": result,
        "status": "OK",
    }


# ──────────── qbot_legacy_dependency_inventory ──────────────────────────

def _tool_qbot_legacy_dependency_inventory(_args: dict | None = None) -> dict[str, Any]:
    declared: list[str] = []
    req_path = _PROJECT_ROOT / "requirements.txt"
    if req_path.is_file():
        try:
            declared = [l.strip() for l in req_path.read_text().splitlines()
                        if l.strip() and not l.strip().startswith("#")]
        except Exception:
            pass

    pyproject = _PROJECT_ROOT / "pyproject.toml"
    if pyproject.is_file():
        try:
            declared.append(f"pyproject.toml: {pyproject.stat().st_size} bytes")
        except Exception:
            pass

    imports_detected: set[str] = set()
    systemd_deps: list[str] = ["qbot-api.service", "q-bot.service", "qbot-qlab-server.service", "postgresql.service"]
    external_services: list[str] = ["postgresql", "intervals.icu", "garmin connect", "hammerhead/karoo", "rwgps"]

    try:
        for p in sorted(_PROJECT_ROOT.rglob("*")):
            if any(skip in p.parts for skip in _SKIP_DIRS):
                continue
            if p.suffix.lower() != ".py":
                continue
            if p.name in _SKIP_FILES:
                continue
            try:
                sz = p.stat().st_size
            except OSError:
                continue
            if sz > _MAX_FILE_SIZE:
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for match in re.finditer(r"^\s*(?:import\s+([a-zA-Z_][\w.]*)|from\s+([a-zA-Z_][\w.]*)\s+import)", content, re.MULTILINE):
                mod = (match.group(1) or match.group(2) or "").split(".")[0]
                if mod and mod not in ("__future__", "os", "sys", "json", "re", "datetime", "typing", "pathlib", "subprocess"):
                    imports_detected.add(mod)
    except Exception:
        pass

    return {
        "tool": "qbot_legacy_dependency_inventory",
        "python_dependencies_declared": declared,
        "python_imports_detected": sorted(imports_detected),
        "systemd_dependencies": systemd_deps,
        "external_services_detected": external_services,
        "potential_risks": [
            "Garmin API key management (.garmin_tokens)",
            "Hammerhead authentication (.hammerhead_tokens)",
            "External API rate limits (Intervals.icu, RWGPS, Garmin)",
            "Systemd timer dependencies for scheduled tasks",
            "State files in /opt/qbot/app/state/",
            "Data files in /opt/qbot/app/data/ (garage.db, caches)",
        ],
        "status": "OK",
    }


# ──────────── qbot_legacy_migration_plan ────────────────────────────────

def _tool_qbot_legacy_migration_plan(_args: dict | None = None) -> dict[str, Any]:
    from qbot_legacy_tools import _tool_qbot_legacy_status

    legacy_status = {}
    try:
        legacy_status = _tool_qbot_legacy_status()
    except Exception as exc:
        legacy_status = {"status": "ERROR", "error": str(exc)}

    file_inv = _tool_qbot_legacy_file_inventory()
    entry_inv = _tool_qbot_legacy_entrypoint_inventory()
    cap_scan = _tool_qbot_legacy_capability_scan()
    dep_inv = _tool_qbot_legacy_dependency_inventory()
    guard = _tool_qbot_project_guard_check()
    git_st = _tool_qbot_git_status()

    caps = cap_scan.get("detected_capabilities", [])
    high_pri = [c for c in caps if c.get("migration_priority") == "high"]
    mid_pri = [c for c in caps if c.get("migration_priority") == "medium"]
    low_pri = [c for c in caps if c.get("migration_priority") == "low"]

    proposed_tools: list[str] = []
    for c in high_pri:
        proposed_tools.append(f"qbot_legacy_{c['capability']}_status")
    for c in mid_pri:
        proposed_tools.append(f"qbot_legacy_{c['capability']}_view")

    risks: list[str] = [
        *dep_inv.get("potential_risks", []),
        "Legacy Q uses MCP (Model Context Protocol) — may need adapter",
        "Data state files could be inconsistent during migration",
        "External APIs may have different auth mechanisms",
    ]

    blockers: list[str] = []
    if legacy_status.get("status") not in ("OK",):
        blockers.append("Legacy Q is not healthy — resolve before migration")
    gv = guard.get("violations", [])
    for v in gv:
        if v.get("severity") == "ERROR":
            blockers.append(f"Guard error: {v.get('what')}")

    mig_pct = 100
    if not blockers:
        mig_pct = 85 if len(high_pri) > 0 else 90
    else:
        mig_pct = max(0, 85 - len(blockers) * 10)

    return {
        "tool": "qbot_legacy_migration_plan",
        "current_legacy_status": legacy_status.get("status", "unknown"),
        "capabilities_to_migrate": len(caps),
        "proposed_new_tools": proposed_tools,
        "migration_phases": [
            {"phase": 1, "name": "read-only wrappers",
             "description": "Create qbot_legacy_*_status tools for each capability",
             "risk": "low"},
            {"phase": 2, "name": "safe execution wrappers",
             "description": "Add read-only execution wrappers behind allowlist",
             "risk": "medium"},
            {"phase": 3, "name": "shadow mode",
             "description": "Run new logic in parallel with legacy, compare outputs",
             "risk": "medium"},
            {"phase": 4, "name": "cutover",
             "description": "Gradually switch production tasks from legacy to new architecture",
             "risk": "high"},
            {"phase": 5, "name": "legacy disable",
             "description": "Stop q-bot.service after verification period",
             "risk": "high"},
        ],
        "risks": risks,
        "blockers": blockers,
        "recommended_next_step": f"Phase 1: create read-only wrappers for {len(high_pri)} high-priority capabilities" if high_pri else "No high-priority capabilities to migrate — focus on mid-priority",
        "migration_readiness_percent": mig_pct,
        "status": "OK" if not blockers else "WARN",
    }


# ──────────── qbot_legacy_inventory_answer_context ──────────────────────

_SENSITIVE_KEYS: set[str] = {"password", "secret", "token", "apikey", "api_key",
                               "pgpassword", "env", "credential", "auth"}


def _sanitize(obj: Any, depth: int = 0) -> Any:
    if depth > 3:
        return "<truncated>"
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            if any(s in str(k).lower() for s in _SENSITIVE_KEYS):
                result[k] = "<redacted>"
            elif isinstance(v, (dict, list)):
                result[k] = _sanitize(v, depth + 1)
            elif isinstance(v, str) and len(v) > 2000:
                result[k] = v[:2000] + "...<truncated>"
            else:
                result[k] = v
        return result
    elif isinstance(obj, list):
        return [_sanitize(v, depth + 1) if isinstance(v, (dict, list))
                else (v[:500] + "...<truncated>" if isinstance(v, str) and len(v) > 500 else v)
                for v in obj[:50]]
    return obj[:2000] + "...<truncated>" if isinstance(obj, str) and len(obj) > 2000 else obj


def _tool_qbot_legacy_inventory_answer_context(_args: dict | None = None) -> dict[str, Any]:
    try:
        raw = _tool_qbot_legacy_migration_plan()
    except Exception as exc:
        return {"tool": "qbot_legacy_inventory_answer_context", "status": "error",
                "error": f"failed to generate migration plan: {exc}"}

    return {
        "tool": "qbot_legacy_inventory_answer_context",
        "safe_for_llm": True,
        "source": "qbot_legacy_migration_plan",
        "context": _sanitize(raw),
        "suggested_answer_outline": [
            "1. Summarize legacy Q capabilities and status",
            "2. Outline migration phases (read-only → safe exec → shadow → cutover → disable)",
            "3. Note current migration readiness score",
            "4. Identify blockers and risks",
            "5. Recommend next action",
        ],
        "llm_must_not": [
            "execute legacy Q code",
            "modify legacy Q files",
            "restart q-bot.service",
            "access secrets or credentials",
            "perform database operations",
            "execute any migration step",
        ],
        "limitations": [
            "Read-only inventory and planning only",
            "No execution of legacy code",
            "No modification of production state",
            "Context sanitized — no secrets exposed",
        ],
    }


def _get_legacy_inventory_tool(name: str):
    mapping = {
        "qbot_legacy_file_inventory": _tool_qbot_legacy_file_inventory,
        "qbot_legacy_entrypoint_inventory": _tool_qbot_legacy_entrypoint_inventory,
        "qbot_legacy_capability_scan": _tool_qbot_legacy_capability_scan,
        "qbot_legacy_dependency_inventory": _tool_qbot_legacy_dependency_inventory,
        "qbot_legacy_migration_plan": _tool_qbot_legacy_migration_plan,
        "qbot_legacy_inventory_answer_context": _tool_qbot_legacy_inventory_answer_context,
    }
    return mapping.get(name)
