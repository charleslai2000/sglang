#!/usr/bin/env python3
"""Bounded public-interface-only R94 driver for the authorized RTX 3060."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from p0b_reducer import (
    STATUS_BLOCKED,
    STATUS_INVALID_INPUT,
    STATUS_NOT_VERIFIED,
    load_provenance,
    parse_raw_jsonl,
    reduce_events,
)

MAX_SECONDS = 600
MAX_REQUESTS = 6
TARGET_LABEL = "RTX 3060 12G"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request: urllib.request.Request, response: Any, newurl: str) -> None:
        raise urllib.error.HTTPError(request.full_url, response.status, "redirect refused", response.headers, None)


OPENER = urllib.request.build_opener(NoRedirect)


def http_json(url: str, payload: dict[str, Any] | None, timeout: float) -> tuple[int, str]:
    data = None if payload is None else json.dumps(payload, sort_keys=True).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="GET" if data is None else "POST")
    request.add_header("Content-Type", "application/json")
    with OPENER.open(request, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def gate_a(events_path: Path, provenance_path: Path) -> tuple[bool, str]:
    """Observe authoritative Gate A evidence; never synthesize product state."""

    try:
        result = reduce_events(parse_raw_jsonl([events_path]), load_provenance(provenance_path))
    except Exception as exc:  # malformed, unavailable, or unbound evidence is fail-closed
        return False, f"Gate A evidence unavailable: {exc}"
    required = ("provenance", "singular_identity", "positive_full_hit", "host_alloc_park")
    if result["status"] == "INVALID_INPUT" or not all(result["oracle"].get(key, False) for key in required):
        return False, "Gate A not established by authoritative raw events"
    return True, "Gate A established by authoritative raw events"


def _result(status: str, reason: str, requests: int, transcript: list[dict[str, Any]]) -> int:
    print(json.dumps({"status": status, "reason": reason, "requests": requests, "transcript": transcript}, sort_keys=True, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:30000")
    parser.add_argument("--target-label", required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--source-manifest-id", required=True)
    parser.add_argument("--deadline-seconds", type=int, default=MAX_SECONDS)
    parser.add_argument("--gate-attempts", type=int, default=3)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args(argv)
    if args.target_label != TARGET_LABEL:
        return _result(STATUS_INVALID_INPUT, "target is not RTX 3060 12G", 0, [])
    if args.deadline_seconds < 1 or args.deadline_seconds > MAX_SECONDS:
        return _result(STATUS_INVALID_INPUT, "deadline must be between 1 and 600 seconds", 0, [])
    if args.gate_attempts < 1 or args.gate_attempts > MAX_REQUESTS or args.poll_seconds < 0:
        return _result(STATUS_INVALID_INPUT, "invalid bounded gate polling parameters", 0, [])
    if args.server_pid < 1 or not args.profile or not args.source_manifest_id:
        return _result(STATUS_INVALID_INPUT, "preflight PID/profile/source binding is required", 0, [])
    parsed = urllib.parse.urlparse(args.base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        return _result(STATUS_INVALID_INPUT, "only loopback public HTTP is permitted", 0, [])
    if any(token in args.base_url.lower() for token in ("3090", "production", "prod")):
        return _result(STATUS_INVALID_INPUT, "3090/production endpoint forbidden", 0, [])
    try:
        provenance = load_provenance(args.provenance)
    except Exception as exc:
        return _result(STATUS_INVALID_INPUT, f"invalid provenance manifest: {exc}", 0, [])
    if any(provenance.get(key) != value for key, value in {
        "target": TARGET_LABEL,
        "server_pid": args.server_pid,
        "profile": args.profile,
        "source_manifest_id": args.source_manifest_id,
    }.items()):
        return _result(STATUS_INVALID_INPUT, "CLI preflight binding disagrees with provenance", 0, [])

    started = time.monotonic()
    requests = 0
    transcript: list[dict[str, Any]] = []

    def public(method_path: str, body: dict[str, Any] | None, phase: str) -> tuple[bool, str]:
        nonlocal requests
        if requests >= MAX_REQUESTS or time.monotonic() - started >= args.deadline_seconds:
            return False, "bounded request/time budget exhausted"
        remaining = max(0.1, args.deadline_seconds - (time.monotonic() - started))
        try:
            code, text = http_json(args.base_url.rstrip("/") + method_path, body, min(30.0, remaining))
            requests += 1
            transcript.append({"phase": phase, "path": method_path, "status": code, "body": text[:256]})
            if not 200 <= code < 300:
                return False, f"public {phase} returned HTTP {code}"
            return True, text
        except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            requests += 1
            transcript.append({"phase": phase, "path": method_path, "error": str(exc)})
            return False, str(exc)

    # State 1: public preflight establishes PID/profile/source binding.  No
    # private process inspection, redirection, event injection, or launch occurs.
    ok, response = public("/health", None, "preflight")
    if not ok:
        return _result(STATUS_BLOCKED, f"infrastructure endpoint unavailable during preflight: {response}", requests, transcript)
    health = _json_object(response)
    if health is None or any(health.get(key) != value for key, value in {
        "server_pid": args.server_pid,
        "profile": args.profile,
        "source_manifest_id": args.source_manifest_id,
    }.items()):
        return _result(STATUS_NOT_VERIFIED, "public preflight did not establish PID/profile/source binding", requests, transcript)

    # State 2: holder staging is a public create; its response must identify the
    # requested RID.  A successful HTTP code alone is not product-state proof.
    ok, response = public("/generate", {"rid": "p0b-r94-holder", "prompt": "p0b-r94-holder", "max_new_tokens": 1}, "holder_staging")
    holder = _json_object(response) if ok else None
    if not ok:
        if "HTTP" not in response and "redirect" not in response.lower():
            return _result(STATUS_BLOCKED, f"infrastructure endpoint unavailable during holder staging: {response}", requests, transcript)
        return _result(STATUS_NOT_VERIFIED, "public holder create did not establish product state", requests, transcript)
    if holder is None or holder.get("rid") != "p0b-r94-holder":
        return _result(STATUS_NOT_VERIFIED, "public holder create response lacks bound RID", requests, transcript)

    # State 3: target create is the only route to Gate A.  No event is invented
    # from this response; the reducer must observe the raw product event file.
    ok, response = public("/generate", {"rid": "p0b-r94-target", "prompt": "p0b-r94-target", "max_new_tokens": 1}, "target_create")
    target = _json_object(response) if ok else None
    if not ok:
        if "HTTP" not in response and "redirect" not in response.lower():
            return _result(STATUS_BLOCKED, f"infrastructure endpoint unavailable during target create: {response}", requests, transcript)
        return _result(STATUS_NOT_VERIFIED, "public target create inability cannot establish Gate A", requests, transcript)
    if target is None or target.get("rid") != "p0b-r94-target":
        return _result(STATUS_NOT_VERIFIED, "public target create response lacks bound RID", requests, transcript)

    # State 4: observe Gate A only.  The holder is not aborted until all
    # required raw evidence is present.  Failure after bounded public creates is
    # NOT_VERIFIED, not BLOCKED.
    passed = False
    gate_message = ""
    for attempt in range(args.gate_attempts):
        passed, gate_message = gate_a(args.events, args.provenance)
        transcript.append({"phase": "gate_a", "attempt": attempt + 1, "result": gate_message})
        if passed:
            break
        if args.poll_seconds and time.monotonic() - started < args.deadline_seconds:
            time.sleep(min(args.poll_seconds, max(0.0, args.deadline_seconds - (time.monotonic() - started))))
    if not passed:
        return _result(STATUS_NOT_VERIFIED, gate_message, requests, transcript)

    # State 5: release is reachable only after Gate A.  Its response is not a
    # PASS claim; post-abort raw events still require offline reduction.
    ok, response = public("/abort_request", {"rid": "p0b-r94-holder"}, "abort_request")
    if not ok:
        if "HTTP" not in response and "redirect" not in response.lower():
            return _result(STATUS_BLOCKED, f"infrastructure endpoint unavailable during abort: {response}", requests, transcript)
        return _result(STATUS_NOT_VERIFIED, "abort response did not establish product state", requests, transcript)
    transcript.append({"phase": "post_abort", "note": "offline authoritative reduction required"})
    return _result(STATUS_NOT_VERIFIED, "release submitted; final authoritative reduction is required", requests, transcript)


if __name__ == "__main__":
    raise SystemExit(main())
