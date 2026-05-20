#!/usr/bin/env python3
"""Hammerhead Dashboard auth/tokenstore for Q-bot.

Dashboard behavior observed from the public frontend bundle:
- localStorage keys: jwt:token and jwt:refresh
- refresh endpoint: POST /v1/auth/token
- refresh payload: grant_type=refresh_token&refresh_token=...
- password payload: grant_type=password&username=...&password=...

Configuration:
- HAMMERHEAD_TOKENSTORE: tokenstore JSON path, defaults to
  /opt/qbot/app/.hammerhead_tokens/hammerhead_tokens.json
- HAMMERHEAD_BEARER_TOKEN: optional bootstrap access token
- HAMMERHEAD_REFRESH_TOKEN: optional bootstrap refresh token
- HAMMERHEAD_EMAIL / HAMMERHEAD_PASSWORD: optional login fallback

No token values are logged by this module.
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


APP_DIR = Path("/opt/qbot/app")
DEFAULT_TOKENSTORE = APP_DIR / ".hammerhead_tokens/hammerhead_tokens.json"
AUTH_URL = "https://dashboard.hammerhead.io/v1/auth/token"
REFRESH_SKEW_SECONDS = 300


class HammerheadAuthError(RuntimeError):
    pass


def _b64url_json(segment: str) -> dict[str, Any]:
    padded = segment + "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))


def jwt_payload(token: str) -> dict[str, Any]:
    try:
        return _b64url_json(token.split(".")[1])
    except Exception as exc:
        raise HammerheadAuthError("Hammerhead auth invalid token format") from exc


def token_exp(token: str | None) -> int | None:
    if not token:
        return None
    exp = jwt_payload(token).get("exp")
    return int(exp) if exp is not None else None


def token_user_id(token: str | None) -> str | None:
    if not token:
        return None
    payload = jwt_payload(token)
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    return str(context.get("userId") or payload.get("sub") or "") or None


def token_is_fresh(token: str | None) -> bool:
    exp = token_exp(token)
    return bool(exp and exp > int(time.time()) + REFRESH_SKEW_SECONDS)


@dataclass
class HammerheadTokens:
    access_token: str
    refresh_token: str | None = None

    @classmethod
    def from_response(cls, payload: dict[str, Any], *, fallback_refresh_token: str | None = None) -> "HammerheadTokens":
        access = payload.get("access_token")
        refresh = payload.get("refresh_token") or fallback_refresh_token
        if not access:
            raise HammerheadAuthError("Hammerhead auth bad token response")
        return cls(access_token=str(access), refresh_token=str(refresh) if refresh else None)

    def public_metadata(self) -> dict[str, Any]:
        return {
            "userId": token_user_id(self.access_token),
            "accessTokenExpiresAt": token_exp(self.access_token),
            "hasRefreshToken": bool(self.refresh_token),
            "accessTokenLength": len(self.access_token),
            "refreshTokenLength": len(self.refresh_token or ""),
            "accessTokenMask": mask_token(self.access_token),
            "refreshTokenMask": mask_token(self.refresh_token),
        }


class HammerheadTokenStore:
    def __init__(self, path: Path | None = None):
        self.path = path or Path(os.getenv("HAMMERHEAD_TOKENSTORE", str(DEFAULT_TOKENSTORE)))

    @classmethod
    def from_env(cls) -> "HammerheadTokenStore":
        load_dotenv(APP_DIR / ".env.hammerhead-garmin-sync")
        load_dotenv(APP_DIR / ".env")
        return cls()

    def load(self) -> HammerheadTokens | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HammerheadAuthError(f"Hammerhead tokenstore invalid JSON: {self.path}") from exc
        access = payload.get("access_token")
        refresh = payload.get("refresh_token")
        if not access:
            return None
        env_refresh = os.getenv("HAMMERHEAD_REFRESH_TOKEN", "").strip()
        env_access = os.getenv("HAMMERHEAD_BEARER_TOKEN", "").strip()
        merged = HammerheadTokens(
            str(access or env_access),
            str(refresh or env_refresh) if (refresh or env_refresh) else None,
        )
        if env_refresh and not refresh:
            self.save(merged)
        return merged

    def save(self, tokens: HammerheadTokens) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "updated_at": int(time.time()),
            "metadata": tokens.public_metadata(),
        }
        old_umask = os.umask(0o077)
        try:
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self.path.chmod(0o600)
        finally:
            os.umask(old_umask)

    def bootstrap_from_env(self) -> HammerheadTokens | None:
        access = os.getenv("HAMMERHEAD_BEARER_TOKEN", "").strip()
        refresh = os.getenv("HAMMERHEAD_REFRESH_TOKEN", "").strip()
        if not access and not refresh:
            return None
        if not access and refresh:
            tokens = refresh_tokens(refresh)
            self.save(tokens)
            return tokens
        tokens = HammerheadTokens(access_token=access, refresh_token=refresh or None)
        self.save(tokens)
        return tokens

    def get_tokens(self) -> HammerheadTokens:
        tokens = self.load() or self.bootstrap_from_env()
        if tokens and token_is_fresh(tokens.access_token):
            return tokens

        if tokens and tokens.refresh_token:
            refreshed = refresh_tokens(tokens.refresh_token)
            self.save(refreshed)
            return refreshed

        login_tokens = login_from_env()
        if login_tokens:
            self.save(login_tokens)
            return login_tokens

        if tokens and tokens.access_token:
            raise HammerheadAuthError(
                "Hammerhead auth expired and no refresh token/login configured"
            )
        raise HammerheadAuthError("Hammerhead auth missing")

    def access_token(self) -> str:
        return self.get_tokens().access_token

    def refresh_after_401(self) -> str:
        tokens = self.load()
        if not tokens or not tokens.refresh_token:
            raise HammerheadAuthError("Hammerhead auth failed and no refresh token configured")
        refreshed = refresh_tokens(tokens.refresh_token)
        self.save(refreshed)
        return refreshed.access_token


def mask_token(token: str | None) -> str | None:
    if not token:
        return None
    if len(token) < 12:
        return f"<len:{len(token)}>"
    return f"{token[:4]}...{token[-4:]}"


def refresh_tokens(refresh_token: str) -> HammerheadTokens:
    response = requests.post(
        AUTH_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if response.status_code in (401, 403):
        raise HammerheadAuthError(f"Hammerhead refresh failed: HTTP {response.status_code}")
    if response.status_code >= 400:
        raise HammerheadAuthError(f"Hammerhead refresh failed: HTTP {response.status_code}")
    return HammerheadTokens.from_response(response.json(), fallback_refresh_token=refresh_token)


def login_from_env() -> HammerheadTokens | None:
    email = os.getenv("HAMMERHEAD_EMAIL", "").strip()
    password = os.getenv("HAMMERHEAD_PASSWORD", "").strip()
    if not email or not password:
        return None
    payload = {
        "grant_type": "password",
        "username": email.lower(),
        "password": password,
    }
    if os.getenv("HAMMERHEAD_TEMP_TOKEN"):
        payload["temp_token"] = os.environ["HAMMERHEAD_TEMP_TOKEN"]
    if os.getenv("HAMMERHEAD_LEGACY"):
        payload["legacy"] = os.environ["HAMMERHEAD_LEGACY"]
    response = requests.post(
        AUTH_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if response.status_code in (401, 403):
        raise HammerheadAuthError(f"Hammerhead login failed: HTTP {response.status_code}")
    if response.status_code >= 400:
        raise HammerheadAuthError(f"Hammerhead login failed: HTTP {response.status_code}")
    return HammerheadTokens.from_response(response.json())


def main() -> int:
    store = HammerheadTokenStore.from_env()
    tokens = store.get_tokens()
    print(json.dumps({"ok": True, "tokenstore": str(store.path), **tokens.public_metadata()}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
