import sys, os
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

conn = _db_connect()
cur = conn.cursor()

for day in ['2026-09-19','2026-09-18','2026-09-13','2026-09-11']:
    cur.execute("""
      SELECT external_id FROM qbot_v2.training_sessions
      WHERE started_at::date = %s AND sport_type='cycling'
      ORDER BY started_at LIMIT 1
    """, (day,))
    row = cur.fetchone()
    if not row:
        print(day, "-> brak jazdy"); continue
    ext = row[0]
    cur.execute("SELECT count(*) FROM qbot_v2.activity_device WHERE external_id=%s", (ext,))
    ndev = cur.fetchone()[0]
    cur.execute("SELECT manufacturer, product, serial_number FROM qbot_v2.activity_device WHERE external_id=%s", (ext,))
    devs = cur.fetchall()
    cur.execute("SELECT count(*) FROM qbot_v2.ride_drivetrain WHERE external_id=%s", (ext,))
    ndt = cur.fetchone()[0]
    cur.execute("SELECT chainring_label, cassette_code, cassette_source, flag FROM qbot_v2.ride_drivetrain WHERE external_id=%s", (ext,))
    dtrows = cur.fetchall()
    cur.execute("SELECT count(*) FROM qbot_v2.activity_record WHERE external_id=%s", (ext,))
    nrec = cur.fetchone()[0]
    # czy jest kadencja w rekordach?
    cur.execute("""SELECT count(*) FROM information_schema.columns
                   WHERE table_schema='qbot_v2' AND table_name='activity_record' AND column_name='cadence_rpm'""")
    has_cad = cur.fetchone()[0]
    print(f"\n{day}  ext={ext}")
    print(f"  activity_record: {nrec} rekordow 1Hz")
    print(f"  activity_device: {ndev} -> {devs}")
    print(f"  ride_drivetrain: {ndt} -> {dtrows}")

conn.close()
