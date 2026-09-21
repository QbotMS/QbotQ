import sys, os
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

with _db_connect() as conn, conn.cursor() as cur:
    # fitmodel_daily - co widzi web
    cur.execute("""
        select day, ftp_est_w, ltp_modelq_w, ctl_xss, atl_xss, tsb_xss,
               wprime_road_kj, hie_modelq_kj
        from qbot_v2.fitmodel_daily
        where day >= '2026-08-01'
        order by day
    """)
    cols = [d[0] for d in cur.description]
    print("fitmodel_daily cols:", cols)
    print("\nfitmodel_daily SIERPIEN:")
    for r in cur.fetchall():
        print(" ", r)

    # modelq2_signature - zrodlo danych dla daily
    cur.execute("""
        select day, tp_w, hie_kj, pp_w, ltp_w, ctl, atl, tsb
        from qbot_v2.modelq2_signature
        where day >= '2026-08-01'
        order by day
    """)
    print("\nmodelq2_signature SIERPIEN:")
    for r in cur.fetchall():
        print(" ", r)

    # co publish wstawia do fitmodel_daily
    cur.execute("""
        select column_name from information_schema.columns
        where table_schema='qbot_v2' and table_name='fitmodel_daily'
        order by ordinal_position
    """)
    print("\nfitmodel_daily ALL COLS:", [r[0] for r in cur.fetchall()])
