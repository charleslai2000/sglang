#!/usr/bin/env python3
"""R129 P2-A live-collection workload driver.

Contract:
  work/P2A-COLLECTION-CONTRACT-20260912.md  (sha 1b9c2969...3b26)
  work/P2A-MEASUREMENT-CONTRACT-20260912.md (sha c0551708...1096a)

Public HTTP only (/v1/tokenize + /v1/completions).  No product imports, no
server control, no /flush_cache, no /close_session, no restart, no new
instrumentation.  The driver only *sends* a real multi-turn session workload
and records what the frozen probe already emits server-side.

Shape (contract): N>=4 sessions, distinct long histories (6k-12k tokens,
unique per-session marker), TURNS>=5, turn 1 = COLD prime (full history),
turns 2..TURNS = WARM re-send full history + novel delta.  Distinct-session
pressure churns device+host so warm turns exercise the storage query and the
L3->L2 stage.  Total requests >= 40, <= 200 HTTP, <= 45 min.

Usage:
  python driver129.py --dry-run          # tokenize only; print/emit token counts
  python driver129.py --run              # execute the workload

All output goes under R129-bundle/ (run-<ts>/).
"""
import argparse
import hashlib
import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = os.environ.get("R129_BASE", "http://127.0.0.1:30000")
MODEL = os.environ.get("R129_MODEL", "/mnt/data/models/qwen35-gptq")
SERVER_LOG = os.environ.get(
    "R129_SERVER_LOG",
    "/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-p2a.log",
)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.environ.get("R129_OUT", HERE)
CONTRACT = os.path.join(os.path.dirname(HERE), "P2A-COLLECTION-CONTRACT-20260912.md")
MEASURE_CONTRACT = os.path.join(
    os.path.dirname(HERE), "P2A-MEASUREMENT-CONTRACT-20260912.md"
)

N_SESSIONS = int(os.environ.get("R129_N", "8"))
TURNS = int(os.environ.get("R129_TURNS", "6"))
N_PRESSURE = int(os.environ.get("R129_N_PRESSURE", "6"))
PRESSURE_EQ_ROUND = int(os.environ.get("R129_PRESSURE_EQ_ROUND", "1"))
BURST_TURNS = sorted(
    int(x) for x in os.environ.get("R129_BURST_TURNS", "").split(",") if x.strip()
)
BURST_N = int(os.environ.get("R129_BURST_N", "0"))
HIST_TARGETS = [
    int(x)
    for x in os.environ.get(
        "R129_HIST_TARGETS", "6000,7200,8400,9600,10800,11800,6800,9200"
    ).split(",")
]
PRESSURE_TARGET = int(os.environ.get("R129_PRESSURE_TARGET", "12000"))
DELTA_WORDS = int(os.environ.get("R129_DELTA_WORDS", "210"))
TOK_PER_WORD = float(os.environ.get("R129_TOK_PER_WORD", "4.80"))
MAX_TOKENS = 1
REQ_TIMEOUT = float(os.environ.get("R129_REQ_TIMEOUT", "900"))
NONCE = os.environ.get("R129_NONCE", time.strftime("%H%M%S"))

WORD = "abcdefghijklmnopqrstuvwxyz"
_lock = threading.Lock()
_DEADLINE = None


def budget_ok():
    return _DEADLINE is None or time.time() < _DEADLINE


def rw(rng):
    return "".join(rng.choice(WORD) for _ in range(rng.randint(4, 10)))


def rare_prefix(k):
    return "".join(chr(0x1F700 + ((k * 13 + j) % 0x60)) for j in range(4))


def make_text(seed, k, n_words):
    """Unique-per-k radix branch: rare prefix + deterministic word soup."""
    rng = random.Random(seed)
    parts = [rare_prefix(k)]
    parts += ["uniq" + rw(rng) for _ in range(max(1, n_words))]
    return " ".join(parts)


def emit(path, rec):
    with _lock:
        with open(path, "a") as h:
            h.write(json.dumps(rec) + "\n")


def _post(url, payload, timeout=1200):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    t0 = time.time()
    code = resp = None
    err = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.status
            resp = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            err = e.read().decode()[:1500]
        except Exception:  # noqa: BLE001
            err = repr(e)[:400]
    except Exception as e:  # noqa: BLE001
        code = "000"
        err = repr(e)[:600]
    return code, resp, err, round(time.time() - t0, 3)


def tokenize(texts):
    return _post(BASE + "/v1/tokenize", {"model": MODEL, "prompt": texts},
                 timeout=300)


def completion(rid, prompt, session, tag, out_dir, stats, max_tokens=MAX_TOKENS):
    if not budget_ok():
        emit(os.path.join(out_dir, "requests.jsonl"),
             {"tag": tag, "rid": rid, "session_id": session, "http": "skip",
              "elapsed_s": 0, "err": "wall_clock_budget_exceeded",
              "ts": round(time.time(), 3)})
        with _lock:
            stats["budget_skipped"] = stats.get("budget_skipped", 0) + 1
        print("SKIP %-34s budget_exceeded" % tag, flush=True)
        return "skip", None, "budget_exceeded", 0.0
    code, resp, err, el = _post(BASE + "/v1/completions", {
        "model": MODEL, "prompt": prompt, "max_tokens": max_tokens,
        "temperature": 0, "stream": False,
        "session_id": session, "rid": rid,
    }, timeout=REQ_TIMEOUT)
    usage = (resp or {}).get("usage") if isinstance(resp, dict) else None
    rec = {"tag": tag, "rid": rid, "session_id": session, "http": code,
           "elapsed_s": el, "err": err,
           "prompt_tokens": (usage or {}).get("prompt_tokens"),
           "ts": round(time.time(), 3)}
    emit(os.path.join(out_dir, "requests.jsonl"), rec)
    with _lock:
        stats["http_total"] += 1
        stats["http_bad"] += 0 if str(code) == "200" else 1
        stats["elapsed_sum"] += el
    print("REQ %-34s %s %8.3fs prompt=%s" % (tag, code, el,
          (usage or {}).get("prompt_tokens")), flush=True)
    return code, resp, err, el


def server_line_count():
    with open(SERVER_LOG, "r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for _ in fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="tokenize only; no completions")
    ap.add_argument("--run", action="store_true", help="execute the workload")
    args = ap.parse_args()
    if not args.dry_run and not args.run:
        ap.error("pass --dry-run or --run")

    ts = time.strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(OUT_ROOT, "run-" + ts)
    os.makedirs(out_dir, exist_ok=True)

    def sha(path):
        try:
            h = hashlib.sha256()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:  # noqa: BLE001
            return None

    # ---- build texts ----
    n = max(4, N_SESSIONS)
    targets = (HIST_TARGETS * ((n // len(HIST_TARGETS)) + 1))[:n]
    # word count ~= tokens/3.8 (latin word soup); calibrate once via tokenize
    sessions = []
    for i in range(n):
        tgt = targets[i]
        words = int(tgt / TOK_PER_WORD)
        text = make_text(0x1000 + i * 7, i, words)
        sessions.append({
            "idx": i,
            "label": "s%d" % i,
            "session_id": "r129-sess-%s-%d" % (NONCE, i),
            "target": tgt,
            "text": text,
            "deltas": [
                make_text(0x5000 + i * 131 + t, 1000 + i * 16 + t, DELTA_WORDS)
                for t in range(1, TURNS + 1)
            ],
        })
    pressures = []
    for i in range(N_PRESSURE):
        words = int(PRESSURE_TARGET / TOK_PER_WORD)
        pressures.append({
            "idx": i,
            "label": "p%d" % i,
            "session_id": "r129-press-%s-%d" % (NONCE, i),
            "target": PRESSURE_TARGET,
            "text": make_text(0x9000 + i * 11, 500 + i, words),
        })

    # ---- calibration: tokenize batch ----
    all_texts = [s["text"] for s in sessions]
    all_texts += [p["text"] for p in pressures]
    code, resp, err, el = tokenize(all_texts)
    counts = (resp or {}).get("count") if isinstance(resp, dict) else None
    tok_err = (resp or {}).get("tokens") if isinstance(resp, dict) else None
    state = {
        "t": round(time.time(), 3), "evt": "tokenize", "http": code,
        "elapsed_s": el, "err": err, "nonce": NONCE,
        "contract_sha": sha(CONTRACT), "measure_contract_sha": sha(MEASURE_CONTRACT),
        "n_sessions": n, "turns": TURNS, "n_pressure": N_PRESSURE,
        "hist_targets": targets, "server_log": SERVER_LOG,
        "server_start_lines": server_line_count(),
    }
    emit(os.path.join(out_dir, "state.jsonl"), state)
    print("TOKENIZE", code, counts, el, flush=True)
    if code != 200 or not isinstance(counts, list):
        emit(os.path.join(out_dir, "state.jsonl"),
             {"evt": "abort_tokenize", "err": err})
        print("FATAL: tokenize failed", file=sys.stderr)
        return 2

    hist_counts = counts[:n]
    press_counts = counts[n:]
    for i, s in enumerate(sessions):
        s["tokens"] = hist_counts[i]
    for i, p in enumerate(pressures):
        p["tokens"] = press_counts[i]
    emit(os.path.join(out_dir, "state.jsonl"), {
        "t": round(time.time(), 3), "evt": "token_counts",
        "history": {s["label"]: {"target": s["target"], "actual": s["tokens"]}
                    for s in sessions},
        "pressure": {p["label"]: p["tokens"] for p in pressures},
        "distinct_history_tokens": sum(s["tokens"] for s in sessions),
    })
    print("HIST", {s["label"]: (s["target"], s["tokens"]) for s in sessions},
          flush=True)
    print("PRESS", {p["label"]: p["tokens"] for p in pressures}, flush=True)

    oob = [s["label"] for s in sessions if not (6000 <= s["tokens"] <= 12000)]
    emit(os.path.join(out_dir, "state.jsonl"),
         {"evt": "range_check", "outside_6k_12k": oob})
    if oob:
        print("WARN: histories outside 6k-12k:", oob, file=sys.stderr)

    if args.dry_run:
        emit(os.path.join(out_dir, "state.jsonl"), {"evt": "dry_run_done"})
        print("DRY_RUN_DONE", out_dir, flush=True)
        return 0

    # ---- execute ----
    global _DEADLINE
    _DEADLINE = time.time() + float(os.environ.get("R129_MAX_SECONDS", "2100"))
    stats = {"http_total": 0, "http_bad": 0, "elapsed_sum": 0.0,
             "budget_skipped": 0}
    plan = {
        "n": n, "turns": TURNS, "n_pressure": N_PRESSURE,
        "pressure_eq_round": PRESSURE_EQ_ROUND,
        "burst_turns": BURST_TURNS, "burst_n": BURST_N,
        "expected_requests": (n * TURNS + N_PRESSURE
                              + (TURNS - 1) * PRESSURE_EQ_ROUND
                              + len([t for t in range(2, TURNS + 1)
                                     if t in BURST_TURNS]) * BURST_N),
    }
    emit(os.path.join(out_dir, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "run_start", "plan": plan,
          "server_start_lines": server_line_count()})
    print("RUN_START", plan, flush=True)
    t_start = time.time()

    # Phase 1: serial COLD prime (full history)
    for s in sessions:
        rid = "r129-%s-cold-%s" % (s["label"], NONCE)
        completion(rid, s["text"], s["session_id"], "cold-%s" % s["label"],
                   out_dir, stats)

    # Phase 2: distinct-session pressure to churn device/host
    for p in pressures:
        rid = "r129-%s-fill-%s" % (p["label"], NONCE)
        completion(rid, p["text"], p["session_id"], "press-%s" % p["label"],
                   out_dir, stats)
    emit(os.path.join(out_dir, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "pressure_fill_done",
          "http_total": stats["http_total"]})
    print("PRESSURE_FILL_DONE", stats, flush=True)

    # Phase 3: WARM turns, all sessions concurrent per turn (queue => RH lead)
    round_recs = []

    def warm_worker(s, turn, prefix):
        text = prefix + "\n\n" + s["deltas"][turn - 1]
        rid = "r129-%s-t%d-%s" % (s["label"], turn, NONCE)
        code, _, _, el = completion(
            rid, text, s["session_id"], "warm-%s-t%d" % (s["label"], turn),
            out_dir, stats)
        with _lock:
            round_recs.append((turn, s["label"], code, el))

    for turn in range(2, TURNS + 1):
        if turn in BURST_TURNS:
            for j in range(BURST_N):
                ptext = make_text(
                    0xC000 + turn * 211 + j, 3000 + turn * 31 + j,
                    int(PRESSURE_TARGET / TOK_PER_WORD)
                )
                rid = "r129-burst-t%d-%d-%s" % (turn, j, NONCE)
                completion(
                    rid, ptext, "r129-burst-%s-t%d-%d" % (NONCE, turn, j),
                    "burst-t%d-%d" % (turn, j), out_dir, stats)
            emit(os.path.join(out_dir, "state.jsonl"),
                 {"t": round(time.time(), 3), "evt": "burst_done", "turn": turn,
                  "n": BURST_N, "http_total": stats["http_total"]})
            print("BURST_DONE turn=%d n=%d" % (turn, BURST_N), flush=True)
        threads = []
        for s in sessions:
            # accumulated history + prior deltas; this turn adds one novel delta
            acc = s["text"] + "".join(
                "\n\n" + s["deltas"][t - 1] for t in range(1, turn)
            )
            th = threading.Thread(target=warm_worker, args=(s, turn, acc))
            threads.append(th)
            th.start()
        for th in threads:
            th.join()
        print("WARM_ROUND_DONE turn=%d http_total=%d" % (turn, stats["http_total"]),
              flush=True)

        # sustained pressure between warm rounds (distinct novel text)
        for j in range(PRESSURE_EQ_ROUND):
            ptext = make_text(
                0xB000 + turn * 97 + j, 2000 + turn * 23 + j,
                int(PRESSURE_TARGET / TOK_PER_WORD)
            )
            rid = "r129-press-t%d-%d-%s" % (turn, j, NONCE)
            completion(rid, ptext, "r129-press-%s-t%d-%d" % (NONCE, turn, j),
                       "press-t%d-%d" % (turn, j), out_dir, stats)

    t_end = time.time()
    emit(os.path.join(out_dir, "state.jsonl"), {
        "t": round(time.time(), 3), "evt": "run_end",
        "http_total": stats["http_total"], "http_bad": stats["http_bad"],
        "elapsed_s": round(t_end - t_start, 1),
        "server_end_lines": server_line_count(),
    })
    print("RUN_END", stats, "elapsed=%.1f" % (t_end - t_start), flush=True)
    return 0 if stats["http_bad"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
