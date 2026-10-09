# P1 SPEC_BUDGET chain — R119 evidence report

- task_id: `P1-SPEC-BUDGET-CHAIN-20260911-R119`
- invocation: `ses-p1-spec-budget-rerun-r119-20260911` (fresh)
- role: `tester`
- epoch: `2026-09-11`
- status: **done**

Server (read-only, never started/stopped/restarted/killed/reconfigured):
PID `48746` (`launch_server`), scheduler child PID `48806`,
`http://127.0.0.1:30000`, health `200` throughout and at finish.
Repo (read-only): `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
(HEAD `4f41f5bab562b99562f30c67540eb05344d13637`). Model
`/mnt/data/models/qwen35-gptq`. No product edits, no instrumentation, no
synthetic events, no child agents. Public HTTP only (`GET /health`,
`POST /v1/tokenize`, `POST /v1/completions`) plus reads of the existing
server log and pinned `/tmp/t38c-probe.log`.

## Result

The COMPLETE SPEC_BUDGET causal chain (legs 1–8) was captured for target
identity `r119-p1-R-T` / `lifecycle_key r119-p1-R-T:28` in session
`r119-s-p1` (generation 28) under the unchanged frozen R117 profile.
All legs are real events with file:line refs (`chain.json`). The batch
HTTP request returned **200** in **69.759 s** (terminal outcome
`completed`), and no `restore_recompute` and no hybrid discard were
emitted for the target.

A second run (`p2`, secondary/corroborating) proved the R118-defect-3
durability fix end-to-end for the target prefix (27392/27403 tokens
durable in L3) but the target's host allocation timed out and it
recomputed (`restore_recompute cause=timeout`); `p2` is therefore not
the primary chain. Both runs together bracket the residual host-pool
bottleneck honestly (see §6).

## 1. R118 defects fixed and how they were verified

1. **`trigger()` NameError.** The session id is now a true module global
   and is also passed explicitly; `trigger(i)` no longer reads a
   function-local name. All p1 trigger requests returned HTTP 200 and the
   trigger rids are present in the server log (`r119-p1-trig-1..4`;
   `grep -c` = 30 / 6 / 6 / 6), proving the triggers actually reached the
   server and entered the ready-horizon passes.
2. **Monitor exited and aborted the batch.** The batch replay now runs in
   a thread whose HTTP client is kept connected and *joined* with
   `R119_KEEPALIVE` (default 1680 s); the driver records the terminal
   outcome. p1's batch returned `http=200 elapsed_s=69.759` and the
   driver logged `outcome=completed` (not `still-pending`/`aborted`).
   (`requests.jsonl`, `state.jsonl` `evt=monitor_end`.)
3. **Candidate-prefix durability.** Before the replay the driver writes a
   small clean unique-first-token seed (2500 tokens, rare-Unicode first
   token) per candidate, then the full write in the same session, then
   decoys to force eviction, and waits on the existing probe log for
   `storage_persisted` for the candidate build rids. p1 persisted the
   target seed (`r119-p1-T-seed`, 46 `storage_persisted`); p2 (target
   built full, no seed) persisted the target full prefix and the target's
   replay `pc_storage_query` hit **27392/27403** tokens. This is the
   R114 recipe's effect confirmed live.

## 2. Workload (p1, primary)

All requests `POST /v1/completions`, `model=/mnt/data/models/qwen35-gptq`,
`temperature=0`, `max_tokens=1`, top-level `session_id`, prompt as
`input_ids` (batch path; tokenizer is not batch-encode enabled); HTTP 200
for every complete.

| tag | session | prompt_tokens | rid |
|---|---|---|---|
| seed-T/seed-F1/seed-F2 | `r119-s-p1` | 2500 each | `r119-p1-T-seed`, `-F1-seed`, `-F2-seed` |
| build-T/F1/F2 | `r119-s-p1` | 27129 / 42796 / 43007 | `r119-p1-T/F1/F2` |
| build-D1..D4 | `r119-p1-dN` | 43032/42814/42701/42751 | `r119-p1-DN` |
| batch replay | `r119-s-p1` | [F1,F2,T] | `r119-p1-R-F1`, `-R-F2`, `-R-T` |
| triggers 1..4 | `r119-s-p1` | 7 | `r119-p1-trig-N` |

Full transcript incl. the batch terminal response: `requests.jsonl`.

## 3. The chain (p1, primary; raw.log line = frozen artifact line)

Target `r119-p1-R-T`, session `r119-s-p1`, generation **28** (constant
across all 50 target `rh_match_prepare` records), prompt 27129 tokens.

1. **SPEC_BUDGET park** — `raw.log:99952` (server 1676672)
   `evt=rh_preadmission_decision`, `decision=exclude reason=negative_cache`,
   `fingerprint=(2,2,'NONE',None,True,'SPEC_BUDGET',42795,
   (470,426,29,42795,('r119-p1-R-F1','r119-p1-R-T')),426,0,65536,42795,
   39321,42795,'exclude','negative_cache')`,
   `negative_cache_blocked=True negative_cursor=42795`,
   `staging_eligible=True restore_potential=True`,
   `speculative_budget_used_tokens=42795 > 39321`,
   causal epoch `l3_publish=470 host_headroom=426 host_release=29
   spec_budget=42795 spec_budget_release_epoch=62`. Issuer
   `r119-p1-R-F1` issued `prefetch_length=42795` at `raw.log:99941`
   (exhausts the budget).
2. **Budget-release epoch strictly advances 62 → 63** — release event
   `raw.log:100044 preview` (`prefetch_revoke rid=r119-p1-R-F1
   storage_hit=42752 requested=42795 miss_reason=alloc_failed`); the
   target is first re-decided at `spec_budget_release_epoch=63` at
   `raw.log:100057`.
3. **Target RH re-entry / wake** — `raw.log:100057`
   `rh_preadmission_decision ... decision=issue reason=issued` at epoch
   63; `raw.log:100058 evt=ready_stage schema=rh_stage.v2
   attempt_id=r119-p1-R-T:prefetch:1 issue_origin=READY_HORIZON
   restore_state_after=RESTORING result=issued`.
4. **L3→L2 stage** — `raw.log:100055 evt=prefetch_issued
   prefetch_length=27128`; revoked once on host alloc
   (`raw.log:113939 prefetch_revoke storage_hit=2496 ... alloc_failed`,
   `raw.log:113940 restore_state=WAIT_CAPACITY HOST_ALLOC`), retried
   (`raw.log:132545 restore_retry cause=capacity`,
   `raw.log:132546 prefetch_issued`), then
   `raw.log:206222 evt=prefetch_finalize completed_tokens=2496
   mode=cache`. Probe evidence: `probe.log:2604,2746 pc_storage_query
   rid=r119-p1-R-T query_suffix_len=27128 kv_hit_pages=2496
   storage_hit_count=2496`, `probe.log:3004 pc_l3_host completed_tokens=2496
   requested_tokens=27128`.
5. **Host-ready** — `raw.log:206228 evt=ready_host schema=rh_ready_host.v1
   attempt_id=r119-p1-R-T:prefetch:2 issue_origin=DEMAND_RETRY
   completed_kv_tokens=2496 required_aux_pools=['mamba']
   completed_aux_units={'mamba':1}`; `raw.log:206227 restore_state=READY`.
6. **Admission** — `raw.log:206233 evt=admission rid=r119-p1-R-T`.
7. **L2→L1 restore + generation** — `raw.log:206229 evt=restore_ready`;
   `raw.log:206234 evt=restore_success rid=r119-p1-R-T n_tokens=2484`
   (**cached_tokens > 0**); completion emitted
   (`requests.jsonl` batch-replay `usage.completion_tokens=3`).
8. **Safety** — `restore_recompute` events for the target: **0**;
   `disposition=RECOMPUTE`: none; hybrid discard: none. Accepted
   all-or-nothing finalize at `raw.log:206223 evt=restore_hybrid_finalize
   result=accepted all_or_nothing=true kv_expected=2496 kv_fetched=2496
   lifecycle_key=r119-p1-R-T:28`. (The disposition at `raw.log:206224` is
   `PARTIAL requested=27128 granted=2496 reason=shortfall`, i.e. a
   partial restore, not a full-prefix recompute.)

`missing_legs`: **none** (all 8 legs present). `chain.json` carries the
joined chain with `raw.log`/`server` line refs and the explicit
`missing_legs: []`.

## 4. cached_tokens / recompute / hybrid_discard checks (p1)

- `restore_success n_tokens=2484` > 0 (`raw.log:206234`);
  `HiCache prefetch success req=r119-p1-R-T completed=2496 matched=12
  loaded=2484` (`raw.log:206226`).
- `restore_recompute` for `r119-p1-R-T`: **0 occurrences** in the frozen
  `raw.log` (regex scanned). No `MISS_RECOMPUTE`, no `cause=miss`/
  `cause=too_short`, no hybrid-discard.
- `restore_hybrid_finalize result=accepted all_or_nothing=true` — the
  consumed restore was accepted; no discard path.
- Session generation **28** consistent from park through the accepted
  finalize (`lifecycle_key=r119-p1-R-T:28` in both the park fingerprint
  context and the finalize).

## 5. Terminal outcome (p1)

Batch replay `r119-p1-R-F1/F2/T`: HTTP **200**, `elapsed_s=69.759`,
`usage={prompt_tokens:112932, completion_tokens:3, total_tokens:112935}`,
`err=null`. Driver `state.jsonl` `evt=monitor_end outcome=completed
still_alive=false`. The connection stayed open for the whole target
lifecycle; nothing was aborted.

## 6. Secondary run p2 (corroboration, not the primary chain)

Target `r119-p2-R-T` / `r119-p2-R-T:33`, session `r119-s-p2`, gen 33,
27404 tokens; target built full (no seed).

- Park `SPEC_BUDGET` server line 1922880, `spec_budget=43006`,
  `spec_budget_release_epoch=74`, `staging_eligible=True`.
- Release epoch advanced 74 → 75 → 76.
- Target `pc_storage_query` at replay: `kv_hit_pages=27392 /
  query_suffix_len=27403` — the FULL target prefix was L3-durable, i.e.
  the R118-defect-3 fix works end-to-end.
- However the target's stage was revoked twice on host allocation
  (`revoked:alloc_failed`, server lines 1922941 and 1992224) and then
  `evt=restore_recompute rid=r119-p2-R-T cause=timeout
  final_storage_survivability=host` (server 2050993). Batch HTTP 200,
  87.579 s.

Interpretation (evidence, not root-cause ownership): under the frozen
profile the L3→host staging path for the target is still gated by host
headroom; a fully-durable target can time out on host alloc and
recompute, while a partially-durable target can succeed (`p1`). The
`p1` chain is the complete one; `p2` is preserved as the real failure it
is.

## 7. Artifacts (bundle `work/R119-bundle/`) and sha256

| file | sha256 |
|---|---|
| `raw.log` (frozen server-log slice, lines 1576721–1782977, 206257 lines) | `41939d53bf4efe8b724e1cc9ff8df66db7c4739a66302623c8ee43a1240c2898` |
| `probe.log` (frozen probe slice beyond byte 22806236) | `0c760323a84b980443a90f19d12e32ef08c6ed9400c18bc928bdec8ecdf4ba2a` |
| `requests.jsonl` (complete p1 transcript incl. batch terminal response) | `5d1998563749503a36e76f78805c0588ff7995c2c90630dd90f1d332cba5b37e` |
| `state.jsonl` | `291271f25c013a7433725c55357846e7b47ee2c217722781a8b36c00224736fa` |
| `chain.json` (joined chain + secondary p2) | `4445f03ed971457bd86f6dd989519e818af62007b9511c170864669e2c527301` |
| `chain-primary.json` (copy) | `4445f03ed971457bd86f6dd989519e818af62007b9511c170864669e2c527301` |
| `manifest.json` (`p0b.raw-bundle.v3`) | `257d96725dda168a8403c8ecbe529df26840d233fd87bc01c36470914bec8123` |
| `baseline-offsets.txt` | `55c5a52ef4205dd43ffb54c8296853035550f20f77a613c021b6169065f23b71` |
| `driver119.py` (fixed driver) | `0b6c9f9aa57d90bdaa6003d0bab65e02e97d7e9bba49d904b70f26bbc2956ab4` |
| `driver.out` (p1 run log) | `d8f228a40b1a42eb5b36f18ce83fc0f7aedaf70c44d269d75cc08267ea264024` |
| `driver-run2.out` (p2 run log) | `ef3759bd1977a7e15ec0394a6358175497f618312b8fb4c62178ddf1fc2b451b` |
| `requests-run2.jsonl` / `state-run2.jsonl` | `8533a313db0ec7fb2bd0d7586e01d194c6fb26d4ce7b39edb31b29b17b9a516a` / `7c6d12951e5d4a6b4b44c461b1c45cc4fb7a62499e2945f9423ef8e9beb3559d` |
| `source-hashes.txt`, `watch.log` | `881c7770a293c0dc148196c75897875b1a5a2e636a179c08d618950fb82efaeb`, `58e441cc00b1d06129180763ef1e45449a8e6305080c2d1827d555f91e740fc7` |

Baselines (`baseline-offsets.txt`): server log start line `1576720`
(bytes `201991953`), probe log start byte `22806236`; server PID 48746,
scheduler 48806; health 200.

## 8. Honest gaps / limitations

1. **p1 target L3 coverage is partial (2496/27128 tokens).** The durable
   build identity for the p1 target finalize is the small clean seed
   (`build_rid=r119-p1-T-seed`); the full-write extension was not promoted
   to L3 before the replay. The target therefore restored its 2496-token
   durable prefix and ordinary prefill recomputed the remainder. No
   `restore_recompute` disposition was emitted (the disposition was
   `PARTIAL/shortfall`), so the specified FAIL condition is not met, but
   the reader should treat leg 4/7 as a partial-coverage restore.
2. **The residual blocker is host-pool headroom, not durability.** p2
   demonstrates a fully durable target (27392/27403) that still failed to
   complete the L2→L1 restore for `cause=timeout` after two
   `revoked:alloc_failed` host-allocation attempts. Whether the parked
   tail *should* be re-queued/prioritised on the host-alloc wake is left
   to the mechanism owner; no product defect is asserted here.
3. p1's target stage was itself revoked once on host alloc
   (`raw.log:113939`) and needed a retry before finalizing; the
   `host_headroom` at park was 426 tokens against a 27128-token request.
4. Only the 8-key top-level L3 object set per query is observable in the
   probe source; per-page hash enumeration is absent (same granularity
   gap recorded by R116).

## 9. Budget accounting

- HTTP requests: p1 ≈ 16 (1 tokenize + 3 seeds + 3 builds + 4 decoys + 4
  triggers + 1 batch) + health; p2 ≈ 17. Total well under 200.
- Wall clock: baseline `23:28:06` → p1 freeze `23:33:18` → p2 done
  `~23:42:30`: ~15 min, under the 60 min budget.
- Server left running and healthy (`GET /health` → 200); no server/GPU
  action.
