# Falcon service evidence reference

- Full service identity, configuration, all three c8/c32 rounds, hashes, and comparability limitations: `control/falcon-rtx3090-t005/runs/T005-FALCON-UNLOCKED-SERVICE-20261025.md`.
- Raw artifacts remain outside Git at `/data/sglang-hicache/falcon-unlocked-20261025/runs/20261025T094033Z/` (1.7 MiB); do not copy raw logs into the repo.
- Revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`; c8 `448.868 ± 13.415`, c32 `777.280 ± 0.926` output tok/s (mean ± sample SD; 3 waves); actual server cap=16 due Mamba state cache.
- Historical T005 comparison is approximate, not a controlled Stock/Unlocked Falcon A/B. GPU unlock GEMM evidence is distinct and does not establish Falcon causal speedup.
