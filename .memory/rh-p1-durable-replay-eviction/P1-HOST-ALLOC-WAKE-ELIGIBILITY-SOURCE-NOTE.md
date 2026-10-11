# P1 HOST_ALLOC wake-eligibility — orchestrator read-only source note

Status: SUPPORTING-EVIDENCE ONLY (not a verdict). Decisive proof requires R123's
`t_feasible` timeline. No product code changed; read-only inspection.

## Finding

`_host_alloc_wait_eligible` (scheduler.py:3716-3727) wakes a parked restore only
when **every** pool in the request's `blocked_domains` has advanced:

```python
return all(
    current.generation_by_pool.get(pool, 0)
    > cursor.snapshot.generation_by_pool.get(pool, 0)
    for pool in cursor.blocked_domains
)
```

But a pool's generation advances only when that pool's host **evictable
signature changes** (`_bump_changed_host_allocability`, unified_radix_cache.py
:3823-3835, called from :3326/:3343 on lock-release and other sites), i.e. only
when that specific pool's host evictable set/count changes. If no mamba host
page changes, the mamba generation never advances.

`blocked_domains` is built at allocation-failure time
(unified_radix_cache.py:6503-6519): KV is always included; an aux pool (mamba) is
added when its sidecar hit is incomplete
(`transfer.keys is None or hit_pages < len(transfer.keys)`).

## Consequence (hypothesis, matches R121)

R121 T: `blocked_domains = {kv, mamba}`, `sidecar_hit_pages = {kv:27328, mamba:0}`
-> mamba added. Then:
- `restore_host_alloc_wake_decision` 00:33:31 grants T (both generations advanced
  kv 1227->1228, mamba 1850->1851) but the retry then fails allocation
  (`free_after 24670 < 27328`, -2658) and re-parks.
- `restore_host_alloc_wake_decision` 00:34:09 (wait:27): kv 1229->1230 advanced,
mamba 1853->1853 did NOT -> `decision=hold_no_generation`,
`retry_outcome=hold_no_generation`.

At that instant T's mamba requirement was already satisfiable (per_pool mamba
`free 75`, `required 1`), so demanding a mamba generation change is spurious: KV
release was the material event. If R123 shows `t_feasible < t_deadline` while T
is held on the unchanged mamba generation, this is a genuine liveness defect in
the blocked-domain wake semantics (the eligibility should be per-domain
sufficiency / "some blocked domain became satisfiable", not "all blocked domains
changed"), not a capacity limit.

## Note

This is the same class of "telemetry/eligibility vs. real state" gap already
registered for `durability_barrier`/`pc_*`; here it affects **wake eligibility**,
which is user-visible (a restore that could proceed is held to timeout).
