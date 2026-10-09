#!/usr/bin/env python3
"""Bounded public-HTTP 3060 driver; product telemetry remains authoritative."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
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


def http_json(url: str, payload: dict[str, Any] | None, timeout: float) -> tuple[int, str]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="GET" if data is None else "POST")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise RuntimeError(str(exc)) from exc


def gate_a(events_path: Path, provenance_path: Path) -> tuple[bool, str]:
    """Gate A observes raw product evidence before any abort request."""

    try:
        result = reduce_events(parse_raw_jsonl([events_path]), load_provenance(provenance_path))
    except Exception as exc:  # fail closed for malformed/unavailable evidence
        return False, f"Gate A blocked: {exc}"
    required = ("provenance", "singular_identity", "positive_full_hit", "host_alloc_park")
    if result["status"] == STATUS_INVALID_INPUT or not all(result["oracle"].get(key, False) for key in required):
        return False, "Gate A blocked: positive full-hit HOST_ALLOC park is not authoritative"
    return True, "Gate A passed: authoritative positive full-hit HOST_ALLOC park observed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:30000")
    parser.add_argument("--target-label", required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--build-rid", default="p0b-r89-build")
    parser.add_argument("--holder-rid", default="p0b-r89-holder")
    parser.add_argument("--target-rid", default="p0b-r89-target")
    parser.add_argument("--deadline-seconds", type=int, default=MAX_SECONDS)
    args = parser.parse_args(argv)

    if args.target_label != TARGET_LABEL:
        print(json.dumps({"status": STATUS_INVALID_INPUT, "reason": "target is not RTX 3060 12G"}))
        return 2
    if args.deadline_seconds < 1 or args.deadline_seconds > MAX_SECONDS:
        print(json.dumps({"status": STATUS_INVALID_INPUT, "reason": "deadline exceeds 600 seconds"}))
        return 2
    if len({args.build_rid, args.holder_rid, args.target_rid}) != 3:
        print(json.dumps({"status": STATUS_INVALID_INPUT, "reason": "request RIDs must be disjoint"}))
        return 2
    if any(token in args.base_url.lower() for token in ("3090", "production", "prod")):
        print(json.dumps({"status": STATUS_INVALID_INPUT, "reason": "3090/production endpoint forbidden"}))
        return 2

    started = time.monotonic()
    requests = 0
    transcript: list[dict[str, Any]] = []

    def public_post(path: str, body: dict[str, Any]) -> bool:
        nonlocal requests
        if requests >= MAX_REQUESTS or time.monotonic() - started >= args.deadline_seconds:
            return False
        try:
            code, text = http_json(
                args.base_url.rstrip("/") + path,
                body,
                timeout=min(30, args.deadline_seconds),
            )
            transcript.append({"method": "POST", "path": path, "status": code, "body": text[:256]})
            requests += 1
            return 200 <= code < 300
        except RuntimeError as exc:
            transcript.append({"method": "POST", "path": path, "error": str(exc)})
            requests += 1
            return False

    # These ordinary requests only stimulate documented HTTP interfaces.  They
    # do not claim a hit, park, retry, finalization, or READY state.
    public_post("/generate", {"rid": args.build_rid, "prompt": "p0b-r89-build", "max_new_tokens": 1})
    public_post("/generate", {"rid": args.holder_rid, "prompt": "p0b-r89-holder", "max_new_tokens": 1})
    public_post("/generate", {"rid": args.target_rid, "prompt": "p0b-r89-target", "max_new_tokens": 1})

    passed, gate_message = gate_a(args.events, args.provenance)
    transcript.append({"gate_a": gate_message, "requests_before_abort": requests})
    if not passed:
        print(
            json.dumps(
                {"status": STATUS_BLOCKED, "requests": requests, "transcript": transcript},
                sort_keys=True,
                indent=2,
            )
        )
        return 0

    # Gate A is intentionally the only path to the externally authorized
    # release action.  The product owns the wake/retry after this call.
    public_post("/abort_request", {"rid": args.holder_rid})
    print(json.dumps({"status": STATUS_NOT_VERIFIED, "requests": requests, "transcript": transcript,
                      "reason": "release submitted; offline authoritative post-run reduction is required"},
                     sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
