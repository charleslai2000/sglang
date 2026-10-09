# COD-20260908-P0-LIVE-VEHICLE

- Task ID: `COD-20260908-P0-LIVE-VEHICLE`
- Epoch: `E20260908-P0P1P2`
- Role: `coder`
- Invocation status: `blocked`
- Admission: `ACCEPT`
- Result: `NEEDS_REASONING`

## Evidence

The current `p0_durable.v2` implementation in the five-file product trace
does not expose the exact vehicle join required by P0. The observed event
families carry `node_id` and/or `final_kv_hash` and operation metadata, but do
not carry the complete identity tuple on the records needed to prove one
session's chain:

```text
session_id -> build_rid -> final_kv_hash/node_id
```

In particular, the current backup submission, batch result, ACK enqueue/drain,
storage-persisted, storage-query, and residency records do not consistently
carry `session_id` and `build_rid`. The current trace also does not publish a
keyed `durability_barrier(combined_durable=true)` event. A timestamp or
operation-order correlation cannot repair this: the P0 contract explicitly
rejects timestamp-only joins.

The current parked client exposes the build request id only in the client-side
response row. `gate3_parked.py` does not propagate that id into the product
storage/residency trace, and it cannot be edited under this dispatch.

## Required smallest hook

Add an additive, marker-gated product trace correlation hook in the existing
five-file trace scope that propagates the vehicle metadata into every relevant
event for the operation:

```text
session_id, session_generation, build_rid, warm_rid?,
node_id, final_kv_hash, operation_id/attempt_id
```

The hook must also emit, after the existing causal checks complete:

```text
durability_barrier: combined_durable=true
residency_barrier: cold_residency=true
```

Both barrier records must contain the same explicit session/build/node/hash
identity. The vehicle can then wait on those records and issue the normal
Qwen3.5-9B warm request only after both barriers. No scheduler change, fixed
sleep, KV-only acceptance, or timestamp join is needed.

## Scope decision

The requested live implementation cannot be completed honestly with the
current five-file trace and the authorized `3090-dev` scope. Implementing a
synthetic fallback, inferring the join from timestamps, or treating
`storage_persisted` as combined durability would weaken the gate. Therefore
the live vehicle remains blocked pending the product correlation hook and a
fresh coder dispatch that authorizes the resulting driver/parser changes.

## Verification

No remote execution was performed. No product file, `gate3_parked.py`,
launcher, or remote file was changed in this invocation. Existing behavior is
fail-closed: synthetic fixture mode is explicitly `--dry-run` and reports
`NOT_VERIFIED`; live mode must not manufacture a PASS without the exact join.

## Open issue

`py_compile`/`git diff --check` for a new live implementation are not claimed,
because the exact join prerequisite is unresolved and no source edit was
authorized or safely applicable in this status-finalization invocation.
