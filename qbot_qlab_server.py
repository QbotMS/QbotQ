#!/usr/bin/env python3
"""HTTP API for QLab to fetch QBot FIT exports.

Only files inside the configured exports directory are exposed.
"""
from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
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
GATE_TOKEN_ENV = "GATE_TOKEN"
GATE_RATE_LIMIT_SEC = max(1, int(os.getenv("GATE_RATE_LIMIT_SEC", "60")))
GATE_BRIDGE_URL_ENV_NAMES = ("GATE_BRIDGE_URL", "HIKCONNECT_GATE_URL", "GATE_UPSTREAM_URL")
GATE_ALLOWED_CLIENT_CIDR_ENV_NAMES = ("GATE_ALLOWED_CLIENT_CIDRS", "GATE_ALLOWED_CIDRS")
GATE_DEVICE_SERIAL_ENV = "GATE_DEVICE_SERIAL"
GATE_LOCK_CHANNEL_ENV = "GATE_LOCK_CHANNEL"
GATE_LOCK_INDEX_ENV = "GATE_LOCK_INDEX"

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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
_gate_last_success_monotonic = 0.0
_gate_last_success_at_utc: str | None = None
_gate_unlock_in_progress = False


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


def _gate_bridge_url() -> str | None:
    for name in GATE_BRIDGE_URL_ENV_NAMES:
        value = os.getenv(name)
        if value:
            return value.rstrip("/")
    return None


def _gate_allowed_client_nets() -> list[Any]:
    nets: list[Any] = []
    raw = ""
    for name in GATE_ALLOWED_CLIENT_CIDR_ENV_NAMES:
        raw = os.getenv(name, "")
        if raw:
            break
    if not raw:
        return nets
    for token in raw.replace(",", " ").split():
        try:
            nets.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            continue
    return nets


def _gate_client_allowed(request: Request | None) -> bool:
    if request is None or request.client is None or not request.client.host:
        return True
    client_host = request.client.host
    try:
        client_ip = ipaddress.ip_address(client_host)
    except ValueError:
        return False

    allowed_nets = _gate_allowed_client_nets()
    if allowed_nets:
        return any(client_ip in net for net in allowed_nets)

    return True


def _gate_status_snapshot() -> dict[str, Any]:
    bridge_url = _gate_bridge_url()
    allowed_nets = _gate_allowed_client_nets()
    last_success_age_sec = None
    if _gate_last_success_monotonic > 0.0:
        last_success_age_sec = round(max(0.0, time.monotonic() - _gate_last_success_monotonic), 1)

    return {
        "status": "ok" if bridge_url else "warn",
        "bridgeConfigured": bool(bridge_url),
        "localOnly": bool(allowed_nets),
        "rateLimitSec": GATE_RATE_LIMIT_SEC,
        "lastSuccessAtUtc": _gate_last_success_at_utc,
        "lastSuccessAgeSec": last_success_age_sec,
        "allowedClientCidrs": [str(net) for net in allowed_nets],
        "deviceConfigured": bool(os.getenv(GATE_DEVICE_SERIAL_ENV)),
    }


async def _unlock_gate_via_hikconnect() -> dict[str, Any]:
    bridge_url = _gate_bridge_url()
    if not bridge_url:
        raise RuntimeError("Gate bridge URL is not configured")

    device_serial = os.getenv(GATE_DEVICE_SERIAL_ENV, "").strip()
    lock_channel = os.getenv(GATE_LOCK_CHANNEL_ENV, "").strip()
    lock_index = os.getenv(GATE_LOCK_INDEX_ENV, "").strip()

    if not device_serial:
        raise RuntimeError("GATE_DEVICE_SERIAL is not configured")

    params = {"deviceSerial": device_serial}
    if lock_channel:
        params["lockChannel"] = lock_channel
    if lock_index:
        params["lockIndex"] = lock_index

    timeout = httpx.Timeout(connect=3.0, read=15.0, write=10.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        response = await client.get(
            bridge_url,
            params=params,
            headers={"Accept": "application/json"},
        )

    if response.status_code >= 400:
        raise RuntimeError(f"Gate bridge returned HTTP {response.status_code}")

    try:
        payload = response.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        return payload

    return {
        "status": "ok",
        "bridgeStatusCode": response.status_code,
        "bridgeResponse": response.text[:500],
    }


async def gate_open(
    token: str | None = None,
    x_gate_token: str | None = Header(default=None, alias="X-Gate-Token"),
    request: Request | None = None,
) -> Response:
    started_at = time.monotonic()
    source = request.client.host if request and request.client and request.client.host else "unknown"
    provided_token = x_gate_token or token

    if not _gate_client_allowed(request):
        logger.info("gate_open src=%s status=403 reason=client_not_allowed", source)
        return JSONResponse(
            {"status": "forbidden", "detail": "gate open is local/vpn only"},
            status_code=403,
        )

    expected = os.getenv(GATE_TOKEN_ENV)
    if not expected:
        logger.info("gate_open src=%s status=503 reason=token_missing", source)
        return JSONResponse(
            {"status": "error", "detail": "GATE_TOKEN is not configured"},
            status_code=503,
        )
    if provided_token != expected:
        logger.info("gate_open src=%s status=403 reason=token_invalid", source)
        return JSONResponse(
            {"status": "forbidden", "detail": "invalid token"},
            status_code=403,
        )

    global _gate_last_success_monotonic, _gate_last_success_at_utc, _gate_unlock_in_progress

    now = time.monotonic()
    if _gate_last_success_monotonic and now - _gate_last_success_monotonic < GATE_RATE_LIMIT_SEC:
        retry_after = max(1, int(GATE_RATE_LIMIT_SEC - (now - _gate_last_success_monotonic)))
        logger.info("gate_open src=%s status=429 reason=rate_limited retry_after=%s", source, retry_after)
        return JSONResponse(
            {"status": "rate_limited", "retryAfterSec": retry_after},
            status_code=429,
        )

    if _gate_unlock_in_progress:
        logger.info("gate_open src=%s status=429 reason=busy", source)
        return JSONResponse(
            {"status": "busy", "detail": "gate unlock already in progress"},
            status_code=429,
        )

    _gate_unlock_in_progress = True
    try:
        result = await _unlock_gate_via_hikconnect()
    except Exception as exc:
        logger.warning("gate_open_failed src=%s error=%s", source, type(exc).__name__)
        return JSONResponse(
            {"status": "error", "detail": "gate bridge failed"},
            status_code=503,
        )
    finally:
        _gate_unlock_in_progress = False

    if isinstance(result, Response):
        if result.status_code < 400:
            _gate_last_success_monotonic = time.monotonic()
            _gate_last_success_at_utc = datetime.now(timezone.utc).isoformat()
            logger.info(
                "gate_open src=%s status=%s duration_ms=%s",
                source,
                result.status_code,
                int((time.monotonic() - started_at) * 1000),
            )
        return result

    if isinstance(result, dict):
        status = str(result.get("status", "ok")).lower()
        if status in {"ok", "success", "opened", "done"}:
            _gate_last_success_monotonic = time.monotonic()
            _gate_last_success_at_utc = datetime.now(timezone.utc).isoformat()
            logger.info(
                "gate_open src=%s status=200 duration_ms=%s bridge=%s",
                source,
                int((time.monotonic() - started_at) * 1000),
                "configured" if _gate_bridge_url() else "missing",
            )
            return JSONResponse(result, status_code=200)
        logger.info(
            "gate_open src=%s status=502 duration_ms=%s bridge=%s",
            source,
            int((time.monotonic() - started_at) * 1000),
            "configured" if _gate_bridge_url() else "missing",
        )
        return JSONResponse(result, status_code=502)

    _gate_last_success_monotonic = time.monotonic()
    _gate_last_success_at_utc = datetime.now(timezone.utc).isoformat()
    logger.info(
        "gate_open src=%s status=200 duration_ms=%s bridge=%s",
        source,
        int((time.monotonic() - started_at) * 1000),
        "configured" if _gate_bridge_url() else "missing",
    )
    return JSONResponse({"status": "ok"}, status_code=200)


@app.get("/gate/open")
async def gate_open_route(
    request: Request,
    token: str | None = None,
    x_gate_token: str | None = Header(default=None, alias="X-Gate-Token"),
) -> Response:
    return await gate_open(token=token, x_gate_token=x_gate_token, request=request)


@app.get("/gate/status")
def gate_status() -> dict[str, Any]:
    return _gate_status_snapshot()


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
    payload = {"ok": True, "service": "qbot-qlab-server", "exports": str(EXPORTS_DIR)}
    payload["gate"] = _gate_status_snapshot()
    return payload


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
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)


if __name__ == "__main__":
    main()
