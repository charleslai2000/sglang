# Step 1 — clean reconciliation reconnaissance (read-only, no git writes)

## Identity
* Repo: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`
* **Production branch tip (`origin/3090-24g-hicache`): `560f9ad5256ad95b8075f474a679918340fcca47`**
  ("Merge branch '3090-24g-opt' into 3090-24g-hicache", 2026-09-16 04:14:17 +0800)
* Dirty workspace HEAD: `ad749d6f28` (75 entries) — **untouched, not to be used**
* Local branch `3090-24g-hicache` does NOT exist (only `origin/` ref); worktree is the single dirty one.
* Frozen artifact: `/opt/sglang/local-prod-v1.1.2-candidate`
  * `manifest/TREE-SHA256.txt` = `cf32a4292b13c40b53ea0dfb12dd426526abdcc4c3b8911460edc5030b2344e5`
  * `launcher/launch.sh` = `6e57bc57c4b5576434e61e5e201602592786f7b73b58db3228d07ec8a5756ba4`

## Delta inventory: frozen v1.1.2 src (9,070 files) vs `origin/3090-24g-hicache` (9,038 files)
**69 deltas** = 36 doc/memory + 33 code/test. (3 files in base but not frozen src: the 3090-dev 22151 docs.)

### CRITICAL FINDING — the native/GIL-free write path is NOT in frozen v1.1.2
`SGLANG_L3_NATIVE_WRITE_PATH` appears in **ZERO** files of every deployed tree:
```
local-prod-v1            native_env_files=0  cadence_files=0
local-prod-v1.1-candidate native_env_files=0  cadence_files=0
local-prod-v1.1.2-candidate native_env_files=0  cadence_files=0
launcher (v1.1.2): no NATIVE/CADENCE reference
```
It exists ONLY in the /tmp overlays: `/tmp/opencode/l3-native-src-20260916/` and
`/tmp/opencode/l3-native-ab-inst-20260916/` (the exact overlay the Gate B PASS was measured on;
its `extent_file_backend.py` differs from the hicache base by **645 lines**).

=> **Gate B's PASS was measured on a tree that was never frozen.** The frozen v1.1.2 candidate does NOT
contain the native write path that produced the 128K 8.9ms->0.124ms result. Step 2's category **B
(native/GIL-free L3 write path)** therefore has **no source in the frozen artifact** — it must come from the
Gate-B overlay tree, and would need review + its own freeze before it can be part of a production candidate.

### Code/test deltas (33) by likely category
* **C — F1 Option-C relocation**: `storage/extent/extent_allocator.py`, `storage/extent/extent_file_backend.py`,
  `test/.../test_extent_file_backend_unit.py`
* **A — WAL/checkpoint correctness**: the `extent_file_backend.py` WAL hunks (same file as C; must be split
  by hunk, not by file)
* **GGUF/Qwen3.8 (category X unless proven a generic dependency)**: `layers/quantization/gguf.py`,
  `model_loader/{gguf_name_maps,loader,weight_utils}.py`, `utils/hf_transformers/gguf_native.py`,
  `configs/qwen3_5.py`, `models/qwen3_5.py`, `models/qwen3_5_text.py` (sizes 5-121 diff lines)
* **M1-HF / HiCache / telemetry**: `environ.py` (1), `scheduler.py` (112), `schedule_batch.py` (24),
  `io_struct.py` (3), `hiradix_cache.py` (9), `metrics_collector.py` (78),
  `managers/detokenizer_manager.py`, `managers/multi_tokenizer_mixin.py`,
  `scheduler_components/{output_streamer,batch_result_processor}.py`, `tokenizer_manager.py`,
  `mem_cache/unified_radix_cache.py`, `mem_cache/hybrid_cache/hybrid_cache_controller.py`,
  `observability/hicache_telemetry.py` + 4 unit tests, `.dockerignore`, `.clang-format`,
  `sgl-model-gateway/LICENSE`, `_version.py`
* NOTE: several of these are **P0-telemetry** work that also appears in the UNREVIEWED `a207b567fe`.
  Category assignment must be evidence-based, not "it exists in the dirty tree".

### D — gate harness (currently NOT in git at all)
8 scripts live only under `/var/log/sglang/local-prod-v1.1/phase9-gates-final-20260916/`:
`gate_common.py`, `gate_a_content_integrity.py`, `gate_a_f1_cold_l1.py`, `f2_restart_recovery.py`,
`wal_forensics.py`, `prompt_builder.py`, `test_gate_helpers.py`, `lock_probe.py` (+ `README.md`).

## Open decision for the owner
Step 2 asks to classify **B (native/GIL-free L3 write path)** into the M1 production branch. Evidence says
that code is **only in /tmp overlays** and its own freeze/review status is unproven. Options:
1. Reconstruct A + C only (+ D harness, + E docs) from the frozen artifact now; treat B as a **separate
   reviewed follow-up** (it needs the Gate-B overlay bytes imported, reviewed, and frozen).
2. Include B by importing the Gate-B overlay bytes, accepting that this expands the review scope to a
   645-line extent_file_backend difference that no reviewer has yet covered as production code.
Recommendation: **Option 1** — it keeps the reconciliation to bytes that already have a reviewed/frozen
identity, and prevents silently promoting an unfrozen 645-line diff into the production branch.
