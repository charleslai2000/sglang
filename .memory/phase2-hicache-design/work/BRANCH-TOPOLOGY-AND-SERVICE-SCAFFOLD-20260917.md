# Branch topology + service scaffold (devops) — with an orchestrator correction

## 1. CORRECTION to the devops report (verified by orchestrator)
Devops claimed the repo worktree `extent_file_backend.py` is a **"hybrid: v1.1.2 minus Option-C, plus the
v1.1 WAL hunk"**. **That is wrong.** Verified by direct diff:

```
diff <worktree> <frozen v1.1>  =>  exactly 3 lines added at 2160a2161,2163:
    # _open_active_wal() max()es against this watermark; a stale value
    # renumbers the new segment below the published checkpoint lsn.
    self._wal_recovered_next_seq = self._wal_next_seq
```

wal_fix site counts: HEAD=3, **worktree=3**, frozen v1.1=4, frozen v1.1.2=4.
Line-diff magnitudes: worktree vs v1.1 = **3 lines**; worktree vs v1.1.2 = 177 lines; HEAD vs v1.1 = 205 lines.

=> The worktree file is simply **pre-fix v1.1** (frozen v1.1 minus the `:2163` checkpoint hunk). It is NOT a
hybrid of v1.1.2. Practical consequence: the missing piece is exactly **one 3-line hunk**, and Option-C is
NOT present in the worktree at all. Any "commit the worktree file" decision must supply that hunk, or it
regresses the WAL checkpoint fix.

## 2. Branch roles (devops finding — contradicts the assumption that hicache is production)
* `3090-24g-opt` = the **working/dev branch AND the GitHub default branch**
  (evidence: `WORK-INVENTORY`, `HANDOFF` §11.4, `ledger.md:7350`).
* `origin/3090-24g-hicache` = **archive/superset, NOT production**. Its only unique content = 2 docs about a
  *different host* (22151) + the merge commit.
* **Actual production source = `/opt/sglang/**`, outside git entirely.**
* A ref `wip/p0-telemetry-current-17` exists on origin at the same commit as `a207b567fe`.

## 3. Blocking finding
`a207b567fe wip(p0-telemetry): UNREVIEWED snapshot` sits on **`origin/3090-24g-opt`, the default branch**
=> a fresh clone receives unreviewed code with 3 open defects. It must not enter a production/archive branch
unreviewed.

## 4. Disk constraint (affects production start)
Launcher `perf` profile: `L2_GB=32`, `L3_MAX=100Gi`, `SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE=50Gi`.
`/` currently **125 GiB free**. With MIN_FREE=50Gi the store can grow only to ~75 GiB before the backend must
stop taking writes. Not fatal, but the L3 ceiling is effectively below the nominal 100Gi. Owner's prior
"reclaim now, tiered" ruling applies before a production start.

## 5. Service scaffold (delivered, CPU-validated, nothing started)
`/tmp/opencode/prod-service-20260917/`: `bin/{common,preflight,start,supervise,stop,status,switch}.sh`
(all `bash -n` OK), `conf/service.env`, `state/gpu-owner.json` (currently `free`), `README.md`, `ANALYSIS.md`.
* Port map: **30000 production / 30164 test / 30165 gates**.
* Preflight PASS on v1.1.2, REFUSE on v1.1 and v1. The launcher fail-closed gate exists on v1.1.2 only.
* Cold start **measured 79 s** (13 s launcher gates + 66 s server init).
* Editable-install landmine reproduced exactly (import resolves to the stale repo copy without PYTHONPATH).
* **Single-GPU reality**: 24,576 MiB total; M1@64K fp8 uses 18,691 MiB => production and test CANNOT serve
  concurrently. Handoff model implemented via the owner-visible `gpu-owner.json` state record.
* Disclosed incident: a scratch flock test wrote canonical lock *content* (flock never held, incumbent never
  signalled); root cause fixed by making the lock path non-overridable.

## 6. Re-dispatched
`harness-storage-reachability-fix-v2-20260917` (devops) — the earlier two `coder` attempts produced no output
(provider failures). Spec: correct host-pool sizing (must be >= graded prompt; the earlier "make L2 small"
instruction was wrong below that floor), deterministic F1 recycle via unrelated unique prefixes (the old
prefix-matching sweep allocated no new slots -> 0 recycles), flush-cache HTTP 400 must be INVALID, unique
namespaces, and the corrected evidence fields.

## 7. Production-source-outside-git: measured (orchestrator)
Correct whole-tree comparison, frozen `src/` (14,647 files) vs `repo HEAD`:

| category | count |
|---|---:|
| source files **differing** from repo HEAD | **20** (17 substantive `.py` + 3 trivial) |
| build artifacts differing | 0 |
| "not in git" total | 5,308 — **overwhelmingly `rust/target/**` build artifacts** + untracked `.memory/` docs (274 artifact-only after filtering) |

The 20 differing source files (production-only patches, present in NO git branch):
* **Option-C relocation**: `mem_cache/storage/extent/extent_allocator.py`, `extent_file_backend.py`
* **WAL checkpoint fix**: `extent_file_backend.py` (the `:2337` hunk in v1.1.2)
* **Qwen3.5/M1 model support**: `configs/qwen3_5.py`, `models/qwen3_5.py` (95 diff lines),
  `models/qwen3_5_text.py` (35 diff lines) — the files EXIST in HEAD, but these production patches do not
* **GGUF**: `layers/quantization/gguf.py`, `model_loader/gguf_name_maps.py`, `model_loader/loader.py`,
  `model_loader/weight_utils.py`, `utils/hf_transformers/gguf_native.py`
* **HiCache telemetry / RH**: `observability/hicache_telemetry.py`,
  `managers/scheduler_components/output_streamer.py`, `managers/tokenizer_manager.py`,
  `mem_cache/unified_radix_cache.py`, `environ.py`, plus the 2 unit tests
* trivial: `.dockerignore`, `mem_cache/cpp_radix_tree/.clang-format`, `sgl-model-gateway/LICENSE`

**Verdict on "is this allowed?":** deploying a build artifact outside git is normal practice. What we have
here is different: a FULL SOURCE TREE carrying 17 substantive production patches that exist in no branch.
Compensating control = the freeze manifest (`manifest/TREE-SHA256.txt` digest + `identity.json` + pins +
launcher preflight), so production IS verifiable and reproducible **by hash**. But it is NOT reproducible by
git, NOT reviewable as a diff/PR, and **if `/opt/sglang/**` is lost, production source is unrecoverable**.
=> Real governance gap; the fix is to export these 20 files as a patch and land them in git.
