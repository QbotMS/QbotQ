import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
import qbot_web as W

conn = W._db_conn()
try:
    data = W._build_report_data(conn, "3186954572", "2026-08-20", "07:00", 0, 0)
finally:
    conn.close()

cl = (data.get("details") or {}).get("climbs") or {}
lst = cl.get("list") or cl.get("climbs") or []
print("kluczy w climbs:", list(cl.keys()))
for x in lst:
    print(f"  #{x.get('i')} {x.get('a_km')}-{x.get('b_km')} km +{x.get('gain_m')} m "
          f"{x.get('avg_pct')}% {x.get('severity')} | ocena={x.get('score')} "
          f"'{x.get('score_label')}' tryb={x.get('chain_mode')} "
          f"W'in={x.get('chain_wbal_in')}% W'min={x.get('chain_wbal_min')}%")
ch = cl.get("chain") or {}
print("chain keys:", list(ch.keys()))
print("chain verdict:", json.dumps({k: v for k, v in ch.items() if k != "per_climb"},
                                   ensure_ascii=False)[:900])
os.remove(__file__)
