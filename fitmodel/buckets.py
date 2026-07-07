from __future__ import annotations

"""FITMODEL B1 -- silnik strainu + alokacja na 3 systemy energetyczne.

Czysta funkcja (bez DB): strumien mocy 1 Hz + FTP -> (low, high, peak, d_strain).
Spec sek. 5.1-5.3.

Waluta strainu (zakotwiczona w FTP, bez PP):
    i = P_sec / FTP_est
    strain_sec = i^4 * (100/3600)     # 1h @ FTP = 100

Alokacja strefowa (proxy, jawnie grubsze niz dekompozycja Xerta):
    i < 0.90          -> Low   (tlenowe)
    0.90 <= i < 1.20  -> High  (progowe)
    i >= 1.20         -> Peak  (neuro)
Praca sekunda-po-sekundzie (bez wygladzania) sama lapie krotkie zrywy -> Peak.

Splyw w dol (Xert "kilka systemow naraz"): High dokłada ułamek do Low;
Peak dokłada do High i Low. Lekko, zeby rozklad nie byl sztucznie czysty.

Durability (osobny odczyt, NIE wchodzi do sumy Low+High+Peak):
    kJ_so_far = ∫P dt / 1000
    dur_mult  = 1 + clip((kJ_so_far - kj_gate)/kj_gate, 0, 1.0)   # cap x2
    D += strain_sec * (dur_mult - 1)
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Progi stref (i = P/FTP)
LOW_HIGH = 0.90
HIGH_PEAK = 1.20

# Splyw w dol (lekki)
SPILL_HIGH_TO_LOW = 0.10
SPILL_PEAK_TO_HIGH = 0.10
SPILL_PEAK_TO_LOW = 0.05

STRAIN_UNIT = 100.0 / 3600.0  # 1h @ FTP = 100


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_buckets(
    power_per_sec: Iterable[float | None],
    ftp: float,
    kj_gate: float = 1500.0,
    spillover: bool = True,
) -> dict[str, Any]:
    """Strumien mocy [W] (1 Hz, None=luka) + FTP -> rozklad strainu.

    Zwraca low/high/peak (po splywie), d_strain (durability), total (=low+high+peak),
    oraz surowe (raw_*) przed splywem i kilka metryk pomocniczych.
    """
    if not ftp or ftp <= 0:
        raise ValueError("ftp musi byc > 0")

    low = high = peak = 0.0
    d_strain = 0.0
    kj = 0.0
    sec = 0
    sec_with_power = 0

    for p in power_per_sec:
        sec += 1
        if p is None or p < 0:
            continue
        sec_with_power += 1
        kj += p / 1000.0  # P[W] * 1s = J -> kJ

        i = p / ftp
        strain = (i ** 4) * STRAIN_UNIT

        if i < LOW_HIGH:
            low += strain
        elif i < HIGH_PEAK:
            high += strain
        else:
            peak += strain

        # durability: bonus za strain wykonany na zmeczeniu (po przekroczeniu bramki kJ)
        dur_mult = 1.0 + _clip((kj - kj_gate) / kj_gate, 0.0, 1.0)
        d_strain += strain * (dur_mult - 1.0)

    raw_low, raw_high, raw_peak = low, high, peak

    if spillover:
        low += raw_high * SPILL_HIGH_TO_LOW + raw_peak * SPILL_PEAK_TO_LOW
        high += raw_peak * SPILL_PEAK_TO_HIGH

    total = low + high + peak
    return {
        "low": round(low, 2),
        "high": round(high, 2),
        "peak": round(peak, 2),
        "d_strain": round(d_strain, 2),
        "total": round(total, 2),
        "raw_low": round(raw_low, 2),
        "raw_high": round(raw_high, 2),
        "raw_peak": round(raw_peak, 2),
        "kj": round(kj, 1),
        "dur_seconds": sec,
        "sec_with_power": sec_with_power,
        "ftp_used": ftp,
        "pct": {
            "low": round(low / total * 100, 1) if total else 0.0,
            "high": round(high / total * 100, 1) if total else 0.0,
            "peak": round(peak / total * 100, 1) if total else 0.0,
        },
    }


# ── Walidacja na realnych jazdach (FIT) ──────────────────────────────────
def _power_stream_from_fit(fit_path: Path) -> list[float | None]:
    import fitparse
    fit = fitparse.FitFile(str(fit_path))
    stream: list[float | None] = []
    for rec in fit.get_messages("record"):
        d = {x.name: x.value for x in rec}
        stream.append(d.get("power"))
    return stream


def _ftp_from_param(default: float = 245.0) -> float:
    try:
        from fitmodel.ftp_resolver import _db_connect
        c = _db_connect()
        with c.cursor() as cur:
            cur.execute(
                "SELECT value FROM qbot_v2.fitmodel_param WHERE key='ftp_anchor_w'"
            )
            row = cur.fetchone()
        c.close()
        if row and row[0]:
            return float(row[0])
    except Exception:
        pass
    return default


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="FITMODEL B1 -- walidacja silnika strainu na jazdach")
    ap.add_argument("--ftp", type=float, default=None, help="FTP [W] (domyslnie ftp_anchor_w z param)")
    ap.add_argument("--kj-gate", type=float, default=1500.0)
    ap.add_argument("--dir", default="/opt/qbot/artifacts/fit")
    ap.add_argument("--limit", type=int, default=12, help="ile jazd policzyc")
    args = ap.parse_args()

    ftp = args.ftp if args.ftp else _ftp_from_param()
    fit_dir = Path(args.dir)
    files = sorted(fit_dir.glob("*.fit"))[: args.limit]

    print(f"FTP={ftp} W, kj_gate={args.kj_gate}, jazd={len(files)}\n")
    print(f"  {'ride':14} {'min':>4} {'kJ':>6} {'LOW%':>5} {'HIGH%':>6} {'PEAK%':>6} "
          f"{'low':>7} {'high':>7} {'peak':>7} {'D':>6}")
    rows = []
    for f in files:
        try:
            stream = _power_stream_from_fit(f)
        except Exception as exc:
            print(f"  {f.name[-12:]:14} BLAD: {exc}")
            continue
        if not any(p for p in stream):
            continue  # FIT bez mocy (np. trening sily) — pomijamy
        r = compute_buckets(stream, ftp, kj_gate=args.kj_gate)
        rid = f.name.split(".")[-2][-12:] if "." in f.name else f.name[:12]
        rows.append((rid, r))
        print(f"  {rid:14} {r['dur_seconds']//60:>4} {r['kj']:>6} "
              f"{r['pct']['low']:>5} {r['pct']['high']:>6} {r['pct']['peak']:>6} "
              f"{r['low']:>7} {r['high']:>7} {r['peak']:>7} {r['d_strain']:>6}")

    # Czy silnik ROZNICUJE profile?
    if rows:
        peaks = sorted(rows, key=lambda x: -x[1]['pct']['peak'])
        highs = sorted(rows, key=lambda x: -x[1]['pct']['high'])
        lows = sorted(rows, key=lambda x: -x[1]['pct']['low'])
        print("\n  Najwiecej LOW :", lows[0][0], f"({lows[0][1]['pct']['low']}%)")
        print("  Najwiecej HIGH:", highs[0][0], f"({highs[0][1]['pct']['high']}%)")
        print("  Najwiecej PEAK:", peaks[0][0], f"({peaks[0][1]['pct']['peak']}%)")
