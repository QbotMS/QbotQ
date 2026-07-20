#!/usr/bin/env python3
"""QBot — poranna weryfikacja duplikatow jazd. TYLKO zglasza, NIC nie kasuje.

Co uznaje za duplikat (w qbot_v2.training_sessions):
  1) same_start: ta sama jazda pod >1 external_id — identyczny start (do minuty)
     + dystans (±1%) + czas trwania (±2%). To klasyczny podwojny import.
  2) row_dupe: to samo external_id w >1 wierszu (doslowny dubel wiersza).

Zachowanie:
  - ZAWSZE wypisuje pelny obraz na stdout (cron -> /opt/qbot/logs/verify_dupes.log).
  - Na Telegram wysyla TYLKO gdy pojawi sie NOWA grupa (nie zgloszona wczesniej),
    zeby nie spamowac tym samym codziennie. Stan: data/verify_dupes_seen.json.
  - Dla kazdego podejrzanego ID pokazuje 'slad' w tabelach (activity_record itd.),
    zeby latwo bylo zdecydowac, ktora kopie zostawic.

Flagi:
  --dry-run          nic nie wysyla i NIE zapisuje stanu (bezpieczny test)
  --force-telegram   wyslij nawet jesli nic nowego (pelny obraz na zadanie)
"""
import os, sys, json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
from fitmodel.api import _db_connect
import qbot_config as cfg
import httpx

STATE = Path("/opt/qbot/app/data/verify_dupes_seen.json")
DIST_TOL = 0.01   # ±1% dystansu
DUR_TOL = 0.02    # ±2% czasu

FOOTPRINT = [
    ("qbot_v2.activity_record", "external_id"),
    ("qbot_v2.fitmodel_qext2_ride", "ride_id"),
    ("qbot_v2.fitmodel_wbal_ride", "external_id"),
    ("qbot_v2.fitmodel_segment", "ride_id"),
    ("qbot_v2.fitmodel_ride_buckets", "ride_id"),
]


def _rel(a, b):
    if not a or not b:
        return 1.0
    a, b = float(a), float(b)
    return abs(a - b) / max(a, b)


def find_same_start(cur):
    cur.execute(
        """
        SELECT date_trunc('minute', started_at) AS m,
               array_agg(external_id ORDER BY started_at) AS ids,
               array_agg(distance_m  ORDER BY started_at) AS dists,
               array_agg(duration_s  ORDER BY started_at) AS durs,
               array_agg(source      ORDER BY started_at) AS srcs
        FROM qbot_v2.training_sessions
        WHERE started_at IS NOT NULL AND external_id IS NOT NULL
        GROUP BY 1
        HAVING count(distinct external_id) > 1
        ORDER BY 1 DESC
        """
    )
    groups = []
    for m, ids, dists, durs, srcs in cur.fetchall():
        d0, t0 = dists[0], durs[0]
        similar = (all(_rel(d, d0) <= DIST_TOL for d in dists)
                   and all(_rel(t, t0) <= DUR_TOL for t in durs))
        if similar:
            groups.append({
                "kind": "same_start",
                "when": m.isoformat(),
                "ids": [str(i) for i in ids],
                "dist_m": [round(float(d)) for d in dists],
                "dur_s": [int(t) for t in durs],
                "src": list(srcs),
            })
    return groups


def find_row_dupes(cur):
    cur.execute(
        """
        SELECT external_id, count(*) FROM qbot_v2.training_sessions
        WHERE external_id IS NOT NULL
        GROUP BY external_id HAVING count(*) > 1 ORDER BY 2 DESC
        """
    )
    return [{"kind": "row_dupe", "external_id": str(e), "rows": n}
            for e, n in cur.fetchall()]


def footprint(conn, cur, ext_id):
    """Ile wierszy z danym ID w kazdej tabeli. Odporne na blad (rollback)."""
    out = {}
    for tbl, col in FOOTPRINT:
        try:
            cur.execute(f"SELECT count(*) FROM {tbl} WHERE {col} = %s", (ext_id,))
            out[tbl.split(".")[-1]] = cur.fetchone()[0]
        except Exception:
            conn.rollback()
            out[tbl.split(".")[-1]] = "?"
    return out


def group_key(g):
    if g["kind"] == "same_start":
        return "same_start:" + "|".join(sorted(g["ids"]))
    return "row_dupe:" + g["external_id"]


def send_telegram(text):
    token = getattr(cfg, "TELEGRAM_TOKEN", "") or ""
    chat = getattr(cfg, "TELEGRAM_CHAT_ID", "") or ""
    if not token or not chat:
        print("[telegram] brak TOKEN/CHAT_ID w qbot_config — pomijam wysylke")
        return False
    for i in range(0, len(text), 4000):
        r = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text[i:i + 4000]},
            timeout=10,
        )
        r.raise_for_status()
    return True


def build_message(groups, new_count, force):
    head = f"\u26a0\ufe0f QBot: podejrzenie {len(groups)} zdublowanych jazd"
    if new_count and not force:
        head += f" ({new_count} nowych)"
    lines = [head]
    for g in groups:
        if g["kind"] == "same_start":
            when = g["when"].replace("T", " ")[:16]
            dist_km = round(g["dist_m"][0] / 1000, 1)
            dur_min = round(g["dur_s"][0] / 60)
            lines.append(f"\u2022 {when} \u2014 {dist_km} km / {dur_min} min")
            for eid in g["ids"]:
                ar = g.get("footprint", {}).get(eid, {}).get("activity_record", "?")
                lines.append(f"    {eid}  (1Hz: {ar})")
        else:
            lines.append(f"\u2022 dosl. dubel wiersza external_id={g['external_id']} ({g['rows']}\u00d7)")
    lines.append("\nNic nie skasowano \u2014 decyzja nalezy do Ciebie.")
    return "\n".join(lines)


def main():
    force = "--force-telegram" in sys.argv
    dry = "--dry-run" in sys.argv

    c = _db_connect(); cur = c.cursor()
    groups = find_same_start(cur) + find_row_dupes(cur)
    for g in groups:
        if g["kind"] == "same_start":
            g["footprint"] = {eid: footprint(c, cur, eid) for eid in g["ids"]}
    c.close()

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"=== verify_dupes {stamp} === grup: {len(groups)} (dry={dry} force={force})")
    for g in groups:
        print(json.dumps(g, ensure_ascii=False))

    try:
        seen = set(json.loads(STATE.read_text())) if STATE.exists() else set()
    except Exception:
        seen = set()
    keys = {group_key(g) for g in groups}
    new_groups = [g for g in groups if group_key(g) not in seen]

    if dry:
        print(f"[dry-run] nowych grup: {len(new_groups)} — nie wysylam, nie zapisuje stanu")
        return

    if groups and (new_groups or force):
        ok = send_telegram(build_message(groups, len(new_groups), force))
        print(f"[telegram] {'wyslano' if ok else 'pominieto'} (nowych={len(new_groups)}, force={force})")
    elif groups:
        print("[telegram] brak NOWYCH grup — cisza (uzyj --force-telegram)")
    else:
        print("[telegram] brak duplikatow — cisza")

    try:
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps(sorted(keys), ensure_ascii=False, indent=2))
    except Exception as e:
        print("[state] zapis nieudany:", e)


if __name__ == "__main__":
    main()
