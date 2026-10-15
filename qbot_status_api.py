#!/usr/bin/env python3
"""SETUP > Polaczenia > Status (15.10.2026): GET /api/setup/status -> qbot_status_checks.all_checks().
Tylko odczyt; tylko wlasciciel (sesja demo -> 403). Strona: /opt/qbot/web/public/status.html (ramka w setup.html).
Dok.: docs/STATUS.md
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request


def build_router(current_user, owner_user):
    r = APIRouter(prefix="/api/setup")

    @r.get("/status")
    def setup_status(request: Request):  # def (nie async) -> wykonuje sie w puli watkow, nie blokuje serwera
        if not current_user(request):
            raise HTTPException(status_code=401, detail="unauthorized")
        if not owner_user(request):
            raise HTTPException(status_code=403, detail="tylko dla wlasciciela")
        from qbot_status_checks import all_checks
        return all_checks()

    return r
