#!/usr/bin/env python3
"""Durable concurrency efficiency sweep for M1/M2/M3/M4 role evaluation.

This is a faithful, parameterized consolidation of the two scratch harnesses that
produced the M1/M2 numbers:

  * /tmp/opencode/F39-CAMPAIGN-20260918/efficiency_sweep.py  (main)
  * /tmp/opencode/M2-RCA-20260918/sweep.py                   (F39 derivative,
    adds a POST /flush_cache before each *distinct* level via RCA_FLUSH=1)

Legacy metric definitions are preserved; the amendment below only ADDS fields
and annotations (nothing is renamed or removed):
  * TTFT       = first streamed content delta, measured client-side (requires
                 stream=true).
  * decode TPS = completion_tokens / (dur_s - ttft_s)            (F39 line 154)
  * aggregate  = total_out_tokens / max(per-request dur_s)       (F39 line 169)
  * cache hit  = usage.prompt_tokens_details.cached_tokens       (F39 line 123)
  * tokens     = usage.prompt_tokens / usage.completion_tokens

Protocol defaults match F39: levels 1,2,4,8; 16 requests per level; max_tokens=64;
ignore_eos=true; temperature=0; stream=true; stream_options.include_usage=true;
thinking off. In shared mode one warm-up request runs before the measured batch
(F39 lines 133-135). Output JSON keeps the efficiency-{m1,m2}.json shape
(config + per-level summaries) so new runs can be diffed directly.

Only existing HTTP endpoints/response fields are used; no new observation
mechanism is introduced.

Additive amendments per owner ledger §127 (C1-C4); existing metric definitions
and the legacy 19-field level schema are preserved byte-for-byte:

  * C1 TTFT split: ``first_output_s`` = arrival of ANY model output delta
    (including ``reasoning_content``) and ``first_content_s`` = arrival of the
    first final-answer ``content`` delta. New summary percentiles
    ``ttft_output_p50/p90/p95`` (basic-performance TTFT) and
    ``ttfc_p50/p90/p95`` (time to first content). The legacy ``ttft_*`` fields
    are KEPT and remain equal to first-content (= TTFC) for backward
    compatibility; every ``manifest`` states this explicitly.
  * C2 reasoning/thinking policy is frozen into the per-run ``manifest`` and
    printed to stdout: ``--reasoning-effort`` and ``--thinking on|off``.
  * C3 ``--workload-kind micro|agent-like``; micro keeps the old 64-token /
    ignore_eos protocol and is labelled a microbenchmark. agent-like uses a
    real long prefix, normal EOS, and typical 256/512 output tokens.
  * C4 cache state is an explicit result field per level: ``prompt_tokens_p50``,
    ``cached_tokens_p50``, ``cached_tokens_mean``, ``newly_prefilled_tokens_p50``,
    ``hit_rate_mean``, plus ``--cache-state``. ``--flush`` is a mechanism only.

Additive R2 amendments (owner dispatch, revised ledger §128 semantics):

  * A. ``first_output_s`` (alias ``first_output_ms``) counts ONLY a genuine model
    output delta, decided by the explicit :func:`is_model_output_delta`. Counted:
    ``reasoning_content`` (or ``reasoning``), ``content``, ``tool_calls`` (any
    non-empty). Excluded: lifecycle SSE objects (``response.created`` /
    ``response.in_progress`` / any ``event:`` heartbeat or keepalive), an empty
    delta ``{}``, a role-only delta (``content=""``), ``[DONE]``, and a
    usage-only chunk. ``first_content_s`` (TTFC) still counts ONLY ``content``
    and never reasoning.
  * B. ``manifest`` freezes the effective reasoning/thinking policy with
    ``file:line`` server references and an ``effective_source`` of
    ``assumed``/``unknown``. ``--thinking-budget <n>`` is separated from the
    final-answer allowance (``--out-tokens``); the wire cap is
    ``--max-tokens-total``. For agent-like workloads the client fails closed
    (exit 2, before any request) unless
    ``max_tokens_total >= thinking_budget + out_tokens``. Each level reports
    ``n_reasoning_only`` (finish_reason=length, empty content) and
    ``n_truncated`` (finish_reason=length, non-empty content) and warns on
    stdout + in JSON when either is non-zero. ``--workload-kind micro`` keeps
    the legacy 64-token/ignore_eos protocol unchanged.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import importlib.util
import json
import os
import statistics
import sys
import time
import types
import urllib.request
from urllib.parse import urlsplit, urlunsplit

DEFAULT_URL = "http://127.0.0.1:30000/v1/chat/completions"
DEFAULT_MODEL = "omnicoder-9b-gptq-int4"

# --- fixed prompts (verbatim from F39 efficiency_sweep.py lines 20-49) ---------
# A fixed token-length body (~1500 tokens). Distinct content per request index so
# the radix prefix is NOT shared across requests (cold case) unless asked for.
BODY = (
    "The following is a fixed-length technical passage used only for load generation. "
    + " ".join(
        f"Line {i:04d}: configuration parameter {i} controls subsystem {i % 17} "
        f"and must be recorded in the run ledger exactly once."
        for i in range(150)
    )
)
# A long shared prefix (~2000 tokens) reused verbatim across every request => cache hit.
SHARED_PREFIX = (
    "You are a deterministic load-test assistant. The passage below is immutable context. "
    + " ".join(
        f"Reference block {i:04d} documents behavior {i} with stability guarantee {i % 13}."
        for i in range(200)
    )
)

DEFAULT_OUT_TOKENS = 64
DEFAULT_COUNT_PER_LEVEL = 16
DEFAULT_LEVELS = "1,2,4,8"
DEFAULT_WORKLOAD_KIND = "micro"
# agent-like default: typical final-answer budget and a realistic long context.
DEFAULT_AGENT_OUT_TOKENS = 256
DEFAULT_PREFIX_TOKENS = 2048
APPROX_CHARS_PER_TOKEN = 4

# --- agent-like long prefix: real, coherent technical prose -------------------
# Built from meaningful paragraphs (not filler tokens), assembled deterministically
# to approximately --prefix-tokens characters. The same immutable prefix is used
# for every request in a level so the radix cache can be reused exactly as it
# would be for an agent replaying a long shared system/context block.
AGENT_PREFIX_PARAGRAPHS = (
    "A serving system for large language models separates the request lifecycle "
    "into queueing, prompt processing, and autoregressive decoding. Queueing covers "
    "the interval between the arrival of a request and its admission into a running "
    "batch. Prompt processing, also called prefill, evaluates the entire input "
    "context and materializes the key and value tensors that later decoding steps "
    "reuse. Decoding then emits one token at a time, and each emitted token extends "
    "the context that the next step attends over. Because prefill and decode have "
    "different compute and memory profiles, schedulers must balance them carefully: "
    "long prefills raise time to first token, while large decode batches raise "
    "per-token latency.",
    "Prefix caching exploits the observation that many requests share an identical "
    "leading token sequence, such as a system instruction, a tool schema, retrieved "
    "documents, or prior conversation turns. When that shared prefix is already "
    "resident in the key-value cache, the server can skip recomputation and restore "
    "the corresponding state instead. The effective prompt length is therefore the "
    "total prompt minus the cached prefix, and only the newly prefilled remainder "
    "consumes fresh compute. Reporting cache hit rate without also reporting the "
    "newly prefilled token count makes latency comparisons ambiguous, because a "
    "warm request and a cold request with the same nominal prompt can differ by an "
    "order of magnitude in prefill cost.",
    "Hierarchical caching extends the same idea across memory tiers. The first tier "
    "is device memory holding the live radix tree. The second tier stores evicted "
    "state in host memory, and the third tier persists it on local storage. A cache "
    "hit can therefore be served from any tier, and the restore latency grows as "
    "the state moves further from the accelerator. Operators instrument each tier "
    "separately so that a regression in end-to-end latency can be attributed to a "
    "specific restore path rather than blamed generically on the cache. Eviction "
    "policy and write-back policy determine whether the cache helps or merely adds "
    "background traffic that competes with serving work.",
    "Quantization reduces weight and activation precision so that a model fits in a "
    "fixed memory budget. Weight-only quantization keeps activations in higher "
    "precision and dequantizes tiles on the fly, which usually preserves quality at "
    "the cost of extra compute per parameter. Activation quantization can use faster "
    "integer kernels but is more sensitive to outliers, so calibration quality "
    "matters. The choice interacts with batching: larger batches amortize weight "
    "reads but increase the working set, and kernel selection can change entirely at "
    "different batch sizes. Performance results are only comparable when the "
    "quantization scheme, the runtime kernels, and the batch shape are all held "
    "constant.",
    "Continuous batching keeps the accelerator busy by admitting new requests as "
    "soon as capacity frees up, rather than waiting for an entire batch to finish. "
    "This improves aggregate throughput but makes per-request latency sensitive to "
    "the composition of the batch. A scheduler may also retract a running request "
    "when memory pressure rises, returning its state to a waiting queue; the "
    "resulting recomputation shows up as latency spikes. Measuring only average "
    "throughput hides these tail effects, which is why percentile latencies and "
    "queue times are reported alongside throughput in any honest evaluation.",
    "Speculative decoding trades extra compute for fewer sequential steps. A small "
    "draft model proposes several tokens, and the target model verifies them in a "
    "single forward pass, accepting the longest matching prefix. The speedup depends "
    "on the acceptance rate, which in turn depends on how well the draft model "
    "approximates the target distribution. When acceptance is high the target model "
    "advances several positions per step; when it is low the draft work is wasted. "
    "Evaluation must therefore report acceptance rate and the resulting tokens per "
    "step, not merely wall-clock speedup on a single favorable prompt.",
    "Reasoning models emit an internal thinking stream before their final answer. "
    "The thinking tokens are model output and arrive first, but they are not the "
    "answer the user is waiting for. If a client measures time to first token by "
    "looking only for final-answer content, it silently measures time to first "
    "content and conflates it with responsiveness. The correct instrumentation "
    "records the arrival of any output delta as the basic time to first token, and "
    "separately records the arrival of the first final-answer delta as time to first "
    "content. The gap between the two is a direct measure of how much the thinking "
    "phase delays the visible answer.",
    "Reproducibility requires freezing every knob that can move a performance "
    "number. Model identity and revision, server command-line arguments, sampling "
    "temperature, output budget, end-of-sequence handling, reasoning policy, cache "
    "state, prompt corpus, and request count all belong in a manifest that travels "
    "with the results. Without that manifest, two runs that look identical can "
    "differ because one used a warm cache and the other a cold one, or because one "
    "let the model stop naturally while the other forced a fixed token count. A "
    "result file that omits these fields cannot be compared across roles, and any "
    "conclusion drawn from it is provisional at best.",
)

# Resolved at runtime from CLI args (kept module-level so _blocking can read them,
# mirroring the F39/RCA global URL/MODEL pattern).
URL = DEFAULT_URL
MODEL = DEFAULT_MODEL


def build_agent_prefix(target_tokens: int) -> str:
    """Build a realistic long prefix (~target_tokens*4 chars) from real prose.

    Repeats the paragraph corpus deterministically until the requested approximate
    token budget is reached, then trims at a sentence boundary so the text stays
    coherent. No placeholder/filler tokens are used.
    """
    target_chars = max(1, int(target_tokens)) * APPROX_CHARS_PER_TOKEN
    parts = []
    total = 0
    i = 0
    while total < target_chars:
        para = AGENT_PREFIX_PARAGRAPHS[i % len(AGENT_PREFIX_PARAGRAPHS)]
        parts.append(para)
        total += len(para) + 1
        i += 1
    text = " ".join(parts)
    if len(text) > target_chars:
        cut = text.rfind(". ", 0, target_chars)
        text = text[: cut + 1] if cut > target_chars // 2 else text[:target_chars]
    return text


def distinct_body(idx: int) -> str:
    """Same length as BODY but unique per idx -> genuinely cold (no radix reuse)."""
    return (
        f"The following is a unique fixed-length passage for request {idx}. "
        + " ".join(
            f"Line {idx:03d}-{i:04d}: parameter {i} for request {idx} controls subsystem "
            f"{(i + idx) % 17} and must be recorded once."
            for i in range(150)
        )
    )


def _reasoning_fields(reasoning_effort, thinking) -> dict:
    """Request-side reasoning/thinking policy (C2).

    ``reasoning_effort`` is sent verbatim when provided; ``thinking`` maps to
    ``chat_template_kwargs.enable_thinking``/``thinking``. Nothing is sent when
    both are None, matching the legacy request shape.
    """
    fields: dict = {}
    if reasoning_effort is not None:
        fields["reasoning_effort"] = reasoning_effort
    ctk = {}
    if thinking is not None:
        on = thinking == "on"
        ctk["enable_thinking"] = on
        ctk["thinking"] = on
    if ctk:
        fields["chat_template_kwargs"] = ctk
    return fields


def payload(
    prompt: str,
    shared: bool,
    idx: int,
    out_tokens: int,
    *,
    workload_kind: str = DEFAULT_WORKLOAD_KIND,
    ignore_eos: bool = True,
    reasoning_effort=None,
    thinking=None,
    seed=None,
    max_tokens_total=None,
    thinking_budget=None,
) -> dict:
    if workload_kind == "agent-like":
        # Long real prefix + a realistic instruction; the prefix is byte-identical
        # across requests so cache reuse behavior is meaningful.
        msgs = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "Read the reference material above and summarize the key "
                    "operational trade-offs in a short technical note."
                ),
            },
        ]
    elif shared:
        msgs = [
            {"role": "system", "content": SHARED_PREFIX},
            {"role": "user", "content": "Reply with the single word ACK."},
        ]
    else:
        # Unique prefix each index (no shared prefix), same length.
        msgs = [
            {"role": "system", "content": distinct_body(idx)},
            {"role": "user", "content": f"Request {idx}. Reply with the single word ACK."},
        ]
    # B: the wire cap is the single SGLang total (reasoning + final answer). The
    # final-answer allowance is ``out_tokens`` and is exposed separately in the
    # manifest; the model cannot spend more than ``max_tokens_total`` overall.
    wire_cap = max_tokens_total if max_tokens_total is not None else out_tokens
    p = {
        "model": MODEL,
        "messages": msgs,
        "max_tokens": wire_cap,
        "temperature": 0.0,
        "ignore_eos": ignore_eos,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if workload_kind != "agent-like":
        # Legacy micro protocol pins thinking off via chat_template_kwargs.
        p["chat_template_kwargs"] = {"enable_thinking": False}
    p.update(_reasoning_fields(reasoning_effort, thinking))
    # B: thinking budget rides the existing custom_params channel read by
    # grammar_manager.py:117-129 and custom_logit_processor.py:85.
    if thinking_budget is not None:
        p["custom_params"] = {"thinking_budget": thinking_budget}
    if seed is not None:
        p["seed"] = seed
    return p


# --- R2 amendment A: what counts as "model output" --------------------------
#: Prefix for Responses-style lifecycle event ``type`` values. Covers
#: ``response.created``, ``response.in_progress``, and any other ``response.*``
#: lifecycle frame emitted before/around model output.
LIFECYCLE_EVENT_PREFIX = "response."
#: Named SSE control/keepalive frames that are not model output.
LIFECYCLE_EVENT_NAMES = frozenset(
    {"ping", "pong", "keepalive", "heartbeat", "done"}
)


def is_lifecycle_event_name(name: str) -> bool:
    """True when an SSE ``event:`` name is a lifecycle/control frame."""
    if not name:
        return False
    return name.startswith(LIFECYCLE_EVENT_PREFIX) or name in LIFECYCLE_EVENT_NAMES


def is_lifecycle_event(obj: dict) -> bool:
    """True for a lifecycle/control SSE object that is NOT model output.

    Covers Responses-style lifecycle payloads (top-level ``type`` beginning with
    ``response.``), named keepalive/heartbeat ``event`` fields, and any frame
    that carries no ``choices`` list at all. The latter includes usage-only
    chunks (``include_usage``), which never start the clock.
    """
    etype = obj.get("type")
    if isinstance(etype, str) and is_lifecycle_event_name(etype):
        return True
    if is_lifecycle_event_name(obj.get("event") or ""):
        return True
    if not obj.get("choices"):
        return True
    return False


def is_model_output_delta(delta: dict) -> bool:
    """Whether ``delta`` carries genuine model output (R2 amendment A).

    **COUNTED** (any non-empty):
      * ``reasoning_content`` or ``reasoning`` (thinking stream)
      * ``content`` (final-answer stream)
      * ``tool_calls``

    **EXCLUDED** (returns ``False``):
      * empty delta ``{}``
      * role-only delta, e.g. the first assistant chunk ``{"role": "assistant",
        "content": ""}``
      * ``[DONE]``, usage-only chunks, and lifecycle frames are filtered before
        this call and never reach it as a delta.

    ``first_content_s`` (TTFC) uses ``delta.get("content")`` directly and MUST
    NOT count reasoning.
    """
    if not delta:
        return False
    if delta.get("content"):
        return True
    if delta.get("reasoning_content") or delta.get("reasoning"):
        return True
    if delta.get("tool_calls"):
        return True
    return False


def parse_stream_chunk(obj: dict, t0: float, state: dict) -> None:
    """Accumulate one parsed SSE JSON object into ``state`` (C1 split, R2 A).

    ``state`` keys populated:
      * ``first_output_s``  - arrival of the first GENUINE model output delta
                              (``is_model_output_delta``: content, reasoning, or
                              tool_calls), the basic-performance TTFT.
      * ``first_content_s`` - arrival of the first final-answer content delta
                              (TTFC). Stays None for reasoning-only streams.
      * ``ttft_s``          - legacy alias of ``first_content_s`` (back-compat).
      * ``text`` / ``usage`` / ``finish_reason``.
    """
    if obj.get("usage"):
        state["usage"] = obj["usage"]
    if is_lifecycle_event(obj):
        return
    for ch in obj.get("choices") or []:
        d = ch.get("delta") or {}
        # finish_reason is captured regardless of whether this delta is output.
        if ch.get("finish_reason"):
            state["finish_reason"] = ch["finish_reason"]
        if not is_model_output_delta(d):
            # Empty/role-only/usage delimiter delta: does NOT start the clock.
            continue
        # One arrival instant per delta: a first delta that is both output and
        # content yields identical first_output_s and first_content_s.
        now = time.time() - t0
        if state.get("first_output_s") is None:
            state["first_output_s"] = now
        has_content = bool(d.get("content"))
        if has_content and state.get("first_content_s") is None:
            state["first_content_s"] = now
            # legacy field is defined as first-content for backward compat
            state["ttft_s"] = now
        if has_content:
            state["text"].append(d["content"])


def parse_stream_lines(lines, t0: float) -> dict:
    """Parse an iterable of raw SSE lines into a per-request result dict.

    Factored out of ``_blocking`` so synthetic SSE streams can be fed directly in
    offline tests (no server, no network). Accepts ``bytes`` or ``str`` lines.
    An explicit ``event:`` lifecycle/keepalive name suppresses its ``data:``
    payload (R2 amendment A).
    """
    state = {
        "first_output_s": None,
        "first_content_s": None,
        "ttft_s": None,
        "text": [],
        "usage": None,
        "finish_reason": None,
    }
    event_name = None
    for raw in lines:
        line = raw.decode() if isinstance(raw, bytes) else raw
        stripped = line.strip()
        if not stripped:
            event_name = None  # blank line terminates an SSE event block
            continue
        if stripped.startswith("event:"):
            event_name = stripped[6:].strip()
            continue
        if not stripped.startswith("data:"):
            continue
        chunk = stripped[5:].strip()
        if chunk == "[DONE]":
            break
        if is_lifecycle_event_name(event_name or ""):
            event_name = None
            continue
        event_name = None
        try:
            obj = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        parse_stream_chunk(obj, t0, state)
    dur = time.time() - t0
    u = state["usage"] or {}
    return {
        "ok": True,
        "ttft_s": state["ttft_s"],
        "first_output_s": state["first_output_s"],
        # ms alias required by the dispatch; seconds remain authoritative.
        "first_output_ms": (
            None if state["first_output_s"] is None else state["first_output_s"] * 1000
        ),
        "first_content_s": state["first_content_s"],
        "dur_s": dur,
        "prompt_tokens": u.get("prompt_tokens"),
        "completion_tokens": u.get("completion_tokens"),
        # Reasoning tokens are reported by the usage payload when available.
        "reasoning_tokens": u.get("reasoning_tokens"),
        "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens"),
        "finish_reason": state["finish_reason"],
        "content_len": len("".join(state["text"])),
    }


def _blocking(p: dict) -> dict:
    data = json.dumps(p).encode()
    req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return parse_stream_lines(r, t0)
    except Exception as e:
        # fail closed: a connection/protocol error is recorded as n_err, never
        # silently retried and never allowed to hang the sweep.
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "dur_s": time.time() - t0}


def flush_url_for(url: str) -> str:
    """Derive the /flush_cache endpoint from the chat completions URL."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/flush_cache", "", ""))


def flush_cache(url: str) -> None:
    """POST /flush_cache (M2-RCA control). Never aborts the sweep on failure."""
    target = flush_url_for(url)
    try:
        req = urllib.request.Request(target, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode(errors="replace").strip()
        print(f"[flush_cache] {body}", flush=True)
        time.sleep(1.0)
    except Exception as e:
        print(f"[flush_cache] ERROR {type(e).__name__}: {e}", flush=True)


def stream_one(p: dict, sem: asyncio.Semaphore) -> "asyncio.Future":
    async def run():
        async with sem:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _blocking, p)
    return run()


async def run_level(
    conc: int,
    count: int,
    shared: bool,
    warm: bool,
    out_tokens: int,
    *,
    workload_kind: str = DEFAULT_WORKLOAD_KIND,
    ignore_eos: bool = True,
    reasoning_effort=None,
    thinking=None,
    prefix_text: str | None = None,
    seed=None,
    max_tokens_total=None,
    thinking_budget=None,
) -> list[dict]:
    sem = asyncio.Semaphore(conc)

    def make(i: int) -> dict:
        if workload_kind == "agent-like":
            # Same real long prefix for every request (agent-style shared context).
            return payload(
                prefix_text or SHARED_PREFIX, True, i, out_tokens,
                workload_kind=workload_kind, ignore_eos=ignore_eos,
                reasoning_effort=reasoning_effort, thinking=thinking, seed=seed,
                max_tokens_total=max_tokens_total, thinking_budget=thinking_budget,
            )
        return payload(
            SHARED_PREFIX if shared else BODY, shared, i, out_tokens,
            workload_kind=workload_kind, ignore_eos=ignore_eos,
            reasoning_effort=reasoning_effort, thinking=thinking, seed=seed,
            max_tokens_total=max_tokens_total, thinking_budget=thinking_budget,
        )

    if warm and shared:
        # single warmup to populate the prefix cache before the measured batch
        await asyncio.get_event_loop().run_in_executor(None, _blocking, make(0))
    tasks = [
        asyncio.create_task(stream_one(make(i), sem))
        for i in range(count)
    ]
    return await asyncio.gather(*tasks)


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def summarize(
    rows,
    label,
    *,
    cache_state=None,
    workload_kind=DEFAULT_WORKLOAD_KIND,
    prompt_chars=None,
):
    ok = [r for r in rows if r.get("ok")]
    # Legacy TTFT percentiles: first CONTENT delta (= TTFC) for backward compat.
    ttfts = [r["ttft_s"] for r in ok if r["ttft_s"] is not None]
    # C1: basic-performance TTFT = ANY model output delta (content or reasoning).
    ttft_out = [r["first_output_s"] for r in ok if r.get("first_output_s") is not None]
    # C1: TTFC = first final-answer content delta.
    ttfc = [r["first_content_s"] for r in ok if r.get("first_content_s") is not None]
    durs = [r["dur_s"] for r in ok]
    out = sum(r["completion_tokens"] or 0 for r in ok)
    dec = [(r["completion_tokens"] or 0) / (r["dur_s"] - r["ttft_s"]) for r in ok
           if r["ttft_s"] is not None and (r["dur_s"] - r["ttft_s"]) > 0]
    cached = [r["cached_tokens"] or 0 for r in ok]
    # C4: cache accounting is a first-class result, not inferred from --flush.
    prompts = [r["prompt_tokens"] or 0 for r in ok]
    newly = [p - c for p, c in zip(prompts, cached)]
    hit_ratios = [c / p for p, c in zip(prompts, cached) if p > 0]
    # R2 B: detect budget exhaustion. length-finish with no final content means
    # the entire allowance was spent in reasoning; length-finish with content
    # means the final answer itself was cut off.
    n_reasoning_only = sum(
        1
        for r in ok
        if r.get("finish_reason") == "length" and (r.get("content_len") or 0) == 0
    )
    n_truncated = sum(
        1
        for r in ok
        if r.get("finish_reason") == "length" and (r.get("content_len") or 0) > 0
    )
    warning = None
    if n_reasoning_only or n_truncated:
        warning = (
            f"BUDGET EXHAUSTION: {n_reasoning_only} reasoning-only (no final "
            f"content) + {n_truncated} truncated final answer at '{label}'; the "
            "generated output was capped by max_tokens_total, not natural EOS. "
            "Results at this level are NOT a valid final-answer measurement."
        )
    return {
        # --- legacy fields (unchanged names; ttft_* == first-content == TTFC) --
        "label": label,
        "n_ok": len(ok),
        "n_err": len(rows) - len(ok),
        "ttft_p50": round(pct(ttfts, .5), 3) if ttfts else None,
        "ttft_p90": round(pct(ttfts, .9), 3) if ttfts else None,
        "ttft_p95": round(pct(ttfts, .95), 3) if ttfts else None,
        "dur_p50": round(pct(durs, .5), 3) if durs else None,
        "dur_p90": round(pct(durs, .9), 3) if durs else None,
        "dur_p95": round(pct(durs, .95), 3) if durs else None,
        "decode_tps_p50": round(pct(dec, .5), 2) if dec else None,
        "decode_tps_p90": round(pct(dec, .9), 2) if dec else None,
        "aggregate_tps": round(out / max(durs) if durs else 0, 2),
        "total_out_tokens": out,
        "cached_tokens_nonzero": sum(1 for c in cached if c > 0),
        "cached_tokens_max": max(cached) if cached else 0,
        "cached_tokens_mean": round(statistics.mean(cached), 1) if cached else 0,
        # --- C1: split TTFT/TTFC ------------------------------------------
        "ttft_output_p50": round(pct(ttft_out, .5), 3) if ttft_out else None,
        "ttft_output_p90": round(pct(ttft_out, .9), 3) if ttft_out else None,
        "ttft_output_p95": round(pct(ttft_out, .95), 3) if ttft_out else None,
        "ttfc_p50": round(pct(ttfc, .5), 3) if ttfc else None,
        "ttfc_p90": round(pct(ttfc, .9), 3) if ttfc else None,
        "ttfc_p95": round(pct(ttfc, .95), 3) if ttfc else None,
        # number of ok requests that produced a final-answer content delta;
        # reasoning-only requests are excluded from the TTFC percentiles.
        "n_ttfc": len(ttfc),
        # --- C4: cache state as a result field ----------------------------
        "prompt_tokens_p50": round(pct(prompts, .5), 1) if prompts else None,
        "cached_tokens_p50": round(pct(cached, .5), 1) if cached else None,
        "newly_prefilled_tokens_p50": round(pct(newly, .5), 1) if newly else None,
        "hit_rate_mean": round(statistics.mean(hit_ratios), 4) if hit_ratios else None,
        "cache_state": cache_state,
        "workload_kind": workload_kind,
        "prompt_chars": prompt_chars,
        # --- R2 B: budget-exhaustion counters + prominent warning ----------
        "n_reasoning_only": n_reasoning_only,
        "n_truncated": n_truncated,
        "warning": warning,
    }


CASES = {
    "distinct": (False, False, "distinct-noreuse"),
    "shared": (True, True, "shared-prefix-reuse"),
}


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Durable concurrency efficiency sweep (F39/M2-RCA protocol)."
    )
    ap.add_argument("--url", default=DEFAULT_URL, help="chat completions endpoint")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="model identifier / path sent to the server")
    ap.add_argument("--tag", default="m2", help="run tag (default drives --outfile)")
    ap.add_argument("--outfile", default=None, help="output JSON path (default efficiency-<tag>.json)")
    ap.add_argument("--levels", default=DEFAULT_LEVELS, help="comma-separated concurrency levels")
    ap.add_argument("--count-per-level", type=int, default=DEFAULT_COUNT_PER_LEVEL, help="requests per level")
    ap.add_argument("--out-tokens", type=int, default=None,
                    help="max_tokens per request (micro default 64; agent-like default 256, "
                         "typical 256/512)")
    ap.add_argument("--mode", choices=["shared", "distinct", "both"], default="both",
                    help="which case(s) to run (default: both)")
    # --- C3: workload kind -------------------------------------------------
    ap.add_argument("--workload-kind", choices=["micro", "agent-like"], default=DEFAULT_WORKLOAD_KIND,
                    help="micro = 64-token/ignore_eos microbenchmark (default, legacy); "
                         "agent-like = long real prefix + normal EOS + typical output tokens")
    ap.add_argument("--prefix-tokens", type=int, default=DEFAULT_PREFIX_TOKENS,
                    help="agent-like approximate prefix tokens (built from real prose)")
    # --- C2: reasoning / thinking policy ----------------------------------
    ap.add_argument("--reasoning-effort", default=None,
                    help="reasoning_effort sent per request (e.g. none|low|medium|high); "
                         "recorded in manifest. Empty = not sent.")
    ap.add_argument("--thinking", choices=["on", "off"], default=None,
                    help="thinking policy sent per request; recorded in manifest. "
                         "Empty = not sent (legacy shape).")
    # --- R2 B: thinking budget separated from final-answer allowance -------
    ap.add_argument("--thinking-budget", type=int, default=None,
                    help="reasoning/thinking token budget sent via custom_params "
                         "(server read: grammar_manager.py:117-129, "
                         "custom_logit_processor.py:85). Separate from the "
                         "final-answer allowance --out-tokens. Default None = "
                         "server policy (no per-request budget).")
    ap.add_argument("--max-tokens-total", type=int, default=None,
                    help="single wire cap (max_tokens) for reasoning + final answer; "
                         "SGLang has one total cap. Default = --out-tokens. For "
                         "agent-like, must be >= thinking_budget + out_tokens or the "
                         "run fails closed before any request.")
    # --- C4: cache state ---------------------------------------------------
    ap.add_argument("--cache-state", choices=["cold-distinct", "warm-shared", "warm-distinct"],
                    default=None,
                    help="explicit cache state label written to each level and the manifest; "
                         "--flush does NOT imply cold")
    ap.add_argument("--flush", action=argparse.BooleanOptionalAction, default=False,
                    help="POST /flush_cache before each distinct level (mechanism only; "
                         "does not by itself define cold/warm - use --cache-state)")
    ap.add_argument("--max-running-requests", type=int, default=8,
                    help="recorded in output config only (not used to drive load)")
    ap.add_argument("--server-argv", default=None,
                    help="server argv string recorded in output config for provenance")
    ap.add_argument("--seed", type=int, default=None,
                    help="optional sampling seed recorded in manifest (not sent unless given)")
    ap.add_argument("--self-check", metavar="REFERENCE_JSON", default=None,
                    help="validate that this harness's output schema matches an existing "
                         "efficiency JSON (e.g. efficiency-m2.json) and exit")
    return ap.parse_args(argv)


# Legacy fields emitted per level, in order, matching efficiency-{m1,m2}.json summaries.
LEGACY_LEVEL_FIELDS = [
    "label", "n_ok", "n_err", "ttft_p50", "ttft_p90", "ttft_p95",
    "dur_p50", "dur_p90", "dur_p95", "decode_tps_p50", "decode_tps_p90",
    "aggregate_tps", "total_out_tokens", "cached_tokens_nonzero",
    "cached_tokens_max", "cached_tokens_mean", "concurrency", "case", "wall_s",
]
# Additive C1/C3/C4 fields appended after the legacy 19.
NEW_LEVEL_FIELDS = [
    "ttft_output_p50", "ttft_output_p90", "ttft_output_p95",
    "ttfc_p50", "ttfc_p90", "ttfc_p95", "n_ttfc",
    "prompt_tokens_p50", "cached_tokens_p50", "newly_prefilled_tokens_p50",
    "hit_rate_mean", "cache_state", "workload_kind", "prompt_chars",
]
# Additive R2 amendment B fields appended after C1/C3/C4.
R2_LEVEL_FIELDS = [
    "n_reasoning_only", "n_truncated", "warning",
]
LEVEL_FIELDS = LEGACY_LEVEL_FIELDS + NEW_LEVEL_FIELDS + R2_LEVEL_FIELDS
# Level schema emitted by the first amendment (C1-C4): accepted for backward
# compatibility so an R1 output still passes --self-check.
R1_LEVEL_FIELDS = LEGACY_LEVEL_FIELDS + NEW_LEVEL_FIELDS
CONFIG_FIELDS = [
    "levels", "count_per_level", "out_tokens", "model", "max_running_requests",
    "server_argv", "endpoint",
]


def self_check(reference_path: str) -> int:
    """Compare our declared output schema against an existing efficiency JSON.

    Backward compatibility (required): a LEGACY reference carrying only the
    original 19 level fields MUST still pass, because every amendment is
    additive. An R1 (C1-C4) or R2 reference carrying the full superset also
    passes. Any level key set that is not a superset of the legacy 19 and a
    subset of the current LEVEL_FIELDS is a mismatch. Reference config keys must
    be a subset of ours. Read-only.
    """
    with open(reference_path) as fh:
        ref = json.load(fh)
    problems = []
    # Legacy output is {config, levels}; amended output adds the C2 manifest.
    allowed_top = ({"config", "levels"}, {"config", "levels", "manifest"})
    if set(ref.keys()) not in allowed_top:
        problems.append(
            f"top-level keys {sorted(ref.keys())} not in "
            f"{[sorted(s) for s in allowed_top]}"
        )
    missing_config = [k for k in CONFIG_FIELDS if k not in ref.get("config", {})]
    if missing_config:
        problems.append(f"reference config missing expected keys: {missing_config}")
    if not isinstance(ref.get("levels"), list) or not ref["levels"]:
        problems.append("reference 'levels' is not a non-empty list")
    else:
        legacy = set(LEGACY_LEVEL_FIELDS)
        full = set(LEVEL_FIELDS)
        for i, lvl in enumerate(ref["levels"]):
            keys = set(lvl.keys())
            # legacy ⊆ keys ⊆ full; accepts legacy 19, R1 33, and R2 36.
            if not (legacy <= keys <= full):
                problems.append(
                    f"level[{i}] keys {sorted(keys)} is not a superset of "
                    f"legacy {sorted(legacy)} / subset of amended {sorted(full)}"
                )
    if problems:
        print(f"SCHEMA MISMATCH vs {reference_path}:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    keys0 = set(ref["levels"][0].keys())
    if keys0 == set(LEGACY_LEVEL_FIELDS):
        kind = "legacy 19-field"
    elif keys0 == set(R1_LEVEL_FIELDS):
        kind = f"R1 {len(R1_LEVEL_FIELDS)}-field"
    else:
        kind = f"R2 {len(LEVEL_FIELDS)}-field"
    print(f"SCHEMA OK: {reference_path} config keys subset of harness, "
          f"{len(ref['levels'])} levels carry all {kind} expected fields")
    return 0


def resolve_cache_state(args, case: str) -> str:
    """C4: explicit cache-state label.

    If the operator passed --cache-state it is used verbatim (it is a claim about
    the server's state that only the operator can make). Otherwise it is derived
    from the case/labels without conflating --flush with coldness: distinct ->
    cold-distinct, shared -> warm-shared. --flush never appears as a state.
    """
    if args.cache_state:
        return args.cache_state
    return "warm-shared" if case == "shared" else "cold-distinct"


# --- R2 B: effective reasoning/thinking policy, with provenance --------------
# Server references the manifest cites by file:line. Keep in sync with the tree.
POLICY_SERVER_REFS = [
    "serving_chat.py:1010-1030 (_plan_qwen35_budget wiring / custom_params)",
    "serving_chat.py:1137-1147 (_apply_qwen35_policy_to_request)",
    "serving_chat.py:1274 (_merge_qwen35_steering into system turn)",
    "serving_chat.py:2568 (_resolve_qwen35_policy)",
    "serving_chat.py:2653-2695 (_plan_qwen35_budget: strict vs processor route)",
    "parser/qwen35_reasoning_policy.py:86-122 (provisional tier ladder)",
    "parser/qwen35_reasoning_policy.py:209-256 (resolve_qwen35_reasoning_policy)",
    "sampling/custom_logit_processor.py:85,107,118 (thinking_budget enforcement)",
    "sampling/custom_logit_processor.py:148-149 (Qwen3.5 <think>/</think> token ids)",
    "constrained/grammar_manager.py:117-129 (custom_params thinking_budget -> "
    "ReasonerGrammarObject.max_think_tokens)",
    "protocol.py:855 (max_tokens, deprecated) / :860-863 "
    "(max_completion_tokens includes reasoning+visible) / :937 (custom_params)",
]


def _load_qwen35_policy_module():
    """Best-effort load of the server policy module WITHOUT the sglang package.

    The running server owns the authoritative policy; this client-side load is
    only to annotate the manifest with the resolved tier budget. Importing
    through ``sglang`` requires numpy (absent on the harness host), so load the
    single file directly. Returns ``None`` on any failure; callers then record
    ``effective_source=unknown`` and never invent a number.
    """
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))),
        "python", "sglang", "srt", "parser", "qwen35_reasoning_policy.py",
    )
    try:
        spec = importlib.util.spec_from_file_location(
            "_perf_qwen35_reasoning_policy", path
        )
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        # dataclass() looks the module up in sys.modules during exec.
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None
    finally:
        # Do not leak a private module entry.
        sys.modules.pop("_perf_qwen35_reasoning_policy", None)


def resolve_effective_policy(args) -> dict:
    """Freeze the reasoning/thinking policy actually requested (R2 B).

    ``effective_source`` is ``assumed`` when the request shape plus the
    client-side policy module let us name the resolved tier budget, and
    ``unknown`` when the server's resolved policy cannot be observed from the
    client (module unavailable, non-Qwen3.5 model, or no effort requested).
    """
    policy_mod = None
    resolved = None
    if args.workload_kind == "agent-like" or args.reasoning_effort is not None:
        policy_mod = _load_qwen35_policy_module()
    if policy_mod is not None and args.reasoning_effort is not None:
        try:
            resolved = policy_mod.resolve_qwen35_reasoning_policy(
                model_type="qwen3_5",  # narrow family; server re-checks
                reasoning_config=types.SimpleNamespace(
                    toggle_param="enable_thinking"
                ),
                effort=args.reasoning_effort,
            )
        except Exception:
            resolved = None
    tier = getattr(resolved, "tier", None) if resolved is not None else None
    ladder_budget = (
        getattr(resolved, "max_thinking_tokens", None)
        if resolved is not None
        else None
    )
    enable_thinking = args.thinking if args.thinking is not None else None
    if args.thinking is None and getattr(resolved, "enable_thinking", None) is not None:
        enable_thinking = resolved.enable_thinking
    ladder = None
    if policy_mod is not None:
        try:
            ladder = dict(policy_mod.DEFAULT_QWEN35_EFFORT_POLICY)
        except Exception:
            ladder = None
    return {
        "reasoning_effort": args.reasoning_effort,
        "thinking": args.thinking,
        "thinking_budget": args.thinking_budget,
        "max_output_tokens": args.out_tokens,
        "max_tokens_total": (
            args.max_tokens_total
            if args.max_tokens_total is not None
            else args.out_tokens
        ),
        # SGLang exposes a SINGLE total cap (reasoning + final answer); be honest
        # about the merged relationship rather than pretending they are separate
        # on the wire.
        "max_tokens_total_relation": (
            "single SGLang cap covering reasoning + final answer "
            "(protocol.py:860-863); max_output_tokens is the final-answer "
            "allowance carved out of it"
        ),
        "resolved_tier": tier,
        "resolved_budget_from_ladder": ladder_budget,
        "enable_thinking": enable_thinking,
        "steering_applied": bool(getattr(resolved, "steering", "")) if resolved else None,
        "effort_policy_ladder": ladder,
        "server_refs": POLICY_SERVER_REFS,
        # Client cannot read the live server's resolved policy: when the module
        # or effort is unavailable this is an assumption, not an observation.
        "effective_source": "assumed" if tier is not None else "unknown",
    }


def build_manifest(args, levels, cases, agent_prefix) -> dict:
    explicit = args.cache_state
    per_case = {case: resolve_cache_state(args, case) for case in cases}
    effective = resolve_effective_policy(args)
    return {
        "model": MODEL,
        "server_argv": args.server_argv,
        "reasoning_effort": args.reasoning_effort,
        "thinking": args.thinking,
        # Legacy key: retained verbatim as the final-answer allowance (R1
        # consumers read it). The wire cap is max_tokens_total below.
        "max_tokens": args.out_tokens,
        # --- R2 B: explicit budget separation -----------------------------
        "thinking_budget": args.thinking_budget,
        "max_output_tokens": args.out_tokens,
        "max_tokens_total": effective["max_tokens_total"],
        "max_tokens_total_relation": effective["max_tokens_total_relation"],
        # --- R2 B: frozen effective policy + provenance -------------------
        "effective_policy": effective,
        "effective_source": effective["effective_source"],
        "ignore_eos": (args.workload_kind == "micro"),
        "mode": args.mode,
        "levels": levels,
        "count_per_level": args.count_per_level,
        "prompt_chars": len(agent_prefix) if agent_prefix is not None else None,
        "seed": args.seed,
        "workload_kind": args.workload_kind,
        # Explicit operator claim if given; otherwise the first case's resolution.
        # Per-case/per-level values live in each level result and cache_states.
        "cache_state": explicit if explicit else per_case[cases[0]],
        "cache_states": per_case,
        "url": URL,
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "max_running_requests": args.max_running_requests,
        "flush_before_each_distinct_level": args.flush,
        "prefix_tokens": args.prefix_tokens if args.workload_kind == "agent-like" else None,
        "ttft_field_semantics": (
            "ttft_* = TTFC (first final-answer content delta) for backward "
            "compatibility; ttft_output_* = basic-performance TTFT (first "
            "GENUINE model output delta per is_model_output_delta(): content / "
            "reasoning_content / tool_calls; lifecycle SSE, empty/role-only/"
            "usage-only deltas and [DONE] do NOT count); "
            "first_output_s/first_output_ms = same basic TTFT; ttfc_* = TTFC."
        ),
        "workload_kind_note": (
            "micro = 64-token/ignore_eos microbenchmark, NOT representative of "
            "agent performance; agent-like = long real prefix, normal EOS, typical "
            "256/512 output tokens."
        ),
    }


async def main() -> int:
    global URL, MODEL
    args = parse_args()
    if args.self_check:
        return self_check(args.self_check)
    URL = args.url
    MODEL = args.model
    levels = [int(x) for x in str(args.levels).split(",") if x.strip() != ""]
    outfile = args.outfile or f"efficiency-{args.tag}.json"
    cases = ["distinct", "shared"] if args.mode == "both" else [args.mode]

    # C3: agent-like uses a real long prefix and normal EOS. micro keeps the
    # legacy 64-token/ignore_eos protocol (values unchanged unless overridden).
    if args.workload_kind == "agent-like":
        agent_prefix = build_agent_prefix(args.prefix_tokens)
        ignore_eos = False
        if args.out_tokens is None:
            args.out_tokens = DEFAULT_AGENT_OUT_TOKENS
    else:
        agent_prefix = None
        ignore_eos = True
        if args.out_tokens is None:
            args.out_tokens = DEFAULT_OUT_TOKENS  # legacy 64-token microbenchmark

    # R2 B: thinking budget is SEPARATE from the final-answer allowance. For
    # agent-like the single SGLang wire cap must cover both, otherwise the run
    # would silently truncate reasoning into the answer. Fail closed BEFORE any
    # request is issued (no network, no partial sweep).
    max_tokens_total = (
        args.max_tokens_total if args.max_tokens_total is not None else args.out_tokens
    )
    if args.thinking_budget is not None:
        if args.thinking_budget < 0:
            print(
                "FAIL-CLOSED: --thinking-budget must be >= 0 "
                f"(got {args.thinking_budget})",
                file=sys.stderr,
            )
            return 2
        if args.workload_kind == "agent-like":
            required = args.thinking_budget + args.out_tokens
            if max_tokens_total < required:
                print(
                    "FAIL-CLOSED: agent-like workload with --thinking-budget "
                    f"{args.thinking_budget} + --out-tokens {args.out_tokens} "
                    f"requires --max-tokens-total >= {required}, but got "
                    f"{max_tokens_total}. SGLang exposes a single total cap "
                    "(protocol.py:860-863), so a smaller cap silently truncates "
                    "the final answer. Refusing to run.",
                    file=sys.stderr,
                )
                return 2

    results = {
        "config": {
            "levels": levels,
            "count_per_level": args.count_per_level,
            "out_tokens": args.out_tokens,
            "max_tokens_total": max_tokens_total,
            "thinking_budget": args.thinking_budget,
            "model": MODEL,
            "tag": args.tag,
            "flush_before_each_distinct_level": args.flush,
            "max_running_requests": args.max_running_requests,
            "server_argv": args.server_argv,
            "endpoint": URL,
        },
        # C2: manifest is emitted per run (file + stdout) so cross-role comparison
        # can verify the workload is the same. Placed at the top of the JSON.
        "manifest": build_manifest(args, levels, cases, agent_prefix),
        "levels": [],
    }
    # Per-run manifest must be visible on stdout as well as on disk (C2).
    print("MANIFEST " + json.dumps(results["manifest"]), flush=True)
    for case in cases:
        shared, warm, label = CASES[case]
        cache_state = resolve_cache_state(args, case)
        for c in levels:
            if args.flush and not shared:
                await asyncio.get_event_loop().run_in_executor(None, flush_cache, URL)
            t0 = time.time()
            rows = await run_level(
                c, args.count_per_level, shared, warm, args.out_tokens,
                workload_kind=args.workload_kind, ignore_eos=ignore_eos,
                reasoning_effort=args.reasoning_effort, thinking=args.thinking,
                prefix_text=agent_prefix, seed=args.seed,
                max_tokens_total=max_tokens_total,
                thinking_budget=args.thinking_budget,
            )
            el = time.time() - t0
            s = summarize(
                rows, f"{label}-c{c}",
                cache_state=cache_state, workload_kind=args.workload_kind,
                prompt_chars=len(agent_prefix) if agent_prefix is not None else None,
            )
            s["concurrency"] = c
            s["case"] = label
            s["wall_s"] = round(el, 2)
            results["levels"].append(s)
            print(json.dumps(s), flush=True)
            # R2 B: surface budget exhaustion prominently, not only in JSON.
            if s.get("warning"):
                print(f"WARNING {s['warning']}", file=sys.stderr, flush=True)

    with open(outfile, "w") as fh:
        json.dump(results, fh, indent=2)
    print(f"\nWROTE {outfile}", file=sys.stderr)
    return 0 if all(s["n_err"] == 0 for s in results["levels"]) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
