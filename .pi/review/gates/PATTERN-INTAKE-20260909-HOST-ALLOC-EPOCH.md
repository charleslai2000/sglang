# Pattern Intake — primary-host allocability epoch/wake

```yaml
schema_version: closest-existing-gate-schema-1
artifact_id: PI-HOST-ALLOC-EPOCH-20260909-01
task_id: ARCH-20260909-PATTERN-INTAKE
orchestration_epoch: 20260909-P4
role: architect
target_branch: 3060-12g-qwen35-4b
target_revision: 1e6a82194e7f5d071823e4abb68514c6d421e4b3
classification: FULL_INTAKE_REQUIRED
disposition: NOVEL_COMPOSITION_REQUIRED
architecture_contract: review/gates/ARCH-20260909-HOST-ALLOC-EPOCH.md
architecture_contract_sha256: 9bdee4894eec0a6319d390ab0e92e5c7ca8e9e2885e3a16eb594fd3626c6a058
novel_mechanism: review/gates/NOVEL-MECHANISM-20260909-HOST-ALLOC-EPOCH.md
implementation_admission: BLOCKED
decision_authority: orchestrator_and_existing_gate_owners
```

## 1. Decision and authority boundary

This intake inventories the repository evidence relevant to implementing the
primary-host allocability epoch/wake contract. It recommends the architecture
contract's generation-vector plus bounded FIFO composition, but it does not
approve that composition, implementation, or runtime behavior.

G1/G2 implementation admission is **BLOCKED**. The concrete prerequisites are:

1. The orchestrator/design authority must accept a pinned architecture
   contract and the linked Novel Mechanism declaration. The architecture
   artifact inspected here still says `PENDING_ORCHESTRATOR_ACCEPTANCE`.
2. The project contract requires a full Pattern Intake conforming to
   `storage/review/gates/pattern-intake/`. No full template or stable corpus is
   present at the pinned revision; the only local example is a narrow EXEMPT
   declaration. This dispatch authorizes writes only under `review/gates/`, so
   this closest-schema artifact cannot silently claim canonical conformance.
   The orchestrator must either (a) accept this documented closest-schema
   substitute as the governing intake, or (b) issue a fresh Task ID with the
   canonical schema/corpus and write authority for its required location.

Once both prerequisites are recorded by the proper authority, no additional
architecture prerequisite is identified by this intake. Coder, tester, and
reviewer gates remain independently required.

## 2. Scope and non-goals

In scope: the Unified HiCache path on `3060-12g-qwen35-4b`; successful host
free and lock-to-evictable mutations; read-only per-pool generation snapshots;
HOST_ALLOC wait metadata; bounded FIFO retry admission; existing full-span
allocation/reclaim; KV plus required auxiliary-pool attribution; and the
HAE-01 through HAE-15 test oracles in the architecture contract.

Out of scope: product implementation; 3090 behavior or deployment; remote
hosts; storage contents or durable formats; HiRadix; lower-frontier discovery;
arbitrary crop; public APIs; cross-process wake delivery; performance tuning;
new monitoring/auditing; and execution or acceptance of tests.

## 3. Corpus pin, search scope, and schema limitation

Repository root searched:
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`.

Pin:

- branch: `3060-12g-qwen35-4b`
- Git revision: `1e6a82194e7f5d071823e4abb68514c6d421e4b3`
- searched namespaces: `review/gates/`,
  `storage/review/gates/pattern-intake/`, `.memory/`, `python/`, `test/`, and
  all Git history reachable by `--all`
- untracked architecture inputs were pinned by SHA-256 rather than falsely
  represented as Git blobs

Exact discovery searches:

```text
rg -n -i "pattern intake|novel mechanism|corpus revision|digest|pinning|G1|G2" review/gates storage .memory
find storage/review/gates/pattern-intake -maxdepth 3 -type f -print
git ls-files review/gates storage/review/gates/pattern-intake
git log --all --oneline -- storage/review/gates/pattern-intake review/gates
git log --all --name-only --pretty=format: | rg -i 'pattern.intake|novel.mechanism'
rg -n "CausalEpochs|ready_host_release_epoch|restore_wait_capacity_fits|demand_restore|WAIT_CAPACITY|HOST_ALLOC|evict_host|dec_host_lock_ref|append_host_mem_release|_drain_release|_drain_extra_release|buffer.*FIFO|fifo" python test
find test -type f | rg -i 'restore|ready.horizon|unified|hicache|capacity|prefetch'
```

Observed results:

- No full Pattern Intake template, full stable pattern corpus, or separate
  Novel Mechanism declaration exists in the target worktree or reachable Git
  history.
- The sole pattern-intake-area artifact is
  `storage/review/gates/pattern-intake/EXEMPT-3060-RUNTIME-COMPAT.md`; it is an
  EXEMPT classification and explicitly says a full intake is not applicable
  to its maintenance scope. It cannot define the missing full schema.
- Existing `review/gates/*.md` artifacts consistently carry task identity,
  evidence, decision, risks, follow-ups, open issues, and authority limits.
  This document uses that closest available schema and adds the fields
  demanded by the project contract.
- Stable corpus IDs below are therefore intake-local IDs, not falsely claimed
  pre-existing repository authority. Their path plus pinned Git blob provides
  stable resolution for this intake revision.

## 4. Pinned inputs and corpus manifest

### 4.1 Design and diagnosis inputs

| ID | Artifact | Pin | Use |
| --- | --- | --- | --- |
| `PI-IN-001` | `review/gates/ARCH-20260909-HOST-ALLOC-EPOCH.md` | SHA-256 `9bdee4894eec0a6319d390ab0e92e5c7ca8e9e2885e3a16eb594fd3626c6a058` | Normative proposed interfaces, invariants, migration, HAE-01..15. |
| `PI-IN-002` | `.memory/phase2-hicache-design/work/ARCH-20260909-HOST-ALLOC-EPOCH.md` | SHA-256 `3b69a61fbbe608133c1c9ae4721325fd4cd15413f3ed82defb671a1b00bba944` | Architect report and governance gap. |
| `PI-IN-003` | hicache worktree `.memory/phase2-hicache-design/work/DEBUG-20260909-HOST-ALLOC-WAKE.md` | SHA-256 `b191ed962b9775575d89a2b8ed15bcbf14396bc8a008f306e6629da6b3df20c3` | Confirmed circular-wait diagnosis and live causal chain. |
| `PI-IN-004` | hicache worktree `.memory/phase2-hicache-design/work/HANDOFF-2026-09-07.md` | SHA-256 `edf75e117fdbc8e82a67e15c21765a5100b6767cc9d804ee24d468ca72067201` | Worktree provenance, frozen 3090 boundary, inherited operational constraints. |

### 4.2 Stable implementation and test evidence

All Git blobs below are from target revision `1e6a8219...`.

| Stable ID | Category | Path / symbol | Git blob | Disposition |
| --- | --- | --- | --- | --- |
| `PI-IMP-001` | stable implementation | `ready_horizon.py`: `CausalEpochs`, negative cursor, `epoch_event` | `aab07577a8b17d8ab3f544b821bc707cf9837033` | **ADAPT** monotonic causal-cursor concept; do not reuse Ready Horizon ownership or free-level-derived epoch. |
| `PI-IMP-002` | stable implementation | `unified_radix_cache.py`: demand-restore RID/ticket accounting | `d8438e140ffc1dfc5cdcb36cc8041790f51bfb68` | **ADAPT** bounded issue accounting; scheduler remains HOST_ALLOC order owner. |
| `PI-IMP-003` | stable implementation | `unified_radix_cache.py`: buffer-mode `pending_hit_allocs` FIFO | `d8438e140ffc1dfc5cdcb36cc8041790f51bfb68` | **ADAPT** FIFO ordering only; **DO NOT ADOPT** retained operation/reservation lifecycle. |
| `PI-IMP-004` | stable implementation | `unified_radix_cache.py::_try_alloc_storage_hit` full `alloc -> evict_host -> alloc` | `d8438e140ffc1dfc5cdcb36cc8041790f51bfb68` | **ADOPT** as sole full-span retry body; no scheduler fit authority. |
| `PI-IMP-005` | stable implementation | hybrid component pools and transfer/finalization path in `unified_radix_cache.py` | `d8438e140ffc1dfc5cdcb36cc8041790f51bfb68` | **ADOPT** all-or-nothing completion; **ADAPT** failures to exact per-pool domains. |
| `PI-IMP-006` | stable implementation | `hicache_restore.py`: `DENIED_ALLOC -> WAIT_CAPACITY/HOST_ALLOC`, T13 clock | `1b99331b9e6b8f13b061070fe40fe763311684bd` | **ADOPT** non-miss wait and timeout; **ADAPT** typed cursor metadata. |
| `PI-IMP-007` | stable implementation | `unified_tree_core.py::dec_host_lock_ref` and evictable-leaf refresh | `a0c93438e15f150b32c7dd0e461244fd24a2baac` | **ADAPT** mutation result to report changed pool/evictability; tree remains truth owner. |
| `PI-IMP-008` | stable implementation | `unified_radix_cache.py::_drain_release/_drain_extra_release` | `d8438e140ffc1dfc5cdcb36cc8041790f51bfb68` | **ADAPT** post-success per-pool generation bump; enqueue is not a bump. |
| `PI-ANTI-001` | anti-pattern | `scheduler.py::_restore_wait_capacity_fits` HOST_ALLOC free-full-span precondition | `6444e27285ccff8260433ece2c11a8565e1ff288` | **REJECT** for HOST_ALLOC; it suppresses the reclaim path and forms the confirmed circular wait. |
| `PI-ANTI-002` | anti-pattern | scheduler legacy paced retry / generic per-pass wake | `6444e27285ccff8260433ece2c11a8565e1ff288` | **REJECT** as allocability liveness; no causal source, permits repeated load. |
| `PI-ANTI-003` | anti-pattern | shortened cache-mode storage-hit crop fallback | `d8438e140ffc1dfc5cdcb36cc8041790f51bfb68` | **REJECT** for hybrid HOST_ALLOC; no sidecar-complete lower frontier is evidenced. |
| `PI-BUG-001` | bug-derived | q/x/w positive 54,976-token KV+Mamba hits park until T13 after alloc failure | input `PI-IN-003` | **ADOPT AS FAILURE ORACLE**; no claim that capacity was physically impossible. |
| `PI-TST-001` | harness/test | `test_hicache_restore_prefetch_budget.py` | `87c5ddf765cc68cf1b249ddb1a6d91065b7122a4` | **ADAPT/EXTEND** scheduler fixture for no-change, budget denial, one-generation/one-grant, timeout. |
| `PI-TST-002` | harness/test | `test_unified_radix_hicache_dispatch.py` hybrid crop guard | `6f3608c6bb679d18eeab61cb3a4e16368af29dea` | **ADOPT/EXTEND** no-crop and KV+Mamba all-or-nothing oracle. |
| `PI-TST-003` | harness/test | `test_unified_radix_allocation_eviction.py` allocation-aware eviction | `669059511c8c468a7c52c2d4dfd98bbd470e623a` | **ADAPT/EXTEND** allocator/removal call history and per-component capacity effects. |
| `PI-BENCH-001` | benchmark | live 3060 q/x/w/y/z causal bundle summarized by `PI-IN-003` | report SHA-256 above | **DIAGNOSTIC ONLY**; cannot substitute for deterministic tests or post-change live acceptance. |
| `PI-DEF-001` | deferred | lower sidecar-complete checkpoint discovery | no repository authority found | **DEFER**; new semantics and authority require fresh Task ID. |
| `PI-DEF-002` | deferred | cross-process generation propagation | no repository authority found | **DEFER**; in-scope contract is same-process/cache-instance only. |
| `PI-DEF-003` | deferred | performance/fairness tuning beyond one FIFO grant | no accepted benchmark oracle found | **DEFER** until correctness gates pass; fresh Task ID. |
| `PI-MISS-001` | missing | full canonical Pattern Intake template and stable repository corpus | exact searches in section 3 | **BLOCKING GOVERNANCE GAP** unless orchestrator explicitly accepts this substitute. |
| `PI-MISS-002` | missing | accepted Novel Mechanism/design-authority decision ID | linked declaration is proposed | **BLOCKING ADMISSION GAP**. |

No other relevant stable implementation, anti-pattern, bug-derived, harness,
benchmark, deferred, or missing item was found in the pinned searched scope.
That is a bounded repository-search statement, not a claim about external or
unavailable corpora.

## 5. Atomic invariant → pattern → test mapping

Each row is independently rejectable. `HAE-*` refers to the architecture
contract's required test cases; these are required future tests, not passes.

| Mapping ID | Atomic invariant | Pattern disposition | Required oracle / case |
| --- | --- | --- | --- |
| `PI-MAP-001` | Per cache instance and pool, generation never decreases; reset identity makes old cursors incomparable. | Adapt `PI-IMP-001`; novel identity boundary. | `HAE-13`; monotonic/reset unit test. |
| `PI-MAP-002` | A successful non-empty direct KV free bumps KV exactly once after free completion. | Adapt `PI-IMP-008`; reject inferred polling `PI-ANTI-001`. | `HAE-02`; before/after allocator and generation call history. |
| `PI-MAP-003` | Queue enqueue does not bump; successful non-empty KV drain bumps once per batch. | Adapt `PI-IMP-008`. | `HAE-03`; enqueue/no-bump and drain/post-success test. |
| `PI-MAP-004` | Effective host unlock that changes primary evictability bumps KV; ineffective unlock does not. | Adapt `PI-IMP-007`; novel delta interface. | `HAE-01`, `HAE-04`; tree before/after evictable-set oracle. |
| `PI-MAP-005` | Auxiliary pools advance only their own member; KV change cannot satisfy auxiliary blocking. | Adapt `PI-IMP-005/008`; novel vector composition. | `HAE-09`, `HAE-10`; per-pool vector and READY-state oracle. |
| `PI-MAP-006` | Failed allocation, reservation release, scheduler pass, timeout, and unrelated epochs never bump. | Reject `PI-ANTI-002`; distinguish `PI-IMP-001`. | `HAE-05`, `HAE-14`; negative bump matrix. |
| `PI-MAP-007` | Wait cursor is captured after all failed-attempt cleanup and holds no reservation. | Adapt `PI-IMP-002/006`; novel ordering boundary. | `HAE-07`, `HAE-12`; reservation ledger plus snapshot ordering. |
| `PI-MAP-008` | A waiter wakes only after every blocked domain advances; budget denial does not consume opportunity. | Adapt `PI-IMP-001/002`; novel multi-domain predicate. | `HAE-05`, `HAE-07`, `HAE-09`. |
| `PI-MAP-009` | One newly observed relevant generation vector grants at most one global FIFO full-span retry. | Adapt FIFO `PI-IMP-003`; reject retained operation; novel global arbiter. | `HAE-06`, `HAE-08`, `HAE-11`; exact retry count/order. |
| `PI-MAP-010` | Failed grantee snapshots post-attempt vector, moves to tail, and cannot self-spin. | Adapt `PI-IMP-003`; novel commit ordering. | `HAE-06`, `HAE-08`, `HAE-12`. |
| `PI-MAP-011` | Retry invokes existing complete-frontier `alloc -> one reclaim -> alloc` at most once. | Adopt `PI-IMP-004`; reject `PI-ANTI-001/002`. | `HAE-01..03`, `HAE-06`; allocator call history. |
| `PI-MAP-012` | Positive allocation pressure remains non-miss HOST_ALLOC; no arbitrary crop or lower-frontier inference. | Adopt `PI-IMP-006`; reject `PI-ANTI-003`. | `HAE-01`, `HAE-05`, `HAE-14`; state/miss/crop oracle. |
| `PI-MAP-013` | Hybrid READY requires complete KV and every sidecar for the same attempt. | Adopt `PI-IMP-005`; extend `PI-TST-002`. | `HAE-09`, `HAE-10`; complete transfer/finalization identity. |
| `PI-MAP-014` | KV-only requests use the same bounded wake without requiring absent pools. | Adapt `PI-IMP-005/006`. | `HAE-15`; compatibility fixture. |
| `PI-MAP-015` | No relevant change means zero retries; original T13 clock remains bounded. | Adopt timeout from `PI-IMP-006`; reject `PI-ANTI-002`. | `HAE-05`; many-pass and timeout-clock assertion. |

## 6. Structural trade-offs, risk, and reversibility

- Cache/tree mutation ownership is necessary because scheduler free-level
  inference cannot observe lock-to-evictable transitions. The dependency is
  one-way: mutation owner → read-only snapshot → scheduler arbiter.
- Per-pool vectors preserve hybrid correctness but add typed failure metadata
  and exact attribution work. A scalar KV epoch is simpler and unsafe when an
  auxiliary pool remains blocked.
- One global FIFO grant minimizes stampede and is deterministic, but an
  insufficient head waiter may defer a later fit-capable request until the
  next causal change. FIFO tail rotation and existing T13 bound this policy;
  relaxing it needs a separately accepted fairness/load contract.
- The mechanism introduces no durable state or wire-format migration. It is
  reversible by removing generation/cursor/arbiter fields and restoring the
  old wake predicate, but that rollback knowingly restores the diagnosed
  liveness gap. Mixed source revisions must fail closed rather than interpret
  missing typed metadata as fit.
- Cross-thread visibility remains a blocking implementation proof obligation:
  use proven owner-thread serialization or an atomic/locked counter boundary.

## 7. Admission handoff

Recommendation to the orchestrator: accept the stable-ID dispositions and
atomic mappings as design evidence, then either explicitly approve this
closest-schema substitution or provide the canonical full schema/corpus and
authorized path. Separately accept or revise
`NM-HOST-ALLOC-EPOCH-20260909-01`. Only then may G1/G2 implementation dispatch
be admitted against the pinned architecture revision.

This recommendation is evidence, not authority. Extra corpus, research,
design, implementation, test, deployment, remote, storage, or 3090 work
requires a fresh Task ID.

Status: `done` for the authorized intake artifact; implementation admission:
`BLOCKED`.
