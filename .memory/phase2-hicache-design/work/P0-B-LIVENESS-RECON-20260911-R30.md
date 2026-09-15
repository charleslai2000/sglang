status: done

artifacts:
- Read-only scout assessment supplied by `ses-p0b-recon-r30-20260911`.
- Reviewed source/test surfaces: scheduler, HiCache restore, UnifiedRadixCache,
  registered HOST_ALLOC tests, mem-pool host tests, and HOST_ALLOC review gates.

evidence:
- Governing hard gate:
  `not allocable -> park -> real allocability change -> wake -> successful restore`.
- Existing code covers terminal mapping, cleanup snapshot/generation capture,
  FIFO generation gating, permissive HOST_ALLOC wake, full-span alloc/evict/alloc,
  per-pool generation state, and bounded telemetry.
- Registered tests cover unlock/direct-free opportunities, no-change/no-spin,
  FIFO rotation, auxiliary-generation requirements, cleanup, telemetry, and
  mutation bumps; dependency-free tests cover terminal parking/wake semantics.
- No live post-fix 3060 evidence currently demonstrates the complete chain.
- Existing registered tests were not executed locally because dependencies are
  unavailable (`pytest`, `orjson`, `torch`).

summary:
- P0-B remains unverified. The minimum next experiment is a fresh authorized
  3060 run that creates a positive 54,976-token KV+Mamba hit under insufficient
  host capacity, observes terminal parking and cleanup, performs one real
  allocability change, verifies one FIFO full-span retry, and verifies complete
  KV+Mamba restore to READY without crop, genuine miss, same-generation wake,
  or repeated retry.
- R30's statement that P0-A is disputed is superseded for control purposes by
  the later independent R29 verification of R28; this report did not inspect
  that later evidence package.

followups:
- Dispatch a fresh background tester/devops execution against the authorized
  3060 experiment for the complete liveness chain.
- Obtain an independent review of whether existing authority documents permit
  this verification-only experiment without changing architecture or product
  code.

open_issues:
- No live 3060 liveness trace yet.
- Architecture/Pattern Intake/Novel Mechanism documents remain governance
  context and must not be silently treated as implementation authorization.
