import os, sys
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

conn = _db_connect(); cur = conn.cursor()
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_schema='qbot_v2' AND table_name='ride_drivetrain'
    ORDER BY ordinal_position
""")
cols = [r[0] for r in cur.fetchall()]
print("cols:", cols)

# szukaj kolumny z koronkami
cog_cols = [c for c in cols if "cog" in c.lower() or "cassette" in c.lower() or "teeth" in c.lower()]
print("cog-like cols:", cog_cols)

sel = ", ".join(["external_id","chainring_t","cassette_label","source"] + cog_cols) if "external_id" in cols else "*"
cur.execute(f"SELECT {sel} FROM qbot_v2.ride_drivetrain ORDER BY 1 DESC LIMIT 8")
names = [d[0] for d in cur.description]
print("\n"+" | ".join(names))
for r in cur.fetchall():
    print(" | ".join("" if v is None else str(v) for v in r))

cur.close(); conn.close()
os.remove(__file__)
