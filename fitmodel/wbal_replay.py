from __future__ import annotations

"""FITMODEL Krok 3 -- replika W'bal tick-po-ticku, zgodna z algorytmem QExt2
(StatsCalculator.kt na Karoo).

Zrodlo prawdy: /home/claude/qext2_ro (klon QbotMS/QExt2, tylko odczyt -- patrz
DECISIONS.md 2026-07-06). WALIDACJA na prawdziwej jezdzie z build-140
(2026-07-06 09:30-10:34, external_id z FIT developer fields qext2_*):
srednia|diff|=0.49pp, max=2.7pp (bylo 5.6pp/13.9pp z surowa moca -- patrz
DECISIONS.md 2026-07-06 "Krok 3: uzycie mocy 3s zamiast surowej").
KLUCZOWE: QExt2 karmi W'bal moca SMOOTHED_3S_AVERAGE_POWER (SDK Karoo,
RideDataAggregator.kt "PWR_3S"), NIE surowa moc z sekundy! Replika musi
usredniac ostatnie do 3 sekund power_w (rosnace okno na starcie, potem
trailing 3) PRZED podaniem do wzoru rozniczkowego.

Formula (Skiba differential, tau dynamiczny):
  - moc > CP_eff: wBal -= (moc-CP_eff)/1000 kJ na kazda sekunde
  - moc <= CP_eff: dcp = CP_eff-moc; tau = 546*exp(-0.01*dcp)+316;
                   wBal += (wPrimeMax_eff - wBal) * (1-exp(-1/tau))
CP_eff/wPrimeMax_eff = (FTP_dnia / W'_dnia z ModelQ) * cf, gdzie
  cf = clamp(readiness * heat * acute, 0.88, 1.06)
  readiness = 1.0 (Karoo NIE dostaje dzis "todayFactor" w /ride-readiness --
              QExt2 uzywa wtedy defaultu 1.0; replika wiernie to odzwierciedla)
  heat = clamp(1 - 0.007*max(tempC-20,0), 0.85, 1.0)
  acute = clamp(1 - clamp(decoupling_pct-5,0,15)*0.0027, 0.96, 1.0)

Bramka postoj/dropout (DECISIONS.md 2026-07-06), prog 30s:
  - dziura < 30s: normalny tick (o realnym dt sekund), brak mocy -> zamrozenie na dt.
  - dziura >= 30s, BRAK wierszy w bazie w trakcie + dystans niezmieniony + predkosc
    przed ~0 -> POSTOJ: analityczna rekonstrukcja odpoczynku (moc=0 przez cala dziure).
  - dziura >= 30s, inaczej (wiersze sa ale power=NULL, lub dystans sie zmienil mimo
    braku wierszy) -> NIEPEWNE/DROPOUT: zamrozenie (bez darmowego bonusu).

Uzycie: python3 fitmodel/wbal_replay.py <external_id>
"""

import math
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitmodel.api import _db_connect

GAP_THRESHOLD_S = 30.0
REST_DISTANCE_TOLERANCE_M = 30.0
REST_SPEED_THRESHOLD_MPS = 0.5
MOVING_SPEED_THRESHOLD_MPS = 0.5
DECOUPLE_MAXLEN = 3600
DECOUPLE_MIN_N = 120


def _temp_factor(temp_c: float | None) -> float:
    if temp_c is None:
        return 1.0
    delta = max(temp_c - 20.0, 0.0)
    return max(1.0 - 0.007 * delta, 0.85)


def _decoupling_percent(hr_buf: list[int], pw_buf: list[int]) -> float:
    n = len(hr_buf)
    if n < DECOUPLE_MIN_N:
        return 0.0
    half = n // 2
    first_hr = sum(hr_buf[:half]) / half
    first_pw = sum(pw_buf[:half]) / half
    second_hr = sum(hr_buf[half:]) / (n - half)
    second_pw = sum(pw_buf[half:]) / (n - half)
    if first_pw <= 0 or second_pw <= 0:
        return 0.0
    r1 = first_hr / first_pw
    r2 = second_hr / second_pw
    if r1 <= 0:
        return 0.0
    drift = ((r2 - r1) / r1) * 100.0
    return min(max(drift, 0.0), 50.0)


def _fetch_ride_rows(external_id: str) -> list[dict]:
    conn = _db_connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ts, power_w, hr_bpm, speed_mps, distance_m, temperature_c
        FROM qbot_v2.activity_record
        WHERE external_id = %s
        ORDER BY ts
        """,
        (external_id,),
    )
    cols = ["ts", "power_w", "hr_bpm", "speed_mps", "distance_m", "temperature_c"]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows


def _fetch_daily_baseline(ride_date) -> tuple[float | None, float | None]:
    """FTP i W' z ModelQ dla dnia jazdy -- KAZDE pole osobno, najblizszy dostepny
    dzien <= data jazdy (dokladnie jak _modelq_ftp_ltp w qbot_api.py; ftp_est_w
    bywa null czesciej niz wprime_modelq_kj, wiec NIE wolno brac jednego wiersza)."""
    conn = _db_connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT ftp_est_w FROM qbot_v2.fitmodel_daily "
        "WHERE day <= %s AND ftp_est_w IS NOT NULL ORDER BY day DESC LIMIT 1",
        (ride_date,),
    )
    r1 = cur.fetchone()
    cur.execute(
        "SELECT wprime_modelq_kj FROM qbot_v2.fitmodel_daily "
        "WHERE day <= %s AND wprime_modelq_kj IS NOT NULL ORDER BY day DESC LIMIT 1",
        (ride_date,),
    )
    r2 = cur.fetchone()
    conn.close()
    ftp = float(r1[0]) if r1 and r1[0] is not None else None
    wprime = float(r2[0]) if r2 and r2[0] is not None else None
    return ftp, wprime


def replay_wbal(external_id: str, verbose: bool = True) -> dict:
    rows = _fetch_ride_rows(external_id)
    if not rows:
        if verbose:
            print(f"STATUS: NO_DATA dla {external_id}")
        return {"status": "NO_DATA", "external_id": external_id}

    ride_date = rows[0]["ts"].date()
    ftp_base, wprime_base_kj = _fetch_daily_baseline(ride_date)
    if not ftp_base or not wprime_base_kj:
        if verbose:
            print(f"STATUS: NO_BASELINE dla {external_id} ({ride_date}) "
                  f"ftp_base={ftp_base} wprime_base_kj={wprime_base_kj}")
        return {"status": "NO_BASELINE", "external_id": external_id, "ride_date": str(ride_date)}

    wprime_base_j = wprime_base_kj * 1000.0

    hr_buf: list[int] = []
    pw_buf: list[int] = []
    pw3s_buf: deque = deque(maxlen=3)  # SMOOTHED_3S_AVERAGE_POWER -- patrz docstring modulu

    wbal_j = wprime_base_j  # start pelny (zaklada odpoczety start)
    cp_eff = ftp_base
    wprime_eff_j = wprime_base_j

    segments_log: list[dict] = []
    n_normal_ticks = 0
    n_frozen_s = 0.0
    n_rest_recovered_s = 0.0
    min_wbal_pct = 100.0

    prev = None
    for row in rows:
        if prev is not None:
            dt = (row["ts"] - prev["ts"]).total_seconds()
        else:
            dt = 1.0
        if dt <= 0:
            dt = 1.0

        # -- per-tick cf (readiness=1.0 -- patrz docstring modulu) --
        heat = _temp_factor(row.get("temperature_c"))
        decoupling_pct = _decoupling_percent(hr_buf, pw_buf)
        drift = min(max(decoupling_pct - 5.0, 0.0), 15.0) * 0.0027
        acute = min(max(1.0 - drift, 0.96), 1.0)
        cf = min(max(1.0 * heat * acute, 0.88), 1.06)
        cp_eff = ftp_base * cf
        new_wprime_eff_j = wprime_base_j * cf
        if wbal_j > new_wprime_eff_j:
            wbal_j = new_wprime_eff_j  # setEffectiveWPrime: tylko przycina w dol
        wprime_eff_j = new_wprime_eff_j

        if dt >= GAP_THRESHOLD_S and prev is not None:
            dist_before = prev.get("distance_m")
            dist_after = row.get("distance_m")
            speed_before = prev.get("speed_mps") or 0.0
            dist_delta = None
            if dist_before is not None and dist_after is not None:
                dist_delta = abs(float(dist_after) - float(dist_before))
            is_rest = (
                dist_delta is not None
                and dist_delta <= REST_DISTANCE_TOLERANCE_M
                and speed_before <= REST_SPEED_THRESHOLD_MPS
            )
            if is_rest:
                dcp = max(cp_eff - 0.0, 0.0)
                tau = 546.0 * math.exp(-0.01 * dcp) + 316.0
                deficit0 = wprime_eff_j - wbal_j
                deficit_n = deficit0 * math.exp(-dt / tau)
                wbal_j = wprime_eff_j - deficit_n
                n_rest_recovered_s += dt
                segments_log.append({
                    "kind": "POSTOJ", "start": str(prev["ts"]), "dur_s": dt,
                    "dist_delta_m": dist_delta, "wbal_pct_after": round(100 * wbal_j / wprime_eff_j, 1),
                })
            else:
                n_frozen_s += dt
                segments_log.append({
                    "kind": "NIEPEWNE/DROPOUT", "start": str(prev["ts"]), "dur_s": dt,
                    "dist_delta_m": dist_delta, "wbal_pct_after": round(100 * wbal_j / wprime_eff_j, 1),
                })
            wbal_j = min(max(wbal_j, 0.0), wprime_eff_j)
            min_wbal_pct = min(min_wbal_pct, 100 * wbal_j / wprime_eff_j)
            pw3s_buf.clear()  # przerwa >=30s -- bufor 3s nie ma sensu ciagnac przez nia
            prev = row
            continue

        power_raw = row.get("power_w")
        power_fresh = power_raw is not None
        speed = row.get("speed_mps") or 0.0
        hr = row.get("hr_bpm")
        moving_advanced = speed > MOVING_SPEED_THRESHOLD_MPS
        has_power = power_fresh and power_raw > 0
        active_sample = moving_advanced and has_power and power_fresh

        if active_sample and hr is not None and hr > 0:
            hr_buf.append(int(hr))
            pw_buf.append(int(power_raw))
            if len(hr_buf) > DECOUPLE_MAXLEN:
                hr_buf.pop(0)
                pw_buf.pop(0)

        if power_fresh:
            pw3s_buf.append(power_raw)  # decoupling/NP nadal na surowej -- W'bal na 3s
            power = sum(pw3s_buf) / len(pw3s_buf)
            p = float(power)
            if p > cp_eff:
                wbal_j -= (p - cp_eff) * dt
            else:
                dcp = max(cp_eff - p, 0.0)
                tau = 546.0 * math.exp(-0.01 * dcp) + 316.0
                deficit0 = wprime_eff_j - wbal_j
                deficit_n = deficit0 * math.exp(-dt / tau)
                wbal_j = wprime_eff_j - deficit_n
            n_normal_ticks += 1
        else:
            n_frozen_s += dt

        wbal_j = min(max(wbal_j, 0.0), wprime_eff_j)
        min_wbal_pct = min(min_wbal_pct, 100 * wbal_j / wprime_eff_j)
        prev = row

    result = {
        "status": "OK",
        "external_id": external_id,
        "ride_date": str(ride_date),
        "ftp_base_w": round(ftp_base, 1),
        "wprime_base_kj": round(wprime_base_kj, 2),
        "final_wbal_pct": round(100 * wbal_j / wprime_eff_j, 1),
        "min_wbal_pct": round(min_wbal_pct, 1),
        "n_normal_ticks": n_normal_ticks,
        "n_frozen_s": round(n_frozen_s, 0),
        "n_rest_recovered_s": round(n_rest_recovered_s, 0),
        "n_big_segments": len(segments_log),
        "segments": segments_log,
    }
    if verbose:
        print(f"Jazda {external_id} ({ride_date}): FTP_bazowe={result['ftp_base_w']}W "
              f"W'_bazowe={result['wprime_base_kj']}kJ")
        print(f"  min W'bal w trakcie: {result['min_wbal_pct']}%  koncowe: {result['final_wbal_pct']}%")
        print(f"  normalne ticki: {n_normal_ticks}  zamrozone (s): {n_frozen_s}  "
              f"odpoczynek-doliczony (s): {n_rest_recovered_s}")
        for seg in segments_log:
            print("  ", seg)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uzycie: python3 fitmodel/wbal_replay.py <external_id>")
        sys.exit(1)
    _res = replay_wbal(sys.argv[1])
