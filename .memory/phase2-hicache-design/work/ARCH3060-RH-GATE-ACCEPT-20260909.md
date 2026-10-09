ENTRY: ACCEPT

status: done
task_id: ARCH3060-RH-GATE-ACCEPT-20260909
orchestration_epoch: 20260909-rh-ab30
role: architect
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
corpus_revision: 82ab235606233160701b15f657a71794cfd29a30
implementation_revision: 67b39b5aca6aaacbf410d21efda9b7059eaa8d2c
gate_verdict: ACCEPT
implementation_admission: AUTHORIZED_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW

## Artifacts

Updated only the three authorized RH gate artifacts:

- `storage/review/gates/pattern-intake/PATTERN-INTAKE-20260909-RH-PREADMISSION.md`
- `review/gates/NOVEL-MECHANISM-20260909-RH-PREADMISSION.md`
- `review/gates/ARCH-20260909-RH-PREADMISSION.md`

This report is the only additional write. No runtime source, test, remote host,
storage, 3090 branch, or unrelated documentation was modified.

## Decision

The Pattern Intake, Novel Mechanism, and G-ARCH RH pre-admission design gates
are explicitly **ACCEPTED** and the exact final implementation revision is
admitted to independent implementation review. This decision accepts only the
design shape and its architecture boundaries. It does not self-approve G-IMPL,
replace an independent reviewer verdict, accept deployment, or establish a
performance claim.

## Observed facts

- Target branch HEAD is exactly
  `67b39b5aca6aaacbf410d21efda9b7059eaa8d2c`.
- The corpus/search pin remains
  `82ab235606233160701b15f657a71794cfd29a30`; implementation revision is
  recorded separately in all three gates.
- The five-commit implementation range changes four product files and five
  focused test files. The product surface is scheduler routing/lifecycle,
  request-local ephemeral state, typed restore issue types, and cache
  attempt/completion handoff.
- `Scheduler._add_request_to_queue` preserves RH-OFF eager-before-append and
  makes RH-ON queue-first; `_ready_horizon_pass` is the RH-ON initial issuer.
- `_prefetch_kvcache` claims before entering the lower issue path, retains the
  claim only for typed `ISSUED`, and rejects duplicate active calls.
- `_release_prefetch_claim` compares the expected attempt; cache terminal
  records carry that attempt, and `_feed_restore_terminal` fences stale
  completions before state transition.
- The cache finalizer supplies actual completed KV tokens, required auxiliary
  pools, completed auxiliary units, and `finalize_result` in the completion
  handoff.
- At the final revision, `discarded` and `rejected` finalization map to
  `DENIED_SHORT`/recompute state `NONE`; only accepted finalization reaches
  READY and emits `rh_ready_host.v1`.
- No final-range change transfers HOST_ALLOC generation/FIFO, allocator,
  Mamba allocation, persistence-format, or storage-truth authority to RH.

## Assumptions and accepted equivalences

- Scheduler queue mutation and initial issue remain serialized by the existing
  scheduler owner; no evidence in the reviewed change introduced concurrency.
- Final names `_claim_prefetch`, `_release_prefetch_claim`, and
  `PrefetchIssueResult` are accepted one-to-one implementations of the
  contract's proposed helper/type names.
- String attempt IDs are accepted in place of the proposed integer shape
  because they preserve monotonic request-local identity, correlation, and
  stale fencing.
- `EAGER_DISAGG_PREFILL` is a compatibility origin for the pre-existing
  disaggregated path, not a second owner for NULL-mode RH pre-admission.

## Evidence matrix

| Requirement | Evidence | Result |
| --- | --- | --- |
| RH-ON sole queue-first owner | Final `_add_request_to_queue` and `_ready_horizon_pass`; RH queue/origin tests | ACCEPT |
| RH-OFF unchanged ordering | Final eager call remains before append with `EAGER_RH_OFF`; focused fixture | ACCEPT structurally; final live equivalence remains open |
| Successful issue holds attempt | Typed result path returns `ISSUED`; coder/tester lifecycle evidence | ACCEPT |
| Stale release fenced | Attempt comparison in scheduler and attempt-bearing cache terminal; stale lifecycle harness | ACCEPT |
| Authoritative KV+aux readiness | Finalizer completion handoff and auxiliary completion test | ACCEPT |
| Hybrid discard cannot READY | Final `DENIED_SHORT`/`NONE` path and `test_discarded_finalization_cannot_be_ready_host` | ACCEPT |
| HOST_ALLOC/Mamba authority unchanged | Five-commit scope and source-boundary inspection; focused neighboring regressions | ACCEPT within design scope |
| Required joined telemetry | Decision/stage/ready/admission schemas and required-field source test | ACCEPT for interface; final live join open |

## Reconciled prior blockers

- The tester BLOCK at `7831d45dd4` correctly identified missing authoritative
  auxiliary values in `ready_host`. Commit `6881529acb` resolves the design
  defect through a finalizer-owned, attempt-correlated completion handoff.
- The tester BLOCK at `6881529acb` correctly identified false READY/readiness
  telemetry after hybrid discard. Commit `67b39b5aca` resolves it by consuming
  `finalize_result` before transition and suppressing readiness for discarded
  or rejected material.
- Earlier issue-result, active-claim, stale-release, and telemetry-contract
  reviewer findings were corrected at `7831d45dd4` and remain represented in
  the final source and focused evidence.

## Rejected alternatives and reversibility

Dual eager-plus-RH initial ownership, relabeling eager enqueue without RH
policy gates, removal of eager issue in RH-OFF, and transfer of HOST_ALLOC
generation/retry authority into RH remain rejected. The accepted mechanism is
ephemeral and process-local. Rollback is drain/restart with RH disabled; no
persistent-data migration or mixed-version protocol is introduced. Hot mode
flip with active requests remains unsupported.

## Evidence limitations and risks

- `orjson` is missing, so dependency-backed ready-horizon and scheduler-feed
  suites were not run for the final revision. Reported dependency-free and
  source-loaded focused tests passed, but do not constitute full integration
  evidence.
- No live 3060/deploy-hash-pinned run exists for `67b39b5aca`. Existing bounded
  RH-OFF/RH-ON traces predate the implementation and cannot prove final runtime
  behavior or joined telemetry.
- No latency, throughput, fairness, or deployment acceptance is granted. The
  earlier diagnostic RH-ON bounded trace regressed aggregate outcomes.
- Independent implementation review remains mandatory and authoritative for
  merge acceptance; a blocking reviewer finding supersedes this admission.

## Summary

The final revision matches the accepted queue ownership, typed issue/attempt
lifecycle, stale-completion fence, authoritative hybrid readiness, telemetry
interface, and rollback boundaries. All three RH design gates now explicitly
record ACCEPT and implementation admission for independent review, with corpus
and implementation revisions separated and unresolved runtime evidence kept
visible.

## Followups

- Orchestrator: submit the final revision and updated gates to a fresh
  independent reviewer dispatch; this architecture report is evidence, not
  reviewer authority.
- Tester: under a fresh Task ID, run dependency-backed suites with `orjson`
  and a deploy-hash-pinned bounded RH-OFF/RH-ON final-revision trace if runtime
  or terminal acceptance is required.

## Open issues

- Missing dependency-backed integration evidence (`orjson`).
- Missing final-revision live/deploy-hash evidence and complete runtime event
  joins.
- Performance/fairness and deployment remain outside this accepted design
  gate.
