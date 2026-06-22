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
            "- Routing (Claude/MCP): qbot.query -> qbot3/adapters/mcp_adapter.py; przy QBOT_QUERY_VNEXT_ENABLED=1 najpierw qbot_query_handler.handle_query (deterministyczny, keyword/intent: domeny zamkniete zywienie/kalendarz/przypomnienia). UNRECOGNIZED -> ALBERT (qbot3.agent_runtime.orchestrate_query) = natywny tool-calling agent LLM, narzedzia z qbot3/tool_registry.py.",
            "- Domena TRAS: QBOT_ROUTES_VIA_ALBERT=1 => trasy obsluguje ALBERT, narzedzia: route_plan_analysis (analiza/podsumowanie ZAPLANOWANEJ trasy), route_profile_detail (SZCZEGOLOWY profil zaplanowanej trasy z ramek: nawierzchnia odcinkami + wysokosci po km + podjazdy) i ride_analysis (ocena WYKONANEJ jazdy/FIT). UWAGA: Planner v2 / core/planner.py dla tras NIE ISTNIEJE — wczesniejszy zapis byl bledny (kasowac przy edycji). Inne fronty (ChatGPT: qbot_mcp_adapter+qbot_query_router; Telegram) maja wlasny routing/rejestr.",
            "- Kanon (czytaj zamiast zgadywac): docs/architecture/QBOT_ARCHITEKTURA_V2.md oraz PROJECT_STATE.md (repo root). Gdy dokument rozjezdza sie z kodem — wygrywa zywy system.",
            "## Jak pracowac",
            "- Po polsku, bezposrednio, bez spekulacji. Brak danych → sprawdz przez DEV MCP, nie zgaduj.",
            "- OBOWIAZKOWO (twarda regula): kazda zmiana narzedzi (dodanie/zmiana/usuniecie w qbot3/tool_registry.py) LUB nowej domeny/intencji MUSI byc w TYM SAMYM kroku odzwierciedlona w prompcie Alberta (_SYSTEM w qbot3/llm/albert.py) — ktore narzedzie do czego i kiedy. Bez aktualnego promptu Albert nie wie ze narzedzie istnieje i myli intencje. Zmiana narzedzia bez aktualizacji promptu = NIEUKONCZONA. Opisy narzedzi trzymaj < 500 znakow (build_tools_spec obcina).",
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
