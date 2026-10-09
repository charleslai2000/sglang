# TEST-20260909-P4-FRONTIER-GUARD

```text
status: done
task_id: TEST-20260909-P4-FRONTIER-GUARD
orchestration_epoch: 20260909-P4
role: tester
remote: root@i-1.gpushare.com:27460 (RTX 3060)
service_pid: 76671
reviewed_commit: 5b61e63993b65ee1fe6380f6bfab455e40b34270
overall_verdict: FAIL for full stressed restore reliability; guard-specific invalid-boundary oracle PASS
```

## Scope and safeguards

- Only the live 3060 service on port 30000 was exercised.
- SSH key: `/home/dev-codex/.ssh/sglang_3060_ed25519`.
- No product code, 3090 service, remote storage deletion, or service restart was performed.
- Remote evidence was read from `/tmp/qwen35-4b-hicache-p4-reconstruct-sm86-20260909-json.log`
  and `/tmp/t38c-probe.log`; neither log was modified or copied.
- The final report is the only local artifact written by this task.
- RH was not enabled or evaluated, and this test does not claim 100% durability.

## Deployment and runtime precondition

At `2026-09-09T07:10:11+08:00`, PID 76671 was alive and port 30000 was listening.
The command line matched the requested profile: Qwen3.5-4B AWQ, `max_running_requests=1`,
`hicache_ratio=2.0`, file backend, `wait_complete`, retry interval `1`, retry max attempts
`120`, restore timeout `180`, and no Ready Horizon flag. The process environment pointed at
`/root/sglang-3060-12g-hicache/python`.

Deployment identity was independently checked:

```text
remote unified_radix_cache.py sha256:
395e55efc4d472547581d2a33d7b989933fb78990cf4a455d8daa0e02845a203
local commit blob sha256 for 5b61e63993...:
395e55efc4d472547581d2a33d7b989933fb78990cf4a455d8daa0e02845a203
```

The deployed source contains `_storage_hit_crop_is_safe` and invokes it at the cache-mode
crop site before the `storage_hit_count`/`hash_value` mutation.

## Exact test commands and timestamps

Initial read-only baseline command, run at `2026-09-09T07:11:47+08:00`:

```text
ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com \
  'date --iso-8601=seconds; ps -p 76671 -o pid=,stat=,etime=,cmd=; \
   curl -sS -o /dev/null -w "%{http_code}" --max-time 10 http://127.0.0.1:30000/health; \
   du -sb /hy-tmp/hicache-qwen35-4b-p4-retry-20260909; \
   find /hy-tmp/hicache-qwen35-4b-p4-retry-20260909 -type f | wc -l; \
   find /hy-tmp/hicache-qwen35-4b-p4-retry-20260909 -type f -name "*.bin" | wc -l'
```

The request harness was executed remotely with Python `urllib`, five concurrent workers,
and this exact payload shape for each character in `xyzwq`:

```python
{
    "rid": "TEST20260909P4FG_" + ch,
    "text": (ch + " ") * 55000,
    "sampling_params": {"temperature": 0, "max_new_tokens": 1},
}
```

Batch 1 started at `2026-09-09T07:12:26.439188+08:00` and completed at
`2026-09-09T07:15:01.321748+08:00`. Batch 2, a controlled post-seed repeat with IDs
`TEST20260909P4FG_R2_{x,y,z,w,q}`, started at `2026-09-09T07:18:04.426553+08:00` and
completed at `2026-09-09T07:22:04.210312+08:00`.

## HTTP results

All ten requests returned HTTP 200, `prompt_tokens=55001`, and one completion token.
HTTP 200 is not counted as restore success.

Batch 1 wall times: q 30.976s, x 61.127s, z 121.572s, w 91.349s, y 154.875s.
Batch 2 wall times: q 46.608s, w 47.031s, x 76.847s, y 209.822s, z 239.775s.

The only response with explicit storage-backed cached-token evidence was `R2_w`:

```json
{
  "rid": "TEST20260909P4FG_R2_w",
  "status": 200,
  "cached_tokens": 54976,
  "cached_tokens_details": {
    "device": 0,
    "host": 20480,
    "storage": 34496,
    "storage_backend": "HiCacheFile"
  }
}
```

## Request-correlated restore evidence

### Batch 1: seed behavior, not historical restore evidence

For all five Batch 1 IDs, `pc_storage_query` reported `query_suffix_len=55000`,
`kv_hit_pages=0`, `storage_hit_count=0`, and `sidecar_hits={}`. There were no
`restore_success`, `hybrid_discard`, or `Failed to fetch` records for these IDs.

The terminal engine outcomes were:

| ID | issued | capacity retry | terminal outcome | recompute |
|---|---:|---:|---|---:|
| `..._q` | 1 | 0 | `revoked:miss` | 1 |
| `..._x` | 1 | 1 | `revoked:miss` | 1 |
| `..._z` | 8 | 1 | `revoked:miss` | 8 |
| `..._w` | 1 | 1 | `revoked:miss` | 1 |
| `..._y` | 57 | 0 | `revoked:miss` | 57 |

This establishes that the pre-existing non-empty storage namespace did not contain matching
material for these prompt keys at the start of the test. Batch 1 therefore seeded the file
backend through recompute; it cannot be used as historical L3 restore evidence.

### Batch 2: post-seed guard and restore exercise

The probe showed these storage-query signatures:

| ID | `kv_hit_pages` | `mamba` sidecar pages | outcome |
|---|---:|---:|---|
| `R2_x` | 54,976 | 54,976 | query hit, then 121 `PREFETCH_BUDGET` waits and `revoked:alloc_failed` recompute |
| `R2_y` | none | none | 121 `REVALIDATE`/`declined_too_short` waits, timeout recompute |
| `R2_z` | none | none | 121 `REVALIDATE`/`declined_too_short` waits, timeout recompute |
| `R2_w` | 34,496 | 34,496 | `prefetch_io_finished=34496`, `restore_success n_tokens=34496`, no recompute |
| `R2_q` | 54,976 | 54,976 | query hit, then `revoked:alloc_failed` recompute |

Exact positive event lines for `R2_w`:

```text
[2026-09-09 07:18:28] evt=prefetch_io_finished rid=TEST20260909P4FG_R2_w n_tokens=34496
[2026-09-09 07:18:28] evt=prefetch_finalize rid=TEST20260909P4FG_R2_w completed_tokens=34496 mode=cache
[2026-09-09 07:18:51] evt=restore_success rid=TEST20260909P4FG_R2_w n_tokens=34496
```

Exact failure/defer evidence for the other L3-hit IDs:

```text
R2_x: 121 WAIT_CAPACITY/PREFETCH_BUDGET, 1 restore_retry cause=capacity,
      then restore_recompute cause=miss; probe query kv=54976,mamba=54976.
R2_q: probe query kv=54976,mamba=54976, then restore_recompute cause=miss
      after revoked:alloc_failed.
R2_y/R2_z: no storage query; 121 WAIT_CAPACITY/REVALIDATE with
           declined_too_short, then restore_recompute cause=timeout.
```

Across both batches and the request-correlated log slice, `hybrid_discard=0` and
`Failed to fetch ...mamba=0` for every test ID. No shortened Mamba boundary was fetched.

Wait/retry/wake capture: four `restore_retry cause=capacity` events were observed
(`Batch1_x`, `Batch1_w`, `Batch1_z`, and `R2_x`); Batch 1 also had repeated
`WAIT_CAPACITY/PREFETCH_BUDGET` states. `R2_y` and `R2_z` had repeated
`WAIT_CAPACITY/REVALIDATE` plus `declined_too_short` and then timed out. No
`frontier_wait` or `frontier_wake` event was emitted for these ten IDs, so there is no
frontier wake to claim.

## Storage preservation

| Snapshot | Bytes | Files | `.bin` files |
|---|---:|---:|---:|
| Pre-test, `07:11:47` | 11,551,690,752 | 275,065 | 275,065 |
| After Batch 1 quiesced, `07:17:32` | 23,051,071,488 | 550,080 | 550,080 |
| Final, `07:22:34` | 23,051,071,488 | 550,080 | 550,080 |

The final service snapshot at `07:22:34+08:00` was PID 76671 alive, health 200, and GPU
memory/utilization `8897 MiB, 0%`. Storage was not cleared or deleted. The Batch 1 writes
account for the increase; Batch 2 did not change the settled file count.

## Acceptance verdict

| Criterion | Verdict | Evidence and limitation |
|---|---|---|
| (a) Invalid shortened frontier eliminated | **PASS (observed guard oracle)** | Zero `hybrid_discard` and zero Mamba fetch failures for all ten IDs. `R2_w` had matched KV/Mamba sidecar pages and restored exactly the validated 34,496 pages. This is not a proof under a pre-existing historical key set because Batch 1 began with no matching material. |
| (b) Full KV+Mamba restore reliability | **FAIL under the five-request pressure profile** | One post-seed L3-hit request restored KV+Mamba (`R2_w`); two L3-hit requests ended in allocator/capacity recompute; two deferred without storage lookup and timed out. The target “all L3-fit requests restore” behavior was not met. |
| (c) Avoidable recompute | **FAIL / not eliminated** | Batch 1 had five request-level miss recomputes. Batch 2 had four recomputes: two `revoked:alloc_failed` after sidecar-positive queries and two timeout recomputes after `REVALIDATE` deferral. Whether each is avoidable requires debugger-deep causal diagnosis; this report does not infer it. |

## Classification, followups, and open issues

- **Guard product behavior:** no invalid shortened-frontier `hybrid_discard` was observed;
  the guard-specific safety oracle passed in the exercised cases.
- **Runtime reliability:** the stressed five-request profile did not achieve full restore
  reliability. The logs show capacity/allocator and timeout paths; causal ownership is not
  assigned here. Route hard causal diagnosis to `debugger-deep` under a fresh Task ID.
- **Missing evidence:** the authorized pre-existing storage was non-empty but had no matching
  x/y/z/w/q key material, so Batch 1 was a seed run. Batch 2 is post-seed, not historical
  durability evidence. A future run needs a request-joined, pre-seeded L3-fit corpus if the
  acceptance requires historical `restore_recompute=0`.
- **No durability claim:** file counts and bytes prove occupancy only. No crash/power-loss
  test, durable ACK join, or 100% durability claim was made.

## Artifacts

- This report:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST-20260909-P4-FRONTIER-GUARD.md`
- Remote engine log (preserved):
  `/tmp/qwen35-4b-hicache-p4-reconstruct-sm86-20260909-json.log`
- Remote probe log (preserved): `/tmp/t38c-probe.log`
- Remote service: PID 76671, `127.0.0.1:30000`, health 200 at final check.
