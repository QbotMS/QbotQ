#!/usr/bin/env python3
"""Regenerate docs/CONTEXT.md from live repo and host signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
OUTPUT_PATH = DOCS_DIR / "CONTEXT.md"
SERVICE_UNITS = (
    "qbot-api",
    "qbot-mcp-bridge",
    "qbot-dev-mcp",
    "qbot-qlab-server",
)


@dataclass
class LiveSignals:
    branch: str = "unknown"
    head: str = "unknown"
    services: dict[str, str] | None = None


def run_cmd(args: list[str]) -> str:
    try:
        proc = subprocess.run(
            args,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return "unknown"
    if proc.returncode != 0:
        return "unknown"
    output = (proc.stdout or "").strip()
    return output if output else "unknown"


def get_git_branch() -> str:
    try:
        return run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    except Exception:
        return "unknown"


def get_git_head() -> str:
    try:
        return run_cmd(["git", "log", "-1", "--pretty=%h %s"])
    except Exception:
        return "unknown"


def get_service_state(unit: str) -> str:
    try:
        import shutil

        if shutil.which("systemctl") is None:
            return "unknown"
        result = subprocess.run(
            ["systemctl", "is-active", unit],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return "unknown"
        state = (result.stdout or "").strip()
        return state if state else "unknown"
    except Exception:
        return "unknown"


def get_timestamp() -> str:
    tz_note = ""
    now = None
    try:
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo("Europe/Warsaw"))
    except Exception:
        now = datetime.now(timezone.utc)
        tz_note = " (UTC fallback, zoneinfo niedostepne)"
    return now.strftime("%Y-%m-%d %H:%M:%S %Z") + tz_note


def build_document(signals: LiveSignals, timestamp: str) -> str:
    services = signals.services or {}
    return "\n".join(
        [
            "# QBot — Kontekst projektu (auto-generowany)",
            f"_Wygenerowano: {timestamp}. NIE edytuj recznie — plik tworzy scripts/build_context.py._",
            "## Zakres",
            "Pracujemy WYLACZNIE nad rdzeniem QBota (qbot-api, qbot-mcp, qbot-dev-mcp, qbot-qlab-server). QExt2 to OSOBNY projekt — nie mieszac.",
            "## Stan na zywo",
            f"- Branch: {signals.branch}",
            f"- HEAD: {signals.head}",
            "- Uslugi: "
            + ", ".join(f"{unit}={services.get(unit, 'unknown')}" for unit in SERVICE_UNITS),
            "## Architektura (skrot — kanon ponizej, ZAWSZE weryfikuj na zywo)",
            "- Publiczny kanal MCP jest swiadomie 2-narzedziowy: qbot.query (odczyt) oraz qbot.action_execute (jedyny executor zapisow). Narzedzia domenowe sa internal, dostepne tylko przez action_execute.",
            "- Aktywny handler MCP dla Claude: qbot3/adapters/mcp_adapter.py (handle_qbot3_mcp, QBOT3_ENABLED=1). app/qbot_mcp_adapter.py to ODDZIELNY adapter konektora ChatGPT — nie mylic.",
            "- Routing: Albert-first tylko dla domen zamknietych (zywienie, kalendarz, przypomnienia). Domena TRAS: Router v2 (qbot_query_handler.py) -> Planner v2 (core/planner.py), NIE Albert. Claude = synteza po stronie czatu.",
            "- Kanon (czytaj zamiast zgadywac): docs/architecture/QBOT_ARCHITEKTURA_V2.md oraz PROJECT_STATE.md (repo root). Gdy dokument rozjezdza sie z kodem — wygrywa zywy system.",
            "## Jak pracowac",
            "- Po polsku, bezposrednio, bez spekulacji. Brak danych → sprawdz przez DEV MCP, nie zgaduj.",
            "",
        ]
    )


def main() -> int:
    signals = LiveSignals()
    try:
        signals.branch = get_git_branch()
    except Exception:
        signals.branch = "unknown"
    try:
        signals.head = get_git_head()
    except Exception:
        signals.head = "unknown"
    try:
        signals.services = {unit: get_service_state(unit) for unit in SERVICE_UNITS}
    except Exception:
        signals.services = {unit: "unknown" for unit in SERVICE_UNITS}

    timestamp = get_timestamp()
    document = build_document(signals, timestamp)
    try:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(document, encoding="utf-8")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 0

    print("WROTE docs/CONTEXT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
