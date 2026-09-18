# GATEA-CLOSURES-REREVIEW-20260917 — R3b focused re-review of D1(b)/D2/L4/L5 (current bytes)

- terminal state: **DONE**
- verdict: **APPROVE-WITH-CONDITIONS** (no code condition remains; sole condition is a
  documentation/handoff-evidence condition, item A1 below)
- role: reviewer-deep (independent, adversarial; read-only)
- task_id: `GATEA-CLOSURES-REREVIEW-20260917` (continuation of the same role; re-adjudication round R4)
- repo: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt` (branch `3090-24g-opt`, HEAD `910e5a01c0`)
- reviewed: the seven `3090-dev/gates/production/` files at the CURRENT bytes; implementer artifact
  `.memory/phase2-hicache-design/agents/GATEA-CLOSURES-IMPLEMENT-20260917.md` (now 88 lines, overwritten).
- constraints honored: no edit to any reviewed file, no git mutation, no GPU, no server/port,
  no `/opt/**`, `/data/**`, `/var/log/**` write. The only repo-tree writes are this artifact and
  gitignored interpreter bytecode (`__pycache__/`, disclosed in §7). Scratch work in `/tmp/opencode`.

## Task

Re-adjudicate my prior conditions D1, D2, L4, L5 against the current bytes; independently verify the
correction round's six claims; decide the classification of the overwritten/garbled implementer
artifact; derive the change surface read-only; confirm no gate was weakened (every semantic delta
strictly conservative); confirm the `--min-index-fraction 0.99` stage check is unchanged and record
the whole-gate ~1% residual as a known escalation. Classify every residual as false-INVALID
(tolerable if labelled) or false-PASS (disqualifying).

## Scope

- In scope: `3090-dev/gates/production/{gate_common.py, gate_a_content_integrity.py,
  gate_a_f1_cold_l1.py, f2_restart_recovery.py, test_gate_helpers.py, README.md, wal_forensics.py}`
  and the implementer artifact.
- Read-only replay evidence from the earlier rounds (r2 membership `n_present=52672`,
  `refs_intact=False`) is reused only as history; no `/data` replay and no live/GPU run was performed
  or authorized. Every code conclusion below is recomputed from the current bytes.

## Result

**All four conditions are CLEARED on the current bytes by direct code inspection plus independent
execution: D1(b), D2, L4, L5.** The correction round is real, confined to the claimed files, and
strictly conservative in every semantic delta. I could find **no false-PASS** in the drop
classification: the only production paths to `foreign` now require a no-decrease delta measured
against a *complete, drop-free* baseline and confirmed by a re-snapshot, and the strict default is
the only production-reachable mode. The exact partial-baseline-vs-growth bypass from my prior report
now yields `unknown -> INVALID` end to end.

- Hashes: all seven current `sha256` values equal the artifact's declared AFTER values exactly
  (including `f2` and `wal_forensics` unchanged), and its declared BEFORE values equal my prior
  report's R2-final hashes — the round changed exactly the claimed five files.
- Suite: 74/74 OK (rc=0), twice, including the *production-env interpreter*
  (`/opt/sglang/local-prod-v1.2.1-candidate/env/bin/python3` → `/usr/bin/python3.12`); `py_compile`
  rc=0. This independently covers the interpreter run the implementer artifact omitted.
- D1(b): `baseline_is_complete` + `require_complete_baseline=True` default + `delta_status_with_rechecks`
  close the demonstrated bypass; AST call-graph audit proves the strict path is the **only**
  production path that can reach `refs_intact=True`, and `require_complete_baseline=False` exists
  only in a test that demonstrates the old permissive behavior.
- D2: README now documents the complete-baseline delta semantics and states the node-id ordering is
  NOT an attribution mechanism; sweep/F2 any-drop behavior is labelled conservative **false-INVALID**.
- L4/L5: both fail-closed changes are real and test-covered against the shipped functions
  (reproduced by me independently).
- Change surface: only the six harness files (five written 21:25:31–21:27:29 by R3b; `f2` written
  20:36 by R2 and unchanged since) plus the artifact (21:37) are attributable to this work. The
  `gguf_native.py`/GGUF tokenizer files (16:58, separate workstream) and all `.memory/**`
  (bookkeeping; `ledger.md` was concurrently written by another agent at 21:40:58) are unrelated.
- Residuals (none disqualifying): one *latent, non-reachable* robustness gap (present-but-unparseable
  proxy values are silently skipped), the known/escalated ≤1% stage tolerance, and unmodified
  observation-window races. Details in Defects-blockers.

## Evidence

### 1. Hashes / line counts / diff confinement — PROVEN (claim verified)

`sha256sum` of the current working tree (recomputed this round):

```
8321becd19ad33bb48c00c11a091aa2b772748e6565a9dde62049ebc9ac40273  gate_common.py
abebbe4c231f48134aac52757c947720751c0703a37958d1bc5b50ca8ee193c6  gate_a_content_integrity.py
49d904052958d368c95a096c3758f3bdc253d618fd9d7d0c58cb97d9a6124c41  gate_a_f1_cold_l1.py
30d1fcd990f65b39e9d818b7347ff39d9c26febaed35da3115f316e68a55bf9a  f2_restart_recovery.py   (unchanged)
e2d50f6ac39704c1fc0610574daffdcd3181ad91a934200307b4a8d843225328  test_gate_helpers.py
65e19c47906776957de06f4d36a45718efc0bb18a968d1f19d92a84027273eb9  README.md
f8ed297f10df81105747b2838ea412b94d9b6f5d54a9de69562bca608730f8bb  wal_forensics.py        (unchanged)
```

Every value equals the implementer artifact's declared AFTER hash exactly, for all seven files.
Line counts 1679/844/1121/691/1016/433/517 also match the artifact. The artifact's declared BEFORE
hashes (`d9caae4d…`, `60ab200c…`, `b19009e7…`, `30d1fcd9…`, `c9fba00a…`, `01c20331…`, `f8ed297f…`)
equal my prior report's R2-final hashes, so the round changed precisely the five files it claims and
left `f2`/`wal_forensics` byte-identical. ⇒ no mismatch finding.

`git status --porcelain` is stable before/after all my runs (no new path); `git diff --stat` for the
harness touches only the six files. See §6.

### 2. CPU suite — PROVEN (claim verified, twice)

```
$ CUDA_VISIBLE_DEVICES="" PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile \
    gate_common.py gate_a_content_integrity.py gate_a_f1_cold_l1.py f2_restart_recovery.py \
    test_gate_helpers.py wal_forensics.py
PY_COMPILE_RC=0

$ CUDA_VISIBLE_DEVICES="" PYTHONDONTWRITEBYTECODE=1 python3 -m unittest test_gate_helpers
Ran 74 tests in 2.123s
OK
UNITTEST_RC=0

$ CUDA_VISIBLE_DEVICES="" PYTHONDONTWRITEBYTECODE=1 \
  /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python3 -m unittest test_gate_helpers
Ran 74 tests in 2.119s
OK
FROZEN_ENV_RC=0        # env/bin/python3 -> /usr/bin/python3.12 (same 3.12.3)
```

This supplies the "frozen-tree-interpreter test run" the implementer artifact omitted: the
production env interpreter resolves to the system 3.12.3 and the suite is green under it.

### 3. D1(b) adversarial re-attack — the prior bypass is CLOSED; no new bypass found

Script `/tmp/opencode/gatea-r3b-attack-20260917.py` imports the **real** production modules and
exercises the shipped functions. Key results (all values actual):

```
signature durable_delta_status(... require_complete_baseline=True)  -> True
OLD escape hatch (test-only, require_complete_baseline=False)       -> 'intact'   [old behavior preserved only in tests]
baseline_is_complete(PARTIAL)                                       -> False
shipped default durable_delta_status(PARTIAL, GROWN)                -> 'unknown'  [was 'intact' in R2]
combine_delta_status(['unknown'])                                   -> None
scope_drop_events(no proof) -> UNKNOWN; drop_scope_ok(...)['ok']    -> False
Gate.finish()                                                       -> ('INVALID', 2)
```

Same pair as my prior report: `PARTIAL = {n_present:100, n_absent:64899, first_absent_index:100,
n_runs:1, longest_run_len:100}`, `GROWN = {n_present:64998, n_absent:1, first_absent_index:64998,
n_runs:1, longest_run_len:64998}`.

New-bypass hunt (all pass, fail-closed direction):

| attack | result |
|---|---|
| partial baseline, no growth | `unknown` |
| complete baseline, one-page loss (≥0.99 ratio) | `lost` → TARGET → INVALID |
| complete baseline, equal complete recheck | `intact` → FOREIGN (intended allow path) |
| complete baseline, partial recheck | `lost` |
| complete baseline, recheck missing a proxy | `unknown` |
| F1 raw membership shape (no `query_window_len` key) | `baseline_is_complete` True only when `n_absent==0`, i.e. all queried window pages present |
| `n_present < query_window_len` with `n_absent==0` | incomplete → `unknown` |
| inconsistent `now` (`n_absent==0` but `first_absent_index` set) | `lost` |
| run-count rise / longest-run fall with equal counts | `lost` |
| drop between the two post-drop snapshots | second snapshot → `lost`; missing snapshot → `unknown` |
| empty/absent baseline or now, `combine([])`, `combine(['unknown'])` | `unknown`/`None` (fail closed) |

**Call-graph audit (required): the strict path is the ONLY production path.** AST scan of the four
production modules plus source inspection:

| production `scope_drop_events` call | `refs_intact` expression | route to `foreign`? |
|---|---|---|
| `gate_a_content_integrity.py:643` | `refs_intact` (None @624, else `combine_delta_status([delta_status_with_rechecks(baseline_by_target[t], post_snaps)])` @637-641) | strict default; complete drop-free baseline + rechecks |
| `gate_a_f1_cold_l1.py:684` | `refs_intact` (None @666, else same strict combo @681-682) | strict default |
| `gate_a_f1_cold_l1.py:833` (`_cold_window_drop_scope`) | `combine_delta_status([durable_delta_status(pre_mem, post_mem)])` @830-831 | strict default (complete pre-snapshot only) |
| `gate_a_f1_cold_l1.py:872` (sweep) | literal `None` | never foreign (any drop INVALID) |
| `f2_restart_recovery.py:342` (primer) | `refs_intact = None` @340 | never foreign (any drop INVALID) |

- `grep`/AST: **0** production occurrences of `require_complete_baseline=False` (only
  `test_gate_helpers.py:809`, which demonstrates the old behavior). `durable_delta_status` default
  is `True` (`gate_common.py:961`); the only other caller, `delta_status_with_rechecks`
  (`gate_common.py:1028`), passes no override.
- `DropScope(refs_intact)` (`gate_common.py:1098`) takes the parameter, not a literal; no production
  literal `refs_intact=True` exists. `DropScope.classify` returns FOREIGN only on `is True`
  (`gate_common.py:1086-1087`).
- The baseline freeze (`gaci:609-614`, `f1:655-658`) only advances while NO drop is in the cumulative
  console window, and `baseline_is_complete` additionally requires full coverage.
- Fail-closed enforcement is at the call sites, not just in recorded checks: `gaci:673-686`
  invalidates and returns before the measured arms; `gaci:339-358` re-asserts
  `pre_no_target_drop_without_backup`; `f1:696-708` returns `ok=False` → caller invalidates at
  `f1:284-286`; `f1:577-584` cold INVALID; `f1:386-388` sweep abort INVALID; `f2:355-362` primer
  INVALID. `Gate.finish` (`gate_common.py:301-326`) orders INVALID > FAIL > PASS and never PASSes
  on a missing/failed required check.

Producer-non-vacuity check: `wal_forensics.mode_membership` computes
`n_absent = len(window) - len(present)` (`wal_forensics.py:273-282`) over
`window = hashes[:query_window_len]` (`:246-252`), and every gate caller passes
`query_window_len = len(ids)-1` (`gaci:801` + explicit stamp `gaci:808`; `f1:771`; `f2:322`).
Therefore `n_absent == 0` means every page of the intended target window is present in the offline
replay index — the completeness predicate is not vacuously true for this producer.
`f1/f2` raw membership dicts lack the `query_window_len` key, but `n_absent==0` is equivalent given
the producer's complement formula (verified as `s7`/`s8` above), so no bypass opens there.

### 4. D2 README — verified by literal grep and by reading the passages

```
$ grep -n -i "node-id|root_id|ordering" README.md
153:   node-id ordering is **not** an attribution mechanism (the rule was removed: ...
189:membership -- is `unknown` => INVALID (fail closed).  `root_id` is record-only;
190:the removed console node-id ordering rule is never used.

$ grep -n -i "delta" README.md
146: ... A drop is disposable only when a **positive DELTA
169:### Target-scoped drop predicate: positive complete-baseline delta
171:`gate_common.durable_delta_status` / `delta_status_with_rechecks` classify a ...
173:a positive no-decrease **delta** proof holds ...
261: ... positive complete-baseline delta above; every other drop is
325: ... complete-baseline delta (in the SWEEP there is no baseline at all, so every
352: ... positive delta proof exists: ANY drop is `unknown` => INVALID.
```

`README.md:145-157` (Gate A item 6) now states: complete frozen drop-free baseline, all proxies in
both snapshots, re-snapshot confirmation, partial/missing/decrease/unattributable → INVALID, the
node-id rule removed (invariant false), and the `--min-index-fraction 0.99` STAGE acceptance as a
separate pre-existing tolerance intentionally unchanged. `README.md:169-190` is a dedicated
delta-semantics section; `README.md:260-266` labels the sweep any-drop rule
`**conservative** (**false-INVALID**…)`; `README.md:350-355` labels the F2 primer the same. The stale
node-id-bound description is gone. ⇒ D2 CLEARED.

### 5. L4 / L5 — real and test-covered (independently reproduced)

- L4: `_missing_delta_proxies` (`gate_common.py:918-926`) + presence gate in `durable_delta_status`
  (`:989-990`) and `baseline_is_complete` (`:943`). Test `test_missing_proxy_is_unknown`
  (`test_gate_helpers.py:876-889`) iterates every proxy and uses the real functions. I reproduced:
  `durable_delta_status({'n_present':1000}, full) == 'unknown'`, `durable_delta_status(full,
  {'n_present':1000}) == 'unknown'`, and `baseline_is_complete(partial-with-any-key-deleted)` False
  for all five proxies. ⇒ L4 CLEARED.
- L5: `_reclaim_evidence` (`gate_a_f1_cold_l1.py:985-996`) now sets
  `no_target_drop_without_backup = scope.get("ok") is True` whenever `dropped_no_backup_n > 0`; a
  `None` scope falls back to `ok = (n==0)`. Test `test_non_none_scope_without_ok_is_fail_closed`
  (`test_gate_helpers.py:586-606`) calls the real function. I reproduced with the real function:
  scope `{"n_total":7,"n_foreign":7}` + 7 drops → False; explicit `{"ok": True, ...}` → True;
  scope `None` + 7 drops → False; 0 drops → True. The value gates
  `post_no_target_drop_without_backup` (`f1:461-463`) and the invalidate conjunction (`f1:490-496`)
  and feeds `reclaim_evidence` for the report. ⇒ L5 CLEARED.

### 6. Change surface / scope (read-only derivation; item 2)

`git status --porcelain` (stable across the whole session; identical to the pre-R3b snapshot):

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

Attribution by mtime + content:

| path | mtime (UTC) | attribution |
|---|---|---|
| `gate_common.py` | 21:25:31 | R3b |
| `gate_a_content_integrity.py` | 21:25:41 | R3b |
| `test_gate_helpers.py` | 21:26:39 | R3b |
| `README.md` | 21:27:10 | R3b |
| `gate_a_f1_cold_l1.py` | 21:27:29 | R3b |
| `f2_restart_recovery.py` | 20:36:23 | R2 (hash unchanged by R3b) |
| `wal_forensics.py` | 11:20:18 | untouched (hash unchanged) |
| `GATEA-CLOSURES-IMPLEMENT-20260917.md` | 21:37:12 | implementer artifact (overwritten) |
| `gguf_native.py` | 16:58:54 | separate GGUF workstream (diff is token-type/vocab handling; sibling `3090-dev/gates/gguf-sampled-smoke/` 14:37–15:29 and `test/.../test_gguf_native_tokenizer_ids.py`) |
| `.memory/phase2-hicache-design/ledger.md` | 21:40:58 | memory bookkeeping (concurrently written by another agent during this review; not harness) |

No other repo path is attributable to R3b. `wal_forensics.py` is byte-identical to R2 and HEAD.
`/opt/sglang/local-prod-v1.2.1-candidate` contains no copy of this harness (env/launcher/manifest/src/tools
only) and was only read (`env/bin/python3` executed; the tree was not written).

### 7. Read-only disclosure

- My only repo-tree writes: this artifact, and gitignored bytecode under the pre-existing
  `3090-dev/gates/production/__pycache__/` produced by the dispatch-required `py_compile` step
  (`PYTHONDONTWRITEBYTECODE` does not suppress explicit `py_compile`; `git check-ignore` confirms
  `.gitignore:2:__pycache__/`). `git status --porcelain` is unchanged before/after; no tracked file
  was touched; no new untracked path appeared. I did not delete pre-existing bytecode either.
- `git status`/`git diff`/`git show` only; no `git` mutation. No GPU command, no server, no port
  bind. The suite's GPU-lock tests use `tempfile` lock paths (`test_gate_helpers.py:88-120`), not
  the production lock.

### 8. Stage check unchanged / known residual (item G)

`gate_a_content_integrity.py` current: `--min-index-fraction` default `0.99` at `:77`;
`min_present = math.ceil(args.min_index_fraction * (target_n - 1))` at `:569`; per-target
`min_present_by_target = {name: math.ceil(args.min_index_fraction * (len(ids)-1))}` at `:573-575`;
the stage check `gate.check("persist_target_in_extent_index", ok, …)` at `:753-754` with
`ok = _targets_in_index_ok(...)`. These are the exact lines/semantics recorded in my prior report
for R2 (`:77`, `:569-575`), i.e. R3b added nothing in this region (R3b insertions are the
refs_intact/recheck block at `:615-644`, after the threshold). The HEAD→current diff shows the
`min_present`/`, min-index-fraction` lines as context and only the R2-era replacement of the inline
`all(...)` with `_targets_in_index_ok` (per-target thresholds, empty-membership guard) — the change
my prior review cleared as C2b/F6. ⇒ **the `--min-index-fraction 0.99` STAGE check
(`persist_target_in_extent_index`) was NOT changed by this round**, and the **whole-gate ~1%
residual it implies REMAINS exactly as previously escalated** (same for the F1/F2 stage thresholds
`f1:625`, `f2:317`); this is a known, owner-escalated residual, not a new finding.

## Defects-blockers

No confirmed defect and no false-PASS. Ordered residuals only:

- **R-A1 (condition, documentation/handoff — not code): implementer artifact overwritten and
  incomplete.** Current artifact is 88 lines; it lost the prior CONDITIONS-ADDRESSED table
  (C1–C5/L1–L3), the r2 evidence section and the F2-removal rationale; it lacks the required
  `git status --porcelain`, the literal D2 grep, and the frozen-tree-interpreter run; its L4/L5
  evidence block is garbled (`:60-63`, `:66-70`). Its hash table and line counts are nonetheless
  accurate and its BEFORE values match my prior report, so it is incomplete/garbled, not fabricated.
  **Classification (one line): (i) documentation/presentation condition — it does not affect code
  soundness or the reviewed bytes, but the artifact must not be cited as the R3b evidence basis.**
  Minimum evidence to clear: either (a) the artifact regenerated with those evidence blocks, or
  (b) a one-line ledger/orchestrator record citing this re-review + direct inspection as the R3b
  evidence basis and declaring the overwritten artifact non-authoritative (ledger lines 8256/8291
  already record the deficiency; a confirmation closes A1). No code change is required either way.
- **R-L4b (latent, NOT reachable — false-PASS class but no production path): present-but-unparseable
  proxy values are skipped, not rejected.** `durable_delta_status` requires proxy *presence* but
  uses `_as_int`; a snapshot with `n_absent: "x"` while everything else is complete returns
  `"intact"` (my attack `s14`). Reachability: the proxy dict is produced only by
  `wal_forensics.mode_membership` (JSON ints) or copied by the harness (`gaci`/`f1`), so a
  non-integer cannot occur on any production path today; `L4`'s shipped claim is about missing
  proxies and is met. Recorded as a latent hardening item (require all five proxies to `_as_int()`
  non-`None`, else `unknown`); **not a blocker, no false-PASS reachable**.
- **R-race (pre-existing, theoretical — not demonstrated): console line vs store-state flush
  ordering and drops after the final snapshot.** The drop verdict consumes the console window and
  the offline snapshot at the same iteration; a drop whose console line lags its store effect (or
  lands after the last snapshot) could in principle escape the drop predicate. This is unchanged by
  R3b (the re-snapshot narrows it), and a real durable-page loss would surface in the measured
  oracles (exact-id storage restore with `storage>0`, `device==0`; batch_exists; head checks) as
  FAIL/INVALID rather than PASS. Classified false-INVALID-side, unproven, no action.
- **R-1% (known, owner-escalated): the unchanged `0.99` stage tolerance admits up to ~1% of the
  target window / a never-durable page without a drop event.** Pre-existing, explicitly labelled in
  README (`:155-157`), and outside the drop predicate this round fixed. Classified false-PASS class
  but **known/escalated, unchanged, and not introduced here**; no new finding.
- Prior D1 (≤1% plus partial-baseline bypass), D2 (README), L4 (missing proxy), L5 (permissive
  default) are all **CLOSED**.

Every semantic delta in this round is strictly conservative (R3b added: complete-baseline
requirement, proxy-presence requirement, worst-case re-snapshot combiner, second post-drop snapshot,
`ok is True` default removal; no allow-surface was added). Remaining permissive paths and why they
are sound: (a) `foreign` only on a complete-baseline no-decrease delta + rechecks — sound by the
completeness argument above; (b) `drop_scope_ok([])` vacuous ok when there are no drop events —
sound; (c) `_reclaim_evidence` True when `dropped_no_backup_n == 0` or scope explicitly `ok is
True` — sound; (d) the stage `0.99` tolerance — pre-existing/escalated (R-1%). No gate was weakened.

## Remaining claims / exclusions

- No live/GPU verification: the corrected drop classification's runtime reachability is judged from
  code, tests and the preserved r2 console history, not from a hardware run.
- I did not re-run `wal_forensics` against `/data`; the producer formula was verified from source,
  and the offline replay value (`n_present=52672`) remains prior-round evidence.
- The artifact deficiency (R-A1) concerns the implementer handoff, not the reviewed bytes; the
  reviewed bytes are identified by hash and match the artifact's declared AFTER table.
- The `/opt` tree and GGUF workstream are outside this verdict (mtime/attribution only).

## Verdict

**APPROVE-WITH-CONDITIONS.** Conditions D1(b), D2, L4 and L5 are CLEARED on the current bytes with
independent execution evidence; no code condition remains and no false-PASS was found. The single
remaining condition is **A1** (documentation/handoff evidence): either regenerate the implementer
artifact's evidence blocks (`git status`/diffstat, literal D2 grep, frozen-env interpreter run,
un-garbled L4/L5) or have the orchestrator record that this re-review is the R3b evidence basis and
the overwritten artifact is non-authoritative — either closes A1 with **no code change**. Absent A1,
the harness bytes themselves are APPROVE-grade and may be committed as the reviewed oracle; the
known ~1% stage residual (R-1%) remains escalated to the owner and is unchanged by this round.

## Terminal state: DONE
