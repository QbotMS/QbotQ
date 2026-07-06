#!/usr/bin/env python3
"""Klient Komoot (nieoficjalne API v007) dla QBot.

Uzywa KomootSession (komoot_auth) do uwierzytelnienia. Trzy operacje:
- list_planned_tours: lista zaplanowanych tras uzytkownika (do wykrywania nowych),
- get_tour_meta: metadane trasy (nazwa, dystans, changed_at),
- get_tour_coordinates: pelna geometria trasy (lat/lng/alt) - wierna co do metra.
"""
from __future__ import annotations
import json, os, sys, urllib.request, urllib.error

sys.path.insert(0, "/opt/qbot/app")
import komoot_auth

API = "https://www.komoot.com/api/v007"
USER_ID = os.getenv("KOMOOT_USER_ID", "473936968752")


class KomootClientError(RuntimeError):
    pass


def _get(session, url):
    req = urllib.request.Request(url, headers=session.authed_headers())
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise KomootClientError("Komoot GET %s -> HTTP %s" % (url, e.code))


def list_planned_tours(session=None, limit=50, page=0, user_id=None):
    session = session or komoot_auth.KomootSession()
    uid = user_id or USER_ID
    url = ("%s/users/%s/tours/?type=tour_planned&sort_field=date&sort_direction=desc&limit=%d&page=%d"
           % (API, uid, int(limit), int(page)))
    d = _get(session, url)
    tours = d.get("_embedded", {}).get("tours", [])
    out = []
    for t in tours:
        out.append({
            "id": str(t.get("id")),
            "name": t.get("name"),
            "status": t.get("status"),
            "date": t.get("date"),
            "changed_at": t.get("changed_at"),
            "distance_m": t.get("distance"),
        })
    return {"total": d.get("page", {}).get("totalElements"), "tours": out}


def get_tour_meta(tour_id, session=None):
    session = session or komoot_auth.KomootSession()
    d = _get(session, "%s/tours/%s" % (API, tour_id))
    return {
        "id": str(d.get("id")),
        "name": d.get("name"),
        "status": d.get("status"),
        "changed_at": d.get("changed_at"),
        "distance_m": d.get("distance"),
        "routing_version": d.get("routing_version"),
    }


def get_tour_coordinates(tour_id, session=None):
    session = session or komoot_auth.KomootSession()
    d = _get(session, "%s/tours/%s/coordinates" % (API, tour_id))
    return d.get("items", [])


if __name__ == "__main__":
    s = komoot_auth.KomootSession()
    L = list_planned_tours(s, limit=5)
    print("total_tras:", L["total"])
    for t in L["tours"]:
        print("  -", t["id"], t["status"], t["changed_at"], "|", t["name"])
    if L["tours"]:
        tid = L["tours"][0]["id"]
        pts = get_tour_coordinates(tid, s)
        print("geometria trasy", tid, "-> punktow:", len(pts))
