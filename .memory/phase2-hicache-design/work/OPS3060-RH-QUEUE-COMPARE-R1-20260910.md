# OPS3060-RH-QUEUE-COMPARE-R1-20260910

## Workload

- Two distinct, previously durable 55K sessions A/B were submitted behind a
  live blocker request (80 prompt tokens, 2,048 generated tokens).
- `max_running_requests=1`, AWQ W4A16/Marlin, FP8 E4M3 KV, Graph ON,
  HiCache file backend on `/hy-tmp/hicache-restore-r3`.
- The blocker creates a real prediction horizon; the blocker plus A/B trace was
  identical between RH OFF and RH ON.

## OFF/ON request results

| Mode | Request | HTTP | Cached device | Cached host | Cached storage | Wall/e2e |
|---|---|---:|---:|---:|---:|---:|
| OFF | blocker | 200 | 0 | 0 | 0 | 23.37/23.36 s |
| OFF | A | 200 | 0 | 0 | 54,976 | 21.68/21.67 s |
| OFF | B | 200 | 0 | 0 | 54,976 | 46.02/46.01 s |
| ON | blocker | 200 | 0 | 0 | 0 | 23.20/23.19 s |
| ON | A | 200 | 0 | 0 | 54,976 | 21.48/21.47 s |
| ON | B | 200 | 0 | 0 | 0 | 51.42/51.41 s |

The ON blocker and A are normal. B is the critical failure: it lost the cache
and ran with `cached_tokens=0` despite being a durable L3 session in the queue.

## Live RH evidence

ON emitted one `rh_stage.v2` and one `rh_ready_host.v1` for A. B's
preadmission records show:

1. B was RH eligible while A/B were both in the frontier.
2. A was issued and consumed `speculative_used_tokens=54999` against a
   `speculative_budget_limit_tokens=39321`.
3. B was held/parked with `reason=speculative_budget`.
4. After A finalized, `spec_budget` became 0, but B remained in the negative
   cache with `reason=negative_cache` and `negative_cursor=0`; no second
   `rh_stage.v2` was emitted.
5. B then entered the runtime path with no cached tokens.

This is an RH staging miss, not a storage miss: the OFF trace restores B from
L3 successfully, while ON prevents the second pre-admission stage.

## Verdict

- RH eligible Host-ready-before-admission rate for the two parked sessions is
  1/2 (50%), below the required 95%.
- RH ON does not yet convert the queued workload to a Host-ready path. It
  improves neither B's path nor the two-session trace's worst-case TTFT.
- The exact negative-cache/spec-budget re-trigger defect is being handed to a
  source debugger for an independent causal report before any code change.
- No broad fleet or 8-session claim is authorized from this result.

