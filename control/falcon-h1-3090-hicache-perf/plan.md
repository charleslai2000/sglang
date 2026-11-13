# Falcon-H1 RTX 3090 HiCache performance plan

Last updated 2026-10-10 during R8.

## Current state

- Retained fixes: Falcon GPTQ/graph policy `601158469`; HiCache CPU/Extent coverage `fd93a2ec2`; marker-gated radix hash `e80f144dd`; trace session contract tests `481f2b485`.
- R7B `detach_not_sealed` was logged on build registration before D→H ACK or eviction. It is a provisional barrier-attempt diagnostic, not evidence of data loss. Source tracing shows the exact decision: no detach manifest registered yet. Later R7B pressure detached/freed target FULL and MAMBA device slots; it also legitimately evicted/freed target MAMBA Host slot (`EvictLayer.HOST`), while target FULL/KV Host had no detach. Thus complete FULL+MAMBA Host co-residency was not retained after broad pressure.
- R7B aggregate Host occupancy (162,379/326,541) did not describe MAMBA capacity. R7C pool-specific evidence: 45 device MAMBA slots, 91 usable Host MAMBA slots, separate from 326,541 KV host token capacity.
- R7C exact target D→H ACK PASS, operation 0, node 26/hash `721e82b9…eafe09c`, FULL+MAMBA commit, synchronized ACK and 1,792 KV Host tokens. Exact-prefix Host restore reports 1,792 Host tokens and greedy `[10553]`, equal to the reference. Target FULL device (1,791 slots) and MAMBA device (1 slot) detach and allocator frees are evidenced. R7C pressure reached detach at competitor 48; Host source/restore is proven but that run did not stop promptly at first observed detach. R8 has a corrected, MAMBA-capacity-aware early-stop driver.
- R8 L3 server is currently running with ExtentFileBackend at unique `runs/R8-20261010T0400Z/extent` (64 MiB extents, 4 GiB file/max, 10 GiB min-free). No L3 target write/read evidence yet.

## Gates

- R7B exact target operation/ACK: **PASS**.
- R7C target FULL+MAMBA Device detach → Host-source H→D restore → greedy equality: **PASS**.
- R8 capacity-bounded L2 re-run: **NOT_RUN** (corrected driver prepared).
- FULL+MAMBA Extent write, eviction, Storage restore, failure/cancel lifecycle: **NOT_RUN**.
- GPU-only / GPU+Host / GPU+Host+Extent matched concurrency and profiling: **NOT_RUN**.

## Next action

Finish R8 L3 target lifecycle using explicit target chain persistence, then device/Host eviction and exact target Storage read/restore; capture Extent `batch_set_v2`/`batch_get_v2`, component-sidecar writes, allocator frees and kernel I/O separately. Do not proceed to three-tier benchmarking until correctness/failure gates pass. Rerun R8 L2 with early stop at the first observed target device detaches and an independent MAMBA usable-slot metric.
