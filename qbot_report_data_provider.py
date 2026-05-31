#!/usr/bin/env python3
"""ReportDataProvider — central data access layer for all QBot reports.

Reads exclusively from local PostgreSQL DB (qbot_v2.* then public.*).
No hardcoded paths, no direct Intervals.icu calls from report modules.
Returns structured data with source, freshness, missing_fields, confidence.

Usage:
    provider = ReportDataProvider()
    daily = provider.get_daily_report_data(date)
    ride = provider.get_ride_report_data(activity_id)
    source_freshness = provider.get_source_freshness(date)
"""

from __future__ import annotations

import os
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------

def _db_conn():
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=5,
    )


def _safe_fetch(cur, sql: str, params: tuple = ()) -> list[dict]:
    try:
        cur.execute(sql, params)
        rows = cur.fetchall()
        if not rows:
            return []
        cols = [d[0] for d in cur.description] if cur.description else []
        result = []
        for row in rows:
            if isinstance(row, dict):
                result.append(dict(row))
            else:
                result.append(dict(zip(cols, row)))
        return result
    except Exception:
        return []


def _safe_fetch_one(cur, sql: str, params: tuple = ()) -> dict | None:
    rows = _safe_fetch(cur, sql, params)
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Source freshness check
# ---------------------------------------------------------------------------

_MAX_FRESHNESS_HOURS: dict[str, int] = {
    "sleep": 24,
    "wellness": 24,
    "energy": 24,
    "nutrition": 48,
    "training": 48,
    "body_comp": 72,
    "xert": 72,
}


def _is_fresh(row_date: date | None, max_hours: int) -> str:
    if row_date is None:
        return "missing"
    delta = (date.today() - row_date).days
    if delta < 0:
        return "fresh"
    if delta == 0:
        return "fresh"
    if delta == 1 and max_hours >= 24:
        return "stale"
    return "missing"


def _freshness_label(freshness: str) -> str:
    return {
        "fresh": "ok",
        "stale": "stale",
        "missing": "missing",
    }.get(freshness, "unknown")


# ===================================================================
# ReportDataProvider
# ===================================================================

class ReportDataProvider:
    """Single entry point for all report data reads.

    All methods return a dict with keys:
      - data: the actual record(s)
      - source: which table/schema provided the data
      - freshness: 'fresh' | 'stale' | 'missing'
      - missing_fields: list of fields that are None
      - status: 'ok' | 'partial' | 'missing'
    """

    # ------------------------------------------------------------------
    # Daily report data
    # ------------------------------------------------------------------

    def get_daily_report_data(self, target_date: date | None = None) -> dict[str, Any]:
        """Aggregate all data needed for the daily report.

        Returns a single dict with typed sub-dicts:
          - date
          - sleep
          - wellness
          - energy (calories expended)
          - nutrition
          - activity_summary
          - body_composition
          - validation (computed from the above)
        """
        d = target_date or date.today()
        ds = d.isoformat()
        yesterday = d - timedelta(days=1)
        yds = yesterday.isoformat()

        result: dict[str, Any] = {
            "date": ds,
            "sleep": self._source_missing("sleep"),
            "wellness": self._source_missing("wellness"),
            "energy": self._source_missing("energy"),
            "nutrition": self._source_missing("nutrition"),
            "activity_summary": self._source_missing("activity"),
            "body_composition": self._source_missing("body_comp"),
            "xert": self._source_missing("xert"),
            "validation": {"status": "unknown", "missing_fields": []},
        }

        try:
            conn = _db_conn()
            cur = conn.cursor()

            # ── Sleep ──
            row = _safe_fetch_one(cur,
                "SELECT * FROM qbot_v2.sleep_daily WHERE date = %s", (ds,))
            if not row or row.get("duration_min") is None:
                row = _safe_fetch_one(cur,
                    "SELECT * FROM qbot_v2.sleep_daily WHERE date = %s", (yds,))
            if row and row.get("duration_min") is not None:
                f_id = row.get("date")
                result["sleep"] = {
                    "data": dict(row),
                    "source": "qbot_v2.sleep_daily",
                    "freshness": "fresh" if str(f_id) in (ds, yds) else "stale",
                    "missing_fields": [],
                    "status": "ok",
                    "czas_h": round(row["duration_min"] / 60, 1) if row.get("duration_min") else None,
                    "score": row.get("score"),
                    "hrv_ms": row.get("hrv_ms"),
                    "resting_hr_bpm": row.get("resting_hr_bpm"),
                }
            else:
                # Fallback to public
                row = _safe_fetch_one(cur,
                    "SELECT * FROM public.qbot_sleep_daily WHERE date = %s", (ds,))
                if row and row.get("sleep_duration_min") is not None:
                    result["sleep"] = {
                        "data": dict(row),
                        "source": "public.qbot_sleep_daily",
                        "freshness": "fresh",
                        "missing_fields": [],
                        "status": "ok",
                        "czas_h": round(row["sleep_duration_min"] / 60, 1) if row.get("sleep_duration_min") else None,
                        "score": row.get("sleep_score"),
                        "hrv_ms": row.get("hrv_ms"),
                        "resting_hr_bpm": row.get("resting_hr_bpm"),
                    }

            # ── Wellness ──
            row = _safe_fetch_one(cur,
                "SELECT * FROM qbot_v2.wellness_daily WHERE date = %s", (ds,))
            if not row or all(row.get(k) is None for k in ("hrv_ms", "resting_hr_bpm", "body_battery_start", "stress_avg")):
                row = _safe_fetch_one(cur,
                    "SELECT * FROM public.qbot_wellness_daily WHERE date = %s", (ds,))
            if row and any(row.get(k) is not None for k in ("hrv_ms", "resting_hr_bpm", "body_battery_start", "stress_avg")):
                mf = [k for k in ("hrv_ms", "resting_hr_bpm", "body_battery_start", "body_battery_end", "stress_avg", "weight_kg") if row.get(k) is None]
                src = "qbot_v2.wellness_daily" if row.get("imported_at") else "public.qbot_wellness_daily"
                result["wellness"] = {
                    "data": dict(row),
                    "source": src,
                    "freshness": "fresh",
                    "missing_fields": mf,
                    "status": "partial" if mf else "ok",
                    "hrv_ms": row.get("hrv_ms"),
                    "resting_hr_bpm": row.get("resting_hr_bpm"),
                    "body_battery_start": row.get("body_battery_start"),
                    "body_battery_end": row.get("body_battery_end"),
                    "stress_avg": row.get("stress_avg"),
                    "weight_kg": row.get("weight_kg"),
                }

            # ── Energy (calories) ──
            row = _safe_fetch_one(cur,
                "SELECT * FROM qbot_v2.energy_daily WHERE date = %s", (ds,))
            if not row or row.get("total_kcal") is None:
                row = _safe_fetch_one(cur,
                    "SELECT * FROM public.daily_energy_expenditure WHERE date = %s", (ds,))
            if row and row.get("total_kcal") is not None:
                mf = [k for k in ("total_kcal", "active_kcal", "resting_kcal", "steps") if row.get(k) is None]
                result["energy"] = {
                    "data": dict(row),
                    "source": "qbot_v2.energy_daily" if "snapshot_at" in (row or {}) else "public.daily_energy_expenditure",
                    "freshness": "fresh",
                    "missing_fields": mf,
                    "status": "partial" if mf else "ok",
                    "total_kcal": row.get("total_kcal") or row.get("kcal_burned_total") or row.get("total_kcal_out"),
                    "active_kcal": row.get("active_kcal") or row.get("active_kcal_out"),
                    "resting_kcal": row.get("resting_kcal") or row.get("resting_kcal_out"),
                    "steps": row.get("steps"),
                }

            # ── Nutrition ──
            row = _safe_fetch_one(cur,
                "SELECT * FROM qbot_v2.nutrition_daily_summary WHERE date = %s", (ds,))
            if not row or row.get("kcal_total") is None:
                row = _safe_fetch_one(cur,
                    "SELECT * FROM public.nutrition_daily_summary WHERE date = %s", (ds,))
            if row and row.get("kcal_total") is not None:
                mf = [k for k in ("kcal_total", "carbs_total", "protein_total", "fat_total") if row.get(k) is None]
                result["nutrition"] = {
                    "data": dict(row),
                    "source": "qbot_v2.nutrition_daily_summary" if "computed_at" in (row or {}) else "public.nutrition_daily_summary",
                    "freshness": "fresh",
                    "missing_fields": mf,
                    "status": "partial" if mf else "ok",
                    "kcal_total": row.get("kcal_total"),
                    "carbs_total": row.get("carbs_total"),
                    "protein_total": row.get("protein_total"),
                    "fat_total": row.get("fat_total"),
                }

            # ── Activity summary (today's training sessions) ──
            rows = _safe_fetch(cur,
                "SELECT * FROM qbot_v2.training_sessions WHERE date = %s ORDER BY started_at DESC LIMIT 10", (ds,))
            if not rows:
                rows = _safe_fetch(cur,
                    "SELECT * FROM public.training_sessions WHERE date = %s ORDER BY started_at DESC LIMIT 10", (ds,))
            if rows:
                result["activity_summary"] = {
                    "data": rows,
                    "source": "qbot_v2.training_sessions" if "external_id" in (rows[0] or {}) else "public.training_sessions",
                    "freshness": "fresh",
                    "missing_fields": [],
                    "status": "ok",
                    "count": len(rows),
                    "total_duration_s": sum(r.get("duration_s") or 0 for r in rows),
                    "total_distance_m": sum(r.get("distance_m") or 0 for r in rows),
                    "total_elevation_m": sum(r.get("elevation_m") or 0 for r in rows),
                    "activities": rows,
                }

            # ── Body composition ──
            row = _safe_fetch_one(cur,
                "SELECT * FROM qbot_v2.body_measurements WHERE date = %s", (ds,))
            if not row:
                row = _safe_fetch_one(cur,
                    "SELECT * FROM public.body_composition WHERE date = %s", (ds,))
            if row and row.get("weight_kg") is not None:
                mf = [k for k in ("weight_kg", "body_fat_pct", "bmi") if row.get(k) is None]
                result["body_composition"] = {
                    "data": dict(row),
                    "source": "qbot_v2.body_measurements" if "completeness_score" in (row or {}) else "public.body_composition",
                    "freshness": "fresh",
                    "missing_fields": mf,
                    "status": "partial" if mf else "ok",
                    "weight_kg": row.get("weight_kg"),
                    "body_fat_pct": row.get("body_fat_pct"),
                    "bmi": row.get("bmi"),
                }

            # ── Xert ──
            row = _safe_fetch_one(cur,
                "SELECT * FROM qbot_v2.xert_profile_snapshots ORDER BY snapshot_at DESC NULLS LAST LIMIT 1")
            if row and row.get("ftp_power_w") is not None:
                result["xert"] = {
                    "data": dict(row),
                    "source": "qbot_v2.xert_profile_snapshots",
                    "freshness": "fresh",
                    "missing_fields": [],
                    "status": "ok",
                    "ftp_power_w": row.get("ftp_power_w"),
                    "ltp_power_w": row.get("ltp_power_w"),
                    "w_prime_kj": row.get("w_prime_kj"),
                    "form_status": row.get("form_status"),
                }

            conn.close()
        except Exception as exc:
            result["_error"] = str(exc)
            return result

        # ── Compute validation ──
        missing_fields = []
        for key in ("sleep", "wellness", "energy", "nutrition", "activity_summary", "body_composition"):
            if result[key].get("status") == "missing":
                missing_fields.append(key)
            elif result[key].get("status") == "partial":
                missing_fields.append(f"{key}(partial)")

        if not missing_fields:
            result["validation"] = {"status": "DATA_OK", "missing_fields": []}
        elif len(missing_fields) <= 3:
            result["validation"] = {"status": "DATA_PARTIAL", "missing_fields": missing_fields}
        else:
            result["validation"] = {"status": "DATA_MISSING", "missing_fields": missing_fields}

        return result

    # ------------------------------------------------------------------
    # Ride report data
    # ------------------------------------------------------------------

    def get_ride_report_data(self, activity_id: str | int | None = None) -> dict[str, Any]:
        """Fetch ride/activity data for the ride report.

        If activity_id is None, tries to find the latest ride from today.
        """
        d = date.today()
        ds = d.isoformat()
        yesterday = (d - timedelta(days=1)).isoformat()

        result: dict[str, Any] = {
            "activity_id": activity_id,
            "aktywnosc": self._source_missing("activity"),
            "wellness": self._source_missing("wellness"),
            "xert": self._source_missing("xert"),
            "validation": {"status": "unknown", "missing_fields": []},
        }

        try:
            conn = _db_conn()
            cur = conn.cursor()

            training_rows = _safe_fetch(cur,
                "SELECT * FROM qbot_v2.training_sessions WHERE date >= %s ORDER BY date DESC, started_at DESC LIMIT 20",
                (yesterday,))
            if not training_rows:
                training_rows = _safe_fetch(cur,
                    "SELECT * FROM public.training_sessions WHERE date >= %s ORDER BY date DESC, started_at DESC LIMIT 20",
                    (yesterday,))

            # Find the matching activity
            act_row = None
            if activity_id is not None:
                for r in training_rows:
                    if str(r.get("id")) == str(activity_id) or str(r.get("external_id", "")) == str(activity_id):
                        act_row = r
                        break
            if act_row is None and training_rows:
                act_row = training_rows[0]
                if activity_id is None:
                    activity_id = act_row.get("id")

            if act_row:
                dist_m = act_row.get("distance_m") or 0
                dur_s = act_row.get("duration_s") or 0
                elev_m = act_row.get("elevation_m") or 0

                mf = []
                if not dist_m:
                    mf.append("distance_m")
                if not dur_s:
                    mf.append("duration_s")
                if not elev_m:
                    mf.append("elevation_m")
                if act_row.get("avg_power_w") is None:
                    mf.append("avg_power_w")
                if act_row.get("avg_hr_bpm") is None:
                    mf.append("avg_hr_bpm")

                fit_source = "intervals_icu"
                if act_row.get("external_id"):
                    # Check if FIT data is available
                    fit_streams_available = bool(act_row.get("external_id"))
                    if fit_streams_available:
                        fit_source = "FIT"

                result["aktywnosc"] = {
                    "data": dict(act_row),
                    "source": f"qbot_v2.training_sessions ({fit_source})",
                    "freshness": "fresh",
                    "missing_fields": mf,
                    "status": "partial" if mf else "ok",
                    "id": act_row.get("id"),
                    "date": str(act_row.get("date", "")),
                    "sport_type": act_row.get("sport_type"),
                    "distance_m": dist_m,
                    "duration_s": dur_s,
                    "elevation_m": elev_m,
                    "avg_power_w": act_row.get("avg_power_w"),
                    "normalized_power_w": act_row.get("normalized_power_w"),
                    "avg_hr_bpm": act_row.get("avg_hr_bpm"),
                    "max_hr_bpm": act_row.get("max_hr_bpm"),
                    "tss": act_row.get("tss"),
                    "fit_streams_source": fit_source,
                }

                act_date_str = str(act_row.get("date", ds))
                # Get wellness for that date
                w_row = _safe_fetch_one(cur,
                    "SELECT * FROM qbot_v2.wellness_daily WHERE date = %s", (act_date_str,))
                if not w_row:
                    w_row = _safe_fetch_one(cur,
                        "SELECT * FROM public.qbot_wellness_daily WHERE date = %s", (act_date_str,))
                if w_row:
                    result["wellness"] = {
                        "data": dict(w_row),
                        "source": "qbot_v2.wellness_daily" if "imported_at" in (w_row or {}) else "public.qbot_wellness_daily",
                        "freshness": "fresh",
                        "missing_fields": [],
                        "status": "ok",
                        "hrv_ms": w_row.get("hrv_ms"),
                        "resting_hr_bpm": w_row.get("resting_hr_bpm"),
                        "body_battery_start": w_row.get("body_battery_start"),
                        "sleep_secs": w_row.get("sleep_duration_min"),
                    }

            conn.close()
        except Exception as exc:
            result["_error"] = str(exc)
            return result

        # ── Compute validation ──
        act = result["aktywnosc"]
        if act.get("status") == "missing":
            result["validation"] = {
                "status": "DATA_MISSING",
                "missing_fields": ["activity_data"],
                "alert": "Brak danych aktywno\u015bci w lokalnej bazie.",
            }
        elif act.get("missing_fields"):
            result["validation"] = {
                "status": "DATA_PARTIAL",
                "missing_fields": act["missing_fields"],
                "alert": "Raport cz\u0119\u015bciowy: " + ", ".join(act["missing_fields"]),
            }
        else:
            result["validation"] = {"status": "DATA_OK", "missing_fields": []}

        return result

    # ------------------------------------------------------------------
    # Source freshness (for diagnostics)
    # ------------------------------------------------------------------

    def get_source_freshness(self, target_date: date | None = None) -> dict[str, Any]:
        """Check freshness of all data sources.

        Returns dict with source name -> {date, freshness, status}.
        """
        d = target_date or date.today()
        ds = d.isoformat()

        result: dict[str, dict] = {}
        try:
            conn = _db_conn()
            cur = conn.cursor()

            checks = [
                ("qbot_v2.sleep_daily", "SELECT MAX(date) FROM qbot_v2.sleep_daily"),
                ("qbot_v2.wellness_daily", "SELECT MAX(date) FROM qbot_v2.wellness_daily"),
                ("qbot_v2.energy_daily", "SELECT MAX(date) FROM qbot_v2.energy_daily"),
                ("qbot_v2.training_sessions", "SELECT MAX(date) FROM qbot_v2.training_sessions"),
                ("qbot_v2.nutrition_daily_summary", "SELECT MAX(date) FROM qbot_v2.nutrition_daily_summary"),
                ("qbot_v2.body_measurements", "SELECT MAX(date) FROM qbot_v2.body_measurements"),
                ("qbot_v2.xert_profile_snapshots", "SELECT MAX(date) FROM qbot_v2.xert_profile_snapshots"),
                ("public.nutrition_daily_summary", "SELECT MAX(date) FROM public.nutrition_daily_summary"),
                ("public.qbot_wellness_daily", "SELECT MAX(date) FROM public.qbot_wellness_daily"),
                ("public.qbot_sleep_daily", "SELECT MAX(date) FROM public.qbot_sleep_daily"),
                ("public.body_composition", "SELECT MAX(date) FROM public.body_composition"),
                ("public.training_sessions", "SELECT MAX(date) FROM public.training_sessions"),
                ("public.daily_energy_expenditure", "SELECT MAX(date) FROM public.daily_energy_expenditure"),
            ]

            for name, sql in checks:
                try:
                    cur.execute(sql)
                    r = cur.fetchone()
                    max_date = r[0] if r and r[0] else None
                    freshness = "missing"
                    if max_date:
                        if isinstance(max_date, date):
                            max_d = max_date
                        else:
                            max_d = date.fromisoformat(str(max_date)[:10])
                        delta_days = (d - max_d).days
                        if delta_days <= 1:
                            freshness = "fresh"
                        elif delta_days <= 3:
                            freshness = "stale"
                        else:
                            freshness = "old"
                    result[name] = {
                        "latest_date": str(max_date)[:10] if max_date else None,
                        "freshness": freshness,
                    }
                except Exception as e:
                    result[name] = {"error": str(e)[:80]}

            conn.close()
        except Exception as exc:
            return {"_error": str(exc)}

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _source_missing(self, name: str) -> dict:
        return {"data": None, "source": None, "freshness": "missing", "missing_fields": [], "status": "missing"}


# ===================================================================
# Module-level convenience
# ===================================================================

def get_provider() -> ReportDataProvider:
    return ReportDataProvider()
