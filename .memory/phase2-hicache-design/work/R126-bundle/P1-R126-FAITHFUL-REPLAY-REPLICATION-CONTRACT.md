# R126 contract (FROZEN) — faithful R121 replay, replication budget

- Applies to `P1-DURABLE-PREFIX-REPLAY-20260912-R126`.
- Additive superset of `R121-bundle/P1-R121-CONTROLLED-EVICTION-CONTRACT.md`
  (`2ac86b5a…b3b`), `R123-bundle/P1-R123-TEMPORAL-WAKE-GATE-CONTRACT.md`
  (`bf7b09ee…1e1f8`), and `R125-bundle/P1-R125-DURABLE-PREFIX-REPLAY-CONTRACT.md`
  (`f78a2fc6…3c1f`). Gate basis is v2 (L2 host pool via `host_alloc.v1`).

## Why R126 exists (changed mechanism = replication, not redesign)
R125 run 1 reached the FULL live chain (non-resident T -> SPEC_BUDGET park ->
release+1 -> RH issue -> HOST_ALLOC grant -> `kv_fetched==D_req`) but Gate 2 was
**NON-EVIDENCE**: at the grant (`work/R125-bundle/raw.log:128043`) BOTH blocked
domains' generations had advanced (`kv 278->279`, `mamba 345->346`), so the old
rule would also grant and the fix's new capacity clause was never consulted.
Independent verification confirms this (T's only `host_alloc.v1` decisions are
`:40801 hold_no_generation` and `:128043 grant`).

The miss is a **race on mamba-generation quiescence**: the new clause decides
only if, over T's HOST_ALLOC wait, the mamba domain stays generation-unchanged
(its requirement `1` is already satisfied, `free+evictable=85 >= 1`) while the kv
domain stops blocking. R121 itself hit that condition (mamba `1853->1853`
unchanged for the whole wait); R125 run 1 did not (one mamba mutation inside the
31 s wait). Nothing about the product or the workload is changed here: R126
samples the same frozen, faithful recipe more than once.

## Recipe (faithful, unchanged)
`work/R125-bundle/driver125.py` at its defaults:
`R125_NONCE=p3`, `R125_USE_F2=1`, `R125_TRIGGERS=4`, `R125_BUILD_T=0`,
`R125_PRESSURE_N=5`, against the running rebuilt server (PID 3082643) and the
current log `sglang-server-r124.log`. This is the literal R121 p3 window
(`[[F1],[F2],[T]]`, qlen=3).

- NONCE is `p3` (R121's durable prefix). `p1` is R124's nonce and must NOT be
  used (it fails Gate 0 by construction). The R125 contract's `p1` text was a
  transcription error; this contract states `p3`.
- Each replay writes a fresh `OUT` dir: `run<N>/`.
- Up to **3** replays, stopping at the first run that satisfies all four gates.

## Gate 0 — identity (mandatory, every run)
T's storage query must report the frozen R121 key set (first 8 keys), 
`key_set_sha256 = 73e15a5fa454204f8ac3b0d1181235999bacaeb59d71f9f5eb208444cf92dcb8`,
`kv_hit_pages == 27328`. A different prefix is a FAIL for that run.

## Gate 1 — no premature consumption
No `admission`/`Prefill batch` for T before the SPEC_BUDGET release; a
`prefetch_issued(rid=T)` must occur with its RH issue epoch >= the release epoch.

## Gate 2 — the fix's NEW clause is the deciding condition (strict)
At the `restore_host_alloc_wake_decision decision=grant` for T, **at least one
blocked domain must have an UNCHANGED generation (`current == captured`) while
its current allocability satisfies its requirement (`free+evictable >=
required`)**. Record per-domain `gen_before/after`, `free`, `evictable`,
`required`, and which clause decided. If every blocked domain's generation
advanced, the old rule would also grant => NON-EVIDENCE for that run (not a PASS,
not a FAIL; go to the next replay).

## Gate 3 — durable-boundary FULL restore (corrected semantics)
All of:
- `restore_hybrid_finalize`: `kv_fetched == D_req` and the Mamba sidecar
  `expected == fetched` on the same boundary, `all_or_nothing=true`.
- `durable-prefix recompute == 0` and `hybrid_discard == 0`.
- The request's HTTP call completes.

`disposition` MAY read `PARTIAL reason=shortfall` **iff** `granted == D_req` and
the shortfall equals `requested - D_req` (the durable-boundary-external tail; for
R121's prefix this tail is 11 tokens, `requested=27339, D_req=27328`). Likewise
`restore_success.n_tokens == granted - 2` is the known telemetry off-by-two
convention (R121 F1: granted 42752, success 42750); it is accepted **only when
`kv_fetched == D_req`**. The literal `disposition==FULL` text of the R125
contract is superseded here because every R121-derived prompt carries that
external tail; this correction is frozen BEFORE the run and does not retro-change
any R125 verdict.

## Timing / record
Also record `t_feasible` (first instant all blocked domains are
gen-advanced-or-capacity-satisfiable), `t_wake`, `t_deadline`, and require
`t_feasible < t_deadline`. Per run record: `D_req`, T `device_hit/host_hit`,
park `wait_reason`+cursor, F1 release epoch before/after, T `prefetch_issued`
epoch, per-domain `kv/mamba` `gen_before/after`, `restore_disposition`,
`restore_success.n_tokens`, `restore_hybrid_finalize`.

## Verdict rules
- PASS a run iff Gates 0,1,2,3 all hold.
- If a run reaches the chain but Gate 2 is NON-EVIDENCE, run the next replay.
- BLOCKED/NOT_VERIFIED iff all replays are exhausted without a Gate-2 hit, or the
  chain cannot be re-established (report exact missing transition).
- No mutation of R121–R125 artifacts; no product code change; no profile change;
  no server restart; forbidden `/flush_cache`, `/close_session`; no new
  instrumentation. <= 3 live replays; <= 60 min; <= 200 HTTP.

## Deliverables
`work/R126-bundle/` (per-run `run<N>/` with `raw.log`, `probe.log`,
`requests.jsonl`, `state.jsonl`, `driver.out`, `sha256sums.txt`) and report
`work/P1-DURABLE-PREFIX-REPLAY-20260912-R126.md` with the per-run Gate table.
