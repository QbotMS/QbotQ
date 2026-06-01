#!/usr/bin/env python3
"""QBot3 Response State Normalizer — single source of truth for response consistency.

Every qbot.query response goes through normalize_response() before being returned.
Ensures top-level status, missing_fields, human_answer, and limitations are
consistent with the action_draft state, contract review, and input kind.
"""

from __future__ import annotations

from typing import Any

from qbot3.errors import (
    OK, CAPABILITY_MISSING, CONFIG_MISMATCH,
    ERROR, PLAN_INVALID, error_result,
)


def normalize_response(response: dict[str, Any]) -> dict[str, Any]:
    """Normalize a qbot.query response for consistency."""
    r = dict(response)
    ad = r.get("action_draft")
    status = r.get("status", "")
    limitations = list(r.get("limitations", []))

    # ── 1. Draft incomplete — action_draft exists but not ready ───────
    if ad and isinstance(ad, dict):
        ready = ad.get("ready_for_execute", False)
        mf = ad.get("missing_fields", [])
        contract = ad.get("contract_review", "")
        pending = ad.get("pending_task", False)
        cq = ad.get("clarification_question", "")

        if not ready or contract == "needs_clarification" or pending or mf:
            # Override: incomplete draft
            r["status"] = "draft_incomplete"
            r["pending_task"] = True
            if "write_draft" in limitations:
                limitations.remove("write_draft")
            if "write_draft_incomplete" not in limitations:
                limitations.append("write_draft_incomplete")
            # Sync missing_fields from action_draft to top level
            r["missing_fields"] = list(dict.fromkeys(mf + r.get("missing_fields", [])))
            # Build human_answer
            if cq:
                r["human_answer"] = cq
                r["answer"] = cq
            elif mf:
                from qbot3.write_router import _build_clarification
                at = ad.get("action_type", "")
                cq = _build_clarification(at, mf, r.get("query", ""))
                r["human_answer"] = cq
                r["answer"] = cq
            else:
                r["human_answer"] = "Potrzebuję więcej informacji, aby przygotować draft."
            # Remove action_draft fields that contradict state
            ad.pop("pending_task", None)
        else:
            # Draft is ready
            r["status"] = "draft"
            r["pending_task"] = False
            r["missing_fields"] = []
            if "write_draft" not in limitations:
                limitations.append("write_draft")
            if "write_draft_incomplete" in limitations:
                limitations.remove("write_draft_incomplete")
            hs = ad.get("human_summary", "")
            r["human_answer"] = f"Przygotowałem draft: {hs}. Zapis wymaga potwierdzenia przez qbot.action_execute."
            if not r.get("answer"):
                r["answer"] = r["human_answer"]
        r["limitations"] = list(dict.fromkeys(limitations))
        return r

    # ── 2. Conversational — ensure natural answer ─────────────────────
    if status in ("ok", "OK") and "conversational" in str(limitations):
        r["status"] = OK.lower()
        if not r.get("human_answer"):
            r["human_answer"] = r.get("answer", "")
        r["missing_fields"] = []
        r["limitations"] = [l for l in limitations if l not in ("pre_routed",)]
        return r

    # ── 3. Read-only pre-routed (capabilities) ────────────────────────
    if status in ("ok", "OK") and "pre_routed" in limitations:
        r["status"] = OK.lower()
        r["human_answer"] = r.get("human_answer") or r.get("answer", "")
        r["missing_fields"] = []
        return r

    # ── 4. BLOCKED / destructive ──────────────────────────────────────
    if status in ("BLOCKED", "blocked") or "destructive" in str(limitations):
        r["status"] = "blocked"
        r["human_answer"] = r.get("human_answer") or "Nie mogę tego wykonać. Operacja jest zablokowana."
        r["missing_fields"] = []
        if "destructive_blocked" not in limitations:
            limitations.append("destructive_blocked")
        r["limitations"] = list(dict.fromkeys(limitations))
        return r

    # ── 5. CAPABILITY_MISSING ─────────────────────────────────────────
    if status in ("CAPABILITY_MISSING", "capability_missing"):
        r["status"] = "capability_missing"
        intent = r.get("plan", {}).get("intent", "")
        if not r.get("human_answer"):
            r["human_answer"] = (
                f"Nie mam capability dla '{intent}'. "
                f"Mogę przygotować proposal — zobacz workspace/proposals/."
            )
        r["missing_fields"] = []
        if "capability_missing" not in limitations:
            limitations.append("capability_missing")
        r["limitations"] = list(dict.fromkeys(limitations))
        return r

    # ── 6. CAPABILITY_MISMATCH ────────────────────────────────────────
    if status in ("CAPABILITY_MISMATCH",):
        r["status"] = "capability_mismatch"
        if not r.get("human_answer"):
            r["human_answer"] = r.get("answer", "Wybrano narzędzie nieodpowiednie dla tej domeny.")
        return r

    # ── 7. CONFIG_MISMATCH ─────────────────────────────────────────────
    if status in ("CONFIG_MISMATCH", "CONFIG_MISMATCH"):
        r["status"] = "config_mismatch"
        if not r.get("human_answer"):
            r["human_answer"] = r.get("answer", "Konfiguracja runtime LLM jest niespójna.")
        return r

    # ── 8. ERROR / PLAN_INVALID ───────────────────────────────────────
    if status in ("ERROR", "PLAN_INVALID", "WRITE_INCONSISTENT", "error"):
        r["status"] = "error"
        if not r.get("human_answer"):
            r["human_answer"] = "Nie mogę przetworzyć zapytania. Sprawdź logi."
        return r

    # ── 9. Default: ok ────────────────────────────────────────────────
    if not status or status == "?":
        r["status"] = OK.lower()
        r["missing_fields"] = []
    r.setdefault("missing_fields", [])
    r.setdefault("human_answer", r.get("answer", ""))
    r["limitations"] = list(dict.fromkeys(limitations))
    # Strip internal/metadata fields — client needs only answer + status + metadata
    KEEP = {"status", "answer", "human_answer", "confidence", "missing_fields",
            "limitations", "request_id", "action_draft", "tool"}
    for _key in list(r.keys()):
        if _key not in KEEP:
            del r[_key]
    return r
