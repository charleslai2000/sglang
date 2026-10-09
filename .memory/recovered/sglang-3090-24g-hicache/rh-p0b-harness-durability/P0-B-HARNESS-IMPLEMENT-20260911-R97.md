status: done

artifacts:
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/R97-harness/p0b_driver.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/R97-harness/p0b_reducer.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/R97-harness/test_reducer.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/R97-harness/run_selftests.sh`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/R97-harness/README.md`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/R97-harness/manifest.sha256`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/P0-B-HARNESS-IMPLEMENT-20260911-R97.md`

evidence:
- No R94 package was present at the canonical path; R89 was rejected by R90 and
  was not reused.
- The replacement reducer accepts only exact product event envelopes for
  `p0_durable.v3`, `host_alloc.v1`, and `rh_ready_host.v1`; rejects synthetic or
  caller-summary input; binds immutable raw/source SHA256 maps, runtime PID /
  worker, SM86 profile, capture completeness, and event `file:line` provenance.
- The oracle derives complete positive KV+sidecar hit, HOST_ALLOC park,
  contiguous per-blocked-pool generation edges, FIFO predecessor ordering,
  attempt-origin/retry lineage, accepted all-or-nothing finalization, and
  accepted `rh_ready_host.v1` ordering. Missing evidence is NOT_VERIFIED;
  malformed/contradictory/forged input is INVALID_INPUT.
- The public driver is RTX 3060-only, rejects holder/target RID prefix
  collisions, enforces a 600-second and six-request maximum, uses the exact
  build -> holder -> target -> Gate A -> one `/abort_request` state machine,
  and sends `{"rid":"<holder-rid>","abort_all":false}` only after Gate A.
  Endpoint failures are BLOCKED with the explicit transport/infrastructure
  reason; inability to create Gate A is NOT_VERIFIED.
- Targeted deterministic self-tests: 17 passed, including the positive raw
  chain and missing identity/generation/FIFO/attempt/finalization/READY/
  provenance cases, summary forgery, synthetic schema, contradictory identity,
  target/bound checks, unavailable endpoint, holder payload, and prefix guard.
- Python `py_compile` passed for all three Python files; SHA256 manifest check
  passed for all five package source/executable entries; no `__pycache__`
  residue remains after checks.
- No-bytecode AST syntax check passed for `p0b_driver.py`, `p0b_reducer.py`,
  and `test_reducer.py`.
- Separate `ls -la` listing and full readback of all six package files completed.
- Final six-file sizes and hashes:
  - `p0b_driver.py` (8447 bytes): `ffe2afd6c3300f6aca68565b95cfbc667f880d2bd4c78a778122801f6f6121e3`
  - `p0b_reducer.py` (21426 bytes): `faa4280b6fab1bb63d4a503f30c365b7fe12aad46c5ad5be7bdfb86d43bd3a51`
  - `test_reducer.py` (15826 bytes): `8fe849f79401b4bc6388325b73408869ade1aa207bd830bc0cdb52da5ea9a0d8`
  - `run_selftests.sh` (320 bytes): `79f1daaea6f76d8e5f5b65a9b40639ecb9160795b759bbf49d63548e1bba1abd`
  - `README.md` (3363 bytes): `7e827a6496bcbfdf457521285500da8b597e712b151daf303ea4746a8e9e5428`
  - `manifest.sha256` (402 bytes): `0da705f9ae885fcf9e59a23bd04d9aac5255405ae218e9b7530b72cee44257f9`
- No remote execution, live server access, event simulation in the driver,
  product/test/gate/storage/Git changes, or dependency installation occurred.

summary:
- R97 strict replacement package delivered with durable canonical persistence.
- P0-B remains NOT_VERIFIED; this package contains no live evidence and must be
  independently reviewed before any transfer or execution.

followups:
- A later execution must provide a real immutable raw bundle and manifest from
  the authorized disposable 3060 only; no product instrumentation is allowed.

open_issues:
- No live P0-B evidence; P0-B remains NOT_VERIFIED.
- `ruff`, `mypy`, `pyright`, and `black` were not installed in the environment;
  formatting/typecheck commands were unavailable. Compile/self-tests and
  manifest verification are the available implementation evidence.
