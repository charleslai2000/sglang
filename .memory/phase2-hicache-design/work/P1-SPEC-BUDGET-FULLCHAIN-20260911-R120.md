# P1 SPEC_BUDGET full-chain — R120 evidence report

- task_id: `P1-SPEC-BUDGET-FULLCHAIN-20260911-R120`
- invocation: `ses-p1-spec-budget-fullchain-r120-20260911` (fresh)
- role: `tester`
- epoch: `2026-09-11`
- status: **not_verified** (verification executed to completion; P1 does NOT close)

Frozen acceptance file verified before starting:
`work/R120-bundle/P1-ACCEPTANCE-CONDITIONS.md` sha256
`b5ffa106be7863a2baedd528249eb6bccb63469619af73970a4c477813c27822` (matches;
accepted). Server read-only throughout: PID 48746 (`launch_server`), scheduler
48806, `http://127.0.0.1:30000`, health 200 before, throughout, and at finish.
Repo read-only HEAD `4f41f5bab562b99562f30c67540eb05344d13637` (source hashes
unchanged vs R119). No product edits, no instrumentation, no synthetic events,
no child agents, no decoys, no server start/stop/restart/kill/reconfigure.

## Result

The single clean no-decoy line (one F1 + one T, distinct build sessions, one
`input_ids` batch replay `prompt=[[F1],[T]]`) was run 3× under the frozen R117
profile. **The SPEC_BUDGET park does not occur and the chain is not produced.**

At the replay, T is already device-resident (`device_hit_tokens=27520/27521`),
so its prefetch is declined `too_short` and T is never a speculative candidate.
F1 is 95 % device+host resident (`device_hit=36864`, `host_hit=4096`), so its
replay prefetch is only **2047 tokens** — far below the 39321 speculative limit:
the budget is never exhausted, nothing parks, and T is recomputed
(`disposition=RECOMPUTE reason=too_short`). Upstream, neither build reached full
L3 durability (frozen `storage_persisted`: F1 20 nodes/40958 of 43008; T 1
node/2046 of 27521). The no-decoy workload supplies no eviction/write-back
pressure, and the live host pool is near-saturated (free+evictable 28672 <
F1+T 70529), so the evicted suffix is not written through. All five frozen
conditions are unmet.

## Workload (one clean line, no decoys)

All requests `POST /v1/completions`, `model=/mnt/data/models/qwen35-gptq`,
`temperature=0`, `max_tokens=1`, `prompt` as `input_ids` (tokenizer is not
batch-encode enable), top-level `session_id`.

| tag | session | prompt_tokens | rid | HTTP | elapsed_s |
|---|---|---|---|---|---|
| build-F1 | `r120-s-F1` | 43008 | `r120-p1-build-F1` | 200 | 13.955 |
| build-T | `r120-s-T` | 27521 | `r120-p1-build-T` | 200 | 15.221 |
| batch replay `[F1,T]` | `r120-s-R` | 70529 | `r120-p1-R-F1`,`r120-p1-R-T` | 200 | 11.305 |

Full transcript: `R120-bundle/requests.jsonl`. Prompts are whitespace word
sequences with a unique rare-Unicode first token (R114 root-promotion recipe);
F1 43008 > 39321 so a *full-prefix* F1 issue would exhaust the budget.

**Harness/API limitation (reported, not a product defect):** a single
`GenerateReqInput` batch carries one scalar `session_id` for every sub-request
(`io_struct.py:878`), and a per-item `session_params` list fails in
`tokenizer_manager.py:1369`. Distinct *build* sessions were used
(`r120-s-F1` gen 39, `r120-s-T` gen 40) with one replay session
(`r120-s-R` gen 41); per-sub-request distinct replay sessions are not
expressible in one batch.

## Per-condition verdicts (C1..C5)

| # | condition | verdict | decisive refs |
|---|---|---|---|
| C1 | T full durable L3 coverage | **FAIL** | `probe.log:671` T build persisted 1 node/2046 tok (frozen); `probe.log:583/584` T replay prefetch=0 declined_too_short → no storage query; `raw.log:36547` T device_hit 27520 |
| C2 | T park uniquely SPEC_BUDGET | **FAIL** | `grep -c SPEC_BUDGET raw.log` = 0; `raw.log:36553` decision=hold state_funnel spec=0; `raw.log:36554` held declined_too_short |
| C3 | release→wake causality | **FAIL** | `raw.log:36548` F1 replay prefetch 2047; `raw.log:36559` spec=2047 ≤ limit 39321; no park to release/wake |
| C4 | full restore gate | **FAIL** | `raw.log:36552` `restore_disposition disposition=RECOMPUTE requested=0 granted=0 reason=too_short`; no finalize/restore_success for T |
| C5 | host headroom sufficient | **FAIL** | `raw.log:56235` free=1114 evictable=27558 locked=36864 → allocable 28672 < F1+T 70529 |

`missing_legs`: all eight (`spec_budget_park`, `release_epoch_advance`,
`rh_reentry_wake`, `l3_to_l2_stage`, `host_ready`, `admission`,
`l2_to_l1_restore_generation`). Full detail + exact field values:
`R120-bundle/condition-evidence.md`, `R120-bundle/chain.json`.

## Exact unmet condition and decisive evidence

**Primary unmet condition: C2/C3 — no SPEC_BUDGET park is emitted.**
- `grep -c SPEC_BUDGET raw.log` = **0** in the entire frozen window.
- `raw.log:36547` `rh_match_prepare r120-p1-R-T fill_len=27521
  device_hit_tokens=27520 host_hit_tokens=0` → T already resident.
- `raw.log:36554` `ready_stage r120-p1-R-T result=held
  reason=declined_too_short`; `raw.log:36552` `restore_disposition
  disposition=RECOMPUTE requested=0 granted=0 reason=too_short`.
- `raw.log:36548` `prefetch_issued r120-p1-R-F1 prefetch_length=2047`;
  `raw.log:36559` `speculative_budget_used_tokens=2047` vs limit `39321` → the
  budget is never exhausted, so the F1-issue→T-park leg cannot exist.

**Product behavior vs harness/profile limit (evidence, not root-cause
ownership):**
- The park mechanism itself is present and does fire when a non-resident
  candidate exceeds the limit — the two *build* requests saw it
  (`build-F1` prefetch 43007, `build-T` 27520 both > 39321, `exclude`, then
  `revoked_full_miss`). No issuer/release/wake ever followed from those.
- The blocker is physical: with only F1(43008)+T(27521) and no decoys, both
  prefixes stay cache-resident (T fully; F1 95 %), so neither needs a
  budget-sized L3 stage at replay. The device pool (65536) is oversubscribed by
  only ~5 k, which is not enough to evict F1's 43 k prefix, and the host pool
  (131073 logical) absorbs the rest. Full L3 durability of the *evicted* suffix
  also fails: the live host pool is nearly saturated (`raw.log:56235`
  free=1114, evictable=27558, locked=36864; `raw.log:56236` free=2010,
  evictable=22566, locked=40960), so the write-back drain cannot complete
  (T frozen at 2046/27521). The R119 runs required decoy pressure to make the
  target fully durable **and** non-resident; the no-decoy constraint removes
  exactly that pressure. This is a workload/profile structural limit, not a
  demonstrated product defect and not (to our knowledge) a harness defect.

**C5 basis:** `host_allocable := full_free + full_evictable` at the replay
promotion instant = `1114 + 27558 = 28672` tokens (`raw.log:56235`).
`F1_required + T_required = 43008 + 27521 = 70529`, deficit ≈ 41857; no
non-negative margin satisfies the inequality. The static logical pool (131073)
is not allocable (36864 tokens locked + write-back working set).

## Artifacts (`work/R120-bundle/`) and sha256

| file | sha256 |
|---|---|
| `raw.log` (frozen server slice lines 2051152–2107393, 56242 lines) | `0cb8ea6bc7898f392e99e66a570e16326447f1c3e4a440064282aecd5d3f2347` |
| `probe.log` (frozen probe slice beyond byte 33890204) | `7936097d8a6de7ce8c76efab659ae31967aa2b4bfaa1bd37fcf5d93c597287b1` |
| `requests.jsonl` (complete transcript incl. batch terminal response) | `39a327bad565eb2cc0341bd7d5a2012f6f9aba96f2dbf8bc3b95a7f325ba9f17` |
| `state.jsonl` | `31d7dd015e251431ff3d1789b7fabef8b2441217b3d723a5326b070ae1abd5f4` |
| `chain.json` (per-condition C1..C5 + evidence + unmet_conditions) | `27ece4c370f2823408e2911ffd08c452c3f985d1948cf95179e9a1b9ffa531b6` |
| `condition-evidence.md` | `8a12c98c9bb703c70c2d1cb78d7a7f5149152054d7b741c9a3a74b4c947ae525` |
| `manifest.json` (`p0b.raw-bundle.v3`) | `6a2b5b2c7f68f518251c5395f9922e16fe2483518e6413daea6c71c58d4d3fd1` |
| `baseline-offsets.txt` | `36c0b0946be45b9f40d0a39e7752cd41f754d3efd162891e7375f756aae747b8` |
| `driver120.py` | `6fd3502f508917963eb4e66cdfddc91c613c9573c0c71b362ce6ab4d708495cd` |
| `driver.out` | `d77ad7def1d1d6d6ec2483eba9a52040cfcc44b57bcb97cce38ec4646f7542fc` |
| `watch.log`, `analysis-run1.txt`, `evidence-refs.txt`, `freeze-offsets.txt` | `d6e7f46b…`, `704e853f…`, `32e7a6f7…`, `4edfd833…` (`sha256sums.txt`) |

Baselines: server log start line `2051151` (bytes `256762570`); probe start
byte `33890204` (line `21764`); server PID 48746 / scheduler 48806; health 200.

## Budget

- HTTP: 4 POST (1 tokenize + 2 builds + 1 batch) + 4 GET health = **8** (limit 40).
- Wall clock: baseline `00:01:23` → run `00:02:22`–`00:03:42` → freeze
  `00:04` → report `00:09`: **~8 min** (limit 60).
- Server left running and healthy (`GET /health` → 200); no server/GPU action.

## Followups (for the orchestrator; not done here)

1. To exercise the park→release→wake→full-restore chain, a task must supply
   eviction/write-back pressure (the R119 decoys did) while keeping host
   headroom >= F1+T — the two requirements conflict under the frozen R117
   profile with a single F1 + single T. A fresh server (empty host pool) or a
   profile with a drainable working set is the natural next experiment.
2. A cache-namespace lever (replay with a different `cache_salt`/`extra_key`,
   which namespaces only the in-process radix tree while L3 keys stay
   token-only) could force host-absence, but it changes the cache identity and
   is outside the sanctioned R118/R119 path, so it was **not** used.
3. Per-sub-request distinct sessions in one batch are not supported by this
   build; if the workload requires them, that is an API/product gap to record.
