# P0-B-DURABLE-RECIPE-20260911-R114 — live P0-B chain with an in-window durability barrier (11/11 VERIFIED)

- Task ID: `P0-B-DURABLE-RECIPE-20260911-R114`
- Invocation: `ses-p0b-durable-recipe-r114-20260911` (fresh)
- Role: `tester`
- Epoch: `2026-09-11`
- ENTRY: `ACCEPT`
- Repo (read-only, not modified): `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
  (HEAD `4f41f5bab562b99562f30c67540eb05344d13637`)
- Server (read-only, never started/stopped/restarted/killed/reconfigured): PID `48746`
  (`launch_server`), scheduler child PID `48806`, `http://127.0.0.1:30000`.

## status

**done — VERIFIED (11/11 predicates, reducer exit 0).**

The R113 gap (`positive_full_hit`, predicate 4) is closed. An in-window
`p0_durable` `durability_barrier` was produced for `session_generation = 10`,
which is exactly the generation of the target `lifecycle_key`
`d4cd1983020c4c5799012e909d7a31b4:10`. The target park → allocability advance →
grant (with a real released predecessor) → accepted all-or-nothing finalize →
`ready_host` READY chain is complete inside the frozen window.

The server was left running and healthy (`GET /health` → 200).

## 1. Constraint compliance and baselines

- Only public HTTP (`GET /health`, `POST /v1/completions`) and reads of the
  existing server log and pinned `/tmp/t38c-probe.log` were used.
- No server start/stop/restart/kill/reconfigure, no repo/source edits, no
  product imports, no instrumentation, no synthetic events, no child agents.
- Baseline recorded before any load (`R114-bundle/baseline-offsets.txt`):
  - server log `/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-r112.log`
    start line `821467` (bytes `111270307`), slice frozen through line `1056600`;
  - `/tmp/t38c-probe.log` start byte offset `7692189` (line `4994`), end bytes
    `10668022`.
- HTTP budget: 14 POSTs + 4 GETs = **18 requests** (limit 200). Wall clock from
  baseline (`22:32:07`) to chain capture (`22:39:17`) to freeze (`22:40:00`):
  **~8 min** (limit 60).

## 2. The durable recipe (two-phase, SAME session generation)

The hard step was producing a barriered write whose parent chain stays
contiguous. Observed, reproducible finding:

1. **First attempt failed.** A small clean write (`r114-s`, 2836 tokens,
   `clean-probe-1`) with the R113-style ASCII prefix `"[SESSION-…"` was a full
   miss (`device_hit_tokens=0`, `host_hit_tokens=0`) and its KV write reached
   `backup_ack_drain` with `kv_durable=true, mamba_durable=true, result=complete`
   for nodes 313/314, but **no `storage_persisted`/`durability_barrier` fired**:
   the new nodes attached under the shared, never-persisted `"[SESSION-"` prefix
   node, so `advance_storage_persisted` (parent must be root or already
   persisted) promoted nothing.
2. **The fix that worked:** make the clean write's **first token unique** by
   prefixing four rare alchemical Unicode code points
   (`chr(0x1F700 + k)` per session). A second small clean write
   (`r114-c1`, 3528 tokens, `clean-probe-2`, nodes 315/316) then promoted and
   emitted `storage_persisted` + `durability_barrier` at `session_generation=10`
   (`probe.log:62-63`, `70-71`).
3. The same session `r114-c1` then received the large target write
   (27051-token prompt) at the **same generation 10**; four independent
   pressure sessions (`r114-q1..q4`, each with its own unique-prefix clean seed)
   saturated the host; the target session prompt was replayed as the second
   FIFO waiter and parked on `HOST_ALLOC`.

## 3. Exact workload (`R114-bundle/requests.jsonl`)

All requests: `POST /v1/completions`, `model=/mnt/data/models/qwen35-gptq`,
`temperature=0`, `max_tokens=1`, top-level `session_id`, HTTP **200**.

| tag | session_id | prompt_tokens | rid (HTTP) | elapsed_s |
|---|---|---|---|---|
| clean-probe-1 | `r114-s` | 2836 | `fe5487c66e734264883f86cfd0149270` | 1.64 |
| clean-probe-2 | `r114-c1` | 3528 | `1e3dbabc421748acbd27fae9990fff57` | 1.62 |
| target-build | `r114-c1` | 27051 | `25dd9122eff34a0eadcd0fe0168746d6` | 6.11 |
| seed-q1 | `r114-q1` | 3372 | `139f883c5e034d7ebb60dd5afe079bcb` | 3.15 |
| pressure-q1 | `r114-q1` | 42864 | `1b165e8c56ab473f8ac718f42d3acd78` | 11.33 |
| seed-q2 | `r114-q2` | 3374 | `d6456323821f4269b8a15ad5c3230986` | 3.07 |
| pressure-q2 | `r114-q2` | 43048 | `37479102501d4b2984df2d46b967d62a` | 11.12 |
| seed-q3 | `r114-q3` | 3417 | `0ddcd615a4d041afb4c723d149d8bcb7` | 3.32 |
| pressure-q3 | `r114-q3` | 42779 | `3ef89387f1aa42e5936aa5b34ab509b1` | 11.49 |
| seed-q4 | `r114-q4` | 3380 | `13355253f0744dc79ceeccb4c375499f` | 3.47 |
| pressure-q4 | `r114-q4` | 43002 | `111b20af92f74ef394ae44deb4b9b0b7` | 12.01 |
| waiter-A (first FIFO waiter) | `r114-q1` | 42864 | `d07965f8447846e9acd070e6505b2485` | 66.92 |
| waiter-B = **target** (replay) | `r114-c1` | 27051 | `d4cd1983020c4c5799012e909d7a31b4` | 85.96 |

Complete transcript: every request above, including both waiters' HTTP
responses, is in `R114-bundle/requests.jsonl` (no R113-style transcript gap).

## 4. Barrier record(s) for the target generation (10)

Frozen `probe.log` (durable slice beyond byte `7692189`) contains **two**
complete barriers for `session_id="r114-c1"`, `session_generation=10`:

```
probe.log:63  {"evt":"durability_barrier","session_id":"r114-c1","session_generation":10,
  "build_rid":"1e3dbabc421748acbd27fae9990fff57","node_id":"315",
  "final_kv_hash":"ee4616e00d20ff75fe29b57bd1093452f576cadbd136096a04d80f9f2b217bbf",
  "kv_durable":true,"mamba_durable":true,"kv_completed_tokens":2048,"kv_requested_tokens":2048,
  "mamba_expected_pages":1,"mamba_succeeded_pages":1,"result":true,
  "reason":"kv_ack_mamba_ack_frontier"}
probe.log:71  {"evt":"durability_barrier","session_id":"r114-c1","session_generation":10,
  "build_rid":"1e3dbabc421748acbd27fae9990fff57","node_id":"316",
  "final_kv_hash":"b0e1fad8ef3aa4f64fac60632fe5b964ce400e063891367ffe50790563feb410",
  "kv_durable":true,"mamba_durable":true,"kv_completed_tokens":1472,"kv_requested_tokens":1472,
  "mamba_expected_pages":1,"mamba_succeeded_pages":1,"result":true,
  "reason":"kv_ack_mamba_ack_frontier"}
```

Promotions backing them: `storage_persisted` `probe.log:62` (node 315,
`result=true`, `context_complete=true`) and `probe.log:70` (node 316).

## 5. Target park / grant / finalize / READY (frozen `raw.log` refs)

Target `rid` **`d4cd1983020c4c5799012e909d7a31b4`**, `lifecycle_key`
**`d4cd1983020c4c5799012e909d7a31b4:10`** (session `r114-c1`, gen 10).

- Pre-wake retry `raw.log:71261` (`evt=restore_host_alloc_retry_result`,
  `retry_outcome="revoked_alloc_failed"`, `attempt_id=null`, `retry_grant=false`,
  `genuine_miss=false`, `crop_attempted=false`, `lower_checkpoint_queried=false`).
- **Target park** `raw.log:71263` (`evt=restore_host_alloc_wait`):
  `state="WAIT_CAPACITY"`, `reason="HOST_ALLOC"`,
  `wait_id="…:wait:11"`, `fifo_sequence=11`,
  `positive_hit_tokens=27008 == requested_primary_tokens=27008 > 0`,
  `blocked_domains=["kv","mamba"]`,
  `captured_generations={"kv":265,"mamba":427}`, `cache_instance_id=1`.
- **Predecessor release terminal** `raw.log:184245`
  (`decision="release"`, `event_id=terminal_event_id="run-48806-4187756182262:host-alloc:174"`,
  `wait_id="d07965f8447846e9acd070e6505b2485:wait:10"`,
  `fifo_sequence=10`, `terminal_state="TIMEOUT"`), strictly before the grant.
- **Target grant** `raw.log:184273`
  (`decision="grant"`, `event_id=wake_event_id="run-48806-4187756182262:host-alloc:178"`,
  `retry_grant=true`, `retry_skip=false`,
  `current_generations={"kv":269,"mamba":436}` vs captured `{kv:265,mamba:427}`
  (strictly advanced for both blocked pools), `cache_instance_id=1`,
  `predecessor_wait_id="…:wait:10"`,
  `predecessor_terminal_event_id="…:host-alloc:174"`,
  `predecessor_terminal_state="TIMEOUT"`, `predecessor_lineage_reason=null`).
  Interleaved non-grant holds at `raw.log:184257/184262/184268`
  (`hold_no_generation`) are not grants.
- **Accepted all-or-nothing finalize** `raw.log:235044`
  (`result="accepted"`, `all_or_nothing=true`, `restore_state_after="READY"`,
  `kv_expected=kv_fetched=27008`, `sidecars={"mamba":{"expected":1,"fetched":1}}`,
  `attempt_id="d4cd1983020c4c5799012e909d7a31b4:5"`,
  `wake_event_id="run-48806-4187756182262:host-alloc:178"`,
  `attempt_origin="HOST_ALLOC_WAKE"`).
- **READY** `raw.log:235049` (`evt=ready_host`):
  `lifecycle_key=d4cd1983020c4c5799012e909d7a31b4:10`,
  `finalize_result=accepted`, `completed_kv_tokens=27008`,
  `attempt_id="d4cd1983020c4c5799012e909d7a31b4:prefetch:2"`,
  `required_aux_pools=['mamba']`, `completed_aux_units={'mamba': 1}`,
  `wake_event_id="run-48806-4187756182262:host-alloc:178"`,
  `restore_state_before=RESTORING`, `restore_state_after=READY`.

## 6. Frozen reducer verdict

Reducer: `work/R111-reducer/p0b_reducer.py` (canonical). Command:

```
cd .memory/phase2-hicache-design/work/R111-reducer
source /mnt/data/neuron/envs/sglang-3090-opt/activate-sglang-3090.sh
python p0b_reducer.py --events <abs>/R114-bundle/raw.log <abs>/R114-bundle/probe.log \
    --manifest <abs>/R114-bundle/manifest.json
```

**Exit code: 0. Status: `VERIFIED`. `raw_event_count: 1746`.** stderr empty.

| # | predicate | passed | reason |
|---|---|---|---|
| 1 | provenance | ✅ true | |
| 2 | singular_identity | ✅ true | |
| 3 | pid_profile_source_binding | ✅ true | |
| 4 | positive_full_hit | ✅ true | barriered gen-10 write + target park 27008≥27008 |
| 5 | host_alloc_park | ✅ true | |
| 6 | generation_transition | ✅ true | kv 265→269, mamba 427→436 (strict) |
| 7 | fifo_predecessor | ✅ true | terminal `host-alloc:174` (`TIMEOUT`) precedes grant |
| 8 | attempt_lineage | ✅ true | finalize+READY both name `host-alloc:178` |
| 9 | accepted_finalization | ✅ true | |
| 10 | ready_after_finalize | ✅ true | |
| 11 | negative_safety | ✅ true | no `genuine_miss`/crop/no-L3/repeat/partial |

11/11. The `raw_provenance` input gate passed (all raw/source hashes matched,
no caller-authored summary keys).

## 7. Producer identity (from captured records)

- `process_id` (scheduler): **48806**
- `run_id`: **run-48806-4187756182262**
- `profile_id`: **profile-97ee3d5d3bfdca6237dc746e**
- `source_build`: **4f41f5bab562b99562f30c67540eb05344d13637:03750d8519fdae277a0d04938c53c73ff2d5400be8c6f9f51a3d2bc7b3338d07**
- target `rid`: **d4cd1983020c4c5799012e909d7a31b4**; `lifecycle_key`:
  **d4cd1983020c4c5799012e909d7a31b4:10**

## 8. Artifacts and sha256

Bundle dir:
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/R114-bundle/`

| file | sha256 |
|---|---|
| `raw.log` (235061-line frozen server-log slice, lines 821468–1056600; all `[HAE]`/`[P3]` intact) | `9df12929d737bbb2e8cb129e115775fe3478f51608b4d116b7e6f57b183dcb8c` |
| `probe.log` (1933-line durable slice beyond byte 7692189) | `9f41d92fd0493119a76c29f82bfac0e7993d562da2f35041ea3b256698b0f961` |
| `manifest.json` (`p0b.raw-bundle.v3`) | `6b70d92427b67a86321df9466286a7c938fe8fa4734e8290b84375808eab0bf1` |
| `requests.jsonl` (complete HTTP transcript incl. both waiters) | `329cfd7627c9a39bc862fee411840fb9953804e7e8cb53731d83adcc284f29c1` |
| `reducer.out.json` (full R111 output) | `c4c5512ec91d1c4c6231d9b30a141e9984c073760e1fb532d4619115b7ef05b9` |
| `reducer.err.txt` (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `reducer.exit.txt` (`EXIT=0`) | `418a5c17f33c70e99b0cc0a07fce69191489cfedc94164bfa903785777c5bd4b` |
| `baseline-offsets.txt` | `861a2c3f63c4bb881c161854041c294e486e8d05ad718fa8f28ba947b21485aa` |

Manifest `source_files` (unchanged from R113): `scheduler.py`
`daf32da4…9dd1d`, `unified_radix_cache.py` `5d3db152…c375b`,
`telemetry_context.py` `d55b057c…f948`, `hicache_restore.py`
`1cc9d2b8…b3604`, `hybrid_cache_controller.py` `a71acb88…d669`.

## 9. Open issues (honest limitations, none blocking this verdict)

1. **Barrier writability is first-token sensitive.** Promotion requires a
   contiguous persisted parent chain; any shared, never-persisted prefix node
   (e.g. `"[SESSION-"`) defers promotion even though the write ACK is complete.
   The winning recipe is a unique first token (rare Unicode) so the write starts
   as a fresh root child. This is a producer/telemetry behavior worth recording,
   not a test defect.
2. **Barrier and park use different prompts within the same generation.** The
   gen-10 barrier belongs to the small clean seed write (`build_rid`
   `1e3dbabc…`, 2048/1472 tokens) while the parked target is the later replay
   (`rid d4cd1983…`, 27008 tokens) in the same open session. The frozen oracle
   joins predicate 4 on `session_generation` only, so this is admissible; a
   stricter oracle additionally requiring the barrier and park to share
   `build_rid`/`node_id` would fail and should be a conscious freeze decision.
3. **No simultaneous two-waiter overlap.** Predecessor waiter-A (`…wait:10`)
   parked at `raw.log:53259` and was released (`TIMEOUT`) at `raw.log:184245`
   before the target parked at `raw.log:71263`; the frozen oracle's FIFO
   predecessor join (released-waiter terminal history) is satisfied, but both
   requests were not simultaneously parked.
4. **Predecessor was a partial hit:** waiter-A park `positive_hit_tokens=8000 <
   requested_primary_tokens=42864`. Predicates 5/7 do not require a full
   predecessor hit; predicate 4's full-hit requirement is met by the target.
5. Clean-probe-1 (`r114-s`) is preserved as a real failed-barrier observation in
   the transcript and `raw.log`; it is not part of the target chain.

## 10. Budget accounting

- HTTP: 18 total (14 POST + 4 GET), limit 200.
- Wall clock: ~8 min from baseline to freeze, limit 60 min.
- Server left running and healthy (`GET /health` → 200); no server/GPU action.

## 11. CORRECTION ADDENDUM (orchestrator, 2026-09-11)

Supersedes the tester's final-message claim of "barrier and park use different
`build_rid`". Source-verified: they are the **SAME** build identity.

- Both the gen-10 `durability_barrier` records (nodes 315/316) and the accepted
  target `restore_hybrid_finalize` (`raw.log:1056511`) carry
  `build_rid = 1e3dbabc421748acbd27fae9990fff57`
  (`.../R114-bundle/probe.log:63,71`; finalize `trace_context.build_rid`).
- The real, correctly-stated limitation is **coverage**, not identity: the barrier
  witnesses only the session's first small write (`fill_len=3528`; barrier
  `kv_completed_tokens` 2048/1472), whereas the target restore requires 27008
  tokens. Under the user's ruling A′, this is recorded as
  **`durability_barrier`/`storage_persisted` telemetry incompleteness**, not a
  product durability failure: the target prefix's durability is instead proven by
  the L3 storage layer (`pc_storage_query` 27008 hits with the identical key set
  absent at build time, `pc_get_v2` 27008 pages, `pc_l3_host` 27008, on-disk
  objects) and judged by R116.
- This addendum is appended; the original report body is preserved unchanged. The
  original (pre-correction) file sha256 was
  `cc411a3c7484dbda6dc03630c55a90b7337842c83833be6bb4f082150496f3d6`; the
  post-correction sha256 is recorded in the ledger (not self-referenced here).
  Nothing else in the report changes; §9.2's first sentence is superseded by this
  section.
