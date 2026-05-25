"""
db.py — lokalny garaż Q-bota (SQLite)
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "data" / "garage.db"
ARTIFACT_ROOT = Path("/opt/qbot/artifacts")
ARTIFACT_SCAN_LIMIT_BYTES = 200_000
ARTIFACT_SEARCH_SUFFIXES = {
    ".md", ".markdown", ".txt", ".json", ".html", ".htm", ".xml", ".csv",
    ".yaml", ".yml", ".sh", ".py", ".ini", ".cfg", ".log",
}

TRIP_SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    destination   TEXT,
    country       TEXT,
    start_date    TEXT,
    end_date      TEXT,
    type          TEXT,          -- road | gravel | bikepacking | mtb | mixed
    distance_km   REAL,
    elevation_m   INTEGER,
    bike_id       INTEGER REFERENCES bikes(id),
    accommodation TEXT,          -- camping | hotel | mixed | warmshowers | hut
    notes         TEXT,
    status        TEXT DEFAULT 'planned',  -- planned | active | completed
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS packing_lists (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id    INTEGER REFERENCES trips(id),
    name       TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS packing_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id      INTEGER REFERENCES packing_lists(id),
    category     TEXT,           -- rower | odzież | elektronika | narzędzia | jedzenie | nocleg | dokumenty | inne
    item         TEXT NOT NULL,
    quantity     INTEGER DEFAULT 1,
    packed       INTEGER DEFAULT 0,
    from_garage  INTEGER DEFAULT 0,   -- 1 = pochodzi z garażu użytkownika
    gear_id      INTEGER REFERENCES gear(id),
    notes        TEXT
);
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS bikes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    brand         TEXT,
    model         TEXT,
    type          TEXT,          -- road | gravel | mtb | tt | track | urban
    year          INTEGER,
    color         TEXT,
    weight_kg     REAL,
    frame_size    TEXT,
    purchase_date TEXT,
    purchase_price REAL,
    notes         TEXT,
    active        INTEGER DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS components (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    bike_id        INTEGER REFERENCES bikes(id),
    category       TEXT,   -- groupset | shifters | derailleurs | cassette | chain |
                           -- crankset | brakes | wheels | tires | saddle | seatpost |
                           -- handlebar | stem | pedals | computer | lights | other
    position       TEXT,   -- front | rear | left | right (opcjonalnie)
    brand          TEXT,
    model          TEXT,
    spec           TEXT,   -- np. "50/34T", "11-30T 11s", "25c"
    weight_g       INTEGER,
    purchase_date  TEXT,
    purchase_price REAL,
    mileage_km     REAL DEFAULT 0,
    serial_number  TEXT,
    notes          TEXT,
    active         INTEGER DEFAULT 1,
    created_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fitting (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bike_id             INTEGER REFERENCES bikes(id),
    saddle_height_mm    REAL,
    saddle_setback_mm   REAL,
    saddle_tilt_deg     REAL,
    reach_mm            REAL,
    stack_mm            REAL,
    drop_mm             REAL,
    handlebar_width_mm  INTEGER,
    stem_length_mm      INTEGER,
    stem_angle_deg      INTEGER,
    crank_length_mm     INTEGER,
    cleat_left          TEXT,
    cleat_right         TEXT,
    shoe_size           TEXT,
    notes               TEXT,
    date_set            TEXT,
    fitter_name         TEXT,
    created_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gear (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    category       TEXT,   -- helmet | shoes | jersey | bib_shorts | jacket |
                           -- vest | gloves | socks | arm_warmers | leg_warmers |
                           -- base_layer | glasses | bag | other
    brand          TEXT,
    model          TEXT,
    size           TEXT,
    color          TEXT,
    purchase_date  TEXT,
    purchase_price REAL,
    condition      TEXT DEFAULT 'good',   -- new | good | worn | retired
    notes          TEXT,
    active         INTEGER DEFAULT 1,
    created_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS memories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    topic      TEXT,
    content    TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _conn() as c:
        c.executescript(SCHEMA)
        c.executescript(TRIP_SCHEMA)


def _rows(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


# ── Garage overview ───────────────────────────────────────────────────────────
def garage_overview() -> dict:
    with _conn() as c:
        bikes      = _rows(c.execute("SELECT * FROM bikes WHERE active=1 ORDER BY name"))
        components = _rows(c.execute("SELECT * FROM components WHERE active=1 ORDER BY bike_id, category"))
        gear       = _rows(c.execute("SELECT * FROM gear WHERE active=1 ORDER BY category, brand"))
        memories   = _rows(c.execute("SELECT * FROM memories ORDER BY updated_at DESC LIMIT 20"))
        # Attach components to each bike
        comp_by_bike = {}
        for comp in components:
            bid = comp["bike_id"]
            comp_by_bike.setdefault(bid, []).append(comp)
        # Attach fitting
        for bike in bikes:
            bike["components"] = comp_by_bike.get(bike["id"], [])
            fit = _rows(c.execute(
                "SELECT * FROM fitting WHERE bike_id=? ORDER BY created_at DESC LIMIT 1",
                (bike["id"],)
            ))
            bike["fitting"] = fit[0] if fit else None

    return {
        "bikes":    bikes,
        "gear":     gear,
        "memories": memories,
    }


def get_bike(bike_id: int) -> dict | None:
    with _conn() as c:
        rows = _rows(c.execute("SELECT * FROM bikes WHERE id=?", (bike_id,)))
        if not rows:
            return None
        bike = rows[0]
        bike["components"] = _rows(c.execute(
            "SELECT * FROM components WHERE bike_id=? AND active=1 ORDER BY category",
            (bike_id,)
        ))
        fit = _rows(c.execute(
            "SELECT * FROM fitting WHERE bike_id=? ORDER BY created_at DESC LIMIT 1",
            (bike_id,)
        ))
        bike["fitting"] = fit[0] if fit else None
    return bike


def save_bike(data: dict) -> dict:
    cols = ["name","brand","model","type","year","color","weight_kg",
            "frame_size","purchase_date","purchase_price","notes","active"]
    with _conn() as c:
        if "id" in data and data["id"]:
            sets = ", ".join(f"{k}=?" for k in data if k in cols)
            vals = [data[k] for k in data if k in cols] + [data["id"]]
            c.execute(f"UPDATE bikes SET {sets} WHERE id=?", vals)
            return {"action": "updated", "id": data["id"]}
        else:
            keys = [k for k in data if k in cols]
            vals = [data[k] for k in keys]
            cur = c.execute(
                f"INSERT INTO bikes ({','.join(keys)}) VALUES ({','.join(['?']*len(keys))})",
                vals
            )
            return {"action": "created", "id": cur.lastrowid}


def save_component(data: dict) -> dict:
    cols = ["bike_id","category","position","brand","model","spec","weight_g",
            "purchase_date","purchase_price","mileage_km","serial_number","notes","active"]
    with _conn() as c:
        if "id" in data and data["id"]:
            sets = ", ".join(f"{k}=?" for k in data if k in cols)
            vals = [data[k] for k in data if k in cols] + [data["id"]]
            c.execute(f"UPDATE components SET {sets} WHERE id=?", vals)
            return {"action": "updated", "id": data["id"]}
        else:
            keys = [k for k in data if k in cols]
            vals = [data[k] for k in keys]
            cur = c.execute(
                f"INSERT INTO components ({','.join(keys)}) VALUES ({','.join(['?']*len(keys))})",
                vals
            )
            return {"action": "created", "id": cur.lastrowid}


def save_fitting(data: dict) -> dict:
    cols = ["bike_id","saddle_height_mm","saddle_setback_mm","saddle_tilt_deg",
            "reach_mm","stack_mm","drop_mm","handlebar_width_mm","stem_length_mm",
            "stem_angle_deg","crank_length_mm","cleat_left","cleat_right",
            "shoe_size","notes","date_set","fitter_name"]
    with _conn() as c:
        if "id" in data and data["id"]:
            sets = ", ".join(f"{k}=?" for k in data if k in cols)
            vals = [data[k] for k in data if k in cols] + [data["id"]]
            c.execute(f"UPDATE fitting SET {sets} WHERE id=?", vals)
            return {"action": "updated", "id": data["id"]}
        else:
            keys = [k for k in data if k in cols]
            vals = [data[k] for k in keys]
            cur = c.execute(
                f"INSERT INTO fitting ({','.join(keys)}) VALUES ({','.join(['?']*len(keys))})",
                vals
            )
            return {"action": "created", "id": cur.lastrowid}


def save_gear(data: dict) -> dict:
    cols = ["category","brand","model","size","color","purchase_date",
            "purchase_price","condition","notes","active"]
    with _conn() as c:
        if "id" in data and data["id"]:
            sets = ", ".join(f"{k}=?" for k in data if k in cols)
            vals = [data[k] for k in data if k in cols] + [data["id"]]
            c.execute(f"UPDATE gear SET {sets} WHERE id=?", vals)
            return {"action": "updated", "id": data["id"]}
        else:
            keys = [k for k in data if k in cols]
            vals = [data[k] for k in keys]
            cur = c.execute(
                f"INSERT INTO gear ({','.join(keys)}) VALUES ({','.join(['?']*len(keys))})",
                vals
            )
            return {"action": "created", "id": cur.lastrowid}


def save_memory(topic: str, content: str) -> dict:
    with _conn() as c:
        # Upsert po topicu
        existing = _rows(c.execute("SELECT id FROM memories WHERE topic=?", (topic,)))
        if existing:
            c.execute(
                "UPDATE memories SET content=?, updated_at=datetime('now') WHERE topic=?",
                (content, topic)
            )
            return {"action": "updated", "topic": topic}
        else:
            c.execute("INSERT INTO memories (topic, content) VALUES (?,?)", (topic, content))
            return {"action": "created", "topic": topic}


def save_memory_append(topic: str, content: str) -> dict:
    """Append a memory note to an existing topic, avoiding exact duplicates."""
    clean = (content or "").strip()
    if not clean:
        return {"error": "empty content", "topic": topic}
    with _conn() as c:
        existing = _rows(c.execute("SELECT content FROM memories WHERE topic=?", (topic,)))
        if not existing:
            c.execute("INSERT INTO memories (topic, content) VALUES (?,?)", (topic, clean))
            return {"action": "created", "topic": topic}
        old = existing[0].get("content") or ""
        if clean in old:
            return {"action": "skipped_duplicate", "topic": topic}
        merged = f"{old.rstrip()}\n\n---\n{clean}" if old.strip() else clean
        c.execute(
            "UPDATE memories SET content=?, updated_at=datetime('now') WHERE topic=?",
            (merged, topic)
        )
        return {"action": "appended", "topic": topic}


def search_garage(query: str) -> dict:
    q = f"%{query}%"
    needle = (query or "").strip().lower()
    with _conn() as c:
        bikes = _rows(c.execute(
            "SELECT id, name, brand, model, type FROM bikes WHERE "
            "name LIKE ? OR brand LIKE ? OR model LIKE ? OR notes LIKE ?",
            (q, q, q, q)
        ))
        components = _rows(c.execute(
            "SELECT id, bike_id, category, brand, model, spec FROM components WHERE "
            "brand LIKE ? OR model LIKE ? OR category LIKE ? OR notes LIKE ? OR spec LIKE ?",
            (q, q, q, q, q)
        ))
        gear = _rows(c.execute(
            "SELECT id, category, brand, model, size FROM gear WHERE "
            "brand LIKE ? OR model LIKE ? OR category LIKE ? OR notes LIKE ?",
            (q, q, q, q)
        ))
        memories = _rows(c.execute(
            "SELECT id, topic, content FROM memories WHERE topic LIKE ? OR content LIKE ?",
            (q, q)
        ))
    artifacts = []
    if needle and ARTIFACT_ROOT.exists():
        for path in sorted(ARTIFACT_ROOT.rglob("*")):
            if not path.is_file():
                continue
            try:
                resolved = path.resolve(strict=False)
                if not resolved.is_relative_to(ARTIFACT_ROOT):
                    continue
            except Exception:
                continue
            rel = path.relative_to(ARTIFACT_ROOT).as_posix()
            hay_parts = [rel.lower()]
            text = ""
            if path.suffix.lower() in ARTIFACT_SEARCH_SUFFIXES:
                try:
                    text = path.read_bytes()[:ARTIFACT_SCAN_LIMIT_BYTES].decode("utf-8", errors="replace")
                    hay_parts.append(text.lower())
                except Exception:
                    text = ""
            if needle not in "\n".join(hay_parts):
                continue
            snippet = None
            if text:
                idx = text.lower().find(needle)
                if idx >= 0:
                    start = max(0, idx - 120)
                    end = min(len(text), idx + max(len(query), 120))
                    snippet = text[start:end].strip()
            artifacts.append({
                "relative_path": rel,
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "match_in": "filename" if needle in rel.lower() else "content",
                "snippet": snippet,
            })
            if len(artifacts) >= 25:
                break
    return {"bikes": bikes, "components": components, "gear": gear, "memories": memories, "artifacts": artifacts}


def update_item(table: str, item_id: int, changes: dict) -> dict:
    allowed = {"bikes", "components", "fitting", "gear", "memories"}
    if table not in allowed:
        return {"error": f"Niedozwolona tabela: {table}"}
    with _conn() as c:
        sets = ", ".join(f"{k}=?" for k in changes)
        vals = list(changes.values()) + [item_id]
        c.execute(f"UPDATE {table} SET {sets} WHERE id=?", vals)
        return {"action": "updated", "table": table, "id": item_id}


def delete_item(table: str, item_id: int) -> dict:
    allowed = {"bikes", "components", "fitting", "gear", "memories",
               "trips", "packing_lists", "packing_items"}
    if table not in allowed:
        return {"error": f"Niedozwolona tabela: {table}"}
    with _conn() as c:
        if table in {"bikes", "components", "gear"}:
            c.execute(f"UPDATE {table} SET active=0 WHERE id=?", (item_id,))
            return {"action": "deactivated", "table": table, "id": item_id}
        else:
            c.execute(f"DELETE FROM {table} WHERE id=?", (item_id,))
            return {"action": "deleted", "table": table, "id": item_id}


# ═══════════════════════════════════════════════════════════════════════════════
# PODRÓŻE & LISTY PAKOWANIA
# ═══════════════════════════════════════════════════════════════════════════════

def get_trips(status: str = None) -> list:
    with _conn() as c:
        if status:
            trips = _rows(c.execute(
                "SELECT t.*, b.name as bike_name FROM trips t "
                "LEFT JOIN bikes b ON t.bike_id=b.id WHERE t.status=? ORDER BY t.start_date DESC",
                (status,)
            ))
        else:
            trips = _rows(c.execute(
                "SELECT t.*, b.name as bike_name FROM trips t "
                "LEFT JOIN bikes b ON t.bike_id=b.id ORDER BY t.start_date DESC"
            ))
        for trip in trips:
            lists = _rows(c.execute(
                "SELECT id, name, created_at FROM packing_lists WHERE trip_id=?",
                (trip["id"],)
            ))
            trip["packing_lists"] = lists
    return trips


def get_trip(trip_id: int) -> dict | None:
    with _conn() as c:
        rows = _rows(c.execute(
            "SELECT t.*, b.name as bike_name FROM trips t "
            "LEFT JOIN bikes b ON t.bike_id=b.id WHERE t.id=?",
            (trip_id,)
        ))
        if not rows:
            return None
        trip = rows[0]
        lists = _rows(c.execute(
            "SELECT * FROM packing_lists WHERE trip_id=?", (trip_id,)
        ))
        for lst in lists:
            lst["items"] = _rows(c.execute(
                "SELECT pi.*, g.brand as gear_brand, g.model as gear_model "
                "FROM packing_items pi "
                "LEFT JOIN gear g ON pi.gear_id=g.id "
                "WHERE pi.list_id=? ORDER BY pi.category, pi.item",
                (lst["id"],)
            ))
        trip["packing_lists"] = lists
    return trip


def save_trip(data: dict) -> dict:
    cols = ["name", "destination", "country", "start_date", "end_date", "type",
            "distance_km", "elevation_m", "bike_id", "accommodation", "notes", "status"]
    with _conn() as c:
        if "id" in data and data["id"]:
            sets = ", ".join(f"{k}=?" for k in data if k in cols)
            vals = [data[k] for k in data if k in cols] + [data["id"]]
            c.execute(f"UPDATE trips SET {sets} WHERE id=?", vals)
            return {"action": "updated", "id": data["id"]}
        else:
            keys = [k for k in data if k in cols]
            vals = [data[k] for k in keys]
            cur = c.execute(
                f"INSERT INTO trips ({','.join(keys)}) VALUES ({','.join(['?']*len(keys))})",
                vals
            )
            return {"action": "created", "id": cur.lastrowid}


def create_packing_list(trip_id: int, name: str, items: list) -> dict:
    """
    items: lista słowników z polami:
      category, item, quantity, from_garage, gear_id, notes
    """
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO packing_lists (trip_id, name) VALUES (?,?)",
            (trip_id, name)
        )
        list_id = cur.lastrowid
        for it in items:
            c.execute(
                "INSERT INTO packing_items (list_id, category, item, quantity, from_garage, gear_id, notes) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    list_id,
                    it.get("category", "inne"),
                    it.get("item", ""),
                    it.get("quantity", 1),
                    1 if it.get("from_garage") else 0,
                    it.get("gear_id"),
                    it.get("notes")
                )
            )
    return {"action": "created", "list_id": list_id, "items_count": len(items)}


def update_packing_item(item_id: int, packed: bool = None, notes: str = None) -> dict:
    changes = {}
    if packed is not None:
        changes["packed"] = 1 if packed else 0
    if notes is not None:
        changes["notes"] = notes
    if not changes:
        return {"error": "Brak zmian do zapisania"}
    with _conn() as c:
        sets = ", ".join(f"{k}=?" for k in changes)
        vals = list(changes.values()) + [item_id]
        c.execute(f"UPDATE packing_items SET {sets} WHERE id=?", vals)
    return {"action": "updated", "item_id": item_id, **changes}


def add_packing_item(list_id: int, category: str, item: str,
                     quantity: int = 1, from_garage: bool = False,
                     gear_id: int = None, notes: str = None) -> dict:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO packing_items (list_id, category, item, quantity, from_garage, gear_id, notes) "
            "VALUES (?,?,?,?,?,?,?)",
            (list_id, category, item, quantity, 1 if from_garage else 0, gear_id, notes)
        )
    return {"action": "created", "item_id": cur.lastrowid}


def get_packing_summary(list_id: int) -> dict:
    """Podsumowanie postępu pakowania"""
    with _conn() as c:
        items = _rows(c.execute(
            "SELECT category, item, quantity, packed, from_garage, notes "
            "FROM packing_items WHERE list_id=? ORDER BY category, item",
            (list_id,)
        ))
    total = len(items)
    packed = sum(1 for i in items if i["packed"])
    by_category: dict = {}
    for it in items:
        cat = it["category"]
        by_category.setdefault(cat, []).append(it)
    return {
        "total": total,
        "packed": packed,
        "remaining": total - packed,
        "progress_pct": round(packed / total * 100) if total else 0,
        "by_category": by_category
    }
