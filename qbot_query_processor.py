"""Bezpieczny procesor zapytań z planami wykonania (Tool Execution Plan v1)."""
from __future__ import annotations

import re
from typing import Any

from qbot_tool_registry import TOOLS

_SAFE_MULTI_EXECUTE_TOOLS: set[str] = {
    "qbot_api_self_check",
    "qbot_git_status",
    "qbot_project_guard_check",
    "qbot_services_status",
    "qbot_db_overview",
    "qbot_system_overview",
    "qbot_project_diff_summary",
    "qbot_project_recent_commits",
    "qbot_recent_tool_calls",
    "qbot_api_tools_list",
    "qbot_operator_runbook",
    "qbot_rwgps_legacy_status",
    "qbot_rwgps_config_status",
    "qbot_rwgps_artifact_store_status",
    "qbot_rwgps_route_list",
    "qbot_rwgps_route_search",
    "qbot_rwgps_route_get",
    "qbot_rwgps_route_export_links",
    "qbot_rwgps_route_export_file",
    "qbot_gpx_artifact_parse",
    "qbot_route_artifact_enrich",
    "qbot_hammerhead_import_status",
    "qbot_hammerhead_import_inventory",
    "qbot_csv_export_status",
    "qbot_csv_export_inventory",
    "qbot_csv_export_latest_get",
    "qbot_xert_readiness_status",
    "qbot_xert_config_status",
    "qbot_intervals_wellness_status",
    "qbot_intervals_config_status",
    "qbot_garmin_config_status",
    "qbot_garmin_upload_dry_run",
    "qbot_cronometer_legacy_status",
    "qbot_weather_config_status",
    "qbot_openmaps_legacy_status",
    "qbot_garage_raw_status",
    "qbot_garage_raw_list",
    "qbot_daily_report_status",
    "qbot_ride_report_status",
    "qbot_roadmap_runner_status",
    "qbot_roadmap_runner_list_tasks",
    "qbot_roadmap_runner_next_task",
    "qbot_assistant_inbox_status",
    "qbot_assistant_inbox_list",
}

_RUNBOOKS: list[dict[str, Any]] = [
    {
        "name": "qbot_full_overview",
        "keywords": ["pełny przegląd", "full overview", "sprawdź wszystko", "kompletny status"],
        "tools": [
            ("qbot_api_self_check", {}),
            ("qbot_system_overview", {}),
            ("qbot_db_overview", {}),
            ("qbot_git_status", {}),
            ("qbot_project_guard_check", {}),
        ],
        "description": "Full system overview — API self-check, system resources, database status, git state, guard violations",
        "required_data": ["API health", "systemd services", "PostgreSQL connection", "git repository", "guard rules"],
        "limitations": ["Read-only diagnostic", "Local services only", "No external API checks"],
    },
    {
        "name": "qbot_safe_to_work",
        "keywords": ["czy można działać", "czy bezpiecznie działać", "safe to work", "czy repo jest gotowe"],
        "tools": [
            ("qbot_project_guard_check", {}),
            ("qbot_git_status", {}),
            ("qbot_api_self_check", {}),
        ],
        "description": "Check if environment is safe to work — guard rules, git state, API health",
        "required_data": ["guard rules", "git repository", "API health"],
        "limitations": ["Checks local state only", "Does not verify remote branches", "No resource usage check"],
    },
    {
        "name": "qbot_recent_errors",
        "keywords": ["pokaż błędy", "recent errors"],
        "tools": [
            ("qbot_recent_tool_calls", {"limit": 20}),
            ("qbot_db_overview", {}),
        ],
        "description": "Show recent errors — recent tool calls with error inference, database overview",
        "required_data": ["PostgreSQL tool_calls table"],
        "limitations": [
            "Recent errors are inferred from recent tool_calls; dedicated error filter not implemented yet",
            "Requires database connection",
        ],
    },
    {
        "name": "qbot_project_status",
        "keywords": ["stan projektu", "project status", "co w projekcie", "status projektu"],
        "tools": [
            ("qbot_git_status", {}),
            ("qbot_project_diff_summary", {}),
            ("qbot_project_recent_commits", {}),
            ("qbot_project_guard_check", {}),
        ],
        "description": "Project status overview — git state, working changes, recent commits, guard check",
        "required_data": ["git repository at /opt/qbot/app"],
        "limitations": ["Local repo only", "Summary diffs", "Max 30 commits"],
    },
    {
        "name": "qbot_api_status",
        "keywords": ["stan api", "api status", "czy api działa", "status qbot api"],
        "tools": [
            ("qbot_api_self_check", {}),
            ("qbot_services_status", {}),
            ("qbot_db_overview", {}),
            ("qbot_recent_tool_calls", {}),
        ],
        "description": "API status overview — self-check, services, database, recent tool calls",
        "required_data": ["API health", "systemd services", "PostgreSQL"],
        "limitations": ["Internal diagnostics only", "No load metrics", "No external API validation"],
    },
    {
        "name": "qbot_operator_full_diagnostic",
        "keywords": ["pełna diagnostyka operatora", "operator full diagnostic"],
        "tools": [
            ("qbot_operator_runbook", {"name": "full_diagnostic", "execute": False}),
        ],
        "description": "Full operator diagnostic — runs full_diagnostic operator runbook",
        "required_data": ["API health", "systemd services", "PostgreSQL", "git repository", "guard rules"],
        "limitations": ["Delegates to qbot_operator_runbook", "Preview only by default"],
    },
    {
        "name": "mcp_connector_review",
        "keywords": ["mcp connector review", "review mcp connector", "sprawdź mcp connector", "mcp adapter review"],
        "tools": [
            ("qbot_operator_runbook", {"name": "mcp_connector_review", "execute": False}),
        ],
        "description": "MCP connector review — preview/execution of the public /mcp adapter runbook",
        "required_data": ["MCP adapter status", "MCP tool list", "final smoke test", "project guard"],
        "limitations": ["Delegates to qbot_operator_runbook", "Preview only by default"],
    },
    {
        "name": "legacy_full_parity_review",
        "keywords": ["legacy full parity review", "full parity audit", "legacy parity review", "pełny audyt legacy"],
        "tools": [
            ("qbot_operator_runbook", {"name": "legacy_full_parity_review", "execute": False}),
        ],
        "description": "Legacy full parity review — broad audit across all historical QBot capabilities",
        "required_data": ["legacy parity audit", "parity matrix", "weather", "garage/gate", "artifacts", "telegram/mcp", "backup", "routes"],
        "limitations": ["Delegates to qbot_operator_runbook", "Preview only by default"],
    },
    {
        "name": "legacy_parity_fix_review",
        "keywords": ["parity fix review", "przegląd parity", "sprawdź rwgps hammerhead csv", "legacy parity fix"],
        "tools": [
            ("qbot_rwgps_legacy_status", {}),
            ("qbot_rwgps_restore_plan", {}),
            ("qbot_hammerhead_import_status", {}),
            ("qbot_hammerhead_restore_plan", {}),
            ("qbot_csv_export_status", {}),
            ("qbot_operator_final_smoke_test", {}),
        ],
        "description": "Legacy parity fix review — RWGPS, Hammerhead, CSV Export status",
        "required_data": ["RWGPS config", "Hammerhead config", "CSV inventory", "operational smoke test"],
        "limitations": ["Read-only review", "No secrets exposed"],
    },
]

_INTENT_MAP: list[dict[str, Any]] = [
    {
        "keywords": ["stan q", "status q", "self check", "czy działa", "sprawdź wszystko",
                      "czy wszystko ok", "status", "sprawdź stan"],
        "tool": "qbot_api_self_check",
        "args": {},
        "confidence": "high",
        "required_data": ["API health endpoint", "PostgreSQL connection", "systemd service status", "git repository state"],
        "limitations": ["Only checks local services", "Does not check external APIs like Intervals.icu or Garmin"],
    },
    {
        "keywords": ["mcp status", "czy mcp działa", "status mcp", "sprawdź mcp"],
        "tool": "qbot_mcp_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Local API health", "public /mcp route", "MCP auth mode"],
        "limitations": ["Read-only status", "No tool execution"],
    },
    {
        "keywords": ["mcp tools", "lista narzędzi mcp", "narzędzia mcp"],
        "tool": "qbot_mcp_tools_list",
        "args": {},
        "confidence": "high",
        "required_data": ["MCP adapter metadata"],
        "limitations": ["Static tool mapping", "Read-only"],
    },
    {
        "keywords": ["roadmap runner status", "runner status", "roadmap status", "status runnera", "status roadmap runnera"],
        "tool": "qbot_roadmap_runner_status",
        "args": {},
        "confidence": "high",
        "required_data": ["roadmap runner state", "assistant inbox"],
        "limitations": ["Read-only status", "No task execution"],
    },
    {
        "keywords": ["next roadmap task", "następny task", "next task roadmapy", "następny task roadmapy"],
        "tool": "qbot_roadmap_runner_next_task",
        "args": {},
        "confidence": "high",
        "required_data": ["roadmap parser", "roadmap state"],
        "limitations": ["Read-only planning", "No execution"],
    },
    {
        "keywords": ["roadmap tasks", "lista tasków roadmapy", "taski roadmapy", "list tasks roadmap", "lista tasków runnera"],
        "tool": "qbot_roadmap_runner_list_tasks",
        "args": {},
        "confidence": "high",
        "required_data": ["roadmap parser"],
        "limitations": ["Read-only", "No execution"],
    },
    {
        "keywords": ["assistant inbox status", "inbox status", "status inbox", "assistant inbox"],
        "tool": "qbot_assistant_inbox_status",
        "args": {},
        "confidence": "high",
        "required_data": ["local inbox state file"],
        "limitations": ["Read-only", "No modification"],
    },
    {
        "keywords": ["inbox list", "lista inbox", "pokaż inbox", "show inbox"],
        "tool": "qbot_assistant_inbox_list",
        "args": {"limit": 20},
        "confidence": "high",
        "required_data": ["local inbox state file"],
        "limitations": ["Read-only", "No modification"],
    },
    {
        "keywords": ["pogoda legacy", "openweathermap", "weather legacy", "weather status"],
        "tool": "qbot_weather_legacy_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Legacy weather/OpenWeatherMap code scan", "current weather path"],
        "limitations": ["Read-only audit", "No external weather API calls"],
    },
    {
        "keywords": ["weather current", "current weather", "pogoda teraz", "teraz pogoda"],
        "tool": "qbot_weather_current",
        "args": {},
        "confidence": "high",
        "required_data": ["Current read-only weather path"],
        "limitations": ["Read-only", "No external API keys exposed"],
    },
    {
        "keywords": [
            "weather forecast", "forecast weather", "prognoza pogody", "prognoza",
            "jutrzejsza pogoda", "jutrzejszy", "jutro", "na jutro", "tomorrow",
            "pogoda na jutro", "prognoza na jutro",
        ],
        "tool": "qbot_weather_forecast",
        "args": {},
        "confidence": "high",
        "required_data": ["Current read-only weather path"],
        "limitations": ["Read-only", "No external API keys exposed"],
    },
    {
        "keywords": ["garaż legacy", "garaz legacy", "brama legacy", "garage status", "gate legacy"],
        "tool": "qbot_garage_legacy_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Legacy garage/gate/home automation code scan"],
        "limitations": ["Read-only audit", "No garage/gate execution"],
    },
    {
        "keywords": ["artifacts legacy", "kontener artefaktów", "kontener artefaktow", "artifacts container", "artifact bridge"],
        "tool": "qbot_artifacts_legacy_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Filesystem artifacts", "PostgreSQL qbot_artifacts", "workspace roots"],
        "limitations": ["Read-only audit", "No file writes"],
    },
    {
        "keywords": ["artifacts inventory", "filesystem artifacts inventory", "inventory artifacts", "lista artefaktów"],
        "tool": "qbot_artifacts_filesystem_inventory",
        "args": {},
        "confidence": "high",
        "required_data": ["Filesystem root /opt/qbot/artifacts"],
        "limitations": ["Read-only inventory", "No file writes"],
    },
    {
        "keywords": ["artifact import preview", "preview import artefaktu", "import file preview"],
        "tool": "qbot_artifact_import_from_file_preview",
        "args": {},
        "confidence": "medium",
        "required_data": ["Filesystem root /opt/qbot/artifacts"],
        "limitations": ["Preview only", "No write"],
    },
    {
        "keywords": ["artifact export preview", "preview export artefaktu"],
        "tool": "qbot_artifact_export_preview",
        "args": {},
        "confidence": "medium",
        "required_data": ["PostgreSQL qbot_artifacts"],
        "limitations": ["Preview only", "No write"],
    },
    {
        "keywords": ["wszystkie integracje", "external integrations", "all integrations", "integracje zewnętrzne"],
        "tool": "qbot_external_integrations_report",
        "args": {},
        "confidence": "high",
        "required_data": ["Weather", "garage/home automation", "artifacts", "telegram", "MCP", "email/webhooks"],
        "limitations": ["Read-only audit", "No secret exposure"],
    },
    {
        "keywords": ["legacy parity matrix", "macierz parity", "parity matrix"],
        "tool": "qbot_legacy_parity_matrix",
        "args": {},
        "confidence": "high",
        "required_data": ["Legacy parity matrix metadata"],
        "limitations": ["Read-only matrix", "No legacy actions"],
    },
    {
        "keywords": ["legacy full parity audit", "pełny audyt legacy", "full parity audit", "all legacy services"],
        "tool": "qbot_legacy_full_parity_audit",
        "args": {},
        "confidence": "high",
        "required_data": ["Legacy parity matrix", "service inventories", "public endpoints"],
        "limitations": ["Read-only audit", "No legacy actions"],
    },
    {
        "keywords": ["usługi", "services", "systemd", "czy działa q-bot",
                      "czy działa qlab", "status usług", "service status"],
        "tool": "qbot_services_status",
        "args": {},
        "confidence": "high",
        "required_data": ["systemd service status for 4 services"],
        "limitations": ["Only checks Q-related services", "Does not report resource usage"],
    },
    {
        "keywords": ["ostatnie wywołania", "tool calls", "historia narzędzi",
                      "logi narzędzi", "recent calls", "ostatnie zapytania",
                      "historia", "logi"],
        "tool": "qbot_recent_tool_calls",
        "args": {"limit": 10},
        "confidence": "medium",
        "required_data": ["PostgreSQL tool_calls table"],
        "limitations": ["Returns at most 50 entries", "Requires database connection"],
    },
    {
        "keywords": ["repo", "git", "czy repo czyste", "status git",
                      "git status", "repo czyste", "branch", "commit"],
        "tool": "qbot_git_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Git repository at /opt/qbot/app"],
        "limitations": ["Only checks local repo", "Requires git safe.directory config for qbot user"],
    },
    {
        "keywords": ["narzędzia", "lista tools", "co umiesz", "available tools",
                      "lista narzędzi", "jakie narzędzia", "co potrafisz",
                      "dostępne", "tools list", "help"],
        "tool": "qbot_api_tools_list",
        "args": {},
        "confidence": "high",
        "required_data": ["Tool registry metadata"],
        "limitations": ["Static listing only", "Does not include detailed usage examples"],
    },
    {
        "keywords": ["baza", "postgres", "db", "tool_calls count",
                      "baza danych", "postgresql", "ile wpisów",
                      "database", "db overview"],
        "tool": "qbot_db_overview",
        "args": {},
        "confidence": "high",
        "required_data": ["PostgreSQL connection", "tool_calls table"],
        "limitations": ["Only reports tool_calls stats", "Does not show raw query results"],
    },
    {
        "keywords": ["system", "vps", "ram", "dysk", "load", "uptime",
                      "serwer", "pamięć", "procesor", "cpu",
                      "system overview", "zasoby"],
        "tool": "qbot_system_overview",
        "args": {},
        "confidence": "high",
        "required_data": ["/proc/uptime", "/proc/loadavg", "/proc/meminfo", "df output", "systemd status"],
        "limitations": ["Read-only OS metrics", "No per-process detail", "No network I/O stats"],
    },
    {
        "keywords": ["projekt", "drzewo", "struktura projektu",
                      "struktura katalogów", "drzewo katalogów",
                      "project tree", "katalogi"],
        "tool": "qbot_project_tree",
        "args": {"max_depth": 2},
        "confidence": "medium",
        "required_data": ["Filesystem at /opt/qbot/app"],
        "limitations": ["Max depth 4", "Skips .git, .venv, __pycache__, logs, outgoing", "Does not read file contents"],
    },
    {
        "keywords": ["pliki projektu", "lista plików", "pliki",
                      "project files", "wszystkie pliki"],
        "tool": "qbot_project_files",
        "args": {},
        "confidence": "medium",
        "required_data": ["Filesystem at /opt/qbot/app"],
        "limitations": ["Max 200 files", "Skips .git, .venv, __pycache__, logs, outgoing", "Does not read file contents"],
    },
    {
        "keywords": ["commity", "ostatnie commity", "git log",
                      "historia commitów", "recent commits"],
        "tool": "qbot_project_recent_commits",
        "args": {"limit": 10},
        "confidence": "high",
        "required_data": ["Git repository at /opt/qbot/app"],
        "limitations": ["Max 30 commits", "Short format only (%h %s)"],
    },
    {
        "keywords": ["diff", "zmiany", "co zmienione", "zmodyfikowane",
                      "niezapisane", "working changes"],
        "tool": "qbot_project_diff_summary",
        "args": {},
        "confidence": "high",
        "required_data": ["Git repository at /opt/qbot/app"],
        "limitations": ["Summary only (--stat, --name-only)", "Does not return full diff content"],
    },
    {
        "keywords": ["guard", "naruszenia", "czy bezpiecznie",
                      "sprawdź zasady", "bezpieczeństwo", "guard check",
                      "czy jest bezpiecznie", "security"],
        "tool": "qbot_project_guard_check",
        "args": {},
        "confidence": "high",
        "required_data": ["Git repository state", "systemd service config", "ss listening ports"],
        "limitations": ["Only checks predefined rules", "Does not scan for CVEs or vulnerabilities"],
    },
    {
        "keywords": ["ostatnie błędy", "error summary", "co się wywaliło"],
        "tool": "qbot_error_summary",
        "args": {"limit": 50},
        "confidence": "high",
        "required_data": ["PostgreSQL tool_calls table"],
        "limitations": ["Recent errors inferred from tool_calls; dedicated error filter not implemented yet", "Requires database connection"],
    },
    {
        "keywords": ["użycie narzędzi", "statystyki tools", "tool usage",
                      "użycie tools"],
        "tool": "qbot_tool_usage_summary",
        "args": {"limit": 200},
        "confidence": "high",
        "required_data": ["PostgreSQL tool_calls table"],
        "limitations": ["Statistical summary only", "Requires database connection"],
    },
    {
        "keywords": ["czy qbot jest gotowy", "readiness", "gotowość"],
        "tool": "qbot_readiness_report",
        "args": {},
        "confidence": "high",
        "required_data": ["API health", "systemd services", "PostgreSQL", "git repository", "guard rules"],
        "limitations": ["Local checks only", "Does not verify external dependencies"],
    },
    {
        "keywords": ["ride readiness", "qext2 readiness", "karoo readiness", "ride-readiness"],
        "tool": "qbot_ride_readiness_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Readiness report", "final smoke test", "legacy takeover", "telegram", "mcp"],
        "limitations": ["Read-only public readiness endpoint", "No MCP or Telegram reconfiguration"],
    },
    {
        "keywords": ["snapshot", "zrzut diagnostyczny", "operator snapshot",
                      "diagnostic snapshot"],
        "tool": "qbot_operator_snapshot",
        "args": {"include_recent_calls": True, "recent_limit": 20},
        "confidence": "high",
        "required_data": ["API health", "system resources", "PostgreSQL", "git repository", "guard rules"],
        "limitations": ["Read-only snapshot", "Large response — use with caution", "No persistent storage"],
    },
    {
        "keywords": ["pokaż logi", "logi api", "journal", "systemd logs",
                      "przegląd logów"],
        "tool": "qbot_logs_overview",
        "args": {"lines": 40},
        "confidence": "high",
        "required_data": ["journalctl access for allowed services"],
        "limitations": ["Allowed services only", "Max 300 lines per service", "Lines truncated to 1000 chars"],
    },
    {
        "keywords": ["backup", "status backupu", "czy backup działa"],
        "tool": "qbot_backup_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Filesystem: /opt/qbot/backups, /var/backups/qbot"],
        "limitations": ["Read-only check", "Does not execute backup", "Limited to allowed directories"],
    },
    {
        "keywords": ["plan backupu", "jak zrobić backup", "backup plan"],
        "tool": "qbot_backup_plan",
        "args": {},
        "confidence": "high",
        "required_data": ["None"],
        "limitations": ["Returns plan text only", "Does not execute any commands"],
    },
    {
        "keywords": ["skrypt backupu", "backup script"],
        "tool": "qbot_create_backup_script_preview",
        "args": {},
        "confidence": "high",
        "required_data": ["None"],
        "limitations": ["Preview only", "Does not write files", "Does not execute backup"],
    },
    {
        "keywords": ["testowe błędy", "czy błędy są z testów"],
        "tool": "qbot_test_error_classification",
        "args": {"limit": 200},
        "confidence": "high",
        "required_data": ["PostgreSQL tool_calls table"],
        "limitations": ["Based on pattern matching — may misclassify", "Requires database connection"],
    },
    {
        "keywords": ["maintenance", "raport utrzymania", "raport operatorski"],
        "tool": "qbot_maintenance_report",
        "args": {},
        "confidence": "high",
        "required_data": ["API health", "PostgreSQL", "git", "guard", "backup", "logs"],
        "limitations": ["Read-only composite report", "Large response", "Aggregates multiple tools"],
    },
    {
        "keywords": ["timer backupu", "backup timer", "automatyczny backup"],
        "tool": "qbot_backup_timer_status",
        "args": {},
        "confidence": "high",
        "required_data": ["systemd qbot-backup.timer"],
        "limitations": ["Read-only systemd check", "Only checks qbot-backup timer"],
    },
    {
        "keywords": ["restore drill", "test restore", "test odtworzenia"],
        "tool": "qbot_restore_drill_status",
        "args": {},
        "confidence": "high",
        "required_data": ["PostgreSQL qbot_restore_drill database"],
        "limitations": ["Read-only", "Checks drill DB only", "Does not execute restore"],
    },
    {
        "keywords": ["plan restore", "jak odtworzyć backup"],
        "tool": "qbot_restore_drill_plan",
        "args": {},
        "confidence": "high",
        "required_data": ["None"],
        "limitations": ["Returns plan text only", "Does not execute any commands"],
    },
    {
        "keywords": ["ściąga operatora", "operator reference", "co mam sprawdzać"],
        "tool": "qbot_operator_quick_reference",
        "args": {},
        "confidence": "high",
        "required_data": ["None"],
        "limitations": ["Static reference only", "Does not read secrets"],
    },
    {
        "keywords": ["czy qbot jest w pełni gotowy"],
        "tool": "qbot_readiness_report",
        "args": {},
        "confidence": "high",
        "required_data": ["API health", "systemd services", "PostgreSQL", "git", "guard", "backup"],
        "limitations": ["Local checks only", "Does not verify external dependencies"],
    },
    {
        "keywords": ["czy qbot jest gotowy finalnie", "final smoke test",
                      "pełny test końcowy"],
        "tool": "qbot_operator_final_smoke_test",
        "args": {},
        "confidence": "high",
        "required_data": ["All operator subsystems"],
        "limitations": ["Read-only final check", "Reports operational readiness %", "No actions taken"],
    },
    {
        "keywords": ["kontekst dla llm", "answer context", "przygotuj odpowiedź"],
        "tool": "qbot_answer_context",
        "args": {"source_tool": "qbot_readiness_report", "source_args": {}},
        "confidence": "high",
        "required_data": ["Readiness report data"],
        "limitations": ["Sanitizes data for LLM", "Removes secrets", "No LLM call", "Truncates large fields"],
    },
    {
        "keywords": ["polityka llm", "llm boundary", "zasady llm"],
        "tool": "qbot_llm_boundary_policy",
        "args": {},
        "confidence": "high",
        "required_data": ["None"],
        "limitations": ["Static policy document", "Educational only"],
    },
    {
        "keywords": ["stan starego q", "legacy status", "czy stary q działa"],
        "tool": "qbot_legacy_status",
        "args": {},
        "confidence": "high",
        "required_data": ["systemd q-bot.service"],
        "limitations": ["Read-only systemd check", "Only q-bot.service"],
    },
    {
        "keywords": ["logi starego q", "legacy logs", "logi q-bot"],
        "tool": "qbot_legacy_logs",
        "args": {"lines": 120},
        "confidence": "high",
        "required_data": ["journalctl for q-bot.service"],
        "limitations": ["Only q-bot.service", "Max 300 lines", "Read-only"],
    },
    {
        "keywords": ["błędy starego q", "legacy errors", "co się wywala w starym q"],
        "tool": "qbot_legacy_error_summary",
        "args": {"lines": 300},
        "confidence": "high",
        "required_data": ["journalctl for q-bot.service"],
        "limitations": ["Only q-bot.service", "Pattern matching only", "Read-only"],
    },
    {
        "keywords": ["raport starego q", "legacy health", "sprawdź starego q"],
        "tool": "qbot_legacy_health_report",
        "args": {},
        "confidence": "high",
        "required_data": ["systemd q-bot.service", "guard check", "services status"],
        "limitations": ["Read-only diagnostic", "No restarts or modifications"],
    },
    {
        "keywords": ["co robi stary q", "capability scan", "funkcje starego q"],
        "tool": "qbot_legacy_capability_scan",
        "args": {},
        "confidence": "high",
        "required_data": ["Filesystem at /opt/qbot/app"],
        "limitations": ["Static scanning only", "No code execution", "No secret reading"],
    },
    {
        "keywords": ["entrypointy starego q", "jak startuje stary q"],
        "tool": "qbot_legacy_entrypoint_inventory",
        "args": {},
        "confidence": "high",
        "required_data": ["systemd q-bot.service", "Filesystem at /opt/qbot/app"],
        "limitations": ["Read-only", "No execution of detected entrypoints"],
    },
    {
        "keywords": ["pliki starego q", "inventory starego q"],
        "tool": "qbot_legacy_file_inventory",
        "args": {},
        "confidence": "high",
        "required_data": ["Filesystem at /opt/qbot/app"],
        "limitations": ["Max 300 files", "Skips secrets and .env", "Read-only"],
    },
    {
        "keywords": ["zależności starego q", "dependency inventory"],
        "tool": "qbot_legacy_dependency_inventory",
        "args": {},
        "confidence": "high",
        "required_data": ["requirements.txt", "Python files", "systemd services"],
        "limitations": ["Static analysis", "No pip execution"],
    },
    {
        "keywords": ["plan migracji starego q", "jak przejąć starego q", "legacy migration plan"],
        "tool": "qbot_legacy_migration_plan",
        "args": {},
        "confidence": "high",
        "required_data": ["All legacy inventory tools", "Guard check", "Git status"],
        "limitations": ["Plan only — no migration steps executed", "Read-only"],
    },
    {
        "keywords": ["status export", "legacy export", "sprawdź export"],
        "tool": "qbot_legacy_export_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Filesystem at /opt/qbot/app"],
        "limitations": ["Read-only diagnostic", "No export execution"],
    },
    {
        "keywords": ["status garmin", "legacy garmin", "sprawdź garmin"],
        "tool": "qbot_legacy_garmin_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Filesystem at /opt/qbot/app"],
        "limitations": ["Read-only diagnostic", "No Garmin API calls"],
    },
    {
        "keywords": ["garmin proxy status", "status garmin proxy", "garmin proxy"],
        "tool": "qbot_garmin_proxy_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Legacy Garmin proxy and sync artifacts"],
        "limitations": ["Read-only diagnostic", "No Garmin API calls"],
    },
    {
        "keywords": ["garmin upload status", "status garmin upload", "upload garmin"],
        "tool": "qbot_garmin_upload_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Legacy Garmin upload code and artifacts"],
        "limitations": ["Read-only diagnostic", "No upload execution"],
    },
    {
        "keywords": ["hammerhead import status", "status hammerhead import", "karoo import status", "hammerhead legacy"],
        "tool": "qbot_hammerhead_import_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Hammerhead sync script and artifacts"],
        "limitations": ["Read-only diagnostic", "No import execution"],
    },
    {
        "keywords": ["status qlab", "legacy qlab", "sprawdź qlab"],
        "tool": "qbot_legacy_qlab_status",
        "args": {},
        "confidence": "high",
        "required_data": ["systemd qbot-qlab-server.service", "Filesystem"],
        "limitations": ["Read-only diagnostic", "No code modifications"],
    },
    {
        "keywords": ["status sync", "legacy sync", "sprawdź sync"],
        "tool": "qbot_legacy_sync_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Filesystem at /opt/qbot/app"],
        "limitations": ["Read-only diagnostic", "No synchronization"],
    },
    {
        "keywords": ["read only wrappers", "wrapper report", "raport wrapperów"],
        "tool": "qbot_legacy_readonly_wrapper_report",
        "args": {},
        "confidence": "high",
        "required_data": ["All 4 capability wrappers"],
        "limitations": ["Read-only composite report", "No legacy actions"],
    },
    {
        "keywords": ["qlab smoke", "sprawdź qlab lokalnie", "qlab smoke check"],
        "tool": "qbot_legacy_qlab_smoke_check",
        "args": {},
        "confidence": "high",
        "required_data": ["systemd qbot-qlab-server.service", "local HTTP to 127.0.0.1:8000"],
        "limitations": ["Local only", "Read-only endpoints", "No data sent"],
    },
    {
        "keywords": ["export dry run", "dry run export", "sprawdź export dry run"],
        "tool": "qbot_legacy_export_dry_run",
        "args": {},
        "confidence": "high",
        "required_data": ["Filesystem at /opt/qbot/app", "Export status wrapper"],
        "limitations": ["Dry-run only", "No export created", "No files written"],
    },
    {
        "keywords": ["sync dry run", "dry run sync"],
        "tool": "qbot_legacy_sync_dry_run",
        "args": {},
        "confidence": "high",
        "required_data": ["Filesystem at /opt/qbot/app", "Sync status wrapper"],
        "limitations": ["Dry-run only", "No sync executed", "No network calls"],
    },
    {
        "keywords": ["garmin dry run", "dry run garmin"],
        "tool": "qbot_legacy_garmin_dry_run",
        "args": {},
        "confidence": "high",
        "required_data": ["Filesystem at /opt/qbot/app", "Garmin status wrapper"],
        "limitations": ["Dry-run only", "No Garmin API calls", "No tokens used"],
    },
    {
        "keywords": ["safe execution report", "raport safe execution", "phase 2 report"],
        "tool": "qbot_legacy_safe_execution_report",
        "args": {},
        "confidence": "high",
        "required_data": ["Smoke check", "Dry-run reports", "Guard check"],
        "limitations": ["Phase 2 report only", "No real execution"],
    },
    {
        "keywords": ["shadow report", "porównaj nowe i stare q", "shadow mode"],
        "tool": "qbot_legacy_shadow_report",
        "args": {},
        "confidence": "high",
        "required_data": ["Shadow probes", "Wrapper reports", "Guard check"],
        "limitations": ["Shadow comparison only", "No production changes"],
    },
    {
        "keywords": ["shadow qlab"],
        "tool": "qbot_legacy_shadow_probe",
        "args": {"capability": "qlab"},
        "confidence": "high",
        "required_data": ["QLab status and smoke check"],
        "limitations": ["Read-only comparison"],
    },
    {
        "keywords": ["shadow export"],
        "tool": "qbot_legacy_shadow_probe",
        "args": {"capability": "export"},
        "confidence": "high",
        "required_data": ["Export status and dry-run"],
        "limitations": ["Read-only comparison"],
    },
    {
        "keywords": ["shadow sync"],
        "tool": "qbot_legacy_shadow_probe",
        "args": {"capability": "sync"},
        "confidence": "high",
        "required_data": ["Sync status and dry-run"],
        "limitations": ["Read-only comparison"],
    },
    {
        "keywords": ["shadow garmin"],
        "tool": "qbot_legacy_shadow_probe",
        "args": {"capability": "garmin"},
        "confidence": "high",
        "required_data": ["Garmin status and dry-run"],
        "limitations": ["Read-only comparison"],
    },
    {
        "keywords": ["cutover plan", "plan przełączenia", "jak przełączyć starego q"],
        "tool": "qbot_legacy_cutover_plan",
        "args": {},
        "confidence": "high",
        "required_data": ["None"],
        "limitations": ["Plan only — PLAN_ONLY", "No actions executed", "Requires manual approval"],
    },
    {
        "keywords": ["cutover readiness", "czy można przełączyć starego q",
                      "bramka cutover", "czy można zrobić cutover"],
        "tool": "qbot_legacy_cutover_readiness_gate",
        "args": {},
        "confidence": "high",
        "required_data": ["All Qbot subsystems", "Legacy diagnostics", "Shadow report"],
        "limitations": ["Readiness check only", "No cutover executed"],
    },
    {
        "keywords": ["manual cutover plan", "plan manualnego przełączenia", "jak przełączyć q"],
        "tool": "qbot_legacy_manual_cutover_plan",
        "args": {},
        "confidence": "high",
        "required_data": ["None"],
        "limitations": ["PLAN_ONLY", "All commands for human review only"],
    },
    {
        "keywords": ["status przejęcia starego q", "ile przejęcia starego q", "takeover status"],
        "tool": "qbot_legacy_takeover_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Cutover readiness gate"],
        "limitations": ["Read-only status report"],
    },
    {
        "keywords": ["status cutover", "czy stary q wyłączony", "status przełączenia"],
        "tool": "qbot_legacy_cutover_status",
        "args": {},
        "confidence": "high",
        "required_data": ["systemd status q-bot/qbot-api/qlab services"],
        "limitations": ["Read-only status", "No commands executed"],
    },
    {
        "keywords": ["rollback legacy", "plan rollbacku starego q"],
        "tool": "qbot_legacy_rollback_plan",
        "args": {},
        "confidence": "high",
        "required_data": ["None"],
        "limitations": ["PLAN_ONLY", "Manual approval required"],
    },
    {
        "keywords": ["zaplanuj narzędzia", "dobierz narzędzia", "llm planner"],
        "tool": "qbot_llm_plan_query",
        "args": {},
        "confidence": "high",
        "required_data": ["Tool registry", "Policy engine"],
        "limitations": ["Planner proposes, Qbot validates", "Rule fallback without LLM key"],
    },
    {
        "keywords": ["wykonaj inteligentnie", "smart run", "uruchom qbot smart"],
        "tool": "qbot_llm_run_query",
        "args": {},
        "confidence": "high",
        "required_data": ["LLM planner", "Policy engine", "Tool registry"],
        "limitations": ["Only READ_ONLY auto-execute", "CONTROLLED_ACTION blocked"],
    },
    {
        "keywords": ["lista polityk narzędzi", "tool policy"],
        "tool": "qbot_tool_policy_list",
        "args": {},
        "confidence": "high",
        "required_data": ["Tool registry"],
        "limitations": ["Static listing"],
    },
    {
        "keywords": ["tryb external llm", "status llm external", "czy chatgpt jest główny"],
        "tool": "qbot_external_llm_status",
        "args": {},
        "confidence": "high",
        "required_data": ["None"],
        "limitations": ["Static status", "No secrets exposed"],
    },
    {
        "keywords": ["polityka modeli", "hierarchia modeli", "model hierarchy"],
        "tool": "qbot_external_llm_policy",
        "args": {},
        "confidence": "high",
        "required_data": ["None"],
        "limitations": ["Static policy document"],
    },
    {
        "keywords": ["przygotuj kontekst dla chatgpt", "context bundle", "pakiet kontekstu"],
        "tool": "qbot_external_context_bundle",
        "args": {"topic": "operational_status"},
        "confidence": "high",
        "required_data": ["Qbot operational tools"],
        "limitations": ["Sanitized output", "No secrets", "Truncated to max_chars"],
    },
    {
        "keywords": ["jaki tool", "jakie narzędzie", "which tool", "recommend tool", "tool plan", "plan narzędzi", "which qbot tool", "tool selector"],
        "tool": "qbot_external_tool_plan",
        "args": {"query": "__QUERY__", "style": "concise", "max_tools": 3, "include_prompt": True},
        "confidence": "high",
        "required_data": ["Qbot tool policy", "Qbot LLM planner"],
        "limitations": ["Returns plan only", "No execution", "Uses policy allowlist"],
    },
    {
        "keywords": ["prompt dla chatgpt", "chatgpt prompt pack", "przygotuj prompt"],
        "tool": "qbot_chatgpt_prompt_pack",
        "args": {"topic": "operational_status", "task": "Summarize status", "style": "concise"},
        "confidence": "high",
        "required_data": ["Qbot context bundle"],
        "limitations": ["Ready-to-paste prompt", "No secrets", "ChatGPT Plus external only"],
    },
    {
        "keywords": ["workflow chatgpt", "jak używać chatgpt z qbot"],
        "tool": "qbot_external_llm_workflow_guide",
        "args": {},
        "confidence": "high",
        "required_data": ["None"],
        "limitations": ["Instructional only", "Step-by-step guide"],
    },
    {
        "keywords": ["telegram status", "czy telegram działa", "status telegram", "telegram info"],
        "tool": "qbot_telegram_status",
        "args": {},
        "confidence": "high",
        "required_data": [
            "qbot_operator_final_smoke_test",
            "qbot_readiness_report",
            "qbot_legacy_takeover_status",
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_WEBHOOK_SECRET",
            "QBOT_PUBLIC_BASE_URL",
        ],
        "limitations": ["Read-only", "No webhook execution", "No tokens exposed", "Cutover-aware summary only"],
    },
    {
        "keywords": ["legacy", "legacy status", "rollback", "stan legacy", "q-bot disabled"],
        "tool": "qbot_legacy_cutover_status",
        "args": {},
        "confidence": "medium",
        "required_data": ["systemctl q-bot.service", "systemctl qbot-api.service"],
        "limitations": ["Read-only systemd check", "Rollback metadata only"],
    },
    {
        "keywords": ["telegram webhook", "plan webhook telegram", "webhook telegram plan",
                      "skonfiguruj webhook telegram"],
        "tool": "qbot_telegram_webhook_plan",
        "args": {},
        "confidence": "high",
        "required_data": ["TELEGRAM_WEBHOOK_SECRET", "QBOT_PUBLIC_BASE_URL"],
        "limitations": ["Plan only, no webhook execution", "No tokens exposed"],
    },
    {
        "keywords": ["telegram help", "komendy telegram", "co potrafi telegram bot",
                      "pomoc telegram"],
        "tool": "qbot_telegram_command_help",
        "args": {},
        "confidence": "high",
        "required_data": ["None"],
        "limitations": ["Static command listing"],
    },
    {
        "keywords": ["public endpoint", "status endpointu", "czy endpoint jest publiczny",
                      "sprawdź publiczny url", "endpoint status"],
        "tool": "qbot_public_endpoint_status",
        "args": {},
        "confidence": "high",
        "required_data": ["QBOT_PUBLIC_BASE_URL"],
        "limitations": ["Read-only", "No secrets exposed"],
    },
    {
        "keywords": ["audyt telegram", "sprawdź starego telegram", "legacy telegram audit",
                      "czy stary telegram działał"],
        "tool": "qbot_telegram_legacy_audit",
        "args": {},
        "confidence": "high",
        "required_data": ["Filesystem at /opt/qbot/app"],
        "limitations": ["Read-only scan", "No token display"],
    },
    {
        "keywords": ["czy wszystko gotowe", "czy wszystko jest gotowe", "czy gotowe", "gotowe", "czy wszystko ok"],
        "tool": "qbot_api_self_check",
        "args": {},
        "confidence": "high",
        "required_data": ["API health endpoint", "PostgreSQL connection", "systemd service status", "git repository state"],
        "limitations": ["Only checks local services", "Does not check external APIs like Intervals.icu or Garmin"],
    },
    {
        "keywords": [
            "sprawdź rwgps storage", "status rwgps storage", "rwgps storage",
            "artifact store", "rwgps artifact store", "storage status rwgps",
            "schema rwgps", "seed check rwgps", "rwgps db", "rwgps postgres",
        ],
        "tool": "qbot_rwgps_artifact_store_status",
        "args": {},
        "confidence": "high",
        "required_data": ["PostgreSQL connectivity", "RWGPS storage schema"],
        "limitations": ["Read-only status check", "No mutations"],
    },
    {
        "keywords": ["rwgps", "ridewithgps", "rwgps status", "sprawdź rwgps"],
        "tool": "qbot_rwgps_legacy_status",
        "args": {},
        "confidence": "high",
        "required_data": ["RWGPS API token", "RWGPS route data"],
        "limitations": ["Read-only status check", "No route modification", "No secrets"],
    },
    {
        "keywords": [
            "rwgps export", "rwgps download", "rwgps gpx", "rwgps tcx", "rwgps json",
            "ridewithgps export", "ridewithgps download", "wyeksportuj trasę rwgps",
            "pobierz gpx rwgps", "pobierz trasę rwgps", "zwróć plik rwgps",
            "artifact_path", "artifact_relative_path", "download_ready", "return_mode",
            "content_base64", "base64 rwgps", "gpx rwgps", "tcx rwgps", "json rwgps",
        ],
        "tool": "qbot_rwgps_route_export_file",
        "args": {"route_id": "__ROUTE_ID__", "format": "gpx", "return_mode": "metadata"},
        "confidence": "high",
        "required_data": ["RWGPS route record", "RWGPS geometry/track points", "RWGPS export artifact path"],
        "limitations": ["Read-only export", "Returns a local artifact path and optional content payload"],
    },
    {
        "keywords": ["rwgps config", "ridewithgps config", "konfiguracja rwgps"],
        "tool": "qbot_rwgps_config_status",
        "args": {},
        "confidence": "high",
        "required_data": [".env.local"],
        "limitations": ["Config presence only", "No secret values"],
    },
    {
        "keywords": ["rwgps route", "ridewithgps route", "pokaż trasę", "szukaj trasy",
                      "lista tras", "list routes", "pokaż wszystkie trasy", "all routes",
                      "route search", "toskania", "florencja", "firenze",
                      "florence"],
        "tool": "qbot_rwgps_route_search",
        "args": {"query": "__QUERY__", "limit": 5, "offset": 0, "include_details": True},
        "confidence": "high",
        "required_data": ["RWGPS route catalog", "RWGPS route detail endpoint", "RWGPS export availability"],
        "limitations": ["Read-only search/detail", "No route modification", "No secrets"],
    },
    {
        "keywords": ["rwgps route list", "lista tras rwgps", "lista wszystkich tras", "pokaż listę tras", "list all rwgps routes"],
        "tool": "qbot_rwgps_route_list",
        "args": {"limit": 20, "offset": 0, "sort": "updated_at", "order": "desc", "search": ""},
        "confidence": "high",
        "required_data": ["RWGPS route catalog"],
        "limitations": ["Read-only listing", "Returns record data, not a summary only"],
    },
    {
        "keywords": [
            "pobierz trasę", "download route", "export route", "gpx track", "zwróć plik",
            "pobierz gpx", "export gpx", "gpx file", "tcx file", "json file",
        ],
        "tool": "qbot_rwgps_route_export_file",
        "args": {"route_id": "__ROUTE_ID__", "format": "gpx"},
        "confidence": "high",
        "required_data": ["RWGPS route record", "RWGPS geometry/track points", "RWGPS export artifact path"],
        "limitations": ["Read-only export", "Returns a local artifact path, not a binary attachment"],
    },
    {
        "keywords": [
            "parse gpx", "gpx parse", "gpx summary", "summarize gpx", "summarise gpx",
            "artifact parse", "artifact summary", "gpx artifact", "track points", "bbox",
            "analizuj gpx", "podsumuj gpx", "przeanalizuj gpx",
        ],
        "tool": "qbot_gpx_artifact_parse",
        "args": {"artifact_path": "__ARTIFACT_PATH__", "return_mode": "summary"},
        "confidence": "high",
        "required_data": ["RWGPS artifact path"],
        "limitations": ["Read-only summary", "No export or mutation"],
    },
    {
        "keywords": [
            "surface profile", "surface enrich", "enrich surface", "surface analysis", "nawierzchnia",
            "surface source", "profile nawierzchni", "route artifact enrich", "artifact enrich",
            "enrich gpx artifact", "enrich route artifact", "osm surface", "osm overpass",
        ],
        "tool": "qbot_route_artifact_enrich",
        "args": {"artifact_path": "__ARTIFACT_PATH__", "enrich": ["summary", "surface"], "surface_source": "auto", "sample_every_m": 100, "return_mode": "summary"},
        "confidence": "high",
        "required_data": ["RWGPS artifact path", "optional Overpass/OSM access"],
        "limitations": ["Read-only enrichment", "Surface profiling is opt-in and may return unknown"],
    },
    {
        "keywords": ["hammerhead import", "hammerhead status", "karoo import", "sprawdź hammerhead"],
        "tool": "qbot_hammerhead_import_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Hammerhead auth", "FIT files", "Tokenstore"],
        "limitations": ["Read-only status", "No import execution"],
    },
    {
        "keywords": ["csv export", "ostatni csv", "export csv"],
        "tool": "qbot_csv_export_status",
        "args": {},
        "confidence": "high",
        "required_data": ["CSV filesystem", "Outgoing directory"],
        "limitations": ["Read-only status", "No file writes by default"],
    },
    {
        "keywords": ["pokaż ostatni csv", "pokaż csv", "csv preview", "podgląd csv"],
        "tool": "qbot_csv_export_latest_get",
        "args": {"source": "garmin_proxy_latest", "limit_rows": 20},
        "confidence": "high",
        "required_data": ["outgoing/qbot_garmin_proxy_latest.csv"],
        "limitations": ["Read-only", "Max 200 rows", "No write"],
    },
    {
        "keywords": ["xert", "xert status", "sprawdź xert", "ftp xert"],
        "tool": "qbot_xert_readiness_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Xert API credentials"],
        "limitations": ["Read-only", "No credentials exposed"],
    },
    {
        "keywords": ["intervals", "intervals status", "sprawdź intervals", "wellness intervals"],
        "tool": "qbot_intervals_wellness_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Intervals API credentials"],
        "limitations": ["Read-only", "No credentials exposed"],
    },
    {
        "keywords": ["garmin", "garmin status", "sprawdź garmin"],
        "tool": "qbot_garmin_config_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Garmin credentials"],
        "limitations": ["Read-only", "No upload"],
    },
    {
        "keywords": ["chronometer", "cronometer", "nutrition", "odżywianie", "kalorie"],
        "tool": "qbot_cronometer_legacy_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Cronometer config"],
        "limitations": ["Read-only status", "No login"],
    },
    {
        "keywords": ["openweathermap", "weather config", "sprawdź pogodę"],
        "tool": "qbot_weather_config_status",
        "args": {},
        "confidence": "medium",
        "required_data": ["Weather API key"],
        "limitations": ["Config check only"],
    },
    {
        "keywords": ["openmaps", "overpass", "mapy", "mapa", "sprawdź mapy"],
        "tool": "qbot_openmaps_legacy_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Overpass API"],
        "limitations": ["Read-only status", "No route planning"],
    },
    {
        "keywords": ["garaż", "garaz", "garage", "rower", "bike"],
        "tool": "qbot_garage_raw_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Garage database"],
        "limitations": ["Read-only status"],
    },
    {
        "keywords": ["szukaj w garażu", "szukaj rower", "garage search"],
        "tool": "qbot_garage_raw_search",
        "args": {"query": ""},
        "confidence": "high",
        "required_data": ["Garage database"],
        "limitations": ["Read-only search"],
    },
    {
        "keywords": ["raport dzienny", "daily report", "daily report status"],
        "tool": "qbot_daily_report_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Report data files"],
        "limitations": ["Read-only status"],
    },
    {
        "keywords": ["raport z jazdy", "ride report", "ostatni raport"],
        "tool": "qbot_ride_report_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Report data files"],
        "limitations": ["Read-only status"],
    },
]

_EXAMPLES = [
    "sprawdź stan Q",
    "czy repo jest czyste",
    "pokaż ostatnie wywołania narzędzi",
    "jakie narzędzia są dostępne",
    "sprawdź stan bazy danych",
    "jakie jest obciążenie systemu",
    "pokaż drzewo projektu",
    "ostatnie commity",
    "czy są jakieś zmiany",
    "sprawdź bezpieczeństwo",
    "sprawdź stan Q, repo i guard",
    "pełny przegląd",
    "czy można działać",
    "ostatnie błędy",
    "stan projektu",
    "stan api",
    "czy qbot jest gotowy",
    "użycie narzędzi",
    "snapshot",
    "pełna diagnostyka operatora",
    "pokaż logi",
    "status backupu",
    "plan backupu",
    "skrypt backupu",
    "testowe błędy",
    "raport utrzymania",
    "timer backupu",
    "restore drill",
    "plan restore",
    "ściąga operatora",
    "czy qbot jest w pełni gotowy",
    "czy qbot jest gotowy finalnie",
    "polityka llm",
    "kontekst dla llm",
]

_MULTI_TOOL_SETS: dict[str, list[str]] = {
    "wszystko": ["qbot_api_self_check", "qbot_system_overview", "qbot_db_overview",
                  "qbot_git_status", "qbot_project_guard_check"],
    "pełny przegląd": ["qbot_api_self_check", "qbot_system_overview", "qbot_db_overview",
                        "qbot_git_status", "qbot_project_guard_check"],
    "kompletny status": ["qbot_api_self_check", "qbot_system_overview", "qbot_db_overview",
                          "qbot_git_status", "qbot_project_guard_check"],
}

_MULTI_TOOL_LIMIT = 5


def _get_tool_args(tool_name: str) -> dict[str, Any]:
    for entry in _INTENT_MAP:
        if entry["tool"] == tool_name:
            return entry["args"]
    return {}


def _materialize_args(query: str, args: dict[str, Any]) -> dict[str, Any]:
    materialized: dict[str, Any] = {}
    route_id_match = re.search(r"\b(\d{6,})\b", query)
    route_id = route_id_match.group(1) if route_id_match else ""
    artifact_path_match = re.search(r"(/opt/qbot/artifacts/[^\s\"']+\.(?:gpx|tcx|json)|[^\s\"']+\.(?:gpx|tcx|json))", query)
    artifact_path = artifact_path_match.group(1).rstrip(".,);]") if artifact_path_match else ""
    for key, value in (args or {}).items():
        if isinstance(value, str) and value == "__QUERY__":
            materialized[key] = query
        elif isinstance(value, str) and value == "__ROUTE_ID__":
            materialized[key] = route_id
        elif isinstance(value, str) and value == "__ARTIFACT_PATH__":
            materialized[key] = artifact_path
        else:
            materialized[key] = value
    return materialized


def _unknown_plan(query: str, reason: str) -> dict[str, Any]:
    return {
        "status": "error",
        "original_query": query,
        "intent": "unknown_intent",
        "selected_tool": None,
        "confidence": "low",
        "execution_mode": "preview_only",
        "execution_plan": {
            "mode": "single_tool",
            "steps": [
                {"step": 1, "action": "classify_intent", "status": "error",
                 "reason": reason},
                {"step": 2, "action": "select_tool", "status": "skipped",
                 "reason": reason},
                {"step": 3, "action": "execute_tool", "status": "skipped",
                 "reason": reason},
            ],
        },
        "planned_tools": [],
        "preview_only": True,
        "tool_result": None,
        "executed_tools": [],
        "tool_results": None,
        "required_data": [],
        "limitations": ["No intent matched — try a different query or use a direct tool"],
        "reason": reason,
        "available_examples": _EXAMPLES,
    }


def _single_tool_result(query: str, entry: dict[str, Any],
                        matched_kws: list[str], best_score: int) -> dict[str, Any]:
    tool_name = entry["tool"]
    if tool_name not in TOOLS:
        return _unknown_plan(query, f"tool {tool_name} not in registry")
    tool_args = _materialize_args(query, entry["args"])

    classify_ok = {"step": 1, "action": "classify_intent", "status": "ok",
                   "reason": f"matched_keywords: {matched_kws}"}
    select_ok = {"step": 2, "action": "select_tool", "status": "ok",
                 "tool": tool_name, "reason": "intent maps to allowlisted tool"}

    try:
        tool_result = TOOLS[tool_name](tool_args)
        execute_step = {"step": 3, "action": "execute_tool", "status": "ok",
                        "tool": tool_name}
    except Exception as exc:
        execute_step = {"step": 3, "action": "execute_tool", "status": "error",
                        "tool": tool_name, "reason": str(exc)}

    exec_status = "ok" if execute_step["status"] == "ok" else "error"

    return {
        "status": exec_status,
        "original_query": query,
        "intent": entry["keywords"][0],
        "selected_tool": tool_name if exec_status == "ok" else None,
        "confidence": entry["confidence"],
        "execution_mode": "single_tool",
        "execution_plan": {
            "mode": "single_tool",
            "steps": [classify_ok, select_ok, execute_step],
        },
        "planned_tools": [tool_name],
        "preview_only": False,
        "tool_result": tool_result if exec_status == "ok" else None,
        "executed_tools": [tool_name] if exec_status == "ok" else [],
        "tool_results": {tool_name: tool_result} if exec_status == "ok" else None,
        "selected_tool_args": tool_args,
        "required_data": entry.get("required_data", []),
        "limitations": entry.get("limitations", []),
        "notes": f"matched by keyword score {best_score}",
    }


def process_query(query: str, execute: bool = False) -> dict[str, Any]:
    q = (query or "").strip().lower()
    if not q:
        return _unknown_plan(query, "empty_query")

    for runbook in _RUNBOOKS:
        matched_kws: list[str] = [kw for kw in runbook["keywords"] if kw in q]
        if matched_kws:
            tool_args_list = list(runbook["tools"])
            return _build_multi_preview(
                query, tool_args_list,
                f"runbook:{runbook['name']} matched keywords: {matched_kws}",
                execute, runbook=runbook,
            )

    for mt_key, mt_tools in _MULTI_TOOL_SETS.items():
        if mt_key in q:
            tool_args_list: list[tuple[str, dict[str, Any]]] = [
                (t, _materialize_args(query, _get_tool_args(t))) for t in mt_tools if t in TOOLS
            ]
            return _build_multi_preview(query, tool_args_list, f"full_overview:{mt_key}", execute)

    matches: list[tuple[int, dict[str, Any], list[str]]] = []
    for entry in _INTENT_MAP:
        score = 0
        kws: list[str] = []
        for kw in entry["keywords"]:
            if kw in q:
                kws.append(kw)
                score += len(kw)
        if score > 0:
            matches.append((score, entry, kws))

    if not matches:
        return _unknown_plan(query, "unknown_intent")

    has_conjunction = bool(re.search(r"\b(i|oraz|też|także|plus)\b|,", q))

    if has_conjunction and len(matches) >= 2:
        tool_args_list: list[tuple[str, dict[str, Any]]] = []
        seen: set[str] = set()
        for _score, entry, _kws in matches:
            t = entry["tool"]
            if t not in seen:
                tool_args_list.append((t, _materialize_args(query, entry["args"])))
                seen.add(t)
        if len(tool_args_list) >= 2:
            if len(tool_args_list) > _MULTI_TOOL_LIMIT:
                tool_args_list = tool_args_list[:_MULTI_TOOL_LIMIT]
            return _build_multi_preview(query, tool_args_list,
                                        f"matched {len(matches)} intents with conjunction", execute)

    best_score, best, matched_kws = max(matches, key=lambda x: x[0])
    return _single_tool_result(query, best, matched_kws, best_score)


def _build_multi_preview(query: str, tool_args_list: list[tuple[str, dict[str, Any]]],
                          reason: str, execute: bool = False,
                          runbook: dict[str, Any] | None = None) -> dict[str, Any]:
    valid = [(t, a) for t, a in tool_args_list if t in TOOLS]
    if len(valid) > _MULTI_TOOL_LIMIT:
        valid = valid[:_MULTI_TOOL_LIMIT]

    tool_names = [t for t, _ in valid]

    if runbook:
        intent = runbook["name"]
        required_data = list(runbook.get("required_data", []))
        runbook_limitations = list(runbook.get("limitations", []))
    else:
        intent = "multi_tool_preview" if not execute else "multi_tool_execution"
        required_data = []
        runbook_limitations = []

    if not execute:
        steps: list[dict[str, Any]] = [
            {"step": 1, "action": "select_runbook", "status": "ok",
             "runbook": runbook["name"], "reason": reason} if runbook
            else {"step": 1, "action": "classify_intent", "status": "ok",
                  "reason": reason},
            {"step": 2, "action": "build_multi_tool_plan", "status": "ok",
             "tools": tool_names, "reason": f"{len(valid)} allowlisted tools selected"},
            {"step": 3, "action": "preview_tools", "status": "skipped",
             "reason": "preview only — tools were not executed"},
        ]

        limitations: list[str] = [] + runbook_limitations + [
            "Preview only; tools were not executed",
            "No arbitrary command execution",
            "Only allowlisted tools can appear in plan",
        ]
        if len(tool_args_list) > _MULTI_TOOL_LIMIT:
            limitations.append(f"Plan truncated to {_MULTI_TOOL_LIMIT} tools")

        return {
            "status": "ok",
            "original_query": query,
            "intent": intent,
            "selected_tool": None,
            "confidence": "medium",
            "execution_mode": "preview_only",
            "execution_plan": {
                "mode": "preview_only",
                "steps": steps,
            },
            "planned_tools": tool_names,
            "preview_only": True,
            "tool_result": None,
            "executed_tools": [],
            "tool_results": None,
            "required_data": required_data,
            "limitations": limitations,
            "notes": f"runbook preview — no tools executed" if runbook
                     else "multi-tool preview — no tools executed",
        }

    safe_valid = [(t, a) for t, a in valid if t in _SAFE_MULTI_EXECUTE_TOOLS]

    execute_steps: list[dict[str, Any]] = [
        {"step": 1, "action": "select_runbook", "status": "ok",
         "runbook": runbook["name"], "reason": reason} if runbook
        else {"step": 1, "action": "classify_intent", "status": "ok",
              "reason": reason},
        {"step": 2, "action": "build_multi_tool_plan", "status": "ok",
         "tools": [t for t, _ in safe_valid],
         "reason": f"{len(safe_valid)} allowlisted tools selected for execution"},
    ]

    executed_tools: list[str] = []
    tool_results: dict[str, Any] = {}
    has_error = False
    has_ok = False

    step_num = 3
    for tool_name, tool_args in safe_valid:
        t_args = dict(tool_args)
        if tool_name == "qbot_operator_runbook":
            t_args["execute"] = True
        try:
            result = TOOLS[tool_name](t_args)
            if isinstance(result, dict) and result.get("status") == "error":
                has_error = True
                execute_steps.append({
                    "step": step_num, "action": "execute_tool",
                    "tool": tool_name, "status": "error",
                    "reason": result.get("error", "tool returned error"),
                })
            else:
                has_ok = True
                execute_steps.append({
                    "step": step_num, "action": "execute_tool",
                    "tool": tool_name, "status": "ok",
                })
            tool_results[tool_name] = result
        except Exception as exc:
            has_error = True
            execute_steps.append({
                "step": step_num, "action": "execute_tool",
                "tool": tool_name, "status": "error",
                "reason": str(exc),
            })
            tool_results[tool_name] = {"error": str(exc), "tool": tool_name}
        executed_tools.append(tool_name)
        step_num += 1

    skipped = [t for t, _ in valid if t not in _SAFE_MULTI_EXECUTE_TOOLS]
    if skipped:
        execute_steps.append({
            "step": step_num, "action": "skip_tool",
            "tools": skipped, "status": "skipped",
            "reason": "not in SAFE_MULTI_EXECUTE_TOOLS",
        })

    if has_error and has_ok:
        status = "partial"
    elif has_error:
        status = "error"
    else:
        status = "ok"

    limitations = [] + runbook_limitations + [
        "Controlled multi-tool execution",
        "Only allowlisted tools were executed",
        "No arbitrary command execution",
    ]

    return {
        "status": status,
        "original_query": query,
        "intent": intent,
        "selected_tool": None,
        "confidence": "medium",
        "execution_mode": "multi_tool_execute",
        "execution_plan": {
            "mode": "multi_tool_execute",
            "steps": execute_steps,
        },
        "planned_tools": tool_names,
        "preview_only": False,
        "tool_result": None,
        "executed_tools": executed_tools,
        "tool_results": tool_results,
        "required_data": required_data,
        "limitations": limitations,
        "notes": f"runbook execution — tools were executed from allowlist" if runbook
                 else "multi-tool execution — tools were executed from allowlist",
    }
