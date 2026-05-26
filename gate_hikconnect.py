"""HikConnect gate bridge — login with HikConnect cloud and unlock the gate."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from base64 import urlsafe_b64decode
from contextlib import contextmanager
from typing import Any

import httpx

_CACHE_TTL_SEC = 300
_FEATURE_CODE = "deadbeef"
_token_cache: dict[str, int | str | None] = {"session_id": None, "expires_at": 0}


def _log_raw(line: str) -> None:
    try:
        with open("/tmp/qbot_gate_hikconnect.log", "a", encoding="utf-8") as fh:
            fh.write(f"{line}\n")
    except Exception:
        pass


def _redact_text(text: str) -> str:
    redacted = text
    for key in ("sessionId", "refreshSessionId", "access_token", "accessToken", "token"):
        redacted = redacted.replace(f'"{key}":"', f'"{key}":"<redacted>')
    return redacted


def _redact_payload(payload: Any) -> str:
    try:
        if isinstance(payload, (dict, list)):
            text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        else:
            text = str(payload)
    except Exception:
        text = "<unprintable>"
    return _redact_text(text)


class _HikConnectClient(httpx.Client):
    def __init__(self) -> None:
        headers = {
            "clientType": "55",
            "lang": "en-US",
            "featureCode": _FEATURE_CODE,
        }
        super().__init__(
            base_url="https://api.hik-connect.com",
            headers=headers,
            timeout=httpx.Timeout(connect=3.0, read=15.0, write=10.0, pool=5.0),
            trust_env=False,
        )

    def set_session_id(self, session_id: str) -> None:
        self.headers.update({"sessionId": session_id})

    @contextmanager
    def without_session_id(self):
        if "sessionId" not in self.headers:
            yield self
            return
        session_id = self.headers.pop("sessionId")
        try:
            yield self
        finally:
            self.headers["sessionId"] = session_id


def _gate_direct_config() -> dict[str, Any]:
    account = os.getenv("HIKCONNECT_ACCOUNT", "").strip()
    password = os.getenv("HIKCONNECT_PASSWORD", "").strip()
    device_serial = os.getenv("GATE_DEVICE_SERIAL", "").strip()
    lock_channel = os.getenv("GATE_LOCK_CHANNEL", "").strip()
    lock_index = os.getenv("GATE_LOCK_INDEX", "").strip()
    token = os.getenv("GATE_TOKEN", "").strip()
    return {
        "account_configured": bool(account),
        "password_configured": bool(password),
        "credentials_configured": bool(account and password),
        "device_serial": device_serial,
        "device_serial_configured": bool(device_serial),
        "lock_channel": lock_channel,
        "lock_channel_configured": bool(lock_channel),
        "lock_index": lock_index,
        "lock_index_configured": bool(lock_index),
        "token_configured": bool(token),
        "configured": bool(account and password and device_serial and lock_channel and lock_index and token),
    }


def _decode_jwt_expiration(jwt: str) -> datetime.datetime:
    parts = jwt.split(".")
    claims_raw = parts[1]
    missing_padding = len(claims_raw) % 4
    if missing_padding:
        claims_raw += "=" * (4 - missing_padding)
    claims_json_raw = urlsafe_b64decode(claims_raw)
    claims = json.loads(claims_json_raw)
    return datetime.datetime.fromtimestamp(claims["exp"])


def _handle_login_response(client: _HikConnectClient, session_id: str, refresh_session_id: str) -> datetime.datetime:
    client.set_session_id(session_id)
    _token_cache["session_id"] = session_id
    login_valid_until = _decode_jwt_expiration(session_id)
    _token_cache["expires_at"] = int(login_valid_until.timestamp()) - 3600
    _token_cache["refresh_session_id"] = refresh_session_id
    return login_valid_until


def _auth(client: _HikConnectClient) -> tuple[str, datetime.datetime]:
    account = os.getenv("HIKCONNECT_ACCOUNT", "")
    password = os.getenv("HIKCONNECT_PASSWORD", "")
    if not account or not password:
        raise RuntimeError("HIKCONNECT_ACCOUNT / HIKCONNECT_PASSWORD not configured")

    data = {
        "account": account,
        "password": hashlib.md5(password.encode("utf-8")).hexdigest(),
    }

    login_urls = [
        f"{client.base_url}/v3/users/login/v2",
    ]

    last_error: Exception | None = None
    for url in login_urls:
        try:
            response = client.post(url, data=data)
            payload = response.json()
        except Exception as exc:
            last_error = exc
            continue

        meta = payload.get("meta") if isinstance(payload, dict) else None
        if isinstance(meta, dict):
            code = meta.get("code")
            if code in (1013, 1014):
                raise RuntimeError("Login failed, probably wrong username/password combination.")
            if code == 1015:
                raise RuntimeError("CAPTCHA hit, please login using Hik-Connect app and then retry.")
            if code == 1100 and isinstance(payload.get("loginArea"), dict):
                new_api_domain = payload["loginArea"].get("apiDomain")
                if isinstance(new_api_domain, str) and new_api_domain:
                    client.base_url = f"https://{new_api_domain}"
                    return _auth(client)

        try:
            session_id = payload["loginSession"]["sessionId"]
            refresh_session_id = payload["loginSession"]["rfSessionId"]
        except Exception as exc:
            raise RuntimeError("Unable to parse login session data.") from exc

        valid_until = _handle_login_response(client, session_id, refresh_session_id)
        return session_id, valid_until

    if last_error is not None:
        raise RuntimeError(f"HikConnect login failed: {type(last_error).__name__}") from last_error
    raise RuntimeError("HikConnect login failed")


def _response_success(payload: Any, response: httpx.Response) -> bool:
    if response.status_code >= 400:
        return False
    if isinstance(payload, dict):
        meta = payload.get("meta")
        if isinstance(meta, dict) and meta.get("code") == 200:
            data = payload.get("data")
            if isinstance(data, dict):
                if data.get("rc") in (1, "1", True):
                    return True
            if payload.get("status") in {"ok", "success", "opened", "done"}:
                return True
            if "操作成功" in str(meta.get("message", "")):
                return True
    text = response.text
    return "\"rc\":1" in text or "\"rc\": 1" in text or "操作成功" in text or "\"status\":\"ok\"" in text


def unlock() -> dict[str, Any]:
    direct = _gate_direct_config()
    if not direct["configured"]:
        raise RuntimeError("Direct HikConnect gate config is incomplete")

    device = direct["device_serial"]
    lock_channel = int(str(direct["lock_channel"]))
    lock_index = int(str(direct["lock_index"]))
    account = os.getenv("HIKCONNECT_ACCOUNT", "")
    password = os.getenv("HIKCONNECT_PASSWORD", "")

    with _HikConnectClient() as client:
        client.base_url = "https://api.hik-connect.com"
        client.headers.update({"Accept": "application/json"})

        session_id, _valid_until = _auth(client)
        client.headers.update({"Authorization": f"Bearer {session_id}", "X-Access-Token": session_id})

        unlock_url = (
            f"{client.base_url}/v3/devconfig/v1/call/{device}/{lock_channel}/remote/unlock"
            f"?srcId=1&lockId={lock_index}&userType=0"
        )
        unlock_attempts = [
            ("GET", None),
            ("GET", (account, password)),
            ("POST", (account, password)),
        ]

        last_response: httpx.Response | None = None
        last_payload: Any = None
        traces: list[str] = []
        for method, request_auth in unlock_attempts:
            try:
                if method == "GET":
                    response = client.get(unlock_url, auth=request_auth)
                else:
                    response = client.put(unlock_url, auth=request_auth)
            except Exception as exc:
                traces.append(f"{method} error={type(exc).__name__}")
                continue

            last_response = response
            try:
                last_payload = response.json()
            except Exception:
                last_payload = None
            traces.append(f"{method} http={response.status_code} body={_redact_payload(last_payload if last_payload is not None else response.text)}")
            _log_raw(
                "UNLOCK_RAW "
                f"http={response.status_code} url={unlock_url} body={_redact_payload(last_payload if last_payload is not None else response.text)}"
            )
            if _response_success(last_payload, response):
                return {
                    "ok": True,
                    "success": True,
                    "status": "ok",
                    "mode": "hikconnect_direct",
                    "deviceSerial": device,
                    "lockChannel": str(lock_channel),
                    "lockIndex": str(lock_index),
                    "rateLimitSec": int(os.getenv("GATE_RATE_LIMIT_SEC", "15")),
                }

        if last_response is not None:
            raise RuntimeError(
                f"HikConnect unlock failed http={last_response.status_code} "
                f"body={_redact_payload(last_payload if last_payload is not None else last_response.text)}; "
                f"trace={' | '.join(traces)}"
            )
        raise RuntimeError("HikConnect unlock request could not be sent")
