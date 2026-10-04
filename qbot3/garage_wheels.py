"""Kola jako zestaw (garaz SQLite). DECYZJA 2026-10-01 (Michal).

Zestaw kol = komponent category='wheels'. Jego bike_id = rower, w ktorym jest zamontowany (NULL = na polce).
Czesci kola (kaseta, tarcze 'rotors', wkladki 'tubeless insert') maja components.wheel_id; ich bike_id
zawsze podaza za kolem. Opony maja wlasne tires.wheel_id (bez bike_id).
Miejsce na kole: components.wheel_pos (przod|tyl). Jedno miejsce = jedna czesc danej kategorii:
kaseta 1 na zestaw (zawsze tyl), tarcza i wkladka po 1 na przod i tyl. Montaz nowej czesci w zajetym
miejscu zdejmuje stara (wheel_id/bike_id NULL, status zapas) -- free_slot(), wolane z zapisu komponentu.
Historia montazu: wheel_mounts (from_at/to_at, source manual|sensor|start) -- pod przyszly przebieg kol.

Rozpoznanie: czujnik predkosci (serial z FIT) -> wheel_sensor -> zestaw. Jazda z takim czujnikiem na innym
rowerze niz obecny montaz -> przelozenie (source=sensor). Inny zestaw w tym rowerze -> na polke.
Jazda BEZ czujnika predkosci (albo z nieznanym) -> NIC nie zmieniamy w garazu.
Starsze jazdy niz ostatni montaz nie cofaja stanu (backfill bezpieczny).
"""
from __future__ import annotations
import os, sqlite3

GARAGE_DB = os.getenv("QBOT_GARAGE_DB", "/opt/qbot/app/data/garage.db")
WHEEL_PART_CATS = ("cassette", "rotors", "tubeless insert")


def gconn():
    c = sqlite3.connect(GARAGE_DB); c.row_factory = sqlite3.Row
    return c


def ensure(gc):
    cols = {r[1] for r in gc.execute("PRAGMA table_info(components)")}
    if "wheel_id" not in cols:
        gc.execute("ALTER TABLE components ADD COLUMN wheel_id INTEGER")
    if "wheel_pos" not in cols:
        gc.execute("ALTER TABLE components ADD COLUMN wheel_pos TEXT")
    gc.execute("""CREATE TABLE IF NOT EXISTS wheel_sensor(
        serial_number INTEGER PRIMARY KEY, wheel_id INTEGER NOT NULL, note TEXT)""")
    gc.execute("""CREATE TABLE IF NOT EXISTS wheel_mounts(
        id INTEGER PRIMARY KEY AUTOINCREMENT, wheel_id INTEGER NOT NULL, bike_id INTEGER,
        from_at TEXT NOT NULL, to_at TEXT, source TEXT, ride_key TEXT)""")
    gc.commit()


WHEEL_POS = ("przód", "tył")


def free_slot(gc, part_id, wheel_id, category, wheel_pos, commit=True):
    """Zdejmij z kola stara czesc z tego samego miejsca. Zwraca id zdjetych."""
    if not wheel_id or category not in WHEEL_PART_CATS:
        return []
    if category == "cassette":
        q = ("SELECT id FROM components WHERE wheel_id=? AND category='cassette' AND active=1 AND id<>?",
             (int(wheel_id), int(part_id)))
    elif wheel_pos in WHEEL_POS:
        q = ("SELECT id FROM components WHERE wheel_id=? AND category=? AND wheel_pos=? AND active=1 AND id<>?",
             (int(wheel_id), category, wheel_pos, int(part_id)))
    else:
        return []                                     # bez strony kola nie wiadomo co zdjac
    ids = [r[0] for r in gc.execute(*q)]
    for i in ids:
        gc.execute("UPDATE components SET wheel_id=NULL, bike_id=NULL, status='zapas' WHERE id=?", (i,))
    if commit:
        gc.commit()
    return ids


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _set_wheel_bike(gc, wheel_id, bike_id):
    gc.execute("UPDATE components SET bike_id=? WHERE id=?", (bike_id, wheel_id))
    gc.execute("UPDATE components SET bike_id=? WHERE wheel_id=?", (bike_id, wheel_id))


def mount(gc, wheel_id: int, bike_id, at=None, source="manual", ride_key=None, commit=True):
    """Zamontuj zestaw w rowerze (bike_id=None -> zdejmij na polke). Inne zestawy w tym rowerze -> polka."""
    ensure(gc)
    at = at or _now()
    wheel_id = int(wheel_id)
    bike_id = int(bike_id) if bike_id not in (None, "", 0) else None
    gc.execute("UPDATE wheel_mounts SET to_at=? WHERE wheel_id=? AND to_at IS NULL", (at, wheel_id))
    if bike_id is not None:
        others = [r[0] for r in gc.execute(
            "SELECT id FROM components WHERE category='wheels' AND active=1 AND bike_id=? AND id<>?", (bike_id, wheel_id))]
        for o in others:
            gc.execute("UPDATE wheel_mounts SET to_at=? WHERE wheel_id=? AND to_at IS NULL", (at, o))
            _set_wheel_bike(gc, o, None)
            gc.execute("INSERT INTO wheel_mounts(wheel_id,bike_id,from_at,source,ride_key) VALUES(?,?,?,?,?)",
                       (o, None, at, source, ride_key))
    _set_wheel_bike(gc, wheel_id, bike_id)
    gc.execute("INSERT INTO wheel_mounts(wheel_id,bike_id,from_at,source,ride_key) VALUES(?,?,?,?,?)",
               (wheel_id, bike_id, at, source, ride_key))
    if commit:
        gc.commit()


def wheel_bike(gc, wheel_id):
    r = gc.execute("SELECT bike_id FROM components WHERE id=?", (int(wheel_id),)).fetchone()
    return r[0] if r else None


def on_ride(pg_conn, external_id: str, log=print):
    """Po imporcie jazdy: czujnik predkosci -> ewentualne przelozenie kol. Zwraca opis albo None."""
    cur = pg_conn.cursor()
    cur.execute("""SELECT DISTINCT serial_number FROM qbot_v2.activity_device
                   WHERE external_id=%s AND device_type='bike_speed' AND serial_number IS NOT NULL""", (str(external_id),))
    serials = [(r["serial_number"] if isinstance(r, dict) else r[0]) for r in cur.fetchall()]
    if not serials:
        return None                                   # brak czujnika predkosci -> nic nie zmieniamy
    cur.execute("SELECT started_at FROM qbot_v2.training_sessions WHERE external_id=%s ORDER BY imported_at DESC LIMIT 1",
                (str(external_id),))
    r = cur.fetchone()
    st = (r["started_at"] if isinstance(r, dict) else r[0]) if r else None
    if st is None:
        return None
    from datetime import timezone as _tz
    st = st.astimezone(_tz.utc)
    from qbot3.rides.activity_devices import bike_for_ride
    name = bike_for_ride(pg_conn, str(external_id)).get("bike")
    if not name:
        return None
    cur.execute("SELECT garage_bike_id FROM qbot_v2.bike_odometer WHERE sensor_bike=%s", (name,))
    r = cur.fetchone()
    if not r:
        return None
    bike_id = int(r["garage_bike_id"] if isinstance(r, dict) else r[0])
    gc = gconn()
    try:
        ensure(gc)
        out = []
        for s in serials:
            w = gc.execute("SELECT wheel_id FROM wheel_sensor WHERE serial_number=?", (int(s),)).fetchone()
            if not w:
                continue                              # nieznany czujnik -> nic
            wid = int(w[0])
            if wheel_bike(gc, wid) == bike_id:
                # juz tu jest; jesli inny zestaw tez wisi na tym rowerze -> zdejmij go
                dup = gc.execute("SELECT 1 FROM components WHERE category='wheels' AND active=1 AND bike_id=? AND id<>?",
                                 (bike_id, wid)).fetchone()
                last = gc.execute("SELECT max(from_at) FROM wheel_mounts WHERE wheel_id=?", (wid,)).fetchone()[0]
                if dup and (last is None or st.isoformat() > last):
                    mount(gc, wid, bike_id, st.isoformat(), "sensor", str(external_id))
                    out.append("kola %s: drugi zestaw zdjety z roweru %s" % (wid, bike_id))
                continue
            last = gc.execute("SELECT max(from_at) FROM wheel_mounts WHERE wheel_id=?", (wid,)).fetchone()[0]
            if last is not None and st.isoformat() <= last:
                continue                              # starsza jazda nie cofa stanu
            mount(gc, wid, bike_id, st.isoformat(), "sensor", str(external_id))
            out.append("kola %s -> rower %s" % (wid, bike_id))
        if out:
            log("   kola: " + "; ".join(out))
        return out or None
    finally:
        gc.close()
