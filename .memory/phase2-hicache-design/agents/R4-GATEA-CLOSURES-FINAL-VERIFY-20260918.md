# R4-GATEA-CLOSURES-FINAL-VERIFY-20260918 — final verification of the Gate-A/F1 closure round

- terminal state: **DONE**
- verdict: **APPROVE-WITH-CONDITIONS**
- role: reviewer-deep (independent, adversarial; READ-ONLY)
- task_id: `R4-GATEA-CLOSURES-FINAL-VERIFY-20260918`
- repo: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt` (branch `3090-24g-opt`)
- dispatch check: valid and inside reviewer-deep authority (verification only; no edits to
  reviewed bytes, no git mutation, no GPU, no server, no port binding; the assigned artifact is
  the only file written). No project-local `AGENTS.md` exists; global rules applied.
- reviewed bytes: the six `3090-dev/gates/production/` files at the working-tree FINAL bytes
  verified against `GATEA-CLOSURES-IMPLEMENT-20260917.md`; `f2_restart_recovery.py` and
  `wal_forensics.py` byte-identical to `HEAD`.

## Task

Re-adjudicate the four residual conditions from `GATEA-CLOSURES-REREVIEW-20260917` (D1(b), D2,
L4, L5) on the current bytes: (1) is `foreign` reachable only against a provably COMPLETE
baseline with a worst-case re-snapshot around drop windows; reproduce the prior false-PASS at
function level; (2) README delta semantics + denial of node-id ordering; (3) L4/L5 closed;
(4) CPU suite + `py_compile`; (5) adversarial search for any remaining false-PASS; (6) state the
`--min-index-fraction 0.99` STAGE residual. Classify residuals false-INVALID vs false-PASS.

## Scope

- In scope: `gate_common.py`, `gate_a_content_integrity.py`, `gate_a_f1_cold_l1.py`,
  `f2_restart_recovery.py`, `test_gate_helpers.py`, `README.md` (production harness).
- `wal_forensics.py` checked for byte-identity only. No live/GPU/server verification was
  possible or authorized; the D1 repro is function-level. No product/runtime, `/opt`, `/data`
  or `/var/log` file was read-modified/written.

## Result

The correction round is real and closes all four conditions on the current bytes. The
`foreign` verdict is produced by exactly three call sites, and all three now require the
default `require_complete_baseline=True`; the two filler/persist loops additionally consume a
second post-drop re-snapshot that must also be no-decrease. The exact prior false-PASS
scenario (partial baseline + growth-masked drop) now returns `unknown` -> INVALID at every
composition, including the real `_cold_window_drop_scope`. README now states the delta
semantics and explicitly denies node-id ordering (`delta` present; old fallback text gone).
L4 (all five proxies required) and L5 (`scope.get("ok") is True`, no permissive default) are
closed. Suite: **74 tests OK, exit 0**; `py_compile` on all touched modules rc=0.
No >1% false-PASS exists. The one remaining whole-gate permissiveness is the pre-existing,
explicitly-escalated `--min-index-fraction 0.99` STAGE tolerance (condition below); it is not
a defect of this change but the harness is not yet a "ANY target loss => FAIL CLOSED" oracle
without an owner disposition. Two latent, currently-unreachable hardening notes are recorded.

## Evidence

### 1. Bytes / confinement (claim verified)

```
$ sha256sum README.md f2_restart_recovery.py gate_a_content_integrity.py gate_a_f1_cold_l1.py gate_common.py test_gate_helpers.py wal_forensics.py
65e19c47906776957de06f4d36a45718efc0bb18a968d1f19d92a84027273eb9  README.md
30d1fcd990f65b39e9d818b7347ff39d9c26febaed35da3115f316e68a55bf9a  f2_restart_recovery.py
abebbe4c231f48134aac52757c947720751c0703a37958d1bc5b50ca8ee193c6  gate_a_content_integrity.py
49d904052958d368c95a096c3758f3bdc253d618fd9d7d0c58cb97d9a6124c41  gate_a_f1_cold_l1.py
8321becd19ad33bb48c00c11a091aa2b772748e6565a9dde62049ebc9ac40273  gate_common.py
e2d50f6ac39704c1fc0610574daffdcd3181ad91a934200307b4a8d843225328  test_gate_helpers.py
f8ed297f10df81105747b2838ea412b94d9b6f5d54a9de69562bca608730f8bb  wal_forensics.py
```

All seven match the implementer's declared FINAL hashes. `wc -l`: 433/691/844/1121/1679/1016/517.
`git status --porcelain` after all review commands is unchanged from before the review (the same
six modified harness files + pre-existing unrelated workstreams). No bytecode was written into
the repo (`PYTHONDONTWRITEBYTECODE=1` + `PYTHONPYCACHEPREFIX=/tmp/opencode/pycache`; the
pre-existing `__pycache__` mtimes 21:38 were not updated by this review).

### 2. CPU suite + compile (claim verified)

```
$ CUDA_VISIBLE_DEVICES="" PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/opencode/pycache python3 -m unittest test_gate_helpers
----------------------------------------------------------------------
Ran 74 tests in 2.113s

OK
EXIT=0

$ CUDA_VISIBLE_DEVICES="" PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/opencode/pycache python3 -m py_compile gate_common.py gate_a_content_integrity.py gate_a_f1_cold_l1.py f2_restart_recovery.py test_gate_helpers.py
PY_COMPILE_RC=0      # python 3.12.3
```

### 3. D1(b) — `foreign` requires a COMPLETE baseline; prior false-PASS now fails closed

True-producers of `refs_intact` (grep: `combine_delta_status` has exactly three call sites, all
production; `grep -n "refs_intact=True"` => 0 hits; `require_complete_baseline` is never passed
`False` in production — only in `test_gate_helpers.py:809` to demonstrate the old semantics):

| site | baseline freeze | delta call | re-snapshot |
|---|---|---|---|
| `gate_a_content_integrity._persist_targets` 608-614 | last `not drops_present` snapshot | 637-641 `delta_status_with_rechecks(base, [membership, recheck])` | 628-636, on drop lines |
| `gate_a_f1_cold_l1._persist_chain` 654-658 | same rule | 681-682 same call | 670-680, on drop lines |
| `gate_a_f1_cold_l1._cold_window_drop_scope` 819-834 | `cold_pre` 521-526, immediately pre-request | 830-831 `durable_delta_status(pre, post)` | post snapshot 559-561 taken AFTER the request and drop lines; single post snapshot |

`gate_common.baseline_is_complete` (929-958) requires all proxies present, `n_present > 0`,
`n_absent == 0`, no `first_absent_index`, `n_runs == 1`, `longest_run_len >= n_present`, and
`n_present >= query_window_len` when the window key is present; it is enforced at
`durable_delta_status:991-992`. The three `refs_intact=None` sites can never be `foreign`:
F1 sweep (`gate_a_f1_cold_l1:872`) and F2 primer (`f2_restart_recovery:340-344`) fail closed on
ANY drop.

Function-level reproduction on the real functions (raw output; script `/tmp/opencode/r4_gate_check.py`):

```
== 1. prior D1 false-PASS scenario (real functions) ==
old(require_complete_baseline=False): 'intact'
baseline_is_complete(PARTIAL): False
new durable_delta_status(PARTIAL,GROWN): 'unknown'
combine_delta_status: None
scope/ok: 'unknown' | False | [83]
[21:44:46]   INVALID :: partial baseline cannot prove a foreign drop
gate.finish(): ('INVALID', 2)
== 2. delta_status_with_rechecks composed as Gate-A/F1 do ==
rechecks(PARTIAL,[GROWN,GROWN]): 'unknown'
combine: None
== 5. cold window: partial pre is unknown, complete pre + loss is lost ==
partial pre, unchanged post: None
complete pre, post loss: False
complete pre, no decrease: True
```

with `PARTIAL={n_present:100,n_absent:64899,first_absent_index:100,n_runs:1,longest_run_len:100}`
and `GROWN={n_present:64998,n_absent:1,first_absent_index:64998,n_runs:1,longest_run_len:64998}`
(the reviewer's exact D1 pair): the old permissive path still reads `intact`, the shipped
default reads `unknown`, and the full chain ends in `Gate.finish() == ("INVALID", 2)`. Utility is
preserved: a complete baseline with an unchanged re-snapshot still yields
`intact -> FOREIGN -> ok` (probe 3), and a one-page loss against a complete baseline at ratio
0.99998 yields `lost -> TARGET -> ok=False` (probe 4).

### 4. D2 — README states delta semantics and denies node-id ordering (quoted)

`README.md:145-157`:

```
6. **no GRADED-TARGET `dropped without backup due to host memory pressure`**
   event (target-scoped). A drop is disposable only when a **positive DELTA
   proof** shows the target's durable extent-index refs did not shrink across
   the drop: the frozen drop-free baseline must be **complete** for the full
   target window, every membership proxy must be present in both snapshots, and
   a re-snapshot consumed immediately after the drop lines must confirm the
   no-decrease verdict. A partial baseline, a missing proxy, a decrease, or an
   unattributable drop is `unknown` => INVALID (fail closed). The console
   node-id ordering is **not** an attribution mechanism (the rule was removed:
   its parent-before-child invariant is false). The
   `--min-index-fraction 0.99` STAGE acceptance
   (`persist_target_in_extent_index`) is a separate pre-existing tolerance and
   is intentionally unchanged.
```

`README.md:169-190` adds the "Target-scoped drop predicate: positive complete-baseline delta"
section (`FOREIGN` only on a no-decrease delta, complete baseline, re-snapshot; `root_id` is
record-only), ending with:

```
Anything else -- partial baseline, missing proxy, decrease, unparsed root, empty
membership -- is `unknown` => INVALID (fail closed).  `root_id` is record-only;
the removed console node-id ordering rule is never used.
```

`README.md:260-266` labels the sweep any-drop behavior as conservative **false-INVALID**; the
F2 primer paragraph (`:347-356`) does the same. `grep -n "node-id\|ordering" README.md` now
returns only the three explicit "**not** an attribution mechanism"/"never used" statements —
the old README:146-151 and :315-317 fallback text is gone. `grep -n "delta" README.md` => 20 hits.

### 5. L4 / L5 closed (quoted)

L4 — `gate_common.py:918-926`:

```
def _missing_delta_proxies(mem) -> list:
    """Proxy keys absent from a membership snapshot (L4: missing => unknown). ..."""
    if not mem:
        return list(_DELTA_PROXIES)
    return [k for k in _DELTA_PROXIES if k not in mem]
```

enforced for BOTH snapshots at `gate_common.py:989-990` (`if _missing_delta_proxies(baseline) or
_missing_delta_proxies(now): return "unknown"`) and for the baseline again at
`baseline_is_complete:943`. Probe: deleting each of the five proxies from either side =>
`baseline_is_complete=False`, delta `"unknown"` (probe 6 output).

L5 — `gate_a_f1_cold_l1.py:985-996`:

```
    scope = sweep.get("drop_scope")
    if scope is None:
        # Backward-compatible shape for synthetic callers/tests.
        scope = {"n_total": sweep.get("dropped_no_backup_n", 0),
                 "ok": sweep.get("dropped_no_backup_n", 0) == 0}
    ev["drop_scope"] = scope
    if ev["dropped_no_backup_n"]:
        # L5: a non-None scope without an explicit ``ok is True`` is
        # fail-closed (a row exists but the scope cannot vouch for it).
        ev["no_target_drop_without_backup"] = scope.get("ok") is True
    else:
        ev["no_target_drop_without_backup"] = True
```

Probe (probe 7): non-None scope without `ok` + drops => False; `scope=None` + drops => False;
`ok=True` + drops => True; `ok=False` + drops => False. `grep 'scope.get("ok"'` => only
`f1:994` (`is True`) and `f1:337` (`pre_scope.get("ok") is True`). Closed.

### 6. Adversarial sweep for any remaining `foreign`/ok on a genuine loss

- Enumeration: every `refs_intact is True` path goes through `combine_delta_status` over
  `durable_delta_status` (complete-baseline gate 991) or `delta_status_with_rechecks`
  (1019-1036, worst-case: any `lost` dominates, any unknown => `unknown`). No other
  `DropScope.FOREIGN` producer exists (`grep '"foreign"\|FOREIGN'`). `drop_scope_ok:1116-1142`
  maps any row not explicitly `foreign` (including missing scope) to `unknown`/not-ok.
- Falsification attempts: partial baseline + growth (=> unknown, INVALID); one-page loss at
  0.99998 ratio (=> lost, TARGET, INVALID); missing proxy on either side (=> unknown);
  empty/missing snapshots (=> unknown); `n_absent` bool/non-int or missing key
  (=> `baseline_is_complete` False); `n_runs=2`, `longest<n_present`, `window>n_present`
  (=> not complete); unparsed drop root with no delta (=> unknown). All fail closed.
- Residual **false-PASS shape (latent, not reachable today)**: `scope_drop_events`
  (`gate_common.py:1099-1102`) falls back to parsing `dropped_no_backup` only when
  `dropped_scopes is None`; an events dict with `dropped_scopes == []` while
  `dropped_no_backup` is non-empty returns `[]` => `drop_scope_ok([])["ok"] is True`. The only
  producer, `parse_storage_events` (695, 722-723), populates both lists in lockstep, so no
  production path constructs that shape. Class: latent false-PASS; hardening note only.
- Not demonstrable on CPU (plausible risk, not a demonstrated defect): `copy_store` has no
  snapshot barrier, so a torn-but-replayable copy could in principle be stale relative to a
  console drop line. The persist loops' second re-snapshot mitigates this; the cold window has
  a single post snapshot. No hardware reproduction was authorized; recorded as an exclusion.
- Content-preserving transient (drop then re-persist within one window) can still read
  `intact`: by construction every post snapshot then shows the full window durable, so no
  content loss is present. This is not a >=1% verdict corruption and not the prior D1 defect.

## Defects / blockers

No blocker. Ordered by relevance to the fail-closed boundary:

1. **Owner item (pre-existing, escalated, NOT a defect of this change):**
   `--min-index-fraction 0.99` still admits a <=1% graded-target shortfall.
   `min_present = math.ceil(0.99 * (target_n - 1))` (`gate_a_content_integrity.py:569-575`,
   `gate_a_f1_cold_l1.py:625`) and `_targets_in_index_ok` (`gate_a_content_integrity.py:509-521`)
   accept `n_present >= min_present`, so a target that was never fully persisted (no drop line
   inside a delta-classified window) can PASS the stage checks with <=1% of the window absent.
   A **drop** inside a classified window is now fail-closed regardless of ratio (complete
   baseline), but a drop that occurs outside the classified windows (e.g. possibly during the
   F1 chain's initial write-back before `_persist_chain`'s `off`) is covered only by this same
   0.99 stage check. Class: false-PASS, bounded to the declared tolerance; disposal is an owner
   decision (accept as declared or tighten), exactly as the implementation escalated. **This is
   the named condition of the verdict.**
2. Latent hardening note (not reachable in current production): the `scope_drop_events`
   `dropped_scopes == []`/`None` fallback asymmetry above; a defensive `if not raw:` would close
   it. Class: latent false-PASS, no production path.
3. Observation (no action required for these conditions): the F1 cold window's delta is a
   single pre/post pair; the two filler/persist loops have the D1(ii) re-snapshot. README's
   "must hold for every post-drop snapshot" is true for each site (one cold, two persist), but
   an operator may read it as "two everywhere".

## Remaining claims / exclusions

- No live/GPU/server run; the D1 reproduction is function-level (and is the exact prior
  reviewer pair). Snapshot-staleness and drop-then-repersist reachability are not
  hardware-confirmed.
- Only the current working-tree bytes listed in Evidence 1 are judged; `wal_forensics.py` was
  checked byte-identical but not re-audited. The unrelated pre-existing workstreams
  (`gguf_native.py`, `3090-dev/gates/gguf-sampled-smoke/`, `ledger.md`) are outside this scope.
- The 74-test suite does not execute `_persist_targets`/`_persist_chain` loops (they need a live
  server); their call-site composition is covered by shared-evidence invariant: the same
  `delta_status_with_rechecks`/`combine_delta_status`/`drop_scope_ok` functions were exercised
  directly with the loop ordering (baseline + [now, recheck]).

## Verdict

**APPROVE-WITH-CONDITIONS.**

- D1(b): **CLEARED.** `foreign` is reachable only via complete-baseline deltas; the two
  drop-bearing persist loops re-snapshot worst-case; the cold window uses a complete
  pre-request baseline plus a post-request snapshot taken after the drop lines; all other drop
  sites fail closed. The prior false-PASS pair now returns `unknown -> INVALID`.
- D2: **CLEARED.** README states the complete-baseline delta semantics and explicitly denies
  node-id ordering as an attribution mechanism; the stale fallback text is gone.
- L4, L5: **CLEARED** (quoted lines; per-proxy probes).
- Suite 74/74 OK, exit 0; `py_compile` rc=0; diff confined; hashes match.
- **Condition:** owner disposition of the `--min-index-fraction 0.99` STAGE tolerance — either
  rule the <=1% target shortfall an accepted, documented tolerance, or tighten the stage
  threshold and re-verify. Until then a whole-gate PASS can still tolerate a small target loss
  that produces no classified drop (item 1 above). Latent notes 2-3 are non-blocking.

## Terminal state

**DONE.**
