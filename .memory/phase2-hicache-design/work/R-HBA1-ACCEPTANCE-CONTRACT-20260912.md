# R-HBA1 — Ready Horizon Behavioral Acceptance (frozen problem definition)

Status: contract FROZEN 2026-09-12 (user authority). Operational seam details
that depend on code reconnaissance are marked `OPEN` and are filled by the
seam scout before the harness is built. This document changes ONLY by the
graded-correction protocol below.

## 0. Claim grading protocol (binding, user rule)

Every statement in this task is labelled:

* `FACT` — directly proven by existing logs / source / experiments;
* `INFERENCE` — derived from facts;
* `OPEN` — not yet proven;
* `DECISION` — engineering ruling made on the evidence.

A conclusion changes ONLY on new decisive evidence, written as
`原结论 X; 新证据 Y; 因此修正为 Z`. No silent rewording.

## 1. The single question (frozen)

`FACT` (from SGLang HiCache design: reuse KV, avoid re-prefill; L3->L2 prefetch
then compute):

> Given a fully durable reusable prefix D that is absent from L1 (device) and
> L2 (host) but present in L3, and a queued continuation with sufficient lead
> time and sufficient resources, does Ready Horizon (RH) (a) stage D L3->L2
> before admission, (b) restore D for execution, (c) skip recomputation of D,
> and (d) bring the A->B task-switch gap close to the L2-hot control?

This is the ONLY mainline. CUDA Graph, Marlin/GDN TPS and C8 throughput are a
separate **Engine Performance** line and MUST NOT change this verdict.

## 2. Frozen test profile (DECISION)

Launcher: `/mnt/data/neuron/sglang-3090-r112-20260911/launch-rhba1.sh`
sha256 `d6d037fa26ee5b8cd420961c68a133c2c7761b18c4f28104fd7594cfd62cd351`.
Model `/mnt/data/models/qwen35-gptq` (Qwen3.5-4B W4A16 / gptq_marlin).
* L3 = `ExtentFileBackend` (extent + RAM authoritative index), own dir
  `l3-extent-rhba1` (does NOT touch E4 `l3-extent`).
* FP8 KV (`--kv-cache-dtype fp8_e4m3`); device pool `--max-total-tokens 65536`.
* `--max-running-requests 1` (forces B to queue behind A).
* `--hicache-storage-prefetch-policy wait_complete`.
* CUDA graphs exactly as frozen (off). NOT changed in this task.
* RH toggle via `RHBA1_RH=on|off`; ON adds exactly
  `--enable-ready-horizon --ready-horizon-frontier-n 8
  --ready-host-watermark-low 55000 --ready-host-watermark-high 110000`.
* No profile/pool enlargement.

Note `FACT`: this profile is byte-identical to `launch-e-20260912.sh`
(`d24195b9…`) except the extent dir / run-id and the RH toggle — the E-phase
architecture (extent L3 + RAM index) is the production baseline.

## 3. Semantic anchor: cache-hit tier accounting (FACT where cited)

* `FACT`: `req.cached_tokens_{device,host,storage}` exist and are set from
  `split_cached_prefix_by_tier(prefix_len=len(req.prefix_indices),
  host_hit_len=req.host_hit_length, storage_hit_len=req.storage_hit_length)`
  in `python/sglang/srt/managers/schedule_batch.py:2560-2590`
  (`_cache_breakdown_computed`, once, first chunk only).
* `FACT`: the OpenAI response exposes the split via
  `output_streamer.get_cached_tokens_details` ->
  `entrypoints/openai/usage_processor.py` as `prompt_tokens_details`.
* `FACT` (resolved by live preflight 2026-09-12, cache mode): with RH
  pre-staging D, the request reports
  `{device:0, host:0, storage:D, storage_backend:"ExtentFileBackend"}`
  (observed `storage=27648`). `restore_success` marker =
  `[P2A] evt=restore_success rid=... n_tokens=...` (wall clock). Durable
  restore also completes Mamba (`restore_hybrid_finalize` mamba 1/1).

## 4. State construction: "L3-only" (RESOLVED)

`FACT` (blocker, from source + E0 G1): `ExtentFileBackend` has no metadata
persistence ("restart starts cold -- no metadata persistence",
`extent_file_backend.py:20`; test `test_crash_reopen_all_cold`). Therefore a
server restart clears the L3 RAM index, so "restart to clear L1/L2" is NOT a
valid way to reach an L3-only state. **L3-only must be constructed within one
server session** (prime -> evict from L1 and L2, keep L3) or another
user-authorized mechanism.

`FACT` (resolved 2026-09-12): `/flush_cache?timeout=N` is a clean L3-only
constructor. Source: `_reset_full` sets `enable_storage=False` transiently
(`unified_radix_cache.py:2730`) then restores it from
`cache_controller.enable_storage` (`:2773`); `CacheController.reset()`
(`cache_controller.py:835`) never disables storage (it restarts the threads);
`_reset_full` never touches `storage_backend`/`_storage_attachment`/
`storage_existence_cache` and never calls `clear_storage_backend` (that is the
separate `/clear_hicache_storage` handler, `scheduler.py:7646`). Live: after
prime -> flush 200, B restored `storage=27648` from L3, so L3 + RAM index
survived. The earlier HTTP 400 was `is_fully_idle()` false (write-through still
draining); a positive server-side `timeout` defers the flush until idle.

`FACT` (`D_req` is empirical): the restorable durable prefix was 27648 for a
27667-token prompt; the non-durable tail is fresh prefill, NOT avoidable
recompute. The harness takes `D_req` from the observed storage hit.

`OPEN` (harness requirement): use a fresh extent dir (or a fresh nonce +
storage clear) per condition so D is built exactly once with a traceable chain.

## 5. Two-session scenario (frozen shape)

* Session A: **GPU occupancy clock, NOT a pressure/eviction vehicle**
  (`DECISION` 2026-09-12). A MUST: share NO prefix with B; not touch B's
  L1/L2/L3 residency; use a short prompt; use a fixed-length output; not itself
  take an L3 restore. Under `--max-running-requests=1`, A must be in `running`
  before B is enqueued.
* Target B: durable prefix `D_req` ~27K tokens + exactly 128 fresh suffix
  tokens; `max_tokens=1`.
* Before each measured B run, prove `device_hit=0`, `host_hit=0`,
  `storage_hit=D_req`; KV + Mamba durable coverage complete.

**Lead construction (`DECISION` 2026-09-12, frozen).** Enqueue B immediately
after A's FIRST streamed token; A's output length is the only knob:
`sufficient` uses a long A (e.g. 256 tokens) and `insufficient` a short A (e.g.
8 tokens). Never predict remaining A time; classify each sample by the measured
monotonic marks. A sample is `sufficient-lead` iff
`B_enqueue < prefetch_issue < ready_host <= A_last_token`; otherwise it is
`insufficient-lead` and MUST NOT be forced into the sufficient group. The
insufficient condition is likewise classified by measurement
(`prefetch_slack <= 0`), never by a subjective "A nearly done". No scheduler
change is made to manufacture insufficient lead.

`FACT` (tokenizer calibration, offline): the deterministic synth generator
`"[nonce] " + WORDS[i % 52]` gives 27,663 tokens at 21,000 words; byte-stable
across calls. Exact `D_req` is fixed by token-count at harness build time, not
by word count.

## 6. Four conditions (frozen)

1. `L2-hot control` — D already resident in L2 (lower bound of what RH can buy).
2. `L3-only, RH OFF` — no pre-staging; true task-switch cost.
3. `L3-only, RH ON, insufficient lead` — prove RH does not fake readiness.
4. `L3-only, RH ON, sufficient lead` — the acceptance condition.

Each condition repeated (target >= 5 measured B runs).

`DECISION` (sample size, 2026-09-12): p95 is a hard gate ONLY with >= 20
measured samples per key condition. With 5-10 samples report p50/max and do NOT
treat p95 as a stable statistic. The frozen matrix (1 hot + 3 L3-only) is not
redefined; the hot controls are reference lower bounds and MUST NOT dominate the
verdict. The verdict weight is on `L3-only RH OFF` vs `L3-only RH ON sufficient
lead`.

## 7. Clock and marks

All marks on `time.monotonic_ns` (same `CLOCK_MONOTONIC` for co-located client
and server processes).

| mark | meaning | source | status |
|---|---|---|---|
| `B_enqueue` | scheduler `_add_request_to_queue` | probe `evt=enqueue_mono_ns` (M1) | `FACT` exists |
| `prefetch_issue` | RH issues L3->L2 stage | probe `evt=prefetch_issued` (M2) | `FACT` exists |
| `ready_host` | staged prefix host-ready | probe `ready_host`/`ready_stage` | `FACT` exists |
| `A_last_token` | A's last streamed token | client | `FACT` (client) |
| `B_admission` | B admitted for scheduling | probe `admission.v2` | `FACT` at C=1 |
| `restore_success` | D restored for execution | `[P2A] evt=restore_success` | `FACT` |
| `B_first_token` | B's first streamed token | client | `FACT` (client) |

`FACT`: `admission.v2` is emitted on `AddReqResult.CONTINUE`
(`scheduler.py:6816-6840`) and was observed live at `--max-running-requests=1`
for the admitted B (preflight 2026-09-12), `ready_host_observed=true`.
Clock note: `ready_host`/`ready_stage`/`prefetch_issued`/`admission.v2` use
`time.monotonic_ns`; `restore_success`/`restore_ready`/`restore_state` use wall
`int(time.time()*1000)` — never mix them in a subtraction.

## 8. Derived metrics (frozen definitions)

* `lead = A_last_token - B_enqueue`
* `prefetch_slack = A_last_token - ready_host`
  * `> 0` => the L3->L2 stage finished while A was still computing (truly
    hidden).
  * `<= 0` => RH did not hide the stage; this sample is NOT sufficient-lead.
* `stage = ready_host - prefetch_issue`
* `TFTT = B_first_token - A_last_token`
* `restore_coverage = restored_durable / D_req`
* `D_req = actual storage-hit durable prefix` (measured per replicate, NOT the
  raw prompt length). `fresh_suffix = B_prompt_tokens - D_req` (includes the
  legitimately non-durable prime tail).
* `avoidable_recompute_tokens = max(0, D_req - cached_prompt_tokens)` where
  `cached_prompt_tokens = device + host + storage` from
  `sglext.cached_tokens_details`. ONLY tokens inside `D_req` count; the
  non-durable tail is fresh prefill and can NEVER be an RH failure.

Throughput naming (prior binding ruling) applies if any throughput is quoted:
`aggregate_output_tps`, `request_tps`, `effective_compute_tps`,
`served_context_tps`; never count L1/L2/L3-hit prefix tokens as input compute.

## 9. Hard gates — sufficient-lead RH ON (frozen)

* `B_enqueue < prefetch_issue < ready_host <= A_last_token`
  (i.e. `prefetch_slack >= 0`; this supersedes the weaker
  `ready_host <= B_admission`, which only proves "ready before admission", not
  "L3 latency hidden by A")
* `ready_host <= B_admission` (necessary, no longer sufficient)
* `restored_durable == D_req`
* KV + Mamba restore complete
* **`avoidable_recompute_tokens == 0`** (inside `D_req`)
* no durable-prefix PARTIAL / shortfall
* no hybrid discard
* HTTP completion

`DECISION`: **if D is restored but then recomputed, RH FAILS** regardless of
output TPS.

## 10. Effectiveness gate (frozen)

`TFTT = B_first_token - A_last_token`.

RH-ON sufficient-lead p95 TFTT must be within `max(100 ms, 25%)` of the L2-hot
control p95, AND materially better than the L3-only RH-OFF control.

`DECISION` (2026-09-12): if the final result shows `restored == D_req`,
`avoidable_recompute == 0`, `prefetch_slack > 0`, RH-ON TFTT ~= hot control,
and RH-OFF TFTT materially worse, the verdict is a stable
**Ready Horizon behavioral acceptance PASS**. The 4B TPS / CUDA Graph / C8
performance lines are separate and MUST NOT re-open this verdict.

## 11. Verdict semantics

* `PASS` — all of §9 plus §10 on repeated sufficient-lead runs.
* `FAIL` — any §9 gate violated in the correct-lead condition (esp. recompute).
* `NOT_VERIFIED` — a required mark/state could not be produced; state the exact
  missing transition. Never fabricate.

## 12. Explicitly out of scope

CUDA Graph on/off, quantization/kernels, C4/C8 throughput matrix, engine TPS
optimization, G1 restart-rebuild. These belong to the Engine Performance line
and to P2-B0 (after this gate closes).
