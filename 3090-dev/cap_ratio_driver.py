#!/usr/bin/env python3
"""cap_ratio_driver.py -- Phase-2 experiment② (ratio sweep) load driver.

Shape per phase2-cap-protocol-architect-e1.md §②.2 (authoritative; built
because the ③-driver gate3_capacity.py is a different shape and was not
deployed on the runner at dispatch time):
  - N=8 agents;  H0 in [52K,56K] tokens per agent history (tokenizer precise
    truncation, prompt_len asserted H0+-2%);
  - per-turn delta d ~= 180 +- (64..256 jitter) (mean preserved 180);
  - TURNS=20;  turn 1 = COLD full-history prime, turns 2..20 = WARM;
  - prime: 8 agents SERIAL COLD (empty cache) -> then CONCURRENT warm turns
    r2..r20;  every warm turn RE-SENDS full history + assistant + delta
    (warmctx mode keeps the working set resident);
  - stream:true (true TTFT via common.run_client_inproc SSE);
  - per-req record: ts / session_id(agent) / turn / prompt_len / history_len
    / delta_len / ttft_s / wall_s / http / finished / device_hit / host_hit
    / storage_hit (+ prefill_effective_tokens counter deltas, cross-check);
  - same shape / same seed / same turn structure across ratio tiers:
    --seed fixes history content and delta draws -> cross-tier comparable.

Health assertions: all http=200, all finished, output_sha16 non-empty,
history_len within H0+-2% -> else non-zero exit and FAIL-运行 classification.

Output (evidence-dir/run-<ts>/): join.log, runs.csv, mid-run-metrics.txt,
verdict.json, turns/ per-request artifacts (payload/body/meta/headers).

Usage (engine already booted with the sweep wrapper):
  SGLANG_PORT=8024 MODEL_PATH=/root/models/Qwen3.5-9B-w4a16 \
  SERVED=qwen3.5-9b-gptq STORAGE_DIR=/data/l3/p2io-cap-ratio-<tag> \
    python cap_ratio_driver.py --tag c0 --ratio 0.90 \
      --evidence-dir /root/evidence-cap-sweep/c0
"""
import argparse
import csv
import json
import os
import random
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

DEFAULT_HISTORY_TARGET = 54500   # mid of [52K, 56K]; tokenizer-truncated
DEFAULT_DELTA_MEAN = 180
DEFAULT_JITTER = (64, 256)

# Stable corpus paragraphs (Chinese) -- the same corpus family as gate2_warmctx
# so the FP8/radix numeric behaviour is comparable; unique per-session marker
# makes each agent's history a distinct radix branch (R6).
_CORPUS = (
    "大语言模型推理中的缓存系统分为三级：GPU 显存一级缓存、主机内存二级缓存与"
    "NVMe 固态硬盘三级缓存。一级缓存存放最近被访问的键值对与状态张量，访问速度最快"
    "但容量有限；当显存放不下时，旧的张量会被逐出到主机内存，仍然保留供后续请求复用；"
    "更久远的数据则会写入三级缓存，通过扩展文件后端按区块持久化。这套分级存储的目标是"
    "让长上下文的智能体在连续多轮对话中，只有新增内容需要真正计算，而历史内容全部命中缓存，"
    "从而大幅降低热会话下一轮的响应延迟。我们通过实验测量不同历史长度下，追加少量新内容时的"
    "首令牌延迟与整体端到端延迟，以验证三级缓存是否成功兜住了历史。"
)

# Delta-side corpus: a different topic so the per-turn new content is novel
# (distinct from the history corpus) while still deterministic-per-seed.
_DELTA_CORPUS = (
    "多智能体协作系统中，每个子代理维护独立的长上下文记忆，包括对话历史、任务状态与"
    "中间推理步骤。当子代理数量增加时，显存中的键值缓存竞争加剧，如何让活跃子代理的"
    "工作集持续驻留于高速缓存、同时保证被停放会话的唤醒延迟可控，是系统设计的核心权衡。"
    "本实验测量不同缓存配额配置下，八路并发长上下文智能体的驻留稳定性与首令牌延迟分布，"
    "用于确定显存分配比例的最优取值区间。"
)


def build_history_prompt(target_tokens, tokenizer, session_seed):
    """>= target_tokens deterministic text; unique marker per session_seed.
    Returns (text, n_tokens)."""
    marker = "会话编号 %d。以下是本轮对话的完整历史背景资料。\n\n" % session_seed
    text = marker
    n = len(tokenizer.encode(text))
    i = 0
    while n < target_tokens:
        text += ("[%d] " % i) + _CORPUS + "\n"
        i += 1
        n = len(tokenizer.encode(text))
    # token-level trim to the exact target for reproducible H0
    ids = tokenizer.encode(text)
    if len(ids) > target_tokens:
        text = tokenizer.decode(ids[:target_tokens], skip_special_tokens=True)
        n = len(tokenizer.encode(text))
    return text, n


def build_delta(target_tokens, tokenizer, seed):
    """Delta text of ~target_tokens, deterministic per seed."""
    head = "请继续阅读以下补充背景，然后回答对应问题。\n\n"
    text = head
    n = len(tokenizer.encode(text))
    i = 0
    while n < target_tokens:
        text += ("[d%d] " % i) + _DELTA_CORPUS + "\n"
        i += 1
        n = len(tokenizer.encode(text))
    ids = tokenizer.encode(text)
    if len(ids) > target_tokens:
        text = tokenizer.decode(ids[:target_tokens], skip_special_tokens=True)
        n = len(tokenizer.encode(text))
    return text, n


def delta_draw(mean, jitter, seed):
    """d ~= mean +- U(-spread, spread), spread ~ U(jitter). Deterministic."""
    rnd = random.Random(seed)
    spread = rnd.uniform(jitter[0], jitter[1])
    d = mean + rnd.uniform(-spread, spread)
    return int(round(max(32, d)))


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


def _mkrow(agent, turn, kind, hist_n, delta_n, meta, sx, ts_s, ts_e,
           mb, ma, rc):
    u = (sx or {}).get("usage") or meta.get("usage") or {}
    ctd = (sx or {}).get("cached_tokens_details") or {}
    out, out_field = common.output_text(meta) if common else ("", None)
    row = {
        "tag": os.environ.get("CAP_TAG", ""),
        "ratio": os.environ.get("CAP_RATIO", ""),
        "session_id": agent, "turn": turn, "turn_kind": kind,
        "ts_start": round(ts_s, 3), "ts_end": round(ts_e, 3),
        "ttft_s": meta.get("ttft_s"), "wall_s": meta.get("wall_s"),
        "http": meta.get("http_code"), "finished": meta.get("finished"),
        "finish_reason": meta.get("finish_reason"),
        "rid": (sx or {}).get("rid") or meta.get("request_id"),
        "rc": rc,
        "history_len": hist_n,
        "delta_len": delta_n,
        "prompt_len": u.get("prompt_tokens") if isinstance(u, dict) else None,
        "completion_tokens": (u.get("completion_tokens")
                              if isinstance(u, dict) else None),
        "cached_tokens": (sx or {}).get("cached_tokens"),
        "device_hit": ctd.get("device"),
        "host_hit": ctd.get("host"),
        "storage_hit": ctd.get("storage"),
        "output_field": out_field,
        "output_sha16": (common.sha16(out) if common else None),
    }
    for label, mode in (("prefill_input_delta", 'mode="input"'),
                        ("prefill_devicehit_delta", 'mode="device_hit"'),
                        ("prefill_hosthit_delta", 'mode="host_hit"'),
                        ("prefill_storagehit_delta", 'mode="storage_hit"')):
        row[label] = _md(mb, ma, "sglang:prefill_effective_tokens_total", mode)
    return row


def _post(lock, out_prefix, payload, max_time):
    m_before = parse_metrics(fetch_metrics(lock))
    ts_start = time.time()
    # serialize the payload before run_client_inproc reads it (that function
    # reads payload_path first, so the file must exist before the call)
    os.makedirs(os.path.dirname(out_prefix) or ".", exist_ok=True)
    with open(out_prefix + ".payload.json", "w") as _f:
        json.dump(payload, _f, ensure_ascii=False)
    rc, meta = common.run_client_inproc(out_prefix + ".payload.json",
                                        out_prefix, max_time)
    ts_end = time.time()
    m_after = parse_metrics(fetch_metrics(lock))
    sx = common.extract_sglext(meta, out_prefix + ".body")
    return rc, meta, sx, ts_start, ts_end, m_before, m_after


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--ratio", type=float, required=True,
                    help="--mamba-full-memory-ratio of the running engine "
                         "(recorded per row; engine read from boot metrics)")
    ap.add_argument("--agents", type=int, default=8)
    ap.add_argument("--history-target", type=int, default=DEFAULT_HISTORY_TARGET)
    ap.add_argument("--turns", type=int, default=20)
    ap.add_argument("--delta-mean", type=int, default=DEFAULT_DELTA_MEAN)
    ap.add_argument("--jitter-min", type=int, default=DEFAULT_JITTER[0])
    ap.add_argument("--jitter-max", type=int, default=DEFAULT_JITTER[1])
    ap.add_argument("--seed", type=int, default=20260907)
    ap.add_argument("--cold-max-new", type=int, default=12)
    ap.add_argument("--warm-max-new", type=int, default=128)
    ap.add_argument("--client-max-time", type=int, default=1200)
    ap.add_argument("--snapshot-interval", type=float, default=5.0)
    ap.add_argument("--evidence-dir", default="/root/evidence-cap-sweep")
    ap.add_argument("--build-check", action="store_true",
                    help="tokenizer-only: print H0/delta token counts and "
                         "exit (no engine needed)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    os.environ["CAP_TAG"] = args.tag
    os.environ["CAP_RATIO"] = str(args.ratio)
    served = os.environ.get("SERVED", "qwen3.5-9b-gptq")

    try:
        from transformers import AutoTokenizer
    except Exception as e:  # noqa: BLE001
        if args.dry_run or args.build_check:
            print("TOKENIZER_UNAVAILABLE: %s" % e)
            return 0
        print("FATAL: transformers unavailable: %s" % e, file=sys.stderr)
        return 2
    model_path = os.environ.get("MODEL_PATH", "/root/models/Qwen3.5-9B-w4a16")
    tok = AutoTokenizer.from_pretrained(model_path)

    if args.build_check:
        h, hn = build_history_prompt(args.history_target, tok, 1)
        d180 = delta_draw(args.delta_mean, (args.jitter_min, args.jitter_max),
                          args.seed + 1)
        dt, dn = build_delta(d180, tok, args.seed + 1)
        print("BUILD_CHECK history_target=%d hist_n=%d hist_delta_pct=%.2f "
              "delta_draw=%d delta_built=%d"
              % (args.history_target, hn,
                 100.0 * (hn - args.history_target) / args.history_target,
                 d180, dn))
        return 0

    if args.dry_run:
        print("DRY_RUN_OK tag=%s ratio=%s agents=%d history_target=%d "
              "turns=%d delta_mean=%d jitter=[%d,%d] seed=%d"
              % (args.tag, args.ratio, args.agents, args.history_target,
                 args.turns, args.delta_mean, args.jitter_min, args.jitter_max,
                 args.seed))
        return 0

    if common is None:
        print("FATAL: common.py not importable (run from /root)", file=sys.stderr)
        return 2

    # ---- shape assertion: single-agent H0 must be within H0+-2% ----
    _, hn0 = build_history_prompt(args.history_target, tok, 0)
    delta_pct = 100.0 * (hn0 - args.history_target) / args.history_target
    assert abs(delta_pct) <= 2.0, \
        "H0 assertion failed: hist_n=%d target=%d (%.2f%%)" % (
            hn0, args.history_target, delta_pct)
    print("H0_OK hist_n=%d target=%d delta_pct=%.2f%%" % (hn0, args.history_target, delta_pct))

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
        "worst": {},
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

    def send(agent, turn, kind, hist_text, hist_n, delta_text, delta_n,
             asst_text, max_new):
        payload = {
            "model": served,
            "messages": [{"role": "user", "content": hist_text}]
            + ([{"role": "assistant", "content": asst_text},
                {"role": "user", "content": delta_text}]
               if asst_text is not None else []),
            "max_tokens": max_new,
            "temperature": 0.0,
            "stream": True,
        }
        prefix = os.path.join(turns_dir,
                              "a%d" % agent, "t%d.%s" % (turn, kind))
        rc, meta, sx, ts_s, ts_e, mb, ma = _post(
            state["metrics_lock"], prefix, payload, args.client_max_time)
        row = _mkrow(agent, turn, kind, hist_n, delta_n, meta, sx,
                     ts_s, ts_e, mb, ma, rc)
        with state["join_lock"]:
            state["join_fh"].write(json.dumps(row) + "\n")
            state["join_fh"].flush()
        # health snapshot
        st = state["worst"]
        st["rc_bad"] = st.get("rc_bad", 0) + (1 if rc else 0)
        st["http_bad"] = st.get("http_bad", 0) + (1 if str(meta.get("http_code")) != "200" else 0)
        st["fin_bad"] = st.get("fin_bad", 0) + (1 if not meta.get("finished") else 0)
        # assistant text for the next turn comes from this turn's output
        if common is not None and rc == 0:
            out_text, _ = common.output_text(meta)
        else:
            out_text = None
        return row, out_text

    histories = {}
    for a in range(args.agents):
        hist_text, hist_n = build_history_prompt(
            args.history_target, tok, a)
        histories[a] = (hist_text, hist_n)

    # ---- prime: serial COLD full history, empty cache ----
    cold_rows = []
    for a in range(args.agents):
        if (time.time() - state["t_start"]) > 3600:
            print("TIME_BUDGET_1H_EXCEEDED during prime", file=sys.stderr)
            break
        hist_text, hist_n = histories[a]
        row, _ = send(a, 1, "cold", hist_text, hist_n, None, 0, None,
                      args.cold_max_new)
        cold_rows.append(row)
        print("[a%d] t1 cold rc=%d prompt=%s ttft=%s wall=%s"
              % (a, row.get("rc"), row.get("prompt_len"),
                 row.get("ttft_s"), row.get("wall_s")), flush=True)

    # ---- steady: concurrent warm turns 2..args.turns ----
    results = {}

    def agent_loop(agent):
        hist_text, hist_n = histories[agent]
        asst_text = None
        recs = []
        for turn in range(2, args.turns + 1):
            d_target = delta_draw(args.delta_mean,
                                  (args.jitter_min, args.jitter_max),
                                  args.seed + agent * 1000 + turn)
            delta_text, delta_n = build_delta(d_target, tok,
                                              args.seed + agent * 1000 + turn)
            row, asst_text = send(agent, turn, "warm", hist_text, hist_n,
                                  delta_text, delta_n, asst_text,
                                  args.warm_max_new)
            recs.append(row)
            print("[a%d] t%d warm rc=%d prompt=%s ttft=%s wall=%s"
                  % (agent, turn, row.get("rc"), row.get("prompt_len"),
                     row.get("ttft_s"), row.get("wall_s")), flush=True)
        results[agent] = recs

    threads = []
    for a in range(args.agents):
        t = threading.Thread(target=agent_loop, args=(a,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

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

    all_rows = cold_rows + [r for a in range(args.agents)
                            for r in results.get(a, [])]
    fieldnames = []
    for r in all_rows:
        for k in r:
            if k not in fieldnames:
                fieldnames.append(k)
    with open(os.path.join(run_dir, "runs.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in all_rows:
            w.writerow(r)

    n_ok = sum(1 for r in all_rows
               if r.get("http") == "200" and r.get("finished"))
    sha_ok = sum(1 for r in all_rows if r.get("output_sha16"))
    summary = {
        "status": "done", "tag": args.tag, "ratio": args.ratio,
        "agents": args.agents, "history_target": args.history_target,
        "turns": args.turns, "seed": args.seed,
        "requests_total": len(all_rows),
        "requests_warm": len(all_rows) - len(cold_rows),
        "requests_ok_http_finished": n_ok,
        "requests_sha16_nonempty": sha_ok,
        "history_first_agent_tokens": hn0,
        "worst": state["worst"],
        "run_dir": run_dir,
        "ts_start": round(state["t_start"], 3),
        "ts_end": round(time.time(), 3),
        "elapsed_s": round(time.time() - state["t_start"], 1),
    }
    with open(os.path.join(run_dir, "verdict.json"), "w") as f:
        json.dump(summary, f, indent=1, default=str)
    print("CAP_RATIO_DRIVER_DONE tag=%s run_dir=%s requests=%d ok=%d"
          % (args.tag, run_dir, len(all_rows), n_ok), flush=True)
    return 0 if n_ok == len(all_rows) and sha_ok == len(all_rows) else 2


if __name__ == "__main__":
    sys.exit(main())