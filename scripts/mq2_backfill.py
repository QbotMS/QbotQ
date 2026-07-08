"""
Backfill XSS do modelq2_ride, PORCJAMI po datach (arg: date_from date_to).
Sygnatura per jazda: Xert benchmark z najblizszego dnia <= data jazdy (czysta dzienna).
Wywolywac: python3 _mq2_backfill.py 2025-01-01 2025-03-31  itd.
"""
import os, sys, bisect
os.environ["QBOT3_ENABLED"]="1"
sys.path.insert(0,"/opt/qbot/app")
import datetime as dt
from fitmodel.ftp_resolver import _db_connect
from fitmodel.modelq2.signature import Signature
from fitmodel.modelq2 import io
from fitmodel.modelq2.xss import compute_xss
from fitmodel.modelq2.mpa import replay_mpa

d_from=dt.date.fromisoformat(sys.argv[1])
d_to=dt.date.fromisoformat(sys.argv[2])

conn=_db_connect(); cur=conn.cursor()
# benchmark sygnatur (posortowane daty do wyszukiwania <=)
cur.execute("SELECT day,tp_w,hie_kj,pp_w FROM qbot_v2.modelq2_xert_bench ORDER BY day")
bench=cur.fetchall()
bdays=[b[0] for b in bench]
def sig_for(d):
    i=bisect.bisect_right(bdays,d)-1
    if i<0: i=0
    _,tp,hie,pp=bench[i]
    return Signature.from_kj(tp_w=float(tp),hie_kj=float(hie),pp_w=float(pp))

# jazdy w oknie (dedup: najdluzszy strumien per dzien)
rides=io.list_rides(d_from,d_to)
byday={}
for eid,d,n in rides:
    if d not in byday or n>byday[d][1]: byday[d]=(eid,n)

done=0
for d in sorted(byday):
    eid,n=byday[d]
    sig=sig_for(d)
    rows=io.fetch_ride_rows(eid)
    res=replay_mpa(rows,sig,smooth=True,keep_series=True)
    x=compute_xss(rows,sig)
    cur.execute("""INSERT INTO qbot_v2.modelq2_ride
        (external_id,ride_date,n_ticks,duration_s,sig_tp_w,sig_hie_kj,sig_pp_w,
         min_wbal_pct,xss_low,xss_high,xss_peak,xss_total)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (external_id) DO UPDATE SET
         xss_low=EXCLUDED.xss_low,xss_high=EXCLUDED.xss_high,xss_peak=EXCLUDED.xss_peak,
         xss_total=EXCLUDED.xss_total,min_wbal_pct=EXCLUDED.min_wbal_pct,
         sig_tp_w=EXCLUDED.sig_tp_w,sig_hie_kj=EXCLUDED.sig_hie_kj,sig_pp_w=EXCLUDED.sig_pp_w""",
        (eid,d,res.n_ticks,int(res.duration_s),sig.tp_w,sig.hie_kj,sig.pp_w,
         round(res.min_wbal_pct,1),round(x.low,1),round(x.high,2),round(x.peak,3),round(x.total,1)))
    done+=1
conn.commit()
print(f"OK: {done} jazd w oknie {d_from}..{d_to}")
cur.execute("SELECT COUNT(*) FROM qbot_v2.modelq2_ride")
print(f"razem w modelq2_ride: {cur.fetchone()[0]}")
conn.close()
