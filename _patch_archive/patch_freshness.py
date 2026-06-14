#!/usr/bin/env python3
"""patch_freshness.py — Etap 1: freshness invariant dla tras RWGPS.

Tworzy:
  /opt/qbot/app/core/invariants.py

Patchuje:
  /opt/qbot/app/tools/rwgps/client.py
    - dodaje rwgps_updated_at do metadata
    - wersjonuje idempotency_key (route_id:fmt:updated_at_date)
    - po rejestracji: superseduje stare rekordy

Po patchu: systemctl restart qbot-api
"""

import ast
import os
import shutil
from datetime import datetime

BASE = "/opt/qbot/app"

INVARIANTS_PY = '''\
"""core/invariants.py — Niezmienniki QBot (freshness, sanity).

Etap 1 PRZEBUDOWA.md: freshness invariant dla artefaktow tras.

Funkcje:
  supersede_stale_route_artifacts(route_id, fmt, keep_idempotency_key)
    -> oznacza stare rekordy artifacts dla tego route_id+fmt jako 'superseded',
       z wyjatkiem rekordu o podanym kluczu (nowo zarejestrowanym).

  check_route_stale(route_id, fmt, rwgps_updated_at) -> bool
    -> True jesli artefakt w DB ma starsza wersje niz rwgps_updated_at.
"""

from __future__ import annotations

import logging
import os
from typing import Any

_log = logging.getLogger("qbot.invariants")


def _db_conn():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "5")),
    )


def supersede_stale_route_artifacts(
    route_id: str | int,
    fmt: str,
    keep_idempotency_key: str,
) -> int:
    """Oznacza stare rekordy artifacts dla route_id+fmt jako superseded.

    Pomija rekord z keep_idempotency_key (nowo zarejestrowany).
    Zwraca liczbe zmienionych rekordow.
    """
    route_id_str = str(route_id)
    prefix = f"rwgps_export:{route_id_str}:{fmt}:"

    try:
        with _db_conn() as conn:
            rows = conn.execute(
                """
                UPDATE qbot_v2.artifacts
                SET status = \'superseded\'::qbot_v2.artifact_status,
                    updated_at = now()
                WHERE idempotency_key LIKE %s
                  AND idempotency_key != %s
                  AND status = \'active\'::qbot_v2.artifact_status
                RETURNING artifact_id, idempotency_key
                """,
                (prefix + "%", keep_idempotency_key),
            ).fetchall()
            conn.commit()

        n = len(rows)
        if n:
            _log.info(
                "freshness: superseded %d old artifact(s) for route %s fmt=%s",
                n, route_id_str, fmt,
            )
        return n

    except Exception as exc:
        _log.warning("freshness: supersede failed for route %s: %s", route_id_str, exc)
        return 0


def check_route_stale(route_id: str | int, fmt: str, rwgps_updated_at: str | None) -> bool:
    """Sprawdza czy aktywny artefakt jest starszy niz rwgps_updated_at.

    Zwraca True (stale) jesli artefakt w DB pochodzi sprzed rwgps_updated_at.
    Zwraca False jesli brak danych lub artefakt aktualny.
    """
    if not rwgps_updated_at:
        return False

    route_id_str = str(route_id)
    prefix = f"rwgps_export:{route_id_str}:{fmt}:"

    try:
        with _db_conn() as conn:
            row = conn.execute(
                """
                SELECT metadata_json, created_at
                FROM qbot_v2.artifacts
                WHERE idempotency_key LIKE %s
                  AND status = \'active\'::qbot_v2.artifact_status
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (prefix + "%",),
            ).fetchone()

        if not row:
            return False

        meta = row.get("metadata_json") or {}
        stored_rwgps_ts = meta.get("rwgps_updated_at")

        if stored_rwgps_ts:
            is_stale = stored_rwgps_ts < rwgps_updated_at
            if is_stale:
                _log.info(
                    "freshness: route %s stale (stored=%s api=%s)",
                    route_id_str, stored_rwgps_ts, rwgps_updated_at,
                )
            return is_stale

        return True  # brak stored_rwgps_ts w starym rekordzie -> potraktuj jako stale

    except Exception as exc:
        _log.warning("freshness: check_route_stale failed for %s: %s", route_id_str, exc)
        return False
'''

# ── Patch client.py: stary blok metadata + rejestracja ──────────────────────
CLIENT_TARGET = f"{BASE}/tools/rwgps/client.py"

OLD_IDEM = '        idem_key = f"rwgps_export:{route_id_str}:{fmt}"'
NEW_IDEM = '''\
        # Wersjonowany klucz idempotencji — zawiera date updated_at z RWGPS.
        # Zmiana trasy na RWGPS = nowy klucz = nowy rekord; stary -> superseded.
        _rwgps_upd = route_view.get("updated_at") or ""
        _idem_date = (
            _rwgps_upd[:10].replace("-", "")  # "20260610"
            if len(_rwgps_upd) >= 10
            else "unknown"
        )
        idem_key = f"rwgps_export:{route_id_str}:{fmt}:{_idem_date}"'''

OLD_META = '''                "route_source": source,
            },
        )
        if artifact_record and artifact_record.get("artifact_id"):
            payload["artifact_store_id"] = str(artifact_record["artifact_id"])
            payload["artifact_store_status"] = "registered"
        else:
            payload["artifact_store_warning"] = "Artifact Store returned empty record"
            payload["artifact_store_status"] = "skipped"'''

NEW_META = '''                "route_source": source,
                "rwgps_updated_at": route_view.get("updated_at") or "",
            },
        )
        if artifact_record and artifact_record.get("artifact_id"):
            payload["artifact_store_id"] = str(artifact_record["artifact_id"])
            payload["artifact_store_status"] = "registered"
            # Freshness invariant: superseduj stare rekordy tej trasy
            try:
                from core.invariants import supersede_stale_route_artifacts as _supersede
                _n_sup = _supersede(route_id_str, fmt, idem_key)
                if _n_sup:
                    payload["freshness_superseded"] = _n_sup
            except Exception as _inv_exc:
                payload["freshness_warning"] = f"supersede failed: {_inv_exc}"
        else:
            payload["artifact_store_warning"] = "Artifact Store returned empty record"
            payload["artifact_store_status"] = "skipped"'''


def write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    ast.parse(content)
    print(f"  OK (AST): {path}")


def patch_file(path: str, old: str, new: str, label: str) -> None:
    src = open(path, encoding="utf-8").read()
    if old not in src:
        raise SystemExit(f"BLAD: anchor '{label}' nie znaleziony w {path}")
    patched = src.replace(old, new, 1)
    ast.parse(patched)
    bak = path + ".bak." + datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, bak)
    open(path, "w", encoding="utf-8").write(patched)
    print(f"  OK patch: {path}")


def main() -> None:
    print("=== Etap 1: freshness invariant ===")

    # 1. core/invariants.py
    write_file(f"{BASE}/core/invariants.py", INVARIANTS_PY)

    # 2. Patch client.py — idem_key wersjonowany
    patch_file(CLIENT_TARGET, OLD_IDEM, NEW_IDEM, "idem_key")

    # 3. Patch client.py — metadata + supersede
    patch_file(CLIENT_TARGET, OLD_META, NEW_META, "meta_supersede")

    print("\nOK: Etap 1 zastosowany.")
    print("Nastepny krok: systemctl restart qbot-api")


if __name__ == "__main__":
    main()
