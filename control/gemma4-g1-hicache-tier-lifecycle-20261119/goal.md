# Gemma4 HiCache tier-lifecycle qualification

## Goal
Qualify Gemma4 E4B W4A16 + E5M2-KV HiCache using the hash-pinned deterministic twelve-request radix tree: shared 16K root, two disjoint 16K branches and twelve disjoint 32K leaves (six leaves per branch). Preserve 64K input + 256 output capability and the owner-authorized pressure configuration `--max-total-tokens=139264`, decimal HiCache 8 GB, and a fresh 32 GiB L3 Extent. This pressure run is not the production C32 throughput result. Acceptance also requires write-through Full and SWA Host capacities to exceed their respective Device pools and leave L3 restore staging room. Obtain request-correlated proof for L1→L2 and L2→L3, branch-exclusive and mixed-tier restore followed by Decode, Radix sharing/splitting, and Frontier capacity wake/retry followed by Decode. Keep production `sanity_check()` enabled; report pressure and production-throughput configurations/results separately.

## Scope
- Use only the authorized `sglang-hicache` worktree, existing Gemma4 model/AOT/overlay assets, and `/data/sglang-hicache` output area. Preserve unrelated dirty/untracked work.
- Fixture shape is 12 × 65,536 prompt tokens and 442,368 unique tree tokens (432 Ki tokens); preserve the original eight requests and two-branch tree while adding four deterministic leaves. Pinned SHA256: `ac06790a415e772880dac9cb0415d09cc1bdc04142652733d1314f583f841a8b`.
- Acquire `/tmp/f1-r16b-gpu-exclusive.lock`; freshly check service/ports, GPU, processes, disk and memory before workloads. Use bounded background execution and durable artifacts; no agent-side wait/poll/sleep loops.
- A restore pass requires RID, cached-token source, physical transfer/persistence evidence, accepted-ready/lifecycle evidence, and successful 256-token output/Decode. Writes, occupancy, or configuration alone do not prove restore.
- Do not weaken invariants or suppress production sanity. Commit/push only related reviewed and verified changes.

## Authorized pressure configuration and current status
The owner authorized a separate pressure setup at `max-total=139264`, E5M2, decimal HiCache 8 GB, and a fresh 32 GiB Extent. A no-generation startup probe measured GPU Full/SWA capacities 139,264/111,411 tokens and Host Full/SWA capacities 186,012/148,810, with no HiCache pool warnings. Artifact: `/data/sglang-hicache/gemma4/runs/20261120T-g1-capacity-139264-hicache8-extent32-20261119T204751Z/`. This establishes the startup capacity relation only; it does not prove any restore or lifecycle gate.

The earlier 172032/4-GB setup is a distinct diagnostic: Host Full/SWA 93,007/74,405 were below Device Full/SWA 172,032/137,625. It is not the authorized pressure target. The 172032/8-GB startup-only probe measured Host Full/SWA 186,013/148,810 and is also distinct. Overall acceptance remains NO-GO until all source, lifecycle, Decode, production-performance and cleanup gates are demonstrated.

## Completion
The hash-pinned tree and actual capacities are recorded; Radix structure, each required tier restore→Decode, Frontier wake/retry→Decode, production throughput/correctness, final full-idle sanity and cleanup are either demonstrated or explicitly failed/unproven. Any missing required gate means NO-GO. A concrete defect is minimally fixed and regression-tested. Only relevant verified work is committed/pushed and the resulting SHA/remote state recorded.