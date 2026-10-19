"""Czujniki i rower per jazda z FIT device_info. DECISIONS 2026-09-12.

qbot_v2.activity_device: jedna linia na (jazda, urzadzenie) -- producent, produkt, serial, typ, bateria.
qbot_v2.bike_sensor: mapowanie czujnika (serial lub producent+typ) -> rower/komponent (z Garazu).
bike_for_ride(): rower z JEDNEJ reguly bike_from_devices (2026-10-19): AXS z numerem ANT (Grizl 10625, Grail 27856),
brak AXS = Monster, sama glowica = nie wiadomo. CZUJNIK PREDKOSCI = KOLO (Garaz wheel_sensor), nie rower;
mierniki mocy sa przekladane -- tez nie decyduja o rowerze. (Wczesniej glosowanie ANT +5 / serial +3 / typ +1.)
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
ALTER TABLE qbot_v2.bike_sensor ADD COLUMN IF NOT EXISTS ant_device_number int;
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
    cur.execute("SELECT device_index,manufacturer,product,product_name,serial_number,device_type,source_type,battery_status,battery_voltage,ant_device_number FROM qbot_v2.activity_device WHERE external_id=%s ORDER BY device_index", (external_id,))
    cols = ["device_index","manufacturer","product","product_name","serial_number","device_type","source_type","battery_status","battery_voltage","ant_device_number"]
    return [(dict(r) if isinstance(r, dict) else dict(zip(cols, r))) for r in cur.fetchall()]


ASK_WHY = "tylko Karoo, czujniki niepołączone"
NO_AXS_BIKE = "Canyon Grand Canyon"      # Monster: jedyny rower bez AXS (regula Michala)
BIKE_SHORT = {"Canyon Grail": "Grail", "Canyon Grizl": "Grizl", "Canyon Grand Canyon": "Monster"}
GARAGE_DB = "/opt/qbot/app/data/garage.db"


def _is_axs(d) -> bool:
    # typ 34 = bike_shifting (AXS). Producent bywa w FIT bledny (styczen 2026: 'garmin' przy AXS 10625) -- nie sprawdzamy go.
    return str(d.get("device_type")) == "34"


def bike_from_devices(devs: list, maps: list) -> tuple:
    """JEDYNA regula roweru w QBot (2026-10-19, decyzja Michala). Czysta funkcja: devs = activity_device jazdy,
    maps = wiersze bike_sensor (bike, component, manufacturer, device_type, serial, ant_device_number).
    -> (rower | None, how, has_axs, powod).
    1) AXS z numerem ANT z bike_sensor -> ten rower (Grail 27856 / Grizl 10625).
    2) AXS z serialem z bike_sensor (stare FIT Garmina bez numeru ANT) -> ten rower.
    3) AXS nieprzypisany -> None (nie zgadujemy).
    4) brak AXS, ale sa czujniki -> Monster (NO_AXS_BIKE).
    5) sama glowica (Karoo po restarcie, czujniki niepolaczone) -> None, powod ASK_WHY; pusta lista -> None.
    CZUJNIK PREDKOSCI IDENTYFIKUJE KOLO, NIE ROWER (kola i czujniki sa przekladane) -- nie glosuje o rowerze.
    Mierniki mocy tez sa przekladane (pedaly Favero, Quarq) -- tez nie glosuja."""
    if not devs:
        return None, None, False, "brak listy czujnikow"
    sensors = [d for d in devs if str(d.get("device_index")) not in ("0", "creator")]
    if not sensors:
        return None, None, False, ASK_WHY
    axs = [d for d in sensors if _is_axs(d)]
    if not axs:
        return NO_AXS_BIKE, "brak_axs", False, "brak AXS"
    for d in axs:
        for bk, _c, _m, t, s_, an in maps:
            if str(t) != "34":
                continue
            if an is not None and d.get("ant_device_number") == an:
                return bk, "axs", True, "AXS %s" % an
            if s_ is not None and d.get("serial_number") == s_:
                return bk, "axs_serial", True, "AXS serial %s" % s_
    return None, None, True, "AXS nieprzypisany (ANT %s, serial %s)" % (
        [d.get("ant_device_number") for d in axs], [d.get("serial_number") for d in axs])


def _wheel_names() -> dict:
    """serial czujnika predkosci -> nazwa kola (Garaz: wheel_sensor + components)."""
    try:
        import sqlite3
        g = sqlite3.connect("file:%s?mode=ro" % GARAGE_DB, uri=True)
        try:
            return {int(sn): ("%s %s" % (br or "", mo or "")).strip() for sn, br, mo in g.execute(
                "SELECT ws.serial_number, c.brand, c.model FROM wheel_sensor ws LEFT JOIN components c ON c.id=ws.wheel_id")}
        finally:
            g.close()
    except Exception:
        return {}


def load_maps(conn) -> list:
    cur = conn.cursor()
    cur.execute("SELECT bike,component,manufacturer,device_type,serial_number,ant_device_number FROM qbot_v2.bike_sensor WHERE active")
    return [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in cur.fetchall()]


def bike_for_ride(conn, external_id: str) -> dict:
    """{'bike': nazwa|None, 'how': ..., 'sensors': [...z komponentem i bateria...], 'has_axs': bool, 'why': powod}.
    Rower WYLACZNIE z bike_from_devices (jedna regula). bike_sensor sluzy tu tez do NAZW komponentow;
    czujniki predkosci opisywane kolem z Garazu (wheel_sensor)."""
    devs = devices_for_ride(conn, external_id)
    maps = load_maps(conn)
    bike, how, has_axs, why = bike_from_devices(devs, maps)
    wheels = _wheel_names()
    sensors = []
    for d in devs:
        if not (d.get("source_type") == "antplus" or d.get("device_type") in ("bike_power", "bike_speed", "heart_rate", "34")):
            continue
        comp = None
        if d.get("device_type") == "bike_speed" and d.get("serial_number") in wheels:
            comp = "czujnik prędkości (koło: %s)" % wheels[d.get("serial_number")]
        if comp is None:
            for bk, cpn, m, t, s_, an in maps:
                if (an is not None and d.get("ant_device_number") == an and m == d.get("manufacturer")) or \
                   (s_ is not None and d.get("serial_number") == s_) or \
                   (s_ is None and an is None and m == d.get("manufacturer") and str(t) == str(d.get("device_type"))):
                    comp = cpn
                    break
        sensors.append({"component": comp or ("%s %s" % (d.get("manufacturer"), d.get("device_type"))),
                        "bike": bike if _is_axs(d) else None,
                        "battery": d.get("battery_status"), "serial": d.get("serial_number"), "manufacturer": d.get("manufacturer"),
                        "type": d.get("device_type")})
    return {"bike": bike, "how": how if bike else None, "sensors": sensors, "has_axs": has_axs, "why": why}
