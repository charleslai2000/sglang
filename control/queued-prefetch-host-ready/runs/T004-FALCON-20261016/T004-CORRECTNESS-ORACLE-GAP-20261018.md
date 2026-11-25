# T004 Falcon numerical correctness oracle check (2026-10-18)

## Conclusion
The required frozen long greedy / multi-round / logits / FULL+MAMBA-state acceptance cannot be run responsibly from the artifacts currently present: no Falcon-specific frozen multi-round input/output/logits oracle or tolerance contract was found. The existing `[10553]` T003 target is a one-token smoke and is not a substitute. No GPU workload was launched for this missing-contract check.

## Evidence inspected
- `control/queued-prefetch-host-ready/runs/T004-FALCON-20261016/T004-NEXT-EXPERIMENT-PROTOCOL-20261018.md` explicitly distinguishes the one-token T003 sentinel from long numerical acceptance and records no Falcon oracle/tolerance.
- `control/falcon-h1-3090-hicache-perf/runs/T003-L2-20261014T1700Z/l2_driver.py` establishes only one greedy token `[10553]` before/after Host restore.
- `control/falcon-h1-3090-hicache-perf/runs/T003-L3R-20261015T0900Z/RESULTS.md` (previously recorded cold Storage restore) also establishes the same one-token output, synchronized H2D and Storage-source path, not multi-round logits or MAMBA state equivalence.
- Repo model test `test/manual/models/test_falcon_h1_models.py` targets different Falcon-H1 0.5B/1.5B models and GSM8K quality; it is not the frozen 7B GPTQ oracle.
- T004 request/SSE artifacts preserve output token IDs for bounded benchmark requests, but have no matched no-cache/cache-sidecar reference logits and no frozen tolerance.
- Cross-family R-HBA1 numerical material is Qwen-specific and cannot define Falcon acceptance.

## Execution and environment check
RTX3090 was idle (1 MiB, 0%); the designated flock was available, but it was deliberately not acquired because there is no valid correctness acceptance contract to execute. No server, profiler, or GPU workload was started. CPU-only targeted tests were attempted using the project venv and repository test paths; collection is currently blocked by missing `sgl_kernel.fp8_scaled_mm`. The previously recorded `/tmp/t002-sm86-overlay-root` no longer exists. Existing sibling build trees contain only partial `common_ops` extensions and do not provide the missing symbol; none were copied, modified, or built. The failures are preserved as environment evidence, not treated as passed tests.

## Next valid action
Obtain or identify the authoritative Falcon 7B GPTQ frozen multi-round token/logit/MAMBA-state oracle and its exact tolerance/configuration. Until then, keep full numerical/state acceptance explicitly NOT_VERIFIED; continue independent non-GPU source/ownership and control reconciliation without weakening criteria or inventing a tolerance.
