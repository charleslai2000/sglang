# P0-B R97 strict raw-bundle harness

This disposable package is an implementation artifact, not live acceptance. It
is restricted to the authorized RTX 3060 12G experiment and existing public
HTTP endpoints. It does not import SGLang, patch product code, add telemetry,
synthesize events, or call scheduler/allocator internals.

## Immutable evidence contract

The reducer accepts only raw JSONL records emitted by these exact product
schemas and event names:

* `p0_durable.v3`: `durability_barrier`, `storage_query`, `storage_persisted`,
  `backup_ack_drain`;
* `host_alloc.v1`: `restore_host_alloc_wait`, `host_allocability_change`,
  `restore_host_alloc_wake_decision`, `restore_host_alloc_retry_result`,
  `restore_hybrid_finalize`;
* `rh_ready_host.v1`: `ready_host`.

The raw event file is never rewritten. The provenance manifest must be
`p0b.raw-bundle.v2`, immutable, bound to task `P0-B-HARNESS-IMPLEMENT-20260911-R97`
and epoch `2026-09-11`, and contain SHA256 maps for absolute `raw_files` and
absolute checked-out `source_files`. It also binds the runtime PID/worker and
the exact `RTX 3060 12G`, SM86 profile, capture completeness, and event-to-raw
`file:line` provenance. Global allocator mutation records may have null request
identity, but are joined only by exact cache instance, pool, and generation
edge. Hash mismatches and contradictory
records are `INVALID_INPUT`; absent files/edges/identity are `NOT_VERIFIED`.
Every result includes absolute `file:line` raw references.

No caller-authored summary fields are accepted. In particular, the reducer
does not consume `positive_hit`, `full_kv_hit`, `complete_kv`, `all_sidecars`,
`ready`, `accepted`, or a caller verdict. Full hit, contiguous per-pool
generation edges, FIFO predecessor ordering, retry attempt lineage, accepted
all-or-nothing finalization, and `rh_ready_host.v1` ordering are derived from
the exact product fields. PASS requires every oracle item.

## Bounded public driver

`p0b_driver.py` accepts only the exact target label and a required profile ID,
rejects 3090/production URLs, allows at most six POSTs and 600 seconds, and
uses the exact state machine:

1. `POST /generate` build RID;
2. `POST /generate` holder RID;
3. `POST /generate` target RID;
4. Gate A over raw evidence;
5. if Gate A passed, exactly one `POST /abort_request` with
   `{"rid":"<holder-rid>","abort_all":false}`.

Gate A cannot be created through the public interface => `NOT_VERIFIED`. A
transport or infrastructure endpoint failure => `BLOCKED` with an explicit
reason. The driver captures byte-for-byte raw events and provenance into the
requested evidence directory and makes those copies read-only. It never
simulates product events.

## Statuses

Only `PASS`, `BLOCKED`, `NOT_VERIFIED`, and `INVALID_INPUT` are emitted. A
bounded but incomplete or missing authoritative chain is `NOT_VERIFIED`.

## Usage

```sh
./p0b_driver.py --target-label 'RTX 3060 12G' \
  --profile-id rtx3060-sm86-r97 \
  --events /absolute/raw-events.jsonl \
  --provenance /absolute/provenance.json \
  --evidence-dir /absolute/captured-r97

./p0b_reducer.py --events /absolute/raw-events.jsonl \
  --provenance /absolute/provenance.json
```

Run `./run_selftests.sh` for the deterministic package checks. The manifest
pins all five source/executable files and excludes itself, the report, and
runtime evidence.
