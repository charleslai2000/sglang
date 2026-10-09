# P0-B R89 strict harness

This disposable package is an implementation artifact, not live P0-B acceptance.
It is restricted to the authorized RTX 3060 12G experiment, existing public HTTP,
and existing product-emitted `p0_durable.v3`, `host_alloc.v1`, `ready_host`, and
`restore_ready` evidence. It does not import SGLang, patch product code, add
telemetry, synthesize events, or control scheduler/allocator behavior.

## Bounds and ownership

`p0b_driver.py` accepts only the exact target label `RTX 3060 12G`, rejects URLs
mentioning 3090/production, uses at most six POST requests, and runs for at most
600 seconds. It submits ordinary `/generate` requests and may submit exactly one
`/abort_request` for the predeclared holder. Gate A runs against raw product
events before `/abort_request`; if the positive full-hit `WAIT_CAPACITY/HOST_ALLOC`
park is not present, the driver returns structured `BLOCKED` and never aborts.
After release, wake, retry, finalization, and READY remain product-owned.

The reducer is offline and fail-closed. Its parser reads raw JSONL and adds
absolute `file:line` references. It rejects normalized/synthetic `p0b.trace.v1`
input with `INVALID_INPUT`; it never constructs that schema. Missing evidence is
`NOT_VERIFIED`, not a pass. The only statuses are `PASS`, `BLOCKED`,
`NOT_VERIFIED`, and `INVALID_INPUT`.

## Exact eleven-item oracle

The reducer evaluates these stable items in order:

1. `provenance` — exact R89 task, epoch, RTX 3060 12G target, and source-file manifest.
2. `singular_identity` — all six lifecycle fields are present on every authoritative event.
3. `positive_full_hit` — complete KV span and every required sidecar are product evidence.
4. `host_alloc_park` — positive-hit full-span terminal `WAIT_CAPACITY/HOST_ALLOC` with cursor/FIFO.
5. `generation_transition` — exact contiguous per-pool `host_alloc.v1` edge and sequence.
6. `fifo_retry` — one generation-advanced eligible grant and one positive-hit retry.
7. `complete_restore` — all-or-nothing KV+sidecar restore and accepted finalization.
8. `ready_after_finalize` — authoritative READY follows the same attempt finalization.
9. `raw_provenance` — every derived event retains an absolute raw source reference.
10. `negative_safety` — no miss, crop, lower-frontier, self-wake, repeated retry, skipped predecessor, partial sidecar, discarded hybrid, or recompute fallback.
11. `single_lifecycle` — all joined records have exactly one six-field identity tuple.

`PASS` is possible only when all eleven are true. A valid but incomplete raw run
is `NOT_VERIFIED`; malformed input or a synthetic schema is `INVALID_INPUT`.

## Usage

The provenance file is an explicit JSON manifest, for example:

```json
{"task_id":"P0-B-HARNESS-IMPLEMENT-20260911-R89","epoch":"2026-09-11","target":"RTX 3060 12G","source_files":{"server.log":"SHA256"}}
```

Run the bounded driver only on the authorized 3060 target:

```sh
./p0b_driver.py --target-label 'RTX 3060 12G' --events /path/raw-events.jsonl \
  --provenance /path/provenance.json
```

Reduce immutable product evidence after the run:

```sh
./p0b_reducer.py --events /path/raw-events.jsonl --provenance /path/provenance.json
```

Run deterministic package checks with `./run_selftests.sh`. `manifest.sha256`
pins the five executable/source package files and intentionally excludes itself,
the report, and runtime evidence.
