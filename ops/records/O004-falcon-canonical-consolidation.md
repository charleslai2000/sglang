# O004 — Falcon canonical consolidation and three-model runtime

Date: 2026-09-23

## Integration decisions

- Falcon fork HEAD was `1d0b7977816ff7f135fe338aed9715b62ff7548d`; it contained 10 non-ancestor commits relative to canonical at review, including old HiCache merge history. Canonical already contained the effective GGUF/IQ3 source state; the early `7b05ad65c1` reasoning-effort implementation was superseded by canonical code. Shared HiCache merge commits and copied records were not replayed as Falcon-specific changes.
- Cherry-picked Falcon runtime fix `b0bd1d96fc` as canonical commit `2d74d9a5828e28663f50c586227b1696c5c902c6`: preserve mixed BF16 attention/GPTQ FFN topology and safe Falcon-H1 prefill graph policy. Added two focused test files. Both tests pass (3 passed).
- The Falcon branch also contains valuable completed phase1/2/3 and G004 control reports. Reports/tasks only were migrated to `control/falcon-archive/{G001-phase1,G002-phase2a,G003-phase2b,G004-decode}/`; profiler captures, SQLite/NSYS/NCU outputs, run JSON/logs, `.memory`, and untracked scratch tools/scripts were excluded. All Falcon model-specific sources/tests are now canonical; shared runtime/evidence unchanged.

## Runtime closure (RTX 3090, same canonical checkout/venv)

- Canonical: `/home/ubuntu/workspaces/3rdparty/sglang`, branch `3090-24g-opt`; all three used `/home/ubuntu/venvs/sglang-3090/bin/python` and `PYTHONPATH=/home/ubuntu/workspaces/3rdparty/sglang/python`, CUDA UUID `GPU-2e3ed202-3655-d919-0a64-259209bc6587`, sequentially on port 30000.
- Swift Q3_K_M: existing served model `ukisai/Swift-Qwen3.8-27b`; health 200 and HTTP completion returned exact `SWIFT-D2`; same model/profile as previous verified service.
- Falcon: `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`, GPTQ-Marlin selected at runtime, Mamba `extra_buffer`, prefill graph disabled, decode full. Health 200; completion returned `Hello! How can I assist you today?`. Effective startup cap: `max_running_requests` was automatically reduced from requested 16 to 8 by Mamba state cache; decode graph captured [1,2,4,8]. Do not claim B=16 launch coverage.
- IQ3_S: `/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`, SHA256 `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810`; max total tokens 16384, FP8 KV, FlashInfer, Triton linear-attention, Mamba extra_buffer/float32, decode graph max bs 8, prefill graph disabled. Health 200; HTTP completion returned exact `IQ3S-D2`.
- After sequential smokes, Swift systemd service was restored and health returned 200. All actual model imports came from canonical source; there were no per-model source clones.

## D1 cleanup and directory convergence

- Removed legacy frozen source trees, M3/M4 envelopes and stale executable deployment/freeze/service/gate tools that referenced them. Historical control/audit references remain unchanged.
- Falcon archive tag was placed on source branch HEAD before deleting branch/worktree/directory.
- Final host cleanup removes obsolete empty checkout shells. Preserve other repositories, models, and unrelated workloads.
