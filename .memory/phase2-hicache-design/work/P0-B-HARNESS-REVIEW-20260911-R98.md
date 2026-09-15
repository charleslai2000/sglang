status: done

artifacts:
- Final review: `work/P0-B-HARNESS-REVIEW-20260911-R98.md`
- Reviewed package: `work/R94-harness/` (exactly six files: README.md,
  run_selftests.sh, p0b_driver.py, p0b_reducer.py, test_reducer.py, and
  manifest.sha256)

evidence:
- Read `P0-B-HARNESS-IMPLEMENT-20260911-R94.md` and directly inspected all
  six materialized package files.
- Read the rejection criteria and source requirements in R90, R86, R79, R54,
  R67, R72, and R53. R95 was not present at its expected canonical path, so no
  claim is made from it.
- `./run_selftests.sh`: 11/11 tests passed; AST checks, manifest SHA256 checks,
  and no-bytecode readback passed after removing only test-generated
  `__pycache__` artifacts. Independent `python3 -m py_compile` also passed.
- Direct code inspection confirmed raw authoritative schema rejection,
  parser-owned absolute file:line references, source-file SHA256 binding,
  summary-field rejection, the eleven named oracle predicates, PID/profile/
  source-manifest checks, captured generation checks, finalization/READY joins,
  four statuses, loopback/3060 restrictions, Gate A ordering, redirect
  refusal, and six-request/600-second driver bounds.

summary:
- verdict: REJECT
- The R94 package is materially stronger than R89 and its positive synthetic
  fixture exercises the intended fail-closed path, but it is not semantically
  safe for the one 3060 execution. The release action is not the exact
  authorized action, and the reducer has a concrete FIFO provenance hole.
- The package therefore cannot be approved for transfer or execution. P0-B
  remains NOT_VERIFIED; no live conclusion follows from the synthetic fixture.

findings:
- severity: HIGH
  disposition: fix before any execution
  defect: `p0b_driver.py:182` submits `{"rid": "p0b-r94-holder"}` to
    `/abort_request`, while the reviewed R67 contract identifies the exact
    public payload as `{"rid": <holder_rid>, "abort_all": ...}`. The driver
    never sends or explicitly fixes `abort_all`.
  evidence: R67:159 and R67:214-216 describe the endpoint contract and the
    exact holder release action; R90 explicitly required correction of the
    abort payload. The current call site contains only `rid`.
  consequence: server-side default/implicit behavior can change which request
    is cancelled or whether the intended staged holder release occurs. Gate A
    can be true while the only release action is not the authorized release
    operation.

- severity: HIGH
  disposition: fix before any execution
  defect: FIFO predecessor validation does not bind the predecessor terminal
    event to the declared predecessor waiter. The reducer checks that the
    event ID named by `predecessor_terminal_event_id` exists and precedes the
    wake, but never checks that its payload `wait_id` equals
    `predecessor_wait_id`; it also does not require the terminal state to be
    the accepted terminal release state.
  evidence: `p0b_reducer.py:447-466` performs the join only by event ID and
    ordinal. `predecessor_terminal` is contractually allowed at lines
    337-338, but `terminal_state` is not semantically checked. The positive
    fixture passes with `wait-prev` and `RELEASED`, yet the implementation
    would also accept a terminal event for a different wait or an unrelated
    terminal state.
  consequence: an unrelated earlier event can satisfy the claimed FIFO
    predecessor/terminal leg, so `fifo_retry` may become true without proving
    that the immediately declared predecessor released before this waiter was
    granted. This violates R79/R54's exact-key predecessor lineage requirement.

- severity: MEDIUM
  disposition: fix before execution or explicitly document as a reviewed
  boundary and add tests
  defect: driver failure classification treats every caught HTTP error as
    `NOT_VERIFIED` during holder/target create and abort. A server-side HTTP
    5xx is represented by `HTTPError` and therefore follows the non-HTTP
    infrastructure branch test incorrectly, despite being an infrastructure
    failure candidate. Conversely, only connection-level failures reliably
    map to `BLOCKED`.
  evidence: `p0b_driver.py:125-127` stringifies all HTTPError/URLError values;
    lines 148-150, 159-161, and 184-186 classify by substring `"HTTP"` rather
    than error class or an explicit infrastructure/public-create distinction.
  consequence: the required distinction “public create inability =
    NOT_VERIFIED; infrastructure failure = BLOCKED” is not robust for HTTP
    service failures. A live outage can be mislabeled as inability, weakening
    the execution stop record.

plausible_risks:
- Event contracts validate field presence and many comparisons, but do not
  comprehensively validate every scalar type/enumeration. This is a robustness
  risk, not counted as a confirmed rejection defect because the accepted
  positive chain and tested malformed boundaries are otherwise fail-closed.
- The reducer's `positive_full_hit` joins accepted target admission with KV and
  sidecar records through the single lifecycle tuple rather than explicit
  admission/event IDs. The single-lifecycle invariant makes this substantially
  safer, but a future schema with multiple same-lifecycle admissions would
  need an explicit request join.
- No live raw bundle exists. As R54/R67/R79/R94 implementation report state,
  public create reachability, HOST_ALLOC reachability, telemetry population,
  and final READY remain unproven.

unsupported_concerns:
- No evidence supports a claim that the package performs simulation,
  instrumentation, product modification, remote execution, or Git changes.
  README and code inspection support the opposite.
- The self-test's synthetic positive fixture is not itself a runtime
  acceptance claim; it is evidence of reducer behavior only.

followups:
- Correct the abort payload to the exact R67 contract, including an explicit
  `abort_all` value, then update the manifest and tests.
- Require predecessor terminal `wait_id == predecessor_wait_id` and the exact
  accepted terminal state; add adversarial tests for unrelated terminal events
  and wrong terminal states.
- Classify HTTP service/infrastructure failures explicitly and test 5xx,
  connection refusal, malformed public create, and redirect cases separately.
- Re-run the package self-tests and independent static review after the fresh
  revision. Do not transfer or execute this R94 package.

open_issues:
- R95 report was requested as input but is absent at
  `work/P0-B-R94-REVIEW-PREP-20260911-R95.md` in the canonical workspace.
- No live evidence bundle can resolve the confirmed harness defects or close
  P0-B.
