# F1-R5 report — 2026-10-09

## Result: BLOCKED before pressure; lifecycle and performance NOT_RUN

R5 was intended to establish a fixed-token target’s L1→L2→L1 FULL+MAMBA path under bounded competitors. The isolated service started on loopback `127.0.0.1:30127`, loaded the pinned Falcon-H1-7B-Instruct-GPTQ-Int4 revision, and completed target insertion/revisit. The prepared driver then deliberately stopped before pressure because it could not find a target-correlated T38C `build_complete` identity/hash. No pressure competitors, cold-residency test, target restore, Extent operation, or performance measurement ran.

### Evidence

- Run directory: `control/falcon-h1-3090-hicache-perf/runs/R5-20261009T1040Z/`.
- `driver.log`: same 1,920 token IDs (`sha256=21b2e701953444c9dcb30dd3a8b66719638187fbd36b0d3fcbf31760feda2da6`) inserted under target session; repeat served 1,792 tokens from device. It recorded aggregate backup counters of 1,792 KV tokens and one MAMBA state, host-used 1,792 tokens, but then failed closed at the intended target identity guard (`no target-correlated build_complete node/hash; stop before pressure`).
- `t38c-probe.jsonl`: only one `backup_host_commit` row, with `node_id=26`, empty `final_kv_hash`, and no session/build/request identity. Thus aggregate KV/MAMBA counters cannot bind this backup to the target’s full identity or establish a usable target-correlated lifecycle trace.
- Startup pool metrics reported device FULL capacity 163,270 tokens, host FULL capacity 326,541 tokens, and 91 usable host MAMBA states. These are configuration facts, not evidence of target eviction/recovery.
- The service was terminated after the guard failure; port 30127 closed and GPU returned to 1 MiB / 0% utilization. The initial launch failure (missing run-local Prometheus directory) and its log are retained.

### Status

- Target FULL+MAMBA L1→L2 commit with target-bound identity: **BLOCKED / NOT_PROVEN**.
- Target device eviction, L2→L1 restoration, and greedy-output comparison after restoration: **NOT_RUN**.
- Extent L3 write/read and L3→L2→L1 lifecycle: **NOT_RUN**.
- GPU-only / GPU+Host / GPU+Host+Extent concurrency benchmark and profiler: **NOT_RUN**.

### Follow-up

Before another GPU run, diagnose why the runtime trace emitted a durable `backup_host_commit` but omitted the target’s final hash/session/build identity and why the expected `build_complete` was absent. Reuse the retained run evidence and inspect trace-context creation/insertion ordering; do not weaken the driver guard or substitute global counters for node identity. Any retry needs a new independent run directory and separate authorization/availability check for the shared GPU.
