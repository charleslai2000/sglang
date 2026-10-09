# Handoff — 3060 Qwen3.5-4B Ready Horizon follow-up

Date: 2026-09-10  
Status: **paused by user; no further work authorized in this session**

## Objective

Continue the independent RTX 3060 12G Qwen3.5-4B AWQ/Marlin + FP8 KV + HiCache
experiment. The current blocking issue is Ready Horizon re-trigger behavior under
`SPEC_BUDGET`; RH is not accepted yet.

## Workspace and branch

- Product workspace: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- Branch: `3060-12g-qwen35-4b`
- 3090 production-candidate state machine was not intentionally changed.
- Memory bus: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design`

The working tree has an **uncommitted, unreviewed** RH fix in exactly:

- `python/sglang/srt/managers/scheduler.py`
- `3090-dev/test_ready_horizon_unit.py`

Do not commit or deploy it until independent review and focused verification pass.
Untracked `.memory/`, `storage/`, and existing review artifacts are present; do not
bulk-clean them.

## Confirmed prior commits

- `03a170ef4f35fe1d87d80a7b6f09e83261aef94e` — nullable RH telemetry fix
- `1a8879750de9560a9acb3710357a45c115d4ac09` — RH telemetry failure marker
- `a96dc148c208d31d6c4b291370ee4e233063c60a2` — tensor-bool telemetry fix

The last commit has an independent PASS gate at:
`review/gates/REVIEW-20260910-RH-TENSOR-BOOL-FIX-R3.md`.

## 3060 environment

- SSH target: `root@i-1.gpushare.com:27460`
- Key: `/home/dev-codex/.ssh/sglang_3060_ed25519`
- Remote checkout: `/root/sglang-3060-12g-hicache`
- Venv: `/root/sglang-env-3060-4b`
- Model: `/hy-tmp/models/Qwen3.5-4B-AWQ`
- Last observed `/health`: HTTP 200
- Last observed GPU processes: target SGLang process plus a separate Neuron process;
  only the exact target SGLang process may be stopped in future work.
- Last observed free disk: root about 14G; `/hy-tmp` about 6.6G. Do not create
  additional large 55K-session stores without checking space.

## Completed 3060 evidence

Reports under `memory_root/work/`:

- `OPS3060-AWQ-RUNTIME-AUDIT-20260910.md`: AWQ W4A16 compressed-tensors/Marlin,
  weight load about 3.85GB, Mamba device state about 2.59GB, FP8 KV, graph pass.
- `OPS3060-BF16-CORRECTNESS-SMOKE-R3-20260910.md`: one BF16 correctness smoke only;
  not a capacity/performance profile.
- `OPS3060-DECODE-CONCURRENCY-SWEEP-R1-20260910.md`: c1/c2/c4/c6/c8 all HTTP 200;
  aggregate output TPS 87.64/24.24/48.83/73.06/98.09 respectively; c2-c8 per-request
  throughput around 12.2 tok/s.
- `OPS3060-CONTEXT-CAPACITY-R3-20260910.md`: 64K, 128K, 192K completed; allocator
  ceiling around 193,294 tokens, so 256K was rejected explicitly rather than OOM.
- `OPS3060-HICACHE-RESTORE-R3-20260910.md`: deterministic 55K GPU/Host/L3 path passed;
  GPU e2e about 0.230s, Host e2e about 0.391s, L3 e2e about 38.301s. Durable gate
  used KV plus all Mamba rank ACKs, not fixed sleep.
- `OPS3060-RH-QUEUE-COMPARE-R1-20260910.md`: initial RH queue comparison; RH was not
  accepted.
- `OPS3060-RH-HORIZON-COMPARE-R2-20260910.md`: pre-fix blocker-horizon causal trace.

## Current defect and minimal patch

The deep-debug report is:
`work/DEBUG3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`.

Root cause: request B was parked with a `SPEC_BUDGET` negative-cache cursor captured
before request A issued. The cursor was `0`; after A's speculative budget was released,
the current counter was also `0`, so the strict wake condition (`current < cursor`) did
not re-trigger B. B then missed RH staging and fell into full runtime recompute.

The local patch:

1. Captures post-issue speculative epochs after the prefetch result.
2. Uses that post-issue cursor for `SPEC_BUDGET` parks.
3. Keeps physical-only limiter semantics separate and unchanged.
4. Adds a unit test for cursor wake after budget release and a regression test that a
   physical-only limiter does not create a speculative-budget park.

Coder report:
`work/CODER3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`.

Local checks already reported passing: `git diff --check`, `py_compile`, and compileall.
The local focused unittest was blocked by missing local `orjson`; the remote venv was
then confirmed to contain `orjson 3.12.0`, `torch 2.6.0+cu124`, and `pytest 9.1.1`.

## Critical pre-fix live evidence

Same live blocker plus queued A/B approximately-55K sessions, `max_running_requests=1`:

| mode/request | e2e | cached device | cached storage |
|---|---:|---:|---:|
| RH OFF A | 21.668s | 54976 | 54976 |
| RH OFF B | 46.008s | 54976 | 54976 |
| RH ON A | 21.467s | 54976 | 54976 |
| RH ON B | 51.412s | 54976 | 0 |

RH ON event counts: `rh_stage=1`, `rh_stage_failure=0`, `ready_host=6`,
`admission=4`, `restore_success=1`. The log chain shows B held at `SPEC_BUDGET`,
then remained negative-cached after the speculative counter returned to zero.

Conclusion: RH eligible Host-ready-before-admission is not yet proven; do not enter
100/500/1000 parked-fleet testing.

## Exact next steps for successor

1. Re-read this handoff and the debugger/coder reports.
2. Independently review the two-file diff and write:
   - `review/gates/REVIEW-20260910-RH-SPEC-BUDGET-RETRIGGER.md`
   - corresponding report under `memory_root/work/`.
3. Copy only the two changed files to the remote checkout and run the focused unit
   test with the remote venv. Do not restart the live service for unit testing.
4. If review and focused test pass, commit only the two tracked product/test files.
5. Deploy that commit to the exact RH-ON c1 profile, preserving storage on `/hy-tmp`.
6. Re-run the identical blocker+A/B horizon trace. Acceptance requires B to wake after
   the speculative budget release, obtain a completed RH stage/Host-ready state before
   admission, avoid `cached=0`, and show no full-history recompute.
7. Record fixed live evidence and only then decide whether RH OFF/ON comparison can
   proceed. Keep RH OFF baseline and all prior reports unchanged.

Suggested remote health check:

```bash
ssh -o BatchMode=yes -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 \
  root@i-1.gpushare.com 'curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:30000/health'
```

Do not treat a report from a stopped child invocation as evidence. At pause time the
independent reviewer and test-runner had been dispatched but were shut down by the user
before their reports were produced; their results are therefore **pending/unavailable**.
