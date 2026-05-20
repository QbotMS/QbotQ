#!/usr/bin/env python3
"""HTTP API for QLab to fetch QBot FIT exports.

Only files inside the configured exports directory are exposed.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv("/opt/qbot/app/.env")

DEFAULT_EXPORTS_DIR = Path("/opt/qbot/app/qlab_exports")
FIT_EXPORT_MODULE = Path("/opt/qbot/app/tools/fit-export/fit_export.py")
ALLOWED_CORS_ORIGINS = {
    "http://localhost:8080",
    "http://127.0.0.1:8080",
}
CORS_METHODS = "GET, POST, OPTIONS"
CORS_HEADERS = "X-QLab-Token, Content-Type, ngrok-skip-browser-warning"
CORS_MAX_AGE = "86400"

app = FastAPI(title="QBot QLab Export API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_CORS_ORIGINS),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-QLab-Token", "Content-Type", "ngrok-skip-browser-warning"],
    allow_credentials=False,
    max_age=int(CORS_MAX_AGE),
)
EXPORTS_DIR = DEFAULT_EXPORTS_DIR


def _apply_cors_headers(response: Response, origin: str | None) -> None:
    if origin in ALLOWED_CORS_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = CORS_METHODS
    response.headers["Access-Control-Allow-Headers"] = CORS_HEADERS
    response.headers["Access-Control-Max-Age"] = CORS_MAX_AGE


@app.middleware("http")
async def force_cors_headers(request, call_next):
    origin = request.headers.get("origin")
    if request.method == "OPTIONS":
        response = Response(status_code=200)
        _apply_cors_headers(response, origin)
        return response
    response = await call_next(request)
    _apply_cors_headers(response, origin)
    return response


def _load_fit_export_module() -> Any:
    spec = importlib.util.spec_from_file_location("qbot_fit_export", FIT_EXPORT_MODULE)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load FIT exporter from {FIT_EXPORT_MODULE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fit_export = _load_fit_export_module()


class ExportFitRequest(BaseModel):
    fitPath: str


def _require_token(x_qlab_token: str | None = Header(default=None)) -> None:
    expected = os.getenv("QLAB_EXPORT_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="QLAB_EXPORT_TOKEN is not configured")
    if x_qlab_token != expected:
        raise HTTPException(status_code=401, detail="Invalid QLab token")


def _safe_export_path(filename: str) -> Path:
    if "/" in filename or "\\" in filename or filename in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = (EXPORTS_DIR / filename).resolve()
    root = EXPORTS_DIR.resolve()
    if root != path and root not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return path


def _start_time_from_log(payload: dict[str, Any]) -> str | None:
    for tick in payload.get("ticks") or []:
        timestamp = (tick.get("rideState") or {}).get("timestamp")
        if timestamp:
            return timestamp
    return None


def _summary_for_log(log_path: Path) -> dict[str, Any]:
    summary_path = log_path.with_name(log_path.name.replace(".qbot_replay_log.json", ".qbot_replay_summary.json"))
    if summary_path.is_file():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["sizeBytes"] = log_path.stat().st_size
            return summary
        except Exception:
            pass

    payload = json.loads(log_path.read_text(encoding="utf-8"))
    stat = log_path.stat()
    activity_id = log_path.name.split(".qbot_replay_log.json", 1)[0]
    return {
        "filename": log_path.name,
        "activityId": activity_id,
        "createdAt": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "sizeBytes": stat.st_size,
        "ticks": payload.get("tickCount") or len(payload.get("ticks") or []),
        "startTime": _start_time_from_log(payload),
    }


def _write_export(fit_path: Path) -> dict[str, Any]:
    if not fit_path.is_file():
        raise HTTPException(status_code=404, detail="FIT file not found")
    if fit_path.suffix.lower() != ".fit":
        raise HTTPException(status_code=400, detail="fitPath must point to a .fit file")

    payload = fit_export.export_fit(fit_path)
    activity_id = fit_export.activity_id_from_fit_path(fit_path)
    log_path = EXPORTS_DIR / f"{activity_id}.qbot_replay_log.json"
    summary_path = EXPORTS_DIR / f"{activity_id}.qbot_replay_summary.json"

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = fit_export.build_summary(payload, log_path, fit_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "filename": log_path.name,
        "summaryFilename": summary_path.name,
        "activityId": activity_id,
        "ticks": payload.get("tickCount"),
        "durationMs": payload.get("durationMs"),
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "qbot-qlab-server", "exports": str(EXPORTS_DIR)}


@app.get("/files", dependencies=[Depends(_require_token)])
def list_files() -> list[dict[str, Any]]:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(EXPORTS_DIR.glob("*.qbot_replay_log.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [_summary_for_log(path) for path in files]


@app.get("/files/{filename}", dependencies=[Depends(_require_token)])
def get_file(filename: str) -> FileResponse:
    path = _safe_export_path(filename)
    return FileResponse(path, media_type="application/json", filename=path.name)


@app.post("/export-fit", dependencies=[Depends(_require_token)])
def export_fit_endpoint(request: ExportFitRequest) -> dict[str, Any]:
    return _write_export(Path(request.fitPath).expanduser().resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve QBot QLab exports over HTTP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8899)
    parser.add_argument("--exports", default=str(DEFAULT_EXPORTS_DIR))
    args = parser.parse_args()

    global EXPORTS_DIR
    EXPORTS_DIR = Path(args.exports).expanduser().resolve()
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
