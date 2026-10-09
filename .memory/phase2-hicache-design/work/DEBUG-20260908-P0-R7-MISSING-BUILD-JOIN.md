ENTRY: ACCEPT

# DEBUG-20260908-P0-R7-MISSING-BUILD-JOIN

- Task ID / epoch: `DEBUG-20260908-P0-R7-MISSING-BUILD-JOIN` / `2026-09-08`
- Role: `debugger-deep`
- Invocation status: `blocked`
- Signal: `NEEDS_REASONING` — the exact failed producer guard requires new
  guard/outcome telemetry or a controlled reproduction. R7 preserved neither.

## Finding

R7 has three independently fatal faults.

1. **Run-ID propagation failure — confirmed.** Assigned R7 run ID is
   `p0-s25-v43-fix2-live-20260907T232817Z`; every retained engine trace record
   (including all 17 complete V3 durability barriers) has `run_id=pid-1007000`.
   The reducer rejects wrong-run events before session state and `event_refs`
   (`p0_session_barrier_vehicle.py:217-232`). This alone prevents every join.

2. **Tailer failure — confirmed effect; exact bytes not retained.** All 25
   barrier waits report `invalid JSONL: Expecting value: line 1 column 1
   (char 0)` and no `event_refs`. `EventTailer` makes parse error sticky
   (`:421-458`), so every wait fails. The final trace copy is completely valid
   JSONL; it contains neither the transient bad bytes nor their offset. A
   concurrent partial-line read is consistent with `readline` then immediate
   `json.loads`, but external/non-JSON input cannot be excluded.

3. **Zero `build_complete` — absence confirmed, exact suppressing check not
   recoverable.** The accepted FIX2 source was deployed, V3 tracing was active,
   and R7 reaches the raw radix-native completion path. The only emitter call
   (`unified_radix_cache.py:1883-1893`) has no per-guard telemetry, and its
   logger swallows all exceptions (`:217-229` outer handler). R7 therefore
   cannot distinguish result/node absence, context/RID mismatch, node lookup or
   empty hash, exact context-readback conflict, or logger write failure. Naming
   one would be speculation.

## Reconstruction and rejected hypotheses

The vehicle sends top-level `session_id` and `stream: true`
(`p0_session_barrier_vehicle.py:801-813`). With
`--enable-session-radix-cache`, that is a radix-native **normal** request,
not legacy `StreamingSession`: `scheduler.py:2638-2644` selects the normal
path and `:2655-2704` makes `Req` then assigns session generation. Thus the
legacy streaming-wrapper early return is not R7's cause.

The normal finished path calls `release_kv_cache` only when `req.finished()`;
that means `finished_reason is not None` (`schedule_batch.py:1319-1321`,
`batch_result_processor.py:1157-1189`). All 25 vehicle build rows are HTTP 200
with `finish_reason=length`. R7 has TP=1, and cache construction sets
`tp_world_size=1` without a TP group (`unified_radix_cache.py:601-609`). Its
strategy is `extra_buffer`, while the lazy insertion route applies only to
`extra_buffer_lazy` (`runtime_context.py:1544-1549`). These facts reject stale
deployment, marker-off, `finished_reason=None`, TP leader, lazy-insert, and
legacy streaming-wrapper explanations.

The remaining unobserved emitter checks are `unified_radix_cache.py:902-947`:
result/node, V3 request context, request/build RID equality, node lookup/hash,
and exact node-context readback. The trace proves the marker is active, but it
does not record outcomes for these checks.

## Direct evidence

Read-only remote root:
`/root/evidence-gate3-parked/p0-s25-v43-fix2-live-r7`.

- `vehicle/trace-copy.jsonl`: 1,061,093,967 bytes; 980,706 valid retained
  records; 979,731 V3, 975 V2, zero `build_complete`, 17 durability barriers.
- Every retained record has `run_id=pid-1007000`. A barrier is otherwise
  complete: V3, session/build/node/hash, `kv_durable=true`,
  `mamba_durable=true`, and `combined_durable=true`.
- `barrier-waits.jsonl`: 25/25 HTTP 200 and finished builds, 25/25 tailer
  error, 25/25 empty `event_refs`. Verdict: `F_unresolved=25`, `NOT_VERIFIED`.
- Evidence SHA-256: trace copy
  `9bb9e36a8345f75beb09a2c5b3d5cd0b5ef1ed73bfe1f56301778ccb374cda2e`;
  barrier waits
  `0ed578e6e5c9bb747d89e76649773f4c2df0ff1ca1f17cbb026380d9dec3d5c3`.

Current remote hashes:

| File | SHA-256 |
| --- | --- |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | `0aba7eafb701d8855fc370cc7a43302f618512e9992f2319784b1cbcc0d4a873` |
| `3090-dev/p0_session_barrier_vehicle.py` | `c557300fe8f287a4ef10c5105a89bd48e3c8f2c01d0621700da362031d1db5bc` |
| `3090-dev/direct-launch-gate3-parked.sh` | `8d59823b64ab7359b113c7ed790e22d1903ac3d529b837421777b14c81401b09` |

## Minimal fixes, in ownership order

1. **coder:** fresh marker-gated diagnostic task: record one structured
   outcome for every emitter return and logger failure (guard name, run/session/
   build IDs, node type/ID, hash presence). Run one controlled session to
   identify the exact remaining producer condition.
2. **coder:** repair only that confirmed condition; add a fixture for the
   radix-native top-level-session path. Never synthesize a producer event in
   the vehicle.
3. **devops:** export/assert the same fresh `T38C_RUN_ID` in the engine before
   exec and capture its environment before traffic. `pid-1007000` is exactly
   the logger fallback at `unified_radix_cache.py:229`.
4. **vehicle owner/coder:** buffer an unterminated trailing JSONL record and
   retry on poll; only a completed malformed record becomes fatal, retaining
   byte/line evidence. Keep strict failure for genuine malformed JSONL.
5. **tester, then devops:** independently test all three faults, then perform
   a new authorized run/evidence namespace.

## Followups and open issues

- `NEEDS_REASONING`: authorize the focused producer guard probe or controlled
  reproduction. No current artifact can determine the exact guard or bad bytes.
- R7 remains `NOT_VERIFIED`. No product, vehicle, launcher, remote files,
  storage, logs, processes, or run were changed.

