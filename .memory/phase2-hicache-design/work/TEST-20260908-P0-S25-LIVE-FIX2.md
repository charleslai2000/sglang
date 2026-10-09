ENTRY: ACCEPT

# TEST-20260908-P0-S25-LIVE-FIX2

- Task ID: `TEST-20260908-P0-S25-LIVE-FIX2`
- Orchestration epoch: `2026-09-08-P0`
- Role: `tester`
- Invocation status: **done**
- Live verdict: **NOT_VERIFIED / fail-closed**
- Host: `root@175.155.64.171:24052`
- Checkout: `/root/sglang-b1-continuity`
- Evidence root: `/root/evidence-gate3-parked/p0-s25-v43-fix1-live-r10`

## Summary

The frozen S=25 RH-off live run was started successfully after remote cleanup,
source synchronization, focused-fixture verification, and exact engine
environment verification. The engine reached health 200 and served 9 HTTP
requests with HTTP 200 responses. Eight initial sessions emitted valid V3
`build_complete` identities.

The run could not reach durable restore acceptance. All eight vehicle build
workers blocked in the vehicle's `wait_for(ready_for_warm)` before submitting
the ninth session. Consequently the engine never received enough subsequent
traffic to evict the final build leaves; the only storage events were V2
ancestor events on nodes 26/27 with `context_complete=false`, not accepted
evidence for the final build identities. No exact final-node KV/Mamba durable
events, durability barriers, warm requests, or restore successes were
observed. This is a confirmed vehicle scheduling/test blocker with missing
live acceptance evidence, not an infrastructure capacity failure and not
enough evidence to classify the product implementation itself as defective.

P0 PASS is not claimed.

## Preconditions and source identity

- Root filesystem before launch: 24G available; `/data`: 122G available.
- Model path, absolute Python, checkout, and launcher were present.
- Launcher contained exactly one `--enable-session-radix-cache`; RH was off.
- Focused remote fixture: `P0 trace-context V4.3 focused checks: PASS`.
- Authoritative source:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py`
- Local source MD5: `e1111771af0c01e34b7ca6288c3c2c92`
- Remote post-sync MD5: `e1111771af0c01e34b7ca6288c3c2c92`
- Local/remote SHA-256:
  `acc21828eac866f0d2f05f465273c8d77f586693544b796f15e62b9f810b9460`
- Remote size: `268141` bytes.
- No local product file was modified by this invocation.

## Frozen launch and runtime evidence

- Run ID: `p0-s25-v43-fix1-live-r10`
- Model: Qwen3.5-9B w4a16
- S=25, active=8, build-workers=8, history=55000
- RH off, TP=1, Mamba ratio 0.42, HiCache ratio 1.3
- KV dtype `fp8_e4m3`, CUDA graph max BS 8
- `max_total_tokens=600000`; engine log resolved/profiled limit `501851`
- `wait_complete`, extent backend, 120G logical storage file
- Engine Python PID: `1023422`; `/proc/1023422/environ` contains the exact
  fresh `T38C_RUN_ID`, `T38C_BUILD_COMPLETE_DEBUG=1`, `PYTHONPATH`, model,
  RH, ratios, dtype, storage, and port values in
  `raw/proc-engine-environ.txt`.
- Vehicle Python PID: `1025583`.
- Engine became ready at `2026-09-08 10:34:03` and was stopped with SIGTERM
  after evidence capture; shutdown drained zero remaining requests.

## Raw event result

The preserved trace contains 409 JSONL events:

| Event | Count |
|---|---:|
| `build_complete` | 8 |
| `residency_release_enqueued` | 8 |
| `residency_free_complete` | 192 |
| `residency_detach` | 184 |
| `backup_host_commit` | 2 |
| `backup_submit` | 2 |
| `extent_commit` | 3 |
| `batch_set_result` | 4 |
| `backup_ack_enqueue` | 2 |
| `backup_ack_drain` | 2 |
| `storage_persisted` | 2 |
| `durability_barrier` | 0 |
| restore events | 0 |

The 8 build identities were:

```text
p0-s25-s00000 gen=3 node=112 hash=c05dd839b5d684a38458a88f5d5f4cf3ee7f19eb2a5b18d8ede50659188be118
p0-s25-s00001 gen=6 node=196 hash=1d02a83cce5c697616837130ab8bed320e5c7d74dc0d93bad98144f0769b4458
p0-s25-s00002 gen=5 node=168 hash=a01f613f10ed00d06d504f2e2e777b9e56157459b11533fa1c25cdea36371df4
p0-s25-s00003 gen=4 node=140 hash=147ead18456c4c47ead5c1ca6f0dfae083162cef680895e28ba942179c892423
p0-s25-s00004 gen=8 node=250 hash=6d33b7e39aa1e8f88c80f5f59748d7639eaa62b69d28a51754d2d33e28c60525
p0-s25-s00005 gen=2 node=84  hash=a6a116fa0dbdd2daf184614f24c5044f57c88266fa8845f9c11cdd29815f945b
p0-s25-s00006 gen=1 node=56  hash=e8bf87a0c3e98f5a3aafb4f62bfdc514c60ec23b27964ddacb50a4661d81c30d
p0-s25-s00007 gen=7 node=223 hash=f9e6c0b1f58da7a0fca0de713008761631ee5520d5c5800894f8682e0221f765
```

For every one of these 8 sessions:

- exact identity event count: `1` (the `build_complete` event only);
- exact final-node durable events: `[]`;
- exact KV durable/frontier: no evidence;
- exact Mamba ACK/durable/frontier: no evidence;
- `durability_barrier`: absent;
- warm request and restore success: absent.

The 2 `storage_persisted` rows were V2, `context_complete=false`, on ancestor
nodes 26 and 27. They were correctly rejected by the V3-only exact identity
join. Root rows: `0`. Root suppression/zero-key messages: none observed in the
preserved engine log. No conflicting duplicate or ancestor/final-node join was
accepted.

## HTTP, error, and progress checks

- `/v1/chat/completions`: 9 requests, 9 responses with HTTP 200.
- `/health`: 1 response 200 and 2 earlier 503 startup probes.
- `/model_info`: 1 response 200.
- `hicache_backup_tokens_total`: KV 64, Mamba 1.
- `evicted_tokens_total`: 61.
- `hicache_dropped_tokens_total`: 0 for KV and Mamba.
- No OOM or engine crash occurred. TorchCodec/libavutil import warnings were
  startup environment warnings; later Triton device-load warnings reported low
  free device memory but no OOM.
- Final vehicle stdout was empty because the vehicle was safely terminated
  while its 8 worker threads were waiting; the raw event and analysis files
  are authoritative for the partial run.

## Precise blocker classification

The vehicle implementation runs one `run_session` per worker and waits for
`ready_for_warm` before that worker returns to the thread pool. With exactly 8
build workers, all 8 workers became blocked after their first build. The
vehicle therefore submitted only 8 build requests, while the engine's final
build leaves remained resident and were not backed to L3. The next request,
which would be needed to create eviction pressure, could not be submitted by
this frozen vehicle.

Classification: **test/vehicle scheduling blocker plus missing acceptance
evidence**. The engine and storage capacity were available, valid V3 build
events were produced, and the run was stopped safely. This invocation does not
prove a product defect or a Mamba provenance defect; it also cannot prove
durable restore behavior for sessions 9--25.

## Artifacts

- Remote raw engine log: `/root/evidence-gate3-parked/p0-s25-v43-fix1-live-r10/engine/launcher.log`
- Remote raw event trace: `/root/evidence-gate3-parked/p0-s25-v43-fix1-live-r10/raw/t38c-probe.log.final`
- Post-stop identical trace copy: `raw/t38c-probe.log.poststop`
- Final per-session analysis: `raw/live-analysis-final.txt`
- Environment capture: `raw/launcher-env.txt`, `raw/proc-engine-environ.txt`
- Metrics: `raw/metrics-final.txt`
- Process and disk evidence: `raw/processes-before-stop.txt`,
  `raw/processes-after-stop.txt`, `raw/df-before-stop.txt`
- Evidence hashes: `raw/md5-final.txt`, `raw/sha256-final.txt`,
  `raw/evidence-sha256-final.txt`
- Remote storage file remains preserved at
  `/root/evidence-gate3-parked/p0-s25-v43-fix1-live-r10/storage/`.

## Cleanup and followups

- SIGTERM safely stopped vehicle PID `1025583`, engine PID `1023422`, and
  launcher wrapper PID `1023417`.
- Final process check: no matching engine, vehicle, or launcher process.
- `/tmp/t38c-durable-trace` is off; `/tmp/t38c-probe.log` was cleared only
  after the final raw copy was preserved.
- No prior evidence was deleted and no RH-on or larger-scale run was used.

A fresh Task ID is required for any vehicle scheduling change, alternate
churn driver, or rerun intended to force the ninth request and complete the
25-session durable restore gate. No such extra work was performed here.

## Open issues

1. The frozen vehicle cannot advance from its first 8 builds to session 9 while
   waiting for exact final-node durability; P0 live acceptance remains open.
2. 17 planned sessions did not start in this invocation.
3. No exact final-node KV/Mamba durable/frontier/barrier or restore evidence
   exists for the 8 started sessions.
4. The empty `raw/live-analysis-final.json` is an abandoned auxiliary analysis
   attempt; `raw/live-analysis-final.txt` is the valid final analysis.

done
