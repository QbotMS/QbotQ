#!/usr/bin/env python3
"""Podglad QEXT2-NEWS w konsoli (do czasu strony w SETUP): stan zrodel i ostatnie ocenione naglowki.
Uzycie: .venv/bin/python3 scripts/news_status.py [ile=30]. Dok.: docs/QEXT2_WIADOMOSCI.md"""
import os
import sys

sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

import qbot_news as N  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
c = _db_connect()
cur = c.cursor(row_factory=dict_row)
cur.execute("SELECT status, count(*) AS n FROM qbot_v2.news_item GROUP BY status ORDER BY status")
print("STATUSY:", {r["status"]: r["n"] for r in cur.fetchall()})
cur.execute("SELECT name, importance, last_ok_at, last_error FROM qbot_v2.news_source ORDER BY sort")
for r in cur.fetchall():
    ok = r["last_ok_at"].astimezone(N.TZ).strftime("%d.%m %H:%M") if r["last_ok_at"] else "-"
    print(f"  {r['name']:24} {r['importance']:9} ok={ok} {r['last_error'] or ''}")
cur.execute("""SELECT i.status, i.score, i.threshold, i.icon, i.text_pl, i.reason, i.title, i.id, i.group_id, i.published_at, s.name
               FROM qbot_v2.news_item i JOIN qbot_v2.news_source s ON s.id=i.source_id
               WHERE i.assessed_at IS NOT NULL ORDER BY i.score DESC NULLS LAST, i.published_at DESC LIMIT %s""", (n,))
for r in cur.fetchall():
    dub = "" if (r["group_id"] or r["id"]) == r["id"] else f" [dubel {r['group_id']}]"
    print(f"{r['status']:10} {r['score']}/{r['threshold']} {r['icon']:5} {r['published_at'].astimezone(N.TZ):%H:%M} "
          f"{(r['text_pl'] or ''):34} | {r['name']}: {r['title'][:70]} — {r['reason']}{dub}")
