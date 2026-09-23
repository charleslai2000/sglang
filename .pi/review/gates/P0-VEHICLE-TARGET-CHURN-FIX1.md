ENTRY: ACCEPT

# P0 vehicle target-churn FIX1 independent gate

- Task ID: `REV-20260908-P0-VEHICLE-TARGET-CHURN-FIX1`
- Orchestration epoch: `phase2-hicache-design / 2026-09-08`
- Role: `reviewer`
- Invocation status: **done**
- Admission: **ACCEPT**
- Gate verdict: **ACCEPT**

## Scope and inputs

Read-only review of:

- `tools/p0_session_barrier_vehicle.py`
- `test/registered/unit/mem_cache/test_p0_trace_context_v4.py`
- `COD-20260908-P0-VEHICLE-TARGET-CHURN-FIX1.md`
- `ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`
- `ledger.md`

No reviewed Python artifact or fixture was modified. Only this gate report and
the assigned reviewer report were written. No engine, launcher, remote host, or
live endpoint was run.

## Verdict summary

ACCEPT. All seven acceptance criteria are evidenced locally. The vehicle runs
all 25 target build futures to completion, then runs exactly nine deterministic
auxiliary builds (`CHURN_COUNT = FROZEN["active"] + 1`) before entering the
warm scheduler. Churn uses unique session IDs and seeds 25 through 33, checks
history digests for target/churn and intra-churn collisions, records each row in
separate churn evidence, and fails closed on any request/build admission error.
Successful churn identities are established only after HTTP/terminal/response
ID admission and churn data never enters target planned/eligible/warm/pass rows.

The existing target gate remains exact: build identity plus KV and Mamba
durability evidence, ordered combined durability, ordered cold residency, no
early lookup, complete SSE, and a bounded warm watchdog are required. The
supplied live acceptance remains unverified and is not claimed by this local
implementation gate.

## Requirement review

| Requirement | Result | Evidence |
|---|---|---|
| Exactly 9 deterministic auxiliary churn builds with distinct histories | PASS | `p0_session_barrier_vehicle.py:55`, `:922-1034`; fixed `CHURN_COUNT=9`, IDs `p0-s25-churn-00000..00008`, seeds `25..33`, target and intra-churn SHA-256 collision checks. Focused fixture `test_p0_trace_context_v4.py:1415-1480` and independent probe passed. |
| Churn HTTP/build/finished/ID failures fail closed and are reported separately | PASS | `p0_session_barrier_vehicle.py:947-1012`, `:797-799`, `:815-819`, `:1282-1285`; per-row `failure`, separate `churn-builds.jsonl`, fatal errors, and warm scheduler suppression. Independent probe rejected HTTP, unfinished, and missing-ID churn responses. |
| Churn identity is established before successful churn admission/counting; no silent collapse | PASS | `p0_session_barrier_vehicle.py:963-1004`; `reducer.establish_build` occurs only after valid response admission; fixed IDs, response IDs, and history hashes are retained per row. Focused fixture confirms 9 reducer states and no target/churn row collapse. |
| Churn follows all targets and precedes warm scheduling | PASS | `p0_session_barrier_vehicle.py:1278-1295`; `_run_build_phase` returns before `_run_churn_phase`, and warm is called only in the no-churn-fail branch. Focused source-order assertion at `test_p0_trace_context_v4.py:1481-1484`. |
| Churn excluded from target accounting and cannot mask target failures | PASS | `p0_session_barrier_vehicle.py:932-935`, `:719-755`, `:1048-1049`; churn is absent from `build_rows`, planned IDs, eligible rows, warm contexts, and PASS quantifiers. Focused fixture confirms 25 target rows and zero churn rows in reducer/build-warm final accounting. |
| Existing warm gates remain exact | PASS | `p0_session_barrier_vehicle.py:364-378`, `:1073-1137`, `:1186-1219`; readiness requires exact identity, KV/Mamba, ordered durability/residency, no early lookup/errors, and worker recheck; response admission requires HTTP 200, terminal SSE, and response ID. Focused suite and prior FIX4 boundary probes pass. |
| Syntax and fixture compatibility | PASS | `PYTHONPYCACHEPREFIX=/tmp/codex-review-pycache python3 -m py_compile ...` passed; `python3 test/registered/unit/mem_cache/test_p0_trace_context_v4.py` returned `P0 trace-context V4.3 focused checks: PASS`; independent AST and whitespace checks passed. |

## Evidence executed

- `PYTHONPYCACHEPREFIX=/tmp/codex-review-pycache python3 -m py_compile /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/tools/p0_session_barrier_vehicle.py /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/test/registered/unit/mem_cache/test_p0_trace_context_v4.py` — **PASS**.
- `python3 /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/test/registered/unit/mem_cache/test_p0_trace_context_v4.py` — **PASS** (`P0 trace-context V4.3 focused checks: PASS`).
- Independent `ast.parse` over both authorized files — **PASS**.
- Independent adversarial churn probe — **PASS**: 34 calls total, 9 churn attempts, 3 independent failure classes (HTTP, unfinished, response ID), 25 target rows, churn rows excluded.
- `git diff --no-index --check /dev/null <authorized-file>` for both untracked authorized files — **PASS**, no whitespace diagnostics (expected comparison status 1).

## Findings

None blocking or non-blocking.

## Followups

- Proceed to the separately authorized fresh S=25 live run under a new Task ID.
- Preserve the exact target/churn separation and fail-closed accounting when
  consuming live evidence.

## Open issues

1. Live S=25 durability, residency, warm, and restore acceptance remains
   `NOT_VERIFIED`; this gate accepts only the local vehicle/fixture implementation.
2. The aggregate checkout remains dirty and the reviewed Python files are
   untracked; this is outside the authorized gate scope.

done
