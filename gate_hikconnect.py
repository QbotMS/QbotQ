"""HikConnect gate bridge -- logowanie do chmury HikConnect i otwarcie bramy.

Przebudowa 16.10.2026 ([GATE-PRZEBUDOWA]):
- sesja HikConnect trzymana w pamieci i uzywana ponownie do wygasniecia (wczesniej logowanie przy KAZDYM otwarciu -> wolno + ryzyko CAPTCHA),
- JEDNA proba otwarcia (bez kolejnych prob z haslem w basic auth). Ponowienie tylko raz, gdy zapamietana sesja zostala odrzucona
  (wtedy brama na pewno sie nie otworzyla), po swiezym logowaniu,
- jedno kryterium sukcesu (_unlock_ok), uzywane wszedzie,
- wynik zawiera powod bledu dla dziennika (bez sekretow).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import threading
import time
from base64 import urlsafe_b64decode
from typing import Any

import httpx

_FEATURE_CODE = "deadbeef"
_SESSION: dict[str, Any] = {"session_id": None, "expires_at": 0.0, "base_url": None}
_LOCK = threading.Lock()


def _redact_text(text: str) -> str:
    redacted = text
    for key in ("sessionId", "refreshSessionId", "rfSessionId", "access_token", "accessToken", "token"):
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
    return _redact_text(text)[:400]


class _HikConnectClient(httpx.Client):
    def __init__(self) -> None:
        super().__init__(
            base_url="https://api.hik-connect.com",
            headers={"clientType": "55", "lang": "en-US", "featureCode": _FEATURE_CODE, "Accept": "application/json"},
            timeout=httpx.Timeout(connect=3.0, read=8.0, write=5.0, pool=3.0),
            trust_env=False,
        )

    def set_session(self, session_id: str) -> None:
        self.headers.update({"sessionId": session_id, "Authorization": f"Bearer {session_id}", "X-Access-Token": session_id})


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


def _jwt_exp(jwt: str) -> float:
    try:
        raw = jwt.split(".")[1]
        raw += "=" * (-len(raw) % 4)
        return float(json.loads(urlsafe_b64decode(raw))["exp"])
    except Exception:
        return time.time() + 3600.0   # nieznany termin -> traktuj jak godzine


def _login(client: _HikConnectClient, depth: int = 0) -> None:
    account = os.getenv("HIKCONNECT_ACCOUNT", "")
    password = os.getenv("HIKCONNECT_PASSWORD", "")
    if not account or not password:
        raise RuntimeError("login: brak konta HikConnect w konfiguracji")
    data = {"account": account, "password": hashlib.md5(password.encode("utf-8")).hexdigest()}
    try:
        payload = client.post("/v3/users/login/v2", data=data).json()
    except Exception as exc:
        raise RuntimeError(f"login: brak odpowiedzi ({type(exc).__name__})") from exc
    meta = payload.get("meta") if isinstance(payload, dict) else None
    code = meta.get("code") if isinstance(meta, dict) else None
    if code in (1013, 1014):
        raise RuntimeError("login: zle konto lub haslo HikConnect")
    if code == 1015:
        raise RuntimeError("login: CAPTCHA -- zaloguj sie raz w aplikacji Hik-Connect")
    if code == 1100 and isinstance(payload.get("loginArea"), dict) and depth == 0:
        dom = payload["loginArea"].get("apiDomain")
        if isinstance(dom, str) and dom:
            client.base_url = f"https://{dom}"
            return _login(client, depth + 1)
    try:
        sid = payload["loginSession"]["sessionId"]
    except Exception as exc:
        raise RuntimeError(f"login: nieoczekiwana odpowiedz (meta.code={code})") from exc
    client.set_session(sid)
    _SESSION.update(session_id=sid, expires_at=_jwt_exp(sid) - 3600.0, base_url=str(client.base_url))


def _unlock_ok(payload: Any, response: httpx.Response) -> bool:
    """JEDNO kryterium sukcesu: HTTP < 400 i meta.code == 200 (a gdy jest data.rc -- musi byc 1)."""
    if response.status_code >= 400 or not isinstance(payload, dict):
        return False
    meta = payload.get("meta")
    if not isinstance(meta, dict) or str(meta.get("code")) != "200":
        return False
    data = payload.get("data")
    if isinstance(data, dict) and "rc" in data:
        return data.get("rc") in (1, "1", True)
    return True


def _unlock_once(client: _HikConnectClient, device: str, channel: int, lock_index: int) -> tuple[bool, str]:
    url = f"/v3/devconfig/v1/call/{device}/{channel}/remote/unlock?srcId=1&lockId={lock_index}&userType=0"
    try:
        resp = client.get(url)
    except Exception as exc:
        return False, f"unlock: brak odpowiedzi HikConnect ({type(exc).__name__})"
    try:
        payload = resp.json()
    except Exception:
        payload = None
    if _unlock_ok(payload, resp):
        return True, "ok"
    return False, f"unlock: odmowa http={resp.status_code} body={_redact_payload(payload if payload is not None else resp.text)}"


def unlock() -> dict[str, Any]:
    """Otwiera brame. Zwraca dict ze status ok/error, powodem i czy uzyto zapamietanej sesji. Wywolania szeregowane (_LOCK)."""
    cfg = _gate_direct_config()
    if not cfg["configured"]:
        return {"ok": False, "status": "error", "reason": "konfiguracja bramy niepelna", "mode": "hikconnect_direct"}
    device = cfg["device_serial"]
    channel = int(str(cfg["lock_channel"]))
    lock_index = int(str(cfg["lock_index"]))
    with _LOCK:
        with _HikConnectClient() as client:
            reused = False
            try:
                if _SESSION.get("session_id") and _SESSION.get("expires_at", 0) > time.time() and _SESSION.get("base_url"):
                    client.base_url = _SESSION["base_url"]
                    client.set_session(_SESSION["session_id"])
                    reused = True
                else:
                    _login(client)
                ok, reason = _unlock_once(client, device, channel, lock_index)
                if not ok and reused and reason.startswith("unlock: odmowa"):
                    # zapamietana sesja mogla wygasnac po stronie HikConnect -- brama sie nie otworzyla, wiec jedno ponowienie jest bezpieczne
                    _SESSION.update(session_id=None, expires_at=0.0)
                    _login(client)
                    ok, reason = _unlock_once(client, device, channel, lock_index)
                    reused = False
            except RuntimeError as exc:
                ok, reason = False, str(exc)
            if not ok and reason.startswith("login"):
                _SESSION.update(session_id=None, expires_at=0.0)
    return {
        "ok": ok,
        "success": ok,
        "status": "ok" if ok else "error",
        "reason": reason,
        "sessionReused": reused,
        "mode": "hikconnect_direct",
    }


def session_info() -> dict[str, Any]:
    exp = float(_SESSION.get("expires_at") or 0.0)
    return {"sessionCached": bool(_SESSION.get("session_id")) and exp > time.time(),
            "sessionValidUntilUtc": datetime.datetime.fromtimestamp(exp, datetime.timezone.utc).isoformat() if exp else None}
