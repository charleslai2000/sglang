ENTRY: ACCEPT

# RH pre-admission pattern corpus/search report

- Task ID: `SCOUT3060-RH-PATTERN-CORPUS-20260909`
- Orchestration epoch: `20260909-rh-ab16`
- Role/status: `scout` / `done`
- Authorized scope: read-only inspection of
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`, branch
  `3060-12g-qwen35-4b`; this report is the only write.

## Corpus pin and limits

Observed repository identity:

- Branch: `3060-12g-qwen35-4b`
- Revision: `82ab235606233160701b15f657a71794cfd29a30`
- HEAD subject: `fix(hicache): close final host alloc telemetry findings`
- Worktree has untracked `.memory/`, `review/gates/`, and `storage/` artifacts;
  they were inspected as worktree evidence but are not Git-indexed at HEAD.

Exact discovery/search commands used:

```text
git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt status --short --branch
git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt rev-parse HEAD
git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt branch --show-current
rg --files review/gates storage/review/gates
git ls-files review/gates storage/review/gates/pattern-intake
git log --all --oneline -- review/gates storage/review/gates/pattern-intake
git log --all --name-only --pretty=format: | rg -i 'pattern.intake|novel.mechanism|ready.horizon|host.alloc'
rg -n -i 'ready[_ -]?horizon|prefetch|restore|budget[_ -]?wait|admission|host[_ -]?ready|request[-_ ]correl|telemetry|residency|frontier|horizon' python 3090-dev test review/gates storage/review/gates
rg -n '^class |^def |^    def test_|CausalEpochs|RestoreState|RestoreWaitReason|WAIT_CAPACITY|HOST_ALLOC|prefetch_budget|admission|telemetry|request_id|trace_id|assert' <targeted source/test files>
```

Search was bounded to the target repository, its gate directories, Python source,
`3090-dev`, and `test`; Git history was searched only for gate/RH/host-allocation
names. No external repositories, remote hosts, storage contents, or unrelated
private data were searched. Search results are evidence of presence/absence in
that scope, not a claim about external corpora.

## Pattern-intake and gate artifacts

Relevant worktree artifacts and observed status:

| ID | Path | Evidence/classification | Status |
| --- | --- | --- | --- |
| `RH-GATE-001` | `review/gates/ARCH-20260909-HOST-ALLOC-EPOCH.md` | Architecture contract distinguishes RH release epoch from HOST_ALLOC generation and specifies restore/admission/telemetry boundaries; sections 4, 5, 8, 10, 11. | Proposed/pending authority; not a RH implementation approval. |
| `RH-GATE-002` | `review/gates/PATTERN-INTAKE-20260909-HOST-ALLOC-EPOCH.md` | Closest existing intake-shaped artifact. It records target revision `1e6a8219...`, stable IDs, dispositions, and mappings, but explicitly says no canonical full template/corpus exists and implementation admission is `BLOCKED` (lines 27–39, 58–100, 117–142, 146–167). | Evidence only; target revision differs from current HEAD. |
| `RH-GATE-003` | `review/gates/NOVEL-MECHANISM-20260909-HOST-ALLOC-EPOCH.md` | Declares a novel cross-boundary composition: host mutation → per-pool generation vector → typed request cursor → FIFO arbiter → full-span allocator → hybrid finalizer (lines 19–36). | Proposed for orchestrator acceptance; no implementation authority. |
| `RH-GATE-004` | `storage/review/gates/pattern-intake/EXEMPT-3060-RUNTIME-COMPAT.md` | Sole artifact under the canonical pattern-intake directory. It is a narrow runtime-compatibility EXEMPT and explicitly says full reusable-pattern intake is not applicable to that maintenance scope. | Not a RH corpus/intake. |
| `RH-GATE-005` | `review/gates/REVIEW-20260909-HYBRID-FRONTIER-GUARD.md` | Positive review evidence for no arbitrary trailing-sidecar crop, KV-only compatibility, hybrid all-or-nothing discard, and scheduler prefetch wake. | Gate artifact; does not establish canonical pattern authority. |
| `RH-GATE-006` | `review/gates/REVIEW-20260909-CAPACITY-SEMANTICS.md` | Negative/bug-derived evidence for positive allocation failure being misclassified as a genuine miss. | Review verdict is REJECT. |
| `RH-GATE-007` | `review/gates/REVIEW-20260909-ALLOC-FAILED-TERMINAL.md` | Positive terminal mapping evidence for `revoked_alloc_failed`, `DENIED_ALLOC`, `HOST_ALLOC`, and `WAIT_CAPACITY`. | Gate artifact; current source/test evidence only. |
| `RH-GATE-008` | `review/gates/REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH-TELEMETRY-FINAL.md` | Current-HEAD deep review (`82ab235...`) accepts source/dependency-free telemetry fixes, while retaining a bounded-sampling P2 tradeoff and live-3060 prerequisites. | Accepted commit-level review; not canonical pattern corpus. |

The current `git ls-files review/gates storage/review/gates/pattern-intake`
result lists only the historical/committed gate files; the RH intake, novel,
architecture, and current review artifacts are untracked worktree files. The
only canonical-directory file found is `EXEMPT-3060-RUNTIME-COMPAT.md`.
`git log --all` found prior RH source/test names, but no canonical full Pattern
Intake template or stable corpus directory.

## Concrete source and test corpus

### Stable implementation candidates

| ID | Path/symbol | Observed behavior | Disposition candidate |
| --- | --- | --- | --- |
| `RH-IMP-001` | `python/sglang/srt/managers/scheduler_components/ready_horizon.py:101-187`, `CausalEpochs`, `NegativeCacheEntry`, `ReadyHorizonView`, `RefillPlan` | Typed causal cursor/epoch inputs, request identity, decline reasons, and immutable policy inputs. | **ADAPT** cursor/event concepts only. RH owns READY_HOST refill semantics; it must not become HOST_ALLOC authority. |
| `RH-IMP-002` | `ready_horizon.py:546-578`, `ReadyHorizonPolicy.epoch_event`, `should_refill` | Event-driven refill with monotonic release counter, budget release, frontier changes, and periodic safety reconciliation. | **ADOPT for RH** event-gated refill; **DO NOT ADOPT** as proof of host allocation fit. |
| `RH-IMP-003` | `ready_horizon.py:581-660`, `partition_ready_first` | Resident-marker based READY membership and stable READY-first admission ordering; explicit priority boundaries are preserved. | **ADOPT** for RH admission ordering; preserve off-mode no-op. |
| `RH-IMP-004` | `scheduler.py:1421-1462, 3804-4106, 5028-5093` | Scheduler initializes RH, builds views/epochs, runs `_ready_horizon_pass`, and conditionally partitions the waiting queue. | **ADOPT as existing integration boundary**; RH should remain delegated policy, not scheduler-wide allocation owner. |
| `RH-IMP-005` | `hicache_restore.py:RestoreState`, `RestoreWaitReason`, `HostAllocWakeArbiter` (top-level classes; current file lines 26 onward) | Typed restore states/reasons and scheduler-owned FIFO HOST_ALLOC retry helper exist beside restore logic. | **ADAPT/keep separate**: RH may consume state/reason views, but HOST_ALLOC wake remains restore/scheduler-owned. |
| `RH-IMP-006` | `unified_radix_cache.py` storage-hit/prefetch allocation path; linked by `ARCH-20260909-HOST-ALLOC-EPOCH.md` sections 5–6 | Existing full-span alloc/reclaim and hybrid finalization are the allocator authority. | **ADOPT as lower-layer authority**; RH must not infer lower checkpoints or crop. |

### Negative and bug-derived candidates

| ID | Evidence | Classification/disposition |
| --- | --- | --- |
| `RH-ANTI-001` | `ready_horizon.py` module contract and tests explicitly exclude `RestoreWaitReason.HOST_ALLOC` and `REVALIDATE` from RH staging (`ready_horizon.py:411-432`; `test_ready_horizon_unit.py:324-332`). | **ADOPT as boundary/negative pattern**: HOST_ALLOC is not RH-stageable. |
| `RH-ANTI-002` | RH module docs state per-pass polling causes the prior retry spin; `epoch_event` rejects unchanged epochs (`ready_horizon.py:22-62, 546-564`; tests `test_no_event_within_interval_no_refill`, `test_identical_epochs_no_event`). | **REJECT** generic per-pass wake/polling. |
| `RH-ANTI-003` | `REVIEW-20260909-CAPACITY-SEMANTICS.md` records positive allocation failure classified as genuine miss; `REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH.md` records arbitrary crop and auxiliary-generation risks at its reviewed revision. | **REJECT** miss conflation, arbitrary crop, scalar-only auxiliary wake. |
| `RH-BUG-001` | `PATTERN-INTAKE-20260909-HOST-ALLOC-EPOCH.md:130` records q/x/w positive KV+Mamba hits parking until T13 after alloc failure. | **ADOPT as failure oracle only**; it does not prove capacity impossibility. |
| `RH-BUG-002` | `ready_horizon.py` docs describe the prior `~141/s`, `1289 issues / 9.04s` deterministic miss issue/revoke/reissue spin. | **ADOPT as RH retry-storm oracle**; safety fuse is a bound, not normal wake authority. |

### Harness/test candidates

| ID | Path/test symbols | Evidence/disposition |
| --- | --- | --- |
| `RH-TST-001` | `3090-dev/test_ready_horizon_unit.py:241-1204` | Unit corpus covers frontier, strict resident marker, candidate filtering, per-RID negative cache, headroom, event gating, no-op behavior, scheduler pass, release-epoch wake, off mode, logs, and deterministic miss parking. **ADOPT/EXTEND** as RH oracle corpus. |
| `RH-TST-002` | `3090-dev/test_ready_horizon_partition.py:74-404` | Covers stable partition, explicit priority, idle/off no-op, order preservation, head-of-line skip semantics, and scheduler gate wiring. **ADOPT** for admission-order invariants. |
| `RH-TST-003` | `3090-dev/test_prefetch_budget_split_unit.py`; `test/registered/unit/managers/test_hicache_restore_prefetch_budget.py` | Prefetch budget split and restore budget tests are present. **ADAPT** for RH `SPEC_BUDGET` interaction; not evidence that HOST_ALLOC fits. |
| `RH-TST-004` | `3090-dev/test_hicache_restore_scheduler_feed.py`; `test/registered/unit/managers/test_hicache_host_allocability.py` | Restore scheduler-feed and host-allocability harnesses provide neighboring wait/admission oracles. **ADAPT**, keeping HOST_ALLOC ownership outside RH. |
| `RH-TST-005` | `3090-dev/test_storage_regression.py:2489+`, including `HostAllocMutationTelemetryTests` and hybrid finalize tests | Dependency-free telemetry/hybrid harness has request IDs and bounded-emission assertions. **ADAPT** for request-correlated RH/restore observations; not a full RH authority oracle. |

### Benchmark, deferred, and missing items

- `RH-BENCH-001`: the live 3060 causal bundle summarized by
  `PATTERN-INTAKE-20260909-HOST-ALLOC-EPOCH.md:134` is diagnostic only. No
  current-HEAD live RH benchmark or runtime pass was found in the bounded scope.
- `RH-DEF-001`: lower sidecar-complete checkpoint discovery is explicitly
  deferred by the existing intake (`:135`); it is outside RH admission.
- `RH-DEF-002`: cross-process generation propagation is explicitly deferred
  (`:136`); current evidence is same-process/cache-instance only.
- `RH-DEF-003`: performance/fairness tuning beyond one FIFO grant is deferred
  (`:137`); no accepted benchmark oracle was found.
- `RH-MISS-001`: canonical full Pattern Intake schema/template and stable
  repository corpus are missing. The existing intake says this directly at
  `review/gates/PATTERN-INTAKE-20260909-HOST-ALLOC-EPOCH.md:32-39, 87-100`.
- `RH-MISS-002`: no accepted RH-specific Novel Mechanism/design-authority ID
  was found. The neighboring HOST_ALLOC novel declaration remains proposed,
  and its authority is explicitly not implementation approval.
- `RH-MISS-003`: no test proving RH and HOST_ALLOC share an authority or that
  RH release epochs can wake HOST_ALLOC was found. The architecture artifact
  instead states these have different ownership/semantics (`ARCH...md:206-209`).
- `RH-MISS-004`: no current-HEAD live 3060 RH acceptance evidence was found;
  current review artifacts retain live prerequisites.

## Atomic invariant → pattern → test mapping suggestions

These are evidence-backed candidate mappings, not design approval or test
results.

| Mapping ID | Atomic invariant | Pattern evidence | Candidate oracle |
| --- | --- | --- | --- |
| `RH-MAP-001` | READY means required host material is physically resident and full-prefix compatible; consumed/dropped markers are not READY material. | `RH-IMP-003`; `test_ready_horizon_unit.py:255-292`; partition marker tests. | `test_ready_requires_resident_marker`, `test_dropped_insert_is_not_pool_material`, `test_consumed_marker_not_counted`, `test_partial_prefix_not_pool_material`. |
| `RH-MAP-002` | Only stageable restore reasons enter RH candidates; HOST_ALLOC/REVALIDATE/frontier/backup-pending do not. | `RH-ANTI-001`; `test_ready_horizon_unit.py:324-332`. | `test_ack_driven_and_untestable_reasons_excluded`, `test_non_stageable_states_excluded`. |
| `RH-MAP-003` | No-headroom and speculative-budget declines do not evict; they park/retry only on the subscribed causal signal or safety bound. | `RH-IMP-002`, `RH-BUG-002`. | `test_headroom_shortfall_never_evicts`, `test_no_headroom_park_wakes_on_release_epoch_not_level`, `test_spec_budget_cleared_only_by_budget_release`, `test_fuse_expiry_is_only_a_safety_bound`. |
| `RH-MAP-004` | Unchanged epochs and refill self-traffic produce no repeated issue. | `RH-ANTI-002`. | `test_identical_epochs_no_event`, `test_refill_own_issue_traffic_no_event`, `test_no_event_epoch_no_refill`. |
| `RH-MAP-005` | READY-first partition preserves explicit priority groups and relative order, and OFF mode is behavior-preserving. | `RH-IMP-003`; `test_ready_horizon_partition.py:74-205, 209-254, 301-404`. | Stable partition, priority boundary, idle/off no-op, and gate-wiring tests. |
| `RH-MAP-006` | HOST_ALLOC positive allocation pressure remains a restore/HOST_ALLOC decision; RH must not convert it to a genuine miss, infer a lower frontier, or declare fit. | `RH-ANTI-003`, `RH-MISS-003`; capacity/hybrid review gates. | Neighboring restore scheduler-feed/host-allocability tests plus a negative RH test asserting HOST_ALLOC is excluded from staging. |
| `RH-MAP-007` | Request-correlated telemetry is observational and must not become wake/fit authority; RH and restore records retain distinct ownership. | `ARCH-20260909-HOST-ALLOC-EPOCH.md:353-366`; `RH-TST-005`. | Schema/log fixture joins by RID/attempt where available; absence of telemetry must not change RH decisions. |

## Novel-boundary evidence

The repository evidence supports a boundary declaration if the RH work would
compose RH causal epochs with HOST_ALLOC generation/wake or alter RH ownership:

1. RH currently owns READY_HOST staging, per-RID negative cache, and READY-first
   admission (`ready_horizon.py:1-71, 189-203, 546-660`).
2. Restore/HOST_ALLOC owns `WAIT_CAPACITY`, typed wait reasons, allocation retry,
   and FIFO retry admission (`hicache_restore.py` top-level state/arbiter
   symbols; `ARCH...md:79-82, 212-258`).
3. The architecture evidence explicitly says RH's release epoch has different
   ownership/semantics from host allocability generation (`ARCH...md:206-209`).
4. Combining them would create a new authority/failure boundary involving
   cross-domain wake, fit semantics, fairness, and telemetry joins. The existing
   HOST_ALLOC novel declaration describes the same kind of new composition but
   remains proposed, not accepted.

Therefore the RH pre-admission gate has a concrete **novel-boundary candidate**
if the requested change crosses that line. If the work is limited to existing
RH staging/admission behavior, the stable RH patterns above are the relevant
corpus and no new mechanism is evidenced by this search.

## Summary, followups, and open issues

Summary: `done`. The concrete RH implementation and harness corpus is present
and has stable local symbols/tests, with positive, negative, bug-derived,
harness/test, benchmark, deferred, and missing classifications above. The
canonical full pattern corpus is absent; the existing closest-schema intake is
not canonical and is pinned to an earlier revision. The RH/HOST_ALLOC ownership
boundary is explicit and must not be silently merged.

Followups (non-blocking recommendations for the orchestrator):

- Require/obtain a fresh canonical Pattern Intake artifact under
  `storage/review/gates/pattern-intake/` before G1/G2 if the task changes RH
  semantics, authority, interfaces, failure behavior, or oracles.
- Treat the current HOST_ALLOC intake/novel artifacts as evidence only until
  their stated authority decisions are recorded.
- Keep any RH/HOST_ALLOC composition in a fresh Novel Mechanism declaration
  with atomic invariants, failure model, observable oracle, alternatives, and
  rollback/removal path.

Open issues:

- Canonical corpus/template and accepted authority decision are missing in the
  searched repository scope.
- Existing intake artifacts cite older revisions than current HEAD; their
  stable IDs should be re-pinned before being treated as current-HEAD corpus.
- No live 3060 RH runtime acceptance evidence was found.
- Extra corpus, research, design, implementation, or test work requires a
  fresh Task ID.
