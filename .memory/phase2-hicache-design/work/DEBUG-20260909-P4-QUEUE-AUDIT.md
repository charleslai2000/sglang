# DEBUG-20260909-P4-QUEUE-AUDIT

```text
status: done
task_id: DEBUG-3060-P4-QUEUE-AUDIT-20260909
orchestration_epoch: 20260909-p4-queue
role: debugger-deep
scope: read-only diagnosis of the authorized RTX 3060 logs, probe trace, and source
```

## Finding

The `2 restore / 3 recompute` outcome was caused by **scheduler prefetch-budget
admission plus a 60-second bounded wait under a single-running-request/device
profile**.  It was not caused by an L3 storage lookup miss, a Mamba sidecar
miss, or a durable-frontier miss for the three recomputes.

All five requests entered the same L3-eligible root-anchor path.  Only `s0`
and `s2` received a prefetch ticket.  The other three were synchronously
declined as `declined_rate_limited`, entered
`WAIT_CAPACITY reason=PREFETCH_BUDGET`, made no storage query at all, and
were released to recompute by T13 approximately 60 seconds later.

## Runtime and source baseline

The server arguments recorded at `05:43:57` for this run include:

- `enable_hierarchical_cache=True`, `enable_ready_horizon=False`,
  `hicache_host_memory_mode='cache'`, `hicache_storage_backend='file'`, and
  `hicache_storage_prefetch_policy='wait_complete'`.
- `hicache_restore_wait_timeout_s=60.0`, `max_running_requests=1`, and
  `max_total_tokens=65536`.
- `hicache_ratio=2.0` and `mamba_full_memory_ratio=0.9`.

This run's `hicache_ratio=2.0` differs from the `1.3` launch recorded in
`TEST-20260909-3060-P4-HICACHE.md`; it is a reproducibility-relevant
configuration difference, not proof by itself of the fault.

The host source directory is not a Git worktree, so its commit cannot be
read there.  The relevant runtime source bytes do match the assigned local
`3060-12g-qwen35-4b` branch (`277dd611001c31edcd3a8894213c5a44b00e9bd4`):

```text
980a525d...  scheduler.py
43b57f5a...  cache_controller.py
6241f568...  scheduler_components/hicache_restore.py
```

The same SHA-256 values were read from the remote source and the assigned
local worktree.

## Per-request timeline and evidence

| Request | Initial outcome at 05:50:47 | Lookup / hybrid evidence | Terminal result | Diagnosis |
| --- | --- | --- | --- | --- |
| s0 `9e6addef...` | `prefetch_issued` at `4247.267` | `pc_storage_query`: `kv_hit_pages=54976`, `sidecar_hits={kv:54976,mamba:54976}`; Mamba sidecar fetch reports `hit_pages={mamba:1}`; `pc_l3_host completed_tokens=54976` at `4288.265` | `restore_success n_tokens=54976` at `05:51:28` | Partial L3 KV+Mamba restore; no storage/Mamba miss. |
| s1 `8b8f7acb...` | `declined_rate_limited` at `4247.505`; host event says `WAIT_CAPACITY reason=PREFETCH_BUDGET` | No `pc_storage_query`, no KV batch, and no Mamba-sidecar read for this RID | `restore_recompute cause=timeout final_storage_survivability=host` at `4307.505` | Budget/timeout before lookup, not an L3 or Mamba miss. |
| s2 `dd6b3e0c...` | `prefetch_issued` at `4247.386` | `pc_storage_query`: `kv_hit_pages=54976`, `sidecar_hits={kv:54976,mamba:54976}`; Mamba sidecar `hit_pages={mamba:1}`; `pc_l3_host completed_tokens=54976` at `4313.943` | `restore_success n_tokens=54976` at `05:52:17` | Partial L3 KV+Mamba restore; delayed resource/promotion path, not a lookup miss. |
| s3 `e9fc1f70...` | `declined_rate_limited` at `4247.745`; `WAIT_CAPACITY reason=PREFETCH_BUDGET` | No storage query or sidecar read | `restore_recompute cause=timeout final_storage_survivability=host` at `4308.391` | Budget/timeout before lookup. |
| s4 `352df0fe...` | `declined_rate_limited` at `4247.626`; `WAIT_CAPACITY reason=PREFETCH_BUDGET` | No storage query or sidecar read | `restore_recompute cause=timeout final_storage_survivability=host` at `4307.714` | Budget/timeout before lookup. |

The probe's cumulative counter moves corroborate the ordered split: `s0` is
the ninth issued request, `s2` the tenth; the subsequent s1/s4/s3 attempts
increase `declined_rate_limited` from 1 to 3.  The apparent input order is
not a storage-result ordering: s2 (the third listed request) was issued
before s1, s4, and s3 were denied.

## Reconstructed causal chain

1. At `05:50:47.267`--`.745`, all five requests passed the L3 gate.  Each
   probe record has `l3_enabled=true`, `gate_pass=true`, a root anchor, and
   a 55,000-token suffix.  Therefore neither a non-durable frontier nor a
   non-issuable anchor selected the three recomputes.
2. s0 and s2 were issued.  s1, s4, and s3 were denied *at issue time* by the
   prefetch limiter.  The scheduler maps `DENIED_RATE` to
   `WAIT_CAPACITY/PREFETCH_BUDGET`; this is exactly the state logged for
   every recompute RID.
3. The successful paths demonstrate that their storage contents existed and
   that the hybrid Mamba sidecar could be read.  s0's key batches run until
   `4288.156`; s2's first key batch appears at `4288.804`, then completes at
   `4313.406`.  This is a serialized/queued storage-service shape, not three
   independent simultaneous storage lookups.
4. s0 finalized and reserved `54976` full-KV tokens at `05:51:28`
   (`full_locked=54976`).  s2 could not reserve/prompt until `05:52:17`,
   where the log records only `full_free=10560` plus `full_evictable=54976`.
   With `max_running_requests=1`, the device/promotion path remained a real
   capacity constraint while the three requests waited.
5. Each denied request expired at about `60.0` seconds: s1 `60.001 s`, s4
   `60.089 s`, and s3 `60.646 s` after its denial.  s2's L3 host completion
   was later, at about `66.56 s` after issue.  There is no
   `restore_retry cause=capacity` for any of the three before T13, followed
   by their logged `restore_recompute cause=timeout`.

The matching source explains the state shape.  Cache mode gives prefetch a
budget of half the host pool (`prefetch_capacity_limit = 0.5 * host_pool`),
and the scheduler will retry a `PREFETCH_BUDGET` waiter only when its
capacity predicate passes.  That predicate includes the prefetch limiter and
later the device admission charge.  Thus the observed root cause is a
controller-level host/device resource admission and queue-timeout interaction.

## Competing hypotheses

| Hypothesis | Verdict | Evidence |
| --- | --- | --- |
| L3/file lookup miss | Rejected for s1/s3/s4; rejected for s0/s2 | The three denied RIDs never call `pc_storage_query`; s0/s2 report 54,976 KV hits. |
| Mamba durability/frontier miss | Rejected as the cause of this 3-recompute split | All root-anchor gates pass; s0/s2 have explicit Mamba sidecar hits.  The denied RIDs never reach sidecar lookup. |
| Host/device prefetch capacity plus queueing | Confirmed as the immediate cause | Exact `declined_rate_limited` -> `PREFETCH_BUDGET` -> T13 `timeout` chain for all three; full-pool lock/promotion evidence and single-running-request launch profile. |
| Physical host OOM, disk failure, or storage thread crash | Not evidenced | No `HOST_ALLOC`, storage-fatal, I/O error, or failed Mamba fetch is joined to these five RIDs.  This run lacks contemporaneous CPU/RAM/disk telemetry, so physical-resource headroom is not independently quantified. |

`final_storage_survivability=host` is a state snapshot at timeout; it is not
evidence that a host allocation failure caused the timeout.  In particular,
the causal event already recorded for all three is `denied_rate_limit`.

## One recommended next experiment

Under a fresh task, rerun the identical five-request RH-OFF queue with only
`hicache_restore_wait_timeout_s=240` (keep `max_running_requests=1`, storage
path, model, and 55K prompts fixed).  The oracle is per denied RID: after a
capacity release it must emit `restore_retry cause=capacity`, then
`pc_storage_query` with KV and Mamba sidecar hits, and finally
`restore_success`; there must be no `restore_recompute cause=timeout`.

This isolates the bounded-queue hypothesis without widening the host/device
budget.  If the retries still do not appear before 240 seconds, the next
owner should instrument/fix the capacity-wake predicate or its release epoch,
not diagnose storage durability.

## Open issues / missing evidence

- The trace does not log the evaluated values of `_restore_wait_capacity_fits`.
  It proves the initial budget denial and absence of retries, but does not
  separately measure how much of the later wake block was host-budget versus
  device-charge failure.
- No contemporaneous OS CPU/RAM, disk latency, or host-pool size sample was
  captured.  The conclusion is about the observed controller resource gate,
  not an unmeasured physical saturation claim.
- This audit does not overturn the earlier P4 hybrid-Mamba missing-key finding
  for a different request.  It establishes only that it did not cause the
  specific s0--s4 queue split.

## Artifacts and evidence sources

- Remote `/tmp/sglang3060-p4-host.log` (35,176,849 bytes at audit)
- Remote `/tmp/t38c-probe.log` (59,556,918 bytes at audit)
- Remote `/root/sglang-3060-12g-hicache` source checksums
- Local assigned branch `3060-12g-qwen35-4b`, commit
  `277dd611001c31edcd3a8894213c5a44b00e9bd4`
- Designated prior reports: `TEST-20260909-3060-P4-HICACHE.md` and
  `HANDOFF-2026-09-07.md`

No remote files, services, product files, or the 3090 branch were modified.
