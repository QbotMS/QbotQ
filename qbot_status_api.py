#!/usr/bin/env python3
"""SETUP > Polaczenia > Status (15.10.2026): GET /api/setup/status -> qbot_status_checks.all_checks().
SETUP > Polaczenia > Aktualizacje (19.10.2026): GET /api/setup/updates (state/updates.json),
  POST /api/setup/updates/refresh -> plik state/updates.request -> qbot-updates-check.path (root) uruchamia
  scripts/updates_check.py. Strona: /opt/qbot/web/public/aktualizacje.html.
Tylko odczyt (refresh tylko zleca sprawdzenie, niczego nie instaluje); tylko wlasciciel (sesja demo -> 403).
Strony: status.html, aktualizacje.html (ramki w setup.html). Dok.: docs/STATUS.md, docs/AKTUALIZACJE.md
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

_STATE = Path("/opt/qbot/app/state")


def build_router(current_user, owner_user):
    r = APIRouter(prefix="/api/setup")

    def _guard(request: Request):
        if not current_user(request):
            raise HTTPException(status_code=401, detail="unauthorized")
        if not owner_user(request):
            raise HTTPException(status_code=403, detail="tylko dla wlasciciela")

    @r.get("/status")
    def setup_status(request: Request):  # def (nie async) -> wykonuje sie w puli watkow, nie blokuje serwera
        _guard(request)
        from qbot_status_checks import all_checks
        return all_checks()

    @r.get("/updates")
    def setup_updates(request: Request):
        _guard(request)
        req = _STATE / "updates.request"
        try:
            data = json.loads((_STATE / "updates.json").read_text())
        except FileNotFoundError:
            data = {"missing": True, "items": [], "counts": {}}
        data.pop("first_seen", None)
        data.pop("python", None)  # strona uzywa items (te same pakiety, juz ocenione) -> mniejsza odpowiedz
        data["refresh_pending"] = req.exists()
        return data

    @r.post("/updates/refresh")
    def setup_updates_refresh(request: Request):
        _guard(request)
        (_STATE / "updates.request").write_text("web\n")
        return {"ok": True, "pending": True}

    return r
