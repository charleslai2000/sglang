#!/usr/bin/env python3
"""gate3_capacity.py -- Phase-2 experiment③: real-Claude capacity curve.

PURPOSE  (2026-09-07 user ruling -- the authoritative wording this driver
---------------------------------------------------------------------
implements; do not regress to any scheduler-pause-based scenario)
Measure how resident device KV / Host-L3 hit rates / recompute / TTFT and
aggregate decode TPS hold as N real Claude-like subagents (N = 4/6/8)
hold ~50-80K-token working prefixes concurrently, each running a small
number of incremental warm turns.  The scenario is pure natural-pressure:
NO scheduler WAIT_CAPACITY, NO /pause_generation.  Every agent keeps its own
long history alive and issues small deltas against it.

Why this driver is needed (phase2-cap-scout-e1.md Q4):
  - gate2_warmctx.py has the long-context history shape (64K = 64030 tokens
    cold-prefilled) but is single-session, not concurrent.
  - gate2_load.py has the multi-subagent concurrency shape but its prompts
    are modest (< 50-80K).
  - No existing driver combines N >= 4 concurrent subagents EACH holding a
    50-80K prefix AND issuing warm deltas.  This driver is that combination.

Load shape
----------
For each agent a in 0..N-1:
  COLD   : a single 50K or 80K-token history prompt (node-local, tokenizer
           truncated, deterministic per agent seed) cold-prefilled into an
           empty cache.  This is the "agent's long context base".
  WARM   : R repeats of history + assistant reply + a short new user delta
           (~tens of tokens).  Computed against the cached prefix: the radix
           tree should device-hit the whole history and only the delta is
           recomputed -- THIS is the business metric the experiment compares
           across N (does hit ratio / TTFT hold as more 50-80K agents compete
           for the same 24G device KV pool?).

Concurrency control
-------------------
  --agents threads each run their own cold + warm scripted turns
  independently.  Threads do NOT coordinate a barrier: a thread issues its
  next turn as soon as the previous one returns (TCP backpressure is the
  natural concurrency governor -- under 24G pressure requests wait in the
  engine queue, exactly like real load).  A deterministic per-agent stagger
  separates the COLD history builds; subsequent warm turns are free-running.

Output
------
  join.log        per-request rows (one JSON per line), schema below.
  runs.csv        CSV export of the same rows (same column names as
                  gate2_load/gate2_warmctx runs.csv: ttft_s / wall_s / http /
                  finished / storage_hit ... -- gate2_analyze.py-compatible).
  mid-run-metrics.txt  metrics gauge sampler time series (every few seconds).
  turns/agent-<n>/t<turn>.<kind>.{payload.json,headers,body,meta.json}
                  per-request artifacts; per-turn metric deltas.
  verdict.json    run summary.

Row schema (join.log / runs.csv):
  agent_id, turn, turn_kind(cold|warm), round, ts_start, ts_end,
  ttft_s, wall_s, http, finished, finish_reason, rid, rc,
  history_tokens (target prefix from the tokenizer), prompt_len (engine),
  completion_tokens, cached_tokens, cached_device, cached_host,
  cached_storage, prefill_input_delta, prefill_devicehit_delta,
  prefill_hosthit_delta, prefill_storagehit_delta, output_field, output_sha16.
  (prefill_* fields are engine-counter deltas over each request's window --
   an independent cross-check of the per-request cached_tokens_details.)

Usage
-----
  SGLANG_PORT=8024 MODEL_PATH=/root/models/Qwen3.5-9B-w4a16 \
    python gate3_capacity.py --agents 6 --tier 55k \
      --evidence-dir /root/evidence-capacity-64k-c6

  unit sanity (no engine needed):
  python gate3_capacity.py --dry-run --agents 4 --tier 55k
"""
import argparse
import csv
import json
import os
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, "p2-0"), "/root", "/root/p2-0"):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
try:
    import common  # noqa: E402
except ImportError:
    common = None

# 50K / 55K / 80K history targets (tokens cold-prefilled per agent).
TIER_TARGETS = {
    "50k": 50000,
    "55k": 55000,
    "80k": 80000,
}

# Attend: kv_cache_dtype=fp8_e4m3 (FP8 KV) under ② 's freeze is the OPPORTION
# premise; the driver is dtype-agnostic (only the engine launch wrapper sets
# KV_DTYPE).  Keep the tokenizer as the single authority for the prompt size.

# Stable Chinese corpus (built for the 64K warmctx baseline).  Repeated with a
# paragraph index so the tokenizer produces a stable, reproducible long text.
_CORPUS = (
    "大语言模型推理中的缓存系统分为三级：GPU 显存一级缓存、主机内存二级缓存与"
    "NVMe 固态硬盘三级缓存。一级缓存存放最近被访问的键值对与状态张量，访问速度最快"
    "但容量有限；当显存放不下时，旧的张量会被逐出到主机内存，仍然保留供后续请求复用；"
    "更久远的数据则会写入三级缓存，通过扩展文件后端按区块持久化。这套分级存储的目标是"
    "让长上下文的智能体在连续多轮对话中，只有新增内容需要真正计算，而历史内容全部命中缓存，"
    "从而大幅降低热会话下一轮的响应延迟。我们通过实验测量不同历史长度下，追加少量新内容时的"
    "首令牌延迟与整体端到端延迟，以验证三级缓存是否成功兜住了历史。"
)

# Talky follow-up the agent asks after reading its own history.  Short so the
# warm delta stays small (a few tens of tokens HF-encoded).
_WARM_DELTA = "现在请用一句话总结刚才这段资料的核心观点，不要展开。"


def build_history_prompt(target_tokens, tokenizer, session_seed):
    """A single user message of >= target_tokens, deterministic per seed.

    A unique per-session marker prefix makes every agent's history a distinct
    radix branch (independent prefixes -> no accidental cross-agent sharing).
    Returns (text, n_tokens).
    """
    marker = "会话编号 %d。以下是本轮对话的完整历史背景资料。\n\n" % session_seed
    text = marker
    n = len(tokenizer.encode(text))
    i = 0
    while n < target_tokens:
        text += ("[%d] " % i) + _CORPUS + "\n"
        i += 1
        n = len(tokenizer.encode(text))
    return text, n


def fetch_metrics(lock=None):
    if common is None:
        return ""
    return common.fetch_metrics_text(lock)


def parse_metrics(text):
    if common is None:
        return {}
    try:
        return common.parse_metrics(text)
    except Exception:  # noqa: BLE001
        return {}


def _md(before, after, name, label_contains=None):
    if common is None:
        return None
    try:
        return common.metric_delta(before, after, name, label_contains)
    except Exception:  # noqa: BLE001
        return None


def _mkrow(agent, turn, kind, round_no, hist_n, meta, sx, ts_s, ts_e,
           mb, ma, rc):
    u = (sx or {}).get("usage") or meta.get("usage") or {}
    ctd = (sx or {}).get("cached_tokens_details") or {}
    out, out_field = common.output_text(meta) if common else ("", None)
    row = {
        "agent_id": agent, "turn": turn, "turn_kind": kind, "round": round_no,
        "ts_start": round(ts_s, 3), "ts_end": round(ts_e, 3),
        "ttft_s": meta.get("ttft_s"), "wall_s": meta.get("wall_s"),
        "http": meta.get("http_code"), "finished": meta.get("finished"),
        "finish_reason": meta.get("finish_reason"),
        "rid": (sx or {}).get("rid") or meta.get("request_id"),
        "rc": rc,
        "history_tokens": hist_n,
        "prompt_len": u.get("prompt_tokens") if isinstance(u, dict) else None,
        "completion_tokens": (u.get("completion_tokens")
                              if isinstance(u, dict) else None),
        "cached_tokens": (sx or {}).get("cached_tokens"),
        "cached_device": ctd.get("device"),
        "cached_host": ctd.get("host"),
        "cached_storage": ctd.get("storage"),
        "output_field": out_field,
        "output_sha16": (common.sha16(out) if common else None),
    }
    # Cache-source deltas from engine counters (independent cross-check).
    for label, mode in (("prefill_input_delta", 'mode="input"'),
                        ("prefill_devicehit_delta", 'mode="device_hit"'),
                        ("prefill_hosthit_delta", 'mode="host_hit"'),
                        ("prefill_storagehit_delta", 'mode="storage_hit"')):
        row[label] = _md(mb, ma, "sglang:prefill_effective_tokens_total", mode)
    return row


def _post(lock, out_prefix, payload, max_time, ev_dir):
    """metrics-before -> in-process SSE client -> metrics-after.  Same shape
    as gateway warmctx._post (uses common.run_client_inproc directly so no
    payload file round-trip is needed)."""
    m_before = parse_metrics(fetch_metrics(lock))
    ts_start = time.time()
    # common.run_client_inproc reads the payload path first; create it before
    # invoking the helper, matching the proven cap-ratio driver path.
    os.makedirs(os.path.dirname(out_prefix) or ".", exist_ok=True)
    with open(out_prefix + ".payload.json", "w") as payload_f:
        json.dump(payload, payload_f, ensure_ascii=False)
    rc, meta = common.run_client_inproc(out_prefix + ".payload.json",
                                        out_prefix, max_time)
    ts_end = time.time()
    m_after = parse_metrics(fetch_metrics(lock))
    sx = common.extract_sglext(meta, out_prefix + ".body")
    return rc, meta, sx, ts_start, ts_end, m_before, m_after


def run_agents(args, tok, state):
    """Spawn --agents threads, each running cold + warm scripted turns."""
    rows = []

    def agent_loop(agent, metrics_lock):
        recs = []
        try:
            time.sleep(agent * args.stagger)
            hist_text, hist_n = build_history_prompt(
                TIER_TARGETS[args.tier], tok, agent)
            turn = 0
            # COLD: full history, short completion.
            turn += 1
            cold_payload = {
                "model": args.served,
                "messages": [{"role": "user", "content": hist_text}],
                "max_tokens": args.cold_max_new,
                "temperature": 0.0,
                "stream": True,
            }
            prefix = os.path.join(state["turns_dir"],
                                  "agent-%d" % agent,
                                  "t%d.cold" % turn)
            rc, meta, sx, ts_s, ts_e, mb, ma = _post(
                metrics_lock, prefix, cold_payload, args.client_max_time,
                state["run_dir"])
            row = _mkrow(agent, turn, "cold", 0, hist_n, meta, sx,
                         ts_s, ts_e, mb, ma, rc)
            recs.append(row)
            with state["join_lock"]:
                state["join_fh"].write(json.dumps(row) + "\n")
                state["join_fh"].flush()
            print("[a%d] t%d cold rc=%d prompt=%d wall=%s ttft=%s"
                  % (agent, turn, rc, hist_n,
                     meta.get("wall_s"), meta.get("ttft_s")), flush=True)

            asst_text, _ = common.output_text(meta) if common else ("", None)
            # WARM: history + assistant + short delta, repeated.
            for r in range(1, args.warm_repeats + 1):
                turn += 1
                warm_payload = {
                    "model": args.served,
                    "messages": [
                        {"role": "user", "content": hist_text},
                        {"role": "assistant", "content": asst_text},
                        {"role": "user", "content": _WARM_DELTA},
                    ],
                    "max_tokens": args.warm_max_new,
                    "temperature": 0.0,
                    "stream": True,
                }
                prefix = os.path.join(state["turns_dir"],
                                      "agent-%d" % agent,
                                      "t%d.warm-r%d" % (turn, r))
                rc2, meta2, sx2, ts_s2, ts_e2, mb2, ma2 = _post(
                    metrics_lock, prefix, warm_payload, args.client_max_time,
                    state["run_dir"])
                row2 = _mkrow(agent, turn, "warm", r, hist_n, meta2, sx2,
                              ts_s2, ts_e2, mb2, ma2, rc2)
                recs.append(row2)
                with state["join_lock"]:
                    state["join_fh"].write(json.dumps(row2) + "\n")
                    state["join_fh"].flush()
                print("[a%d] t%d warm r%d rc=%d wall=%s ttft=%s"
                      % (agent, turn, r, rc2,
                         meta2.get("wall_s"), meta2.get("ttft_s")), flush=True)
        except Exception as e:  # noqa: BLE001
            print("agent %d error: %s" % (agent, e), file=sys.stderr)
            recs.append({"agent_id": agent, "turn": turn, "rc": -1,
                         "error": str(e)})
        state["results"][agent] = recs

    state["results"] = {}
    threads = []
    for a in range(1, args.agents + 1):
        t = threading.Thread(target=agent_loop, args=(a, state["metrics_lock"]))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    return [r for s in state["results"].values() for r in s]


def write_outputs(args, rows, state, t_start):
    run_dir = state["run_dir"]
    fieldnames = []
    for r in rows:
        for k in r:
            if k not in fieldnames:
                fieldnames.append(k)
    with open(os.path.join(run_dir, "runs.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    n_ok = sum(1 for r in rows if r.get("http") == "200" or r.get("finished"))
    summary = {
        "status": "done", "agents": args.agents, "tier": args.tier,
        "target_tokens": TIER_TARGETS[args.tier],
        "warm_repeats": args.warm_repeats, "requests_total": len(rows),
        "requests_ok": n_ok,
        "run_dir": run_dir,
        "ts_start": round(t_start, 3),
        "ts_end": round(time.time(), 3),
        "elapsed_s": round(time.time() - t_start, 1),
    }
    with open(os.path.join(run_dir, "verdict.json"), "w") as f:
        json.dump(summary, f, indent=1, default=str)
    print("GATE3_CAPACITY_DONE agents=%d tier=%s run_dir=%s requests=%d"
          % (args.agents, args.tier, run_dir, len(rows)), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", type=int, default=6,
                    help="concurrent subagents (4/6/8)")
    ap.add_argument("--tier", default="55k", choices=sorted(TIER_TARGETS),
                    help="50k|55k|80k history target")
    ap.add_argument("--warm-repeats", type=int, default=3,
                    help="warm turns per agent")
    ap.add_argument("--cold-max-new", type=int, default=12)
    ap.add_argument("--warm-max-new", type=int, default=64)
    ap.add_argument("--stagger", type=float, default=2.0,
                    help="per-agent COLD launch stagger (seconds)")
    ap.add_argument("--client-max-time", type=int, default=1200,
                    help="per-request timeout -- cold 80K prefill can be slow "
                         "under 8-way contention")
    ap.add_argument("--snapshot-interval", type=float, default=5.0,
                    help="mid-run metric sampler cadence (seconds)")
    ap.add_argument("--evidence-dir", default="/root/evidence-capacity")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--served", default=None)
    args = ap.parse_args()
    args.served = args.served or os.environ.get("SERVED", "qwen3.5-9b-gptq")

    if args.dry_run:
        tiers = []
        for t in sorted(TIER_TARGETS):
            try:
                from transformers import AutoTokenizer
                tok = AutoTokenizer.from_pretrained(
                    os.environ.get("MODEL_PATH", "/root/models/Qwen3.5-9B-w4a16"))
                _, n = build_history_prompt(TIER_TARGETS[t], tok, 1)
                tiers.append((t, TIER_TARGETS[t], n))
            except Exception as e:  # noqa: BLE001
                tiers.append((t, TIER_TARGETS[t], "tokenizer-unavailable: %s" % e))
        print("DRY_RUN_OK agents=%d tiers=%s warm_repeats=%d"
              % (args.agents, tiers, args.warm_repeats))
        return 0

    if not common:
        print("FATAL: common.py not importable "
              "(gate2/gate3 drivers run from /root)", file=sys.stderr)
        return 2

    try:
        from transformers import AutoTokenizer
    except Exception as e:  # noqa: BLE001
        print("FATAL: transformers unavailable: %s" % e, file=sys.stderr)
        return 2
    tok = AutoTokenizer.from_pretrained(
        os.environ.get("MODEL_PATH", "/root/models/Qwen3.5-9B-w4a16"))

    run_dir = os.path.join(args.evidence_dir,
                           "run-%s" % time.strftime("%Y%m%d-%H%M%S"))
    turns_dir = os.path.join(run_dir, "turns")
    os.makedirs(turns_dir, exist_ok=True)
    state = {
        "run_dir": run_dir,
        "turns_dir": turns_dir,
        "join_fh": open(os.path.join(run_dir, "join.log"), "a"),
        "join_lock": threading.Lock(),
        "metrics_lock": threading.Lock(),
        "mid_fh": open(os.path.join(run_dir, "mid-run-metrics.txt"), "a"),
        "t_start": time.time(),
    }
    stop = threading.Event()

    def sampler():
        while True:
            try:
                snap = parse_metrics(fetch_metrics(state["metrics_lock"]))
            except Exception:  # noqa: BLE001
                snap = {}
            with state["join_lock"]:
                state["mid_fh"].write(json.dumps(
                    {"ts": round(time.time(), 3), "metrics": snap}) + "\n")
                state["mid_fh"].flush()
            if stop.wait(args.snapshot_interval):
                return

    th = threading.Thread(target=sampler, daemon=True)
    th.start()

    t_start = time.time()
    rows = run_agents(args, tok, state)
    stop.set()
    th.join()
    try:
        final = parse_metrics(fetch_metrics(state["metrics_lock"]))
    except Exception:  # noqa: BLE001
        final = {}
    with state["join_lock"]:
        state["mid_fh"].write(json.dumps(
            {"ts": round(time.time(), 3), "metrics": final}) + "\n")
        state["mid_fh"].flush()
        state["mid_fh"].close()
        state["join_fh"].close()
    write_outputs(args, rows, state, t_start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
