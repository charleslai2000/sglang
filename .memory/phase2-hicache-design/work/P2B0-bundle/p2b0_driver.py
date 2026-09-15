#!/usr/bin/env python3
"""P2-B0 concurrent streaming workload driver (self-contained, raw urllib).

Contract: work/P2B0-EXECUTION-CONTRACT-20260912.md  (metrics/cells/seams)
Semantics: work/P2-B0-CONTRACT-20260911-R71.md      (scenario + idle split)

This is the P2-B0 *measurement vehicle*.  It only sends client traffic over the
public OpenAI-compatible HTTP API and records what the frozen P2-A timing probe
already emits server-side.  It uses **streaming** (`"stream": true`) so that the
first-token and last-token timestamps are real (R71 sec. 3.2: TTFT P95 must use a
real first-token timestamp), and captures the *full* ``usage`` object verbatim
plus any ``sglext.cached_tokens_details`` so the analyzer can classify scenarios.

Shape: each of ``--agents`` threads is one session with a distinct long history
(unique per-session rare-prefix marker -> independent radix branches).  Each
session runs ``--prime-turns`` cold/extend turns to populate L2/L3, then
``--measure-turns`` (or ``--measure-seconds``, whichever comes first) warm
re-sends of history + assistant + a small novel delta that should be
hit-dominated.  Phases are labelled ``prime`` / ``measure`` per row.

No product imports, no server control, no /flush_cache, no restart, no new
instrumentation, no GPU work.  ``--dry-run`` runs with NO server and NO GPU: it
synthesizes SSE bytes, drives the *real* streaming parser, verifies TTFT/TFTT
detection and row schema, writes synthetic ``join.jsonl``/``gpu.csv``/
``metrics.csv``/server-log window, and prints ``DRY_RUN_OK``.

Outputs (under ``--out-dir``):
  join.jsonl   one JSON row per request (schema below)
  gpu.csv      GPU timeline (sampler thread; shares mono_ns with metrics.csv)
  metrics.csv  server /metrics timeline (sampler thread)
  cell.json    args + driver/launch-script hashes + completion set + wall

join.jsonl row fields:
  schema, nonce, seq, agent, session, session_id, phase, turn, rid, http, rc,
  err, stream, send_mono_ns, first_token_mono_ns, last_token_mono_ns, ttft_s,
  tftt_s, elapsed_s, chunk_count, content_chunks, output_chars,
  output_tokens_est, finish_reason, usage (verbatim), sglext (verbatim),
  cached_tokens_details, prompt_tokens, completion_tokens, cached_tokens,
  hist_tokens_target, model, id, output_sha16.

Usage:
  python p2b0_driver.py --dry-run --agents 4
  python p2b0_driver.py --run --agents 4 --measure-seconds 300 --out-dir DIR
"""
import argparse
import hashlib
import io
import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    from p2b0_sampler import Sampler  # noqa: E402
except Exception:  # noqa: BLE001 - sampler is optional
    Sampler = None

WORK_DIR = os.path.dirname(HERE)
CONTRACT = os.path.join(WORK_DIR, "P2B0-EXECUTION-CONTRACT-20260912.md")
EXPECTED_LAUNCH_SHA = (
    "d24195b9a66c832226d8956ac6c79c168fbc92c4b67de44c0e1485847ab3c651"
)

BASE = os.environ.get("P2B0_BASE", "http://127.0.0.1:30000")
MODEL = os.environ.get("P2B0_MODEL", "/mnt/data/models/qwen35-gptq")
SERVER_LOG = os.environ.get(
    "P2B0_SERVER_LOG",
    "/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-e.log",
)
LAUNCH_SCRIPT = os.environ.get(
    "P2B0_LAUNCH_SCRIPT",
    "/mnt/data/neuron/sglang-3090-r112-20260911/launch-e-20260912.sh",
)
CELL_LAUNCHER = os.environ.get(
    "P2B0_CELL_LAUNCHER",
    "/mnt/data/neuron/sglang-3090-r112-20260911/launch-p2b0.sh",
)
OUT_ROOT = os.environ.get("P2B0_OUT", HERE)

WORD = "abcdefghijklmnopqrstuvwxyz"
TERMINAL_FAIL = (None, "", "error", "abort", "cancelled")


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def sha256_file(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:  # noqa: BLE001
        return None


def sha16(s):
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()[:16]


def line_count(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)
    except Exception:  # noqa: BLE001
        return None


def rw(rng):
    return "".join(rng.choice(WORD) for _ in range(rng.randint(4, 10)))


def rare_prefix(k):
    """Rare unicode marker making each session a distinct radix branch."""
    return "".join(chr(0x1F700 + ((k * 13 + j) % 0x60)) for j in range(4))


def make_text(seed, k, n_words):
    rng = random.Random(seed)
    parts = [rare_prefix(k)]
    parts += ["uniq" + rw(rng) for _ in range(max(1, n_words))]
    return " ".join(parts)


def make_fake_clock(start=1_000_000_000, step=1_000_000):
    state = {"t": int(start)}

    def clock():
        v = state["t"]
        state["t"] += int(step)
        return v
    return clock


# --------------------------------------------------------------------------
# request records + streaming SSE parser
# --------------------------------------------------------------------------
def new_rec(args, idx, session, phase, turn, seq, rid):
    return {
        "schema": "p2b0-request-1",
        "nonce": args.nonce,
        "seq": seq,
        "agent": idx,
        "session": session["label"],
        "session_id": session["session_id"],
        "phase": phase,
        "turn": turn,
        "rid": rid,
        "http": None,
        "rc": None,
        "err": None,
        "stream": True,
        "send_mono_ns": None,
        "first_token_mono_ns": None,
        "last_token_mono_ns": None,
        "ttft_s": None,
        "tftt_s": None,
        "elapsed_s": None,
        "chunk_count": 0,
        "content_chunks": 0,
        "output_chars": 0,
        "output_tokens_est": None,
        "finish_reason": None,
        "usage": None,
        "sglext": None,
        "cached_tokens_details": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "cached_tokens": None,
        "hist_tokens_target": args.hist_tokens,
        "model": args.model,
        "id": None,
        "output_sha16": None,
    }


def parse_sse(resp, rec, clock=time.monotonic_ns):
    """Parse an SSE byte stream.  Returns the concatenated output text.

    Records first/last token timestamps (on non-empty content chunks), chunk
    counts, finish_reason, the full usage object and any sglext /
    cached_tokens_details verbatim.
    """
    parts = []
    for raw_line in resp:
        try:
            line = raw_line.decode("utf-8", "replace").strip()
        except AttributeError:  # already str
            line = str(raw_line).strip()
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except Exception:  # noqa: BLE001 - ignore non-JSON keepalives
            continue
        if not isinstance(obj, dict):
            continue
        rec["chunk_count"] += 1
        if rec["id"] is None and obj.get("id") is not None:
            rec["id"] = obj.get("id")
        sg = obj.get("sglext")
        if isinstance(sg, dict):
            rec["sglext"] = sg
            if sg.get("cached_tokens_details") is not None:
                rec["cached_tokens_details"] = sg.get("cached_tokens_details")
        if obj.get("cached_tokens_details") is not None:
            rec["cached_tokens_details"] = obj.get("cached_tokens_details")
        if isinstance(obj.get("usage"), dict):
            rec["usage"] = obj.get("usage")
        for choice in (obj.get("choices") or []):
            if not isinstance(choice, dict):
                continue
            text = choice.get("text")
            if text:
                now = clock()
                if rec["first_token_mono_ns"] is None:
                    rec["first_token_mono_ns"] = now
                rec["last_token_mono_ns"] = now
                rec["content_chunks"] += 1
                rec["output_chars"] += len(text)
                parts.append(text)
            fr = choice.get("finish_reason")
            if fr:
                rec["finish_reason"] = fr
    return "".join(parts)


def finalize_rec(rec, send_ns, clock, out_text=""):
    rec["send_mono_ns"] = send_ns
    first = rec["first_token_mono_ns"]
    last = rec["last_token_mono_ns"]
    if first is not None:
        rec["ttft_s"] = round((first - send_ns) / 1e9, 6)
    if first is not None and last is not None:
        rec["tftt_s"] = round((last - first) / 1e9, 6)
    rec["elapsed_s"] = round((clock() - send_ns) / 1e9, 6)
    rec["output_tokens_est"] = rec["content_chunks"] or None
    rec["output_sha16"] = sha16(out_text) if out_text else None
    usage = rec.get("usage")
    if isinstance(usage, dict):
        rec["prompt_tokens"] = usage.get("prompt_tokens")
        rec["completion_tokens"] = usage.get("completion_tokens")
        ptd = usage.get("prompt_tokens_details")
        if isinstance(ptd, dict):
            rec["cached_tokens"] = ptd.get("cached_tokens")
        if rec["cached_tokens"] is None:
            rec["cached_tokens"] = usage.get("cached_tokens")
    http = rec.get("http")
    rec["rc"] = 0 if str(http) == "200" else (
        http if isinstance(http, int) else -1)
    return rec


def p2b0_rid(args, session, phase, turn):
    return "p2b0-%s-%s-%s-t%d" % (args.nonce, session["label"], phase, turn)


def build_sessions(args):
    sessions = []
    for i in range(max(1, args.agents)):
        words = max(1, int(args.hist_tokens / args.tok_per_word))
        sessions.append({
            "idx": i,
            "label": "s%d" % i,
            "session_id": "p2b0-sess-%s-%d" % (args.nonce, i),
            "hist_words": words,
            "hist_tokens_target": args.hist_tokens,
            "history": make_text(0x1000 + i * 7, i, words),
        })
    return sessions


def make_delta(args, idx, turn):
    return make_text(0x5000 + idx * 131 + turn, 1000 + idx * 16 + turn,
                     args.delta_words)


def run_one(args, rec, prompt, session_id):
    payload = {
        "model": args.model,
        "prompt": prompt,
        "max_tokens": args.max_tokens,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
        "return_cached_tokens_details": True,
        "session_id": session_id,
        "rid": rec["rid"],
    }
    body = json.dumps(payload).encode("utf-8")
    url = args.base.rstrip("/") + "/v1/completions"
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    send_ns = time.monotonic_ns()
    out = ""
    try:
        with urllib.request.urlopen(req, timeout=args.client_max_time) as resp:
            rec["http"] = resp.status
            out = parse_sse(resp, rec)
    except urllib.error.HTTPError as e:
        rec["http"] = e.code
        try:
            rec["err"] = e.read().decode("utf-8", "replace")[:1500]
        except Exception:  # noqa: BLE001
            rec["err"] = repr(e)[:400]
    except Exception as e:  # noqa: BLE001 - never raise out of a thread
        rec["http"] = "000"
        rec["err"] = repr(e)[:600]
    finalize_rec(rec, send_ns, time.monotonic_ns, out)
    rec["_out"] = out
    return rec


def completion_set(rows):
    total = len(rows)
    bad = sum(1 for r in rows if str(r.get("http")) != "200")
    completed = sum(
        1 for r in rows
        if str(r.get("http")) == "200"
        and r.get("finish_reason") not in TERMINAL_FAIL)
    reasons = {}
    for r in rows:
        key = r.get("finish_reason")
        key = "null" if key is None else str(key)
        reasons[key] = reasons.get(key, 0) + 1
    by_phase = {}
    for r in rows:
        ph = r.get("phase") or "unknown"
        by_phase.setdefault(ph, {"total": 0, "completed": 0, "bad_http": 0})
        by_phase[ph]["total"] += 1
        if str(r.get("http")) == "200" and r.get("finish_reason") not in TERMINAL_FAIL:
            by_phase[ph]["completed"] += 1
        if str(r.get("http")) != "200":
            by_phase[ph]["bad_http"] += 1
    return {
        "requests_total": total,
        "completed": completed,
        "bad_http": bad,
        "finish_reasons": reasons,
        "by_phase": by_phase,
    }


# --------------------------------------------------------------------------
# provenance / cell.json
# --------------------------------------------------------------------------
def launch_info(path, expected):
    info = {
        "path": path,
        "present": os.path.exists(path),
        "sha256": None,
        "expected_sha256": expected,
        "matches_contract": None,
    }
    if info["present"]:
        info["sha256"] = sha256_file(path)
        info["matches_contract"] = info["sha256"] == expected
    return info


def build_cell(args, out_dir, rows, wall, server_log, start_line, end_line,
               synthetic, extra=None):
    cell = {
        "schema": "p2b0-cell-1",
        "task_id": "P2-B0-20260912",
        "classification": "MEASUREMENT",
        "synthetic": bool(synthetic),
        "nonce": args.nonce,
        "args": vars(args),
        "driver": {
            "path": os.path.abspath(__file__),
            "sha256": sha256_file(__file__),
        },
        "launch_script": launch_info(args.launch_script, EXPECTED_LAUNCH_SHA),
        "cell_launcher": {
            "path": args.cell_launcher,
            "present": os.path.exists(args.cell_launcher),
            "sha256": sha256_file(args.cell_launcher),
        },
        "contract": {
            "path": CONTRACT,
            "present": os.path.exists(CONTRACT),
            "sha256": sha256_file(CONTRACT),
        },
        "out_dir": out_dir,
        "join_path": os.path.join(out_dir, "join.jsonl"),
        "gpu_path": os.path.join(out_dir, "gpu.csv"),
        "metrics_path": os.path.join(out_dir, "metrics.csv"),
        "server_log": {
            "path": server_log,
            "present": os.path.exists(server_log),
            "start_line": start_line,
            "end_line": end_line,
        },
        "completion_set": completion_set(rows),
        "nominal_concurrency": args.agents,
        "wall": wall,
    }
    if extra:
        cell.update(extra)
    return cell


# --------------------------------------------------------------------------
# real run
# --------------------------------------------------------------------------
def run_main(args, out_dir):
    sessions = build_sessions(args)
    join_path = os.path.join(out_dir, "join.jsonl")
    lock = threading.Lock()
    state = {
        "seq": 0,
        "budget_skipped": 0,
        "errors": {},
        "measure_start_mono_ns": None,
        "measure_deadline": None,
    }
    join_fh = open(join_path, "w", encoding="utf-8")

    sampler = None
    if not args.no_sampler and Sampler is not None:
        sampler = Sampler(out_dir, base=args.base,
                          gpu_sample_ms=args.gpu_sample_ms, run_id=args.nonce)
        sampler.start()

    start_line = line_count(args.server_log)
    t_start_ns = time.monotonic_ns()
    n = len(sessions)

    def barrier_action():
        state["measure_start_mono_ns"] = time.monotonic_ns()
        if args.measure_seconds and args.measure_seconds > 0:
            state["measure_deadline"] = time.monotonic() + args.measure_seconds

    barrier = threading.Barrier(n, action=barrier_action)

    def next_seq():
        with lock:
            state["seq"] += 1
            return state["seq"]

    def persist(rec):
        row = {k: v for k, v in rec.items() if not k.startswith("_")}
        with lock:
            join_fh.write(json.dumps(row, default=str) + "\n")
            join_fh.flush()

    def send(session, phase, turn, prompt):
        rid = p2b0_rid(args, session, phase, turn)
        rec = new_rec(args, session["idx"], session, phase, turn,
                      next_seq(), rid)
        return run_one(args, rec, prompt, session["session_id"]), rid

    def agent_loop(session):
        prompt_ctx = {"text": session["history"]}
        try:
            for turn in range(1, max(0, args.prime_turns) + 1):
                if turn == 1:
                    prompt_ctx["text"] = session["history"]
                else:
                    prompt_ctx["text"] = (prompt_ctx["text"] + "\n\n"
                                          + make_delta(args, session["idx"], turn))
                rec, _ = send(session, "prime", turn, prompt_ctx["text"])
                persist(rec)
                out = rec.get("_out", "")
                if rec.get("http") == 200 and out:
                    prompt_ctx["text"] = prompt_ctx["text"] + "\n\n" + out
        except Exception as e:  # noqa: BLE001
            with lock:
                state["errors"]["agent%d-prime" % session["idx"]] = repr(e)[:300]
        finally:
            # Always rendezvous, even if this agent's prime failed, so a single
            # bad agent cannot wedge every other agent at the barrier.
            try:
                barrier.wait(timeout=args.prime_barrier_timeout)
            except threading.BrokenBarrierError:
                pass
        try:
            with lock:
                if (state["measure_deadline"] is None
                        and args.measure_seconds and args.measure_seconds > 0):
                    state["measure_deadline"] = (
                        time.monotonic() + args.measure_seconds)
            turn = 0
            while True:
                deadline = state["measure_deadline"]
                if deadline is not None and time.monotonic() >= deadline:
                    break
                if args.measure_turns and turn >= args.measure_turns:
                    break
                turn += 1
                prompt_ctx["text"] = (prompt_ctx["text"] + "\n\n"
                                      + make_delta(args, session["idx"], 1000 + turn))
                rec, _ = send(session, "measure", turn, prompt_ctx["text"])
                persist(rec)
                out = rec.get("_out", "")
                if rec.get("http") == 200 and out:
                    prompt_ctx["text"] = prompt_ctx["text"] + "\n\n" + out
        except Exception as e:  # noqa: BLE001
            with lock:
                state["errors"]["agent%d-measure" % session["idx"]] = repr(e)[:300]

    threads = [threading.Thread(target=agent_loop, args=(s,), daemon=True)
               for s in sessions]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    t_end_ns = time.monotonic_ns()

    if sampler is not None:
        sampler.stop()
        sampler.join(timeout=10)
    join_fh.flush()
    join_fh.close()
    end_line = line_count(args.server_log)

    rows = []
    try:
        with open(join_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except Exception:  # noqa: BLE001
        pass

    wall = {
        "start_mono_ns": t_start_ns,
        "end_mono_ns": t_end_ns,
        "wall_s": round((t_end_ns - t_start_ns) / 1e9, 3),
        "measure_start_mono_ns": state["measure_start_mono_ns"],
        "measure_seconds_budget": args.measure_seconds,
    }
    cell = build_cell(args, out_dir, rows, wall, args.server_log,
                      start_line, end_line, synthetic=False,
                      extra={"budget_skipped": state["budget_skipped"],
                             "agent_errors": state["errors"],
                             "sampler": None if sampler is None else {
                                 "gpu_samples": sampler.gpu_samples,
                                 "metrics_samples": sampler.metrics_samples,
                                 "gpu_path": sampler.gpu_path,
                                 "metrics_path": sampler.metrics_path}})
    with open(os.path.join(out_dir, "cell.json"), "w", encoding="utf-8") as fh:
        json.dump(cell, fh, indent=1, default=str)
    print("RUN_DONE out=%s requests=%d bad_http=%d wall_s=%s"
          % (out_dir, cell["completion_set"]["requests_total"],
             cell["completion_set"]["bad_http"], wall["wall_s"]), flush=True)
    return 0 if cell["completion_set"]["bad_http"] == 0 else 2


# --------------------------------------------------------------------------
# dry-run (no server, no GPU)
# --------------------------------------------------------------------------
def synth_sse(rid, prompt_tokens, dev, host, storage, out_chunks=4):
    words = ["Hello", " there", " cache", " hit", "!"]
    lines = []
    for i in range(out_chunks):
        fr = "length" if i == out_chunks - 1 else None
        obj = {
            "id": rid, "object": "text_completion", "created": 0,
            "model": "synth",
            "choices": [{"index": 0, "text": words[i % len(words)],
                         "finish_reason": fr}],
        }
        lines.append("data: " + json.dumps(obj) + "\n\n")
    cached = dev + host + storage
    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": out_chunks,
        "total_tokens": prompt_tokens + out_chunks,
        "prompt_tokens_details": {"cached_tokens": cached},
    }
    lines.append("data: " + json.dumps(
        {"id": rid, "choices": [], "usage": usage}) + "\n\n")
    sg = {"cached_tokens_details": {"device": dev, "host": host,
                                    "storage": storage}}
    lines.append("data: " + json.dumps(
        {"id": rid, "choices": [], "sglext": sg}) + "\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


def synth_tiers(idx, phase, turn):
    """Deterministic tier mix covering all four scenario classes."""
    if phase == "prime":
        if turn == 1:
            return (0, 0, 1200)          # cold-L3 (not pre-staged)
        return (100, 200, 0)             # L2-restore
    mode = (idx + turn) % 4
    if mode == 0:
        return (500, 0, 0)               # L1-hit
    if mode == 1:
        return (0, 300, 0)               # L2-restore
    if mode == 2:
        return (100, 100, 400)           # RH-staged-L3 (pre-staged)
    return (0, 0, 500)                   # cold-L3 (not pre-staged)


def _synth_server_line(kind, rid, ns):
    stamp = "[2026-09-12 00:00:00]"
    if kind == "enqueue":
        return ("%s [P2A] ts_ns=%d evt=enqueue_mono_ns rid=%s "
                "enqueue_mono_ns=%d node_id=0 build_id=%s "
                "session_generation=1 probe_ns=1000"
                % (stamp, ns, rid, ns, rid))
    if kind == "prefetch":
        return ("%s [P2A] ts_ns=%d evt=prefetch_issued rid=%s "
                "prefetch_length=100 prefetch_issue_mono_ns=%d "
                "attempt_id=%s:prefetch:1 node_id=0 build_id=%s "
                "session_generation=1 probe_ns=1000"
                % (stamp, ns, rid, ns, rid, rid))
    if kind == "admission":
        return ("%s [P3] ts_ns=%d evt=admission.v2 schema=rh_admission.v2 "
                "rid=%s rh_decision_id=%s:rh:1 hicache_prefetch_attempt_id=%s "
                "hicache_prefetch_origin=prefetch ready_host_observed=true "
                "admission_monotonic_ns=%d can_run=true"
                % (stamp, ns, rid, rid, rid, ns))
    if kind == "ready":
        return ("%s [P3] ts_ns=%d evt=ready_host schema=rh_ready_host.v1 "
                "rid=%s attempt_id=%s:prefetch:1 issue_origin=DEMAND "
                "completed_kv_tokens=100 required_aux_pools=['mamba'] "
                "completed_aux_units={'mamba': 1} "
                "restore_state_before=RESTORING restore_state_after=READY "
                "finalize_result=accepted ready_monotonic_ns=%d "
                "event_id=run-1:ready:1 run_id=run-1 process_id=1 "
                "profile_id=profile-synth"
                % (stamp, ns, rid, rid, ns))
    return ""


def dry_run_main(args, out_dir):
    sessions = build_sessions(args)
    join_path = os.path.join(out_dir, "join.jsonl")
    rows = []
    events = []   # (rid, prestaged, base_ns)
    seq = 0
    clock = make_fake_clock()

    def emit_session(session, phase, turn, dev, host, storage, prestaged):
        nonlocal seq
        seq += 1
        rid = p2b0_rid(args, session, phase, turn)
        rec = new_rec(args, session["idx"], session, phase, turn, seq, rid)
        rec["http"] = 200  # synthesized stream completed OK
        # keep the synthetic prompt >= cached breakdown so the analyzer's
        # uncached-prefill guard (cached <= prompt) exercises cleanly
        prompt_tokens = (dev + host + storage) + 64 + session["idx"] * 10 + turn
        raw = synth_sse(rid, prompt_tokens, dev, host, storage, out_chunks=4)
        send_ns = clock()
        out = parse_sse(io.BytesIO(raw), rec, clock)
        finalize_rec(rec, send_ns, clock, out)
        rows.append(rec)
        events.append((rid, prestaged, send_ns))

    for session in sessions:
        for turn in range(1, max(0, args.prime_turns) + 1):
            dev, host, storage = synth_tiers(session["idx"], "prime", turn)
            emit_session(session, "prime", turn, dev, host, storage, False)
        for turn in range(1, max(0, args.measure_turns) + 1):
            dev, host, storage = synth_tiers(session["idx"], "measure", turn)
            prestaged = storage > 0 and ((session["idx"] + turn) % 4 == 2)
            emit_session(session, "measure", turn, dev, host, storage, prestaged)

    with open(join_path, "w", encoding="utf-8") as fh:
        for rec in rows:
            fh.write(json.dumps(rec, default=str) + "\n")

    # measure window from the synthetic rows (same fake-clock scale)
    measure = [r for r in rows if r["phase"] == "measure"]
    w0 = min(r["send_mono_ns"] for r in measure)
    w1 = max((r["last_token_mono_ns"] for r in measure
              if r["last_token_mono_ns"] is not None), default=w0 + 1)
    if w1 <= w0:
        w1 = w0 + 1
    n_samp = 120
    span = w1 - w0
    with open(os.path.join(out_dir, "gpu.csv"), "w", newline="") as gh, \
            open(os.path.join(out_dir, "metrics.csv"), "w", newline="") as mh:
        gh.write("mono_ns,gpu_index,timestamp,utilization_gpu,"
                 "utilization_memory,power_draw,clocks_sm,rc,err\n")
        mh.write("mono_ns,num_queue_reqs,num_running_reqs,"
                 "realtime_decode_tokens,realtime_decode_present,http,rc,err,"
                 "num_queue_reqs_present,num_running_reqs_present,"
                 "realtime_decode_err,num_queue_reqs_err,"
                 "num_running_reqs_err\n")
        for i in range(n_samp):
            ns = w0 + (span * i) // (n_samp - 1)
            idle = (i % 5) in (0, 1)
            util = 5 if idle else 65
            gh.write("%d,0,2026/09/12 00:00:00.000,%d,40,120,1500,0,\n"
                     % (ns, util))
            queue = 3 if (idle and i % 2 == 0) else 0
            mh.write("%d,%d,1,%d,1,200,0,,1,1,,,\n"
                     % (ns, queue, i * 7))

    log_path = os.path.join(out_dir, "server-log-window.log")
    n_lines = 0
    with open(log_path, "w", encoding="utf-8") as lf:
        for rid, prestaged, base_ns in events:
            enq = base_ns
            iss = base_ns + 1_000_000
            adm = base_ns + 6_000_000
            rdy = base_ns + 2_000_000 if prestaged else base_ns + 9_000_000
            for line in (
                _synth_server_line("enqueue", rid, enq),
                _synth_server_line("prefetch", rid, iss),
                _synth_server_line("admission", rid, adm),
                _synth_server_line("ready", rid, rdy),
            ):
                lf.write(line + "\n")
                n_lines += 1

    t0 = w0
    t1 = w1
    wall = {
        "start_mono_ns": t0,
        "end_mono_ns": t1,
        "wall_s": round((t1 - t0) / 1e9, 6),
        "measure_start_mono_ns": w0,
        "measure_seconds_budget": args.measure_seconds,
    }
    cell = build_cell(args, out_dir, rows, wall, log_path, 1, n_lines,
                      synthetic=True,
                      extra={"budget_skipped": 0, "agent_errors": {},
                             "synthetic_note": (
                                 "ALL DATA SYNTHETIC - dry-run self-test only; "
                                 "not real runtime behavior")})
    with open(os.path.join(out_dir, "cell.json"), "w", encoding="utf-8") as fh:
        json.dump(cell, fh, indent=1, default=str)

    # ---- self-test: >=3 chunks, first+last detected, finite ttft/tftt ----
    ok = True
    bad = []
    for r in rows:
        if r["chunk_count"] < 3:
            ok = False
            bad.append((r["rid"], "chunk_count<3"))
        if r["first_token_mono_ns"] is None:
            ok = False
            bad.append((r["rid"], "no_first_token"))
        if r["last_token_mono_ns"] is None:
            ok = False
            bad.append((r["rid"], "no_last_token"))
        if r["ttft_s"] is None or not (r["ttft_s"] >= 0):
            ok = False
            bad.append((r["rid"], "bad_ttft"))
        if r["tftt_s"] is None:
            ok = False
            bad.append((r["rid"], "bad_tftt"))
    if not rows:
        ok = False
        bad.append(("_", "no_rows"))
    print("DRY_RUN self_check=%s rows=%d events=%d min_chunks=%s bad=%s"
          % ("PASS" if ok else "FAIL", len(rows), len(events),
             min((r["chunk_count"] for r in rows), default=0), bad[:5]),
          flush=True)
    if not ok:
        print("DRY_RUN_FAIL", out_dir)
        return 2
    print("DRY_RUN_OK", out_dir, flush=True)
    return 0


# --------------------------------------------------------------------------
def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="P2-B0 streaming workload driver")
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--agents", type=int, default=4,
                    help="nominal client concurrency C<n>")
    ap.add_argument("--prime-turns", type=int, default=2)
    ap.add_argument("--measure-turns", type=int, default=10,
                    help="0 = run only until --measure-seconds")
    ap.add_argument("--hist-tokens", type=int, default=6000)
    ap.add_argument("--delta-words", type=int, default=210)
    ap.add_argument("--max-tokens", type=int, default=32)
    ap.add_argument("--measure-seconds", type=float, default=300.0,
                    help="wall budget for the measure phase (0 = turns only)")
    ap.add_argument("--client-max-time", type=float, default=1200.0,
                    help="per-request socket timeout (seconds)")
    ap.add_argument("--tok-per-word", type=float, default=4.8)
    ap.add_argument("--prime-barrier-timeout", type=float, default=3600.0)
    ap.add_argument("--gpu-sample-ms", type=int, default=200)
    ap.add_argument("--no-sampler", action="store_true")
    ap.add_argument("--rh", default="unknown",
                    choices=["on", "off", "unknown"],
                    help="ready-horizon profile of the running server (provenance)")
    ap.add_argument("--max-running", default=None,
                    help="engine --max-running-requests = nominal C<n> (provenance)")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--server-log", default=SERVER_LOG)
    ap.add_argument("--launch-script", default=LAUNCH_SCRIPT,
                    help="frozen launch script to hash")
    ap.add_argument("--cell-launcher", default=CELL_LAUNCHER)
    ap.add_argument("--nonce", default=time.strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run", action="store_true")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not args.dry_run and not args.run:
        print("FATAL: pass --dry-run or --run", file=sys.stderr)
        return 2
    if args.dry_run and args.run:
        print("FATAL: pass only one of --dry-run / --run", file=sys.stderr)
        return 2
    args.agents = max(1, args.agents)
    if args.out_dir:
        out_dir = args.out_dir
    elif args.dry_run:
        out_dir = os.path.join(OUT_ROOT, "dry-run")
    else:
        out_dir = os.path.join(OUT_ROOT, "run-%s-%s" % (args.nonce, args.agents))
    os.makedirs(out_dir, exist_ok=True)
    if args.dry_run:
        return dry_run_main(args, out_dir)
    return run_main(args, out_dir)


if __name__ == "__main__":
    sys.exit(main())
