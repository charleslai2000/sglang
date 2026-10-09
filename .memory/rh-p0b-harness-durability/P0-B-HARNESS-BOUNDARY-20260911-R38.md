# P0-B external harness authorization boundary — R38

- ENTRY: ACCEPT
- Task ID: `P0-B-HARNESS-BOUNDARY-20260911-R38`
- Invocation identity: `ses-p0b-harness-boundary-r38-20260911`
- Epoch: `2026-09-11`
- Role: `architect`
- Status: `done`

## Decision

**R31 authorizes a bounded verification-only run on the authorized RTX 3060,
but it does not authorize creation of a new bespoke harness, adapter, reducer,
or driver, even if that artifact is temporary, stored outside the repository,
and deleted after the run.** Creating executable logic that supplies the
missing orchestration, event correlation, schema adaptation, or verdict oracle
is test/harness implementation. Its location, persistence, and non-product
label do not change that classification. Fresh user authorization is required
before such an artifact is authored, transferred, or executed.

An external activity remains verification rather than implementation only when
it uses already-existing, reviewed executables and public interfaces without
adding executable logic or new observation mechanisms. A fresh execution Task
ID is still required for any 3060 activity.

Accordingly, the P0-B chain is **BLOCKED under current authorization** if no
existing reviewed vehicle can produce and correlate the required evidence. R34
and R32 establish exactly that limitation. The block must not be bypassed by
placing new code in `/tmp`, a home directory, an inline heredoc, `python -c`, a
shell function, a notebook, or another checkout.

## Observed facts

1. The phase plan authorizes the remote 3060 12G experimental instance for
   P0/P1/P2/P3 **experiment verification only**, requires a fresh Task ID per
   execution, and expressly does not authorize product-code, test-code,
   review-gate, storage, or Git changes
   (`3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/plan.md:3-11,46-55`).
2. R31's authorization verdict permits a verification-only P0-B run on that
   3060, while expressly excluding implementation and source/test/gate/storage/
   Git changes (`.../work/P0-B-AUTH-REVIEW-20260911-R31.md:13-22`). R31 also
   records that no dedicated exact HOST_ALLOC live driver was found (`:29-32`).
3. R30 defines the hard gate as `not allocable -> park -> real allocability
   change -> wake -> successful restore` and requires the positive full
   KV+Mamba case, one real transition, one FIFO full-span retry, READY, and
   specified negative conditions (`.../work/P0-B-LIVENESS-RECON-20260911-R30.md:8-27`).
4. R32 verified the 3060 target and dependencies and ran existing suites, but
   found no dedicated live driver. Existing runtime logs have null or absent
   causal fields and do not prove FIFO retry through full KV+Mamba restore and
   READY (`.../work/P0-B-LIVENESS-RUN-20260911-R32.md:8-23`). Its raw runtime
   inspection contains `host_alloc.v1` mutation rows with `rid=null`,
   `attempt_id=null`, `causal_rid=null`, and `trace_context=null`, demonstrating
   that passive temporal proximity cannot provide the missing join
   (`.../work/R32-artifacts/runtime-log-inspection.txt:18,50,64-76`).
5. R33 classifies most focused failures as fixture/API-shape gaps, leaves FIFO
   semantics open, and states that no live driver or correlated trace exists
   (`.../work/P0-B-FAILURE-TRIAGE-20260911-R33.md:7-25`). These unit-fixture
   repairs do not supply the missing live-chain observation boundary.
6. R34 finds useful but separate identity/barrier, generation/FIFO, scheduler,
   pressure, and hybrid components; no existing test-backed vehicle joins real
   capacity transition through HOST_ALLOC retry to full restore and READY
   (`.../work/P0-B-HARNESS-SCOUT-20260911-R34.md:6-28`).
7. R37 performed no remote action because its prerequisite artifacts were not
   visible in that invocation and reiterated that a separately authorized
   minimal harness would be needed if existing vehicles cannot produce the
   chain (`.../work/P0-B-LIVE-COLLECT-20260911-R37.md:6-25`). The R31, R32,
   R33, R34, R35, R36, R37, and R32 raw artifacts are now observable under the
   repository-local `.memory` tree; this resolves the artifact-location issue
   for analysis, but not the harness capability or authorization gap.
8. The accepted P0 vehicle gate is acceptance of the local vehicle/fixture
   boundary only, not live-runtime acceptance or live-rerun authority
   (`review/gates/P0-VEHICLE-BARRIER-SCHEDULER-FIX4.md:28-45,80-92`).
9. The residency gate requires a six-field logical identity
   `(run_id, session_id, session_generation, build_rid, node_id,
   final_kv_hash)` and rejects omission of `run_id`
   (`review/gates/P0-RESIDENCY-BARRIER-EMITTER-FIX2.md:24-37,41-71`).
10. The deep HOST_ALLOC gate remains rejected and requires correlated 3060 live
    scenarios; it also warns that request-scoped mutations can lack causal RID
    and trace context (`review/gates/REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH-FINAL.md:12-16,135-162`).
11. Global `AGENTS.md` prohibits introducing auditing, tracing, interception,
    monitoring, or instrumentation merely because evidence is required
    (`/home/dev-codex/AGENTS.md:3-10`).

## Classification rule: verification versus implementation

The boundary is determined by **behavior and responsibility**, not filesystem
location or lifetime.

### Verification activity allowed by R31, under a fresh execution Task ID

- Perform bounded identity/source/dependency/capacity preflight on the
  authorized 3060 only.
- Run already-existing, independently reviewed tests and vehicles at their
  reviewed revisions and through their documented interfaces.
- Use an existing generic HTTP client or existing checked-in load vehicle to
  submit bounded requests, provided no new control algorithm or semantic oracle
  is added.
- Configure an existing vehicle using its already-supported flags and data
  formats. Declarative values are allowed only when they select existing
  behavior; they may not encode a new reducer, scheduler, callback, or event
  adapter.
- Copy already-emitted logs and existing command output into a task evidence
  directory; compute hashes and perform offline inspection with existing
  standard tools.
- Stop fail-closed and report `NOT_VERIFIED` when required product-emitted
  fields or transitions are absent.

These actions verify existing behavior. They do not add a new component to the
system or alter what the target emits.

### Implementation requiring fresh user authorization

- Author any new Python, shell, notebook, plugin, callback, reducer, parser,
  adapter, or executable orchestration logic tailored to P0-B.
- Combine existing pieces with new control flow that creates pressure, detects
  a HOST_ALLOC park, triggers a release, selects the retry, or decides READY.
- Add or synthesize identity fields, join records across incompatible schemas,
  infer causal edges, or produce an acceptance verdict not already produced by
  a reviewed vehicle.
- Monkeypatch/import-hook the checkout, stage an overlay, modify process
  environment to load replacement behavior, or transfer modified fixtures as
  if they were merely run configuration.
- Add logging, probes, hooks, interception, polling endpoints, process-memory
  access, or other target-affecting observation mechanisms.
- Write the same logic inline (`python -c`, heredoc, shell function) or outside
  the repository. Ephemerality is a rollback property, not an authorization
  exemption.

### Narrow exception: non-programmatic command composition

A fixed, bounded sequence of documented commands that only invokes existing
reviewed interfaces is execution procedure, not harness implementation. It
crosses into implementation when it contains stateful branching, causal
correlation, schema transformation, retry control, or a novel pass/fail oracle.
If classification is ambiguous, treat it as implementation and stop for
authorization.

## Ownership and interface boundaries

- Product restore/scheduler and allocator remain authoritative for
  `WAIT_CAPACITY/HOST_ALLOC`, waiter ordering, fit/retry, allocation,
  finalization, and READY. An external driver may stimulate public interfaces
  and observe emitted facts; it must not become scheduling or wake authority.
- Product-emitted stable identity and state transitions are the evidence source
  of truth. An external process may validate a join but must not manufacture
  missing identity or convert time adjacency into causality.
- Existing tests are unit/contract oracles. Their success cannot substitute for
  the live physical-capacity transition.
- The external evidence collector, if already authorized and existing, owns
  only collection, ordering validation, bundle creation, and fail-closed
  reporting.

## Exact minimum evidence for a P0-B claim

All legs must come from one bounded, current-revision 3060 run and one singular
request lifecycle. Absence or ambiguity in any leg means `NOT_VERIFIED`.

1. **Provenance and target:** task ID, UTC interval, hostname, RTX 3060 12G/SM86
   identity, Python/runtime/dependency versions, exact source hashes (because
   the remote checkout lacks Git metadata), server command/config, and proof
   that no 3090/production target was accessed.
2. **Singular lifecycle identity:** authoritative non-empty `run_id`,
   `session_id`, `session_generation`, `build_rid`, `node_id`, and
   `final_kv_hash`, retained or unambiguously joined across hit, failure, park,
   transition, retry, restore/finalization, and READY. Also retain request RID,
   restore `attempt_id`, cache instance/rank, and HOST_ALLOC generation cursor
   wherever those are distinct dimensions. No conflicting identity or
   cross-run/session join is allowed.
3. **Positive full hit:** product evidence that the requested approximately
   54,976-token span is a real positive storage hit for the complete KV span and
   every required Mamba sidecar/page/key. Client hit counters or a synthetic
   fixture are insufficient.
4. **Real terminal allocation failure and park:** pre-attempt KV and Mamba
   availability/evictability snapshots; requested full-span requirements;
   allocation result proving not allocable; terminal mapping to
   `WAIT_CAPACITY` with reason `HOST_ALLOC`; waiter ticket/FIFO position; and
   captured per-pool generation cursor. It must not be a genuine miss,
   transient speculative-budget wait, crop, or partial allocation.
5. **Actual allocability transition:** a product-emitted release, unlock,
   eviction, or direct-free event with before/after KV and Mamba capacity and
   the causally corresponding per-pool generation change. Elapsed time, a
   generic headroom counter, or an uncorrelated `causal_rid=null` mutation row
   is insufficient.
6. **Exactly one eligible FIFO retry:** wake-decision evidence linked to the
   parked RID/attempt and captured generation cursor, showing required domains
   advanced, FIFO eligibility/order was respected, and one retry occurred.
   Demonstrate no same-generation self-wake, no spin, no skipped eligible
   predecessor, and no repeated retry.
7. **Successful all-or-nothing restoration:** bounded-reclaim allocation of the
   entire requested KV span and all required Mamba material; restore attempt
   success; hybrid finalization with state consistent with the scheduler; no
   crop, lower-frontier substitution, partial sidecar acceptance, discarded
   hybrid, or recompute fallback.
8. **READY after completion:** explicit product READY/admission event after full
   restore and finalization, on the same identity and attempt lineage. HTTP 200,
   client completion, or restore-shaped synthetic rows alone are insufficient.
9. **Evidence bundle:** immutable raw server/event log, exact command transcript,
   pre/post safety state, ordered normalized trace that preserves raw references,
   manifest, verdict, and SHA256 checksums. Any reducer output is derivative and
   must cite raw rows; raw evidence remains authoritative.
10. **Focused regression context:** reviewed fixture revision and results of the
    focused/exact HOST_ALLOC and terminal/wake/full-span suites. Green unit
    evidence is necessary context but does not replace items 3-8. The unresolved
    FIFO contract must not be silently changed to obtain a pass.

## Invariants and stop conditions

- No product, test, review-gate, storage, or Git modification under R31.
- No new instrumentation or target-affecting observation mechanism.
- No 3090 or production access and no production/runtime acceptance claim.
- No synthetic field completion, heuristic identity join, or causality inferred
  solely from timestamps.
- No advancement to P0-C or P1 while P0-B is `NOT_VERIFIED`.
- Preserve existing server/resources unless a fresh execution dispatch
  explicitly authorizes bounded lifecycle action; stop on provenance mismatch.

## BLOCKED / escalation condition

Stop before authoring, transferring, or running an external harness and return
`blocked` with `NEEDS_REROUTE` when any required P0-B evidence cannot be emitted,
collected, and correlated by existing reviewed vehicles and documented public
interfaces. Specifically, missing causal identity in the R32-style
`host_alloc.v1` rows, the need for a compatibility adapter/reducer, or the need
for stateful pressure/release/retry orchestration triggers this condition.

The orchestrator should request **fresh explicit user authorization** for a
minimal, verification-only harness implementation. That authorization should
name: permitted authoring location; exact files; whether transfer to the 3060
is allowed; approved public interfaces and log inputs; allowed server lifecycle
actions; resource/time/request bounds; prohibition on product monkeypatching
and new instrumentation; evidence outputs; independent review before execution;
cleanup/rollback; and continued exclusion of 3090/production. A specialist
implementation dispatch and independent review must follow authorization; R38
does not itself approve either.

## Rejected alternatives

1. **“Outside the repository means no code change.”** Rejected: it avoids a Git
   diff but still creates executable harness logic and may affect the target.
2. **“Temporary means verification.”** Rejected: deletion improves
   reversibility but does not change responsibility or authorization.
3. **Join events by timestamp/RID guess.** Rejected: R32 shows null causal fields,
   and the hard gate requires an identity-consistent causal chain.
4. **Use unit fixtures or synthetic rows as live proof.** Rejected: they validate
   mechanics/parsers, not physical capacity transition and all-or-nothing live
   restoration.
5. **Make Ready Horizon drive HOST_ALLOC wake/retry.** Rejected: restore/
   scheduler and allocator own that authority; changing it would expand product
   architecture and governance scope.
6. **Reuse R31 as implied authority to invent a driver.** Rejected: R31 expressly
   excludes implementation and itself identifies the absent dedicated driver.

## Migration path and reversibility if separately authorized

The least-expansive future path is a disposable, offline-first verification
asset that (1) drives only documented external request interfaces, (2) consumes
only existing product-emitted logs, (3) never imports or patches product
internals, (4) fails closed on missing fields, and (5) writes only an isolated
evidence directory. Review its exact content and hashes before transfer; execute
it under a new 3060-only Task ID; remove the remote copy after evidence capture;
and retain hashes plus raw evidence. If existing telemetry cannot support the
join, stop: adding telemetry is a separate product/governance decision, not the
next automatic migration step.

## Assumptions and uncertainty

- Assumption: “composed outside the repository” means new bespoke executable
  logic rather than only a list of existing documented commands. If it means
  the latter, the narrow execution-procedure exception above applies.
- The durable R31/R32/R33/R34 artifacts exist in the repository-local `.memory`
  tree, while R37 searched a different child-visible `.memory` root. This report
  treats the repository-local artifacts as the supplied evidence baseline but
  makes no claim about how they should be synchronized.
- It is uncertain whether the current product revision can emit every required
  causal field without modification. R32 is evidence that the inspected live
  logs did not. This uncertainty strengthens the fail-closed stop condition; it
  does not authorize instrumentation.

## Artifacts

- Created only this report:
  `.memory/phase2-hicache-design/work/P0-B-HARNESS-BOUNDARY-20260911-R38.md`
- No repository product/test/gate file, remote host, storage, Git state, 3090,
  or production resource was changed or accessed.

## Evidence

- Read global `/home/dev-codex/AGENTS.md` and the designated R30/R31/R32/R33/
  R34/R37 reports, R32 raw inventory/runtime evidence, phase context/plan/ledger,
  and cited architecture/review gates.
- Analysis was local and read-only except for this authorized report.
- No tests, imports, compilation, runtime commands, remote access, or experiments
  were performed.

## Summary

R31 permits running existing reviewed verification mechanisms on the authorized
3060, not building the missing mechanism. A bespoke external P0-B driver is
harness/test implementation even when ephemeral and outside the repository.
Because R32 and R34 show that existing mechanisms cannot produce the complete
causally joined hard path, P0-B remains `NOT_VERIFIED` and creation/use of that
driver is **BLOCKED pending fresh explicit user authorization**.

## Followups

1. Orchestrator: obtain fresh user authorization using the bounded decision
   packet in the BLOCKED section if a bespoke harness is desired.
2. After authorization, dispatch a fresh harness implementation specialist with
   exact write set and constraints, then an independent reviewer; neither step
   is authorized by this report alone.
3. Only after review, dispatch fresh 3060 execution and independent evidence
   review. Preserve the P0-B hard gate and fail closed on any missing leg.
4. If the user declines implementation authorization, report P0-B blocked; do
   not attempt to close it with R32 logs, synthetic evidence, or inline logic.

## Open issues

1. Current live telemetry may not expose enough causal identity to join a real
   HOST_ALLOC mutation to the parked request and restore attempt.
2. The authoritative FIFO behavior remains an open contract decision; a harness
   may observe but must not redefine it.
3. R35 fixture changes are independently approved by R36 in the repository-local
   evidence, but their dependency-complete 3060 rerun remains outstanding and
   still cannot substitute for the live chain.
4. Repository-local and workspace-root `.memory` visibility differed across
   R34/R37 invocations; coordination should materialize an explicit evidence
   package for a future dispatch without changing the product boundary.
5. HOST_ALLOC governance and telemetry gates remain rejected/open; a verification
   harness must not be treated as resolution of those architecture decisions.
