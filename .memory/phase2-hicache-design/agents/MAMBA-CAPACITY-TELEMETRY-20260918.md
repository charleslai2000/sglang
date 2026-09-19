# MAMBA-CAPACITY-TELEMETRY-20260918

Status: DONE
Role: domain-analyzer (read-only production telemetry quantification)
Task: quantify the `mamba_available_tokens == 0 -> WAIT_CAPACITY -> extreme TTFT` tail from existing
production telemetry and decide whether it is a Mamba-pool capacity problem; produce the data that
justifies (or kills) the narrow `max_mamba_cache_size` 48/56/64 sweep. READ-ONLY: no restart/stop,
no signal, no GPU workload, no config edit, no git mutation. Only this artifact was written inside
the workspace; the raw `/metrics` scrape captures live in the pre-approved temp dir
`/tmp/opencode/mam_metrics{,2,3}.txt`.

Window captured: the run `prod-20260917T211800Z-1653969` from boot 21:18:00Z to its natural stop
23:05:31Z (supervisor rc=0), requests 21:20:03Z -> 23:06:28Z. Evidence digests at read time
(2026-09-17T23:39Z): `server.console.log` sha256 a5f63862c7c5fa413318b8c13b5590ef4c11dc157413eeca30edde75cb90f5dd;
`sglang-request-metrics-20260917_21.log` 0c2be21dc49858e5a9bce76402c471b4c716f5e20a01f5473e56407a77d240b7;
`_22.log` 6ad2cc594503112185101e1d5af24597e356a7df0980969074777c1cd3066a1f;
`_23.log` f6d17f7543e582509014811bb8bf9177495c6cfc5f667cc5d42f86a458a32dd5.

---

## Result

**Diagnosis (one line): the WAIT_CAPACITY tail is explained by the Mamba state pool — but by the
pool's host-side staging capacity and by the wake predicate's slot-vs-token mismatch, not by a
shortage of simultaneous device slots.**
Every one of the 42 WAIT_CAPACITY parks has `blocked_domains == ["mamba"]`, Mamba host staging
`free == 0` and `evictable == 0`, while the host KV pool was 48.5–80.6 % free. The prefetch retry
allocates exactly **one** Mamba host slot (`MambaComponent.prepare_prefetch`,
`srt/mem_cache/unified_cache/components/mamba_component.py:836-849`) and that single-slot alloc
failed because the whole Mamba host pool was allocated and none of it evictable. The Mamba host pool
holds only **142 usable slots** (one radix checkpoint per slot), so it can host-buffer at most ~142
distinct linear-attention checkpoints; any request whose matched prefix needs a checkpoint that is
not host-resident parks. Worse, the wake predicate charges the **whole matched-prefix token count**
against that slot pool (`required_aux_units["mamba"] = len(prefetch_key)`, 484 – 65,347 units
measured, versus a 142-slot pool), so a grant is arithmetically impossible even if one slot were free.
All 261 wake checks resolved to `hold_no_generation`; all 42 requests left only via the 60 s T13
timeout (41) or abort (1), then recomputed. The device-side `max_mamba_cache_size` (48) was **never**
the binding constraint in this window: measured device high-water is only 23 slots with `mamba usage`
max 0.48, and `mamba_available_tokens == 0` at the live scrape is "all 48 device slots are owned by
the radix tree (4 active + 44 evictable)", not "concurrency starved". Purely raising
`max_mamba_cache_size` 48→56/64 does **not** raise the 142-slot host Mamba pool and therefore is
**not justified by this telemetry** as a fix for the tail; the levers the data implicates are
(a) the Mamba host pool share of `--hicache-size 32` (~7.3–7.7 GB), (b) the wake predicate's
requirement units, and (c) the 60 s park+burn rule itself.

Headline numbers (all sourced below):

| Quantity | Measured |
|---|---|
| Requests in window | 515 completed records (`sglang-request-metrics-*.log`), plus 1 parked request that never completed (`83e7736d`); 36 of the 515 are the parked requests with records |
| TTFT p50 / p95 / p99 / max | 0.665 s / 62.8 s / 83.0 s / **125.9 s** |
| TTFT for the 36 parked requests | p50 62.6 s, p95 121.3 s, max 125.9 s; `queue_time` sum 2475 s |
| TTFT for all other requests | p50 0.591 s, p95 7.2 s, max 63.4 s |
| Simultaneous running requests (max, all measures) | **7 decode HWM; 8 max in-flight (received→finished)** vs configured `max_running_requests=8` |
| Device Mamba slots | HWM `mamba num = 23` (usage max 0.48); configured `max_mamba_cache_size=48` |
| Mamba host pool | **142 usable slots** (`sglang:hicache_mamba_host_usable_tokens`), 7.31 GB |
| Host KV pool | 1,509,560 slots, 24.73 GB; free at every park 732k–1.22M (48–81 %) |
| WAIT_CAPACITY parks | 42 (37 distinct rids, 5 re-parks); latency penalty **p50 60.0 s, p95 60.4 s, max 60.6 s, sum 2515 s** |
| Per-slot Mamba cost (derived + log-confirmed) | **49.125 MiB = 51,511,296 B** |
| VRAM cost of the pool (49 allocated slots for 48) | 2.524 GB (= 2.351 GiB) |
| Prefix reuse observed | cached/prompt = **88.6 %** overall (device 87.8 %, host 0.76 %, L3 0.0 %) |

Correction discipline: earlier drafts of the park tables used line numbers of neighbouring
`[P3]`/`[HAE]` lines; the final table in E7 uses the exact `restore_host_alloc_wait` record lines
(3003-13140). Also corrected: the charge is 1 Mamba host slot per prefetch attempt while the wake
predicate compares the whole matched prefix length against the pool; and the waiters' host-copy
count is 14/36 (not 13). The correlational tables and the raw event rows are in Evidence.

---

## Evidence

### E1. Config verified from the live process (not the task's list)
`ps -p 1654119 -o args` (run 21:18:00Z-23:05:31Z; server pid 1654119, scheduler pid 1654601) shows,
among others: `--context-length 131072 --max-total-tokens 524288 --max-running-requests 8
--max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3 --mem-fraction-static 0.92
--mamba-ssm-dtype float32 --mamba-radix-cache-strategy extra_buffer --enable-hierarchical-cache
--hicache-size 32 --hicache-write-policy write_back --hicache-storage-backend extent
--hicache-storage-prefetch-policy wait_complete --enable-ready-horizon --disable-prefill-cuda-graph`.
The server's own `server_args={...}` echo is at `server.console.log:14` and confirms
`hicache_restore_wait_timeout_s: 60.0`, `mamba_full_memory_ratio: 0.9`, `page_size: 1`.
This matches the task list exactly. (This verification was done while the process was alive; the
window closures happened at 23:05:31Z, and later `ps -p 1654119` returns nothing.)

### E2. Pool geometry at boot (`server.console.log`, run prod-20260917T211800Z-1653969)
- L672 `Mamba Cache is allocated. max_mamba_cache_size: 48, conv_state size: 0.05GB, ssm_state size: 2.30GB`
- L673 `KV Cache is allocated. dtype: torch.float8_e4m3fn, #tokens: 524288, K size: 4.00 GB, V size: 4.00 GB`
- L674 `Memory pool end. avail mem=2.48 GB`
- L682 `max_total_num_tokens=524288, ... max_running_requests=8, context_len=131072, available_gpu_mem=1.92 GB`
- L684 `Allocating kv hierarchical KV host pool: 1509560 tokens, 24.73 GB host memory.`
- L685 `Allocating 7.31 GB host memory for hierarchical Mamba cache (layout=page_first).`
- L688 `Attached hybrid pool stack to UnifiedRadixCache: pools=KV + MAMBA, transfer_layer_num=32`

### E3. Mamba state slots required per active request (derivation, source-cited)
The model `/data/models/qwen35-9b-w4a16/config.json` (`text_config`) gives
`num_hidden_layers=32`, `layer_types` with **24** `linear_attention` and 8 `full_attention`
(`full_attention_interval=4`), `linear_key_head_dim=128`, `linear_num_key_heads=16`,
`linear_value_head_dim=128`, `linear_num_value_heads=32`, `linear_conv_kernel_dim=4`,
`mamba_ssm_dtype="float32"`.

- Shape: `srt/configs/qwen3_next.py:288-313` (`mamba2_cache_params`) builds
  `Mamba2StateShape.create(...)` from those fields; `srt/configs/mamba_utils.py:188-237` yields
  `conv_state_shape = (linear_value_head_dim*linear_num_value_heads + 2*linear_num_key_heads*linear_key_head_dim,
  conv_kernel-1) = (8192, 3)` and `temporal_state_shape = (32, 128, 128)`.
- Per-slot bytes: `srt/configs/mamba_utils.py:115-125` (`mamba_cache_per_req`) =
  `(conv_numel*conv_itemsize + ssm_numel*temporal_itemsize) * len(layers)` =
  `(24576*2 + 524288*4)*24 = 51,511,296 B = 49.125 MiB`.
- Allocation uses `size+1` slots per buffer: `srt/mem_cache/memory_pool.py:588-619`
  (`conv_state ... (num_mamba_layers, size + 1) + conv_shape`, `temporal_state ... (num_mamba_layers, size + 1) + temporal_state_shape`).
- **Slots per request**: with `--mamba-radix-cache-strategy extra_buffer`, the sizing ratio is
  `MAMBA_CACHE_SIZE_MAX_RUNNING_REQUESTS_RATIO (3) + MAMBA_CACHE_V2_ADDITIONAL_RATIO_OVERLAP (2) = 5`
  (`srt/mem_cache/kv_cache_configurator.py:156-161, 1860-1889`; extra-buffer predicate at
  `:1529-1541`; `--disable-overlap-schedule` is **not** set, so the overlap branch applies).
  The same `5` slots/request is recorded independently in the operator ledger
  (`.memory/phase2-hicache-design/ledger.md:7478-7479`: "SSR = 5 ... 106 slots ~ 5 slots/req").
  ⇒ `48 // 5 = 9 ≥ 8`: the device pool was explicitly sized (ledger line 7480: "取 48 (1.2× 余量)")
  so it does not cap `max_running_requests=8`; `resolve_max_num_reqs`
  (`srt/mem_cache/kv_cache_configurator.py:1935-1961`) issues no cap warning in the log
  (`grep -c "capped to|was reduced from" server.console.log == 0`).
- Where the pool is computed: device pool = `max_mamba_cache_size` via
  `srt/mem_cache/kv_cache_configurator.py:2075-2082` (`explicit max_mamba_cache_size` branch) and
  allocated in `srt/mem_cache/memory_pool.py:505-619`; the log line is emitted at `:847-856`.
  Host pool = `srt/mem_cache/hybrid_cache/hybrid_pool_assembler.py:710-736`:
  `_split_hicache_size(hicache_size, (kv_pool, mamba_pool))` splits `--hicache-size 32` by **device pool bytes**
  (`:134-147`, using `get_kv_size_bytes()`), then `MambaPoolHost(..., mamba_host_size, ...)`;
  `MambaPoolHost.size` = `host_size*1e9 // size_per_token` (`srt/mem_cache/pool_host/mamba.py:79-87`),
  `size_per_token = (conv+ssm)*num_mamba_layers` (`:293-299`, same 51,511,296 B per slot).

### E4. Simultaneous running requests (Q1)
- From decode log lines (`Decode batch, #running-req: N`):
  `{1:1830, 2:1616, 3:425, 4:119, 5:6, 7:3}` over 3999 decode lines in this window, **HWM = 7**.
- From prefill lines `#running-req`: HWM 6; max `#queue-req` seen 4.
- From the request-metric JSONL: overlap of `[request_received_ts, request_finished_ts]` gives
  **max 8 in-flight**; overlap of `[forward_entry_time, request_finished_ts]` gives **max 7 running**.
- Live `/metrics` scrapes: `sglang:num_running_reqs` 1.0 (idle-ish), `num_queue_reqs` 0–1.
- Conclusion: the observed concurrency **never exceeded the configured 8**; implied mamba device
  requirement = `8 × 5 = 40` slots ≤ 48 → device pool not exhausted by concurrency.

### E5. Mamba pool used/max over time (Q3)
- Device (`mamba num: X, mamba usage: Y` in console): HWM `mamba num = 23`, and
  **`mamba usage` max = 0.48**; never ≥ 0.5 anywhere in the log. Distribution in E4's companion:
  `{0:4, 3:485, 4:1351, 7:1090, 8:524, 10:2, 11:247, 12:167, 13:1, 14:32, 15:57, 16:33, 17:2, 18:1, 23:3}`.
- Live `/metrics` (22:38Z): `mamba_used_tokens 4, mamba_evictable_tokens 31, mamba_available_tokens 13`
  → 4+31+13 = 48; (22:56Z): `4/43/1`; (23:03Z): **`4/44/0`** (available reaches 0 with 4 active + 44
  radix-cached — i.e. "0 available" is the tree owning the pool, not admission starvation).
- Scheduler sanity print at 21:56:55Z: `mamba_free=1 mamba_evictable=37 mamba_locked=10`
  (`evt=promotion_reserve`, `server.console.log:6446`).

### E6. WAIT_CAPACITY events: count and duration (Q4)
Signal line: `[P2A] ts_ms=... evt=restore_state rid=... state=WAIT_CAPACITY reason=HOST_ALLOC`
(first at line 3002, 21:44:08Z; last at line 13139, 23:04:49Z; 42 occurrences). The park is emitted by
`_capture_host_alloc_wait` → `restore_host_alloc_wait` (`srt/managers/scheduler.py:3872-3890`;
state machine T3 `DENIED_ALLOC → WAIT_CAPACITY/HOST_ALLOC` at
`srt/managers/scheduler_components/hicache_restore.py:377-378, 537-538`).
- Count: **42 parks / 37 rids** (5 rids park twice: `ac5435c0`, `c0710e18`, `747b5372`, `c69529e3`,
  `5e648375`), terminal events `restore_host_alloc_retry_result` = 42, all
  `terminal = forfeited_alloc_failed`.
- Duration = `release.ts_mono_ns − wait.wait_started_mono_ns` (release = `decision=release`,
  `terminal_state=TIMEOUT` for 41, `ABORTED` for 1):
  **min 52.0 s, p50 60.0 s, p90 60.4 s, p95 60.4 s, p99 60.6 s, max 60.6 s, total 2515.3 s.**
  (One park was released at 52.0 s by the request being aborted; the other 41 timed out at the full
  `--hicache-restore-wait-timeout-s 60` clock; 41 `evt=restore_recompute ... cause=timeout`.)
- Wake telemetry: 303 `restore_host_alloc_wake_decision` records = 261 `hold_no_generation` +
  42 `release`; **0 grants**. 261/261 holds show `free_units{"kv":..., "mamba":0}`,
  `evictable_units{"kv":0,"mamba":0}`, and `current_generations["mamba"]==12` in every hold
  (captured mamba gen was 12 in all 42 parks). I.e. the Mamba allocability generation never advanced
  while any waiter was parked; it first moved 12→13 at 23:06:30Z, after the last park had timed out.
- Park reasons are exclusively `HOST_ALLOC`: `restore_disposition` reasons over the run are
  `aux_alloc_failed` 42 (all the parks), `revoked:miss` 13, `too_short` 13 — no KV/DEVICE_QUOTA park
  exists in this window.
- The parks cluster in the load bursts: per-30-min counts
  `{21:43:10, 21:53:16, 22:00:10, 22:10:1, 22:53:3, 23:00:2}`.
- Aggregate cost: the 36 parked requests that produced a metric record account for
  `sum(queue_time)=2475 s`; TTFT p50 62.6 s vs 0.591 s for everyone else (see E10).
- Counter cross-check: `sglang:hicache_prefetch_aux_alloc_failed_tokens_total` =
  **543,258** at 22:38Z = the exact sum of `required_aux_units["mamba"]` over the 37 parks up to
  22:12Z (E7).

### E7. At each park: KV vs Mamba occupancy (Q5) — the decisive table
The park/retry records embed the allocability snapshot. **All 42 parks:**
`blocked_domains == ["mamba"]`, `free_units["mamba"] == 0`, `evictable_units["mamba"] == 0`,
and in `restore_host_alloc_retry_result`: `failed_domains == ["mamba"]`, `genuine_miss == false`,
per-pool `mamba.{free_before,free_after} == 0`, `mamba.{evictable_before,evictable_after} == 0`,
`mamba.{alloc1,alloc2,reclaimed} == null/null/0`, **while**
`kv.free_before == kv.free_after ∈ {1216797, 1180822, 1154549, 1099035, 1038293, 935558, 835971, 791070, 732185}`
and `kv.reclaimed == 0`. In other words, the KV host pool was at 48.5 % – 80.6 % free at every
single park; the block was 100 % Mamba host staging.

Representative rows (line = `server.console.log` line of the `restore_host_alloc_wait`
record; dur = park duration s):

| # | line | time (UTC) | rid | `required_aux_units["mamba"]` (prefix tokens, not slots) | host KV free (slots) | host mamba free/evict (slots) | dur s |
|---|---|---|---|---|---|---|---|
| 1 | 3003 | 21:44:08 | c9a31e95 | 3,556 | 1,216,797 | 0 / 0 | 60.0 |
| 4 | 3193 | 21:45:08 | ac5435c0 | 3,436 | 1,216,797 | 0 / 0 | 60.0 |
| 5 | 3324 | 21:45:44 | 790edcb8 | 57,697 | 1,216,797 | 0 / 0 | 60.0 |
| 12 | 4955 | 21:51:48 | cb10524b | 62,040 | 1,216,797 | 0 / 0 | 60.0 |
| 19 | 5989 | 21:55:21 | 63cec62a | 62,800 | 1,216,797 | 0 / 0 | 60.0 |
| 26 | 9690 | 21:59:32 | 25e6f928 | 62,681 | 1,038,293 | 0 / 0 | 60.0 |
| 34 | 11271 | 22:05:17 | 9b42ac86 | 65,347 | 835,971 | 0 / 0 | 60.0 |
| 36 | 11790 | 22:09:32 | 83e7736d | 12,187 | 791,070 | 0 / 0 | 52.0 (aborted; no response record) |
| 38 | 12137 | 22:54:06 | 9c84dfc4 | 484 | 791,070 | 0 / 0 | 60.0 |
| 42 | 13140 | 23:04:49 | a9b323a0 | 3,646 | 732,185 | 0 / 0 | 60.0 |

Full 42-row table is derivable from `server.console.log` by joining lines containing
`"evt": "restore_host_alloc_wait"` (lines 3003-13140) with the closest following
`"evt": "restore_host_alloc_wake_decision"` with `"decision": "release"`.
`required` here is the value written by `required_aux_units.setdefault("mamba", len(prefetch_key))`,
i.e. **tokens of matched prefix** (the same quantity as `requested_primary_tokens`), while the
`free/evict` columns are **host slot counts** from the mamba host pool (total 142). This unit
mismatch is mechanism (1) above. Required units range 484 … 65,347; 9 parks needed ≥ 10k units,
i.e. all 42 parks required more units than the entire 142-slot pool contains. Sum over the whole run
564,651; over the sweep-relevant first phase (≤22:12Z) **543,258**, which equals the exporter counter
`sglang:hicache_prefetch_aux_alloc_failed_tokens_total` exactly at 22:38Z.

Interpretation, source-cited. Three mechanisms compound; the telemetry separates them cleanly:

1. **The retry unit is one host slot, but the wake predicate charges the whole matched-prefix
   length.** `MambaComponent.prepare_prefetch` allocates **1** host slot
   (`srt/mem_cache/unified_cache/components/mamba_component.py:836-849`); the cache records
   `required_aux_units.setdefault(failed_pool, len(prefetch_key))` when that alloc fails
   (`srt/mem_cache/unified_radix_cache.py:5451-5457`), and the scheduler's wake predicate tests
   `free + evictable >= required` in the *same* record's units
   (`srt/managers/scheduler.py:3747-3765`). `free_units`/`evictable_units` for the mamba pool are
   **slot counts** (`host_group.available_size` and `_host_evictable_signature`, both host slots —
   `srt/mem_cache/unified_radix_cache.py:3866-3889, 3703-3718`). **Decisive arithmetic:** the pool's
   total is 142 slots (E8), while the smallest observed park requirement is 484 and the largest
   65,347. So `free + evictable >= required` **cannot be satisfied by any observed park even with a
   completely empty pool**; the capacity path of `_host_alloc_wait_eligible` is dead for all 42.
2. **The only other wake path, a Mamba allocability-generation advance, never fired.** The predicate
   skips a blocked domain whose generation advanced (`srt/managers/scheduler.py:3747-3751`), and the
   FIFO arbiter additionally requires a new generation vector to grant (`hicache_restore.py:211-222`).
   The mamba generation was captured at **12** for every one of the 42 parks and remained 12 for all
   261 wake checks; it only advanced 12→13 at 23:06:30Z (`lock_release_evictable`) after the last
   park had already timed out. The `queued_release_drain` advances had stopped at 21:40:46Z (gen 12,
   E6), i.e. the pool's reclaimable set stopped changing once it saturated.
3. **Why the pool saturates: it is 142 slots, and the tree holds ~142 host checkpoints with none
   reclaimable.** `_host_evictable_signature` requires the node to be in the host LRU and
   `host_lock_ref == 0` (`srt/mem_cache/unified_radix_cache.py:3703-3718`); the HAE snapshots
   themselves report `evictable=0` at every park, and the only mamba host frees after 21:40 are the
   shutdown-time releases. The `hicache_backup_tokens_total{pool="mamba"}=142` counter equals the
   pool size exactly: the backup path wrote exactly one checkpoint per slot and then had no room.

Consequence: for a `blocked_domains==["mamba"]` waiter, the observed release mechanism is the 60 s
T13 timeout (41/42) or abort (1/42) — **0 grants in 303 wake decisions**. This matches the measured
duration distribution (p50 60.0 s, max 60.6 s, sum 2515 s) and `cause=timeout` for 41 recomputes.

### E8. Why the Mamba pool is small: sizing split (source-cited, exact)
`--hicache-size 32` (GB, SI) is split by device-pool bytes (`_split_hicache_size`,
`srt/mem_cache/hybrid_cache/hybrid_pool_assembler.py:134-147`, called at `:710-712`):
- KV device pool = 524,288 tokens × 16,384 B/token (K 4.00 + V 4.00 GiB fp8, `server.console.log:673`)
  = `8.590e9 B` (the `GB` constant used by that log is `1024^3`, `srt/mem_cache/memory_pool.py:103`).
- Mamba device pool = 49 × 51,511,296 B = `2.524e9 B` (E3).
- Mamba host share = `32 × 2.524/(2.524+8.590)` = **7.2666 GB** → `MambaPoolHost.size` =
  `int(7.2666e9 // 51,511,296)` = 141, then `page_num = size//1 + 1` → **142 usable slots**
  (`srt/mem_cache/pool_host/mamba.py:79-87`). This matches exactly the printed
  `7.31 GB` (`server.console.log:685`) and the live gauge
  `sglang:hicache_mamba_host_usable_tokens = 142`.
- KV host share = 24.733 GB → 1,509,560 slots (printed 24.73 GB, `server.console.log:684`).
The Mamba host pool is thus **~10,600× smaller** than the KV host pool in slots, and
`hicache_backup_tokens_total{pool="mamba"}=142` (backups) with
`hicache_dropped_tokens_total{pool="mamba"}=218→234` under host pressure (KV side: 132,612→146,188
dropped) confirms the pool saturates almost immediately.

### E9. VRAM: peak and headroom (Q6)
- Sampling method: manual `nvidia-smi --query-gpu=... --format=csv` while the server was up (idle
  between bursts; no GPU workload of my own), plus one independent observation already recorded in
  the operator ledger. This is point sampling, not a recorded peak:
  - 22:24:59Z (my sample): used 23,251 MiB / 24,576, free 874 MiB, util 0 %, 35 °C.
    Processes: pid 1654119 python 300 MiB + pid 1654601 `sglang::scheduler` 22,876 MiB.
  - 22:38Z (ledger `PROD-STATE-CHECK-R2` observation, not mine; during load):
    23,009 MiB used / 1,567 MiB free, util 100 %.
  - 23:06:32Z (my sample, after stop): used 1 MiB, free 24,124 MiB.
- Limits: nvidia-smi is point-in-time; the highest sample seen is 23,251 MiB (free 874 MiB, 3.6 %),
  so the run's true peak may be higher. No in-process VRAM gauge exists in the metric set
  (`sglang:kv_cache_memory_usage_gb=8.0`, `graph_memory_usage_gb{phase=decode}=0.146`), so
  "VRAM peak" here is an observer sample, not a recorded peak.
- Sizing check at boot: `Memory pool end. avail mem=2.48 GB`, `available_gpu_mem=1.92 GB` after graph
  capture. The Mamba host pool is host DRAM, not VRAM.

### E10. Prefix/cache-hit telemetry (Q7)
From `cached_tokens` / `cached_tokens_details` in the request-metric JSONL (n=515):
`cached/prompt = 12,715,025 / 14,355,360 = 88.57 %`; device 87.81 %; **host 0.76 %**; **L3 (storage) 0.00 %**;
per-request mean 74.7 %. The owner's ~87.4 % figure matches the device share (87.8 %).
Correlation with the tail:
- Parked requests: hit rate **0.337**; 7/36 have `cached_tokens == 0`; 14/36 carry a nonzero
  `cached_tokens_details.host` (they did match a host Mamba checkpoint).
- Non-parked requests: hit rate **0.915**; 67/478 have `cached_tokens == 0`.
- So the tail is *anti-correlated* with prefix reuse (parked requests are the low-reuse ones), and
  host-tier hits are negligible in volume (0.76 % of tokens) precisely because the Mamba host pool is
  tiny. `hicache_prompt_tokens_total` sources: l1 10,547–10,654k, l2 97.3–103.4k, **l3 0**.
- `prefetch_origin`: parked requests are all `READY_HORIZON` (36/36); all 13 `prefetch_issued` /
  13 `prefetch_revoke` / 13 `restore_disposition(RECOMPUTE, revoked:miss)` events happen at
  21:22–21:40Z, i.e. the storage-restore path was exercised and then revoked as genuine misses;
  `enable_storage_metrics` counter `hicache_prefetch_aux_alloc_failed_tokens_total` is the Mamba-park
  accumulator (E6).

### E11. Sweep cost arithmetic (owner figures checked, not assumed)
Per-slot bytes derived above = **51,511,296 B (49.125 MiB)**; this is confirmed by *two independent*
log readings and the operator ledger:
- today's `0.05GB conv + 2.30GB ssm` over 49 slots → 48.1 MiB (this run);
- the 106-slot baseline `5.02 GiB / 107 = 48.04 MiB` (`.memory/phase2-hicache-design/ledger.md:7478-7479`).
Device Mamba pool cost (with the +1 padding slot):
| `max_mamba_cache_size` | allocated slots | exact cost | vs 48 |
|---|---|---|---|
| 48 (current) | 49 | **2.524 GB** (2.351 GiB) | — |
| 56 | 57 | **2.936 GB** (2.734 GiB) | +0.41 GB |
| 64 | 65 | **3.348 GB** (3.118 GiB) | **+0.82 GB** |
| 106 (old baseline) | 107 | 5.512 GB (5.133 GiB) | +2.99 GB |
Note the owner's rough figures (48≈2.27, 56≈2.65, 64≈3.03 GB) are ~10 % low; they appear to divide by
the *device* pool bytes only (2.30+0.05 measured is 2.35 GB at 48, not 2.27) and omit the +1 slot.
The marginal VRAM cost is **~0.41 GB per 8-slot step** ≈ 0.5 % of the 24.576 GB card.
All of it is host-side pool *plus* ~0.8 GB *device* VRAM; with 874–1,567 MiB free during load, a
+0.82 GB device step would exceed observed free VRAM, so a sweep cell would have to come out of the
KV device pool (max_total_tokens) or `mem_fraction_static`, exactly as the owner's constraints allow.

### E12. What the data says about the sweep cells
- Raising 48→56/64 changes only the **device** pool. The observed tail mechanism (E7/E8) is the
  **host** Mamba pool (142 slots) plus the wake predicate's token-vs-slot mismatch (mechanism 1);
  the device pool's own HWM was 23/48 with usage 0.48, and the concurrency peak (7 running,
  8 in-flight) needed only 40 slots. A 56/64 device pool leaves `mamba_available_tokens` at 8/16
  instead of 0 in the idle steady state, but it does not change the 142-slot host pool, the
  `required_aux_units` comparison, or the 60 s T13 clock, so it cannot by itself stop the parks.
  Caveat in fairness to the sweep: 48//5 = 9 and a **9-request** burst would want 45 slots; at 48
  the tree has only 3 spare, at 64 it has 19. The measured window never exceeded 8 in-flight, so
  the 56/64 cells can only matter if the sweep load generates ≥9-slot concurrency pressure — the
  production data cannot rule that in.
- Therefore: cell 48 is the control and is expected to reproduce the tail; 56/64 are worth running
  only as a controlled falsification test of the "device pool drives the tail" hypothesis, and the
  observed production load cannot justify them on its own. The sweep as currently instrumented
  (fixed `--hicache-size 32`, same `--max-running-requests 8`) answers
  "does more device headroom reduce the *frequency* of reaching 0 available?", not
  "does it stop the 60 s parks?".
- **KV-pool trade**: the parks show host KV free 732k–1.22M of 1.51M slots even at peak; the device
  KV pool is 8.0 GB fp8 and device KV usage peaked at 0.33 of 524,288 ≈ 175k tokens (below the
  128K context and the 524k cap). A device-pool trade of e.g. −0.82 GB (64 vs 48) is therefore
  feasible on the KV side, but the binding VRAM number observed during load was 874–1,567 MiB free,
  so a 64-cell would still need a KV/`mem_fraction_static` concession to fit. Note this cost is real
  even though the device pool did not cause the tail — it is the price of the falsification test.
- Recommendation (data-backed, no sweep run here): run 48 as control; prioritize a cell that changes
  the **host** Mamba share (e.g. `--hicache-size` up, or an explicit Mamba host allocation) and/or
  tests the T13 park rule; treat 56/64 as a secondary falsification of the device-pool hypothesis
  (especially if the sweep can drive ≥9 concurrent requests), and only with a documented KV
  concession. Do not adopt 64 on the strength of the 48→64 device-slot change alone.

---

## Defects / blockers

1. **No Mamba host-pool time series exists in the exported telemetry.** `mamba_available_tokens`
   and friends are *device* gauges; the host Mamba pool appears only as
   `hicache_mamba_host_usable_tokens` (142), `hicache_backup_tokens_total{mamba}` (142) and
   `hicache_dropped_tokens_total{mamba}` (218→234). The authoritative statement "free=0, evictable=0
   at every park" comes from the HAE snapshot embedded in the wait/retry records, not from a gauge.
   This is sufficient for the diagnosis, but there is no continuous host-Mamba occupancy trace.
2. **`request_parameters` carries the full prompt text in the JSONL**; I did not read prompt bodies
   and did not quote any. The metric files are large (49 MB); only scalar fields were parsed.
3. **One parked request has no completion record** (`83e7736d9b074370840cba8b6a5d5c88`, parked at
   22:09:32Z, released at 22:09:26+52 s as `ABORTED/abort_request`); it is excluded from TTFT stats.
   The `restore_host_alloc_wait` count (42) vs the request-metric waiter count (36) differs by the
   5 re-parks (same rid) and this aborted rid.
4. **The live `/metrics` scrape is point-in-time**; the prior two scrapes (22:38Z, 22:56Z) plus the
   23:03Z scrape are the only direct gauge readings (the server stopped at 23:05:31Z). The park
   snapshots are the reliable per-event source.
5. **The exact `0.05/2.30 GB` log rounding vs derived 0.058/2.466 GB**: log prints 2 decimals in GB
   (and GiB-based `GB` constant), so ±0.02 GB per component; the per-slot figure is consistent to
   <2 % across three independent readings, so the sweep arithmetic is unaffected.
6. **The observed production process is now stopped** (supervisor rc=0 at 23:05:31Z; a new lock
   generation 8 belongs to the separately-authorized sweep at 23:13:47Z). All findings above are from
   the preserved logs and are not affected; no production GPU work was performed by me.
7. **No benchmark / no controlled perturbation** was run (as instructed), so the diagnosis is
   observational: it establishes the blocking domain and mechanism beyond doubt (100 % of parks
   mamba-only with KV 48–81 % free) but does not *experimentally* prove that raising the Mamba host
   share eliminates the tail. That proof requires the sweep/window work owned elsewhere.

---

## Remaining claims / exclusions

Not claimed:
- That `max_mamba_cache_size=64` fixes the tail. The evidence says the device pool was at most 48 %
  used and the blocking resource was the 142-slot host Mamba pool plus the 60 s T13 park rule.
- That the tail is caused by KV-pool exhaustion. Refuted for this window: KV free was 732k–1.22M of
  1.51M host slots and 0.33 device usage at every park; `kv.reclaimed == 0` in all retries.
- Any new VRAM number beyond the sampled points; the true peak may exceed 23,251 MiB.
- That the storage tier (L3/extent) contributed: `hicache_prompt_tokens_total{l3}=0`,
  `cache_hit_rate` device-only; the 13 `revoked:miss` events were genuine misses, not capacity.
- That `WAIT_CAPACITY` is observed on any other reason: all 42 are `HOST_ALLOC`; `reason` values in
  `restore_disposition` are only `aux_alloc_failed` (42), `revoked:miss` (13), `too_short` (13).

Exclusions honored:
- No software design, no implementation, no config recommendation applied; no code changes.
- The 48/56/64 sweep outcome is another agent's deliverable; I only supply the quantification that
  says what the cells can and cannot change. Its launch (23:13:47Z) is recorded here as context.

Questions that would change downstream decisions (for the orchestrator, not answered here):
1. Is the intended fix allowed to change host memory sizing (`--hicache-size` / Mamba host split),
   or is the sweep constrained to `--max-mamba-cache-size` only? The data implies the former is the
   lever for the 60 s tails.
2. Should `hicache_restore_wait_timeout_s` (60 s T13) be tuned instead of/in addition to capacity,
   i.e. is a bounded 5–10 s wait + recompute acceptable when the host Mamba pool cannot ever stage
   the matched prefix?
3. Does the operator want the Mamba radix tree to retain its host checkpoints under pressure
   (the current behavior drops them, `hicache_dropped_tokens_total{mamba}`), or is recompute the
   accepted fallback — this decides whether capacity or policy is the fix.

---

## Terminal state

DONE
