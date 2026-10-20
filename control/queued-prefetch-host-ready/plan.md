# Current plan

## Established
- Current checkout is `3090-24g-hicache` at `592a9ef996d8efc4a06cf64ce9079e34b1003637`, tracking `origin/3090-24g-hicache` at the same SHA before integration. Extensive dirty/untracked Runtime, tests, reports and control evidence pre-exist; preserve all except narrowly authorized, individually reviewed T004 deliverables.
- Owner ruling waives same-target Host release/refill as a completion gate; do not revisit accepted lock-window or three mechanism-pair qualification. Queue Prefetch OFF disables queue-stage prefetch only and retains normal demand restore and Ready Horizon.
- **T004-L0FIX7 is one valid matched fixture ON/OFF L0 pair**, frozen in `runs/T004-FALCON-20261016/T004-L0-ONOFF-FIXTURE-20261020.md`. Both arms use the same 2,048-token A/B/C/D fixture and one-token measured suffix, Falcon revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`, token-ID file SHA256 `db08701160022b6e616d482fb0d811f7257ccb547c0b29774d5e54aff69fd87f`, and 8-running/8-queued/32,768-token capacity. Separate Extents qualified all four measured RIDs per arm at 2,048 FULL KV + 2,048 MAMBA L3 pages.
- Frozen per-RID ledger: ON B/C/D share Prefill batch-3, Wall/Kernel Busy Union 381.93/136.88 ms. OFF B batch-1 949.13/22.21 ms; C/D share batch-2 297.16/89.25 ms. A has 1,023 Decode steps: ON 5,306.09/2,713.16 ms, OFF 5,190.40/2,774.41 ms. Each RID Direct KV bytes 92,274,688; read-call service-derived range 0.858–2.731 GB/s (instrumented logical O_DIRECT service, not media bandwidth). A output 1,024 tokens; B/C/D each output one token. This is one pair and the Prefill batch structures differ; **no net performance benefit is established**.
- Report constraints: Kernel Busy Union is not GPU-exclusive active time or stall. Independent Host-ready timestamps are absent; H2D→dependent-kernel wait is NOT_VERIFIED; batch-level H2D is not divided across RIDs. Physical-media attribution is unavailable. Full long-sequence/multi-round logits and FULL+MAMBA state contract is not frozen or accepted. Queue Prefetch is not production ACCEPTED and T004 is not DONE.
- Run artifacts/manifests and Nsight report/SQLite hashes are recorded in the report. GPU workload used `/tmp/f1-r16b-gpu-exclusive.lock`; no further GPU operation was performed in this continuation.

## Remaining
- Secure/freeze an authorized, same-revision Falcon-H1-7B GPTQ no-cache reference, token fixture, and explicit tolerance; then execute long greedy/multi-round logits and FULL KV+MAMBA-state comparison without changing tolerance. Do not call one-token smoke acceptance.
- Continue only the performance repetitions/long-output workload required by the active Task after ensuring matched batch/workload conditions. Existing three mechanism pairs and L0FIX7 are not evidence for a net benefit. Keep all non-identifiable GPU wait and physical-media claims explicitly NOT_VERIFIED.
- Complete relevant CPU regressions and ownership review. This session's attempted focused pytest collection failed before tests because the active environment's `sgl_kernel` does not export `fp8_scaled_mm`; the prior `/tmp` matching overlays are no longer present. Do not report the current rerun as passing or alter/build/copy kernels merely to mask the environment mismatch.
- Selectively stage, inspect staged diff, commit and push only the independently reviewed T004 fixture, report, and proven-owned runner/driver changes. Do not include broad shared Runtime patches or any unrelated dirty files. Verify pushed SHA and enumerate remaining dirty/untracked status. Keep T004 ACTIVE and Queue Prefetch unaccepted.

## Validation in this continuation
- `python3 -m py_compile` passed for `driver.py`, `run_nsys_timeline.py`, `analyze_seed_gpu_join.py`, and `collect_fpm_timeline.py`.
- `git diff --check` passed.
- Current focused pytest attempt: **collection failed (4 modules)** with `ImportError: cannot import name 'fp8_scaled_mm' from 'sgl_kernel'`; system Python lacks pytest. No test assertion ran in the current environment.
- No source commit or push has been performed in this continuation; no unreviewed dirty content was staged.
