from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from tools.rwgps.client import list_routes

_PAGE_SIZE = 200


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", str(text))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"[^a-zA-Z0-9]+", " ", ascii_text).lower()
    return " ".join(ascii_text.split())


def _tokenize(text: str) -> list[str]:
    return [token for token in _normalize_text(text).split() if token]


def _route_tokens(route: dict[str, Any]) -> list[str]:
    parts = [
        route.get("name"),
        route.get("description"),
        route.get("locality"),
        route.get("region"),
        route.get("country"),
        route.get("status"),
    ]
    tokens: list[str] = []
    for part in parts:
        tokens.extend(_tokenize(str(part or "")))
    return tokens


def _updated_at_key(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).timestamp()
    except Exception:
        return 0.0


def _match_score(query_tokens: list[str], route_tokens: list[str], route_name: str) -> tuple[int, list[str]]:
    if not query_tokens:
        return (0, [])

    matches: set[str] = set()
    route_token_set = set(route_tokens)
    route_name_norm = _normalize_text(route_name)
    score = 0

    for qtok in query_tokens:
        if not qtok:
            continue
        qroot = qtok[:-1] if len(qtok) > 4 and qtok[-1] in "aeiouy" else qtok
        best = 0
        best_match = ""
        for rtok in route_token_set:
            rroot = rtok[:-1] if len(rtok) > 4 and rtok[-1] in "aeiouy" else rtok
            if qtok == rtok:
                best = 4
                best_match = rtok
                break
            if qtok == rroot or qroot == rtok:
                best = max(best, 3)
                best_match = rtok
                continue
            if qtok.startswith(rtok) or rtok.startswith(qtok) or qroot.startswith(rtok) or rtok.startswith(qroot):
                best = max(best, 2)
                best_match = rtok
                continue
            if qtok in rtok or rtok in qtok or qtok in route_name_norm:
                best = max(best, 1)
                best_match = rtok
        if best:
            score += best
            if best_match:
                matches.add(best_match)

    return score, sorted(matches)


def _route_summary(route: dict[str, Any], *, score: int, matched_tokens: list[str]) -> dict[str, Any]:
    return {
        "route_id": route.get("id"),
        "name": route.get("name"),
        "distance_km": route.get("distance_km"),
        "elevation_m": route.get("elevation_m"),
        "updated_at": route.get("updated_at"),
        "score": score,
        "matched_tokens": matched_tokens,
    }


def _fetch_all_routes() -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    offset = 0
    while True:
        result = list_routes(limit=_PAGE_SIZE, offset=offset, sort="updated_at", order="desc")
        if not isinstance(result, dict) or not result.get("ok"):
            break
        batch = result.get("routes") or []
        if not isinstance(batch, list) or not batch:
            break
        for item in batch:
            if isinstance(item, dict):
                routes.append(item)
        total = result.get("total")
        if isinstance(total, int) and offset + len(batch) >= total:
            break
        if len(batch) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return routes


def find_routes(name_hint: str, limit: int = 5) -> list[dict[str, Any]]:
    hint = str(name_hint or "").strip()
    routes = _fetch_all_routes()
    if not routes:
        return []

    query_tokens = _tokenize(hint)
    ranked: list[dict[str, Any]] = []
    for route in routes:
        route_name = str(route.get("name") or "")
        score, matched_tokens = _match_score(query_tokens, _route_tokens(route), route_name)
        ranked.append(
            {
                **_route_summary(route, score=score, matched_tokens=matched_tokens),
                "_updated_at_key": _updated_at_key(route.get("updated_at")),
            }
        )

    ranked.sort(
        key=lambda item: (
            -int(item.get("score", 0) or 0),
            -float(item.get("_updated_at_key", 0.0) or 0.0),
            str(item.get("name") or "").lower(),
        ),
        reverse=False,
    )

    cleaned: list[dict[str, Any]] = []
    for item in ranked[: max(0, int(limit))]:
        item = dict(item)
        item.pop("_updated_at_key", None)
        cleaned.append(item)
    return cleaned
