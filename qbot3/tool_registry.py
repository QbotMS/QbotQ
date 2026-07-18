#!/usr/bin/env python3
"""QBot3 Tool Registry — pure tool definitions, zero legacy imports.

Each tool is a dict: {callable, category, description, args_schema, safety}
Albert discovers tools through this registry, not through legacy routers.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_TOOL_REGISTRY: dict[str, dict[str, Any]] = {}
_READ_ONLY_TOOLS: dict[str, dict[str, Any]] = {}
_WRITE_TOOLS: dict[str, dict[str, Any]] = {}


def _safe_call(func: Any, args: dict[str, Any]) -> dict[str, Any]:
    try:
        result = func(args)
        if isinstance(result, dict):
            return result
        return {"status": "OK", "data": result}
    except Exception as exc:
        return {"status": "ERROR", "error": str(exc)[:500]}


# ── helpers ────────────────────────────────────────────────────────────

def _today() -> str:
    return date.today().isoformat()


def _resolve_date(question: str, base: date | None = None) -> tuple[date, str]:
    base = base or date.today()
    ql = question.lower()
    if any(k in ql for k in ("jutro", "tomorrow", "jutrze")):
        return base + timedelta(days=1), "tomorrow"
    if any(k in ql for k in ("pojutrze", "pojutrz")):
        return base + timedelta(days=2), "day_after_tomorrow"
    if any(k in ql for k in ("wczoraj", "yesterday")):
        return base - timedelta(days=1), "yesterday"
    m = re.search(r'(\d{4}-\d{2}-\d{2})', question)
    if m:
        try:
            return date.fromisoformat(m.group(1)), "explicit"
        except ValueError:
            pass
    return base, "today"


def _idempotency_key(prefix: str, question: str) -> str:
    import uuid
    key = uuid.uuid5(uuid.NAMESPACE_DNS, f"{prefix}:{question.strip().lower()}")
    return f"{prefix}_{str(key)[:16]}"


# ── tool loaders ───────────────────────────────────────────────────────

def _load_status_tool() -> dict[str, Any]:
    from qbot_tools import _tool_qbot_status
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_status,
        "category": "system",
        "description": "QBot process status — hostname, pid, python version",
        "args_schema": {},
        "safety": "read",
    }


def _load_readiness_tool() -> dict[str, Any]:
    from qbot_operator_tools import _tool_qbot_readiness_report
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_readiness_report,
        "category": "system",
        "description": "QBot readiness assessment: resources, blockers, overall status",
        "args_schema": {},
        "safety": "read",
    }




def _load_planning_facts_tool() -> dict[str, Any]:
    from qbot_planning_memory import list_planning_facts
    return {
        "callable": lambda args: {
            "status": "OK",
            "facts": list_planning_facts(
                fact_date=args.get("date"),
                status=args.get("status"),
                fact_type=args.get("fact_type"),
                title=args.get("title"),
            ),
            "count": len(list_planning_facts(
                fact_date=args.get("date"),
                status=args.get("status"),
                fact_type=args.get("fact_type"),
                title=args.get("title"),
            )),
        },
        "category": "planning",
        "description": "List planning facts (notes, decisions) optionally filtered by date, status, fact_type or title",
        "args_schema": {
            "date": {"type": "string"},
            "status": {"type": "string"},
            "fact_type": {"type": "string"},
            "title": {"type": "string"},
        },
        "safety": "read",
    }


def _load_weather_forecast_tool() -> dict[str, Any]:
    from qbot_integration_tools import _tool_qbot_weather_forecast
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        q = args.get("_question", "")
        period = args.get("period", "")
        if not period:
            d, resolved = _resolve_date(q)
            period = "jutro" if resolved == "tomorrow" else "today"
        return _tool_qbot_weather_forecast({
            "location": args.get("location", "Marki"),
            "period": period,
            "hours": args.get("hours", 48),
        })
    return {
        "callable": _wrapper,
        "category": "weather",
        "description": (
            "Live fetch prognozy pogody z OpenWeatherMap — pobiera bezpośrednio z API, "
            "nie z cache DB. Używaj gdy użytkownik pyta o pogodę. "
            "Zwraca: temperatura, opady, wiatr, ciśnienie. "
            "Parametry: location (miasto, domyślnie Warszawa), period (today/jutro), "
            "hours (1-48, domyślnie 24)."
        ),
        "args_schema": {"location": {"type": "string"}, "period": {"type": "string"}, "hours": {"type": "integer"}},
        "safety": "read",
    }


def _load_nutrition_templates_tool() -> dict[str, Any]:
    from qbot_nutrition_tools import _tool_qbot_nutrition_template_list
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_nutrition_template_list,
        "category": "nutrition",
        "description": "List all saved meal templates with nutritional values (kcal, protein, carbs, fat)",
        "args_schema": {"limit": {"type": "integer"}},
        "safety": "read",
    }


def _load_nutrition_template_get_tool() -> dict[str, Any]:
    from qbot_nutrition_tools import _tool_qbot_nutrition_template_get
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_nutrition_template_get,
        "category": "nutrition",
        "description": "Get one saved meal template by name or id",
        "args_schema": {"name": {"type": "string"}},
        "safety": "read",
    }


def _load_nutrition_write_resolve_tool() -> dict[str, Any]:
    from qbot3.nutrition_write_resolver import resolve_nutrition_write

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query", "") or args.get("_question", "")).strip()
        payload = args.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        return resolve_nutrition_write(query, payload)

    return {
        "callable": _wrapper,
        "category": "nutrition",
        "description": (
            "Resolve ambiguous nutrition writes with meal template / food lookup and arithmetic. "
            "Use before nutrition_log_add when the query mentions minus/pomniejszone, pół kilo, "
            "opakowanie, template or szablon. Never guess kcal from raw prompt numbers."
        ),
        "args_schema": {
            "query": {"type": "string", "description": "Original nutrition write text"},
            "payload": {"type": "object", "description": "Optional base payload to refine"},
        },
        "safety": "read",
    }


def _load_nutrition_day_summary_tool() -> dict[str, Any]:
    from qbot_nutrition_tools import _tool_qbot_nutrition_day_summary
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_nutrition_day_summary,
        "category": "nutrition",
        "description": "Daily nutrition summary — total kcal, macros, meals for a given date",
        "args_schema": {"date": {"type": "string"}},
        "safety": "read",
    }


def _load_planning_fact_lookup_tool() -> dict[str, Any]:
    return _load_planning_facts_tool()


def _load_nutrition_meal_list_tool() -> dict[str, Any]:
    from qbot_nutrition_tools import _tool_qbot_nutrition_meal_list
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_nutrition_meal_list,
        "category": "nutrition",
        "description": "List meals logged for a date",
        "args_schema": {"date": {"type": "string"}},
        "safety": "read",
    }


def _load_wellness_day_tool() -> dict[str, Any]:
    from qbot_wellness_store import _tool_qbot_wellness_day_get
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_wellness_day_get,
        "category": "wellness",
        "description": (
            "Live fetch danych wellness z Garmin — pobiera bezpośrednio z Garmin API, "
            "nie z cache DB. Używaj gdy DB (qbot_wellness_daily) nie ma rekordu dla danej "
            "daty lub gdy użytkownik pyta o aktualne dane. "
            "Zwraca: hrv_ms, resting_hr_bpm, sleep_duration_min, kcal_burned. "
            "Parametry: date (ISO, domyślnie dziś)."
        ),
        "args_schema": {"date": {"type": "string"}},
        "safety": "read",
    }


def _load_sleep_day_tool() -> dict[str, Any]:
    from qbot_wellness_store import _tool_qbot_sleep_day_get
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_sleep_day_get,
        "category": "wellness",
        "description": (
            "Live fetch danych snu z Garmin — pobiera bezpośrednio z Garmin API, "
            "nie z cache DB. Używaj gdy DB (qbot_wellness_daily) nie ma rekordu "
            "dla danej daty. "
            "Zwraca: sleep_duration_min, sleep_score, awake_duration, source. "
            "Parametry: date (ISO, domyślnie dziś)."
        ),
        "args_schema": {"date": {"type": "string"}},
        "safety": "read",
    }


def _load_xert_readiness_tool() -> dict[str, Any]:
    from qbot_integration_tools import _tool_qbot_xert_readiness_status
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_xert_readiness_status,
        "category": "fitness",
        "description": (
            "Live fetch danych treningowych z Xert API — pobiera bezpośrednio, "
            "nie z cache DB. Używaj gdy DB (training_sessions, xert_metrics) nie ma "
            "rekordu lub użytkownik pyta o aktualny stan. "
            "BENCHMARK Xert (NIE zrodlo CP/FTP) - kanoniczne CP/FTP/W'/forma bierz z fitness_status (ModelQ v2). "
            "Zwraca: ftp_watts, ltp_watts, w_prime_kj, form_status. "
            "Parametry: brak (zawsze bieżący stan)."
        ),
        "args_schema": {},
        "safety": "read",
    }


def _load_fitness_status_tool() -> dict[str, Any]:
    from qbot_integration_tools import _tool_qbot_fitness_status
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_fitness_status,
        "category": "fitness",
        "description": (
            "Kanoniczny stan formy z ModelQ v2 (fitmodel_daily) - JEDYNE zrodlo "
            "CP/FTP/W'/formy. Uzyj dla pytan o CP, FTP, LTP, W', CTL/ATL/TSB, "
            "gotowosc/readiness. Zwraca: ftp_w, cp_w, ltp_w, wprime_kj (+lo/hi/confidence), "
            "ctl, atl, tsb, readiness_score/label, source. Xert NIE jest zrodlem CP "
            "(benchmark: xert_readiness). Parametr: date (ISO, domyslnie najnowszy dzien)."
        ),
        "args_schema": {"date": {"type": "string"}},
        "safety": "read",
    }


def _load_rwgps_list_tool() -> dict[str, Any]:
    from qbot_route_tools import _tool_qbot_rwgps_route_list
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_rwgps_route_list,
        "category": "routes",
        "description": (
            "Live fetch listy tras z RWGPS API — pobiera bezpośrednio, "
            "nie z cache DB. Używaj gdy użytkownik pyta o dostępne trasy. "
            "Zwraca: lista tras z nazwami i ID. "
            "Parametry: brak (zawsze aktualna lista)."
        ),
        "args_schema": {},
        "safety": "read",
    }


def _load_rwgps_route_find_tool() -> dict[str, Any]:
    from tools.rwgps.route_find import find_routes

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        name_hint = str(args.get("name_hint") or args.get("query") or args.get("search") or "").strip()
        limit_raw = args.get("limit", 5)
        try:
            limit = max(1, min(20, int(limit_raw)))
        except (TypeError, ValueError):
            limit = 5
        routes = find_routes(name_hint, limit=limit)
        matched = [item for item in routes if int(item.get("score", 0) or 0) > 0]
        return {
            "status": "OK" if matched else "PARTIAL",
            "name_hint": name_hint,
            "count": len(matched) if matched else len(routes),
            "routes": matched if matched else routes,
            "matches": matched,
            "closest_routes": routes,
        }

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "Wyszukaj trasy RWGPS po nazwie lub fragmencie nazwy. "
            "Używaj do rozwiązywania route_id po nazwie trasy przed importem lub podglądem. "
            "Parametry: name_hint, limit."
        ),
        "args_schema": {
            "name_hint": {"type": "string", "description": "Fragment nazwy trasy lub hint wyszukiwania"},
            "limit": {"type": "integer", "description": "Maksymalna liczba wyników", "default": 5},
        },
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
    }


def _load_artifact_search_tool() -> dict[str, Any]:
    from qbot3.artifacts.store import search_artifacts
    from qbot3.errors import success_result

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query") or args.get("name_hint") or args.get("search") or "").strip()
        limit_raw = args.get("limit", 50)
        try:
            limit = max(1, min(200, int(limit_raw)))
        except (TypeError, ValueError):
            limit = 50
        artifacts = search_artifacts(
            query=query,
            project_id=args.get("project_id"),
            artifact_type=args.get("artifact_type"),
            status=str(args.get("status", "active")),
            limit=limit,
        )
        return success_result({"query": query, "count": len(artifacts), "artifacts": artifacts})

    return {
        "callable": _wrapper,
        "category": "artifacts",
        "description": (
            "Wyszukaj artefakty po nazwie, tytule, project_id albo artifact_id. "
            "Używaj do znajdowania istniejących artefaktów przed zapisem lub importem."
        ),
        "args_schema": {
            "query": {"type": "string", "description": "Fraza wyszukiwania"},
            "project_id": {"type": "string"},
            "artifact_type": {"type": "string"},
            "status": {"type": "string", "default": "active"},
            "limit": {"type": "integer", "default": 50},
        },
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
    }


def _load_garage_status_tool() -> dict[str, Any]:
    from qbot_garage_tools import _tool_qbot_garage_raw_status
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_garage_raw_status,
        "category": "garage",
        "description": "Garage DB status — tables, counters, seed status",
        "args_schema": {},
        "safety": "read",
    }


def _load_artifacts_list_tool() -> dict[str, Any]:
    from qbot3.errors import DATA_MISSING, error_result, success_result
    from qbot3.artifacts.store import list_artifacts, list_projects

    def _normalize_project_id(raw: str | None) -> str | None:
        if not raw:
            return None
        pid = raw.strip().lower().replace(" ", "_").replace("-", "_")
        # Known alias map
        ALIASES = {
            "toskania_2026": "tuscany_2026",
            "toskania": "tuscany_2026",
            "toscana": "tuscany_2026",
        }
        return ALIASES.get(pid, pid)

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            if args.get("list_projects"):
                projects = list_projects()
                return success_result({"projects": projects, "count": len(projects)})

            artifacts = list_artifacts(
                project_id=_normalize_project_id(args.get("project_id")),
                artifact_type=args.get("artifact_type"),
                status=str(args.get("status", "active")),
            )
            if not artifacts:
                return error_result(DATA_MISSING, "Brak artefaktów dla podanych filtrów")
            # Wypłaszcz metadata_json żeby Albert widział rwgps_url wprost
            for a in artifacts:
                if isinstance(a.get("metadata_json"), dict):
                    a["metadata"] = a["metadata_json"]
                elif isinstance(a.get("metadata_json"), str):
                    import json as _j
                    try:
                        a["metadata"] = _j.loads(a["metadata_json"])
                    except Exception:
                        pass
            return success_result({"artifacts": artifacts, "count": len(artifacts)})
        except Exception as exc:
            return error_result("ARTIFACT_ERROR", str(exc)[:300])

    return {
        "callable": _wrapper,
        "category": "artifacts",
        "description": (
            "Lista projektów lub artefaktów QBot Sandbox. "
            "Używaj dla pytań o projekty, pliki projektu, trasę, raporty, importy lub bazę garage.db. "
            "Parametry: list_projects=true albo project_id, artifact_type, status."
        ),
        "args_schema": {
            "project_id": {"type": "string", "description": "ID projektu, np. tuscany_2026"},
            "artifact_type": {"type": "string", "enum": ["route", "poi", "plan", "report", "export", "database", "import", "document"]},
            "status": {"type": "string", "description": "active|archived|deleted|tmp"},
            "list_projects": {"type": "boolean", "description": "Pokaż listę projektów zamiast artefaktów"},
        },
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
    }


def _load_artifact_save_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result
    from qbot3.artifacts.store import save_file

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            content = args.get("content")
            if content is None and args.get("content_base64"):
                import base64
                content = base64.b64decode(str(args["content_base64"]))
            if content is None:
                return error_result("ARTIFACT_ERROR", "content or content_base64 required")

            result = save_file(
                content=content,
                filename=str(args.get("filename", "artifact.txt")),
                artifact_type=str(args.get("artifact_type", "document")),
                title=str(args.get("title", args.get("filename", "artifact.txt"))),
                project_id=args.get("project_id"),
                mutation_type=str(args.get("mutation_type", "source")),
                source=str(args.get("source", "albert")),
                parent_artifact_id=args.get("parent_artifact_id"),
                idempotency_key=args.get("idempotency_key"),
                metadata=args.get("metadata"),
                subdir=args.get("subdir"),
                is_tmp=bool(args.get("is_tmp", False)),
            )
            return success_result({
                "artifact_id": str(result.get("artifact_id")),
                "file_path": result.get("file_path"),
                "title": result.get("title"),
                "artifact_type": result.get("artifact_type"),
                "project_id": result.get("project_id"),
                "size_bytes": result.get("size_bytes"),
                "sha256": result.get("sha256"),
            })
        except Exception as exc:
            return error_result("ARTIFACT_SAVE_ERROR", str(exc)[:300])

    return {
        "callable": _wrapper,
        "category": "artifacts",
        "description": (
            "Zapisz artefakt do /opt/qbot/artifacts i zarejestruj go w qbot_v2.artifacts. "
            "Używaj dla plików tekstowych i binarnych (content_base64). "
            "Parametry: content lub content_base64, filename, artifact_type, title, project_id, subdir, is_tmp."
        ),
        "args_schema": {
            "content": {"type": "string", "description": "Zawartość pliku tekstowego"},
            "content_base64": {"type": "string", "description": "Zawartość binarna w base64"},
            "filename": {"type": "string", "description": "Nazwa pliku"},
            "artifact_type": {"type": "string", "enum": ["route", "poi", "plan", "report", "export", "database", "import", "document"]},
            "title": {"type": "string", "description": "Czytelna nazwa artefaktu"},
            "project_id": {"type": "string", "description": "ID projektu"},
            "mutation_type": {"type": "string", "enum": ["source", "copy", "split", "merge", "edit", "export", "analysis", "generated", "import"]},
            "source": {"type": "string", "description": "Źródło artefaktu"},
            "parent_artifact_id": {"type": "string", "description": "ID artefaktu nadrzędnego"},
            "idempotency_key": {"type": "string", "description": "Klucz idempotencji"},
            "metadata": {"type": "object", "description": "Dodatkowe metadane JSON"},
            "subdir": {"type": "string", "description": "Podkatalog względem /opt/qbot/artifacts"},
            "is_tmp": {"type": "boolean", "description": "True dla plików tymczasowych"},
        },
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
    }


def _load_canonical_docs_tool() -> dict[str, Any]:
    # 2026-06-28: QBOT_BIBLE/KNOWHOW/PROJECT_INSTRUCTION w /opt/qbot/docs/ to stuby (redirect).
    # Aktualna architektura: docs/architecture/QBOT_ARCHITEKTURA_QBOT3.md
    # Aktualne instrukcje pracy: CLAUDE.md
    _APP_DIR = Path("/opt/qbot/app")
    _DOCS = {
        "QBOT_ARCHITEKTURA_QBOT3": _APP_DIR / "docs/architecture/QBOT_ARCHITEKTURA_QBOT3.md",
        "CONTEXT": _APP_DIR / "docs/CONTEXT.md",
        "CLAUDE": _APP_DIR / "CLAUDE.md",
    }

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        q = args.get("query", args.get("_question", "")).lower()
        results = []
        for label, path in _DOCS.items():
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            lines = text.splitlines()
            headings = [l.strip().lstrip("#").strip() for l in lines if l.strip().startswith("#")][:8]
            summary = "; ".join(headings[:4]) if headings else ""
            excerpts = []
            if q:
                terms = [w for w in re.findall(r'\w+', q) if len(w) >= 4]
                for term in terms:
                    for line in lines:
                        if term in line.lower():
                            excerpts.append(line.strip()[:240])
                            if len(excerpts) >= 5:
                                break
            results.append({
                "label": label,
                "path": str(path),
                "exists": True,
                "headings": headings,
                "summary": summary,
                "matched_excerpts": excerpts[:5],
            })
        return {
            "status": "OK",
            "documents": results,
            "count": len(results),
            "answer": "\n".join(
                f"- {r['label']}: {r['summary']}"
                + (("\n  excerpt: " + r['matched_excerpts'][0][:200]) if r['matched_excerpts'] else "")
                for r in results
            ) if results else "Brak dokumentów kanonicznych.",
        }

    return {
        "callable": _wrapper,
        "category": "docs",
        "description": "Read canonical QBot architecture docs (QBOT_ARCHITEKTURA_QBOT3, CONTEXT, CLAUDE) with excerpt matching. Use when asked about QBot architecture, routing, tools, instructions.",
        "args_schema": {"query": {"type": "string", "description": "Search terms for excerpt matching"}},
        "safety": "read",
    }


# ── Garmin diagnostics ─────────────────────────────────────────────────

def _load_garmin_diagnostics_tool() -> dict[str, Any]:
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, error_result, success_result
        q = args.get("_question", "")
        try:
            import psycopg
            from psycopg.rows import dict_row
            c = psycopg.connect(
                host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
                dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
                password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
            )
            cur = c.cursor()
            today = date.today().isoformat()
            cutoff_30d = (date.today() - timedelta(days=30)).isoformat()

            # Check all qbot_v2 Garmin tables
            tables_info = {
                "v2_sleep": {"schema": "qbot_v2", "table": "sleep_daily"},
                "v2_energy": {"schema": "qbot_v2", "table": "energy_daily"},
                "v2_wellness": {"schema": "qbot_v2", "table": "wellness_daily"},
                "v2_training": {"schema": "qbot_v2", "table": "training_sessions"},
                "v2_body_measurements": {"schema": "qbot_v2", "table": "body_measurements"},
                "v2_body_daily": {"schema": "qbot_v2", "table": "body_daily"},
            }

            details = {}
            for key, tbl in tables_info.items():
                schema_tbl = f"{tbl['schema']}.{tbl['table']}"
                exists = False
                try:
                    cur.execute(
                        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema=%s AND table_name=%s)",
                        (tbl["schema"], tbl["table"]),
                    )
                    exists = cur.fetchone()["exists"]
                except Exception:
                    pass
                if not exists:
                    details[key] = {"exists": False}
                    continue

                try:
                    cur.execute(f"SELECT count(*)::int FROM {schema_tbl}")
                    total = cur.fetchone()["count"]
                    cur.execute(f"SELECT count(*)::int FROM {schema_tbl} WHERE date >= %s", (cutoff_30d,))
                    cnt_30d = cur.fetchone()["count"]
                    cur.execute(f"SELECT MAX(date) as last_date FROM {schema_tbl}")
                    last_row = cur.fetchone()
                    last_date = str(last_row["last_date"]) if last_row and last_row["last_date"] else None
                    details[key] = {
                        "exists": True, "total_rows": total,
                        "last_30d": cnt_30d, "last_date": last_date,
                    }
                except Exception as e:
                    details[key] = {"exists": True, "error": str(e)[:100]}

            c.close()

            # Aggregate health status
            has_recent = any(
                v.get("last_30d", 0) > 0 for v in details.values() if isinstance(v, dict)
            )
            details["health"] = "OK" if has_recent else "NO_RECENT_DATA"

            return success_result(details)
        except ImportError:
            return error_result(CONNECTOR_MISSING, "psycopg not available")
        except Exception as exc:
            return error_result(CONNECTOR_MISSING, f"DB check failed: {str(exc)[:200]}")
    return {
        "callable": _wrapper,
        "category": "garmin",
        "description": (
            "Sprawdza stan synchronizacji Garmin w DB — czy tabele qbot_v2.sleep_daily, "
            "energy_daily, wellness_daily, training_sessions istnieją i mają dane. "
            "Zwraca tabelarycznie: exists, total_rows, last_30d, last_date."
        ),
        "args_schema": {},
        "safety": "read",
    }


def _load_nutrition_range_summary_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DATA_MISSING, error_result, success_result
    from qbot_nutrition_tools import _tool_qbot_nutrition_day_summary
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        date_from = args.get("date_from", date.today().isoformat())
        date_to = args.get("date_to", date_from)
        days = []
        try:
            d = date.fromisoformat(date_from)
            end = date.fromisoformat(date_to)
            while d <= end:
                day_result = _tool_qbot_nutrition_day_summary({"date": d.isoformat()})
                if isinstance(day_result, dict) and day_result.get("total_kcal"):
                    days.append({"date": d.isoformat(), "summary": day_result})
                d += timedelta(days=1)
        except Exception as exc:
            return {"status": "ERROR", "error": f"Range iteration error: {str(exc)[:200]}"}
        if not days:
            return error_result(DATA_MISSING, f"Brak danych żywieniowych dla zakresu {date_from}–{date_to}")
        total_kcal = sum(d["summary"].get("total_kcal", 0) for d in days)
        total_protein = sum(d["summary"].get("total_protein_g", 0) for d in days)
        total_carbs = sum(d["summary"].get("total_carbs_g", 0) for d in days)
        total_fat = sum(d["summary"].get("total_fat_g", 0) for d in days)
        return success_result({
            "date_from": date_from, "date_to": date_to,
            "days_with_data": len(days), "total_kcal": total_kcal,
            "total_protein_g": round(total_protein, 1),
            "total_carbs_g": round(total_carbs, 1),
            "total_fat_g": round(total_fat, 1),
        })
    return {
        "callable": _wrapper,
        "category": "nutrition",
        "description": "Nutrition summary for a date range — total kcal, macros, meal count. Parameters: date_from (ISO), date_to (ISO)",
        "args_schema": {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
        "safety": "read",
        "status": "legacy",
    }






def _load_rwgps_route_fetch_tool() -> dict[str, Any]:
    from qbot_route_tools import _tool_qbot_rwgps_route_get
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_rwgps_route_get,
        "category": "routes",
        "description": (
            "Live fetch trasy z RWGPS API — pobiera bezpośrednio trasę po ID. "
            "Używaj TYLKO gdy potrzebne są surowe metadane jednej trasy (sam dystans/nazwa/punkty). Do ANALIZY/OCENY trasy (nawierzchnia, podjazdy, pogoda, forma) NIE używaj tego — użyj route_plan_analysis. "
            "Zwraca: szczegóły trasy (dystans, przewyższenie, punkty). "
            "Parametry: route_id (wymagany, string lub number)."
        ),
        "args_schema": {"route_id": {"type": "string"}},
        "safety": "read",
    }


def _load_route_stage_plan_analyze_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result
    from qbot3.artifacts.route_analyzer import analyze_stage_endpoints

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        route_id = args.get("route_id")
        stage_km = args.get("stage_km", [])
        lodging_radius_km = args.get("lodging_radius_km", 5.0)
        check_lodging = bool(args.get("check_lodging", True))

        if not route_id:
            return error_result("MISSING_ARGS", "Wymagany parametr: route_id (int)")
        if not stage_km:
            return error_result("MISSING_ARGS", "Wymagany parametr: stage_km (lista kilometrów)")

        try:
            route_id_int = int(route_id)
        except (TypeError, ValueError):
            return error_result("INVALID_ARGS", f"route_id musi być liczbą całkowitą, dostałem: {route_id}")

        if isinstance(stage_km, (str, bytes)):
            stage_values = [stage_km]
        else:
            stage_values = list(stage_km)

        try:
            stage_values_f = [float(k) for k in stage_values]
        except (TypeError, ValueError) as exc:
            return error_result("INVALID_ARGS", f"stage_km musi być listą liczb: {exc}")

        try:
            lodging_radius = float(lodging_radius_km)
        except (TypeError, ValueError):
            return error_result("INVALID_ARGS", f"lodging_radius_km musi być liczbą: {lodging_radius_km}")

        result = analyze_stage_endpoints(
            route_id=route_id_int,
            stage_km=stage_values_f,
            lodging_radius_km=lodging_radius,
            check_lodging=check_lodging,
        )
        if result.get("status") == "error":
            return error_result("ROUTE_ANALYZER_ERROR", result.get("error", "nieznany błąd"))
        return success_result(result)

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "Analizuje końcówki etapów trasy RWGPS lokalnie na podstawie pliku JSON/GPX. "
            "Nie wysyła pełnej geometrii do LLM. Wylicza punkty na śladzie, robi reverse geocoding "
            "przez Nominatim i opcjonalnie sprawdza noclegi przez Overpass. "
            "Używaj dla pytań o podział trasy na etapy, końcówki etapów po kilometrze i bazę noclegową."
        ),
        "args_schema": {
            "route_id": {"type": "integer", "description": "ID trasy RWGPS, np. 55256628"},
            "stage_km": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Lista kilometrów końcowych etapów, np. [65, 150, 235]",
            },
            "lodging_radius_km": {
                "type": "number",
                "description": "Promień szukania noclegów w km, domyślnie 5.0",
            },
            "check_lodging": {
                "type": "boolean",
                "description": "Czy sprawdzać noclegi przez Overpass API, domyślnie true",
            },
        },
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Reads /opt/qbot/artifacts/exports/rwgps/rwgps_{route_id}.json locally.",
    }


def _load_stage_gpx_analyze_tool() -> dict[str, Any]:
    from pathlib import Path
    from qbot3.artifacts.route_analyzer import analyze_stage_gpx
    from qbot3.errors import error_result, success_result

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        file_path = args.get("file_path", "")
        stage = args.get("stage")
        resolved: dict[str, Any] | None = None

        if not file_path and stage is not None:
            try:
                stage_int = int(stage)
            except (TypeError, ValueError):
                return error_result("INVALID_ARGS", "stage musi być liczbą całkowitą")

            # Generic: resolve stage -> route_id via qbot_planning_facts
            # (route_stages), same mechanism as route_poi_analyze's stage
            # invariant. GPX is then read from the canonical RWGPS export
            # path, same convention used everywhere else.
            resolved = _resolve_stage_from_planning_facts(args.get("project_id"), stage_int)
            if resolved:
                candidate = Path("/opt/qbot/artifacts/exports/rwgps") / f"rwgps_{resolved['route_id']}.gpx"
                if candidate.exists():
                    file_path = str(candidate)

            if not file_path:
                # Fallback: legacy Tuscany-specific layout, kept for
                # backward compatibility if files are placed there manually.
                base = Path("/opt/qbot/artifacts/projects/tuscany_2026/projects")
                matches = sorted(base.glob(f"tuscany_2026_stage_{stage_int:02d}_*.gpx"))
                if matches:
                    file_path = str(matches[0])

            if not file_path:
                if resolved:
                    return error_result(
                        "FILE_NOT_FOUND",
                        f"Brak pliku GPX dla stage={stage_int} "
                        f"(route_id={resolved['route_id']}): "
                        f"/opt/qbot/artifacts/exports/rwgps/rwgps_{resolved['route_id']}.gpx"
                    )
                return error_result(
                    "STAGE_NOT_FOUND",
                    f"Brak wpisu dla stage={stage_int}"
                    + (f" w project_id={args.get('project_id')}" if args.get("project_id") else "")
                    + " w qbot_planning_facts (fact_type='route_stages')."
                )

        if not file_path:
            return error_result("MISSING_ARGS",
                "Podaj file_path (np. /opt/qbot/artifacts/exports/rwgps/"
                "rwgps_55444268.gpx) lub stage=<numer etapu>")
        try:
            result = analyze_stage_gpx(str(file_path))
        except Exception as exc:
            return error_result("ANALYSIS_ERROR", str(exc))
        if result.get("status") == "ERROR":
            return error_result("ANALYSIS_ERROR", result.get("error", "nieznany błąd"))

        # Sanity-check (Etap 1 PRZEBUDOWA): porownaj distance_km z GPX
        # z distance_km z qbot_planning_facts.route_stages (ground truth
        # dla tego etapu), tylko gdy stage zostal uzyty do resolwowania
        # pliku. Rozjazd >5% = PARTIAL z ostrzezeniem, nie cichy OK.
        top_status = "OK"
        if resolved and resolved.get("distance_km") and result.get("distance_km"):
            try:
                gpx_km = float(result["distance_km"])
                plan_km = float(resolved["distance_km"])
                diff_pct = abs(gpx_km - plan_km) / plan_km * 100.0 if plan_km else 0.0
                result["sanity_check"] = {
                    "ok": diff_pct <= 5.0,
                    "distance_km_gpx": gpx_km,
                    "distance_km_planning_facts": plan_km,
                    "diff_pct": round(diff_pct, 2),
                }
                if diff_pct > 5.0:
                    top_status = "PARTIAL"
                    result.setdefault("warnings", [])
                    result["warnings"].append(
                        f"sanity check: dystans z GPX ({gpx_km:.2f} km) rozjeżdża się "
                        f"z planning_facts ({plan_km:.2f} km) o {diff_pct:.1f}% "
                        f"(tolerancja 5%) - mozliwy nieaktualny artefakt GPX dla "
                        f"route_id={resolved.get('route_id')}"
                    )
                    # zlamany niezmiennik -> ticket incydentu (best-effort, dedup 6h)
                    try:
                        from core.incidents import open_incident
                        _rid = resolved.get("route_id")
                        open_incident(
                            f"sanity-check dystansu: route_id={_rid} GPX vs planning_facts rozjazd",
                            severity="medium",
                            source="invariant",
                            action_type="stage_gpx_analyze",
                            error_text=(
                                f"GPX {gpx_km:.2f} km vs planning_facts {plan_km:.2f} km "
                                f"= {diff_pct:.1f}% (>5%)"
                            ),
                            detail={
                                "route_id": _rid,
                                "distance_km_gpx": gpx_km,
                                "distance_km_planning_facts": plan_km,
                                "diff_pct": round(diff_pct, 2),
                            },
                        )
                    except Exception:
                        pass
            except (TypeError, ValueError, ZeroDivisionError):
                pass

        return success_result(result, status=top_status)

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "Analizuje lokalny plik GPX etapu i zwraca pełny profil: "
            "distance_km, elevation_gain_m, elevation_loss_m, min/max elevation, "
            "profile_5km, climbs i descents. "
            "Używaj gdy pytanie dotyczy przewyższenia, profilu wysokościowego, "
            "podjazdów/zjazdów konkretnego etapu Tuscany lub innej trasy. "
            "Pliki GPX etapów znajdują się w "
            "/opt/qbot/artifacts/projects/tuscany_2026/projects/ jako "
            "tuscany_2026_stage_{NN}_*.gpx. "
            "Można też podać stage=1 zamiast pełnej ścieżki."
        ),
        "args_schema": {
            "file_path": {
                "type": "string",
                "description": "Pełna ścieżka do pliku GPX",
            },
            "stage": {
                "type": "integer",
                "description": "Numer etapu Tuscany (1-7) — rozpozna plik automatycznie",
            },
        },
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Parsuje GPX lokalnie, nie wysyła danych do RWGPS.",
    }


def _load_rwgps_route_surface_analyze_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        route_id = args.get("route_id")
        project_id_arg = args.get("project_id")
        stage = args.get("stage")

        if stage is not None:
            try:
                stage_int = int(stage)
            except (TypeError, ValueError):
                return error_result("INVALID_ARGS", "stage musi być liczbą całkowitą")
            resolved = _resolve_stage_from_planning_facts(project_id_arg, stage_int)
            if not resolved:
                return error_result(
                    "STAGE_NOT_FOUND",
                    f"Brak wpisu dla stage={stage_int}"
                    + (f" w project_id={project_id_arg}" if project_id_arg else "")
                    + " w qbot_planning_facts (fact_type='route_stages')."
                )
            route_id = resolved["route_id"]
            project_id_arg = resolved.get("project_id") or project_id_arg

        if route_id is None:
            return error_result("MISSING_ARGS", "Wymagany parametr: route_id (int) lub stage")
        try:
            rid = str(int(route_id))
        except (TypeError, ValueError):
            return error_result("INVALID_ARGS", "route_id musi byc liczba: %s" % route_id)
        project_id = str(project_id_arg or "tuscany_2026")
        refresh = bool(args.get("refresh_overpass", False))
        try:
            from scripts.analyze_rwgps_surface import analyze_rwgps_surface_route
            result = analyze_rwgps_surface_route(rid, project_id=project_id, refresh_overpass=refresh)
        except Exception as exc:
            return error_result("SURFACE_ERROR", str(exc)[:300])
        if not result.get("ok"):
            return error_result("SURFACE_ERROR", result.get("error") or result.get("status", "nieznany blad"))
        keep = ("route_id", "route_name", "geometry", "surface_breakdown", "dominant_surface",
                "practical_groups", "unknown_percent", "highway_breakdown", "tracktype",
                "smoothness", "overpass", "recommendation", "warnings")
        trimmed = {k: result[k] for k in keep if k in result}
        return success_result(trimmed)

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "Analizuje nawierzchnie trasy RWGPS (OSM/Overpass): zwraca rozklad "
            "asfalt/gravel/grunt/nieznana w %, dominujaca nawierzchnie, smoothness, "
            "tracktype, pokrycie i rekomendacje. Uzywaj gdy pytanie dotyczy nawierzchni, "
            "asfaltu/szutru/sciezek, gravela lub ryzykownych odcinkow trasy. "
            "Wymaga route_id (np. z rwgps_route_last). Overpass moze trwac kilkanascie sekund."
        ),
        "args_schema": {
            "stage": {"type": "integer", "description": "Numer etapu z qbot_planning_facts.route_stages - jesli podany, route_id/project_id sa wyliczane automatycznie z planu etapow (nadpisuja inne podane wartosci)."},
            "route_id": {"type": "integer", "description": "ID trasy RWGPS"},
            "project_id": {"type": "string", "description": "ID projektu, domyslnie tuscany_2026"},
            "refresh_overpass": {"type": "boolean", "description": "Wymus odswiezenie OSM (domyslnie cache)"},
        },
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Wrapper na scripts.analyze_rwgps_surface.analyze_rwgps_surface_route.",
    }


def _load_route_gpx_split_tool() -> dict[str, Any]:
    from qbot3.artifacts.gpx_splitter import split_route_gpx
    from qbot3.errors import error_result, success_result

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        route_id = args.get("route_id")
        if route_id is None:
            return error_result("MISSING_ARGS", "Wymagany parametr: route_id (int)")

        try:
            route_id_int = int(route_id)
        except (TypeError, ValueError):
            return error_result("INVALID_ARGS", f"route_id musi być liczbą całkowitą, dostałem: {route_id}")

        project_id = str(args.get("project_id", "tuscany_2026") or "tuscany_2026")
        source_gpx_path = args.get("source_gpx_path")
        overwrite_existing = bool(args.get("overwrite_existing", True))

        result = split_route_gpx(
            route_id=route_id_int,
            project_id=project_id,
            source_gpx_path=str(source_gpx_path) if source_gpx_path else None,
            overwrite_existing=overwrite_existing,
        )
        if result.get("status") == "error":
            return error_result("ROUTE_GPX_SPLIT_ERROR", result.get("error", "nieznany błąd"))
        return success_result(result)

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "Lokalnie dzieli GPX RWGPS na etapy i zapisuje poprawne pliki GPX w sandboxie. "
            "Nie wysyła pełnej geometrii do LLM. Dla Tuscany 2026 / RWGPS 55256628 tworzy "
            "7 plików stage: 01 scandicci-capannoli, 02 capannoli-castagneto carducci, "
            "03 castagneto carducci-castiglione della pescaia, 04 castiglione della pescaia-cinigiano, "
            "05 cinigiano-pienza, 06 pienza-monteriggioni, 07 monteriggioni-scandicci."
        ),
        "args_schema": {
            "route_id": {"type": "integer", "description": "ID trasy RWGPS, np. 55256628"},
            "project_id": {"type": "string", "description": "ID projektu, domyślnie tuscany_2026"},
            "source_gpx_path": {"type": "string", "description": "Opcjonalna ścieżka do lokalnego GPX"},
            "overwrite_existing": {"type": "boolean", "description": "Nadpisz istniejące pliki stage, domyślnie true"},
        },
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Reads /opt/qbot/artifacts/exports/rwgps/rwgps_{route_id}.gpx locally and writes stage GPX artifacts.",
    }


def _load_system_env_status_tool() -> dict[str, Any]:
    from qbot3.errors import OK, AUTH_MISSING, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        checks = {
            "openai_key": bool(os.getenv("OPENAI_API_KEY") or os.getenv("QGPT_API_KEY")),
            "anthropic_key": bool(os.getenv("ANTHROPIC_API_KEY")),
            "deepseek_key": bool(os.getenv("DEEPSEEK_API_KEY")),
            "telegram_token": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
            "xert_email": bool(os.getenv("XERT_EMAIL")),
            "garmin_email": bool(os.getenv("GARMIN_EMAIL")),
            "rwgps_token": bool(os.getenv("RWGPS_AUTH_TOKEN")),
            "intervals_key": bool(os.getenv("INTERVALS_API_KEY")),
            "postgres_host": os.getenv("PGHOST", "not set"),
            "db_connected": False,
            "albert_provider": os.getenv("ALBERT_LLM_PROVIDER", "openai"),
        }
        try:
            import psycopg
            c = psycopg.connect(
                host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
                dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
                password=os.getenv("PGPASSWORD", ""), connect_timeout=3,
            )
            c.close()
            checks["db_connected"] = True
        except Exception:
            pass
        return success_result(checks)
    return {
        "callable": _wrapper,
        "category": "system",
        "description": "System environment status: check which API keys and connectors are configured, DB connectivity",
        "args_schema": {},
        "safety": "read",
    }


# ── Daily report status (internal capability wrapper) ──────────────────

def _load_daily_report_status_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, TOOL_ERROR, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            from qbot3.capabilities import find_capability
            cap = find_capability("daily_report_status")
            if not cap:
                return error_result(CONNECTOR_MISSING, "daily_report_status capability not loaded")
            result = cap.run({"question": args.get("_question", "")})
            if isinstance(result, dict):
                data = result.get("data", result)
                summary = data.get("summary", str(data)[:300]) if isinstance(data, dict) else str(data)
                return success_result(data, summary=summary)
            return error_result(TOOL_ERROR, "capability returned non-dict")
        except ImportError as exc:
            return error_result(CONNECTOR_MISSING, f"capabilities module: {exc}")
        except Exception as exc:
            return error_result(TOOL_ERROR, str(exc)[:200])
    return {
        "callable": _wrapper,
        "category": "system",
        "description": "Daily report pipeline status: pipeline stage, channel delivery (telegram/email), data source errors, legacy tool errors, sleep data wait status. Używaj gdy pytanie dotyczy raportu dziennego, emaila, Telegram pipeline.",
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Internal capability — nie jest publicznym MCP tool. Wrapper dla qbot3.capabilities.system.daily_report_status.",
    }


# ── Gate status (internal capability wrapper) ─────────────────────────

def _load_gate_status_tool() -> dict[str, Any]:
    from qbot3.errors import OK, CONNECTOR_MISSING, TOOL_ERROR, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            from qbot3.capabilities import find_capability
            cap = find_capability("gate_status")
            if not cap:
                return error_result(CONNECTOR_MISSING, "gate_status capability not loaded")
            result = cap.run({"question": args.get("_question", "")})
            if isinstance(result, dict):
                data = result.get("data", result)
                summary = data.get("summary", str(data)[:300]) if isinstance(data, dict) else str(data)
                return success_result(data, summary=summary)
            return error_result(TOOL_ERROR, "capability returned non-dict")
        except ImportError as exc:
            return error_result(CONNECTOR_MISSING, f"capabilities module: {exc}")
        except Exception as exc:
            return error_result(TOOL_ERROR, str(exc)[:200])
    return {
        "callable": _wrapper,
        "category": "system",
        "description": "Gate (HikConnect) configuration and last-success status. Tylko odczyt — nie otwiera furtki.",
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Internal capability — nie jest publicznym MCP tool. Wrapper dla qbot3.capabilities.system.gate_status.",
    }


# ── Hammerhead sync status (internal capability wrapper) ──────────────

def _load_hammerhead_sync_status_tool() -> dict[str, Any]:
    from qbot3.errors import OK, CONNECTOR_MISSING, TOOL_ERROR, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            from qbot3.capabilities import find_capability
            cap = find_capability("hammerhead_sync_status")
            if not cap:
                return error_result(CONNECTOR_MISSING, "hammerhead_sync_status capability not loaded")
            result = cap.run({"question": args.get("_question", "")})
            if isinstance(result, dict):
                data = result.get("data", result)
                summary = data.get("summary", str(data)[:300]) if isinstance(data, dict) else str(data)
                return success_result(data, summary=summary)
            return error_result(TOOL_ERROR, "capability returned non-dict")
        except ImportError as exc:
            return error_result(CONNECTOR_MISSING, f"capabilities module: {exc}")
        except Exception as exc:
            return error_result(TOOL_ERROR, str(exc)[:200])
    return {
        "callable": _wrapper,
        "category": "system",
        "description": "Hammerhead→Garmin sync pipeline status: config, dedup state, last log, outgoing files. Tylko odczyt — nie wykonuje transferu.",
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Internal capability — nie jest publicznym MCP tool. Wrapper dla qbot3.capabilities.system.hammerhead_sync_status.",
    }


# ── LLM status (internal capability wrapper) ──────────────────────────

def _load_llm_status_tool() -> dict[str, Any]:
    from qbot3.errors import OK, CONNECTOR_MISSING, TOOL_ERROR, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            from qbot3.capabilities import find_capability
            cap = find_capability("llm_status")
            if not cap:
                return error_result(CONNECTOR_MISSING, "llm_status capability not loaded")
            result = cap.run({"question": args.get("_question", "")})
            if isinstance(result, dict):
                data = result.get("data", result)
                summary = result.get("summary", "") or (data.get("summary", "") if isinstance(data, dict) else "")
                if not summary:
                    inner = data if isinstance(data, dict) else result
                    parts = []
                    parts.append(f"Provider: {inner.get('provider','?')}")
                    parts.append(f"Model: {inner.get('model','?')}")
                    parts.append(f"Fallback: {inner.get('fallback_model','?')}")
                    keys_str = ", ".join(f"{k}={'Y' if v else 'N'}" for k, v in inner.get("providers_configured", {}).items())
                    parts.append(f"Keys: {keys_str}")
                    summary = " | ".join(parts)
                return success_result(data, summary=summary)
            return error_result(TOOL_ERROR, "capability returned non-dict")
        except ImportError as exc:
            return error_result(CONNECTOR_MISSING, f"capabilities module: {exc}")
        except Exception as exc:
            return error_result(TOOL_ERROR, str(exc)[:200])
    return {
        "callable": _wrapper,
        "category": "system",
        "description": "Status używanego modelu LLM i providera. Zwraca provider, model, fallback_model, providers_configured. Tylko odczyt — bez sekretów.",
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Internal capability — nie jest publicznym MCP tool. Wrapper dla qbot3.capabilities.system.llm_status.",
    }


# ── MCP tools list ─────────────────────────────────────────────────────

def _load_mcp_tools_list_tool() -> dict[str, Any]:
    from qbot3.errors import OK, success_result
    return {
        "callable": lambda args: success_result({
            "mcp_tools": [
                {"name": "qbot.query", "description": "Main QBot3 interface — read, plan, draft"},
                {"name": "qbot.action_execute", "description": "Execute write actions after safety validation"},
            ]
        }),
        "category": "system",
        "description": "List all available MCP public tools with descriptions",
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Returns the 2 public MCP tools: qbot.query and qbot.action_execute",
    }


def _load_system_logs_recent_tool() -> dict[str, Any]:
    from qbot3.errors import CONNECTOR_MISSING, error_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        log_path = "/opt/qbot/logs/q-bot.log"
        try:
            if not os.path.isfile(log_path):
                return error_result(CONNECTOR_MISSING, f"Log file not found: {log_path}")
            lines = 20
            with open(log_path, "r") as f:
                tail = list(f)[-lines:]
            return {"status": "OK", "logs": tail, "source": log_path, "lines": len(tail)}
        except Exception as exc:
            return error_result(CONNECTOR_MISSING, f"Cannot read logs: {str(exc)[:200]}")
    return {
        "callable": _wrapper,
        "category": "system",
        "description": "Recent system logs tail (last 20 lines from q-bot.log)",
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Reads /opt/qbot/logs/q-bot.log — may not exist if log rotation changed path",
    }


def _load_docs_list_qbot_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DOC_MISSING, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        docs_dir = Path("/opt/qbot/docs")
        if not docs_dir.is_dir():
            return error_result(DOC_MISSING, "Docs directory /opt/qbot/docs not found")
        files = sorted(f.name for f in docs_dir.iterdir() if f.suffix in (".md", ".txt"))
        if not files:
            return error_result(DOC_MISSING, "No documentation files found")
        return success_result({"docs": files, "count": len(files), "path": str(docs_dir)})
    return {
        "callable": _wrapper,
        "category": "docs",
        "description": "List all QBot documentation files",
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Lists .md/.txt files from /opt/qbot/docs",
    }


def _load_nutrition_balance_today_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        today = date.today().isoformat()
        result = {"date": today, "kcal_in": None, "kcal_out": None, "balance": None, "sources": {}}
        try:
            from qbot_nutrition_tools import _tool_qbot_nutrition_day_summary
            nutr = _tool_qbot_nutrition_day_summary({"date": today})
            if isinstance(nutr, dict) and nutr.get("total_kcal"):
                result["kcal_in"] = nutr["total_kcal"]
                result["sources"]["nutrition"] = nutr
        except Exception:
            pass
        try:
            import psycopg
            from psycopg.rows import dict_row
            c = psycopg.connect(
                host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
                dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
                password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
            )
            cur = c.cursor()
            cur.execute("SELECT kcal_burned FROM qbot_wellness_daily WHERE date=%s AND source='garmin' LIMIT 1", (today,))
            row = cur.fetchone()
            if row and row.get("kcal_burned"):
                result["kcal_out"] = row["kcal_burned"]
                result["sources"]["garmin"] = {"kcal_burned": row["kcal_burned"]}
            c.close()
        except Exception:
            pass
        if result["kcal_in"] is not None or result["kcal_out"] is not None:
            if result["kcal_in"] is not None and result["kcal_out"] is not None:
                result["balance"] = round(result["kcal_in"] - result["kcal_out"], 1)
            return success_result(result)
        return error_result(DATA_MISSING, f"Brak danych bilansowych dla {today}. Nutrition: {result['kcal_in']}, Garmin: {result['kcal_out']}")
    return {
        "callable": _wrapper,
        "category": "nutrition",
        "description": "Daily nutrition balance: kcal in vs kcal out (Garmin). Parameters: date (ISO, default today)",
        "args_schema": {"date": {"type": "string"}},
        "safety": "read",
        "mode": "read_only",
        "status": "legacy",
        "notes": "Legacy — use db_schema_list + db_select_readonly instead",
    }


def _load_garmin_energy_today_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            import psycopg
            from psycopg.rows import dict_row
            c = psycopg.connect(
                host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
                dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
                password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
            )
            cur = c.cursor()
            today = date.today().isoformat()
            cur.execute(
                "SELECT date, source, kcal_burned, hrv_ms, resting_hr_bpm, sleep_duration_min "
                "FROM qbot_wellness_daily WHERE date=%s ORDER BY source_priority LIMIT 5", (today,)
            )
            rows = cur.fetchall()
            c.close()
            if not rows:
                return error_result(DATA_MISSING, f"Brak danych Garmin energy dla {today}")
            return success_result({"date": today, "records": rows, "count": len(rows)})
        except ImportError:
            return error_result(CONNECTOR_MISSING, "psycopg not available")
        except Exception as exc:
            return error_result(CONNECTOR_MISSING, f"DB error: {str(exc)[:200]}")
    return {
        "callable": _wrapper,
        "category": "garmin",
        "description": "Garmin energy data for today: kcal_burned, HRV, resting HR, sleep",
        "args_schema": {"date": {"type": "string"}},
        "safety": "read",
        "mode": "read_only",
        "status": "legacy",
        "notes": "Legacy — use db_schema_list + db_select_readonly instead",
    }


def _load_garmin_sync_status_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            import psycopg
            from psycopg.rows import dict_row
            c = psycopg.connect(
                host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
                dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
                password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
            )
            cur = c.cursor()
            # Use imported_at (real column name) instead of updated_at (doesn't exist)
            cur.execute("SELECT MAX(date) as last_date, MAX(imported_at) as last_sync FROM qbot_wellness_daily")
            row = cur.fetchone()
            cur.execute("SELECT COUNT(*) as cnt FROM qbot_wellness_daily WHERE date >= %s", ((date.today() - timedelta(days=7)).isoformat(),))
            count_7d = cur.fetchone()["cnt"]
            # Check import_runs for additional sync metadata
            last_import = None
            try:
                cur.execute("SELECT status, created_at FROM qbot_import_runs WHERE import_type='garmin' ORDER BY created_at DESC LIMIT 1")
                ir = cur.fetchone()
                if ir:
                    last_import = {"status": ir["status"], "created_at": str(ir["created_at"]) if ir["created_at"] else None}
            except Exception:
                pass
            c.close()
            if not row or not row.get("last_date"):
                return error_result(DATA_MISSING, "Brak danych Garmin w DB")
            return success_result({
                "last_data_date": str(row["last_date"]),
                "last_sync": str(row.get("last_sync", "")),
                "records_last_7d": count_7d,
                "has_recent_data": count_7d > 0,
                "last_import_run": last_import,
            })
        except ImportError:
            return error_result(CONNECTOR_MISSING, "psycopg not available")
        except Exception as exc:
            return error_result(CONNECTOR_MISSING, f"DB error: {str(exc)[:200]}")
    return {
        "callable": _wrapper,
        "category": "garmin",
        "description": (
            "Live sprawdzenie stanu synchronizacji Garmin — ostatnia data danych, "
            "ostatni czas syncu, liczba rekordów w 7 dni. "
            "Używaj gdy użytkownik pyta o synchronizację lub aktualność danych Garmin. "
            "Zwraca: last_data_date, last_sync, records_last_7d, has_recent_data."
        ),
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Queries qbot_wellness_daily metadata",
    }




def _load_rwgps_route_last_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DATA_MISSING, error_result, success_result
    try:
        from qbot_route_tools import _tool_qbot_rwgps_route_list
        def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
            result = _tool_qbot_rwgps_route_list({})
            if isinstance(result, dict):
                routes = result.get("data", result.get("routes", []))
                if not routes:
                    return error_result(DATA_MISSING, "Brak tras RWGPS")
                last = routes[0] if isinstance(routes, list) else routes
                return success_result({"last_route": last})
            return error_result(DATA_MISSING, "No RWGPS route data")
        return {
            "callable": _wrapper,
            "category": "routes",
            "description": (
                "Live fetch ostatniej trasy z RWGPS API — pobiera bezpośrednio, "
                "nie z cache DB. Używaj gdy użytkownik pyta o ostatnią trasę. "
                "Zwraca: route_id, nazwa, dystans, lokacje. "
                "Parametry: brak."
            ),
            "args_schema": {},
            "safety": "read",
            "mode": "read_only",
            "status": "implemented",
            "notes": "Calls rwgps_route_list and returns first (latest) entry",
        }
    except ImportError:
        def _stub(args: dict[str, Any]) -> dict[str, Any]:
            from qbot3.errors import CONNECTOR_MISSING
            return error_result(CONNECTOR_MISSING, "RWGPS route tools not available")
        return {
            "callable": _stub,
            "category": "routes",
            "description": (
                "Live fetch ostatniej trasy z RWGPS API. "
                "Zwraca: route_id, nazwa, dystans. Parametry: brak."
            ),
            "args_schema": {},
            "safety": "read",
            "mode": "read_only",
            "status": "adapter_missing",
        }


def _load_rwgps_artifact_status_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        route_id = str(args.get("route_id", "")).strip()
        if not route_id:
            return error_result(CONNECTOR_MISSING, "route_id required")
        artifacts_dir = Path("/opt/qbot/artifacts")
        if not artifacts_dir.is_dir():
            return error_result(CONNECTOR_MISSING, "Artifact directory not found")
        patterns = [f"*{route_id}*", f"*{route_id}.*"]
        found = []
        for p in patterns:
            for f in artifacts_dir.rglob(p):
                if f.is_file():
                    found.append(str(f.relative_to(artifacts_dir)))
        if found:
            return success_result({"route_id": route_id, "artifacts": found, "count": len(found)})
        return error_result(DATA_MISSING, f"Brak artifactów dla trasy {route_id}")
    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "Live sprawdzenie artefaktów trasy (GPX/JSON) w RWGPS API. "
            "Używaj po rwgps_route_list lub rwgps_route_fetch gdy potrzebujesz "
            "sprawdzić czy dana trasa ma gotowe pliki. "
            "Zwraca: lista dostępnych formatów (gpx, json, fit, tcx). "
            "Parametry: route_id (wymagany string)."
        ),
        "args_schema": {"route_id": {"type": "string"}},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Searches /opt/qbot/artifacts for files matching route_id",
    }


def _load_route_artifact_enrich_dry_run_tool() -> dict[str, Any]:
    """Diagnostyka nawierzchni trasy przez Overpass/OSM — tylko dry-run, bez zapisu do DB."""
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        from qbot3.errors import CONNECTOR_MISSING, error_result, success_result
        import json as _json

        route_id = str(args.get("route_id", "")).strip()
        sample_every_m = int(args.get("sample_every_m", 50))
        sample_every_m = max(25, min(sample_every_m, 5000))

        if not route_id:
            return error_result(CONNECTOR_MISSING, "route_id required — podaj ID trasy RWGPS")

        # Znajdź artifact w DB
        import psycopg
        from psycopg.rows import dict_row
        try:
            c = psycopg.connect(host="127.0.0.1", dbname="qbot", user="qbot", password="", row_factory=dict_row)
            artifact = c.execute(
                "SELECT id, route_id, source, export_format, artifact_path, sha256, status "
                "FROM route_artifacts WHERE route_id = %s ORDER BY id LIMIT 1", (route_id,)
            ).fetchone()
            c.close()
        except Exception as exc:
            return error_result(CONNECTOR_MISSING, f"DB error: {exc}")

        if not artifact:
            return error_result(CONNECTOR_MISSING, f"Brak artifactu dla route_id={route_id} w DB. "
                                f"Najpierw pobierz trasę przez rwgps_route_fetch.")

        # Użyj istniejącego artifact_path do analizy
        artifact_path = artifact.get("artifact_path") or ""
        if not artifact_path:
            return error_result(CONNECTOR_MISSING, "Artifact nie ma ścieżki")

        # Wywołaj analizę surface — tylko odczyt, nie zapisuje do route_surface_profiles
        try:
            import mcp_server
            surface_json = mcp_server.analyze_rwgps_artifact_surface(artifact_path, sample_distance_m=sample_every_m)
            surface_result = _json.loads(surface_json) if isinstance(surface_json, str) else surface_json
        except Exception as exc:
            return error_result(CONNECTOR_MISSING, f"Surface analysis error: {exc}")

        if not isinstance(surface_result, dict):
            return error_result(CONNECTOR_MISSING, "Surface analysis returned non-dict")

        if not surface_result.get("ok"):
            return error_result(CONNECTOR_MISSING,
                                surface_result.get("error", "UNKNOWN"),
                                surface_result.get("reason", "Surface analysis failed"))

        # Zbuduj wynik dry-run (bez zapisu do DB)
        result = {
            "route_id": route_id,
            "artifact_id": artifact["id"],
            "artifact_format": artifact["export_format"],
            "artifact_sha256": artifact["sha256"],
            "dry_run": True,
            "would_write_to": ["route_surface_profiles", "route_surface_segments"],
            "surface_analysis": {
                "engine_version": surface_result.get("engine_version"),
                "sample_distance_m": surface_result.get("sample_distance_m"),
                "point_count": surface_result.get("point_count"),
                "distance_km": surface_result.get("distance_km"),
                "sampled_points": surface_result.get("sampled_points"),
                "matched_points": surface_result.get("matched_points"),
                "unmatched_points": surface_result.get("unmatched_points"),
                "coverage_pct": surface_result.get("coverage_pct"),
                "dominant_surface": surface_result.get("dominant_surface"),
                "surface_percentages": surface_result.get("surface_percentages"),
                "surface_percentages_raw": surface_result.get("surface_percentages_raw"),
                "surface_percentages_refined": surface_result.get("surface_percentages_refined"),
                "unknown_pct_raw": surface_result.get("unknown_pct_raw"),
                "unknown_pct_refined": surface_result.get("unknown_pct_refined"),
                "geology_context": surface_result.get("geology_context"),
                "valhalla": surface_result.get("valhalla"),
                "landcover_used": surface_result.get("landcover_used"),
                "road_type_percentages": surface_result.get("road_type_percentages"),
                "tracktype_percentages": surface_result.get("tracktype_percentages"),
                "smoothness_summary": surface_result.get("smoothness_summary"),
                "confidence": surface_result.get("confidence"),
                "warnings": surface_result.get("warnings"),
                "source": "route_surface_engine_v1 + osm_overpass",
                "cache_hit": surface_result.get("cache_hit", False),
            },
        }

        # Dodaj przykładowe tagi OSM dla pierwszych 3 segmentów
        return success_result(result)

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "Diagnostyka nawierzchni trasy RWGPS przez OpenStreetMap/Overpass — DRY-RUN, bez zapisu do DB. "
            "2026-06-28: używa route_surface_engine_v1 po rzeczywistym śladzie, nie route_frames. "
            "Odczytuje tagi OSM surface/highway/tracktype, dodaje landcover/geology_context fail-open. "
            "Pokazuje raw/refined procenty, dominujący typ, zasięg OSM. "
            "NIE zapisuje do route_surface_profiles ani route_surface_segments. "
            "Parametry: route_id (wymagany, z rwgps_route_list), "
            "sample_every_m (opcjonalny, 25-5000, domyślnie 50)."
        ),
        "args_schema": {
            "route_id": {"type": "string", "description": "ID trasy RWGPS (liczba)"},
            "sample_every_m": {"type": "integer", "default": 50, "description": "Odstęp próbkowania nawierzchni w metrach (25-5000)"},
        },
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Dry-run surface enrichment — czyta artifact, woła Overpass API, nie zapisuje do DB surface tables.",
    }



def _load_rwgps_poi_push_tool() -> dict:
    from qbot3.errors import error_result
    from qbot_route_tools import _tool_qbot_rwgps_poi_push

    def _wrapper(args):
        return _tool_qbot_rwgps_poi_push(args)

    return {
        "name": "rwgps_poi_push",
        "description": "Analizuje POI na trasie RWGPS (woda/sklepy/atrakcje), wybiera najlepsze i dodaje do trasy w RWGPS. Wymaga route_id. Domyslnie dry_run=True.",
        "safety_class": "WRITE_SAFE",
        "fn": _wrapper,
        "schema": {
            "route_id": "str",
            "km_from": "float",
            "km_to": "float",
            "km_total": "float",
            "dry_run": "bool",
            "confirm": "bool",
            "focus": "str: all|logistics|attractions",
        },
    }

def _resolve_stage_from_planning_facts(
    project_id: str | None, stage: int
) -> dict[str, Any] | None:
    """Generyczny lookup stage->route_id/distance_km z qbot_planning_facts.

    Czyta fact_type='route_stages' (najnowszy, opcjonalnie filtrowany po
    fact_json.project_id), szuka w fact_json.stages[] wpisu ze stage==stage.
    Zwraca {"route_id": str, "distance_km": float, "project_id": str,
    "segment": str | None} albo None jesli nie znaleziono.
    """
    import psycopg
    from psycopg.rows import dict_row
    try:
        c = psycopg.connect(
            host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
            dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
            password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
        )
        cur = c.cursor()
        cur.execute(
            "SELECT id, fact_json FROM qbot_planning_facts "
            "WHERE fact_type='route_stages' ORDER BY id DESC LIMIT 20"
        )
        rows = cur.fetchall()
        c.close()
    except Exception:
        return None

    target_pid = (project_id or "").strip().lower() or None
    for row in rows:
        fact_json = row.get("fact_json")
        if isinstance(fact_json, str):
            try:
                fact_json = json.loads(fact_json or "{}")
            except Exception:
                fact_json = {}
        if not isinstance(fact_json, dict):
            continue
        row_pid = str(fact_json.get("project_id") or "").strip().lower()
        if target_pid and row_pid != target_pid:
            continue
        stages = fact_json.get("stages")
        if not isinstance(stages, list):
            continue
        for s in stages:
            try:
                if int(s.get("stage")) == int(stage):
                    route_id = s.get("route_id")
                    distance_km = s.get("distance_km")
                    if route_id in (None, "") or distance_km in (None, ""):
                        continue
                    return {
                        "route_id": str(route_id),
                        "distance_km": float(distance_km),
                        "project_id": row_pid or fact_json.get("project_id"),
                        "segment": s.get("segment"),
                    }
            except Exception:
                continue
    return None


def _load_route_poi_analyze_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result
    from qbot_route_tools import _tool_qbot_route_poi_analyze

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        stage = args.get("stage")
        if stage is not None:
            try:
                stage_int = int(stage)
            except (TypeError, ValueError):
                return error_result("INVALID_ARGS", "stage musi być liczbą całkowitą")
            resolved = _resolve_stage_from_planning_facts(args.get("project_id"), stage_int)
            if not resolved:
                return error_result(
                    "STAGE_NOT_FOUND",
                    f"Brak wpisu dla stage={stage_int}"
                    + (f" w project_id={args.get('project_id')}" if args.get("project_id") else "")
                    + " w qbot_planning_facts (fact_type='route_stages')."
                )
            args = dict(args)
            args["route_id"] = resolved["route_id"]
            args["project_id"] = resolved.get("project_id") or args.get("project_id")
            args["km_from"] = 0.0
            args["km_to"] = resolved["distance_km"]
            args["artifact_id"] = None
            args["path"] = None
            args["merge_artifact_ids"] = None

        route_id = args.get("route_id")
        artifact_id = args.get("artifact_id")
        project_id = args.get("project_id")
        path = args.get("path")
        focus = args.get("focus")
        retry_chunk_id = args.get("retry_chunk_id")
        retry_mode = bool(args.get("retry_mode", False))
        merge_artifact_ids = args.get("merge_artifact_ids")
        timeout_sec = args.get("timeout_sec")
        km_from = args.get("km_from")
        km_to = args.get("km_to")
        buffers = args.get("buffers")
        output_format = str(args.get("output_format", "md")).strip().lower() or "md"
        merge_list: list[str] = []
        if isinstance(merge_artifact_ids, list):
            merge_list = [str(item).strip() for item in merge_artifact_ids if str(item).strip()]
        elif isinstance(merge_artifact_ids, str):
            merge_list = [item.strip() for item in merge_artifact_ids.split(",") if item.strip()]

        if not route_id and not artifact_id and not path and not merge_list:
            return error_result("MISSING_ARGS", "Wymagany route_id, artifact_id, path lub merge_artifact_ids")
        if km_from is None or km_to is None:
            if not merge_list:
                return error_result("MISSING_ARGS", "Wymagane km_from i km_to")
            km_from = 0
            km_to = 0

        if km_from is None or km_to is None:
            return error_result("MISSING_ARGS", "Wymagane km_from i km_to")

        try:
            km_from_f = float(km_from)
            km_to_f = float(km_to)
        except (TypeError, ValueError):
            return error_result("INVALID_ARGS", "km_from i km_to muszą być liczbami")

        result = _tool_qbot_route_poi_analyze({
            "route_id": route_id,
            "artifact_id": artifact_id,
            "project_id": project_id,
            "path": path,
            "km_from": km_from_f,
            "km_to": km_to_f,
            "buffers": buffers,
            "focus": focus,
            "retry_chunk_id": retry_chunk_id,
            "retry_mode": retry_mode,
            "merge_artifact_ids": merge_list or None,
            "timeout_sec": timeout_sec,
            "output_format": output_format,
            "open_window": bool(args.get("open_window", False)),
            "ride_start": args.get("ride_start"),
            "avg_speed_kmh": args.get("avg_speed_kmh", 18.0),
            "google_hours": args.get("google_hours", True),
            "confirm": True,
        })
        if result.get("status") not in {"OK", "PARTIAL"} or not result.get("ok", True):
            return error_result("ROUTE_POI_ANALYSIS_FAILED", result.get("error", "nieznany błąd"))

        payload = dict(result)
        payload.pop("tool", None)
        payload.pop("safety_class", None)
        return success_result(payload)

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "[Dla zapytań informacyjnych o POI użyj route_poi_analyze_readonly - to narzędzie zapisuje/aktualizuje raport POI w artefaktach i wymaga potwierdzenia (action_execute).] "
            "Analizuje POI trasy RWGPS na podstawie GPX lokalnie i zapisuje raport MD do artefaktów. "
            "Parametry: project_id, route_id lub artifact_id lub path, albo merge_artifact_ids; km_from/km_to, buffers, output_format, focus, retry_chunk_id, retry_mode, timeout_sec."
        ),
        "args_schema": {
            "stage": {"type": "integer", "description": "Numer etapu z qbot_planning_facts.route_stages - jesli podany, route_id/km_from/km_to sa wyliczane automatycznie z planu etapow (nadpisuja inne podane wartosci)."},
            "route_id": {"type": "string", "description": "ID trasy RWGPS"},
            "artifact_id": {"type": "string", "description": "ID artefaktu GPX"},
            "project_id": {"type": "string", "description": "ID projektu logistycznego, np. tuscany_2026"},
            "path": {"type": "string", "description": "Lokalna ścieżka do pliku GPX"},
            "merge_artifact_ids": {"type": "array", "items": {"type": "string"}, "description": "Lista artefaktów partial/chunk do scalenia"},
            "km_from": {"type": "number", "description": "Początek analizowanego zakresu km"},
            "km_to": {"type": "number", "description": "Koniec analizowanego zakresu km"},
            "buffers": {
                "type": "object",
                "description": "Bufory POI: attractions_m, hard_resupply_m, soft_food_m, water_m, oraz opcjonalnie chunk_km, chunk_overlap_km, min_chunk_km, analysis_timeout_sec, overpass_timeout_sec, overpass_retries, retry_backoff_sec",
            },
            "focus": {"type": "string", "enum": ["all", "logistics", "hard_resupply", "food_only"], "default": "all"},
            "retry_chunk_id": {"type": "string", "description": "Identyfikator chunku do ponownej analizy"},
            "retry_mode": {"type": "boolean", "default": False},
            "timeout_sec": {"type": "number", "description": "Deadline całej analizy"},
            "output_format": {"type": "string", "enum": ["json", "md"], "default": "md"},
            "open_window": {"type": "boolean", "default": False, "description": "Wlacza weryfikacje godzin otwarcia i okna przejazdu"},
            "ride_start": {"type": "string", "description": "ISO start jazdy, np. 2026-07-01T07:00"},
            "avg_speed_kmh": {"type": "number", "default": 18.0, "description": "Srednia predkosc do ETA"},
            "google_hours": {"type": "boolean", "default": True, "description": "Pozwala na Google Places gdy OSM nie wystarcza"},
        },
        "safety": "write",
        "mode": "write",
        "status": "implemented",
        "notes": "Writes a project/report-specific MD artifact under /opt/qbot/artifacts/reports/ and registers it in artifact store.",
    }


def _load_route_poi_analyze_readonly_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result
    from qbot_route_tools import _tool_qbot_route_poi_analyze

    def _slim_poi_data(data: dict[str, Any]) -> dict[str, Any]:
        analysis = data.get("analysis") or {}

        def _count(section: str) -> int | None:
            value = analysis.get(section)
            if isinstance(value, list):
                return len(value)
            if isinstance(value, int):
                return value
            return None

        hard_resupply = _count("hard_resupply")
        soft_food_stop = _count("soft_food_stop")
        food_count = None
        if hard_resupply is not None or soft_food_stop is not None:
            food_count = (hard_resupply or 0) + (soft_food_stop or 0)

        slim = {
            "status": data.get("status"),
            "ok": data.get("ok"),
            "route_id": data.get("route_id"),
            "km_from": analysis.get("km_from") if analysis.get("km_from") is not None else data.get("km_from"),
            "km_to": analysis.get("km_to") if analysis.get("km_to") is not None else data.get("km_to"),
            "counts": {
                "water": _count("water"),
                "food": food_count,
                "attractions": _count("attractions"),
                "attractions_google": _count("town_fallback_check"),
            },
            "report_path": data.get("report_path"),
            "report_json_path": data.get("report_json_path"),
            "report_artifact_id": str(data.get("report_artifact_id") or ""),
            "note": (
                "Pełny raport POI w report_path/report_json_path. "
                "Tu tylko liczniki — czytaj artefakt dla szczegółów."
            ),
        }
        return slim

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        stage = args.get("stage")
        if stage is not None:
            try:
                stage_int = int(stage)
            except (TypeError, ValueError):
                return error_result("INVALID_ARGS", "stage musi być liczbą całkowitą")
            resolved = _resolve_stage_from_planning_facts(args.get("project_id"), stage_int)
            if not resolved:
                return error_result(
                    "STAGE_NOT_FOUND",
                    f"Brak wpisu dla stage={stage_int}"
                    + (f" w project_id={args.get('project_id')}" if args.get("project_id") else "")
                    + " w qbot_planning_facts (fact_type='route_stages')."
                )
            args = dict(args)
            args["route_id"] = resolved["route_id"]
            args["project_id"] = resolved.get("project_id") or args.get("project_id")
            args["km_from"] = 0.0
            args["km_to"] = resolved["distance_km"]
            args["artifact_id"] = None
            args["path"] = None
            args["merge_artifact_ids"] = None

        route_id = args.get("route_id")
        artifact_id = args.get("artifact_id")
        project_id = args.get("project_id")
        path = args.get("path")
        focus = args.get("focus")
        retry_chunk_id = args.get("retry_chunk_id")
        retry_mode = bool(args.get("retry_mode", False))
        merge_artifact_ids = args.get("merge_artifact_ids")
        timeout_sec = args.get("timeout_sec")
        km_from = args.get("km_from")
        km_to = args.get("km_to")
        buffers = args.get("buffers")
        output_format = str(args.get("output_format", "md")).strip().lower() or "md"
        merge_list: list[str] = []
        if isinstance(merge_artifact_ids, list):
            merge_list = [str(item).strip() for item in merge_artifact_ids if str(item).strip()]
        elif isinstance(merge_artifact_ids, str):
            merge_list = [item.strip() for item in merge_artifact_ids.split(",") if item.strip()]

        if not route_id and not artifact_id and not path and not merge_list:
            return error_result("MISSING_ARGS", "Wymagany route_id, artifact_id, path lub merge_artifact_ids")
        if km_from is None or km_to is None:
            if not merge_list:
                return error_result("MISSING_ARGS", "Wymagane km_from i km_to")
            km_from = 0
            km_to = 0

        if km_from is None or km_to is None:
            return error_result("MISSING_ARGS", "Wymagane km_from i km_to")

        try:
            km_from_f = float(km_from)
            km_to_f = float(km_to)
        except (TypeError, ValueError):
            return error_result("INVALID_ARGS", "km_from i km_to muszą być liczbami")

        result = _tool_qbot_route_poi_analyze({
            "route_id": route_id,
            "artifact_id": artifact_id,
            "project_id": project_id,
            "path": path,
            "km_from": km_from_f,
            "km_to": km_to_f,
            "buffers": buffers,
            "focus": focus,
            "retry_chunk_id": retry_chunk_id,
            "retry_mode": retry_mode,
            "merge_artifact_ids": merge_list or None,
            "timeout_sec": timeout_sec,
            "output_format": output_format,
            "open_window": bool(args.get("open_window", False)),
            "ride_start": args.get("ride_start"),
            "avg_speed_kmh": args.get("avg_speed_kmh", 18.0),
            "google_hours": args.get("google_hours", True),
            "confirm": True,
        })
        if result.get("status") not in {"OK", "PARTIAL"} or not result.get("ok", True):
            return error_result("ROUTE_POI_ANALYSIS_FAILED", result.get("error", "nieznany błąd"))

        payload = _slim_poi_data(dict(result))
        payload.pop("tool", None)
        payload.pop("safety_class", None)
        return success_result(payload)

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "[UŻYJ TEGO dla zapytań INFORMACYJNYCH typu 'co jest na etapie/trasie X', 'jakie POI na trasie', 'pokaż mi atrakcje/wodę/jedzenie na etapie' - zwraca wynik ANALIZY NATYCHMIAST, bez wymogu potwierdzenia. Dla zapisu/aktualizacji raportu POI w artefaktach projektu użyj route_poi_analyze.] "
            "Analizuje POI trasy RWGPS na podstawie GPX lokalnie i zapisuje raport MD do artefaktów. "
            "Parametry: project_id, route_id lub artifact_id lub path, albo merge_artifact_ids; km_from/km_to, buffers, output_format, focus, retry_chunk_id, retry_mode, timeout_sec."
        ),
        "args_schema": {
            "stage": {"type": "integer", "description": "Numer etapu z qbot_planning_facts.route_stages - jesli podany, route_id/km_from/km_to sa wyliczane automatycznie z planu etapow (nadpisuja inne podane wartosci)."},
            "route_id": {"type": "string", "description": "ID trasy RWGPS"},
            "artifact_id": {"type": "string", "description": "ID artefaktu GPX"},
            "project_id": {"type": "string", "description": "ID projektu logistycznego, np. tuscany_2026"},
            "path": {"type": "string", "description": "Lokalna ścieżka do pliku GPX"},
            "merge_artifact_ids": {"type": "array", "items": {"type": "string"}, "description": "Lista artefaktów partial/chunk do scalenia"},
            "km_from": {"type": "number", "description": "Początek analizowanego zakresu km"},
            "km_to": {"type": "number", "description": "Koniec analizowanego zakresu km"},
            "buffers": {
                "type": "object",
                "description": "Bufory POI: attractions_m, hard_resupply_m, soft_food_m, water_m, oraz opcjonalnie chunk_km, chunk_overlap_km, min_chunk_km, analysis_timeout_sec, overpass_timeout_sec, overpass_retries, retry_backoff_sec",
            },
            "focus": {"type": "string", "enum": ["all", "logistics", "hard_resupply", "food_only"], "default": "all"},
            "retry_chunk_id": {"type": "string", "description": "Identyfikator chunku do ponownej analizy"},
            "retry_mode": {"type": "boolean", "default": False},
            "timeout_sec": {"type": "number", "description": "Deadline całej analizy"},
            "output_format": {"type": "string", "enum": ["json", "md"], "default": "md"},
            "open_window": {"type": "boolean", "default": False, "description": "Wlacza weryfikacje godzin otwarcia i okna przejazdu"},
            "ride_start": {"type": "string", "description": "ISO start jazdy, np. 2026-07-01T07:00"},
            "avg_speed_kmh": {"type": "number", "default": 18.0, "description": "Srednia predkosc do ETA"},
            "google_hours": {"type": "boolean", "default": True, "description": "Pozwala na Google Places gdy OSM nie wystarcza"},
        },
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Read-only variant that returns POI analysis without entering the write tool path.",
    }


# ── RWGPS route import GPX (write tool) ────────────────────────────────

def _load_rwgps_route_import_gpx_tool() -> dict[str, Any]:
    from qbot_route_tools import _tool_qbot_rwgps_route_import_gpx
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_rwgps_route_import_gpx,
        "category": "routes",
        "description": (
            "Importuj trasę RWGPS z GPX lokalnego albo rozwiązanego po nazwie. "
            "Używaj source_route_id/route_id albo route_name_hint do wybrania trasy źródłowej. "
            "confirm=false = tylko walidacja i dry-run. confirm=true = wykonanie. "
            "Zwraca: status, resolved_route_id, resolved_route_name, a dla confirm=true: new_route_id, html_url."
        ),
        "args_schema": {
            "source_route_id": {"type": "string", "description": "Canonical RWGPS source route ID"},
            "route_id": {"type": "string", "description": "RWGPS route ID to resolve from hint"},
            "route_name_hint": {"type": "string", "description": "Fragment nazwy trasy do wyszukania"},
            "find_latest": {"type": "boolean", "default": False, "description": "Preferuj najnowszą trasę przy remisie"},
            "gpx_path": {"type": "string", "description": "Absolute path to local .gpx file"},
            "name": {"type": "string", "description": "Route name, e.g. 'Toskania 2026 7D-B Etap 01'"},
            "description": {"type": "string", "description": "Route description"},
            "privacy": {"type": "string", "enum": ["private", "public", "friends"], "default": "private"},
            "confirm": {"type": "boolean", "default": False, "description": "Set true to execute real RWGPS POST"},
        },
        "safety": "write",
        "mode": "write",
        "status": "implemented",
    }


# ── write tools ────────────────────────────────────────────────────────

def _load_nutrition_log_add_tool() -> dict[str, Any]:
    from qbot_nutrition_tools import _tool_qbot_nutrition_meal_from_template, _tool_qbot_nutrition_intake_log
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_nutrition_intake_log,
        "category": "nutrition",
        "description": "Log a meal entry. Parameters: date (ISO), meal_name, kcal_total, protein_g, carbs_g, fat_g, template_id (optional)",
        "args_schema": {
            "date": {"type": "string"}, "meal_name": {"type": "string"},
            "kcal_total": {"type": "number"}, "protein_g": {"type": "number"},
            "carbs_g": {"type": "number"}, "fat_g": {"type": "number"},
        "template_id": {"type": "integer"},
        },
        "safety": "write",
}


def _load_nutrition_log_delete_tool() -> dict[str, Any]:
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        from qbot3.adapters.mcp_adapter import _execute_nutrition_delete
        idem_key = _idempotency_key("nutr", json.dumps(args, sort_keys=True, ensure_ascii=False, default=str))
        return _execute_nutrition_delete("nutrition_log_delete", args, idem_key)
    return {
        "callable": _safe_call,
        "wrapped": _wrapper,
        "category": "nutrition",
        "description": (
            "Delete one logged meal by meal_id. Use with nutrition_meal_list or nutrition_day_summary to discover the id first."
        ),
        "args_schema": {
            "type": "object",
            "properties": {
                "meal_id": {"type": "integer", "description": "ID wpisu intake_logs"},
                "meal_log_id": {"type": "integer", "description": "Alias meal_id"},
                "intake_log_id": {"type": "integer", "description": "Alias meal_id"},
            },
            "required": ["meal_id"],
        },
        "safety": "write",
    }


def _load_nutrition_log_correct_tool() -> dict[str, Any]:
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        from qbot3.adapters.mcp_adapter import _execute_nutrition_correct
        idem_key = _idempotency_key("nutr", json.dumps(args, sort_keys=True, ensure_ascii=False, default=str))
        return _execute_nutrition_correct("nutrition_log_correct", args, idem_key)
    return {
        "callable": _safe_call,
        "wrapped": _wrapper,
        "category": "nutrition",
        "description": (
            "Correct one logged meal by meal_id. Use with nutrition_meal_list or nutrition_day_summary to discover the id first. "
            "Supports optional item_id for a specific item inside the meal."
        ),
        "args_schema": {
            "type": "object",
            "properties": {
                "meal_id": {"type": "integer", "description": "ID wpisu intake_logs"},
                "meal_log_id": {"type": "integer", "description": "Alias meal_id"},
                "intake_log_id": {"type": "integer", "description": "Alias meal_id"},
                "item_id": {"type": "integer", "description": "Optional ID of a specific intake_items row"},
                "meal_name": {"type": "string", "description": "New meal name"},
                "kcal_total": {"type": "number", "description": "New kcal value"},
                "protein_g": {"type": "number", "description": "New protein grams"},
                "carbs_g": {"type": "number", "description": "New carbs grams"},
                "fat_g": {"type": "number", "description": "New fat grams"},
            },
            "required": ["meal_id"],
        },
        "safety": "write",
    }


def _load_garmin_workout_create_tool() -> dict[str, Any]:
    from qbot_garmin_workouts import execute_garmin_workout_create

    return {
        "callable": _safe_call,
        "wrapped": lambda args: execute_garmin_workout_create(
            args,
            idempotency_key=str(args.get("idempotency_key", "")),
            confirm=bool(args.get("confirm", False)),
            dry_run=bool(args.get("dry_run", False)),
            source=str(args.get("source", "qbot3")),
        ),
        "category": "training",
        "description": (
            "Create a Garmin Connect structured workout using existing QBot Garmin auth. "
            "Supports canonical payloads with workoutName/sportType/workoutSegments or simplified payloads with "
            "name/sport/steps. Use confirm=true for real execution and dry_run=true for preview."
        ),
        "args_schema": {
            "workoutName": {"type": "string"},
            "name": {"type": "string"},
            "sport": {"type": "string"},
            "sportType": {"type": "object"},
            "workoutSegments": {"type": "array"},
            "steps": {"type": "array"},
            "description": {"type": "string"},
            "confirm": {"type": "boolean"},
            "dry_run": {"type": "boolean"},
            "idempotency_key": {"type": "string"},
        },
        "safety": "write",
    }






def _load_planning_fact_add_tool() -> dict[str, Any]:
    from qbot_planning_memory import save_planning_fact
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            draft = {
                "fact_type": str(args.get("fact_type", "custom")),
                "date": str(args.get("date", _today())),
                "title": str(args.get("title", "")),
                "fact_json": args.get("fact_json", {}),
                "confidence": str(args.get("confidence", "medium")),
            }
            result = save_planning_fact(draft=draft, channel="albert", confirm=True)
            if result.get("status") == "OK":
                return {"status": "OK", "write_committed": True,
                        "planning_fact_id": result.get("planning_fact_id"),
                        "title": draft["title"], "fact_type": draft["fact_type"]}
            return {"status": "ERROR", "error": result.get("error", "save_planning_fact failed")}
        except Exception as exc:
            return {"status": "ERROR", "error": str(exc)[:300]}
    return {
        "callable": _wrapper,
        "category": "planning",
        "safety": "write",
        "description": (
            "Zapisz nowy fakt planowania do qbot_planning_facts. "
            "Parametry: title (wymagany), fact_type (domyslnie: custom), "
            "date (ISO, domyslnie: dzisiaj), fact_json (opcjonalny dict z danymi), "
            "confidence (low/medium/high, domyslnie: medium)."
        ),
        "args_schema": {
            "title": {"type": "string", "description": "Tytul faktu (wymagany)"},
            "fact_type": {"type": "string", "description": "Typ: custom/route_stages/trip_plan/nutrition_plan"},
            "date": {"type": "string", "description": "Data ISO YYYY-MM-DD"},
            "fact_json": {"type": "object", "description": "Dane faktu jako JSON"},
            "confidence": {"type": "string", "description": "low/medium/high"},
        },
    }


def _load_planning_fact_update_tool() -> dict[str, Any]:
    from qbot_planning_memory import update_planning_fact
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            fact_id = args.get("fact_id")
            if not fact_id:
                return {"status": "ERROR", "error": "fact_id wymagany"}
            result = update_planning_fact(
                fact_id=int(fact_id),
                fact_json_patch=args.get("fact_json_patch"),
                stage_patch=args.get("stage_patch"),
                title=args.get("title"),
                status=args.get("status"),
                confidence=args.get("confidence"),
                valid_until=args.get("valid_until"),
                confirm=True,
            )
            if result.get("status") == "OK":
                return {"status": "OK", "write_committed": True,
                        "fact_id": int(fact_id),
                        "updated_fields": result.get("updated_fields", [])}
            return {"status": "ERROR", "error": result.get("error", "update_planning_fact failed")}
        except Exception as exc:
            return {"status": "ERROR", "error": str(exc)[:300]}
    return {
        "callable": _wrapper,
        "category": "planning",
        "safety": "write",
        "description": (
            "Zaktualizuj istniejacy fakt planowania (qbot_planning_facts) po jego ID. "
            "Uzyj planning_fact_get aby najpierw poznac fact_id. "
            "Parametry: fact_id (wymagany, int), fact_json_patch (dict scalany z fact_json), "
            "stage_patch ({stage: N, ...pola}) - aktualizuje jeden etap w fact_json.stages, "
            "title, status, confidence, valid_until (opcjonalne). "
            "fact_json_patch i stage_patch wzajemnie sie wykluczaja."
        ),
        "args_schema": {
            "fact_id": {"type": "integer", "description": "ID wiersza w qbot_planning_facts (wymagany)"},
            "fact_json_patch": {"type": "object", "description": "Pola do scalenia z fact_json (plytkie)"},
            "stage_patch": {"type": "object", "description": "{stage: N, route_id: ..., distance_km: ...} - aktualizuje etap N"},
            "title": {"type": "string"},
            "status": {"type": "string", "description": "proposed/confirmed/superseded"},
            "confidence": {"type": "string", "description": "low/medium/high"},
            "valid_until": {"type": "string", "description": "Data ISO YYYY-MM-DD"},
        },
    }


def _load_memory_write_tool() -> dict[str, Any]:
    from qbot3.memory import write_memory
    return {
        "callable": lambda args: (write_memory(
            str(args.get("memory_type", "confirmed_fact")),
            {"key": args.get("key", ""), "value": args.get("value", ""), "source": args.get("source", "qbot3")},
            source="qbot3",
        ), {"status": "OK", "memory_type": args.get("memory_type", "confirmed_fact")})[1],
        "category": "memory",
        "description": "Save a confirmed fact to memory. Parameters: memory_type (confirmed_fact|conversation_summary), key, value",
        "args_schema": {
            "memory_type": {"type": "string"}, "key": {"type": "string"}, "value": {"type": "string"},
        },
        "safety": "write",
    }


# ── DB introspection tool loaders ──────────────────────────────────────

def _load_db_schema_list_tool() -> dict[str, Any]:
    from qbot3.db_introspection import db_schema_list
    return {
        "callable": lambda args: db_schema_list(args),
        "category": "db",
        "description": (
            "Lista tabel w bazie danych. Wywołaj to jako pierwszy krok gdy potrzebujesz "
            "danych użytkownika (nutrition, kalendarz, wellness, trasy, sprzęt) "
            "i nie znasz jeszcze nazw tabel. Parametry: schema (domyślnie 'public')."
        ),
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "notes": "Transparent DB introspection — Albert should use this when the target table is unknown.",
    }

def _load_db_table_describe_tool() -> dict[str, Any]:
    from qbot3.db_introspection import db_table_describe
    return {
        "callable": lambda args: db_table_describe(args),
        "category": "db",
        "description": (
            "Kolumny i typy danych tabeli. Wywołaj po db_schema_list aby poznać "
            "dostępne kolumny przed budowaniem zapytania SQL. "
            "Parametry: table (nazwa tabeli), schema (domyślnie 'public')."
        ),
        "args_schema": {"table": {"type": "string"}, "schema": {"type": "string"}},
        "safety": "read",
        "mode": "read_only",
        "notes": "Use this to discover actual column names and types when the schema is unknown or a reader failed.",
    }

def _load_db_sample_rows_tool() -> dict[str, Any]:
    from qbot3.db_introspection import db_sample_rows
    return {
        "callable": lambda args: db_sample_rows(args),
        "category": "db",
        "description": "Sample rows from a table. Parameters: table (required), schema (default: public), limit (default: 5, max: 50)",
        "args_schema": {"table": {"type": "string"}, "schema": {"type": "string"}, "limit": {"type": "integer"}},
        "safety": "read",
        "mode": "read_only",
        "notes": "Use to inspect actual row shape after db_table_describe or when rows are needed for orientation.",
    }

def _load_db_select_readonly_tool() -> dict[str, Any]:
    from qbot3.db_introspection import db_select_readonly
    return {
        "callable": lambda args: db_select_readonly(args),
        "category": "db",
        "description": (
            "Wykonaj bezpieczne zapytanie SELECT na bazie danych. "
            "Użyj do pobrania danych nutrition, kalendarza, wellness, tras, sprzętu. "
            "Zawsze sprawdź kolumny przez db_table_describe przed użyciem. "
            "Parametry: sql (zapytanie SELECT, bez modyfikacji danych)."
        ),
        "args_schema": {"sql": {"type": "string"}},
        "safety": "read",
        "mode": "read_only",
        "notes": "Primary transparent read path for ordinary questions; use db_schema_list / db_table_describe first when schema is unknown.",
    }


def _load_garmin_live_fetch_tool() -> dict[str, Any]:
    """Live fetch danych Garmin wellness/energy dla konkretnej daty.

    Używa garminconnect bezpośrednio. Nie zapisuje do DB.
    Wymaga ważnych tokenów OAuth (garmin_auth.garmin_client).
    """
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        from qbot3.errors import CONNECTOR_MISSING, error_result, success_result
        from datetime import date as dt_date

        target_date = args.get("date", dt_date.today().isoformat())

        try:
            from garmin_auth import garmin_client, GarminAuthError
            client = garmin_client()
        except GarminAuthError as exc:
            return error_result(CONNECTOR_MISSING, f"Garmin auth: {exc}")
        except Exception as exc:
            return error_result(CONNECTOR_MISSING, f"Garmin client init error: {str(exc)[:200]}")

        try:
            summary = client.get_user_summary(target_date)
            if not summary:
                return error_result(
                    CONNECTOR_MISSING,
                    f"Garmin zwrócił pustą odpowiedź dla daty {target_date}."
                )

            result: dict[str, Any] = {
                "date": target_date,
                "source": "garmin_live",
                "fetched_at": dt_date.today().isoformat(),
            }

            field_map = {
                "totalKilocalories":        "total_kcal_out",
                "activeKilocalories":       "active_kcal_out",
                "bmrKilocalories":          "resting_kcal_out",
                "restingHeartRate":         "resting_hr_bpm",
                "totalSteps":               "steps",
                "averageStressLevel":       "stress_avg",
                "bodyBatteryMostCharged":   "body_battery_max",
                "bodyBatteryLeastCharged":  "body_battery_min",
            }
            for api_key, result_key in field_map.items():
                val = summary.get(api_key)
                if val is not None:
                    result[result_key] = val

            energy_fields = {"total_kcal_out", "active_kcal_out", "resting_kcal_out"}
            if not any(f in result for f in energy_fields):
                result["warning"] = (
                    "Garmin zwrócił dane ale bez pól energetycznych. "
                    f"Dostępne klucze: {list(summary.keys())[:15]}"
                )

            return success_result(result)

        except Exception as exc:
            err = str(exc)
            if "401" in err or "auth" in err.lower() or "token" in err.lower():
                return error_result(
                    CONNECTOR_MISSING,
                    f"Garmin API: błąd autoryzacji — tokeny wygasłe. {err[:150]}"
                )
            return error_result(
                CONNECTOR_MISSING,
                f"Garmin API error dla {target_date}: {err[:200]}"
            )

    return {
        "callable": _wrapper,
        "category": "garmin",
        "description": (
            "Live fetch danych wellness i energii z Garmin API dla konkretnej daty. "
            "Pobiera bezpośrednio z Garmin — nie z cache DB. "
            "Używaj gdy DB (daily_energy_expenditure, qbot_wellness_daily) nie ma "
            "rekordu dla danej daty lub gdy ostatni import był dawno. "
            "Zwraca: total_kcal_out, active_kcal_out, resting_kcal_out, steps, "
            "resting_hr_bpm, body_battery. "
            "Parametry: date (ISO YYYY-MM-DD, domyślnie dziś)."
        ),
        "args_schema": {
            "date": {
                "type": "string",
                "description": "Data w formacie ISO (YYYY-MM-DD). Domyślnie: dziś.",
            }
        },
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Live Garmin fetch — wymaga ważnych tokenów OAuth w garmin_auth.",
    }


# ── init ───────────────────────────────────────────────────────────────

def _init_registry():
    if _TOOL_REGISTRY:
        return

    loaders = [
        ("status", _load_status_tool),
        ("readiness", _load_readiness_tool),
        ("system_env_status", _load_system_env_status_tool),
        ("planning_facts", _load_planning_facts_tool),
        ("planning_fact_lookup", _load_planning_fact_lookup_tool),
        ("weather_forecast", _load_weather_forecast_tool),
        ("nutrition_template_list", _load_nutrition_templates_tool),
        ("nutrition_template_get", _load_nutrition_template_get_tool),
        ("nutrition_write_resolve", _load_nutrition_write_resolve_tool),
        ("nutrition_day_summary", _load_nutrition_day_summary_tool),
        ("nutrition_meal_list", _load_nutrition_meal_list_tool),
        ("nutrition_range_summary", _load_nutrition_range_summary_tool),
        ("wellness_day", _load_wellness_day_tool),
        ("sleep_day", _load_sleep_day_tool),
        ("xert_readiness", _load_xert_readiness_tool),
        ("fitness_status", _load_fitness_status_tool),
        ("garmin_diagnostics", _load_garmin_diagnostics_tool),
        ("garmin_live_fetch", _load_garmin_live_fetch_tool),
        ("rwgps_route_list", _load_rwgps_list_tool),
        ("rwgps_route_fetch", _load_rwgps_route_fetch_tool),
        ("route_stage_plan_analyze", _load_route_stage_plan_analyze_tool),
        ("route_gpx_split", _load_route_gpx_split_tool),
        ("stage_gpx_analyze", _load_stage_gpx_analyze_tool),
        ("rwgps_route_surface_analyze", _load_rwgps_route_surface_analyze_tool),
        ("garage_status", _load_garage_status_tool),
        ("artifacts_list", _load_artifacts_list_tool),
        ("artifact_save", _load_artifact_save_tool),
        ("canonical_docs", _load_canonical_docs_tool),
        ("mcp_tools_list", _load_mcp_tools_list_tool),
        ("daily_report_status", _load_daily_report_status_tool),
        ("gate_status", _load_gate_status_tool),
        ("hammerhead_sync_status", _load_hammerhead_sync_status_tool),
        ("llm_status", _load_llm_status_tool),
        ("system_logs_recent", _load_system_logs_recent_tool),
        ("docs_list_qbot", _load_docs_list_qbot_tool),
        ("nutrition_balance_today", _load_nutrition_balance_today_tool),
        ("garmin_energy_today", _load_garmin_energy_today_tool),
        ("garmin_sync_status", _load_garmin_sync_status_tool),
        ("rwgps_route_last", _load_rwgps_route_last_tool),
        ("rwgps_artifact_status", _load_rwgps_artifact_status_tool),
        ("rwgps_route_find", _load_rwgps_route_find_tool),
        ("route_plan_analysis", _load_route_plan_analysis_tool),
        ("ride_analysis", _load_ride_analysis_tool),
        ("route_profile_detail", _load_route_profile_detail_tool),
        ("route_list", _load_route_list_tool),
        ("route_recompute", _load_route_recompute_tool),
        ("route_attractions", _load_route_attractions_tool),
        ("route_delete", _load_route_delete_tool),
        ("tire_pressure", _load_tire_pressure_tool),
        ("route_fuel_plan", _load_route_fuel_plan_tool),
        ("route_time_estimate", _load_route_time_estimate_tool),
        ("route_wbgt", _load_route_wbgt_tool),
        ("route_artifact_enrich_dry_run", _load_route_artifact_enrich_dry_run_tool),
        ("route_poi_analyze", _load_route_poi_analyze_tool),
        ("route_poi_analyze_readonly", _load_route_poi_analyze_readonly_tool),
        ("route_report", _load_route_report_tool),
        ("route_analysis", _load_route_analysis_tool),
        ("rwgps_poi_push", _load_rwgps_poi_push_tool),
        ("rwgps_route_import_gpx", _load_rwgps_route_import_gpx_tool),
        ("artifact_search", _load_artifact_search_tool),
        # DB introspection tools (transparent read-only for Albert)
        ("db_schema_list", _load_db_schema_list_tool),
        ("db_table_describe", _load_db_table_describe_tool),
        ("db_sample_rows", _load_db_sample_rows_tool),
        ("db_select_readonly", _load_db_select_readonly_tool),
        # Write tools
        ("nutrition_log_add", _load_nutrition_log_add_tool),
        ("nutrition_log_delete", _load_nutrition_log_delete_tool),
        ("nutrition_log_correct", _load_nutrition_log_correct_tool),
        ("garmin_workout_create", _load_garmin_workout_create_tool),
        ("planning_fact_add", _load_planning_fact_add_tool),
        ("planning_fact_update", _load_planning_fact_update_tool),
        ("memory_confirmed_fact_add", _load_memory_write_tool),
    ]

    for name, loader in loaders:
        try:
            spec = loader()
            _TOOL_REGISTRY[name] = spec
            if spec.get("safety") == "write":
                _WRITE_TOOLS[name] = spec
            else:
                _READ_ONLY_TOOLS[name] = spec
        except Exception as exc:
            _TOOL_REGISTRY[name] = {
                "error": str(exc)[:200],
                "safety": "error",
                "category": "error",
            }


def _load_route_time_estimate_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result
    import qbot_route_time_tools as _rtt

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        out = _rtt._tool_route_time_estimate(args or {})
        st = out.get("status")
        if st == "OK":
            return success_result({"analysis": out.get("analysis", ""), "note": out.get("notes", "")})
        if st in ("NO_DATA", "NEEDS_INPUT"):
            return success_result({"analysis": out.get("analysis", ""), "warning": out.get("notes", "")})
        return error_result("ROUTE_TIME_ESTIMATE_FAILED", out.get("error") or out.get("notes") or "blad szacowania czasu trasy")

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "Szacowany CZAS przejechania ZAPLANOWANEJ trasy (model v2, z danych). "
            "Pytania: 'ile zajmie trasa', 'jak dlugo bede jechal', 'ile czasu na trase'. "
            "WYMAGA route_id z danymi kanonicznymi (grade 200m + nawierzchnia); bez fallbacku - brak danych => NEEDS_INPUT. "
            "Predkosc moving z empirycznej tabeli nawierzchnia x nachylenie; poziom wg trybu: normalny(mediana,domyslny)/sport/wyscig. "
            "Zwraca CZAS RUCHU i CZAS CALKOWITY OSOBNO + profil czasu zegarowego. Dokladnosc czesci tocznej ~+-15% (nieobciazona). "
            "DLUGIE postoje (obiad/zwiedzanie) NIE sa zgadywane - podaje je uzytkownik (planned_long_stops + planned_long_stop_min). "
            "Mikro i krotkie przerwy auto. Wiatr/pogoda osobno (meteo). Pokaz pole analysis w calosci."
        ),
        "args_schema": {
            "route_id": {"type": "string", "description": "ID zaplanowanej trasy (wymagane; dane kanoniczne z bazy)"},
            "mode": {"type": "string", "description": "Tryb/poziom: normalny (mediana, domyslny) / sport (asfalt p75) / wyscig (p90,p75)"},
            "planned_long_stops": {"type": "number", "description": "Liczba planowanych dlugich postojow (obiad/zwiedzanie); domyslnie 0"},
            "planned_long_stop_min": {"type": "number", "description": "Laczny czas dlugich postojow w minutach; domyslnie 0"},
            "start_time": {"type": "string", "description": "Godzina startu HH:MM (opcjonalnie, profil czasu zegarowego)"},
        },
        "safety": "read",
    }


def _load_route_list_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            from qbot3.routes.route_versions import list_all_routes, list_route_versions
            rid = str((args or {}).get("route_id") or "").strip()
            if rid:
                return success_result(list_route_versions(rid))
            return success_result({"routes": list_all_routes()})
        except Exception as exc:
            return error_result("ROUTE_LIST_FAILED", repr(exc))

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "Lista tras w bazie QBota (numer, nazwa, dystans, ile wersji, czy policzona). "
            "Uzyj gdy trzeba pokazac lub wybrac istniejaca trase albo sprawdzic ktore sa policzone. "
            "Z route_id zwraca wersje jednej trasy. NIE zmyslaj numerow tras - bierz je stad. Dok.: docs/ROUTE_STORE.md"
        ),
        "args_schema": {
            "route_id": {"type": "string", "description": "Opcjonalne; podane = wersje jednej trasy, brak = wszystkie trasy"},
        },
        "safety": "read",
        "mode": "read_only",
    }


def _load_route_recompute_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        rid = str((args or {}).get("route_id") or "").strip()
        if not rid:
            return error_result("ROUTE_RECOMPUTE_NEEDS_ID", "Podaj route_id trasy do przeliczenia.")
        scope_raw = str((args or {}).get("scope") or "all").strip().lower()
        scope = "poi" if scope_raw in {"poi", "poi_only", "poi-only", "tylko_poi", "tylko poi"} else "all"
        try:
            from qbot3.routes.route_precompute_orchestrator import ensure_route_precompute
            out = ensure_route_precompute(route_id=rid, trigger_source="albert_manual", scope=scope)
            note = (
                f"Odswiezono TYLKO POI aktywnej wersji trasy {rid} (reszta warstw nietknieta)."
                if scope == "poi"
                else f"Przeliczono cala aktywna wersje trasy {rid}."
            )
            return success_result({
                "route_id": rid,
                "scope": out.get("scope", scope),
                "route_version_key": out.get("route_version_key"),
                "job_count": out.get("job_count"),
                "retention": out.get("retention"),
                "note": note,
            })
        except Exception as exc:
            return error_result("ROUTE_RECOMPUTE_FAILED", repr(exc))

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "Recznie przelicza wskazana trase. scope='all' (domyslnie): PELNY przelicz aktywnej "
            "(najnowszej) wersji — osie, nawierzchnia, POI (+ opcj. cien/wysokosci); uzyj gdy trasa "
            "pobrana z RWGPS nie zostala jeszcze przeliczona albo po odmowie w Telegramie. "
            "scope='poi': odswieza WYLACZNIE POI (sklepy/woda/godziny) istniejacej, JUZ przeliczonej "
            "trasy, bez ruszania reszty warstw i bez przycinania wersji; uzyj gdy wracasz do "
            "policzonej trasy po czasie i chcesz tylko aktualne POI. WYMAGA route_id. Ciezka i "
            "zapisujaca; scope='all' zostawia 3 najnowsze wersje. Dok.: docs/ROUTE_STORE.md"
        ),
        "args_schema": {
            "route_id": {"type": "string", "description": "ID trasy RWGPS do przeliczenia (wymagane)"},
            "scope": {"type": "string", "description": "'all' = pelny przelicz (domyslnie) | 'poi' = odswiez tylko POI istniejacej, juz przeliczonej trasy"},
        },
        "safety": "write",
        "mode": "write",
    }


def _load_route_attractions_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        rid = str((args or {}).get("route_id") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", rid):
            return error_result("ROUTE_ATTRACTIONS_NEEDS_ID", "Podaj numer trasy (route_id).")
        raw = (args or {}).get("enable", True)
        if isinstance(raw, bool):
            enabled = raw
        else:
            enabled = str(raw).strip().lower() in {"on", "true", "1", "tak", "wlacz", "w\u0142\u0105cz", "yes", "enable", "pokaz", "poka\u017c"}
        try:
            from qbot3.routes.route_poi_store import set_route_poi_attractions
            pref = set_route_poi_attractions(rid, enabled)
            if enabled:
                from qbot3.routes.route_attraction_store import ensure_route_attractions
                out = ensure_route_attractions(route_id=rid)
                note = f"Wlaczono i przeliczono kanoniczne atrakcje (do 2 km) dla trasy {rid}."
            else:
                out = {"status": "DISABLED"}
                note = f"Wylaczono pokazywanie atrakcji dla trasy {rid}; sklepy, woda i jedzenie pozostaly bez zmian."
            return success_result({
                "route_id": rid,
                "attractions_enabled": pref.get("attractions_enabled"),
                "attractions_status": out.get("status"),
                "attractions_run_id": out.get("run_id"),
                "route_version_key": out.get("route_version_key"),
                "note": note,
            })
        except Exception as exc:
            return error_result("ROUTE_ATTRACTIONS_FAILED", repr(exc))

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "Wlacza lub wylacza kanoniczne ATRAKCJE dla wskazanej trasy. Wikipedia i Wikidata sa pierwszym sitem; "
            "Google dostarcza lokalizacje i pomocniczy sygnal rankingu. Korytarz do ok. 2 km, preferowane krotkie postoje "
            "historyczne. Wlaczenie przelicza tylko osobna warstwe atrakcji; nie odswieza sklepow, wody ani "
            "jedzenia. Wylaczenie tylko ukrywa atrakcje i takze nie rusza logistyki. WYMAGA route_id. Uzyj gdy user mowi "
            "np. 'wlacz/pokaz atrakcje dla trasy X' albo 'wylacz atrakcje dla trasy X'."
        ),
        "args_schema": {
            "route_id": {"type": "string", "description": "ID trasy RWGPS (wymagane)"},
            "enable": {"type": "boolean", "description": "true = wlacz atrakcje (domyslnie) | false = wylacz"},
        },
        "safety": "write",
        "mode": "write",
    }


def _load_route_delete_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        rid = str((args or {}).get("route_id") or "").strip()
        if not rid.isdigit():
            return error_result("ROUTE_DELETE_NEEDS_ID", "Podaj numer trasy (route_id) do skasowania.")
        confirm = bool((args or {}).get("confirm", False))
        try:
            from scripts.route_store_purge import purge_route
            return success_result(purge_route(rid, confirm=confirm))
        except Exception as exc:
            return error_result("ROUTE_DELETE_FAILED", repr(exc))

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "NIEODWRACALNE kasowanie CALEJ trasy z bazy po numerze (wszystkie wersje, warstwy, surowka i pliki; "
            "przejazdy zostaja, tylko odpiete). DWUSTOPNIOWO: BEZ confirm (domyslnie) zwraca PODGLAD co zniknie - "
            "pokaz go uzytkownikowi i POCZEKAJ na wyrazne 'tak/kasuj'. Dopiero potem wywolaj z confirm=true. "
            "WYMAGA route_id. Nie kasuj bez podgladu i zgody uzytkownika. Dok.: docs/ROUTE_STORE.md"
        ),
        "args_schema": {
            "route_id": {"type": "string", "description": "ID trasy RWGPS do skasowania (wymagane)"},
            "confirm": {"type": "boolean", "default": False, "description": "false=podglad; true=realne skasowanie (tylko po zgodzie uzytkownika)"},
        },
        "safety": "write",
        "mode": "write",
    }


def _load_route_plan_analysis_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result
    import qbot_route_tools as _rt

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        out = _rt._tool_qbot_route_plan_analysis(args or {})
        st = out.get("status")
        if st == "OK":
            return success_result({"analysis": out.get("analysis", ""), "note": out.get("notes", "")})
        if st == "WARN":
            return success_result({"analysis": out.get("notes", ""), "warning": out.get("notes", "")})
        return error_result("ROUTE_PLAN_ANALYSIS_FAILED", out.get("error") or out.get("notes") or "blad analizy trasy")

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "PELNA, gotowa analiza ZAPLANOWANEJ trasy (jeszcze nieprzejechanej; track z RWGPS). "
            "To DOMYSLNE i jedyne narzedzie do ogolnej analizy/oceny/sprawdzenia trasy: "
            "'przeanalizuj trase', 'pelna analiza trasy', 'analiza techniczna trasy', 'sprawdz trase', 'ocen trase', 'analiza planowanej trasy'. "
            "Zwraca komplet w jednym tekscie (pole analysis): nawierzchnia, podjazdy i przewyzszenie (kanoniczna os 50 m: DEM + warstwa nawierzchni), "
            "dopasowanie do aktualnej formy (FTP). POGODA/WIATR NIE sa w tym narzedziu - sa w route_report (silnik METEO). "
            "NIE lacz tego z rwgps_route_fetch, rwgps_route_surface_analyze ani route_poi_analyze — to narzedzie juz zawiera nawierzchnie i przewyzszenie. "
            "Dla JUZ PRZEJECHANEJ jazdy (plik FIT) uzyj ride_analysis, nie tego. "
            "Bez route_id bierze najnowsza otrasowana trase. Pokaz uzytkownikowi pole analysis w calosci, bez przerabiania."
        ),
        "args_schema": {
            "route_id": {"type": "string", "description": "ID trasy RWGPS (opcjonalne; domyslnie najnowsza otrasowana)"},
            "artifact_id": {"type": "integer", "description": "ID artefaktu trasy (opcjonalne)"},
            "start": {"type": "string", "description": "Start 'YYYY-MM-DD HH:MM' (opcjonalne; dolicza prognoze pogody)"},
        },
        "safety": "read",
        "mode": "read_only",
    }


def _load_ride_analysis_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result
    import qbot_route_tools as _rt

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        out = _rt._tool_qbot_ride_analysis(args or {})
        st = out.get("status")
        if st == "OK":
            return success_result({"analysis": out.get("analysis", ""), "note": out.get("notes", "")})
        if st == "WARN":
            return success_result({"analysis": out.get("notes", ""), "warning": out.get("notes", "")})
        return error_result("RIDE_ANALYSIS_FAILED", out.get("error") or out.get("notes") or "blad oceny jazdy")

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "Ocena JUZ PRZEJECHANEJ, WYKONANEJ jazdy na podstawie pliku FIT (Garmin/Hammerhead). "
            "Uzyj zawsze gdy mowa o przejechanej jezdzie: 'dzisiejsza jazda', 'wczorajsza jazda', "
            "'dzisiejsza trasa' / 'wczorajsza trasa' (czyli ta przejechana dzis/wczoraj), 'moja jazda', "
            "'jak mi poszlo', 'ocen przejazd', 'analiza dzisiejszej jazdy', 'analiza trasy dzisiejszej', 'podsumuj jazde'. "
            "Naklada FIT na plan (siatka 80 m), liczy roznice plan-wykonanie (moc/predkosc/wiatr) i werdykt wobec formy. "
            "WAZNE: slowa 'dzisiejsza/wczorajsza' przy slowie trasa oznaczaja jazde WYKONANA -> uzyj TEGO narzedzia, NIE route_plan_analysis. "
            "Bez argumentow bierze najnowszy FIT. Pokaz pole analysis w calosci."
        ),
        "args_schema": {
            "fit": {"type": "string", "description": "Sciezka do pliku FIT (opcjonalne; domyslnie najnowszy)"},
            "ride": {"type": "string", "description": "Klucz jazdy (opcjonalne; domyslnie 'latest')"},
        },
        "safety": "read",
        "mode": "read_only",
    }


def _load_route_profile_detail_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result
    import qbot_route_tools as _rt

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        out = _rt._tool_qbot_route_profile_detail(args or {})
        st = out.get("status")
        if st == "OK":
            return success_result({"analysis": out.get("analysis", ""), "note": out.get("notes", "")})
        if st == "WARN":
            return success_result({"analysis": out.get("notes", ""), "warning": out.get("notes", "")})
        return error_result("ROUTE_PROFILE_DETAIL_FAILED", out.get("error") or out.get("notes") or "blad profilu")

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "SZCZEGOLOWY profil ZAPLANOWANEJ trasy z kanonicznej osi 50 m (DEM + warstwa nawierzchni): nawierzchnia ODCINKAMI (km od-do z typem), "
            "profil wysokosci po kilometrach (delta netto) i lista podjazdow. "
            "Uzyj gdy uzytkownik chce ROZBICIE / szczegoly nawierzchni i przewyzszen 'km po km' / 'odcinek po odcinku', "
            "a nie samo podsumowanie procentowe (od tego jest route_plan_analysis). Bez route_id bierze najnowsza otrasowana trase. "
            "Opcjonalnie land_cover=true dodaje pokrycie terenu OSM per sektor."
        ),
        "args_schema": {
            "route_id": {"type": "string", "description": "ID trasy RWGPS (opcjonalne; domyslnie najnowsza otrasowana)"},
            "artifact_id": {"type": "integer", "description": "ID artefaktu trasy (opcjonalne)"},
            "land_cover": {"type": "boolean", "default": False, "description": "Dodaje pokrycie terenu OSM per sektor: las/pola/laki/zabudowa/woda + podsumowanie"},
        },
        "safety": "read",
        "mode": "read_only",
    }


def _load_tire_pressure_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result
    import qbot_pressure_tools as _pt

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        out = _pt._tool_qbot_tire_pressure(args or {})
        st = out.get("status")
        if st == "OK":
            return success_result({"analysis": out.get("analysis", ""), "note": out.get("notes", "")})
        return error_result("TIRE_PRESSURE_FAILED", out.get("error") or "blad kalkulatora cisnien")

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "B5 - kalkulator CISNIENIA OPON (punkt startowy). Uzyj przy pytaniu o cisnienie opon "
            "('na ile napompowac', 'jakie cisnienie', 'cisnienie opon'). Liczy przod/tyl dla OBU zestawow "
            "kol w bar i psi: <=42 mm Berto, >=42 mm Heine (surface-aware, baza Rene Herse). Waga zawodnika "
            "z body_measurements, masa roweru z garazu. Param: weight_kg, bike_weight_kg, width1_mm, width2_mm, "
            "surface (asfalt/szuter_gladki/szuter_luzny/techniczny). Pokaz pole analysis w calosci."
        ),
        "args_schema": {
            "width1_mm": {"type": "number", "description": "Szerokosc opony zestaw #1 mm (opcjonalne; nadpisuje oponę odczytaną z garażu)"},
            "width2_mm": {"type": "number", "description": "Szerokosc opony zestaw #2 mm (opcjonalne; nadpisuje oponę odczytaną z garażu)"},
            "surface": {"type": "string", "description": "Nawierzchnia: asfalt/szuter_gladki/szuter_luzny/techniczny (opcjonalne)"},
            "weight_kg": {"type": "number", "description": "Waga zawodnika kg (opcjonalne; domyslnie body_measurements)"},
            "bike_weight_kg": {"type": "number", "description": "Masa roweru kg (opcjonalne; domyslnie garaz lub 10)"},
            "extra_load_kg": {"type": "number", "description": "Dodatkowy ladunek kg (opcjonalne)"},
        },
        "safety": "read",
        "mode": "read_only",
    }


def _load_route_fuel_plan_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result
    import qbot_fuel_tools as _ft

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        out = _ft._tool_qbot_route_fuel_plan(args or {})
        if out.get("status") == "OK":
            return success_result({
                "analysis": out.get("analysis", ""),
                "note": out.get("notes", ""),
                "data": out.get("data", {}),
            })
        return error_result("ROUTE_FUEL_PLAN_FAILED",
                            out.get("error") or "blad kalkulatora zywienia trasy")

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "Plan zywienia na ZAPLANOWANA trase: B2 plyny (L/h) + B3 wegle (g/h). "
            "Mirror 1:1 wzorow QExt2, karmiony estymatami planu: if_target, vi, "
            "temp_c/humidity_pct (z prognozy A5), duration_h (z B4), body_kg (z body_measurements). "
            "Zwraca gotowe sekcje B2/B3 w polu analysis — pokaz w calosci. "
            "B1 (%FTP) pominiete. Bez parametrow uzywa domyslnych i zaznacza zaleznosci A5/B4."
        ),
        "args_schema": {
            "if_target": {"type": "number", "description": "Planowany target IF (0.4-1.1; domyslnie 0.70)"},
            "vi": {"type": "number", "description": "Variability Index (domyslnie 1.05; gravel ~1.05-1.10)"},
            "duration_h": {"type": "number", "description": "Czas jazdy w h (z B4; domyslnie 3.0 — ZALEZNOSC)"},
            "temp_c": {"type": "number", "description": "Temperatura C z prognozy A5 (brak -> mnoznik 1.00)"},
            "humidity_pct": {"type": "number", "description": "Wilgotnosc % z prognozy A5 (brak -> 1.00)"},
            "body_kg": {"type": "number", "description": "Waga zawodnika kg (domyslnie z body_measurements)"},
        },
        "safety": "read",
        "mode": "read_only",
    }

def _load_route_report_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result
    import qbot_route_report_tool as _rr

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        out = _rr._tool_route_report(args or {})
        if out.get("status") == "OK":
            return success_result({
                "analysis": out.get("analysis", ""),
                "variant": out.get("variant"),
                "route_id": out.get("route_id"),
                "context_for_section_c": out.get("context_for_section_c"),
                "note": out.get("notes", ""),
            })
        return error_result("ROUTE_REPORT_FAILED",
                            out.get("error") or out.get("notes") or "blad raportu trasy")

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "Znormalizowany RAPORT TRASY - orkiestrator: skleja gotowe narzedzia w 3 warianty "
            "(skrocony domyslny / pelny / grupa). Triggery: 'analizuj trase X', 'zrob raport trasy X', 'raport trasy'. "
            "skrocony=dystans+czas+nawierzchnia+pogoda+wiatr+cisnienia; pelny=pelne sekcje A/B + C; "
            "grupa=trasa+warunki+logistyka BEZ danych osobistych. Param: variant, route_id, start. "
            "Pokaz analysis w calosci; sekcje C uzupelnij sam."
        ),
        "args_schema": {
            "variant": {"type": "string", "description": "skrocony (domyslny) / pelny / grupa"},
            "route_id": {"type": "string", "description": "ID trasy RWGPS (opcjonalne; domyslnie najnowsza otrasowana)"},
            "start": {"type": "string", "description": "Start 'YYYY-MM-DD HH:MM' (opcjonalne; dolicza pogode i okno POI)"},
            "surface_detail": {"type": "boolean", "description": "true = pelna tabela nawierzchni po ramkach 80 m; domyslnie false (scalone zmiany >=300 m)"},
        },
        "safety": "read",
        "mode": "read_only",
    }


def _load_route_analysis_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result
    import qbot_route_analysis_tool as _ra

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        out = _ra._tool_route_analysis(args or {})
        if out.get("status") == "OK":
            return success_result({
                "analysis": out.get("analysis", ""),
                "variant": out.get("variant"),
                "route_id": out.get("route_id"),
                "note": out.get("notes", ""),
            })
        return error_result("ROUTE_ANALYSIS_FAILED",
                            out.get("error") or out.get("notes") or "blad analizy trasy")

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "PELNA ANALIZA TRASY (jednowarstwowa analiza LLM). Buduje jeden kontekst "
            "(trasa, zawodnik, sprzet, POI z km, zywienie, czas) i robi spojna analize sekcji A-F. "
            "Triggery: 'analizuj trase X', 'pelna analiza trasy X', 'przeanalizuj trase X'. "
            "Warianty: skrocony (A+C+F) / pelny (A-F) / grupa (A+B+D+F bez danych osobistych). "
            "Param: variant, route_id, start. Pokaz pole analysis w calosci."
        ),
        "args_schema": {
            "variant": {"type": "string", "description": "skrocony / pelny / grupa"},
            "route_id": {"type": "string", "description": "ID trasy RWGPS (opcjonalne; domyslnie najnowsza otrasowana)"},
            "start": {"type": "string", "description": "Start YYYY-MM-DD HH:MM (opcjonalne; dolicza pogode i okno POI)"},
        },
        "safety": "read",
        "mode": "read_only",
    }


def lookup(name: str, allow_legacy: bool = False) -> dict[str, Any] | None:
    _init_registry()
    spec = _TOOL_REGISTRY.get(name)
    if spec is None:
        return None
    if not allow_legacy and spec.get("status") == "legacy":
        return None
    return spec


def list_read_tools(include_legacy: bool = False) -> dict[str, dict[str, Any]]:
    _init_registry()
    if include_legacy:
        return dict(_READ_ONLY_TOOLS)
    return {n: s for n, s in _READ_ONLY_TOOLS.items() if s.get("status") != "legacy"}


def list_write_tools() -> dict[str, dict[str, Any]]:
    _init_registry()
    return dict(_WRITE_TOOLS)


def list_all_tools(include_legacy: bool = False) -> dict[str, dict[str, Any]]:
    _init_registry()
    if include_legacy:
        return dict(_TOOL_REGISTRY)
    return {n: s for n, s in _TOOL_REGISTRY.items() if s.get("status") != "legacy"}


def tool_descriptions() -> list[dict[str, Any]]:
    _init_registry()
    return [
        {
            "name": name,
            "category": spec.get("category", ""),
            "description": spec.get("description", ""),
            "args_schema": spec.get("args_schema", {}),
            "safety": spec.get("safety", "read"),
            "mode": spec.get("mode", "read_only"),
            "status": spec.get("status", "implemented"),
            "notes": spec.get("notes", ""),
        }
        for name, spec in sorted(_TOOL_REGISTRY.items())
        if "error" not in spec and spec.get("status") != "legacy"
    ]



def _load_route_wbgt_tool() -> dict[str, Any]:
    from qbot3.errors import error_result, success_result
    import qbot_wbgt_tools as _wbgt

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        out = _wbgt._tool_qbot_route_wbgt(args or {})
        if out.get("status") == "OK":
            return success_result({
                "analysis": out.get("analysis", ""),
                "note": out.get("notes", ""),
                "summary": out.get("data", {}),
            })
        return error_result("ROUTE_WBGT_FAILED", out.get("error") or "blad WBGT")

    return {
        "callable": _wrapper,
        "category": "routes",
        "description": (
            "WBGT (Wet Bulb Globe Temperature) - obciazenie cieplne na trasie w pelnym sloncu. "
            "Uzyj przy pytaniu o upal / przegrzanie / obciazenie cieplne / czy bezpiecznie jechac w upale. "
            "Model Liljegren (KNMI) z radiacja sloneczna z Open-Meteo - dokladniejszy niz feels_like. "
            "Param: lat, lon (wymagane), date (YYYY-MM-DD UTC, domyslnie dzis), "
            "from/to (HH:MM UTC, opcjonalne okno przejazdu). "
            "Zwraca szczyt WBGT, strefe ryzyka (ACSM) i rozklad godzinowy. Czas UTC. Pokaz pole analysis."
        ),
        "args_schema": {
            "lat": {"type": "number", "description": "szerokosc geograficzna punktu"},
            "lon": {"type": "number", "description": "dlugosc geograficzna punktu"},
            "date": {"type": "string", "description": "data YYYY-MM-DD (UTC), domyslnie dzis"},
            "from": {"type": "string", "description": "poczatek okna przejazdu HH:MM (UTC)"},
            "to": {"type": "string", "description": "koniec okna przejazdu HH:MM (UTC)"},
        },
        "safety": "read",
        "mode": "read_only",
    }
