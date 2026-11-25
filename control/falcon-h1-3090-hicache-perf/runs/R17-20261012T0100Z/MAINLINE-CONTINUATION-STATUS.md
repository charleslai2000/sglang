# Mainline continuation — 2026-10-11

## Identity and scope

- Only authorized tree/branch: `/home/ubuntu/workspaces/3rdparty/sglang-hicache`, `3090-24g-hicache`, HEAD `6f612b0301416157e48fc5e40ac01680bc212b3c`. The branch was fast-forwarded from ancestor `a5895b5d` to origin; no new branch/worktree or sibling `opt` use.
- Historical R17 measurements/assets under `provenance-20c837f1/` belong to `/tmp/sglang-r17` commit `20c837f1a3daaec47508feaecf5514dd586c636c`; never represent them as mainline.
- `target-6f612b03-dirty-current/manifest.json` is pre-fix identity-only; its tracked dirty SHA `d9339f4429e1b3021fe4b45daf4cc8c8f59d1c09733f05200e3c17e5c5f721ce` is stale after edits. Direct imports resolve runtime Python from the authorized tree. Python 3.12.3, Torch 2.13.0+cu129, CUDA runtime 12.9. Actual `sgl_kernel.sm86.common_ops` import resolved to `/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages/sgl_kernel/sm86/common_ops.cpython-312-x86_64-linux-gnu.so`, SHA256 `a0bca3a0210008c8b29aa3926b64147525ec54ce06a92153f4a2aad86b67e679`; this differs from the installed `.abi3.so` SHA `22c9f5eb...`.

## UnifiedRadix 125-failure investigation

Original full-file run: **125 failed, 1143 passed, 1164 skipped, 52 subtests passed**. It is not 125 independent semantic failures. The same process log contains CUDA OOM (11 MiB free, ~23.54 GiB in use), followed by repeated `cudaHostRegister rc=712` (`cudaErrorHostMemoryAlreadyRegistered`) on identical address/size. Repeated parameterized cases then cascade.

After fixture lifecycle/interface updates, a fresh-process full-file rerun still returned **128 failed, 1020 passed, 1163 skipped, 52 subtests passed**. It again exhibited the same OOM/host-registration issue. Therefore the UnifiedRadix file is **not PASS**, and the recurring pinned-host registration failure remains unresolved; do not classify all 128 as runtime defects or as fully repaired environment noise.

Confirmed independent causes and dispositions:
- Two prefetch tests used mocks missing `completed_tokens`, `stats_requested_tokens`, and iterable `pool_transfers`. Mocks updated; focused tests pass.
- One L3 bigram fake controller missed `storage_failure_reason`, `prefetch_speculative_rate_limited`, and modern keyword args to `prefetch()`. Contract updated; isolated case passes.
- One 4-token H2D KV-event test inherited a 2048-token promotion margin. Test now sets margin 0 and load threshold 1; isolated case passes.
- HiRadix write failure was incorrectly unwrapped as `write_result[0]` even when the allocation-failure sentinel is a 0-D tensor. Both production call sites now unwrap only actual tuples; the write-through fragment test passes.
- Mamba fake tree lacked the new optional ancestor-leaf refresh hook. Production caller now feature-checks it; fake was updated. `test_mamba_path_state_cap.py` passes.
- Two resumable-insert cases pass in the focused run, but fail later in the full file after CUDA exhaustion/mapping errors.
- 17 listed failures are parameterized variants of `test_hicache_write_back_drop_respects_pins_then_frees_subtree`, and the log shows fixture setup/registration failing before assertions. They are not established semantic regressions.
- Remaining full-suite failures have not all been individually replayed. Root-cause count across every reported item is incomplete; preserve this as a concrete unresolved test-lifecycle issue.

Focused fresh process covering operation identity, Mamba membership/path cap, unified dispatch, load-back timing, staged backup dispatch, HiRadix failure sentinel, L3 bigram, KV events, resumable insert and prefetch mocks: **57 passed, 1 skipped, 2 subtests passed**. No assertions weakened or tests manually skipped. Dirty Python modules and runner compile; `run_target_source.sh` passes `bash -n`, runner `--help` works, `git diff --check` passes.

Uncommitted runtime diff has 7 code files: operation/node ACK identity and host-slot metadata in cache controller; HiRadix legacy tensor return compatibility; Mamba/UnifiedTree ancestor leaf eligibility refresh; UnifiedRadix durable host ACK tracing. Three tracked tests accompany it. Snapshot patch SHA256: `058af768c0bc278e5de50344df0b2bd68127dba2a7f6f83b3e82dded68438d3e`. No commit/push yet; complete review remains.

## Historical R17 GPU-only reference (not mainline)

Frozen 40-request workload, 15,016 prompt tokens and 128 outputs/request; model revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`; three clean repeats per concurrency. These results remain R17-only.

| c | Request window mean ± SD | FPM event sum mean ± SD | Prefill event TPS range | Decode output TPS range | Aggregate output tok/s | E2E p50/p95/p99 | Queue mean/max | NVML window mean util/power/SM clock; max temp |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 8 | 16.379 ± 0.022 s | 16.213 ± 0.033 s | 2685–2712 | 458.05–458.82 | 312.6 | 3.250/3.286/3.292 s | 0.045/0.280 s | 93.16% / 328.54 W / 1849.6 MHz; 65°C |
| 16 | 12.997 ± 0.272 s | 12.834 ± 0.248 s | 2545–2787 | 663.16–664.32 | 394.0 | 4.760/5.117/5.121 s | 0.291/1.493 s | 87.56% / 306.08 W / 1760.4 MHz; 61°C |

Phase timing is CUDA-event `model_runner.forward/cuda_graph.replay`, not GPU union or kernel-only. FPM scheduled Prefill tokens/run: c8 13,601, c16 13,760. Saved per-request TTFT is null. Four historical filtered NCU reports (8 selected launches each, c8/c16 × prefill/decode) are replay diagnostics only; prefill set has Marlin rows but no requested CUTLASS 128x128; decode selected Marlin, Mamba conv/scan, BF16 GEMM. Do not average heterogeneous kernels or call them clean throughput.

## Current-mainline clean c8 sample

A real c8 run completed on the current dirty mainline, trial `mainline-gpu-only-c8-t2` (trial 1 directory is preserved as a failed port-probe attempt and contains identity manifest only). Trial 2 HEAD `6f612b03...`, tracked-dirty SHA `a901bf5cbc15648ab8c67b2d5220dff38d633749298abcaff2ba1e0383baf809`, model revision `52036ae...`, 40/40 requests × 128 output, same fixed workload manifest `782e1c5...`. Python runtime/worker code imports from the current tree. Scheduler PID 298396 mapped the actual `common_ops.cpython-312...so` hash `a0bca3...`; mapped JIT Marlin and Mamba artifacts also captured in `service-mapped-files.json`.

| c8 trial 2 metric | Measured |
|---|---:|
| Request window / aggregate output TPS | 16.437 s / 311.50 tok/s |
| Prefill FPM tokens / event time / event TPS | 13,601 / 5.109 s / 2662.31 tok/s |
| Decode outputs / active event time / active TPS | 5,120 / 11.191 s / 457.51 tok/s |
| FPM forward event sum / estimated unsampled remainder | 16.300 s / 0.137 s |
| Scheduler queue event samples / API queue mean | 5 / 45.85 ms |
| E2E p50/p95/p99 | 3.257 / 3.303 / 3.306 s |
| Cache reported tokens | 0 |
| NVML request-window samples / util / power / SM clock / max temp | 16 / 96.38% / 325.23 W / 1843 MHz / 58°C |
| Device memory | ~24.54 GB reported used at request-window samples (weights + runtime allocation) |

DeviceTimer remains `model_runner.forward/cuda_graph.replay` event time, not kernel-only or GPU union; `ttft_s` is null for the non-streaming request API. Scheduler queued records are event samples, not queue latency; API `queue_time_s` is the available request-level scheduler queue metric. Full raw files are in `mainline-gpu-only-c8-t2/`.

## Current-mainline GPU-only measurements

Runs use the authorized dirty mainline tree at HEAD `6f612b0301416157e48fc5e40ac01680bc212b3c`, model revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`, frozen 40-request workload, 15,016 prompt tokens and 128 requested output tokens/request. Each successful trial records a fresh tracked-dirty digest, imported-module paths/hashes, service process mappings, native DSO mappings/hashes, request outputs, scheduler FPM events, Prometheus metrics and NVML samples. The service is launched with HiCache off, Prefill CUDA graph disabled, full Decode graph, TP=1 and max running requests 16. FPM phase timings are `model_runner.forward/cuda_graph.replay` device-timer intervals, not GPU-union or kernel-only time. The request API is non-streaming, so TTFT is unavailable.

| Concurrency / trial | 40×128 success | Window | Aggregate output TPS | Prefill event TPS | Decode output TPS | API queue mean | Cache tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| c8 t2 | yes | 16.437 s | 311.50 | 2662.3 | 457.51 | 45.85 ms | 0 |
| c8 t3 | yes | 16.404 s | 312.12 | 2671.0 | 458.12 | 45.65 ms | 0 |
| c8 t4 | yes | 16.467 s | 310.92 | 2646.8 | 457.98 | 45.42 ms | 0 |
| c16 t1 | yes | 12.879 s | 397.55 | 2761.7 | 662.73 | 288.79 ms | 0 |
| c16 t2 | **incomplete / interrupted** | — | — | — | — | — | — |
| c16 t3 | yes | 12.995 s | 393.99 | 2727.3 | 662.58 | 290.14 ms | 0 |

c8 t2/t3/t4 each completed 40/40 requests; throughput mean **311.52 ± 0.60 tok/s** (sample SD). Request-window NVML: t2 96.38% / 325.23 W / 1843.1 MHz / max 58°C; t3 90.29% / 321.57 W / 1849.4 MHz / max 59°C; t4 96.81% / 326.78 W / 1845.0 MHz / max 59°C. c16 t1 and t3 each completed 40/40: 397.55 and 393.99 tok/s, mean 395.77 ± 2.52 tok/s (sample SD); request-window NVML t1 83.15% / 319.12 W / 1842.7 MHz / max 57°C, t3 86.31% / 325.37 W / 1842.7 MHz / max 57°C. c16 t2 remains incomplete and excluded. Its captured logs show only start sample (6 prefill/8 decode tokens), no scheduler on_idle invariant error or a complete py-spy dump. A separate NCU-traced c8 service produced `py-spy` stacks in the idle-pool invariant checker and later `DecodeCudaGraphRunner.execute`; the latter service spent 237.59 s in Decode graph capture under `NCU --set full`. These are distinct observations and do **not** establish c16 t2's root cause. Do not label t2 as fixed or diagnosed.

The first c8 t1 attempt is preserved as a failed port-probe run and is excluded. Successful GPU-only runs are in the tagged c8 t2/t3/t4 and c16 t1/t3 directories. All completed runs report zero cache hits; c8 t2 Prometheus explicitly shows 0 device/host/storage hits and 15,022 newly-prefilled tokens. Current-mainline HiCache L1/L2/L3 restore is therefore not established.

No NCU hardware-counter report was completed. Direct root NCU launch was restored; initial failures were ubuntu-owned lock permission, then root Git safe-directory identity. Root-owned CUDA target failed at scheduler `cudaSetDevice/cuDevicePrimaryCtxRetain`; an NCU-run service using the bypass reached service startup but full-set Decode CUDA graph capture took 237.59 s and profiling was interrupted. A further counter-focused launch attempt is preserved as failed/incomplete. Archived R17 NCU remains bound to `/tmp/sglang-r17`, not current mainline. Cache restore remains unqualified. UnifiedRadix full-file failure remains unresolved; focused tests passed. Runtime diff review, regression closure, commit and push remain incomplete.

After each interrupted/profiling attempt, service/process and port checks were performed. The latest check showed no runner, SGLang, NCU process or listener on ports 30160/30127, and RTX 3090 at 1 MiB / 0% utilization.

## Next actions

1. Diagnose the c16 t2 historical stall from its actual captured artifacts/process evidence; its root cause is unresolved and t1/t3 only provide two clean samples.
2. Establish a safe NCU invocation that profiles the ubuntu-owned CUDA worker without root-owned product startup; use a focused counter set, avoid graph-capture replay overhead, and capture c8/c16 prefill/decode with per-launch evidence.
3. Finish runtime diff review, buffer-mode return contract review, UnifiedRadix OOM/host-registration attribution and required regression shards.
4. Continue R7C/R11-derived L1/L2 Host-source H→D correctness and DMA proof; L3 read-back independently, keeping unproven layers NOT_QUALIFIED.
5. Selectively commit/push only after review and regression criteria; retain all historical and untracked assets.
