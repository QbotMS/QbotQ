#!/usr/bin/env python3
"""Garmin Connect auth helpers for Q-bot automations.

Configuration:
- GARMIN_TOKENSTORE: optional tokenstore directory/string, defaults to
  /opt/qbot/app/.garmin_tokens
- GARMIN_EMAIL / GARMIN_PASSWORD: optional fallback credentials when tokens
  cannot be loaded or must be refreshed by garminconnect.

No token or password values are logged by this module.

21.10.2026 - dwie ochrony (awaria importu 21.10 11:19):
1. WLASCICIEL TOKENOW: zadania Garmina dzialaja jako root (cron) i jako qbot (qbot-garmin-watch).
   Gdy root odswiezyl tokeny, plik garmin_tokens.json zostawal root:600 -> qbot nie mogl go
   przeczytac -> logowanie od zera haslem -> Garmin zadal kodu MFA + 429. Teraz przy kazdym
   logowaniu i na koncu procesu (atexit) plik wraca na qbot:qbot (tylko gdy dziala root).
2. BLOKADA PROB: gdy Garmin zada kodu MFA albo odpowie 429 (za duzo prob), zapisujemy
   state/garmin_auth_block.json i wysylamy pozycje do dzwonka (klucz garmin:auth).
   Kolejne garmin_client() NIE lacza sie z Garminem (zeby nie przedluzac blokady), tylko rzucaja
   GarminAuthError. Wstrzymanie znika samo: gdy plik tokenow sie zmieni (ponowne logowanie
   scripts/garmin_login.py albo udane odswiezenie), albo dla 429 po RATE_PAUSE_S.
"""

from __future__ import annotations

import atexit
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from garminconnect import Garmin


APP_DIR = Path("/opt/qbot/app")
DEFAULT_TOKENSTORE = APP_DIR / ".garmin_tokens"
DEFAULT_PROFILE = APP_DIR / ".garmin_profile.json"
BLOCK_FILE = APP_DIR / "state" / "garmin_auth_block.json"
RATE_PAUSE_S = 60 * 60          # 429: przerwa w probach logowania
NOTIF_KEY = "garmin:auth"
OWNER = "qbot"
_ATEXIT_DONE: set[str] = set()


class GarminAuthError(RuntimeError):
    pass


# ---------------------------------------------------------------- wlasciciel plikow tokenow
def _token_file(tokenstore: str) -> Path:
    p = Path(tokenstore)
    return p / "garmin_tokens.json" if p.is_dir() else p


def _fix_owner(*paths: str | Path) -> None:
    """Tylko root: oddaj pliki kontu qbot (qbot-garmin-watch dziala jako qbot)."""
    if os.geteuid() != 0:
        return
    try:
        import pwd
        pw = pwd.getpwnam(OWNER)
    except Exception:
        return
    for raw in paths:
        p = Path(raw)
        targets = [p, *p.glob("*.json")] if p.is_dir() else [p]
        for f in targets:
            try:
                st = f.stat()
                if (st.st_uid, st.st_gid) != (pw.pw_uid, pw.pw_gid):
                    os.chown(f, pw.pw_uid, pw.pw_gid)
            except OSError:
                pass


# ---------------------------------------------------------------- blokada prob
def auth_block() -> dict[str, Any] | None:
    """Aktualne wstrzymanie logowania (albo None). Czyta tez qbot_status_checks."""
    try:
        b = json.loads(BLOCK_FILE.read_text(encoding="utf-8"))
        return b if isinstance(b, dict) else None
    except Exception:
        return None


def _write_block(kind: str, reason: str) -> None:
    data = {"kind": kind, "reason": reason, "ts": time.time(),
            "at": datetime.now().astimezone().isoformat(timespec="seconds")}
    try:
        BLOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = BLOCK_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, BLOCK_FILE)
        _fix_owner(BLOCK_FILE)
    except OSError as e:
        print(f"garmin_auth: nie moge zapisac blokady ({type(e).__name__})")


def _clear_block() -> None:
    try:
        BLOCK_FILE.unlink()
    except FileNotFoundError:
        return
    except OSError as e:
        print(f"garmin_auth: nie moge usunac blokady ({type(e).__name__})")
        return
    _notif(None)


def _active_block(tokenstore: str) -> dict[str, Any] | None:
    b = auth_block()
    if not b:
        return None
    ts = float(b.get("ts") or 0)
    try:
        tok_mtime = _token_file(tokenstore).stat().st_mtime
    except OSError:
        tok_mtime = 0.0
    if tok_mtime > ts:                       # tokeny odswiezone po blokadzie -> probujemy znowu
        _clear_block()
        return None
    if b.get("kind") == "rate" and time.time() - ts > RATE_PAUSE_S:
        os.environ["_QBOT_GARMIN_RETRY"] = "1"   # przerwa minela: jedna proba, blokade zdejmie sukces
        return None
    return b


def _classify(e: Exception) -> str | None:
    s = f"{type(e).__name__} {e}"
    if "MFA" in s or "mfa" in s:
        return "mfa"
    if "429" in s or "TooManyRequests" in s or "Too Many Requests" in s:
        return "rate"
    return None


def _notif(kind: str | None) -> None:
    """Dzwonek: kind=None -> zamknij pozycje. Najlepsza proba - brak bazy nie psuje logowania."""
    try:
        os.environ.setdefault("QBOT3_ENABLED", "1")
        from fitmodel.api import _db_connect
        import qbot_notif
        conn = _db_connect()
        try:
            with conn.cursor() as cur:
                if kind is None:
                    qbot_notif.resolve(cur, NOTIF_KEY)
                elif kind == "mfa":
                    qbot_notif.push(cur, NOTIF_KEY, "system", "Garmin: zaloguj QBota ponownie",
                                    "Garmin zażądał kodu weryfikacyjnego. Import z Garmina jest wstrzymany do "
                                    "ponownego logowania (komenda w wiki: Strażnik importu Garmina).")
                else:
                    qbot_notif.push(cur, NOTIF_KEY, "system", "Garmin: chwilowa blokada logowania",
                                    "Garmin odrzuca logowanie (za dużo prób). Import wstrzymany na 60 min, "
                                    "potem QBot sam spróbuje ponownie.")
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"garmin_auth: dzwonek niedostepny ({type(e).__name__})")


# ---------------------------------------------------------------- klient
def _creds() -> tuple[str, str | None, str | None]:
    load_dotenv(APP_DIR / ".env")
    tokenstore = os.getenv("GARMIN_TOKENSTORE", str(DEFAULT_TOKENSTORE)).strip()
    email = os.getenv("GARMIN_EMAIL", "").strip() or None
    password = os.getenv("GARMIN_PASSWORD", "").strip() or None
    return tokenstore, email, password


def _apply_profile(client: Garmin) -> None:
    if DEFAULT_PROFILE.exists():
        try:
            profile: dict[str, Any] = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
            if profile.get("display_name"):
                client.display_name = profile["display_name"]
        except Exception:
            pass


def garmin_client() -> Garmin:
    tokenstore, email, password = _creds()

    if not tokenstore and not (email and password):
        raise GarminAuthError("Garmin auth missing: set GARMIN_TOKENSTORE or GARMIN_EMAIL/GARMIN_PASSWORD")

    if tokenstore:
        _fix_owner(tokenstore)
        if tokenstore not in _ATEXIT_DONE:   # odswiezenie tokenow w trakcie pracy zapisuje plik ponownie
            atexit.register(_fix_owner, tokenstore)
            _ATEXIT_DONE.add(tokenstore)
        b = _active_block(tokenstore)
        if b:
            raise GarminAuthError(f"Logowanie do Garmina wstrzymane od {b.get('at')} ({b.get('kind')}): "
                                  f"{b.get('reason')}")

    client = Garmin(email, password)
    try:
        if tokenstore:
            client.login(tokenstore=tokenstore)
        else:
            client.login()
    except Exception as e:
        kind = _classify(e)
        if kind:
            was = auth_block()
            _write_block(kind, f"{type(e).__name__}: {str(e)[:200]}")
            if not was or was.get("kind") != kind:
                _notif(kind)
        raise
    finally:
        if tokenstore:
            _fix_owner(tokenstore)

    if BLOCK_FILE.exists():
        _clear_block()
    _apply_profile(client)
    return client


def relogin_interactive() -> None:
    """Ponowne logowanie z kodem MFA (scripts/garmin_login.py). Zapisuje nowe tokeny i zdejmuje blokade."""
    tokenstore, email, password = _creds()
    if not (email and password):
        raise GarminAuthError("Brak GARMIN_EMAIL/GARMIN_PASSWORD w .env")
    client = Garmin(email, password, prompt_mfa=lambda: input("Kod z Garmina (mail/aplikacja): ").strip())
    client.login()
    if tokenstore:
        client.client.dump(tokenstore)
        _fix_owner(tokenstore)
    _clear_block()


def upload_activity(fit_path: Path, *, method: str = "upload") -> dict[str, Any]:
    client = garmin_client()
    method = method.lower().strip()
    if method == "import":
        result = client.import_activity(str(fit_path))
    elif method == "upload":
        result = client.upload_activity(str(fit_path))
    else:
        raise ValueError("Garmin upload method must be 'upload' or 'import'")

    activity_id = extract_activity_id(result)
    activity_url = f"https://connect.garmin.com/modern/activity/{activity_id}" if activity_id else None
    return {
        "status": "success",
        "method": method,
        "raw": result,
        "activityId": activity_id,
        "activityUrl": activity_url,
    }


def extract_activity_id(result: Any) -> str | None:
    if isinstance(result, dict):
        for key in ("activityId", "activity_id", "internalId", "uploadId"):
            value = result.get(key)
            if value:
                return str(value)
        detailed = result.get("detailedImportResult") or result.get("detailedImportResultDto")
        if isinstance(detailed, dict):
            for bucket in ("uploadSuccesses", "successes"):
                values = detailed.get(bucket)
                if isinstance(values, list) and values:
                    found = extract_activity_id(values[0])
                    if found:
                        return found
            for key in ("activityId", "activity_id"):
                value = detailed.get(key)
                if value:
                    return str(value)
        for key in ("activityId", "activity_id"):
            for value in walk_values(result, key):
                if value:
                    return str(value)
    return None


def walk_values(value: Any, wanted_key: str):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == wanted_key:
                yield item
            yield from walk_values(item, wanted_key)
    elif isinstance(value, list):
        for item in value:
            yield from walk_values(item, wanted_key)
