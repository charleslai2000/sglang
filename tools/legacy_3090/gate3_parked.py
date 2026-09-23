#!/usr/bin/env python3
"""gate3_parked.py -- Phase-2 experiment④: parked-session scale / random resume.

CORRECTED SEMANTICS (2026-09-07 user ruling -- authoritative, DO NOT revert)
---------------------------------------------------------------------------
A session is NOT parked by the scheduler WAIT_CAPACITY / /pause_generation.
A session becomes "parked" the moment it finishes one turn: it leaves the
active set, its GPU cache footprint is allowed to drain (Device -> Host L2 ->
L3 extent) through NATURAL LRU/eviction pressure caused by the OTHER active
sessions, while its history stays reachable in the cache.  After a random
interval (minutes / tens of turns of unrelated traffic) the session is picked
again for its next turn, and we measure how well the cache serves that resume.

WHY this is the real-observable thing
-------------------------------------
Real Claude traffic has 100s-1000s of sessions alive; only c8 active at any
instant (frozen engine config c8 = --max-running-requests 8).  The GPU/Host
layers cannot physically hold all 100-1000 histories at once (working set >>
single-layer capacity), so most resume requests MUST be served from Host L2
or L3 extent.  That is the business question: with the three-tier cache, how
good is the resume TTFT / hit distribution / recompute when the residency is
L2/L3 rather than Device?

No scheduler pause/wait endpoint is touched.  No headroom is artificially
created.  The cache is left to do what it does under natural churn.

TWO SEMANTIC MODES (2026-09-07 user ruling -- authoritative)
------------------------------------------------------------
The SAME parking mechanics (build S prefixes -> rotate active<=c8 -> retire ->
natural evict -> re-pick) run under one of two explicit modes.  The mode only
changes what is EXPECTED and what is REPORTED, never the driver behaviour
(no WAIT/pause, active cap, cooldown, fixed seed are identical in both).

  --mode fit      (S=100, the L3-fit formal capacity test)
    S small enough that ~55K/session histories can be kept resident in
    Host/L3 (200G extent holds ~170 session @55K).  Expect high Host/L3 hit,
    minimal recycle.  Reports the full architect protocol §④.3 judgement:
    random-resume TTFT p50/p95/p99, >30s/>60s ratios, turns/hour, Host/L3
    residency (host_hit+storage_hit), storage_hit detail, recompute fraction.

  --mode oversub  (S=500/1000, L3 oversubscription STRESS)
    S is an EXPLICIT oversubscription of the 200G L3 extent.  This is NOT a
    "can we keep everything resident" test -- by construction most sessions'
    histories cannot stay resident and the extent MUST recycle/GC.  Extent
    recycle is ALLOWED and RECORDED (never treated as a fault).  Reports the
    degradation-vs-S curve: L3 residency / recycle-GC (evicted/backuped/
    load_back deltas + extent_recycle events) / recompute fraction / random
    resume TTFT p50/p95/p99 / >30s/>60s ratios / turns/hour, all comparable
    across S under the same H0/seed/active/wake lambda.

FORBIDDEN CLAIM
---------------
This driver + gate3_parked_analyze.py MUST NOT claim "the 200G L3 can fully
park S x 55K sessions".  S=500/1000 oversub results are reported only within
the "oversubscription stress, degradation curve" framework.  A full-retention
capacity figure is only ever computed for S=100 (fit) from the per-session
measured L3 bytes, and any claim about what larger NVMe would be needed for
full retention is left to a LATER decision (ledger:2476), never stated here.

Scenario
--------
Build S parked-session prefixes (each ~50-80K tokens, from the warmctx-type
long-history generator).  Then run R rounds of "pick K sessions, turn active,
issue one turn, retire them":

  active window   = --active (the engine's c8 by default, but keep it a knob
                    so the driver can also probe a/k/2K sensitivities).
  pick rule       = buried.turn_order weighted by --pick-lam (higher lam =
                    larger multi-turn per-session bias, emulating a chat
                    with a hot few); sessions that have never run come first.
  turn            = a WARM-shaped turn: full history + previous assistant +
                    a short new user delta.  The history was cold-built in
                    build phase; after retirement the cache MAY evict it.
  retire          = after its turn the session is removed from the active set
                    immediately (its next turn waits --park-min/max seconds on
                    average --pick-lam turns of unrelated traffic).
  metrics         = a high-cadence sampler (default 2s) capturing the pool /
                    host gauges; a coarse sampler (default 60s) captures the
                    same gauges plus Host/L3 residency (hicache_* gauges) and
                    -- if it exists -- the L3 extent physical footprint
                    (via st_blocks of the storage dir's hicache.data*; the L3
                    extent file is SPARSE, so logical ls -l bytes are NOT the
                    footprint -- physical du is.  default off; pass
                    --l3-backend-dir to enable).
  obey-ac        = when true (default) we never issue more than --active
                    concurrent in-flight turns: a session whose turn is
                    pending waits for a free slot.  (We do not coordinate
                    with the engine's own c8 scheduler; this is a client-side
                    cap that keeps the driver civil under tests.  To instead
                    saturate the engine's queue, pass --obey-ac false.)
  busy-skip      = when the picker rolls a session that is already in flight,
                    that "wake" is consumed but counted as `busy_skip` -- the
                    session's next turn happens later.  (The engine may still
                    hold a stale queue entry; a skipped wake does not add an
                    in-flight request.)

Bookkeeping for analysis
------------------------
Every resume row carries: ts_start/ts_end, ttft_s/wall_s, http/finished,
cached_tokens_details (device/host/storage per-request), the session's age at
wake (seconds since the PREVIOUS turn's end -- its parked duration), its turn
index, the round number it was picked in, history_tokens and the per-request
prefill_effective_tokens deltas (input/device_hit/host_hit/storage_hit).
Together with the gauge sampler and the engine's own counters this lets the
analysis answer:

  random-resume TTFT, device/host/L3 hit proportions, recompute tokens,
  turns/hour, aggregate TPS, Host/L3 occupancy, recycle/GC (evicted/
  backup tokens), session age vs resume latency.

No engine pause/wait endpoint is called.  No new engine counters or TTls:
the driver only reads existing /metrics and speaks the normal
/v1/chat/completions SSE API.

Usage
-----
  SGLANG_PORT=8024 MODEL_PATH=/root/models/Qwen3.5-9B-w4a16 \
  python gate3_parked.py \
      --sessions 500 --build-tier 64k --rounds 60 --active 8 \
      --park-min 30 --park-max 300 --pick-lam 1.0 --obey-ac \
      --evidence-dir /root/evidence-parked-500c8

  unit sanity (no engine needed):
  python gate3_parked.py --dry-run --sessions 50 --active 4 --rounds 2
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

# 50K/55K/64K/80K tier targets (history tokens per built session).  The
# authoritative ④ semantics use H0=55K per session (ledger:2473-2475), so
# 55k is the DEFAULT tier.  64k (64030 warmctx precedent) kept for parity with
# gate3_capacity; default previously pointed at "64k" which was NOT in this
# map (argparse rejects a default not in choices -> crash on no --build-tier).
BUILD_TIERS = {
    "50k": 50000,
    "55k": 55000,
    "64k": 64000,
    "80k": 80000,
}

# L3-fit anchor: how many sessions a 200G extent can keep resident at H0=55K.
# 55K x ~15.27KB/token (FP8 cell) ~= 840MB/session -> ~170 sessions.  S=100 is
# the fit anchor; S=500/1000 are EXPLICIT oversubscription (ledger:2474).
L3_FIT_SESSIONS = 170
FIT_SESSIONS = 100
OVERSUB_SESSIONS = (500, 1000)

# Default fit park ladder (spec e5 §1.2 / §6.2 #1): cohort park-window bands
# deliberately manufacture the four Gate B hit states:
#   HOT  (park 0-30s)   -> GPU/L1 resident samples
#   MID  (park 120-300s)-> Host-ready samples
#   COLD (park 600-2400s)-> RH-staged (RH ON) / L3-on-demand (RH OFF) samples
# n_hot=5 / n_mid=30 / n_cold=65 (of S=100).  It is an INJECTION bias only;
# analyze re-buckets by measured age_at_wake_s.
FIT_PARK_LADDER = [
    ("HOT", 0, 30, 5),
    ("MID", 120, 300, 30),
    ("COLD", 600, 2400, 65),
]


def parse_park_ladder(spec):
    """Parse a --park-ladder CLI spec into [(name, min_s, max_s, n), ...].
    Format: "HOT:0-30@5,MID:120-300@30,COLD:600-2400@65".  Returns [] on empty."""
    if not spec:
        return []
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            name, rest = part.split(":", 1)
            rng_s, cnt_s = rest.split("@", 1)
            lo, hi = rng_s.split("-", 1)
            out.append((name.strip(), float(lo), float(hi), int(cnt_s)))
        except (ValueError, KeyError) as e:
            raise argparse.ArgumentTypeError(
                "bad park-ladder segment %r: %s" % (part, e))
    return out

# Tunables that define the "shape" of the churn (documented for the reader).
_CORPUS = (  # stable Chinese corpus; equivalent to gate3_capacity
    "大语言模型推理中的缓存系统分为三级：GPU 显存一级缓存、主机内存二级缓存与"
    "NVMe 固态硬盘三级缓存。一级缓存存放最近被访问的键值对与状态张量，访问速度最快"
    "但容量有限；当显存放不下时，旧的张量会被逐出到主机内存，仍然保留供后续请求复用；"
    "更久远的数据则会写入三级缓存，通过扩展文件后端按区块持久化。这套分级存储的目标是"
    "让长上下文的智能体在连续多轮对话中，只有新增内容需要真正计算，而历史内容全部命中缓存，"
    "从而大幅降低热会话下一轮的响应延迟。我们通过实验测量不同历史长度下，追加少量新内容时的"
    "首令牌延迟与整体端到端延迟，以验证三级缓存是否成功兜住了历史。"
)
_DELTA = "现在请用一句话总结刚才这段资料的核心观点，不要展开。"


def build_history_prompt(target_tokens, tokenizer, session_seed):
    """Same history builder as gate3_capacity -- single long history, distinct
    radix branch per seed."""
    marker = "会话编号 %d。以下是本轮对话的完整历史背景资料。\n\n" % session_seed
    text = marker
    n = len(tokenizer.encode(text))
    i = 0
    while n < target_tokens:
        text += ("[%d] " % i) + _CORPUS + "\n"
        i += 1
        n = len(tokenizer.encode(text))
    return text, n


# ---------------------------------------------------------------------------
# Deterministic churn primitives (pure, unit-testable)
# ---------------------------------------------------------------------------

def poisson_spacing(rng, lam):
    """--pick-lam as a mean inter-arrival count: useful for the park schedule
    (a session is on average every `lam` turns eligible again)."""
    return max(0, int(rng.expovariate(1.0 / max(lam, 1e-9))))


class Sched:
    """Bounded deterministic random-resume scheduler.

    Data kept tiny: only the per-session turn-eligibility bookkeeping.  This
    is what makes the unit sanity of the real churn logic possible without an
    engine: you can feed it a fake transport and assert on the wake order.
    """

    def __init__(self, num_sessions, active, rng,
                 park_min_s=0.0, park_max_s=0.0, pick_lam=1.0,
                 ladder=None):
        self.n = num_sessions
        self.active = active
        self.rng = rng
        self.park_min = park_min_s
        self.park_max = park_max_s
        self.lam = pick_lam
        # Park ladder (Gate B cohort windows): a list of (name, min_s, max_s,
        # n_sessions) bands assigned deterministically to session id slices.
        # When present, _park_seconds uses the session's cohort band instead
        # of the uniform --park-min/--park-max window.  The ladder is an
        # INJECTION bias, not a classifier: analyze must re-bucket by the
        # measured age_at_wake_s (spec §2/OD4).
        self.ladder = ladder or []
        self.cohort = [None] * num_sessions
        start = 0
        for name, lo, hi, cnt in self.ladder:
            for sid in range(start, min(start + cnt, num_sessions)):
                self.cohort[sid] = (name, lo, hi)
            start += cnt
        # park window drawn per retire (wall-clock seconds); the session is
        # eligible again only when both the wall-clock window AND the
        # turn-count cooldown have elapsed.  (The turn-count cooldown models
        # "the session missed its window because OTHER sessions were busy".)
        self.park_window = [0.0] * num_sessions
        self.retired_at = [None] * num_sessions  # wall-clock retire ts
        # turn-count cooldown: eligible after this many OTHER turns issued
        self.eligible_in_turns = [0] * num_sessions
        self.last_turn_ts = [None] * num_sessions
        self.turn_count = [0] * num_sessions

    # -- transport-independent core (testable) --
    def _park_seconds(self, sid=0):
        for name, lo, hi, cnt in self.ladder:
            if self.cohort[sid] is not None and self.cohort[sid][0] == name:
                if hi <= lo:
                    return lo
                return self.rng.uniform(lo, hi)
        if self.park_max <= self.park_min:
            return self.park_min
        return self.rng.uniform(self.park_min, self.park_max)

    def retire(self, sid, now):
        self.eligible_in_turns[sid] = poisson_spacing(self.rng, self.lam)
        self.park_window[sid] = self._park_seconds(sid)
        self.retired_at[sid] = now
        self.last_turn_ts[sid] = now

    def cohort_of(self, sid):
        """Expose a session's ladder cohort (name) for row tagging / analyze."""
        c = self.cohort[sid]
        return c[0] if c else None

    def due(self, sid, now, turns_so_far):
        if self.last_turn_ts[sid] is None:
            return True  # never-run session is always eligible
        turns_ok = (turns_so_far - self.turn_count[sid]) >= self.eligible_in_turns[sid]
        if self.retired_at[sid] is None:
            return turns_ok
        clock_ok = (now - self.retired_at[sid]) >= self.park_window[sid]
        return turns_ok and clock_ok

    def pick(self, now, turns_so_far):
        """Return up to `active` session ids that are eligible, or []."""
        due_ = [s for s in range(self.n) if self.due(s, now, turns_so_far)]
        if not due_:
            return []
        # prioritize never-run sessions (they must all get a first turn),
        # otherwise weighted by lam over the pending-eligible population.
        never = [s for s in due_ if self.last_turn_ts[s] is None]
        if never:
            chosen = never
        else:
            chosen = self.rng.sample(due_, min(self.active, len(due_)))
        return chosen[:self.active]


# ---------------------------------------------------------------------------
# Metrics / IO helpers
# ---------------------------------------------------------------------------

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


def _first_val(snap, prefix):
    """First value in a parsed metrics dict whose key starts with prefix."""
    for k, v in snap.items():
        if k.startswith(prefix):
            return v
    return None


def extent_footprint(l3_dir):
    """Physical L3 footprint (bytes) of the extent backend data files under
    l3_dir.  The extent file is SPARSE (ftruncate'd to file_size at boot), so
    `ls -l` would report the logical size -- use st_blocks via os.stat (disk
    blocks) which matches `du`'s physical accounting with the default block
    size.  Returns None when the dir does not exist."""
    if not l3_dir or not os.path.isdir(l3_dir):
        return None
    total = 0
    for fn in os.listdir(l3_dir):
        if not fn.startswith("hicache.data"):
            continue
        try:
            total += os.stat(os.path.join(l3_dir, fn)).st_blocks * 512
        except OSError:
            continue
    return total


# Gate B: layered cache-hit parent label.  Each resume row is tagged by where
# the served history actually came from, using the SSE cached_tokens_details
# (device/host/storage) plus --rh on|off and the per-session cached snapshot.
#   GPU-resident  : history served from Device (L1) -- device_hit dominates.
#   Host-ready    : served from Host L2 (host_hit) -- the session's history
#                   was already backed up to host DRAM.
#   RH-staged     : host_hit served because the L3 extent was pre-staged to
#                   Host by Ready-Horizon BEFORE the request arrived.  When
#                   --rh on we attribute host-serving to RH staging ONLY if we
#                   actually observed RH staging for that session (storage hit
#                   earlier in the run implies the extent path was active).
#   L3-on-demand  : served from L3 extent (storage_hit) -- a synchronous
#                   restore, the slowest normal hit path.
# Host-ready-STAGED is used when --rh on but we could not confirm RH staging
# for that session: the "Host-ready" label would be misleading, so it is
# flagged as possibly staged (Gate C distinguishes staged vs on-demand).
def classify_hit_parent(ctd, rh_on, session_has_storage_hit):
    device = ctd.get("device") or 0
    host = ctd.get("host") or 0
    storage = ctd.get("storage") or 0
    if storage > 0:
        return "L3-on-demand"
    if device > 0 and device >= host:
        return "GPU-resident"
    if host > 0:
        if rh_on and session_has_storage_hit:
            return "RH-staged"
        if rh_on:
            return "Host-ready-STAGED"
        return "Host-ready"
    return "GPU-resident" if device > 0 else "miss"


def _mkrow(args, state, rid, session, turn, kind, hist_n, meta, sx,
           ts_s, ts_e, mb, ma, rc, extra):
    u = (sx or {}).get("usage") or meta.get("usage") or {}
    ctd = (sx or {}).get("cached_tokens_details") or {}
    out, out_field = common.output_text(meta) if common else ("", None)
    row = {
        "session": session, "turn": turn, "turn_kind": kind,
        "ts_start": round(ts_s, 3), "ts_end": round(ts_e, 3),
        "ttft_s": meta.get("ttft_s"), "wall_s": meta.get("wall_s"),
        "http": meta.get("http_code"), "finished": meta.get("finished"),
        "finish_reason": meta.get("finish_reason"),
        "rid": rid,
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
        "prefill_input_delta": _md(mb, ma,
            "sglang:prefill_effective_tokens_total", 'mode="input"'),
        "prefill_devicehit_delta": _md(mb, ma,
            "sglang:prefill_effective_tokens_total", 'mode="device_hit"'),
        "prefill_hosthit_delta": _md(mb, ma,
            "sglang:prefill_effective_tokens_total", 'mode="host_hit"'),
        "prefill_storagehit_delta": _md(mb, ma,
            "sglang:prefill_effective_tokens_total", 'mode="storage_hit"'),
    }
    row.update(extra or {})
    return row


def _build_one(args, tok, state, s):
    """Build ONE session prefix (COLD full-history prefill).  Deterministic per
    session; session id 0-based so a later resume hits the SAME radix branch."""
    hist_text, hist_n = build_history_prompt(
        BUILD_TIERS[args.build_tier], tok, s)
    m_before = parse_metrics(fetch_metrics(state["metrics_lock"]))
    ts_s = time.time()
    prefix = os.path.join(state["turns_dir"], "build", "s%05d" % s)
    payload = {
        "model": args.served,
        "messages": [{"role": "user", "content": hist_text}],
        "max_tokens": args.build_max_new,
        "temperature": 0.0,
        "stream": True,
    }
    out_prefix = prefix + ".payload.json"
    os.makedirs(os.path.dirname(out_prefix) or ".", exist_ok=True)
    with open(out_prefix, "w") as payload_f:
        json.dump(payload, payload_f, ensure_ascii=False)
    rc, meta = common.run_client_inproc(out_prefix, prefix,
                                        args.build_client_max)
    ts_e = time.time()
    m_after = parse_metrics(fetch_metrics(state["metrics_lock"]))
    sx = common.extract_sglext(meta, prefix + ".body")
    # The first parked resume must continue the same conversation as the
    # build request.  Preserve the build assistant output for run_rounds;
    # starting with an empty assistant message changes the chat-template
    # suffix and is not the specified warm-turn semantics.
    build_asst, _ = common.output_text(meta) if common else ("", None)
    with state["join_lock"]:
        state["build_asst"][s] = build_asst or ""
    row = _mkrow(args, state, (sx or {}).get("rid") or meta.get("request_id"),
                 s, 0, "build", hist_n, meta, sx, ts_s, ts_e,
                 m_before, m_after, rc, {"kind": "build"})
    with state["join_lock"]:
        state["join_fh"].write(json.dumps(row) + "\n")
        state["join_fh"].flush()
    print("[build] s%05d rc=%d prompt=%d wall=%s ttft=%s"
          % (s, rc, hist_n, meta.get("wall_s"), meta.get("ttft_s")),
          flush=True)
    return row


def run_builds(args, tok, state):
    """Build S session prefixes (COLD full-history prefill), deterministic per
    session.  Runs --build-workers concurrent builders (default 0 = sequential,
    which is only sane for tiny S).  Session ids are 0-based (matching
    Sched.pick and run_rounds) so a later resume hits the SAME radix branch.
    #Dependency: S>=500 REQUIRES --build-workers (sequential 500x55K => ~2h,
    1000x55K => ~4h; 8 workers => ~20/40min, spec e5 §6.2 #2)."""
    workers = max(0, getattr(args, "build_workers", 0) or 0)
    if workers <= 1:
        for s in range(args.sessions):
            _build_one(args, tok, state, s)
            # short inter-build gap so a session's prefill is not the direct
            # sequencer of the next one (avoids accidental L3 residency).
            if args.build_gap > 0:
                time.sleep(args.build_gap)
        return

    results = {}
    lock = threading.Lock()
    marker = [0]

    def _worker(_):
        while True:
            with lock:
                s = marker[0]
                marker[0] += 1
            if s >= args.sessions:
                return
            try:
                row = _build_one(args, tok, state, s)
                results[s] = row
            except Exception as e:  # noqa: BLE001
                print("[build] s%05d ERROR %s" % (s, e), file=sys.stderr)
            # inter-build gap (per worker; preserves natural spacing)
            if args.build_gap > 0:
                time.sleep(args.build_gap)

    threads = [threading.Thread(target=_worker, args=(i,))
               for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Ensure build rows are written in deterministic session order in join.log
    # (they were written by workers already; just report completion).
    print("BUILDS_DONE sessions=%d workers=%d built=%d"
          % (args.sessions, workers, len(results)), flush=True)


def run_rounds(args, tok, sched, state):
    """Run `rounds` rounds of pick-active/retire.  In-flight concurrency stays
    <= active when --obey-ac.   Returns (rows, busy_retries)."""
    rows = []
    turns_issued = 0
    busy_retries = 0
    hist_cache = {}
    # pool of currently in-flight sessions (turn pending)
    inflight = set()
    # per-session last assistant text (this IS the multi-turn state)
    # Seed each session's first warm turn with the assistant answer produced
    # by its cold build; later turns update this map with their own output.
    last_asst = dict(state.get("build_asst", {}))
    # Gate B: per-session "has this session ever been served from L3 extent?"
    # (any prior storage hit -> the extent path is real for it).  Used to
    # distinguish RH-staged host serving from plain Host-ready.
    session_storage_hit = {}  # sid -> True once any prior resume hit storage
    # Gate A: full-history recompute attribution rows (see classify_recompute).
    attribution = []

    R = args.rounds
    for rnd in range(1, R + 1):
        # 1. pick up to --active sessions
        picks = sched.pick(time.time(), turns_issued)
        if not picks:
            # nothing due yet (park windows), idle-wait and retry
            time.sleep(args.idle_wait)
            # count this round as a no-op pass (turns_issued unchanged)
            continue
        # 2. filter out sessions that are still in flight
        picks = [s for s in picks if s not in inflight]
        if len(picks) < len(sched.pick(time.time(), turns_issued)) \
                and not picks:
            busy_retries += 1
            time.sleep(args.idle_wait)
            continue
        if not picks:
            continue
        # 3. issue one turn per picked session (serial within the round keeps
        #    the driver's own concurrency at exactly the active window; the
        #    engine still schedules c8 internally).
        for sid in picks:
            inflight.add(sid)
        for sid in picks:
            if sid not in hist_cache:
                hist_cache[sid] = build_history_prompt(
                    BUILD_TIERS[args.build_tier], tok, sid)
            hist_text, hist_n = hist_cache[sid]
            m_before = parse_metrics(fetch_metrics(state["metrics_lock"]))
            ts_s = time.time()
            turn = sched.turn_count[sid] + 1
            prefix = os.path.join(state["turns_dir"], "turn",
                                  "s%05d" % sid, "t%03d" % turn)
            payload = {
                "model": args.served,
                "messages": [
                    {"role": "user", "content": hist_text},
                    {"role": "assistant",
                     "content": last_asst.get(sid, "")},
                    {"role": "user", "content": _DELTA},
                ],
                "max_tokens": args.turn_max_new,
                "temperature": 0.0,
                "stream": True,
            }
            os.makedirs(os.path.dirname(prefix + ".payload.json") or ".",
                        exist_ok=True)
            with open(prefix + ".payload.json", "w") as payload_f:
                json.dump(payload, payload_f, ensure_ascii=False)
            rc, meta = common.run_client_inproc(prefix + ".payload.json",
                                                prefix, args.client_max_time)
            ts_e = time.time()
            m_after = parse_metrics(fetch_metrics(state["metrics_lock"]))
            sx = common.extract_sglext(meta, prefix + ".body")
            out, _ = common.output_text(meta) if common else ("", None)
            if out:
                last_asst[sid] = out

            # Gate B parent label + per-session L3-backing evidence.
            ctd = (sx or {}).get("cached_tokens_details") or {}
            has_stor = bool((ctd.get("storage") or 0) > 0)
            if has_stor:
                session_storage_hit[sid] = True
            parent = classify_hit_parent(
                ctd, args.rh == "on", session_storage_hit.get(sid, False))
            # Gate A: full-history recompute?  (recompute >= history tokens:
            # the long history was presented again but NOT served from any
            # cache tier -> it was re-prefilled.)
            prompt_len = None
            u = (sx or {}).get("usage") or meta.get("usage") or {}
            if isinstance(u, dict):
                prompt_len = u.get("prompt_tokens")
            d, h, s = (ctd.get("device") or 0), (ctd.get("host") or 0), \
                (ctd.get("storage") or 0)
            hit_sum = d + h + s
            full_recompute = bool(
                hist_n is not None and prompt_len is not None
                and hit_sum == 0
                and prompt_len >= hist_n * 0.9
            )
            if full_recompute:
                # The history WAS built this run (never_built is impossible
                # here).  The driver's tag is PROVISIONAL: without a per-event
                # engine extent_recycle timestamp to compare against this
                # recompute's timestamp, we cannot prove capacity eviction, so
                # we conservatively tag state_machine (suspicious) and let
                # gate3_parked_analyze.py flip it to capacity_evicted ONLY when
                # an engine [P3] extent_recycle event for that session has
                # ts_recycle < this recompute's ts.  We do NOT use the global
                # eviction_observed flag here -- L2 writeback/backup growth
                # alone is not evidence that THIS session's L3 entry was
                # recycled (reviewer D3).
                attribution.append({
                    "event": "full_history_recompute",
                    "session_id": sid,
                    "turn": turn,
                    "ts": round(time.time(), 3),
                    "reason": "state_machine",  # provisional; analyze flips
                    "prior_l3": bool(session_storage_hit.get(sid)),
                    "hit_sum": hit_sum,
                    "ttft_s": meta.get("ttft_s"),
                    "evidence_ref": "run=%s sid=%d turn=%d ttft=%.1f hit_sum=%d "
                                    "prior_l3=%s"
                                    % (state["run_dir"], sid, turn,
                                       (meta.get("ttft_s") or 0.0), hit_sum,
                                       bool(session_storage_hit.get(sid))),
                })
            # retire: remove from active set; next turn waits
            # park_min..park_max (seconds) AND lam turns of unrelated traffic.
            # prev_end = the PREVIOUS turn's retirement time (parking start
            # for THIS wake); must be captured BEFORE retire() advances it.
            prev_end = sched.retired_at[sid] if sched.retired_at[sid] is not None \
                else sched.last_turn_ts[sid]
            retired_at = time.time()
            sched.retire(sid, retired_at)
            sched.turn_count[sid] = turn
            inflight.discard(sid)
            row = _mkrow(
                args, state, (sx or {}).get("rid") or meta.get("request_id"),
                sid, turn, "resume", hist_n, meta, sx, ts_s, ts_e,
                m_before, m_after, rc,
                {
                    "round": rnd,
                    "age_at_wake_s": round(ts_s - prev_end, 3)
                    if prev_end is not None else None,
                    "turn_kind_parked": "resume",
                    # Gate B layered hit parent (GPU|Host|RH|L3).
                    "hit_parent_mux": parent,
                    # Gate C: this request's parent was RH-staged
                    # (0 = not staged, 1 = claimed RH-staged / Host-STAGED).
                    "rh_synced": 1 if parent in ("RH-staged", "Host-ready-STAGED")
                                 else 0,
                    "rh_flag": args.rh,
                    # Park ladder cohort the session was injected into
                    # (HOT/MID/COLD or None for uniform mode); analyze MUST
                    # re-bucket by measured age_at_wake_s (spec OD4).
                    "cohort": sched.cohort_of(sid),
                })
            rows.append(row)
            with state["join_lock"]:
                state["join_fh"].write(json.dumps(row) + "\n")
                state["join_fh"].flush()
            turns_issued += 1
            ctd_p = (sx or {}).get("cached_tokens_details") or {}
            print("[r%03d] s%05d t%03d rc=%d parent=%s ttft=%s dev=%s host=%s "
                  "stor=%s age=%s" % (
                      rnd, sid, turn, rc, parent, meta.get("ttft_s"),
                      ctd_p.get("device"), ctd_p.get("host"),
                      ctd_p.get("storage"),
                      row.get("age_at_wake_s")), flush=True)
        # short intra-round gap so active-set churn does not look like a
        # burst (the natural parking model is per-session idle gaps).
        if args.round_gap > 0:
            time.sleep(args.round_gap)
    return rows, busy_retries, attribution


def write_attribution(state, attribution):
    """Gate A recompute attribution table (recompute_attribution.csv).  One row
    per full-history recompute event.  The driver tags every full recompute as
    PROVISIONAL `state_machine` (it cannot prove capacity eviction without a
    per-event engine extent_recycle timestamp).  gate3_parked_analyze.py flips
    an event to `capacity_evicted` only when the engine's [P3] extent_recycle
    for that session has ts_recycle < this recompute's ts.  The final oversub
    qualification is: state_machine == 0 after that recheck.
    """
    if not attribution:
        return
    run_dir = state["run_dir"]
    path = os.path.join(run_dir, "recompute_attribution.csv")
    fieldnames = ["event", "session_id", "turn", "ts", "reason",
                  "prior_l3", "hit_sum", "ttft_s", "evidence_ref"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames,
                           extrasaction="ignore")
        w.writeheader()
        for a in attribution:
            w.writerow(a)
    print("RECOMPUTE_ATTRIBUTION_WRITTEN events=%d file=%s" % (
        len(attribution), path), flush=True)


def write_outputs(args, rows, state, t_start, busy):
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
    n_ok = sum(1 for r in rows
               if r.get("http") == "200" or r.get("finished"))
    # ---- oversubscription semantics framing (forbidden claim guard) ----
    caveats = []
    if args.mode == "oversub":
        caveats = [
            "oversubscription_stress_curve",  # NOT a full-retention capacity claim
            "recycle_allowed_recorded_not_fault",
            "no_claim_l3_full_park_Sx55K",
        ]
    elif args.mode == "fit":
        caveats = [
            "l3_fit_formal_capacity_test_S100",
        ]
    summary = {
        "status": "done", "sessions": args.sessions,
        "build_tier": args.build_tier, "active": args.active,
        "rounds": args.rounds, "requests_total": len(rows),
        "requests_ok": n_ok, "busy_retries": busy,
        "mode": args.mode, "rh": args.rh,
        "semantic_caveats": caveats,
        "run_dir": run_dir,
        "ts_start": round(t_start, 3),
        "ts_end": round(time.time(), 3),
        "elapsed_s": round(time.time() - t_start, 1),
    }
    with open(os.path.join(run_dir, "verdict.json"), "w") as f:
        json.dump(summary, f, indent=1, default=str)
    print("GATE3_PARKED_DONE mode=%s rh=%s sessions=%d active=%d rounds=%d "
          "run_dir=%s requests=%d busy_retries=%d frame=%s"
          % (args.mode, args.rh, args.sessions, args.active, args.rounds,
             run_dir, len(rows), busy,
             "oversub-stress" if args.mode == "oversub" else "l3-fit"), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=None,
                    help="number of parked sessions (100 fit / 500,1000 oversub); "
                         "defaults from --mode")
    ap.add_argument("--mode", choices=("fit", "oversub"), default=None,
                    help="fit        = L3-fit formal capacity test (default S=100, "
                         "complete-residency semantics + full Gate A/B judgement, "
                         "recycle must be minimal)\n"
                         "oversub     = L3 OVERSUSUBSCRIPTION stress (default "
                         "S=500; the 200G L3 cannot keep 500-1000x55K resident "
                         "-- extent recycle is ALLOWED and recorded, degradation "
                         "curve only, NEVER a full-retention claim)")
    ap.add_argument("--rh", choices=("on", "off"), default="off",
                    help="Ready Horizon staged comparison arm (Gate C A/B): "
                         "PASS the SAME seed/sessions/activity twice with "
                         "--rh on and --rh off to build the paired table.  The "
                         "driver only labels/stages both arms; whether the "
                         "engine can toggle RH is a TUNER-side launcher "
                         "dependency (verified by tester on 24052).")
    ap.add_argument("--build-tier", default="55k",
                    choices=sorted(BUILD_TIERS),
                    help="55k (authoritative) | 50k | 64k | 80k history per session")
    ap.add_argument("--rounds", type=int, default=60,
                    help="resume rounds (pick+turn per round)")
    ap.add_argument("--active", type=int, default=8,
                    help="active window (frozen engine c8 default); knob for "
                         "sensitivity probes")
    ap.add_argument("--park-min", type=float, default=30.0,
                    help="min parked time per session (s); UNIFORM mode "
                         "(ignored when --park-ladder given)")
    ap.add_argument("--park-max", type=float, default=300.0,
                    help="max parked time per session (s); UNIFORM mode "
                         "(ignored when --park-ladder given)")
    ap.add_argument("--park-ladder", type=parse_park_ladder, default=None,
                    help="Gate B cohort park-window ladder "
                         "\"HOT:0-30@5,MID:120-300@30,COLD:600-2400@65\" -- "
                         "deliberately manufactures GPU/Host/RH/L3 hit states by "
                         "session-id cohort.  Fit default = FIT_PARK_LADDER; "
                         "oversub stays uniform 30-300 (no ladder).  Injection "
                         "bias only -- analyze re-buckets by age_at_wake_s.")
    ap.add_argument("--pick-lam", type=float, default=1.0,
                    help="mean inter-wake in turns (higher = less eligible "
                         "at each pick -> longer real parking)")
    ap.add_argument("--build-workers", type=int, default=0,
                    help="concurrent COLD build workers (0/1 = sequential).  "
                         "S>=500 REQUIRES this (sequential 500-1000x55K is "
                         "hours; 8 workers => ~20-40min); S=100 fine either "
                         "way (spec e5 §6.2 #2)")
    ap.add_argument("--obey-ac", action="store_true",
                    help="cap client-side in-flight turns at --active")
    ap.add_argument("--idle-wait", type=float, default=2.0,
                    help="wait (s) when nothing is due or all picks busy")
    ap.add_argument("--round-gap", type=float, default=1.0,
                    help="intra-round gap (s)")
    ap.add_argument("--build-gap", type=float, default=0.5,
                    help="inter-build gap (s)")
    ap.add_argument("--post-build-settle", type=float, default=0.0,
                    help="diagnostic-only wait after cold builds before turns; "
                         "allows asynchronous L3 write-back to drain")
    ap.add_argument("--build-max-new", type=int, default=12)
    ap.add_argument("--turn-max-new", type=int, default=64)
    ap.add_argument("--build-client-max", type=int, default=1500,
                    help="per-build timeout (s); 80K cold prefill under a cold "
                         "machine can be slow")
    ap.add_argument("--client-max-time", type=int, default=1200,
                    help="per-resume timeout (s)")
    ap.add_argument("--snapshot-interval", type=float, default=2.0,
                    help="high-cadence gauge sampler interval (s)")
    ap.add_argument("--coarse-interval", type=float, default=60.0,
                    help="coarse sampler interval (s), also captures "
                         "--l3-backend-dir footprint")
    ap.add_argument("--l3-backend-dir", default=None,
                    help="L3 extent storage dir (runner-side path) -- passed "
                         "to read physical extent footprint via st_blocks")
    ap.add_argument("--seed", type=int, default=0,
                    help="random seed (0 = fresh each run)")
    ap.add_argument("--evidence-dir", default="/root/evidence-parked")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--served", default=None)
    args = ap.parse_args()
    args.served = args.served or os.environ.get("SERVED", "qwen3.5-9b-gptq")
    # ---- mode semantic resolution (fit / oversub) ----
    if args.mode is None:
        args.mode = "oversub" if (args.sessions or 0) >= OVERSUB_SESSIONS[0] \
            else "fit"
    if args.sessions is None:
        args.sessions = FIT_SESSIONS if args.mode == "fit" else OVERSUB_SESSIONS[0]
    if args.mode == "fit" and args.sessions > L3_FIT_SESSIONS:
        # Library note: oversub semantics NEVER claimed fit; only S<=L3-fit
        # anchor runs as a formal capacity test.
        print("WARN fit-mode with sessions=%d > L3-fit anchor %d -- results are "
              "NOT a full-retention claim" % (args.sessions, L3_FIT_SESSIONS),
              flush=True)
    if args.mode == "oversub" and args.sessions < OVERSUB_SESSIONS[0]:
        print("WARN oversub-mode with sessions=%d < 500 -- degradation curve "
              "point is weak; prefer 500/1000" % args.sessions, flush=True)
    # Park ladder: explicit --park-ladder wins; else fit defaults to the Gate B
    # cohort ladder, oversub stays uniform (spec e5 §6.2 #1).
    if args.park_ladder:
        args.ladder = args.park_ladder
    elif args.mode == "fit":
        args.ladder = list(FIT_PARK_LADDER)
    else:
        args.ladder = None

    if args.dry_run:
        import random as _r
        rng = _r.Random(args.seed if args.seed else 42)
        # pure-logic sanity: build a small schedule and assert the invariants
        sch = Sched(args.sessions, args.active, rng,
                    args.park_min, args.park_max, args.pick_lam,
                    ladder=args.ladder)
        t0 = 0.0
        for rnd in range(1, 4):
            picks = sch.pick(t0, rnd - 1)
            before = len(picks)
            for sid in picks:
                sch.retire(sid, t0)
                sch.turn_count[sid] += 1
                sch.last_turn_ts[sid] = t0
            after = len(sch.pick(t0 + 1, rnd))
            assert before <= args.active and after <= args.active
        print("DRY_RUN_OK mode=%s rh=%s sessions=%d active=%d rounds=%d "
              "tier=%s schedule_pick_ok=True"
              % (args.mode, args.rh, args.sessions, args.active,
                 args.rounds, args.build_tier))
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

    rng = random.Random(args.seed if args.seed else None)
    sched = Sched(args.sessions, args.active, rng,
                  args.park_min, args.park_max, args.pick_lam,
                  ladder=args.ladder)

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
        # Gate A diagnostics: set by the coarse sampler when it observes the
        # engine's extent recycle / eviction counters actually moving.
        "eviction_observed": False,
        "has_l3": bool(args.l3_backend_dir),
        "build_asst": {},
    }
    stop = threading.Event()
    _prev_evict = None
    _prev_backup = None
    _prev_loadback = None

    def _snap_evict_counts(snap):
        """Detect whether the engine reported ANY eviction/recycle/backup
        activity during this run (coarse-pass counter deltas)."""
        nonlocal _prev_evict, _prev_backup, _prev_loadback
        ev = _first_val(snap, "sglang:evicted_tokens_total")
        bk = _first_val(snap, "sglang:backuped_tokens_total")
        lb = _first_val(snap, "sglang:load_back_tokens_total")
        if _prev_evict is not None and (ev is None or _prev_evict <= _prev_evict):
            return  # no deltas yet
        if (ev is not None and _prev_evict is not None and ev > _prev_evict) \
                or (bk is not None and _prev_backup is not None and bk > _prev_backup) \
                or (lb is not None and _prev_loadback is not None and lb > _prev_loadback):
            state["eviction_observed"] = True
        if ev is not None:
            _prev_evict = ev
        if bk is not None:
            _prev_backup = bk
        if lb is not None:
            _prev_loadback = lb

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

    def coarse():
        while True:
            # sleep first so the fast sampler gets the first word
            if stop.wait(args.coarse_interval):
                return
            try:
                snap = parse_metrics(fetch_metrics(state["metrics_lock"]))
            except Exception:  # noqa: BLE001
                snap = {}
            # Gate A: watch evicted/backuped/load_back move as the recycle
            # evidence source (best effort; engine log extent_recycle is the
            # authoritative source consumed by gate3_parked_analyze.py).
            with state["metrics_lock"]:
                _snap_evict_counts(snap)
            snap2 = dict(snap)
            foot = extent_footprint(args.l3_backend_dir)
            if foot is not None:
                snap2["l3_extent_physical_bytes"] = foot
            with state["join_lock"]:
                state["mid_fh"].write(json.dumps(
                    {"ts": round(time.time(), 3), "metrics": snap2,
                     "l3_physical": foot,
                     "eviction_observed": bool(state["eviction_observed"])}) + "\n")
                state["mid_fh"].flush()

    threads = [threading.Thread(target=sampler, daemon=True),
               threading.Thread(target=coarse, daemon=True)]
    for t in threads:
        t.start()

    t_start = time.time()
    run_builds(args, tok, state)
    if args.post_build_settle > 0:
        print("POST_BUILD_SETTLE seconds=%s" % args.post_build_settle,
              flush=True)
        time.sleep(args.post_build_settle)
    rows, busy, attribution = run_rounds(args, tok, sched, state)
    write_attribution(state, attribution)
    stop.set()
    for t in threads:
        t.join()
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
    write_outputs(args, rows, state, t_start, busy)
    return 0


if __name__ == "__main__":
    sys.exit(main())
