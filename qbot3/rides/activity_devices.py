"""Czujniki i rower per jazda z FIT device_info. DECISIONS 2026-09-12.

qbot_v2.activity_device: jedna linia na (jazda, urzadzenie) -- producent, produkt, serial, typ, bateria.
qbot_v2.bike_sensor: mapowanie czujnika (serial lub producent+typ) -> rower/komponent (z Garazu).
bike_for_ride(): nazwa roweru na podstawie czujnikow (najpierw serial, potem producent+typ).
"""
from __future__ import annotations
import json, os, sys
sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

DDL = """
CREATE TABLE IF NOT EXISTS qbot_v2.activity_device(
  external_id text NOT NULL, device_index int, manufacturer text, product text, product_name text,
  serial_number bigint, device_type text, source_type text, battery_status text, battery_voltage numeric,
  software_version numeric, ant_device_number int, PRIMARY KEY(external_id, device_index));
CREATE TABLE IF NOT EXISTS qbot_v2.bike_sensor(
  id serial PRIMARY KEY, bike text NOT NULL, component text, manufacturer text, device_type text,
  serial_number bigint, note text, active boolean DEFAULT true);
"""
SEED = [  # (bike, component, manufacturer, device_type, serial, note)
    ("Monster gravel", "miernik mocy Favero Assioma", "favero_electronics", "bike_power", 2005667661, "pedaly"),
    ("Monster gravel", "czujnik predkosci Garmin", "garmin", "bike_speed", 9568256, None),
    ("Canyon Grizl", "czujnik predkosci Garmin", "garmin", "bike_speed", 7208960, None),
    ("Canyon Grizl", "miernik mocy Quarq (SRAM)", "sram", "bike_power", None, "AXS PM, brak seriala w ANT+"),
    ("Canyon Grizl", "przerzutka SRAM AXS", "sram", "34", None, "bike_shifting"),
]


def _conn():
    from fitmodel.api import _db_connect
    return _db_connect()


def ensure_tables(conn):
    cur = conn.cursor(); cur.execute(DDL)
    cur.execute("SELECT count(*) FROM qbot_v2.bike_sensor")
    if cur.fetchone()[0] == 0:
        for b, c, m, t, s, n in SEED:
            cur.execute("INSERT INTO qbot_v2.bike_sensor(bike,component,manufacturer,device_type,serial_number,note) VALUES(%s,%s,%s,%s,%s,%s)", (b, c, m, t, s, n))
    conn.commit()


def parse_fit_devices(fit_path: str) -> list[dict]:
    import fitmodel._fitparse_compat  # noqa
    from fitparse import FitFile
    out = {}
    for m in FitFile(fit_path).get_messages("device_info"):
        d = {x.name: x.value for x in m}
        idx = d.get("device_index")
        if idx is None: continue
        if not isinstance(idx, int):
            idx = 0 if str(idx) == "creator" else (abs(hash(str(idx))) % 1000 + 100)
        prod = d.get("product") if d.get("product") is not None else d.get("garmin_product")
        dt = d.get("device_type") if d.get("device_type") is not None else d.get("antplus_device_type")
        row = out.setdefault(int(idx), {"device_index": int(idx)})
        # ostatni wpis z bateria wygrywa (stan na koniec jazdy)
        for k, v in (("manufacturer", d.get("manufacturer")), ("product", None if prod is None else str(prod)),
                     ("product_name", None if d.get("product_name") is None else str(d.get("product_name"))),
                     ("serial_number", d.get("serial_number")), ("device_type", None if dt is None else str(dt)),
                     ("source_type", None if d.get("source_type") is None else str(d.get("source_type"))),
                     ("battery_status", None if d.get("battery_status") is None else str(d.get("battery_status"))),
                     ("battery_voltage", d.get("battery_voltage")), ("software_version", d.get("software_version")),
                     ("ant_device_number", d.get("ant_device_number"))):
            if v is not None: row[k] = v
    return list(out.values())


def store_devices(conn, external_id: str, rows: list[dict]) -> int:
    cur = conn.cursor(); n = 0
    for r in rows:
        cur.execute("""INSERT INTO qbot_v2.activity_device(external_id,device_index,manufacturer,product,product_name,serial_number,device_type,source_type,battery_status,battery_voltage,software_version,ant_device_number)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (external_id,device_index) DO UPDATE SET manufacturer=EXCLUDED.manufacturer,product=EXCLUDED.product,product_name=EXCLUDED.product_name,
              serial_number=EXCLUDED.serial_number,device_type=EXCLUDED.device_type,source_type=EXCLUDED.source_type,battery_status=EXCLUDED.battery_status,
              battery_voltage=EXCLUDED.battery_voltage,software_version=EXCLUDED.software_version,ant_device_number=EXCLUDED.ant_device_number""",
            (external_id, r.get("device_index"), r.get("manufacturer"), r.get("product"), r.get("product_name"), r.get("serial_number"),
             r.get("device_type"), r.get("source_type"), r.get("battery_status"), r.get("battery_voltage"), r.get("software_version"), r.get("ant_device_number")))
        n += 1
    conn.commit(); return n


def ingest_devices(external_id: str, fit_path: str, conn=None) -> int:
    own = conn is None
    conn = conn or _conn()
    try:
        ensure_tables(conn)
        return store_devices(conn, external_id, parse_fit_devices(fit_path))
    finally:
        if own: conn.close()


def devices_for_ride(conn, external_id: str) -> list[dict]:
    cur = conn.cursor()
    cur.execute("SELECT device_index,manufacturer,product,product_name,serial_number,device_type,source_type,battery_status,battery_voltage FROM qbot_v2.activity_device WHERE external_id=%s ORDER BY device_index", (external_id,))
    cols = ["device_index","manufacturer","product","product_name","serial_number","device_type","source_type","battery_status","battery_voltage"]
    return [(dict(r) if isinstance(r, dict) else dict(zip(cols, r))) for r in cur.fetchall()]


def bike_for_ride(conn, external_id: str) -> dict:
    """{'bike': nazwa|None, 'how': 'serial'|'type'|None, 'sensors': [...z komponentem i bateria...], 'has_axs': bool}"""
    devs = devices_for_ride(conn, external_id)
    cur = conn.cursor(); cur.execute("SELECT bike,component,manufacturer,device_type,serial_number FROM qbot_v2.bike_sensor WHERE active")
    maps = [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in cur.fetchall()]
    votes = {}; how = None; sensors = []; has_axs = False
    for d in devs:
        comp = None; bike = None
        for b, c, m, t, s in maps:
            if s is not None and d.get("serial_number") == s:
                bike, comp = b, c; votes[b] = votes.get(b, 0) + 3; how = how or "serial"; break
        if bike is None:
            for b, c, m, t, s in maps:
                if s is None and m == d.get("manufacturer") and str(t) == str(d.get("device_type")):
                    bike, comp = b, c; votes[b] = votes.get(b, 0) + 1; how = how or "type"; break
        if d.get("manufacturer") == "sram" and str(d.get("device_type")) == "34": has_axs = True
        if d.get("source_type") == "antplus" or d.get("device_type") in ("bike_power", "bike_speed", "heart_rate", "34"):
            sensors.append({"component": comp or ("%s %s" % (d.get("manufacturer"), d.get("device_type"))), "bike": bike,
                            "battery": d.get("battery_status"), "serial": d.get("serial_number"), "manufacturer": d.get("manufacturer"), "type": d.get("device_type")})
    bike = max(votes, key=votes.get) if votes else None
    return {"bike": bike, "how": how if bike else None, "sensors": sensors, "has_axs": has_axs}
