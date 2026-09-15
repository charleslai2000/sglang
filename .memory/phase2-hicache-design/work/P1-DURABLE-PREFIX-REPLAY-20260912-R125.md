# P1 durable-prefix replay (Option A) — R125 tester report

## Status: BLOCKED (P1 gate NOT_VERIFIED)

The experiment ran (2/2 allowed live runs) and reproduced most of R121's chain on
the rebuilt server, but the **fixed HOST_ALLOC capacity clause was never the
deciding factor**, so the fix is **not runtime-exercised**. Per the frozen
contract this is a **NON-EVIDENCE** outcome, not a PASS. Budget is exhausted, so
this needs a fresh dispatch/decision.

- Bundle: `work/R125-bundle/` (root = run 1, chain-bearing; `run2/` = corrected
  attempt). `chain.json`, `condition-evidence.md`, `manifest.json`,
  `sha256sums.txt`, `driver125.py`, `raw.log`, `probe.log`, `requests.jsonl`,
  `state.jsonl`, `watch.log`.
- Contract: `P1-R125-DURABLE-PREFIX-REPLAY-CONTRACT.md` sha256
  `f78a2fc698de375de612ace8c023e4a6518a6781c155c2f5e92b66dd521f3c1f` **VERIFIED**.

## Verified facts

- Contract hashes VERIFIED: R125 `f78a2fc6…3c1f`; R121 `2ac86b5a…b3b`;
  R123 `bf7b09ee…1e1f8`; R124 correction `c57905ff…3cd2`.
- Server: PID `3082643`, scheduler child `3086752`, port 30000, health 200
  (never restarted/signalled; no `/flush_cache`, no `/close_session`).
  Fix present: `python/sglang/srt/managers/scheduler.py` sha256
  `892efc25e2a9ef7c5ebb4afa09cf6914182b1467981d14cd76c53eea5d8de9d7`.
- L3 durable prefix re-verified on disk (3,086,735-entry dir): 8/8 R121 T
  objects, F1 42944/42959, F2 42944/43002.

## Blocking contract defect corrected: nonce is `p3`, not `p1`

The contract's "use `R121_NONCE=p1`" contradicts its own mandatory Gate 0. R121
ran with `nonce:"p3"`; R124 used `p1`. Offline reproduction (driver prompts →
existing `/v1/tokenize` → reimplemented `hash_binding.cpp` page-hash chain):

| nonce | T_K | T tokens | matches R121 8 keys / 27328 |
|---|---|---|---|
| p1 | 252 | 27170 | NO |
| **p3** | **240** | **27340** | **YES (exact)** |

Using `p1` would fail Gate 0 by construction. The replay used `p3`.

## Gate 0 — identity — PASS

`probe.log:2718` and `:2809` (`pc_storage_query rid=r121-p3-R-T`): the 8 keys
equal the frozen R121 set, `query_suffix_len=27339`,
`kv_hit_pages=27328`, `storage_hit_count=27328`,
`sidecar_hits={"kv":27328,"mamba":27328}`.

`key_set_sha256 = 73e15a5fa454204f8ac3b0d1181235999bacaeb59d71f9f5eb208444cf92dcb8`
(expected identical). **kv_hit_pages = 27328.**

## Run 1 — chain reached; Gates 1 PASS, Gate 2 NON-EVIDENCE, Gate 3 partial

`raw.log` = window slice, server lines 1465903..1737009. Recipe: p3, F1+F2
seeded, 5 pressure requests, window `[[F1],[F2],[T]]`; **T not built** (replayed
from durable L3; pure non-resident restore candidate).

| leg | raw.log:line | reading |
|---|---|---|
| T non-resident | `2` | match `device_hit=0 host_hit=0`, `fill_len=27340` |
| T SPEC_BUDGET park | `12` | `reason=negative_cache`, `negative_cursor=42958 > 39321` |
| F1 release +1 | `73` | `restore_host_alloc` epoch 17→18 exactly once |
| T RH issue | `75` `77` `78` | `prefetch_issued(27339)`; `ready_stage result=issued` at epoch 18 |
| T HOST_ALLOC wait | `40800` | `restore_host_alloc_wait wait:8`, `blocked_domains=[kv,mamba]` |
| **T grant (NON-EVIDENCE)** | **`128043`** | both generations advanced |
| T finalize | `271087` | `kv_fetched=27328==D_req`, mamba 1/1, READY, accepted |
| T disposition | `271088` | `PARTIAL requested=27339 granted=27328 reason=shortfall` |
| T success | `271098` | `n_tokens=27326` |

Gate 1 (no premature consumption): PASS. T's first `prefetch_issued` is at
`raw.log:75`; `ready_stage` at `raw.log:78` carries epoch 18 = release epoch 18
(release at `raw.log:73`). No T `restore`/`Prefill batch` occurs before the
release; T's queued `admission … can_run=0` at `raw.log:106` is after it.
`durable-prefix recompute == 0`, `hybrid_discard == 0`; batch HTTP 200.

### Deciding-clause record — `raw.log:128043` (`restore_host_alloc_wake_decision decision=grant`)

| pool | gen_before | gen_after | advanced? | free | evictable | free+evict | required | cap_satisfied | new_clause_decides |
|---|---|---|---|---|---|---|---|---|---|
| kv | 278 | 279 | **yes** | 2242 | 1984 | 4226 | 27328 | no | **no** |
| mamba | 345 | 346 | **yes** | 64 | 21 | 85 | 1 | yes | **no** |

`captured_generations={kv:278,mamba:345}`, `current_generations={kv:279,mamba:346}`,
`blocked_domains=[kv,mamba]`. Both blocked domains' generations advanced, so the
original invalidation branch (`scheduler.py:3736-3740`) satisfied every domain;
the new capacity branch (`scheduler.py:3743-3754`) was never consulted. The old
rule would also grant ⇒ **NON-EVIDENCE**. The only hold (`raw.log:40801`) had
both generations unchanged but `free+evictable kv=6212 < 27328`, a legitimate
capacity hold, not the fixed clause.

### Gate 3 — durable-boundary restore

The durable boundary was **fully fetched**: `restore_hybrid_finalize
kv_expected=27328, kv_fetched=27328==D_req`, `per_sidecar.mamba={1,1}`,
`all_or_nothing=true`, `restore_state_after=READY`, `result=accepted`; no
durable-prefix recompute, no `hybrid_discard`. Literal Gate 3 predicates not met:
`disposition==FULL` is `PARTIAL reason=shortfall` (solely the 11-token
durable-boundary-external tail `27339-27328`), and
`restore_success.n_tokens=27326 = D_req-2` (same `granted → success -2`
convention as R121 F1: granted 42752, success 42750).

### D_req and timing (run 1)

- `D_req = 27328` = `pc_storage_query.kv_hit_pages == storage_hit_count`.
- `requested_primary_tokens = 27339`; external tail = **11** tokens.
- `t_wake` (grant) = `24150110953157` ns; `t_deadline` (wait:8) =
  `24178421434716` ns; `wait_started_mono_ns = 24118421434716`.
- `t_feasible` (first instant `free+evictable >= required` for every blocked
  domain): not reached before the grant (at grant kv `4226 < 27328`); capacity
  became sufficient only after the generation-driven grant. So run 1 was **not**
  at the proven-to-flip condition. F1 release epoch 17→18; T issue epoch 18.

## Run 2 (`run2/raw.log`) — corrected attempt; chain not reached

Change aimed at a quiescent-mamba capacity grant: no builds, `USE_F2=0`,
`TRIGGERS=0`, pressure-only preprocessing, extra settle. Outcome: F1 parked
`HOST_ALLOC` (`run2/raw.log:1786`) and ran to its 60 s **TIMEOUT**
(`run2/raw.log:109023`); with `--max-running-requests 1` F1 held the only running
slot, T was never RH-issued (no `pc_storage_query`/`prefetch_issued`/HOST_ALLOC
for T), and T was served by ordinary recompute (`Prefill batch #cached-token: 0`,
`run2/raw.log:109040-109047`). No restore for T.

## Exact unmet condition and blocker classification

- Unmet: at T's grant, **no blocked domain had an unchanged generation while its
  `free+evictable >= required`** (`raw.log:128043`: kv 278→279, mamba 345→346).
- Single decisive line for the outcome: **`work/R125-bundle/raw.log:128043`**.
- Classification: **harness/workload-timing**, not product behavior. The fix did
  not misbehave; R121's quiescent-mamba flip window was not recreated (R121's
  flip had mamba `1853→1853`, `free+evictable 76 >= 1`; here both generations
  moved). Secondary: the contract's `p1` nonce text is a contract defect
  (corrected to `p3`); Gate 3's literal `FULL`/`n_tokens==D_req` are defeated by
  the external tail and the `-2` telemetry convention.
- No new product defect is implicated; no product change is licensed by R125.

## Decision genuinely needed (user/orchestrator)

2/2 live runs are used and Gate 2 cannot be produced without another run or a
different recipe. Options:

1. **(Recommended)** Authorize one further bounded run suite (~3-4 runs) with a
   recipe tuned to hold the mamba pool quiescent while kv becomes capacity-feasible
   (e.g., keep F2 for F1-release timing but drop trigger churn; or gate the
   window on a stable mamba evictable signature), reporting any new-clause grant.
2. Accept the current result as **NON-EVIDENCE** and close R125 as P1
   NOT_VERIFIED without runtime exercise of the fix.
3. Rework the frozen contract's Gate 3 to express "durable boundary fully
   fetched" (`kv_fetched==D_req`) rather than literal `disposition==FULL`, since
   every R121-derived prompt carries an 11-token external tail.
