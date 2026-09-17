#!/usr/bin/env python3
"""OpenAI-compatible smokes for the DEV provider.

Runs, against an already-running server:

  1. /health       -> 200
  2. /v1/models WITHOUT a key -> 401/403 (auth is really enforced)
  3. /v1/models WITH the key  -> 200 and contains the served model name
  4. chat completion -> non-empty, coherent answer
  5. tool call     -> the model really emits a function call

Exits non-zero on the first failure, printing which check failed.  Standard
library only.

Auth notes
----------
* sglang always allows /health and /metrics without a key (deliberate, so
  liveness probes and Prometheus need no secret); every other endpoint needs
  the bearer token once --api-key is set.
* Check 2 exists because "AUTH=ON" is otherwise an assertion rather than a
  measured fact: a launch path that silently drops --api-key still serves 200
  on every endpoint, and nothing else in the startup gates would notice.
  Confirmed possible on this host -- a pre-fix launch ran with no key and all
  other checks passed.
* The key file is root:root 0600, so this process reads it through
  `sudo -n cat` rather than opening it directly.  The value never becomes an
  argv element of any process.
* Proxies are disabled explicitly: a stray http_proxy in the environment
  would otherwise redirect a loopback/LAN call.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request


def fail(check: str, detail: str) -> None:
    print(f"{check}=FAIL: {detail}")
    raise SystemExit(1)


def read_key(keyfile: str) -> str:
    try:
        proc = subprocess.run(
            ["sudo", "-n", "cat", keyfile],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        fail("SMOKE", f"cannot read the API key file: {exc}")
    if proc.returncode != 0:
        fail(
            "SMOKE",
            "sudo cat of the API key file failed: "
            + proc.stderr.decode(errors="replace").strip(),
        )
    key = proc.stdout.decode().strip()
    if not key:
        fail("SMOKE", "the API key file is empty")
    return key


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(
    url: str,
    *,
    token: str | None = None,
    payload: dict | None = None,
    timeout: float = 300.0,
) -> tuple[int, bytes]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with OPENER.open(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        fail("NETWORK", f"{url} unreachable: {exc}")


def main() -> int:
    if len(sys.argv) != 5:
        print(
            "usage: provider-smoke.py <base_url> <model> <api-key-file> <timeout>",
            file=sys.stderr,
        )
        return 2
    base, model, keyfile, timeout_s = sys.argv[1:5]
    timeout = float(timeout_s)
    token = read_key(keyfile)

    # ---- 1. /health ------------------------------------------------------
    code, _ = request(f"{base}/health", timeout=30.0)
    if code != 200:
        fail("HEALTH", f"/health returned HTTP {code}")
    print("HEALTH=PASS")

    # ---- 2. auth is really enforced --------------------------------------
    # Without this, a key-less launch is indistinguishable from a keyed one
    # for every other check in this file.
    code, body = request(f"{base}/v1/models", timeout=60.0)
    if code not in (401, 403):
        fail(
            "AUTH_REQUIRED",
            f"/v1/models without a key returned HTTP {code}; expected 401/403. "
            f"API key is NOT being enforced. body={body[:200]!r}",
        )
    print(f"AUTH_REQUIRED=PASS (no key -> {code})")

    # ---- 3. /v1/models with the key --------------------------------------
    code, body = request(f"{base}/v1/models", token=token, timeout=60.0)
    if code != 200:
        fail("MODELS", f"/v1/models returned HTTP {code}: {body[:200]!r}")
    try:
        listed = [m["id"] for m in json.loads(body).get("data", [])]
    except (ValueError, KeyError, TypeError) as exc:
        fail("MODELS", f"unparseable /v1/models body: {exc}")
    if model not in listed:
        fail("MODELS", f"{model!r} not in served models {listed}")
    print(f"AUTH_WITH_KEY=PASS (with key -> 200, {model})")

    # ---- 4. chat completion ---------------------------------------------
    # A factual question with a single-token answer, so "non-empty and
    # coherent" is checkable without a judge.
    chat_payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "What is the capital city of France? Answer with just the city name.",
            }
        ],
        "max_tokens": 64,
        "temperature": 0.0,
        # Skip the reasoning preamble: keeps the smoke fast and deterministic.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    code, body = request(
        f"{base}/v1/chat/completions", token=token, payload=chat_payload, timeout=timeout
    )
    if code != 200:
        fail("CHAT_SMOKE", f"HTTP {code}: {body[:300]!r}")
    try:
        msg = json.loads(body)["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        fail("CHAT_SMOKE", f"unparseable completion body: {exc}")
    content = (msg.get("content") or "").strip()
    if not content:
        fail("CHAT_SMOKE", f"empty completion content (message={msg!r})")
    if "paris" not in content.lower():
        fail(
            "CHAT_SMOKE",
            f"reply is not a coherent answer to the France question: {content!r}",
        )
    print(f"CHAT_SMOKE=PASS ({content[:60]!r})")

    # ---- 5. tool call ----------------------------------------------------
    # The qwen3_coder parser emits <tool_call><function=...>.  Require a real
    # parsed tool_calls entry with the required argument, not just prose about
    # calling a function.
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather for a city.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name"},
                        "unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "description": "Temperature unit",
                        },
                    },
                    "required": ["city"],
                },
            },
        }
    ]
    tool_payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "What is the current weather in Paris? Use the get_weather tool.",
            }
        ],
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 256,
        "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    code, body = request(
        f"{base}/v1/chat/completions", token=token, payload=tool_payload, timeout=timeout
    )
    if code != 200:
        fail("TOOL_SMOKE", f"HTTP {code}: {body[:300]!r}")
    try:
        msg = json.loads(body)["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        fail("TOOL_SMOKE", f"unparseable tool-call body: {exc}")
    calls = msg.get("tool_calls") or []
    if not calls:
        fail(
            "TOOL_SMOKE",
            "model returned no tool_calls "
            f"(content={(msg.get('content') or '')[:160]!r})",
        )
    fn = (calls[0].get("function") or {}).get("name")
    if fn != "get_weather":
        fail("TOOL_SMOKE", f"expected function get_weather, got {fn!r}")
    raw_args = (calls[0].get("function") or {}).get("arguments") or ""
    try:
        parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except ValueError as exc:
        fail("TOOL_SMOKE", f"tool arguments are not valid JSON ({exc}): {raw_args!r}")
    if not isinstance(parsed, dict) or "city" not in parsed:
        fail("TOOL_SMOKE", f"tool arguments lack the required 'city': {parsed!r}")
    print(f"TOOL_SMOKE=PASS (get_weather city={parsed.get('city')!r})")

    print("SMOKE=ALL_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
