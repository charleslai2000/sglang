# Reconciliation Report: 3090-24g-opt @ ad749d6f28 -> Frozen v1.1.2
Generated: 2026-09-17
Repo: /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt
Frozen: /opt/sglang/local-prod-v1.1.2-candidate/src
Option-C ref: /tmp/opencode/v1.1.2-optionC-20260917/src

---

## 1. Group Verification with Per-File Hashes

### Group A [14 files] — Worktree == Frozen (already present, need committing)

| File | HEAD SHA256 | Worktree SHA256 | Frozen v1.1.2 SHA256 | Match? |
|------|------------|-----------------|---------------------|--------|
| `.dockerignore` | cd1c6325d3559c6f... | 71b793acddb338c8... | 71b793acddb338c8... | YES |
| `.memory/phase2-hicache-design/work/ARTIFACT-CAPABILITY-INVENTORY-20260916.md` | 705c82827026d250... | 1993a9a87b75e9d3... | 1993a9a87b75e9d3... | YES |
| `.memory/phase2-hicache-design/work/OPEN4-SHIM-NECESSITY-VERDICT-20260916.md` | 1cc166004402bf55... | 355d543310ea11f1... | 355d543310ea11f1... | YES |
| `.memory/phase2-hicache-design/work/TOKENIZER-PROVENANCE-RESOLUTION-20260916.md` | 9776feeae573a442... | 051a7d37bc65c055... | 051a7d37bc65c055... | YES |
| `python/sglang/_version.py` | 2747d0bf4808e378... | 30851ed9d3424824... | 30851ed9d3424824... | YES |
| `python/sglang/srt/environ.py` | 9e1aa781bb6cd454... | e49571c1d6536096... | e49571c1d6536096... | YES |
| `python/sglang/srt/managers/scheduler_components/output_streamer.py` | 40c87e24d173929f... | 8485d9563e073b8e... | 8485d9563e073b8e... | YES |
| `python/sglang/srt/managers/tokenizer_manager.py` | 124bd800a7835406... | 9f9d38028008c7f6... | 9f9d38028008c7f6... | YES |
| `python/sglang/srt/mem_cache/cpp_radix_tree/.clang-format` | afbd654a7903e970... | dc2a6c4be9a0951d... | dc2a6c4be9a0951d... | YES |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | 0c5ff256c77c861a... | 5b5dc29fa21eefdf... | 5b5dc29fa21eefdf... | YES |
| `python/sglang/srt/observability/hicache_telemetry.py` | 0ecb7fd1ba9ec919... | 788318d91dc41520... | 788318d91dc41520... | YES |
| `sgl-model-gateway/LICENSE` | 9c422689c8f5c317... | 1495e1e757ef4d09... | 1495e1e757ef4d09... | YES |
| `test/registered/unit/observability/test_hicache_request_telemetry.py` | 2fdb604234d0ec30... | e577d94086dd188d... | e577d94086dd188d... | YES |
| `test/registered/unit/observability/test_output_streamer_hicache_telemetry_wiring.py` | 93858d895c1005c1... | 717ac93c6a3b1c05... | 717ac93c6a3b1c05... | YES |

**Verification: All 14 Group A files have worktree bytes identical to frozen v1.1.2 bytes. **

### Group B [9 files] — Frozen-only (absent from worktree, older in HEAD)

| File | HEAD SHA256 | Worktree | Frozen v1.1.2 SHA256 | Status |
|------|------------|----------|---------------------|--------|
| `python/sglang/srt/configs/qwen3_5.py` | 98de12f7eff0a09b... | ABSENT | 07da0996a3139b09... | PRESENT but differs |
| `python/sglang/srt/layers/quantization/gguf.py` | cc4ed6e1e642c826... | ABSENT | 74eaa05bf3a0cae1... | PRESENT but differs |
| `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py` | a3bb514d52d0ab8e... | ABSENT | fdbd9e4965b5f061... | PRESENT but differs |
| `python/sglang/srt/model_loader/gguf_name_maps.py` | 434f337af3636b53... | ABSENT | 7612c4bd9e64730f... | PRESENT but differs |
| `python/sglang/srt/model_loader/loader.py` | 613b823d626ce653... | ABSENT | 78677be30f352983... | PRESENT but differs |
| `python/sglang/srt/model_loader/weight_utils.py` | 965123fcc6b89f34... | ABSENT | bb84e385eb87c309... | PRESENT but differs |
| `python/sglang/srt/models/qwen3_5.py` | b1e31d60cdf11658... | ABSENT | e9be4d53414b1283... | PRESENT but differs |
| `python/sglang/srt/models/qwen3_5_text.py` | fb60baa60694d4f5... | ABSENT | c140253b8125df0a... | PRESENT but differs |
| `python/sglang/srt/utils/hf_transformers/gguf_native.py` | a9a95b6cd1c6f2b5... | ABSENT | c5f2e9730c88f589... | PRESENT but differs |

**Verification: All 9 Group B files exist in HEAD with older content and are absent from the worktree. They must be applied from frozen.**

### Group C [2 files] — Divergent worktree (older than both HEAD and frozen)

| File | HEAD SHA256 | Worktree SHA256 | Frozen v1.1.2 SHA256 | Status |
|------|------------|-----------------|---------------------|--------|
| `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py` | 0f02e6ca1c01cf32... | 030487eebc58e39b... | b284ec2a710d2afb... | WORKTREE LAGGING |
| `test/registered/unit/mem_cache/test_extent_file_backend_unit.py` | 4f3b23602dd6b5f5... | 71c13ad1cb5bc329... | bb08e341d14c7fe5... | WORKTREE LAGGING |

**Verification: Both Group C files have worktree bytes that differ from HEAD and from frozen v1.1.2. The worktree holds an older partial version.**

## 2. Option-C Cross-Check

Cross-checked all 9 Group B files against `/tmp/opencode/v1.1.2-optionC-20260917/` (which matches frozen 11/11).

**Result: frozen v1.1.2 == optionC tree for all 9 files. SHA256 matches confirmed for every file.**

Specifically for `extent_allocator.py` (the Option-C file):
- frozen v1.1.2 SHA256: `fdbd9e4965b5f0613ff7e12c539995233403f9567d7e7b54f5bb4d93bef10d13`
- optionC SHA256:      `fdbd9e4965b5f0613ff7e12c539995233403f9567d7e7b54f5bb4d93bef10d13`
- **MATCH: frozen == optionC**

## 3. Patch Files

### B-frozen-only.patch
- Path: `/tmp/opencode/reconcile-20260917/B-frozen-only.patch`
- Size: 30894 bytes
- Contains: 9 file diffs (HEAD -> frozen v1.1.2)
- Format: Unified diff with `a/` and `b/` labels

### C-provenance.patch
- Path: `/tmp/opencode/reconcile-20260917/C-provenance.patch`
- Size: 17417 bytes
- Contains: 2 file diffs (worktree -> frozen v1.1.2)
- Format: Unified diff showing exactly what the worktree is missing

## 4. Per-File Summary of Group B Changes

### `python/sglang/srt/configs/qwen3_5.py`
- **Change:** Adds Qwen3.5 model configuration class (Qwen3_5Config) with GGUF-specific builder (from_gguf). Registers qwen35 architecture so the model loader can instantiate the correct config when encountering a Qwen3.5 GGUF checkpoint. Includes mapping from GGUF tensor names to HuggingFace parameter names.
- **Diff size:** +95/-0

### `python/sglang/srt/layers/quantization/gguf.py`
- **Change:** Extends GGUF quantization layer to handle BF16 weights stored as uint8 in GGUF format. Adds _match_dense_weight_dtype() method that casts unquantized GGUF weights to the layer's compute dtype (F32/BF16), enabling fused_mul_mat_gguf to consume checkpoint shards with fused tensor shards in compact dtype.
- **Diff size:** +16/-0

### `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py`
- **Change:** Implements Option-C: adds plan_relocation() method that computes a safe relocation plan for moving extent refs between slots. Takes victim_slots, key_lengths, and excluded_slots, produces an ordered list of (key, ExtentRef, component) tuples that can be durably replayed via the existing WAL SET+BATCH_COMMIT protocol. Enables cross-host extent migration without new WAL frame types.
- **Diff size:** +63/-0

### `python/sglang/srt/model_loader/gguf_name_maps.py`
- **Change:** Adds GGUF-to-HF name mapping tables for Qwen3.5 architecture. Defines _QWEN35_GLOBAL_TENSORS dict mapping GGUF tensor names (token_embd.weight, output_norm.weight, output.weight) to HuggingFace parameter names (model.embed_tokens.weight, model.norm.weight, lm_head.weight). Adds GGUF_HF_NAME_MAP_BUILDERS and GGUF_HF_NAME_MAP_VALIDATORS registries.
- **Diff size:** +121/-0

### `python/sglang/srt/model_loader/loader.py`
- **Change:** Integrates GGUF name maps into the model loader. Modifies _get_gguf_weights_map() to import and use GGUF_HF_NAME_MAP_BUILDERS and GGUF_HF_NAME_MAP_VALIDATORS from gguf_name_maps. Adds qwen35 architecture dispatch so GGUF checkpoints with Qwen3.5 architecture are loaded with the correct name mapping and config class.
- **Diff size:** +14/-4

### `python/sglang/srt/model_loader/weight_utils.py`
- **Change:** Adds BF16 weight handling for GGUF uint8 quantized weights. When weight_type is BF16 and param dtype is uint8, the weight is reinterpreted as bfloat16 via param.view(torch.bfloat16). Handles GGUF checkpoints that store BF16 weights in a compressed uint8 container format.
- **Diff size:** +5/-0

### `python/sglang/srt/models/qwen3_5.py`
- **Change:** Implements Qwen3.5 model class with GGUF support. Adds GGUF weight loading path for Qwen3.5 architecture, including handling of fused QKV weights, gated MLP, and ssm_a (Mamba) parameters. Defines parameter name mappings for GGUF-to-model weight conversion and adds support for both dense and quantized GGUF weight formats.
- **Diff size:** +78/-2

### `python/sglang/srt/models/qwen3_5_text.py`
- **Change:** Implements Qwen3.5 text-only model variant. Adds _LM_HEAD_PARAM_NAMES tuple covering both standard and GGUF quantized lm_head parameter names. Implements _gguf_ssm_a_to_a_log() to undo llama.cpp's GGUF-time A_log -> -exp(A_log) storage transform for Mamba SSM parameters. Adds GGUF weight loading with proper dtype handling for text-only Qwen3.5 models.
- **Diff size:** +26/-9

### `python/sglang/srt/utils/hf_transformers/gguf_native.py`
- **Change:** Registers Qwen3.5 architecture in the GGUF-native HF transformers integration. Adds Qwen3_5TextConfig import and registers qwen35 architecture with from_gguf builder. Adds tokenizer pattern for Qwen3.5 BPE tokenization that handles the model's specific special token set and regex patterns.
- **Diff size:** +12/-0

## 5. Group C Provenance Decision

### extent_file_backend.py

The worktree is frozen v1.1 minus one 3-line hunk (`self._wal_recovered_next_seq = self._wal_next_seq` in `checkpoint()`, at v1.1 `:2163` / v1.1.2 `:2337`). This hunk ensures the WAL recovery sequence number is advanced past the checkpoint LSN, preventing new WAL segments from being numbered below the published checkpoint. Without it, WAL replay after a crash recovery could produce incorrect or duplicate data.

**The worktree also contains NO Option-C code** (the `_append_relocation_commit` method and `plan_relocation` integration are absent).

### test_extent_file_backend_unit.py

The worktree test file is also older than frozen, missing tests for the Option-C relocation plan and the WAL checkpoint fix.

### Minimal Decision Needed

**Adopt frozen v1.1.2 bytes for both Group C files.** The worktree is a regressed v1.1 that is missing both the WAL checkpoint fix (3-line hunk) and the Option-C relocation feature. Committing the worktree bytes as-is would regress the WAL checkpoint fix and lose Option-C entirely.

## 6. Ordered Apply/Commit + Merge Plan

### Prerequisites
- Read-only access to repo (no git writes)
- Read-only access to `/opt/sglang/local-prod-v1.1.2-candidate/src`
- All patches exported to `/tmp/opencode/reconcile-20260917/`

### Step 1: Commit Group [A] as-is

**Command:** `git add -A && git commit -m "chore: commit frozen v1.1.2 production files (Group A)"`

**What it does:** Stages all 14 Group A files (8 modified tracked + 6 untracked) and commits them. The worktree bytes are already byte-identical to frozen v1.1.2, so this simply records them in git history.

**Reversibility:** `git revert <commit>` or `git reset HEAD~1` (soft reset to undo commit, keep working tree).

**Blast radius:** Minimal — only adds commit history for files already matching production.

**Risk:** LOW. The 8 modified tracked files are already at frozen bytes; the 6 untracked files (.memory/*, test wiring, .dockerignore) are also at frozen bytes. No code changes are introduced — this is purely a commit recording existing state.

### Step 2: Apply Group [B] from frozen export

**Command:** `git apply /tmp/opencode/reconcile-20260917/B-frozen-only.patch`

**What it does:** Applies the 9 file diffs (HEAD -> frozen v1.1.2) to the working tree. This replaces the older HEAD content of these 9 tracked files with the frozen v1.1.2 content. The patch is clean (no rejects expected) because these files are tracked in HEAD with older content.

**Reversibility:** `git checkout HEAD -- <file>` for each file, or `git reset --hard HEAD` before the commit step.

**Blast radius:** Medium — touches 9 production source files including GGUF loader, Qwen3.5 model support, and Option-C extent allocator.

**Risk:** MEDIUM. These are substantive code changes (Qwen3.5 model support, GGUF loader, Option-C relocation). The patch has been verified against frozen v1.1.2 which matches the optionC reference tree 11/11. However, these changes have NOT been tested in this environment (CPU-only, no GPU). The Option-C relocation feature is the highest-risk change — it modifies extent allocation behavior.

### Step 3: Resolve Group [C]

**Command:** `git apply /tmp/opencode/reconcile-20260917/C-provenance.patch`

**What it does:** Replaces the worktree's regressed v1.1 content of `extent_file_backend.py` and `test_extent_file_backend_unit.py` with frozen v1.1.2 content. This adds back the 3-line WAL checkpoint fix and the Option-C relocation integration.

**Reversibility:** `git checkout HEAD -- <file>` for each file, or `git stash` before applying.

**Blast radius:** Low — 2 test/infrastructure files.

**Risk:** LOW-MEDIUM. The WAL checkpoint fix is a 3-line hunk that prevents WAL segment numbering regression. The test file update adds coverage for Option-C. Both are well-understood changes.

### Step 4: Commit Groups [B] + [C]

**Command:** `git add -A && git commit -m "feat: apply frozen v1.1.2 production patch (Group B: Qwen3.5/GGUF/Option-C, Group C: WAL checkpoint fix)"`

**Reversibility:** `git revert <commit>` or `git reset HEAD~1`.

**Risk:** LOW (revert is clean).

### Step 5: Merge `3090-24g-hicache` into `3090-24g-opt`

**Topology:**
- `3090-24g-opt` @ ad749d6f28 (6 commits since merge-base)
- `origin/3090-24g-hicache` @ 560f9ad525 (3 commits since merge-base)
- Merge-base: 34bd2ed49f

**hicache-only 3 commits:**
1. `560f9ad525` Merge branch '3090-24g-opt' into 3090-24g-hicache
2. `0a725c6385` docs(3090-dev): handover report for 22151 HiCache production env
3. `5a76070743` docs(3090-dev): baseline production deploy issue record + relaunch script (Qwen3.5-9B on 22151)

**opt-only 6 commits:**
1. `ad749d6f28` docs(memory): commit-time state, cross-host resume, path corrections
2. `1dcaa80473` test(extent-g1): use a real KV+Mamba grouped fixture
3. `a207b567fe` wip(p0-telemetry): UNREVIEWED snapshot of the 17-file current identity
4. `48233f3aba` fix(qwen3_5_text): strip model.language_model. prefix before generic strip
5. `ce73d6671f` docs(memory): vendor P0 telemetry authoritative evidence (<1MB)
6. `1352a69997` docs(memory): record branch consolidation 3060-12g-qwen35-4b -> 3090-24g-opt

**Merge command:** `git merge origin/3090-24g-hicache -m "merge: 3090-24g-hicache into 3090-24g-opt"`

**Reversibility:** `git revert -m 1 <merge-commit>` to undo the merge.

**Blast radius:** Medium — merges 3 hicache commits (2 docs + 1 merge) into opt branch.

**Risk:** LOW for the merge itself. The 3 hicache commits are all docs-only + merge commit. However, the opt branch contains `a207b567fe wip(p0-telemetry): UNREVIEWED snapshot` which is on `origin/3090-24g-opt` (the GitHub default branch). A fresh clone gets this unreviewed commit.

### DO-NOT-EXECUTE List

1. **DO NOT** `git commit`, `git merge`, `git push`, `git rebase`, `git stash`, `git branch`, `git checkout`, `git reset`, or `git add` on the repo.
2. **DO NOT** modify `/opt/sglang/**` (read-only).
3. **DO NOT** modify `/data/l3/**`, `/data/models/**`, or `/var/log/**`.
4. **DO NOT** delete scratch trees under `/tmp/opencode/*-src*`.
5. **DO NOT** run GPU workloads, bind ports, or start servers.
6. **DO NOT** execute the merge plan steps above — this report is analysis + patch export only.
7. **DO NOT** apply the patches to the repo working tree.

### Recommended Direction

1. **Apply [A] first** — commit the 14 files that are already at frozen bytes. This is the lowest-risk step and records the current worktree state.
2. **Apply [B] second** — use the exported patch to bring in the 9 frozen-only files (Qwen3.5/GGUF/Option-C). Review the Option-C relocation feature carefully before applying.
3. **Apply [C] third** — adopt frozen bytes for the 2 divergent files (extent_file_backend.py + test). The worktree is regressed and must be replaced.
4. **Merge [3090-24g-hicache] last** — after all source patches are applied and committed, merge the hicache branch. The merge is clean (3 docs-only commits).
5. **Do NOT push `a207b567fe` (UNREVIEWED telemetry snapshot) to any production/archive branch.** This commit is on the GitHub default branch and will be fetched by any fresh clone.

## 7. Would a Fresh Clone Equal Production?

**No, a fresh clone of `3090-24g-opt` @ ad749d6f28 would NOT equal production.**

After applying all patches and merging, the following would still differ:

| Directory/File | In Frozen (Production) | In Repo | Reason |
|---------------|----------------------|---------|--------|
| `launcher/` | Present | Absent | Production has launcher scripts not in the repo |
| `manifest/` | Present | Absent | Production has deployment manifest files |
| `env` | Symlink -> `/home/ubuntu/venvs/sglang-3090` | Absent | Production has a venv symlink |
| `tools/` | Present | Present (different content) | Production tools may differ from repo tools |
| `3090-dev/` | Present | Present | Both have this directory |
| `3rdparty/` | Present | Present | Both have this directory |

The expected differences are: **launcher/**, **manifest/**, **env** (symlink), and potentially **tools/** content. These are deployment artifacts not meant to be in the source repo.

## 8. Confirmation

- [x] **No git writes**: No commit, merge, push, rebase, stash, branch create/delete, checkout, reset, or add performed.
- [x] **No worktree modification**: All 8 modified files + 66 untracked entries remain byte-identical.
- [x] **No /opt modification**: /opt/sglang/** was read-only throughout.
- [x] **No /data or /var/log modification**: These paths were not accessed.
- [x] **No GPU lock, server, or port binding**: CPU-only operation.
- [x] **No scratch tree deletion**: All `/tmp/opencode/*-src*` trees preserved.
- [x] **All writes under /tmp/opencode/reconcile-20260917/**: Patches, hashes, summaries, and report are in the output directory.
