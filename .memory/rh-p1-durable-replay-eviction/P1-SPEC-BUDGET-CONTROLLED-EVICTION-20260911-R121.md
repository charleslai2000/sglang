# P1 SPEC_BUDGET controlled-eviction closure — R121 evidence report

- task_id: `P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R121`
- invocation: `ses-p1-controlled-eviction-r121-20260911`
- role: `tester`
- epoch: `2026-09-11`
- status: **not_verified** (verification executed to completion; P1 does NOT close)

Frozen contract verified before starting:
`work/R121-bundle/P1-R121-CONTROLLED-EVICTION-CONTRACT.md` sha256
`2ac86b5a54264fad46d049e2c32e3cc37c125f8c778a38dfb14e840a37be3b3b` (matches).
Server read-only throughout: PID 48746 (`launch_server`), scheduler 48806,
`http://127.0.0.1:30000`, health 200 before/during/after. Repo read-only HEAD
`4f41f5bab562b99562f30c67540eb05344d13637` (source hashes unchanged vs R119/R120).
No product edits, no instrumentation, no synthetic events, no child agents, no
server start/stop/restart/kill/reconfigure.

## Result

The controlled-eviction preprocessing worked: attempt 3 (`NONCE=p3`,
replay `[F1,F2,T]`) achieved **full durability**, **full device+host eviction**
(`device_hit=0 host_hit=0`), and — for the first time — the **SPEC_BUDGET park**
and the **F1 exactly-once release → T wake** legs. The chain still does **not**
close: at T's stage the host pool could not allocate `D_req=27328`, T's restore
was revoked twice with `alloc_failed`, and T ended in `restore_recompute
cause=timeout`. The top-level hard precondition **HOST_HEADROOM_SUFFICIENT is
unmet**, so C4 and C5 FAIL and the `l2_to_l1_restore_generation` leg is missing.

## Workload and measurement window

All requests `POST /v1/completions`, `model=/mnt/data/models/qwen35-gptq`,
`temperature=0`, `max_tokens=1`, prompt as `input_ids`, top-level `session_id`.
Builds (distinct sessions, unique rare-Unicode first token):

| tag | session | prompt_tokens | rid | HTTP | elapsed_s |
|---|---|---|---|---|---|
| build-F1 | `r121-s-F1-p3` | 42959 | `r121-p3-build-F1` | 200 | 17.509 |
| build-F2 | `r121-s-F2-p3` | 43002 | `r121-p3-build-F2` | 200 | 21.090 |
| build-T | `r121-s-T-p3` | 27340 | `r121-p3-build-T` | 200 | 18.443 |

Controlled pressure (preprocessing only, `r121-p3-q1..q5`, ~43k each, all HTTP
200) drove F1/T out of GPU L1; fully drained before the window (last pressure
admission wall 00:28:40; window start wall 00:32:50; zero pressure events in
window). Four fallback triggers (`r121-p3-trig-1..4`) opened the ready-horizon
epochs. Measurement batch replay `[r121-p3-R-F1, r121-p3-R-F2, r121-p3-R-T]`
(session `r121-s-R-p3`, gen 60) HTTP 200 in 83.492 s.
Window: raw line 103819 / server line 2416575 / wall 2026-09-12 00:32:50.

## Per-condition verdicts (C1..C5 and the hard precondition)

| # | condition | verdict | decisive refs |
|---|---|---|---|
| P | `FULL_DURABLE` | **PASS** | `probe.log:3264` `kv_hit_pages=storage_hit_count=27328`, mamba sidecar 27328; build barriers F1 21 / F2 21 / T 14 |
| P | `NOT_DEVICE_RESIDENT` | **PASS** | `raw.log:103819` T `device_hit_tokens=0 host_hit_tokens=0 fill_len=27340`; F1 same |
| P | `HOST_HEADROOM_SUFFICIENT` | **FAIL** | `raw.log:103892` free+evict=8162 < F1 42944; `raw.log:125841` 6178 < T 27328; `raw.log:224763` 24670 < 27328 |
| C1 | T full durable L3 coverage | **PASS** (identity-join caveat) | `probe.log:3264`; `D_req=27328`; external tail 11 (`query_suffix_len=27339`) |
| C2 | T park uniquely SPEC_BUDGET | **PASS** | `raw.log:103830` `decision=exclude reason=negative_cache`, `spec_used=42958 > 39321`, `negative_cache_blocked=True`, `staging_eligible=True restore_potential=True`, `restore_state_before=NONE` |
| C3 | release→wake causality (epoch +1) | **PASS** | `raw.log:103821` F1 issue 42958; `raw.log:103888` `prefetch_revoke alloc_failed`; epoch 96→97; `raw.log:103901` T `decision=issue spec_budget_release_epoch=97` |
| C4 | corrected full restore gate | **FAIL** | T revoked `alloc_failed` `raw.log:125839`/`raw.log:224763`; `raw.log:270213` `restore_recompute cause=timeout`; no `restore_success`/`restore_hybrid_finalize` |
| C5 | host headroom proven sufficient | **FAIL** | window start 8162, T stage 6178, after reclaim 24670, all < requirement; effective margin −2658 |

`missing_legs`: `l2_to_l1_restore_generation` (T). Full field values:
`R121-bundle/condition-evidence.md`, `R121-bundle/chain.json`.

## Exact unmet precondition and decisive evidence

**Primary unmet condition: top-level `HOST_HEADROOM_SUFFICIENT` (⇒ C5, C4).**
- Host KV pool = 131073 tokens. `host_allocable := free_units.kv + evictable_units.kv`
  (`host_alloc.v1`); `full_locked` is not published by available telemetry — the
  verdict is invariant to it because free+evictable alone is already short.
- Window start F1 host wait `raw.log:103892`: `free=162`, `evictable=8000`
  → **8162** < F1_required **42944**.
- T stage `raw.log:125841`: `free=98`, `evictable=6080` → **6178** < T_required
  **27328**. First retry `raw.log:125839` `revoked_alloc_failed reclaimed=0`.
- Second T retry `raw.log:224763`: `reclaimed=22526`, `free_after=24670`,
  `evictable_after=0` → **24670 < 27328**; disposition `revoked:alloc_failed`.
- Terminal T outcome `raw.log:270213` (server 2582969)
  `restore_recompute cause=timeout final_storage_survivability=host`.

## Chain achieved and why it stops

- Achieved: `full_durable T` → `SPEC_BUDGET park` (T, unique cause) →
  `F1 exactly-once release (spec_budget_release_epoch 96→97)` →
  `T wake/reissue at epoch 97` (`issue_origin=READY_HORIZON`).
- Not achieved: `full L3→L2→L1 restore` and `generation`. T's restore was
  issued at 97, then host allocation was revoked twice (`alloc_failed`), which
  truncated the restore below `D_req=27328` and forced a timeout recompute of the
  durable prefix. Per contract §FAIL this is classified as a **HOST_HEADROOM
  precondition failure**, not a durable-coverage shortfall.
- C1 identity-join caveat: park/query use replay identity `r121-p3-R-T`
  (session `r121-s-R-p3` gen 60) while the durable producer is build session
  `r121-s-T-p3` (`build_rid=r121-p3-build-T`). No T finalize exists (restore
  failed), so the `build_rid` consistency triple across park/query/finalize
  cannot be shown; coverage (`kv_hit_pages=storage_hit_count=27328`, mamba 27328)
  is fully shown.

## Procedure note (harness gap, not a product defect)

The contract requires the three-way precondition to be evidenced and dismissed
(*fail-fast*) **before** the window opens. The driver keyed on its `wait_idle`
request-drain signal and opened the window without independently proving host
pool headroom; the host pool was in fact far below requirement. This is a
harness/test gap: the drain check measured request-queue idleness, not host
allocability. The verdict is unchanged (`NOT_VERIFIED`), and the C2/C3 evidence
is retained as the positive result of the attempt.

## Artifacts (`work/R121-bundle/`) and sha256

| file | sha256 |
|---|---|
| `raw.log` (server slice from line 2312756) | `2bdca1c2e605ec3463bcdac9501a6e8b52a836a5fe99aac3b908db880b80cca9` |
| `probe.log` (probe slice from line 25948) | `424a1ec95cf9c2cee94d075fd0dbb59ddf7b7d4a083403e2b45225fea1018630` |
| `requests.jsonl` | `f886dfad319738481f05388da8cfada382649448af8701b7bbc7cf9577316b15` |
| `state.jsonl` | `77fb536f8770e2e59c575aabe977566e6f13cf5784678f5b9d42a5f092fb817a` |
| `chain.json` | `1f9dcef8d090d0b8a12aa388d935067c80ed5770eea0ab4249c0496e22325a8a` |
| `condition-evidence.md` | `ec0258851c25b390d9798ea66bf6b9554d47042978441a74d62b192ce26df1cd` |
| `manifest.json` (`p0b.raw-bundle.v3`) | `08ae228b2ea3385a3b1c49e921bd2ac155570cbf29f2422314f4fbc76f5607b6` |
| `driver121.py` | `9ae5320efe699dfc36d91aa968d150d625e8968479603c96e956635e9947cc6d` |
| `baseline-offsets-attempt2.txt` | `68abead6c34466ed9a4b9b18569c6be4d31385c271e018f72b7b4b11951bce3a` |

Baseline attempt 2: server log start line `2312756` (bytes `287273682`), probe
start byte `40437937` (line `25948`); server PID 48746 / scheduler 48806; health
200. Attempt 1 (`[F1,T]`, no park) preserved under `attempt1-2subreq/`.

## Budget

- HTTP: 13 POST (3 builds + 5 pressure + 4 triggers + 1 batch) + health GETs ≤ 20
  (limit 200).
- Wall clock for attempt 3: build+pressure+drain+replay ≈ 18 min (limit 60).
- Server left running and healthy; no server/GPU action.

## Followups (for the orchestrator; not done here)

1. P1 remains NOT_VERIFIED on `HOST_HEADROOM_SUFFICIENT`. Achieving the window
   needs a host pool with genuine free+evictable ≥ `F1_required + T_required`
   (≥ 70272 at these sizes) **at window start**, or smaller F1/T — i.e. a fresh
   server / quiet host pool, or a profile whose working set can actually be
   reclaimed. The controlled-eviction recipe freed the device but not the host.
2. The harness drain gate should be strengthened to check host
   `free_units+evictable_units` (and `full_locked` if published) rather than
   request-queue idleness, so the contract's fail-fast precondition is enforced
   before a window is opened.
3. The C1 `build_rid` triple-join across park/query/finalize could only close on
   a run where T restore reaches `restore_success`; record it as a
   not-yet-joinable identity here.
