from datetime import datetime, timedelta
from fitmodel.fit_ingest import summarize_qext2


def _recs(n, schema=None, zero_from=None, dup=False):
    t0 = datetime(2026, 10, 9, 10, 0, 0)
    out = []
    for i in range(n):
        r = {"timestamp": t0 + timedelta(seconds=i), "qext2_wbal_pct": 0 if zero_from is not None and i >= zero_from else 50,
             "qext2_xss": float(i), "qext2_cp_eff_w": 240.0}
        if schema is not None:
            r["qext2_schema"] = schema
        out.append(r)
        if dup and zero_from is not None and i >= zero_from:
            out.append(dict(r))
    return out, t0


def test_stare_pliki_maja_schemat_1():
    recs, t0 = _recs(10)
    assert summarize_qext2(recs, t0)["model_schema"] == 1


def test_nowe_pliki_schemat_2():
    recs, t0 = _recs(10, schema=2)
    assert summarize_qext2(recs, t0)["model_schema"] == 2


def test_sekundy_zera_z_timestampow_nie_z_liczby_rekordow():
    recs, t0 = _recs(20, zero_from=15, dup=True)
    s = summarize_qext2(recs, t0)
    assert s["wbal_zero_seconds"] == 5
    assert s["wbal_zero_first_offset_s"] == 15
