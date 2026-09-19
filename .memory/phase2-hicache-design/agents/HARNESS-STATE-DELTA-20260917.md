# HARNESS-STATE-DELTA-20260917 — read-only state delta of the Gate-A/F1 harness correction round

- terminal state: **DONE**
- task_id: `HARNESS-STATE-DELTA-20260917`
- role: executor — READ-ONLY diagnosis + CPU-only test execution
- repo: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt` (branch `3090-24g-opt`, HEAD `910e5a01c05da1311925bc5fd174f9a0ec04b3a3`)
- authority: read-only inspection + CPU tests only. No edits (except this artifact), no git mutations, no GPU, no server.
- question answered: is the working tree a COHERENT-COMPILABLE state or a BROKEN intermediate state?

## Scope

Read-only. Inspected the six harness files under `3090-dev/gates/production/`, the
implementer artifact `.memory/phase2-hicache-design/agents/GATEA-CLOSURES-IMPLEMENT-20260917.md`,
and cross-checked reviewer conditions F1..F6. Ran only `python3 -m py_compile` and
`python3 -m unittest test_gate_helpers` on CPU (`CUDA_VISIBLE_DEVICES=""`), with
`PYTHONDONTWRITEBYTECODE=1` and `PYTHONPYCACHEPREFIX=/tmp/opencode/pycache` so no bytecode
was written into the repo. `git status` was re-checked after the run and is identical to
the pre-run snapshot.

## Result

**The working tree is a BROKEN intermediate state: it compiles (rc 0) but fails its own
test suite (1 failure / 60 tests).** The correction round is half-applied: `gate_common.py`
(and the callers) removed the F2 node-id ordering bound, but `test_gate_helpers.py` still
asserts the removed behavior (`test_root_above_bound_is_foreign`), so the tests now
contradict the code. F1, F2, F3, F6 are PRESENT; F4 and F5 are ABSENT.

## Evidence

### 1. `git -C <repo> status --porcelain` (verbatim)

```
 M .memory/phase2-hicache-design/ledger.md
 M 3090-dev/gates/production/README.md
 M 3090-dev/gates/production/f2_restart_recovery.py
 M 3090-dev/gates/production/gate_a_content_integrity.py
 M 3090-dev/gates/production/gate_a_f1_cold_l1.py
 M 3090-dev/gates/production/gate_common.py
 M 3090-dev/gates/production/test_gate_helpers.py
 M python/sglang/srt/utils/hf_transformers/gguf_native.py
?? .memory/phase2-hicache-design/HANDOFF-20260917-PRODUCTION-PRIORITY.md
?? .memory/phase2-hicache-design/agents/
?? .memory/phase2-hicache-design/work/EPOCH-RESUME-20260917-R2.md
?? .memory/phase2-hicache-design/work/GGUF-ARTIFACT-PROVENANCE-20260917.md
?? .memory/phase2-hicache-design/work/PROD-TAKEOVER-AUTHORITY-AND-GATE-A-20260917.md
?? .memory/protocol-subagent-smoke-20260917/
?? 3090-dev/gates/gguf-sampled-smoke/
?? test/registered/unit/utils/test_gguf_native_tokenizer_ids.py
```

### 2. sha256 current vs HEAD (all six under `3090-dev/gates/production/`)

| file | current sha256 | HEAD sha256 (`git show HEAD:<path> \| sha256sum`) | current/HEAD differ? |
|---|---|---|---|
| `gate_common.py` | `d9caae4df4052c9bc3467fb77b6a012e3dba9f2582c973928f6e7ac78a118f3d` | `d93e66b9bc7e29267482ef6267e8059d41b991fbcf8f2d50af40438abe97749b` | yes |
| `gate_a_content_integrity.py` | `60ab200c3db367339e4630f1dc7f530e42acffe39a0989ce3e26de5e7cd0353e` | `4794059114f377b47af1a142c3a6ad2df0dbdd8032990e38ad759f5a4891f921` | yes |
| `gate_a_f1_cold_l1.py` | `b19009e76616509a4299672971212aca2d5f6629d6cc4cf15a9320f3c0459313` | `d596c7761f0bf5e4b9b365ca3542f976f47fb5b76b01554c6c4c01531ee962fb` | yes |
| `f2_restart_recovery.py` | `30d1fcd990f65b39e9d818b7347ff39d9c26febaed35da3115f316e68a55bf9a` | `2f8a004d5aafd3422d11a6e78e33122552565c3b308c8f5d1647a26b943bf063` | yes |
| `test_gate_helpers.py` | `30472c11127006788a9c248f46d2ed36803e9224fd4f548be086a9f0e9f217fe` | `6a7965735dfe4ccc950f8815571c280fd3e2c180ea0a92672dd251372f162bf3` | yes |
| `README.md` | `0687fa5d949238683df433ea859039b9a56c23e2f302865eb2647200773d09fe` | `020f04c529e575e54af7ddfc4238218c2189fa0ddd4bb3cfc20312334c87aa1e` | yes |

Current line counts: gate_common 1597, gate_a_content_integrity 819, gate_a_f1_cold_l1 1089,
f2_restart_recovery 691, test_gate_helpers 740, README 382.

`git diff --stat` vs HEAD for the six: `1006 insertions(+), 74 deletions(-)`.

**Staleness cross-check against the implementer artifact's declared "after" hashes**
(artifact `.memory/phase2-hicache-design/agents/GATEA-CLOSURES-IMPLEMENT-20260917.md:58-68`):

| file | artifact "after" sha | current sha | matches artifact? |
|---|---|---|---|
| `gate_common.py` | `e57e09806cbc92fa0a9c51ff30863022379ff8aa9147d6ddaa0c509e526ca542` | `d9caae4d…` | NO (changed again in correction round) |
| `gate_a_content_integrity.py` | `fa7121d8244b63399556d5dac249bcd5235bb63ffbf3f11f2a8865070e4d48d8` | `60ab200c…` | NO |
| `gate_a_f1_cold_l1.py` | `8d95450e2e0ceffb556209a0cb09970a6826aa3d80196d2d433d5c4279c49cb7` | `b19009e7…` | NO |
| `f2_restart_recovery.py` | `4c51277db75f89d8ae6ae5487521c2ce24f42ffd425d34eeb8940fe2505c6017` | `30d1fcd9…` | NO |
| `test_gate_helpers.py` | `30472c11127006788a9c248f46d2ed36803e9224fd4f548be086a9f0e9f217fe` | `30472c11…` | YES (untouched this round) |
| `README.md` | `0687fa5d949238683df433ea859039b9a56c23e2f302865eb2647200773d09fe` | `0687fa5d…` | YES (untouched this round) |

The artifact still describes the PRE-correction code (e.g. line 36-37 says the node-id ordering
bound is used; current code removed it). The artifact is confirmed STALE, as stated in the task.

### 3. F1..F6 status in the current bytes

| condition | status | evidence |
|---|---|---|
| F1 drop must not inherit 0.99 tolerance; only `foreign` on positive no-durable-loss proof; one-page loss INVALID | **PRESENT** | `gate_common.py:914-956` `durable_delta_status` (monotone set proxies; `nw_n < bl_n -> "lost"` at 938-939, so a 1-page loss is `lost`); `gate_common.py:959-973` `combine_delta_status` (any `lost` -> `False`; unknown -> `None`); `gate_common.py:998-1006` `DropScope.classify` returns FOREIGN only when `refs_intact is True`; `gate_common.py:1034-1060` `drop_scope_ok` ok only when every row explicitly FOREIGN. `--min-index-fraction` (0.99) is still used only for index-precondition checks (`f2:69,317`; `gate_a_content_integrity.py:77,569,574`; `gate_a_f1_cold_l1.py:95,318,620`), **not** in the drop verdict: `gate_a_content_integrity.py:621-628` and `gate_a_f1_cold_l1.py:658-663` derive `refs_intact` via `combine_delta_status([durable_delta_status(...)])`. |
| F2 remove/guard `root_id > max_target_node_id => foreign` + "parent allocated before children" comment | **PRESENT** | Bound removed: `gate_common.py:989-991` "``root_id`` is accepted for recording only. The node-id ordering bound was removed because its invariant is false … it must not steer a drop to ``foreign``." `DropScope.classify` (`gate_common.py:1001-1006`) ignores `root_id` (`# noqa: ARG002 (record-only)`). The false invariant is documented (not asserted) at `gate_common.py:819-828`; `target_node_evidence` is report-only (`gate_common.py:855-896`). Call sites explicitly say the bound is not used: `gate_a_f1_cold_l1.py:657`, `gate_a_content_integrity.py:619-620,660`, `f2_restart_recovery.py:337-339`. No residual `root_id > max` comparison in code (only comment/doc references). |
| F3 F1 cold window must not use pre-request `cold_pre_target_still_indexed` as `refs_intact` | **PRESENT** | `gate_a_f1_cold_l1.py:550-566`: after the measured cold request a NEW `cold_post` membership snapshot is taken and `_cold_window_drop_scope(cold_events, target_evidence, cold_pre_mem, cold_post_mem)` is called; comment 550-553: "The pre-request `cold_pre_target_still_indexed` verdict is STALE relative to cold-window drops and must never be reused as `refs_intact`." Helper `gate_a_f1_cold_l1.py:794-807` computes `refs_intact = gc.combine_delta_status([gc.durable_delta_status(pre_mem, post_mem)])` and states "The pre-request verdict alone is never used as `refs_intact`." The pre-request check `cold_pre_target_still_indexed` (523-531) remains only as a precondition, not as the drop verdict. |
| F4 README must label F1 reserve preflight CONSERVATIVE (false-INVALID possible, never false-PASS) | **ABSENT** | `README.md:235-258` ("Relocation-destination reserve (owner closure 2)") describes the preflight and that it returns INVALID before the measured request, but never uses "conservative"/"false-INVALID"/"false-PASS". `grep -in "conserv" README.md` -> no output; `grep -in "false" README.md` -> only line 265 (`flush_cache_confirmed = false`, unrelated). README sha is unchanged from the artifact's after-hash, i.e. untouched by the correction round. (The conservative statement exists only in the artifact at lines 176-179, not the README.) |
| F5 implementer artifact r2 evidence block corrected + CONDITIONS-ADDRESSED / SENSITIVITY | **ABSENT** | Artifact line count 193; section headers are only Scope/Result/Evidence/Defects-blockers/Remaining claims/Terminal state (artifact lines 12,23,56,159,163,191). `grep -n "CONDITIONS-ADDRESSED"` -> no match; `grep -n "SENSITIVITY"` -> no match. The r2 block at artifact lines 134-149 is still the old one and is internally contradictory: line 141 shows `R2 scope refs_intact=None  {…"ok": false, "unknown_roots": [83,…]}`, while line 146 claims "the offline membership verdict is `refs_intact=False`". No corrected `refs_intact=False` r2 case was added. |
| F6 empty-membership `all()` must not default True (fail-open); L3 Gate A per-target `min_present` | **PRESENT** | Empty guard: `gate_a_content_integrity.py:509-521` `_targets_in_index_ok` returns `False` when `not membership` (515-516) with docstring "empty membership is NOT ok … must never default to ``True`` (fail-open)". Per-target threshold: `gate_a_content_integrity.py:568-575` computes `min_present_by_target = {name: ceil(min_index_fraction*(len(ids)-1)) for …}` (comment: "a global max would be a false-INVALID for the shorter prompt") and `_targets_in_index_ok` compares `min_present_by_target.get(name, m.get("min_present_required") or default_min)` per target (517-521); called at `gate_a_content_integrity.py:668`. The persistence loop also invalidates when membership is empty (`gate_a_content_integrity.py:602-606`). |

Note on F1's "positive proof" semantics: the current `foreign` path requires
`refs_intact is True`, which `durable_delta_status` can only return after passing every
monotone no-decrease check with a usable positive baseline (`bl_n > 0`), otherwise `unknown`
-> INVALID. This matches F1's "positive proof no graded-target durable ref/node was removed".

### 4. Coherence check (CPU-only)

`py_compile` (all six `.py` files; bytecode redirected out of the repo):

```
$ python3 --version
Python 3.12.3
$ CUDA_VISIBLE_DEVICES="" PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/opencode/pycache \
    python3 -m py_compile gate_common.py gate_a_content_integrity.py gate_a_f1_cold_l1.py \
    f2_restart_recovery.py test_gate_helpers.py
PY_COMPILE_RC=0
```

`unittest` raw output (tail; full run in the transcript):

```
...
======================================================================
FAIL: test_root_above_bound_is_foreign (test_gate_helpers.TestDropScopePredicate.test_root_above_bound_is_foreign)
----------------------------------------------------------------------
Traceback (most recent call last):
  File ".../3090-dev/gates/production/test_gate_helpers.py", line 663, in test_root_above_bound_is_foreign
    self.assertEqual(scoped[0]["scope"], gc.DropScope.FOREIGN)
AssertionError: 'unknown' != 'foreign'
- unknown
+ foreign


----------------------------------------------------------------------
Ran 60 tests in 2.103s

FAILED (failures=1)
$ echo $?
1
```

Exact count: **60 tests, 1 failure** (`test_root_above_bound_is_foreign`), rc=1.

Root cause of the failure (decisive): `test_gate_helpers.py:659-664` still asserts the
PRE-correction node-id bound:

```
659:    def test_root_above_bound_is_foreign(self):
660:        ev = gc.parse_storage_events([self.UNIFIED + "\n"])  # root 83
661:        scoped = gc.scope_drop_events(
662:            ev, {"node_ids": [18, 51], "max_node_id": 51}, refs_intact=None)
663:        self.assertEqual(scoped[0]["scope"], gc.DropScope.FOREIGN)
664:        self.assertTrue(gc.drop_scope_ok(scoped)["ok"])
```

but current `gate_common.DropScope.classify` (1001-1006) returns `UNKNOWN` for
`refs_intact=None`, as F2 requires. So the test file was NOT updated when the bound was
removed in this correction round. (`test_root_above_bound_is_foreign` is absent at HEAD;
it was added in the implementation round, per `git show HEAD:... | grep` -> "(not at HEAD)".)

### 5. Truncation / half-written check

- No conflict markers: `grep -rn "<<<<<<<\|>>>>>>>\|=======" *.py` -> no output.
- All five `.py` files parse (`py_compile` rc 0), so no syntax error / unexpected EOF.
- File tails look complete: `gate_a_content_integrity.py`, `gate_a_f1_cold_l1.py`,
  `f2_restart_recovery.py` each end with the expected
  `if __name__ == "__main__": raise SystemExit(main())`; `test_gate_helpers.py` ends with
  `unittest.main(verbosity=2)`; `gate_common.py` ends with a complete `return f"ERR {exc!r}"`.
- No hunk ending mid-function detected.
- The only "incompleteness" is semantic, not textual: `test_gate_helpers.py` still encodes
  the removed F2 rule (see §4), and `README.md` lacks F4 (see §3).

## Defects / blockers

1. **D1 (blocking, tree inconsistency):** `test_gate_helpers.py:659-664` asserts the removed
   F2 node-id bound behavior; `test_root_above_bound_is_foreign` FAILS (`'unknown' != 'foreign'`).
   The suite is red: `Ran 60 tests … FAILED (failures=1)`. The tree is a half-applied
   correction round.
2. **D2 (failing condition):** F4 ABSENT — `README.md:235-258` does not label the F1 reserve
   preflight as conservative / "false-INVALID possible, never false-PASS".
3. **D3 (failing condition):** F5 ABSENT — the implementer artifact
   `GATEA-CLOSURES-IMPLEMENT-20260917.md` has no `CONDITIONS-ADDRESSED` section, no
   `SENSITIVITY` case, and its r2 evidence block (lines 134-149) is uncorrected and
   self-contradictory (`refs_intact=None` at line 141 vs `refs_intact=False` at line 146).
4. **D4 (stale artifact):** the artifact's declared "after" sha256 for the four code files no
   longer matches the working tree (see §2 table); the artifact still documents the
   pre-correction node-id-bound rule (lines 36-37, 173-175).

## Remaining claims / exclusions

- No GPU, no server, no port binding, no live gate run, no product code executed. The test
  run is CPU-only unit tests.
- No git mutation performed (no add/commit/checkout/stash/reset/fetch). `git status`,
  `git show`, and `git diff --stat` were read-only.
- No repo file was created or modified by this task except this artifact; bytecode was
  redirected via `PYTHONPYCACHEPREFIX=/tmp/opencode/pycache` and `PYTHONDONTWRITEBYTECODE=1`,
  and `git status --porcelain` after the run is byte-identical to the pre-run snapshot.
- F1..F6 were assessed from the current bytes only; this report does not re-adjudicate the
  reviewer's design reasoning, only presence/absence and coherence.
- The pre-existing modification `python/sglang/srt/utils/hf_transformers/gguf_native.py` and
  the untracked GGUF/protocol-smoke paths are outside this task's six-file scope and were not
  inspected.
- Follow-on (not performed, requires orchestrator dispatch): update
  `test_root_above_bound_is_foreign` to the removed-bound expectation, add the F4 README
  conservative label, and add the F5 artifact `CONDITIONS-ADDRESSED`/r2 correction.

## Terminal state

DONE
