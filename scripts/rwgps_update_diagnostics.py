#!/usr/bin/env python3
"""Diagnostic script: test RWGPS update endpoints (PUT/PATCH) for route geometry replacement.

Tests are run on a fresh COPY of source route 55256628.
Logs: method, url, status_code, response body (first 1000 chars).
"""

import json
import logging
import sys
import os
from pathlib import Path

import httpx

# ── Config ──────────────────────────────────────────────────────────────────
SOURCE_ROUTE_ID = "55256628"
RWGPS_API_BASE = "https://ridewithgps.com"
RWGPS_AUTH_TOKEN = os.environ.get("RWGPS_AUTH_TOKEN") or "ce78435f8fc0da670d32e5291673d4c8"
RWGPS_API_KEY = os.environ.get("RWGPS_API_KEY") or "6ff5461b"
RWGPS_USER_ID = os.environ.get("RWGPS_USER_ID") or "1040578"

HEADERS = {
    "Accept": "application/json",
    "x-rwgps-auth-token": RWGPS_AUTH_TOKEN,
    "x-rwgps-api-key": RWGPS_API_KEY,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rwgps_diag")


def log_response(method: str, url: str, resp: httpx.Response, tag: str = ""):
    body_preview = resp.text[:1000]
    log.info("─── %s ───", tag or f"{method} {url}")
    log.info("  %s %s  →  HTTP %s", method, url, resp.status_code)
    log.info("  body[0:1000]: %s", body_preview)
    log.info("")


def json_payload(text: str) -> str:
    """Return pretty-printed JSON for logging."""
    try:
        return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    except Exception:
        return text


def try_request(method: str, url: str, json_body: dict | None = None, tag: str = "") -> httpx.Response:
    """Make an HTTP request and log the result."""
    with httpx.Client(timeout=30.0, follow_redirects=False) as client:
        try:
            resp = client.request(
                method=method.upper(),
                url=url,
                headers=HEADERS,
                json=json_body,
            )
        except httpx.RequestError as e:
            log.error("  REQUEST FAILED: %s", e)
            return None
    log_response(method, url, resp, tag)
    return resp


# ── Step 0: Check source route exists ───────────────────────────────────────
log.info("=" * 72)
log.info("STEP 0: Check source route %s", SOURCE_ROUTE_ID)
log.info("=" * 72)

r = try_request("GET", f"{RWGPS_API_BASE}/api/v1/routes/{SOURCE_ROUTE_ID}.json?track_points=1", tag="GET source route (v1)")
if r is None:
    log.error("Cannot reach RWGPS API. Aborting.")
    sys.exit(1)
if r.status_code != 200:
    log.error("Source route not accessible (HTTP %s). Aborting.", r.status_code)
    sys.exit(1)

data = r.json()
route_v1 = data.get("route") or data
has_track_points = bool(route_v1.get("track_points"))
log.info("  Source route: id=%s, name=%s, track_points=%s",
         route_v1.get("id"), route_v1.get("name"), len(route_v1.get("track_points") or []) if has_track_points else 0)

# ── Step 0b: Try GET without /api/v1 ────────────────────────────────────────
log.info("=" * 72)
log.info("STEP 0b: GET source via legacy path (no /api/v1)")
log.info("=" * 72)
try_request("GET", f"{RWGPS_API_BASE}/routes/{SOURCE_ROUTE_ID}.json", tag="GET source route (legacy)")

# ── Step 1: Copy source route ───────────────────────────────────────────────
log.info("=" * 72)
log.info("STEP 1: Copy source route 55256628 via POST /routes/{id}/copy.json")
log.info("=" * 72)

copy_url = f"{RWGPS_API_BASE}/routes/{SOURCE_ROUTE_ID}/copy.json"
with httpx.Client(timeout=30.0, follow_redirects=False) as client:
    resp = client.post(copy_url, headers=HEADERS)

log_response("POST", copy_url, resp, "COPY route")

if resp.status_code not in (200, 201):
    log.error("Copy failed. Cannot proceed with tests. Exiting.")
    sys.exit(1)

copy_data = resp.json()
copy_route = copy_data.get("route") or copy_data
TEST_ROUTE_ID = str(copy_route.get("id", ""))
log.info("  Copied route ID: %s", TEST_ROUTE_ID)

if not TEST_ROUTE_ID:
    log.error("No route ID from copy. Exiting.")
    sys.exit(1)

TEST_ROUTE_URLS = {
    "v1": f"{RWGPS_API_BASE}/api/v1/routes/{TEST_ROUTE_ID}.json",
    "v1_track_points": f"{RWGPS_API_BASE}/api/v1/routes/{TEST_ROUTE_ID}.json?track_points=1",
    "legacy": f"{RWGPS_API_BASE}/routes/{TEST_ROUTE_ID}.json",
    "user_v1": f"{RWGPS_API_BASE}/api/v1/users/{RWGPS_USER_ID}/routes/{TEST_ROUTE_ID}.json",
    "user_legacy": f"{RWGPS_API_BASE}/users/{RWGPS_USER_ID}/routes/{TEST_ROUTE_ID}.json",
}

# ── Step 2: GET the copy to check initial state ─────────────────────────────
log.info("=" * 72)
log.info("STEP 2: GET copy route (initial state)")
log.info("=" * 72)

try_request("GET", TEST_ROUTE_URLS["v1_track_points"], tag="GET copy (v1 + track_points)")
try_request("GET", TEST_ROUTE_URLS["legacy"], tag="GET copy (legacy)")

# ── Step 3: Test UPDATE endpoints ───────────────────────────────────────────
log.info("=" * 72)
log.info("STEP 3: Test UPDATE endpoints with various payload styles")
log.info("=" * 72)

SAMPLE_PAYLOADS = [
    ("flat", {"name": f"Tuscany 2026 — DIAG COPY (flat) {TEST_ROUTE_ID}"}),
    ("nested_route", {"route": {"name": f"Tuscany 2026 — DIAG COPY (nested) {TEST_ROUTE_ID}"}}),
    ("flat_description", {"name": f"Tuscany 2026 — DIAG COPY {TEST_ROUTE_ID}", "description": "Diagnostic test copy"}),
    ("nested_description", {"route": {"name": f"Tuscany 2026 — DIAG COPY {TEST_ROUTE_ID}", "description": "Diagnostic test copy"}}),
]

# Only for the first flat payload, add track_points if we have them
if has_track_points:
    tp_sample = route_v1["track_points"][:5]
    SAMPLE_PAYLOADS.append(("flat_with_track_points", {"name": f"DIAG TP {TEST_ROUTE_ID}", "track_points": tp_sample}))
    SAMPLE_PAYLOADS.append(("nested_with_track_points", {"route": {"name": f"DIAG TP {TEST_ROUTE_ID}", "track_points": tp_sample}}))

URL_VARIANTS = [
    ("v1", TEST_ROUTE_URLS["v1"]),
    ("legacy", TEST_ROUTE_URLS["legacy"]),
    ("user_v1", TEST_ROUTE_URLS["user_v1"]),
    ("user_legacy", TEST_ROUTE_URLS["user_legacy"]),
]

all_results = []

for method in ("PUT", "PATCH"):
    for url_label, url in URL_VARIANTS:
        for payload_label, payload in SAMPLE_PAYLOADS:
            tag = f"{method} {url_label} ({payload_label})"
            resp = try_request(method, url, payload, tag=tag)
            if resp is not None:
                all_results.append({
                    "method": method,
                    "url_label": url_label,
                    "url": url,
                    "payload_label": payload_label,
                    "status_code": resp.status_code,
                    "body_preview": resp.text[:1000],
                })

# ── Step 4: Report summary ──────────────────────────────────────────────────
log.info("=" * 72)
log.info("SUMMARY: All endpoint tests")
log.info("=" * 72)

working = []
failing = []
for r in all_results:
    line = f"{r['method']:6s} {r['url_label']:12s} {r['payload_label']:30s} → HTTP {r['status_code']}"
    if 200 <= r['status_code'] < 400:
        working.append(r)
        log.info("  ✅ %s", line)
    else:
        failing.append(r)
        log.info("  ❌ %s", line)

log.info("")
log.info("Working: %d  |  Failing: %d  |  Total: %d", len(working), len(failing), len(all_results))

# ── Step 5: Cleanup — delete copy ────────────────────────────────────────────
log.info("=" * 72)
log.info("STEP 5: Cleanup — delete test copy")
log.info("=" * 72)

# Try DELETE on all URL variants to maximize chance of cleanup
for url_label, url in TEST_ROUTE_URLS.items():
    if "track_points" in url_label:
        continue
    try_request("DELETE", url, tag=f"DELETE copy ({url_label})")

log.info("=" * 72)
log.info("DIAGNOSTIC COMPLETE")
log.info("=" * 72)

# ── Print machine-readable JSON summary ──────────────────────────────────────
summary = {
    "source_route_id": SOURCE_ROUTE_ID,
    "test_route_id": TEST_ROUTE_ID,
    "results": all_results,
    "working_count": len(working),
    "failing_count": len(failing),
    "has_working_update": any(200 <= r["status_code"] < 400 for r in all_results if r["method"] in ("PUT", "PATCH")),
    "update_endpoints": sorted(set(
        (r["method"], r["url_label"], r["status_code"])
        for r in all_results if r["method"] in ("PUT", "PATCH")
    )),
}
print("\n\n---MACHINE_SUMMARY---")
print(json.dumps(summary, indent=2, ensure_ascii=False))
print("---END_MACHINE_SUMMARY---")


# ── Appendix: test import_stage_from_canonical ──────────────────────────────
def test_import_stage_2() -> dict:
    """Test the full copy→fetch→trim→update pipeline for stage 2 (65-150 km).

    Returns result dict. Does NOT clean up — the created route is left for
    manual inspection if the test passes, or for diagnosis if it fails.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from tools.rwgps.client import import_stage_from_canonical

    log.info("")
    log.info("=" * 72)
    log.info("APPENDIX: test import_stage_from_canonical — stage 2 (65-150 km)")
    log.info("=" * 72)

    try:
        result = import_stage_from_canonical(
            "55256628",
            start_km=65.0,
            end_km=150.0,
            name="Toskania 7D-B Etap 02 TEST FINAL",
        )
    except Exception as e:
        log.error("PIPELINE FAILED: %s", e)
        return {"ok": False, "error": str(e)}

    log.info("Pipeline result: %s", json.dumps(result, indent=2, ensure_ascii=False))
    log.info("")
    log.info("VERIFICATION:")
    log.info("  route_id:           %s", result.get("route_id"))
    log.info("  html_url:           %s", result.get("html_url"))
    log.info("  distance_km:        %s", result.get("distance_km"))
    log.info("  track_points_count: %s", result.get("track_points_count"))
    log.info("  ok:                 %s", result.get("ok"))

    # Validate
    checks = {
        "has_route_id": bool(result.get("route_id")),
        "distance_gt_0": (result.get("distance_m") or 0) > 0,
        "track_points_gt_0": (result.get("track_points_count") or 0) > 0,
        "geometry_not_empty": result.get("track_points_count", 0) > 1,
        "distance_matches_stage": abs((result.get("distance_m") or 0) - (150.0 - 65.0) * 1000) < 5000,
    }
    for check, passed in checks.items():
        log.info("  %s: %s", check, "✅" if passed else "❌")

    result["_checks"] = checks
    return result


if __name__ == "__main__":
    # Only run the main script when executed directly
    # The test function requires sys.path setup
    if len(sys.argv) > 1 and sys.argv[1] == "test-stage2":
        test_import_stage_2()
