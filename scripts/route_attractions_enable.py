#!/usr/bin/env python3
"""Wlacza trwaly przelacznik atrakcji trasy (jak POBIERZ na stronie), bez liczenia.
  .venv/bin/python3 scripts/route_attractions_enable.py <route_id>"""
import os
import sys

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
from qbot3.routes.route_poi_store import set_route_poi_attractions  # noqa: E402

print(set_route_poi_attractions(sys.argv[1], True))
