#!/usr/bin/env python3
"""gate2_warmctx.py -- Phase-2 experiment② long-context warm-turn latency driver.

Purpose
-------
Measure whether the NEXT-turn response latency of a long-history Agent depends
only on the NEW content (delta) or grows with the full history length -- the
core three-tier-cache (GPU L1 / Host L2 / NVMe L3) business metric.

Per context tier (32K / 64K / 128K):
  - COLD: a single large prompt (tokenized to ~target length) is prefilled
    cold (empty cache).  This builds the full history in the radix tree and is
    the "build history" step -- its latency is NOT the warm-turn metric.
  - WARM: a second request on the SAME session re-sends the byte-identical
    history plus a short assistant turn + a short new user delta (~tens of
    tokens).  The unified radix tree should hit the cached history prefix, so
    only the delta is (re)computed.  WARM TTFT / E2E is the measured metric.

If the 3-tier cache holds history, WARM latency should be ~flat across
32K/64K/128K (only the delta matters).  If it grows linearly/2x with context,
the cache is not holding the history as expected.

Streaming
---------
stream=true: common.run_client_inproc parses the SSE stream and sets
  ttft_s = first content/reasoning token time (TRUE TTFT), wall_s = full body
  (E2E).  This avoids the stream:false caveat where ttft=wall=E2E.
  (Fallback: if engine returns non-streaming body, ttft=wall=E2E as before --
   recorded in a per-row flag.)

Metric collection
-----------------
Per-request rows in runs.csv (same evidence shape as gate2/gen):
  tier, session, turn(cold/warm), ts_start/end, ttft_s, wall_s(E2E), http,
  finished, prompt_len, completion_tokens, cached_tokens,
  cached_tokens_details{device,host,storage}, finish_reason.
  Plus per-request counter deltas (prefill_effective_tokens input/device_hit/
  host_hit/storage_hit) from /metrics for cross-check of cache-hit source.

Usage (engine already running with the tier's wrapper):
  SGLANG_PORT=8024 STORAGE_DIR=/data/l3/p2io-warmctx-<tier> \
    python gate2_warmctx.py --tier 32k --sessions 3 --evidence-dir /root/evidence-warmctx-<tier>
"""
import argparse
import csv
import json
import os
import subprocess
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

# Tiers -> target history token length (tokens prefilled cold)
TIER_TARGETS = {
    "32k": 32000,
    "64k": 64000,
    "128k": 128000,
}

# A fixed corpus paragraph (Chinese, stable across runs).  Repeated/truncated
# to hit the target token count with the tokenizer.
_CORPUS = (
    "大语言模型推理中的缓存系统分为三级：GPU 显存一级缓存、主机内存二级缓存与"
    "NVMe 固态硬盘三级缓存。一级缓存存放最近被访问的键值对与状态张量，访问速度最快"
    "但容量有限；当显存放不下时，旧的张量会被逐出到主机内存，仍然保留供后续请求复用；"
    "更久远的数据则会写入三级缓存，通过扩展文件后端按区块持久化。这套分级存储的目标是"
    "让长上下文的智能体在连续多轮对话中，只有新增内容需要真正计算，而历史内容全部命中缓存，"
    "从而大幅降低热会话下一轮的响应延迟。我们通过实验测量不同历史长度下，追加少量新内容时的"
    "首令牌延迟与整体端到端延迟，以验证三级缓存是否成功兜住了历史。"
)

# Common delimiters to make repeated paragraphs parse as distinct-ish but
# deterministic.  Kept simple: paragraph index prefix.
def build_history_prompt(target_tokens, tokenizer, session_seed):
    """Build a single user message whose token count is >= target_tokens.
    Prefix with a unique session marker so different sessions have distinct
    prefixes (independent radix branches).  Returns (text, n_tokens)."""
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
    if lock is not None:
        lock.acquire()
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "15",
             "http://127.0.0.1:%s/metrics" % os.environ.get("SGLANG_PORT", "8024")],
            capture_output=True, text=True)
        return r.stdout
    finally:
        if lock is not None:
            lock.release()


def parse_metrics(text):
    """Reuse common.parse_metrics (extended prefixes for cache-hit sources)."""
    if common is None:
        return {}
    try:
        return common.parse_metrics(text)
    except Exception:
        return {}


def metric_delta(before, after, name, label_contains=None):
    if common is None:
        return None
    try:
        return common.metric_delta(before, after, name, label_contains)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", required=True, choices=sorted(TIER_TARGETS))
    ap.add_argument("--sessions", type=int, default=3,
                    help="independent sessions per tier (default 3)")
    ap.add_argument("--cold-max-new", type=int, default=12,
                    help="max_tokens for the COLD (history-build) completion -- "
                         "keep short so the warm delta stays small")
    ap.add_argument("--warm-max-new", type=int, default=64,
                    help="max_tokens for the WARM (delta) completion")
    ap.add_argument("--warm-repeats", type=int, default=3,
                    help="repeated warm turns per session (append same delta) "
                         "-- averages out jitter; default 3")
    ap.add_argument("--evidence-dir", default="/root/evidence-warmctx",
                    help="output dir for run-<ts>/ artifacts")
    ap.add_argument("--client-max-time", type=int, default=900,
                    help="per-request client timeout (seconds)")
    ap.add_argument("--snapshot-interval", type=float, default=5.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        print("DRY_RUN_OK tier=%s sessions=%d target=%d"
              % (args.tier, args.sessions, TIER_TARGETS[args.tier]))
        return 0

    if common is None:
        print("FATAL: common.py not importable (run from /root)", file=sys.stderr)
        return 2

    try:
        from transformers import AutoTokenizer
    except Exception as e:
        print("FATAL: transformers unavailable: %s" % e, file=sys.stderr)
        return 2
    tok = AutoTokenizer.from_pretrained(
        os.environ.get("MODEL_PATH", "/root/models/Qwen3.5-9B-w4a16"))

    target = TIER_TARGETS[args.tier]
    run_dir = os.path.join(args.evidence_dir,
                           "run-%s" % time.strftime("%Y%m%d-%H%M%S"))
    turns_dir = os.path.join(run_dir, "turns")
    os.makedirs(turns_dir, exist_ok=True)
    lock = threading.Lock()
    join_fh = open(os.path.join(run_dir, "join.log"), "a")
    t_start = time.time()

    def post(payload, out_prefix, max_time):
        """POST via common.run_client_inproc. Returns (rc, rec, sx, m_before,
        m_after)."""
        m_before = parse_metrics(fetch_metrics(lock))
        ts_start = time.time()
        rc, meta = common.run_client_inproc(out_prefix + ".payload.json",
                                            out_prefix, max_time)
        ts_end = time.time()
        m_after = parse_metrics(fetch_metrics(lock))
        sx = common.extract_sglext(meta, out_prefix + ".body")
        return rc, meta, sx, ts_start, ts_end, m_before, m_after

    rows = []
    for s in range(1, args.sessions + 1):
        seed = s
        hist_text, hist_n = build_history_prompt(target, tok, seed)
        # COLD turn: full history, short completion
        cold_payload = {
            "model": os.environ.get("SERVED", "qwen3.5-9b-gptq"),
            "messages": [{"role": "user", "content": hist_text}],
            "max_tokens": args.cold_max_new,
            "temperature": 0.0,
            "stream": True,
        }
        cp = os.path.join(turns_dir, "s%d" % s, "t0-cold")
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        with open(cp + ".payload.json", "w") as f:
            json.dump(cold_payload, f, ensure_ascii=False)
        rc, meta, sx, ts_s, ts_e, mb, ma = post(cold_payload, cp,
                                                args.client_max_time)
        # assistant turn text from cold response
        asst_text, _ = common.output_text(meta)
        row = _mkrow(args.tier, s, "cold", meta, sx, ts_s, ts_e, mb, ma,
                     hist_n, rc)
        rows.append(row)
        join_fh.write(json.dumps(row) + "\n")
        join_fh.flush()
        print("[%s] s%d cold rc=%d prompt=%d wall=%s ttft=%s"
              % (args.tier, s, rc, hist_n, meta.get("wall_s"),
                 meta.get("ttft_s")), flush=True)

        # WARM turns: history + assistant + small new user delta, repeated.
        delta_text = ("现在请用一句话总结刚才这段资料的核心观点，不要展开。")
        for r in range(1, args.warm_repeats + 1):
            warm_payload = {
                "model": os.environ.get("SERVED", "qwen3.5-9b-gptq"),
                "messages": [
                    {"role": "user", "content": hist_text},
                    {"role": "assistant", "content": asst_text},
                    {"role": "user", "content": delta_text},
                ],
                "max_tokens": args.warm_max_new,
                "temperature": 0.0,
                "stream": True,
            }
            wp = os.path.join(turns_dir, "s%d" % s, "t1-warm-r%d" % r)
            with open(wp + ".payload.json", "w") as f:
                json.dump(warm_payload, f, ensure_ascii=False)
            rc2, meta2, sx2, ts_s2, ts_e2, mb2, ma2 = post(
                warm_payload, wp, args.client_max_time)
            row2 = _mkrow(args.tier, s, "warm", meta2, sx2, ts_s2, ts_e2,
                          mb2, ma2, hist_n, rc2)
            rows.append(row2)
            join_fh.write(json.dumps(row2) + "\n")
            join_fh.flush()
            print("[%s] s%d warm r%d rc=%d wall=%s ttft=%s"
                  % (args.tier, s, r, rc2, meta2.get("wall_s"),
                     meta2.get("ttft_s")), flush=True)
    join_fh.close()

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

    warm = [r for r in rows if r["turn"] == "warm"]
    cold = [r for r in rows if r["turn"] == "cold"]
    summary = {
        "status": "done",
        "tier": args.tier, "target_tokens": target,
        "sessions": args.sessions, "warm_repeats": args.warm_repeats,
        "cold_requests": len(cold), "warm_requests": len(warm),
        "run_dir": run_dir,
        "ts_start": round(t_start, 3),
        "ts_end": round(time.time(), 3),
        "elapsed_s": round(time.time() - t_start, 1),
    }
    with open(os.path.join(run_dir, "verdict.json"), "w") as f:
        json.dump(summary, f, indent=1, default=str)
    print("WARMCTX_DONE tier=%s run_dir=%s cold=%d warm=%d"
          % (args.tier, run_dir, len(cold), len(warm)), flush=True)
    return 0


def _mkrow(tier, session, turn, meta, sx, ts_s, ts_e, mb, ma, hist_n, rc):
    u = (sx or {}).get("usage") or meta.get("usage") or {}
    ctd = (sx or {}).get("cached_tokens_details") or {}
    row = {
        "tier": tier, "session": session, "turn": turn,
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
        "prefill_input_delta": metric_delta(mb, ma,
            "sglang:prefill_effective_tokens_total", 'mode="input"'),
        "prefill_devicehit_delta": metric_delta(mb, ma,
            "sglang:prefill_effective_tokens_total", 'mode="device_hit"'),
        "prefill_hosthit_delta": metric_delta(mb, ma,
            "sglang:prefill_effective_tokens_total", 'mode="host_hit"'),
        "prefill_storagehit_delta": metric_delta(mb, ma,
            "sglang:prefill_effective_tokens_total", 'mode="storage_hit"'),
    }
    return row


if __name__ == "__main__":
    sys.exit(main())
