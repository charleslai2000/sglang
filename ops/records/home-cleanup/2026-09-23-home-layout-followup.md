# HOME layout follow-up — 2026-09-23

## Removed from HOME

- `SGLANG-ENV.md` and `SGLANG-TASK-BRIEF.md` moved verbatim into this directory as dated historical snapshots. They describe 2026-09-16 state and are not current operational authority. `ops/records/O003-swift-canonical-service-and-opt-cleanup.md` records current Swift service state.
- Both `SGLANG-TASK-BRIEF.md.bak-*` backups removed after diff inspection: they are earlier conflicting versions of the retained task brief, adding stale model-completeness, disk-capacity, and tokenizer-decision statements.
- `models.json.pre-unification-20260922-042426` removed as an old pre-unification snapshot; it was not used as a current manifest. No `models.json` at the repo root exists; canonical service/model config is maintained in deploy conf and service unit.
- `build-iq3s/` (124 KiB, 12 files) copied byte-for-byte into `ninfer-v100-iq3_s/.memory/agents/build-iq3s-20260923/`, verified by per-file SHA256, then removed from HOME.
- `c64r-artifacts/` (93 MiB, 238 files) copied byte-for-byte into `experiments/E001-c64r-deterministic-l3-restart/evidence/c64r-artifacts-20260923/`, verified by per-file SHA256, then removed from HOME. Retained as incomplete/negative-run evidence, not a PASS artifact.
- `/home/ubuntu/models/qwen35-9b-gptq-int4` moved to `/data/models/qwen35-9b-gptq-int4`. Its model payload is 7,670,240,000 bytes and SHA256 `a81fb938ed15819c7e76453fa3e599fa4dee84af75972d3f2aca6b65b11cefaa`; no matching same-name directory was present under `/data/models`. It is a distinct Qwen3.5 text-only GPTQ artifact, not a duplicate of the Qwen3.5 W4A16, Swift GGUF, or OmniCoder models. Current Swift service does not use it.

## Source checkouts relocated

- CUTLASS moved from `fc-src/cutlass` to `workspaces/3rdparty/cutlass-v4.4.2`; the same Git checkout, nested untracked `fmt/` content, and revision were preserved. Experiment record `ninfer-v100-swift/experiments/E002-ninfer-iq3s-hybrid/results.md` now points to the relocated path. `git status` still reports untracked `fmt/`; do not discard it.
- The other `fc-src` checkouts (flashinfer, flashmla, fmt, sgl-attn, triton) moved intact to sibling directories under `workspaces/3rdparty/`. No source was deleted. FlashMLA retains one pre-existing local modification at `csrc/kerutils/include/kerutils/device/common.h`; CUTLASS retains untracked nested `fmt/`.
- No verified consumers in this workspace referenced these checkouts by their former absolute `fc-src` path; the one CUTLASS experiment note was updated.

## State after move

- Swift service remains active; `GET http://127.0.0.1:30000/health` returned HTTP 200 after the model move. The service uses `/data/models/swift-qwen38-27b-q3_k_m`, not the moved GPTQ model.
- HOME size fell from ~49 GiB at the prior layout checkpoint to ~42 GiB; root filesystem remained on the same `/dev/sda1` (about 420 GiB used / 64 GiB free). The artifacts copied under `workspaces/3rdparty` remain on that same filesystem, so their relocation is organizational, not space reclamation.
- Canonical SGLang branch `3090-24g-opt` remains clean except for this new operational record and the archived evidence files/records (untracked until integrated). No runtime source changes were made.
