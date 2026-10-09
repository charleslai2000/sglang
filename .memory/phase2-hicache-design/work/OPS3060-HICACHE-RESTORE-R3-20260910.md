# OPS3060-HICACHE-RESTORE-R3-20260910

## Profile

- RTX 3060 12 GB; Qwen3.5-4B AWQ W4A16/Marlin; FP8 E4M3 KV.
- `max_total_tokens=65536`, HiCache file backend, write-through, data-disk path
  `/hy-tmp/hicache-restore-r3`.
- RH was OFF for the deterministic restore paths. The service was restored to
  RH-ON c1 after the run.
- Each prompt had exactly 55,000 pre-tokenized input IDs and one generated token.
  The 24-token page tail is not historical recompute; it is the legal tail after
  the 54,976-token cached prefix.

## Results

| Residency path | HTTP | Cached device | Cached host | Cached storage | Wall/e2e | Result |
|---|---:|---:|---:|---:|---:|---|
| GPU resident repeat | 200 | 54,976 | 0 | 0 | 0.236/0.230 s | PASS |
| Host resident resume | 200 | 10,240 | 44,736 | 0 | 0.401/0.391 s | PASS |
| L3 resident after restart | 200 | 0 | 0 | 54,976 | 38.311/38.301 s | PASS |

All three paths returned one completion token and reported `prompt_tokens=55000`.
The GPU repeat had `cached_tokens=54976`; host resume had `cached_tokens=54976`;
the L3 resume had `cached_tokens=54976`. No path performed a full-history
recompute. The L3 path was a real post-restart storage lookup with no GPU or Host
residency left to satisfy the request.

## Durability gate evidence

The first cold-only attempt was intentionally rejected as a durability setup:
the session still fit the 65K device pool, so it did not force complete old-
session eviction before the ACK frontier advanced. It was not used as a result.

The corrected A+B run used two distinct 55K histories. It waited on the actual
`p0_durable.v2` `backup_ack_drain` records with both
`kv_durable=true` and `mamba_all_rank_durable=true`, aggregating unique
operations until the gate observed 50 complete operations and 100,096 durable
tokens. A then resumed with host attribution, and after a server restart the
same A history resumed with 54,976 storage-hit tokens. This restart result is
the decisive proof that A's KV+Mamba state was materially present in L3; the
trace also records Mamba-complete ACKs for the backing operations.

## Interpretation

- 3060 production-candidate path is stable for one 55K parked session across
  GPU, Host, and L3 tiers.
- Measured warm-path ordering is approximately GPU 0.23s, Host 0.39s, and L3
  on-demand 38.3s. The L3 number is expected to include storage transfer and
  scheduler/prefill work; it is not a Host-ready result.
- The earlier cold-only gate timeout exposed an important operational rule:
  durable testing must force/observe eviction and ACK completion before wake.
  Fixed sleep is not a valid gate.
- This closes the single-session P4 restore requirement. It does not yet close
  multi-session durability at 8-way scale or Ready Horizon OFF/ON staging.

## Service handoff

Final remote service is AWQ/Marlin + FP8 KV, `max_total_tokens=65536`, HiCache
file backend on `/hy-tmp/hicache-restore-r3`, RH ON with frontier-n 8; health is
HTTP 200 and idle GPU memory is approximately 8513 MiB used / 3525 MiB free.

