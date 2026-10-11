# FORMAL INVALIDATION — R122 host-headroom gate v1

- Artifact invalidated: `work/R122-bundle/P1-R122-HEADROOM-GATE-ADDENDUM.md`
  sha256 `92ad1c29f4749be9fc4056a5e8d9dbb89d7800f652ccccdc2959651401faea25`.
- Status: **INVALIDATED** (not merely "corrected"). The gate *intent* (two
  moments; sequential chain; Gate B = "F1 released so T is genuinely
  allocatable") remains user-ratified, but its **measurement basis is wrong and
  must not be used again**.
- Reason: v1 defined `host_allocable := full_free + full_evictable`, which reads
  the **device** KV pool (`_component_available_size(ComponentType.FULL)` =
  `token_to_kv_pool_allocator`, `unified_radix_cache.py:4366-4368 -> :3018-3021`,
  size 65536). The predicate that blocks a restore is `HOST_ALLOC` against the
  **L2 host** pool (`host_allocability_snapshot -> cache_controller.mem_pool_host`,
  `unified_radix_cache.py:3838-3876`, size 131073). A v1 gate therefore reports
  PASS (63488 / 65534) while the host pool is 2786. v1's cited R121
  `raw.log:270084` is a `[P2A] promotion_reserve` **device** line, not host.
- Binding replacement: `P1-R122-HEADROOM-GATE-ADDENDUM-v2-CORRECTION.md`
  (sha256 `cbd1cf5748146a6bf1e77bedb6586d99019ea48ccd791a9b0d0f2a47555decce`
  at time of this record; R123 freezes a superseding temporal contract).
- Standing rule going forward: **every HOST_ALLOC capacity/eligibility claim
  MUST be sourced from the L2 host pool** — `mem_pool_host` via `host_alloc.v1`
  events (`restore_host_alloc_wait`, `restore_host_alloc_wake_decision`,
  `restore_host_alloc_retry_result`, `host_allocability_change`) or
  `host_allocability_snapshot`. Deviating to a device-pool (`full_*`) quantity
  is INVALID for HOST_ALLOC reasoning.
- Procedure note: the v1 bytes are intentionally NOT edited, so R122's cited
  sha256 chain stays auditable. This separate record is the formal marker.
