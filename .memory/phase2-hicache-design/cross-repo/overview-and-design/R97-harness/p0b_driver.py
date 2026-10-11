#!/usr/bin/env python3
"""Bounded public-interface-only RTX 3060 P0-B vehicle.

This driver never fabricates telemetry and never imports product code.  It
submits the predeclared build/holder/target sequence, checks Gate A from raw
product evidence, and only then sends the exact holder abort payload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
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
TARGET = "RTX 3060 12G"


def _http_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, str]:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def gate_a(events_path: Path, provenance_path: Path) -> tuple[bool, str]:
    """Gate A requires authoritative evidence before any release action."""
    result = reduce_events(parse_raw_jsonl([events_path]), load_provenance(provenance_path, [events_path]))
    needed = ("provenance", "pid_profile_source_binding", "singular_identity", "positive_full_hit", "host_alloc_park")
    if result["status"] == STATUS_INVALID_INPUT or not all(result["oracle"].get(key, False) for key in needed):
        return False, "Gate A not verified: authoritative positive full-hit HOST_ALLOC park is absent"
    return True, "Gate A passed: authoritative positive full-hit HOST_ALLOC park observed"


def _capture_bundle(
    events: Path,
    provenance: Path,
    destination: Path,
    transcript: list[dict[str, Any]],
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    event_copy = destination / events.name
    provenance_copy = destination / provenance.name
    transcript_copy = destination / "driver-transcript.json"
    shutil.copyfile(events, event_copy)
    transcript_copy.write_text(
        json.dumps(transcript, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = json.loads(provenance.read_text(encoding="utf-8"))
    manifest["raw_files"] = {
        str(event_copy.resolve()): hashlib.sha256(event_copy.read_bytes()).hexdigest(),
        str(transcript_copy.resolve()): hashlib.sha256(transcript_copy.read_bytes()).hexdigest(),
    }
    event_sources: dict[str, list[str]] = {}
    with event_copy.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            event_sources.setdefault(record["evt"], []).append(
                f"{event_copy.resolve()}:{line_number}"
            )
    manifest["event_sources"] = event_sources
    manifest["capture"] = {"complete": True, "collector": "raw-jsonl"}
    provenance_copy.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for path in (event_copy, transcript_copy, provenance_copy):
        path.chmod(0o400)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:30000")
    parser.add_argument("--target-label", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--build-rid", default="p0b-r97-build")
    parser.add_argument("--holder-rid", default="p0b-r97-holder")
    parser.add_argument("--target-rid", default="p0b-r97-target")
    parser.add_argument("--deadline-seconds", type=int, default=MAX_SECONDS)
    args = parser.parse_args(argv)

    if args.target_label != TARGET or args.deadline_seconds < 1 or args.deadline_seconds > MAX_SECONDS:
        print(json.dumps({"status": STATUS_INVALID_INPUT, "reason": "RTX 3060/600-second bounds rejected"}))
        return 0
    if len({args.build_rid, args.holder_rid, args.target_rid}) != 3 or any(not rid for rid in (args.build_rid, args.holder_rid, args.target_rid)):
        print(json.dumps({"status": STATUS_INVALID_INPUT, "reason": "build/holder/target RIDs must be distinct"}))
        return 0
    if args.target_rid.startswith(args.holder_rid):
        print(json.dumps({"status": STATUS_INVALID_INPUT, "reason": "target RID must not match holder abort prefix"}))
        return 0
    if any(token in args.base_url.lower() for token in ("3090", "production", "prod")):
        print(json.dumps({"status": STATUS_INVALID_INPUT, "reason": "3090/production endpoint forbidden"}))
        return 0
    if not args.events.is_file() or not args.provenance.is_file():
        print(json.dumps({"status": STATUS_NOT_VERIFIED, "reason": "raw evidence/provenance is missing"}))
        return 0
    try:
        manifest = load_provenance(args.provenance, [args.events])
    except Exception as exc:
        print(json.dumps({"status": STATUS_INVALID_INPUT, "reason": f"provenance rejected: {exc}"}))
        return 0
    if manifest.get("profile", {}).get("profile_id") != args.profile_id:
        print(json.dumps({"status": STATUS_INVALID_INPUT, "reason": "profile-id is not bound by provenance"}))
        return 0

    started = time.monotonic()
    requests = 0
    transcript: list[dict[str, Any]] = []
    infrastructure_reason: str | None = None

    def public_post(path: str, body: dict[str, Any]) -> bool:
        nonlocal requests, infrastructure_reason
        if requests >= MAX_REQUESTS or time.monotonic() - started >= args.deadline_seconds:
            infrastructure_reason = "bounded request/time limit reached"
            return False
        try:
            code, text = _http_json(args.base_url.rstrip("/") + path, body, min(30.0, args.deadline_seconds))
            requests += 1
            transcript.append({"method": "POST", "path": path, "status": code, "request": body, "response_prefix": text[:256]})
            if code >= 500:
                infrastructure_reason = f"endpoint returned infrastructure status {code} for {path}"
            return 200 <= code < 300
        except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            requests += 1
            infrastructure_reason = f"endpoint unavailable for {path}: {exc}"
            transcript.append({"method": "POST", "path": path, "request": body, "error": str(exc)})
            return False

    # Exact public state machine: build -> holder -> target -> Gate A -> one holder abort.
    public_post("/generate", {"rid": args.build_rid, "prompt": "p0b-r97-build", "max_new_tokens": 1})
    public_post("/generate", {"rid": args.holder_rid, "prompt": "p0b-r97-holder", "max_new_tokens": 1})
    public_post("/generate", {"rid": args.target_rid, "prompt": "p0b-r97-target", "max_new_tokens": 1})
    try:
        gate_passed, gate_message = gate_a(args.events, args.provenance)
    except Exception as exc:  # malformed evidence is reported, never released
        gate_passed, gate_message = False, f"Gate A invalid/not verified: {exc}"
    transcript.append({"state": "GATE_A", "message": gate_message, "requests_before_abort": requests})
    if infrastructure_reason is not None:
        status, reason = STATUS_BLOCKED, infrastructure_reason
    elif not gate_passed:
        status, reason = STATUS_NOT_VERIFIED, gate_message
    else:
        # AbortReq has two fields; abort_all is explicit and must remain false.
        public_post("/abort_request", {"rid": args.holder_rid, "abort_all": False})
        status, reason = STATUS_NOT_VERIFIED, "release submitted; post-run authoritative reduction is required"

    _capture_bundle(args.events, args.provenance, args.evidence_dir, transcript)
    report = {"status": status, "reason": reason, "requests": requests, "transcript": transcript, "captured_bundle": str(args.evidence_dir.resolve())}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
