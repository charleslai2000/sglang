# B5/B6-R2 A audit

The old harness did not include the previous assistant response in the next request. It built each prompt from synthetic user-side `history` only; it did not use a chat template and did not reconstruct an assistant turn. It also used long opaque identity output as a free-form oracle.

Offline token audit of the old prompt construction (10 sessions, all 5 turns):

```text
turn transition       previous len  LCP  LCP/previous
0 -> 1                       75      59       0.787
1 -> 2                       93      77       0.828
2 -> 3                      111      95       0.856
3 -> 4                      129     113       0.876
```

Different-session comparison (`session 0 turn 4` vs `session 1 turn 0`) had LCP 8 tokens. Thus same-session LCP was not intrinsically short and the old prompts were distinct across sessions, but the old harness was not a faithful conversation replay: assistant responses were absent and each request was independently serialized as plain text. The old zero-hit result cannot be used to diagnose the cache mechanism because it did not run the required micro device-hit/host-hit gates and its effective reuse trace was not validated by runtime counters.

R2 must use append-only, stable per-session context, a short machine-parseable code oracle, offline token-ID audit, and the micro gates before any 200-session benchmark.
