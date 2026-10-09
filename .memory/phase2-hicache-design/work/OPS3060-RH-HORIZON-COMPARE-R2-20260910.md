# 3060 RH blocker-horizon A/B trace — 2026-09-10

## Scope

RTX 3060 12G, Qwen3.5-4B AWQ/Marlin, FP8 KV, CUDA Graph ON, HiCache file backend, `max_running_requests=1`, RH OFF/ON on the same blocker-plus-two-parked-session trace. This is a pre-fix diagnosis run; it is not an acceptance result for RH.

## Trace shape

1. Submit one live blocker: 80 prompt tokens, 2048 generated tokens.
2. Submit two deterministic approximately-55K parked requests A/B while the blocker holds the only running slot.
3. Compare RH OFF and RH ON with the same storage directory and request order.

## Observed results

| mode/request | HTTP | wall/e2e (s) | cached device | cached storage |
|---|---:|---:|---:|---:|
| RH OFF blocker | 200 | 23.366 / 23.358 | 0 | 0 |
| RH OFF A | 200 | 21.682 / 21.668 | 54976 | 54976 |
| RH OFF B | 200 | 46.020 / 46.008 | 54976 | 54976 |
| RH ON blocker | 200 | 23.200 / 23.193 | 0 | 0 |
| RH ON A | 200 | 21.480 / 21.467 | 54976 | 54976 |
| RH ON B | 200 | 51.424 / 51.412 | 54976 | 0 |

RH OFF event counts: `rh preadmission=0`, `rh_stage=0`, `ready_host=8`, `admission=5`, `restore_success=2`.

RH ON event counts: `rh preadmission=10`, `rh_stage=1`, `rh_stage_failure=0`, `ready_host=6`, `admission=4`, `restore_success=1`.

## Causal finding

The RH ON log shows A issuing while B enters `state_funnel` hold. After A issues, B is parked with `SPEC_BUDGET`; the speculative counter becomes `54999` against a limit of `39321`. When A is ready and the counter returns to zero, B remains in the negative cache with cursor zero. The strict re-trigger condition therefore does not fire (`current speculative inflight 0 < stored cursor 0` is false). B receives no completed RH stage and falls through to a full runtime recompute (`cached=0`), explaining the 51.424s path.

This is consistent with the deep-debug report: the negative-cache cursor was recorded before A's issue instead of after the issue. The physical-only limiter semantics are separate and must remain unchanged.

## Gate status

NOT VERIFIED / pre-fix blocker. The run proves the RH horizon has a real re-trigger defect, not a node lookup or storage durability defect. Do not scale to fleet testing or claim RH success until the minimal SPEC_BUDGET cursor fix passes independent review, focused test, and the same live trace.

## Evidence

* `work/DEBUG3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`
* `work/CODER3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`
* `escalations/ESC-20260910-RH-SPEC-BUDGET-RETRIGGER.md`
