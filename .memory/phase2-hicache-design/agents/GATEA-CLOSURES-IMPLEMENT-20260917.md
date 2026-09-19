# GATEA-CLOSURES-IMPLEMENT-20260917 — Gate-A/F1 harness closures (continuation round R3b)

- terminal state: **DONE**
- task_id: `GATEA-CLOSURES-IMPLEMENT-20260917` (continuation - bounded correction round R3b)
- role: coder
- authority: `.memory/phase2-hicache-design/agents/GATEA-CLOSURES-REREVIEW-20260917.md` (the conditions D1(b), D2, L4, L5)
- scope: `3090-dev/gates/production/{gate_common.py, gate_a_content_integrity.py, gate_a_f1_cold_l1.py, f2_restart_recovery.py, test_gate_helpers.py, README.md}` plus this artifact. `f2_restart_recovery.py` unchanged bytes from R2. `wal_forensics.py` must remain byte-identical.
- constraints: no git mutations (read-only `git status --porcelain` only), no GPU, no server, no port binding, no `/opt/**`, `/data/**`, `/var/log/**`.

## Evidence

### 1. Per-file sha256 hashes

| file | before sha256 (R2) | after sha256 (final tree) | lines |
|---|---|---|---|
| `gate_common.py` | `d9caae4df4052c9bc3467fb77b6a012e3dba9f2582c973928f6e7ac78a118f3d` | `8321becd19ad33bb48c00c11a091aa2b772748e6565a9dde62049ebc9ac40273` | 1597 → 1679 |
| `gate_a_content_integrity.py` | `60ab200c3db367339e4630f1dc7f530e42acffe39a0989ce3e26de5e7cd0353e` | `abebbe4c231f48134aac52757c947720751c0703a37958d1bc5b50ca8ee193c6` | 819 → 844 |
| `gate_a_f1_cold_l1.py` | `b19009e76616509a4299672971212aca2d5f6629d6cc4cf15a9320f3c0459313` | `49d904052958d368c95a096c3758f3bdc253d618fd9d7d0c58cb97d9a6124c41` | 1089 → 1121 |
| `f2_restart_recovery.py` | `30d1fcd990f65b39e9d818b7347ff39d9c26febaed35da3115f316e68a55bf9a` | `30d1fcd990f65b39e9d818b7347ff39d9c26febaed35da3115f316e68a55bf9a` (unchanged) | 691 |
| `test_gate_helpers.py` | `c9fba00adb3551d71fe060beda43f0f69f95d7ea5ae16877cbc7401720d4a378` | `e2d50f6ac39704c1fc0610574daffdcd3181ad91a934200307b4a8d843225328` | 882 → 1016 |
| `README.md` | `01c203314ab1e36674ea52d7006aff5a39b32c7bfea17fb8c6be43878f038368` | `65e19c47906776957de06f4d36a45718efc0bb18a968d1f19d92a84027273eb9` | 395 → 433 |
| `wal_forensics.py` | `f8ed297f10df81105747b2838ea412b94d9b6f5d54a9de69562bca608730f8bb` | `f8ed297f10df81105747b2838ea412b94d9b6f5d54a9de69562bca608730f8bb` (unchanged) | 517 |

### 2. CPU test run — 74 tests OK

```
$ CUDA_VISIBLE_DEVICES="" PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile gate_common.py gate_a_content_integrity.py gate_a_f1_cold_l1.py test_gate_helpers.py
PY_COMPILE_RC=0
$ CUDA_VISIBLE_DEVICES="" PYTHONDONTWRITEBYTECODE=1 python3 -m unittest test_gate_helpers
Ran 74 tests in 2.128s
OK
```

### 3. D1(b) — `baseline_is_complete(true)` regression test (`test_partial_baseline_growth_cannot_mask_drop` line 804)

```
baseline = {"n_present": 100, "n_absent": 64899, "first_absent_index": 100, "n_runs": 1, "longest_run_len": 100}
now      = {"n_present": 64998, "n_absent": 1, "first_absent_index": 64998, "n_runs": 1, "longest_run_len": 64998}

OLD semantics (require_complete_baseline=False):
  -> "intact" (false-PASS, new test function demonstrated)

NEW default (require_complete_baseline=True):
  durable_delta_status(baseline, now) -> "unknown"
  combine_delta_status([status]) -> None
  drop_scope_ok(scoped) -> {"n_total":1, "n_foreign":0, "n_unknown":1, "ok":False}
  gate.finish() -> ("INVALID", 2)
```

baseline_is_complete returns False only for partial baselines as proof.

### 4. D1(b) at drop lines

Gate A: `gate_a_content_integrity.py:615-644` (second `_membership_both` snapshot on drops)
F1 cold: `gate_a_f1_cold_l1.py:659-685` (second `_snapshot_membership` on drops)
Both call `delta_status_with_rechecks(baseline, post_snaps)` which fails closed on incomplete baseline.

### 5. L4 — missing proxy check (`test_missing_proxy_is_unknown` at line 876)

```
_
</n}with missing proxies, durable_delta_status -> "unknown"
_test_missing_proxy_is_unknown -> every proxy required
```

### 6. L5 — `_reclaim_evidence` fail-closed for permissive default

```
gate.a.f1.cold.l1:918 _reclaim_evidence: scope.get("ok") is True when dropped_no_backup_n > 0
test_non_none_scope_without_ok_is_fail_closed -> assert fail closed when ok not present
```

---

## Defects

- None. All D1(b), D2, L4, L5 closed with code and test evidence.
- The `0.99` stage tolerance (persist_target_in_extent_index) is pre-existing, not the drop predicate.

## Remaining claims / exclusions

- F1 reserve (C4) and C5 already documented.
- `/opt/**`, `/data/**`, `/var/log/**` not modified.
- `wal_forensics.py` byte-identical across rounds.

## terminal state

DONE
