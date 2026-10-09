#!/usr/bin/env python3
"""Bounded public-HTTP vehicle for the disposable 3060 P0-B experiment.

The vehicle deliberately does not inspect logs, processes, allocator objects, or
private endpoints.  A public ``/generate`` request can exercise a workload, but
it cannot deterministically create and observe the HOST_ALLOC allocability
transition required by P0-B.  Consequently this driver records public response
facts and exits with a structured BLOCKED result rather than inventing internal
events.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


MAX_SECONDS = 600.0
MAX_REQUESTS = 6
TARGET_GPU = "3060"
SCENARIO = "single-positive-hit"
TRACE_SCHEMA = "p0b.public-http-trace.v1"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Prevent hidden follow-up requests from violating the request bound."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        return None


def _json_body(response: urllib.response.addinfourl) -> Any:
    raw = response.read(256 * 1024)
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"non_json_body": True, "bytes": len(raw)}


def _request(
    opener: urllib.request.OpenerDirector,
    url: str,
    method: str,
    body: dict[str, Any] | None,
    timeout: float,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener.open(request, timeout=max(0.1, timeout)) as response:
            parsed = _json_body(response)
            return {"status_code": response.status, "body": parsed}
    except urllib.error.HTTPError as exc:
        parsed = _json_body(exc)
        return {"status_code": exc.code, "body": parsed, "error": "http_error"}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"status_code": None, "body": None, "error": type(exc).__name__}


def _blocked(
    reason_code: str,
    message: str,
    started: float,
    requests_used: int,
    trace_path: str | None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "BLOCKED",
        "reason_code": reason_code,
        "message": message,
        "target_gpu": TARGET_GPU,
        "scenario": SCENARIO,
        "requests_used": requests_used,
        "max_requests": MAX_REQUESTS,
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "trace_path": trace_path,
        "reducer_compatible": False,
    }
    if details:
        result["details"] = details
    return result


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    started = time.monotonic()
    trace: dict[str, Any] = {
        "schema": TRACE_SCHEMA,
        "target_gpu": TARGET_GPU,
        "scenario": SCENARIO,
        "base_url": args.base_url,
        "events": [],
    }
    requests_used = 0
    trace_path = str(args.trace_out) if args.trace_out else None

    parsed_url = urllib.parse.urlparse(args.base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        result = _blocked(
            "INVALID_BASE_URL",
            "base URL must be an absolute HTTP(S) URL",
            started,
            requests_used,
            trace_path,
        )
        return 2, result
    if args.target != TARGET_GPU:
        result = _blocked(
            "TARGET_NOT_AUTHORIZED",
            "this disposable vehicle is authorized for RTX 3060 only",
            started,
            requests_used,
            trace_path,
        )
        return 2, result
    if args.seconds <= 0 or args.seconds > MAX_SECONDS:
        result = _blocked(
            "TIME_BOUND_INVALID",
            f"scenario bound must be in (0, {MAX_SECONDS}] seconds",
            started,
            requests_used,
            trace_path,
        )
        return 2, result
    if args.repeat <= 0 or args.repeat > 55000:
        result = _blocked(
            "SCENARIO_BOUND_INVALID",
            "prompt repeat must be in [1, 55000]",
            started,
            requests_used,
            trace_path,
        )
        return 2, result

    opener = urllib.request.build_opener(NoRedirect)
    deadline = started + args.seconds

    def remaining() -> float:
        return deadline - time.monotonic()

    health_url = args.base_url.rstrip("/") + "/health"
    if remaining() <= 0 or requests_used >= MAX_REQUESTS:
        return 2, _blocked("TIME_BOUND_EXPIRED", "deadline expired before health request", started, requests_used, trace_path)
    health = _request(opener, health_url, "GET", None, min(args.request_timeout, remaining()))
    requests_used += 1
    trace["events"].append({"type": "http_response", "endpoint": "/health", **health})
    if health.get("status_code") != 200:
        result = _blocked(
            "HEALTH_NOT_READY",
            "public health endpoint did not return HTTP 200",
            started,
            requests_used,
            trace_path,
            {"health": health},
        )
        _write_trace(args.trace_out, trace)
        return 2, result

    if remaining() <= 0 or requests_used >= MAX_REQUESTS:
        result = _blocked("TIME_BOUND_EXPIRED", "deadline expired before generate request", started, requests_used, trace_path)
        _write_trace(args.trace_out, trace)
        return 2, result

    rid = f"P0BHARNESSR76_{time.time_ns()}"
    generate_body = {
        "rid": rid,
        "text": (args.character + " ") * args.repeat,
        "sampling_params": {"temperature": 0, "max_new_tokens": 1},
    }
    generate_url = args.base_url.rstrip("/") + "/generate"
    generated = _request(opener, generate_url, "POST", generate_body, min(args.request_timeout, remaining()))
    requests_used += 1
    trace["events"].append({"type": "http_response", "endpoint": "/generate", "rid": rid, **generated})
    _write_trace(args.trace_out, trace)

    result = _blocked(
        "PUBLIC_HTTP_CANNOT_CREATE_HOST_ALLOC",
        "public /generate completed or failed, but public HTTP exposes no deterministic control or observation of a HOST_ALLOC allocability change; refusing to simulate internal events",
        started,
        requests_used,
        trace_path,
        {"rid": rid, "health": health, "generate": generated},
    )
    return 2, result


def _write_trace(path: Path | None, trace: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:30000")
    parser.add_argument("--target", default=TARGET_GPU)
    parser.add_argument("--seconds", type=float, default=MAX_SECONDS)
    parser.add_argument("--request-timeout", type=float, default=120.0)
    parser.add_argument("--repeat", type=int, default=55000)
    parser.add_argument("--character", default="x")
    parser.add_argument("--trace-out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    code, result = run(args)
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
