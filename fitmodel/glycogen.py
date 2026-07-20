from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
from fitparse import FitFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import psycopg2
except ModuleNotFoundError:  # pragma: no cover - runtime fallback for this venv
    import psycopg as psycopg2


ENV_FILE = Path("/etc/qbot/qbot-api.env")
DEFAULT_CHO_ABSORPTION = 0.85
DEFAULT_GLYCOGEN_DRAIN = 110.0
DEFAULT_CAPACITY_PER_KG = 9.0
DEFAULT_WEIGHT_KG = 70.0

# Fizjologia / jednostki
GROSS_EFFICIENCY = 0.23        # sprawnosc brutto (moc mech / metaboliczna)
J_PER_KCAL = 4184.0           # dzul -> kcal (BRAK tej konwersji byl bledem: burn x4184 za duzy)
KCAL_PER_G_CHO = 4.0          # kcal na gram weglowodanow

# Ocena kompletnosci logu jedzenia (do flagi confidence)
DEFAULT_BMR_KCAL = 1877.0     # fallback (Mifflin-St Jeor M, 175 cm, ~47 lat, ~100 kg)
NONEX_FACTOR = 1.4            # calkowity wydatek poza jazda = NONEX x BMR
COMPLETE_LOG_FRAC = 0.6       # log uznany za kompletny gdy zalogowane kcal >= 60% wydatku dnia


def _load_env_file(env_path: Path = ENV_FILE) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _db_connect():
    _load_env_file()
    kwargs: dict[str, Any] = {
        "host": os.getenv("PGHOST", "127.0.0.1"),
        "port": int(os.getenv("PGPORT", "5432")),
        "user": os.getenv("PGUSER", "qbot"),
        "dbname": os.getenv("PGDATABASE", "qbot"),
    }
    password = os.getenv("PGPASSWORD")
    if password:
        kwargs["password"] = password
    return psycopg2.connect(**kwargs)


def _coerce_date(value: date | datetime | str | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _get_field_value(message: Any, field_name: str) -> Any:
    try:
        if hasattr(message, "get_value"):
            return message.get_value(field_name)
    except Exception:
        pass
    try:
        for field in getattr(message, "fields", []):
            if getattr(field, "name", None) == field_name:
                return getattr(field, "value", None)
    except Exception:
        pass
    return None


def _parse_fit_rows(fit_path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        fit = FitFile(fit_path)
        for message in fit.get_messages("record"):
            timestamp = _get_field_value(message, "timestamp")
            if timestamp is None:
                continue
            if isinstance(timestamp, datetime):
                timestamp = timestamp.replace(microsecond=0)
            rows.append(
                {
                    "timestamp": timestamp,
                    "power": _get_field_value(message, "power"),
                }
            )
    except Exception:
        return []
    rows.sort(key=lambda row: row["timestamp"])
    return rows


def cho_fraction(pct_ftp: float) -> float:
    if pct_ftp <= 0.55:
        return 0.50
    if pct_ftp <= 0.75:
        return 0.50 + (pct_ftp - 0.55) * (0.75 - 0.50) / (0.75 - 0.55)
    if pct_ftp <= 1.00:
        return 0.75 + (pct_ftp - 0.75) * (0.95 - 0.75) / (1.00 - 0.75)
    return 0.95


def compute_cho_burn_ride(fit_path: str, ftp_w: float) -> float:
    rows = _parse_fit_rows(fit_path)
    return _compute_cho_burn_rows(rows, ftp_w)


def _compute_cho_burn_rows(rows: list[dict[str, Any]], ftp_w: float) -> float:
    """Weglowodany [g] spalone na jezdzie z serii mocy 1 Hz.

    Na sekunde: moc metaboliczna = moc / sprawnosc [J/s]; -> kcal (/4184);
    frakcja CHO wg %FTP; -> gramy (/4 kcal/g).
    (Wczesniej brakowalo /4184 -> burn byl ~4184x za duzy, zerujac bak co jazde.)
    """
    power_values = [row["power"] for row in rows if row.get("power") is not None]
    if not power_values or ftp_w in (None, 0):
        return 0.0

    total = 0.0
    for row in rows:
        power = row.get("power")
        if power is None:
            continue
        power_w = float(power)
        pct_ftp = power_w / float(ftp_w)
        kcal_per_sec = (power_w / GROSS_EFFICIENCY) / J_PER_KCAL
        cho_per_sec = kcal_per_sec * cho_fraction(pct_ftp) / KCAL_PER_G_CHO
        total += float(cho_per_sec)
    return float(total)


def _compute_ride_kcal_rows(rows: list[dict[str, Any]]) -> float:
    """Calkowity wydatek metaboliczny jazdy [kcal] z serii mocy (do oceny logu)."""
    total = 0.0
    for row in rows:
        power = row.get("power")
        if power is None:
            continue
        total += (float(power) / GROSS_EFFICIENCY) / J_PER_KCAL
    return float(total)


def load_params(db_conn) -> dict[str, float]:
    with db_conn.cursor() as cur:
        cur.execute("SELECT key, value FROM qbot_v2.fitmodel_param")
        params: dict[str, float] = {}
        for key, value in cur.fetchall():
            if key is None or value is None:
                continue
            try:
                params[str(key)] = float(value)
            except Exception:
                continue
    return params


def load_cho_intake(db_conn, day: date) -> float:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(ii.carbs_g), 0)
            FROM qbot_v2.intake_logs il
            JOIN qbot_v2.intake_items ii ON il.id = ii.intake_log_id
            WHERE il.date = %s
            """,
            (day,),
        )
        row = cur.fetchone()
    if not row or row[0] is None:
        return 0.0
    return float(row[0])


def load_logged_kcal(db_conn, day: date) -> float:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(ii.kcal), 0)
            FROM qbot_v2.intake_logs il
            JOIN qbot_v2.intake_items ii ON il.id = ii.intake_log_id
            WHERE il.date = %s
            """,
            (day,),
        )
        row = cur.fetchone()
    if not row or row[0] is None:
        return 0.0
    return float(row[0])


def _has_intake_log(db_conn, day: date) -> bool:
    """Czy dla dnia jest JAKIKOLWIEK wpis zywienia (odroznia 'brak logu' od '0 g')."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT 1 FROM qbot_v2.intake_logs WHERE date=%s LIMIT 1", (day,))
        return cur.fetchone() is not None


def load_bmr_kcal(db_conn, weight_kg: float, day_value: date) -> float:
    """BMR (Mifflin-St Jeor) z athlete_profile + waga; fallback do stalej."""
    try:
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT sex, height_cm, birth_year FROM qbot_v2.athlete_profile ORDER BY id LIMIT 1"
            )
            row = cur.fetchone()
    except Exception:
        row = None
    if not row or row[1] is None or row[2] is None:
        return DEFAULT_BMR_KCAL
    sex = (str(row[0]) or "M").strip().upper()
    height_cm = float(row[1])
    age = day_value.year - int(row[2])
    bmr = 10.0 * float(weight_kg) + 6.25 * height_cm - 5.0 * age
    bmr += 5.0 if sex.startswith("M") else -161.0
    return float(bmr) if bmr > 0 else DEFAULT_BMR_KCAL


def _fit_day_from_rows(rows: list[dict[str, Any]], fit_path: str) -> date | None:
    if rows:
        first_ts = rows[0].get("timestamp")
        if isinstance(first_ts, datetime):
            return first_ts.date()
    stem = Path(fit_path).stem
    for token in stem.replace(".", "_").replace("-", "_").split("_"):
        if len(token) == 10:
            try:
                return date.fromisoformat(token)
            except Exception:
                continue
    return None


def _find_fit_files_for_day(fit_dir: str, day_value: date) -> list[Path]:
    paths = sorted(Path(fit_dir).glob("*.fit"))
    matched: list[Path] = []
    for path in paths:
        rows = _parse_fit_rows(str(path))
        fit_day = _fit_day_from_rows(rows, str(path))
        if fit_day == day_value:
            matched.append(path)
            continue
        if day_value.isoformat() in path.name:
            matched.append(path)
    return matched


def _fetch_weight_kg(db_conn, day_value: date) -> float | None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT weight_kg
            FROM qbot_v2.fitmodel_daily
            WHERE day <= %s
              AND weight_kg IS NOT NULL
            ORDER BY day DESC
            LIMIT 1
            """,
            (day_value,),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            return float(row[0])
        cur.execute(
            """
            SELECT weight_kg
            FROM qbot_v2.qbot_wellness_daily
            WHERE date <= %s
              AND weight_kg IS NOT NULL
            ORDER BY date DESC, source_priority ASC, imported_at DESC
            LIMIT 1
            """,
            (day_value,),
        )
        row = cur.fetchone()
    if row and row[0] is not None:
        return float(row[0])
    return None


def _load_daily_glycogen_state(db_conn, day_value: date) -> tuple[float, float, float | None]:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT glycogen_g, glycogen_pct, weight_kg
            FROM qbot_v2.fitmodel_daily
            WHERE day < %s
              AND glycogen_g IS NOT NULL
            ORDER BY day DESC
            LIMIT 1
            """,
            (day_value,),
        )
        row = cur.fetchone()
    if row and row[0] is not None:
        glycogen_g = float(row[0])
        glycogen_pct = float(row[1]) if row[1] is not None else 0.0
        weight_kg = float(row[2]) if row[2] is not None else None
        return glycogen_g, glycogen_pct, weight_kg
    return 0.0, 0.0, None


def compute_glycogen_balance(db_conn, fit_dir: str, start_day: date, end_day: date) -> list[dict]:
    """Dzienny bilans glikogenu [g] i [%] z flaga pewnosci.

    Model: stan += (wchlonione CHO) - (spalone na jezdzie) - (drain bazowy CNS),
    przyciete do [0, capacity]. Odbudowa zachodzi naturalnie w dni z nadwyzka CHO
    (bez sztucznego 'full refill').

    Pewnosc (confidence):
      - 'none' : brak logu jedzenia -> wartosc None, stan wstrzymany.
      - 'low'  : log jest, ale niekompletny (kcal < 60% wydatku dnia) -> nie ufamy
                 niskiemu intake; zakladamy pokrycie bazowe (drain zneutralizowany),
                 ale realny burn jazdy dalej drenuje. Zasada: brak danych != wyczerpanie.
      - 'high' : log kompletny -> pelny bilans z danych.
    """
    params = load_params(db_conn)
    cho_absorption = float(params.get("cho_absorption_factor", DEFAULT_CHO_ABSORPTION))
    drain_base = float(params.get("glycogen_drain_base_g_day", DEFAULT_GLYCOGEN_DRAIN))
    capacity_per_kg = float(params.get("glycogen_capacity_g_per_kg", DEFAULT_CAPACITY_PER_KG))

    state_g, _, state_weight_kg = _load_daily_glycogen_state(db_conn, start_day)
    results: list[dict] = []
    current = _coerce_date(start_day)
    end_value = _coerce_date(end_day)

    ride_burn_by_day: dict[date, float] = {}
    ride_kcal_by_day: dict[date, float] = {}
    ftp_cache: dict[date, float] = {}
    for path in sorted(Path(fit_dir).glob("*.fit")):
        rows = _parse_fit_rows(str(path))
        fit_day = _fit_day_from_rows(rows, str(path))
        if fit_day is None or fit_day < current or fit_day > end_value:
            continue
        if fit_day not in ftp_cache:
            with db_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ftp_est_w
                    FROM qbot_v2.fitmodel_daily
                    WHERE day <= %s AND ftp_est_w IS NOT NULL
                    ORDER BY day DESC
                    LIMIT 1
                    """,
                    (fit_day,),
                )
                row = cur.fetchone()
            if row and row[0] is not None:
                ftp_cache[fit_day] = float(row[0])
            else:
                ftp_cache[fit_day] = float(params.get("ftp_anchor_w", 245.0))
        ride_burn_by_day[fit_day] = ride_burn_by_day.get(fit_day, 0.0) + _compute_cho_burn_rows(rows, ftp_cache[fit_day])
        ride_kcal_by_day[fit_day] = ride_kcal_by_day.get(fit_day, 0.0) + _compute_ride_kcal_rows(rows)

    while current <= end_value:
        weight_kg = _fetch_weight_kg(db_conn, current) or state_weight_kg or DEFAULT_WEIGHT_KG
        capacity_g = float(capacity_per_kg * weight_kg)
        cho_burn = float(ride_burn_by_day.get(current, 0.0))

        if not _has_intake_log(db_conn, current):
            # brak wpisow zywienia -> nie zgadujemy bilansu; brak danych, stan wstrzymany
            results.append({
                "day": current, "glycogen_g": None, "glycogen_pct": None,
                "cho_in": None, "cho_burn": cho_burn, "capacity_g": capacity_g,
                "confidence": "none",
            })
            state_weight_kg = weight_kg
            current += timedelta(days=1)
            continue

        cho_in = load_cho_intake(db_conn, current) * cho_absorption

        # Ocena kompletnosci logu: zalogowane kcal vs wydatek dnia (baza + jazda)
        logged_kcal = load_logged_kcal(db_conn, current)
        bmr = load_bmr_kcal(db_conn, weight_kg, current)
        expend_kcal = NONEX_FACTOR * bmr + float(ride_kcal_by_day.get(current, 0.0))
        complete = expend_kcal > 0 and logged_kcal >= COMPLETE_LOG_FRAC * expend_kcal

        if complete:
            inflow = cho_in
            confidence = "high"
        else:
            # log niepelny: nie ufamy niskiemu intake. Zakladamy ze co najmniej
            # pokryto bazowe zapotrzebowanie (drain), ale realny burn jazdy zostaje.
            inflow = max(cho_in, drain_base)
            confidence = "low"

        state_g = max(0.0, min(capacity_g, state_g + inflow - cho_burn - drain_base))
        glycogen_pct = 0.0 if capacity_g <= 0 else float((state_g / capacity_g) * 100.0)
        results.append(
            {
                "day": current,
                "glycogen_g": float(state_g),
                "glycogen_pct": float(np.clip(glycogen_pct, 0.0, 100.0)),
                "cho_in": float(cho_in),
                "cho_burn": cho_burn,
                "capacity_g": capacity_g,
                "confidence": confidence,
            }
        )
        state_weight_kg = weight_kg
        current += timedelta(days=1)

    return results


def update_glycogen_in_daily(db_conn, fit_dir: str, days: int = 30) -> dict:
    end_day = date.today()
    start_day = end_day - timedelta(days=days - 1)
    rows = compute_glycogen_balance(db_conn, fit_dir, start_day, end_day)
    updated = 0
    latest_glycogen_pct = None
    latest_conf = None
    with db_conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO qbot_v2.fitmodel_daily (day, glycogen_g, glycogen_pct, glycogen_confidence)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (day) DO UPDATE SET
                    glycogen_g = EXCLUDED.glycogen_g,
                    glycogen_pct = EXCLUDED.glycogen_pct,
                    glycogen_confidence = EXCLUDED.glycogen_confidence
                """,
                (row["day"], row["glycogen_g"], row["glycogen_pct"], row.get("confidence")),
            )
            updated += 1
            latest_glycogen_pct = row["glycogen_pct"]
            latest_conf = row.get("confidence")
    db_conn.commit()
    return {"updated": updated, "latest_glycogen_pct": latest_glycogen_pct, "latest_confidence": latest_conf}


if __name__ == "__main__":
    conn = _db_connect()
    try:
        result = update_glycogen_in_daily(conn, "/opt/qbot/artifacts/fit/", days=30)
        print("RESULT:", result)
        with conn.cursor() as cur:
            cur.execute("SELECT day, glycogen_pct, glycogen_g, glycogen_confidence FROM qbot_v2.fitmodel_daily ORDER BY day DESC LIMIT 7")
            print("fitmodel_daily:")
            for row in cur.fetchall():
                print(row)
    finally:
        conn.close()
