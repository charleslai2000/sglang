STATUS: done

# TEST-20260908-P0-S25-LIVE-EMITTER-FIX3

- Invocation status: done
- Live verdict: **NOT_VERIFIED / fail-closed**
- Host: `root@175.155.64.171:24052`
- Remote checkout: `/root/sglang-b1-continuity`
- Run ID: `p0-s25-v43-emitter-fix3-live-r13`
- Evidence: `/data/evidence-gate3-parked/p0-s25-v43-emitter-fix3-live-r13`

## Summary

The fresh S=25, RH-off run used the accepted FIX3 emitter and FIX1 target-churn
vehicle with exact source-hash agreement. It produced 25 target builds, exactly
9 unique churn builds, and 25 combined KV/Mamba durability barriers. It produced
**zero** strict product `residency_barrier(cold_residency=true)` events, so the
vehicle issued no warm request and observed no restore success. The run was
stopped early and safely after the observed causal condition: the final node had
exact KV/Mamba detach+free, but no subsequent queue-drain trigger, leaving the
barrier/vehicle wait unresolved. No barrier, warm, restore, or PASS result was
synthesized.

## Source identity and preconditions

Remote hashes matched the local worktree before launch:

```text
150cb9cf4cb9a53c6e646e132d9f71ca9f403e9d8db0afc0bf984cc01e9243fe  python/sglang/srt/mem_cache/unified_radix_cache.py
5965d8d8744dc0f0f106064b9dd69d26a4069b67ff88fbf0614c3a2766d3bd62  3090-dev/p0_session_barrier_vehicle.py
fbc5dfedd081b0ee8ec5a7aaf6c4928fbf43b615716ef8f464372d47c772a30f  3090-dev/test_p0_trace_context_v4.py
8d59823b64ab7359b113c7ed790e22d1903ac3d529b837421777b14c81401b09  3090-dev/direct-launch-gate3-parked.sh
```

The remote V4.3 fixture passed before launch. The launcher command line had
exactly one `--enable-session-radix-cache`. Frozen configuration was preserved:
S=25, history=55000, active=8, build_workers=8, RH=off, TP=1, Qwen3.5-9B
w4a16, `fp8_e4m3`, Mamba ratio 0.42, HiCache ratio 1.3, `wait_complete`,
120G extent storage, graph8, max_total_tokens 600000.

## Commands and timeline

Source sync used `scp` for the authorized product, vehicle, and fixture files;
no checkout reset was performed. The accepted launcher was run with:

```text
STORAGE_DIR=/data/evidence-gate3-parked/p0-s25-v43-emitter-fix3-live-r13/storage \
MAX_SIZE=120G FILE_SIZE=120G RH=off SGLANG_PORT=8024 \
MODEL_PATH=/root/models/Qwen3.5-9B-w4a16 SERVED=qwen3.5-9b-gptq \
KV_DTYPE=fp8_e4m3 MAMBA_RATIO=0.42 HICACHE_RATIO=1.3 \
T38C_RUN_ID=p0-s25-v43-emitter-fix3-live-r13 T38C_BUILD_COMPLETE_DEBUG=1 \
PYTHONPATH=/root/sglang-b1-continuity/3090-dev \
./3090-dev/direct-launch-gate3-parked.sh
```

The exact vehicle command was preserved in `raw/vehicle-command.txt`; it used
the required `--sessions 25 --active 8 --build-workers 8 --history-target 55000
--rh off`, fresh `/tmp/t38c-probe.log`, and the `/data` evidence directory.

- Engine launched as PID 1040731; health reached HTTP 200 at
  `2026-09-08T14:04:47+08:00`.
- Vehicle ran as PID 1041299 and reached its observed terminal condition only
  through the authorized early-stop path at `2026-09-08T14:24:40+08:00`.
- Vehicle SIGTERM was confirmed gone at `14:24:42`; captured exit code was 143.
- Engine SIGTERM was sent at `2026-09-08T14:25:27` and PID 1040731 was gone at
  `14:25:35`.
- Final matching-process check found no engine, vehicle, or launcher process.

## Raw runtime counts

Counts are independently parsed from the preserved post-stop trace and restricted
to the r13 run ID:

| Evidence | Result |
|---|---:|
| Target `build_complete` identities | 25/25 |
| Churn `build_complete` identities | 9/9 |
| Total `build_complete` | 34 |
| Build order | all 25 target, then all 9 churn |
| Unique target sessions / build RIDs | 25 / 25 |
| Unique churn sessions / build RIDs | 9 / 9 |
| `durability_barrier` | 25 |
| Durability `combined_durable` / KV / Mamba | 25 / 25 / 25 |
| Durability records with all six identity fields non-empty | 25/25 |
| Strict `residency_barrier` | 0 |
| Strict residency `cold_residency=true` | 0/25 |
| `warm_lookup_start` / `warm_request` | 0 / 0 |
| Restore success events | 0 |
| `residency_detach` / `residency_free_complete` | 1589 / 1993 |
| Total parsed r13 events | 9698 |

The absence of a strict residency event is a product/runtime evidence failure,
not a vehicle pass condition. The vehicle bundle files that require final
`_write_bundle` execution (`barrier-waits.jsonl`, `build-warm.jsonl`,
`reducer-result.json`, and `verdict.json`) were not produced because the
vehicle was deliberately stopped after the causal deadlock was recorded. This
missing bundle is explicitly recorded in `vehicle/terminal-artifacts-status.txt`;
no synthetic rows were created.

## Trace and runtime artifacts

Pre-stop and post-stop copies are byte-identical:

```text
SHA-256: 01fd2aba55d24b013beb4d8a99ac431ccd65f4130a246b42d09ed7c2fb906f36
Bytes:   11067166
Compare: identical
```

The remote evidence contains the launcher environment/command, `/proc` captures,
health polling, raw event copies, early-stop final events, vehicle stdout/stderr,
source hashes, process snapshots, stop records, raw counts, and final disk state.
The optional libtorchcodec import traceback is present in the engine log as a
pre-existing nonfatal warning. No CUDA out-of-memory, assertion, zero-progress,
or SIGSEGV marker was found. One HTTP 503 was observed during startup health
polling before HTTP 200; no vehicle request failure is claimed from that event.

## Comparison with r12

r12 had 25/25 target builds, 9 churn builds, 25 durability barriers, 0 strict
residency barriers, and 0 warm/restore. r13 reproduces the same acceptance-blocking
residency outcome despite the accepted FIX3 source hash and adds preserved causal
evidence of final detach+free without a queue-drain trigger. Therefore r13 does
not upgrade the result to runtime PASS.

## Open issues

1. Product/runtime emitted no strict residency barrier after 25 durability
   barriers; warm and restore were consequently never eligible.
2. The observed final detach+free had no subsequent queue-drain trigger,
   producing the barrier/vehicle deadlock. Hard causal diagnosis remains for
   `debugger-deep` under a fresh Task ID.
3. The vehicle was intentionally SIGTERM-stopped before its 1800-second
   watchdog to preserve evidence; exit 143 is an early-stop terminal status,
   not a natural vehicle verdict.
4. Final vehicle reducer/warm artifacts are unavailable because `_write_bundle`
   was not reached. The raw trace and explicit missing-artifact status are
   preserved; no evidence was synthesized.

## Status packet

- Status: `done`
- Artifacts: remote evidence at
  `/data/evidence-gate3-parked/p0-s25-v43-emitter-fix3-live-r13` and this report.
- Evidence: source hashes, remote fixture PASS, health/process captures, raw
  counts, pre/post trace hash, early-stop basis, vehicle exit 143, engine stop,
  and final zero matching processes.
- Summary: `NOT_VERIFIED / fail-closed`; 25 target + 9 churn + 25 durability,
  0 strict residency, 0 warm, 0 restore.
- Followups: route the queue-drain/barrier deadlock to `debugger-deep` with a
  fresh Task ID; preserve r11/r12 and this r13 evidence.
- Open issues: listed above.
