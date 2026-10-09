ENTRY: ACCEPT

# TEST-20260908-P0-S25-LIVE-FIX4

- Task ID: `TEST-20260908-P0-S25-LIVE-FIX4`
- Orchestration epoch: `2026-09-08-P0`
- Role: `tester`
- Invocation status: **done**
- Live verdict: **NOT_VERIFIED / fail-closed**
- Host: `root@175.155.64.171:24052`
- Checkout: `/root/sglang-b1-continuity`
- Run ID: `p0-s25-v43-fix4-live-r11`
- Evidence root: `/root/evidence-gate3-parked/p0-s25-v43-fix4-live-r11`

## Summary

The accepted cache FIX1 and vehicle FIX4 were synchronized and independently
verified on the remote checkout. The frozen S=25 run produced all 25 exact
V3 `build_complete` identities. Sixteen sessions reached an exact final-node
KV+Mamba durability barrier, but no session reached the required cold
residency barrier. The vehicle therefore correctly issued no warm request and
no restore request.

The run is **not a P0 PASS**. The blocker is a vehicle/workload churn gap:
after the 25 builds, the frozen vehicle did not generate enough subsequent
churn to drive every final build node through the required eviction/cold
residency chain. Nine sessions never reached the exact KV+Mamba durability
barrier, and all 25 lacked `residency_barrier(cold_residency=true)`. This is
missing acceptance evidence caused by the vehicle workload, not evidence of a
product restore defect or an infrastructure capacity failure.

## Preconditions and source identity

- Remote root before launch: 24G free; `/data`: 122G free.
- r10 evidence and its 120G storage were preserved; r10 was not modified.
- Focused remote fixture: `P0 trace-context V4.3 focused checks: PASS`.
- Remote source SHA-256 after sync:
  - `python/sglang/srt/mem_cache/unified_radix_cache.py`: `acc21828eac866f0d2f05f465273c8d77f586693544b796f15e62b9f810b9460`
  - `3090-dev/p0_session_barrier_vehicle.py`: `dc590169bcd10aa91ebd5859f530f5386045cdffa645aad869186f49d64703ed`
  - `3090-dev/test_p0_trace_context_v4.py`: `3edf72dac645cb90ac07915301e9e807dbda438f5fad4a95d9fb02666e0019b8`
- The three hashes match the gate-reviewed local accepted sources in
  `sglang-3090-24g-opt`.
- No local product implementation file was modified.

## Frozen runtime contract

S=25, active=8, build-workers=8, history=55000, RH off, Qwen3.5-9B
w4a16, TP=1, Mamba ratio 0.42, HiCache ratio 1.3, `fp8_e4m3`, graph8,
max-total 600000, resolved/profiled 501851, `wait_complete`, extent backend,
120G logical storage. The launcher command contained exactly one
`--enable-session-radix-cache`. `/proc/$engine_pid/environ` matched the fresh
run ID, `T38C_BUILD_COMPLETE_DEBUG=1`, and absolute `PYTHONPATH` before the
vehicle started.

## Runtime counts

| Evidence | Count/result |
|---|---:|
| Exact V3 `build_complete` | 25/25 |
| Root-node build suppression | 0 |
| Any `build_complete` suppression | 0 |
| `storage_persisted` | 448 |
| `backup_submit` / ACK drain | 448 / 448 |
| `extent_commit` | 1131 |
| `durability_barrier` | 16 |
| Exact KV durable on barrier | 16/16 |
| Exact Mamba durable on barrier | 16/16 |
| `residency_barrier(cold_residency=true)` | 0/25 |
| Warm request / lookup | 0 |
| Restore success | 0 |
| Historical recompute | 0 observed; acceptance not measurable because no warm occurred |
| Chat HTTP 200 | 26 |
| Chat HTTP 4xx/5xx | 0 |
| Assertion failures | 0 |
| Actual OOM | 0 |
| Zero-progress markers | 0 |

The seven log lines containing “CUDA OOM” are Triton low-free-memory
preload advisories, not OOM failures. The libtorchcodec traceback is the
pre-existing optional media import warning. The final asyncio cancellation
trace is shutdown fallout after the requested SIGTERM, not a request failure.

## Exact build identities and durable chain

The final-node identity tuples below are taken from the post-stop trace. The
display table abbreviates long IDs; the full exact tuples follow it. A
durable `Y` means the same exact identity reached a barrier carrying both
`kv_durable=true` and `mamba_durable=true`; no row reached the residency
barrier, warm, or restore stages.

| Session | Build RID | Node | Final KV hash | KV+Mamba durable | Residency | Warm/restore |
|---|---|---:|---|:---:|:---:|:---:|
| s00000 | `de1a726d…00adc` | 56 | `a89002a1…d7f4bf8` | Y | N | N/N |
| s00001 | `9400e752…9eca9` | 140 | `f1f9c6c1…f0f88de5` | Y | N | N/N |
| s00002 | `80099605…021f5c` | 196 | `3bb6ca49…f2ad8de` | Y | N | N/N |
| s00003 | `54d4dce5…4af3a2` | 168 | `f24eeb32…a1c75a` | Y | N | N/N |
| s00004 | `f5fc70c8…6df941` | 250 | `6d33b7e3…c60525` | Y | N | N/N |
| s00005 | `56146b26…7b3d6a` | 112 | `9eec83ac…0fe32ee` | Y | N | N/N |
| s00006 | `fe427a08…0b7848e` | 84 | `1c1133a0…126c600` | Y | N | N/N |
| s00007 | `82e11792…563e533` | 223 | `f9e6c0b1…221f765` | Y | N | N/N |
| s00008 | `83117e46…94f208` | 279 | `41eea7f3…91c118b` | Y | N | N/N |
| s00009 | `ddd8ac23…e5f73afa` | 446 | `2e574097…6a32077` | Y | N | N/N |
| s00010 | `ee8baaaa…6dac7db` | 473 | `96db3856…a4c8614` | Y | N | N/N |
| s00011 | `701f6b33…8ef7542` | 335 | `e99290bf…9d7b3fa9` | Y | N | N/N |
| s00012 | `f7c5ba89…e0e7893c8` | 391 | `a9781d8b…0fbf1a9` | Y | N | N/N |
| s00013 | `beb7562e…4fbc52890` | 363 | `d53c2b63…572dabfd` | Y | N | N/N |
| s00014 | `3a61472e…d9cb26f` | 307 | `83425ca4…4050671` | Y | N | N/N |
| s00015 | `61acd4fe…0b4bd` | 419 | `dde4d97b…ec214785` | Y | N | N/N |
| s00016 | `51abc069…252b065` | 586 | `8bbfe16d…c488d04` | N | N | N/N |
| s00017 | `3273a617…2fa8ba` | 669 | `dccaaa5b…ec51e13` | N | N | N/N |
| s00018 | `bcfb1267…6b4f4` | 696 | `0058510c…e8e0bfeb` | N | N | N/N |
| s00019 | `0357c0ee…6d5794` | 530 | `e17a809a…e429f39` | N | N | N/N |
| s00020 | `75183aae…39ce88` | 502 | `5935031e…88ab422` | N | N | N/N |
| s00021 | `7c03c4b7…436782` | 614 | `45a68028…e2fb1d2` | N | N | N/N |
| s00022 | `da8d3a09…a014b3f6` | 642 | `e2236034…24c04f85` | N | N | N/N |
| s00023 | `52bc7a98…0983cb` | 558 | `ed17bde9…c7fe2b9` | N | N | N/N |
| s00024 | `113c8b7d…1bc059a0` | 723 | `d6d5e150…f35a258` | N | N | N/N |

Full exact `(session, build_rid, node_id, final_kv_hash)` tuples:

```text
s00000 de1a726dd693480d8947544d1de00adc 56 a89002a12dcf2354ed09ff7fa51975f517dd3971cfd7930667a05beded7f4bf8
s00001 9400e752bc014011897ceced4f09eca9 140 f1f9c6c1b28f08527cbc06e23bf0cfea6ad25a8ed8b6edc1f75fa81cf0f88de5
s00002 800996058eec459f89dbbb98e4021f5c 196 3bb6ca491db0290ff050cd7f4f8e4110d57b290523c7c15569006e357f2ad8de
s00003 54d4dce576074619a0e12326420af3a2 168 f24eeb32ca8204961f7e5367eaf6ba94bb5bfd9ed6b1f61ff50272a5c9a1c75a
s00004 f5fc70c8cb654ec083f44d55b66df941 250 6d33b7e39aa1e8f88c80f5f59748d7639eaa62b69d28a51754d2d33e28c60525
s00005 56146b2644dc4d258daa046ae77b3d6a 112 9eec83ac6f3fc96ef415d5e962a07f030542c84e3bfc430f7a4d1c3800fe32ee
s00006 fe427a08ed2a4c8f8f70c0fed0b7848e 84 1c1133a0108b0d3c9e307b35110cf60ba1fbb1d6b83ba59f3156f7707126c600
s00007 82e11792c46f48c4b308af6c8563e533 223 f9e6c0b1f58da7a0fca0de713008761631ee5520d5c5800894f8682e0221f765
s00008 83117e4691a644dfbcb32db1ba94f208 279 41eea7f3dce75c5edb4a67c3c01c49278d374bb79c999a88e16f61ab191c118b
s00009 ddd8ac23f4a84e13a0b47ecce5f73afa 446 2e574097696a713fe4fbdf03d68b4d27bd13de87ebc40406d694c54d86a32077
s00010 ee8baaaa05b04bdc8fd06009b6dac7db 473 96db38566a25bff53e2fc37ed7dda3ceac675ec592dcdca5c6a65d9b6a4c8614
s00011 701f6b33818b4e9aa6286df728ef7542 335 e99290bfd811620ddf74a06439777046b90c4b06108d0da9878849d29d7b3fa9
s00012 f7c5ba8972f945f0801d83ee0e7893c8 391 a9781d8b613978cc4dae708e2db5d396b5365b391a6056f7fafadb8390fbf1a9
s00013 beb7562eb4514db4be677a0f4bc52890 363 d53c2b6352398cf000622dbf4fdb26c17f74246e66c315d14c777369572dabfd
s00014 3a61472e534141f986c476433d9cb26f 307 83425cae4655776b916edc760f4019cb9eeec9b8449375f842c33a5b64050671
s00015 61acd4fe3bdf46dabbf235f85cb0b4bd 419 dde4d97b709f9c526fc9ff78c71e0a7511521401e8b348a393040049ec214785
s00016 51abc069d0454948a547def24252b065 586 8bbfe16d98b80e1865d0f3db551236144ea5c8856f70ee9000445974ec488d04
s00017 3273a6177810426f8de1d0d32b2fa8ba 669 dccaaa5b908a7c3e271d15159bd61516bb16d70d78466a1f655375e1fec51e13
s00018 bcfb1267b6b0426cb9661d5ba36f4ff4 696 0058510c26d5f3f987b439e9c90484a5c59e11254d49d7c2855a5232e8e0bfeb
s00019 0357c0eeb603471ca1f9f6f8746d5794 530 e17a809ac3f9b94ca8762a4e7a44223bb73a0683e56caad7d1496002ae429f39
s00020 75183aae730047eab1b93190df39ce88 502 5935031ecdb75c496ea6aa237a61aea8eca456517964f1217b61f6c7088ab422
s00021 7c03c4b78ab845059077d7402a436782 614 45a68028ba63f34cd36f956129abaa8ed603d9db0e36e235d5e5e1e88e2fb1d2
s00022 da8d3a090fdd4cfbb0a340faa014b3f6 642 e2236034a24a01235c951bbb660f1ee95a16ba763649cfaa53ab586224c04f85
s00023 52bc7a985ac24fc09565c8674f0983cb 558 ed17bde9067f49458d5821e3b3aec316bb49779d60cfe581ea9c25454c7fe2b9
s00024 113c8b7d6cf745c2b5e9ee2e1bc059a0 723 d6d5e150fa885ea7968cd3b5095da7ef994a248df641983cb31638d81f35a258
```

Durable sessions were exactly `s00000`–`s00015`; sessions `s00016`–`s00024`
had build identities but no exact combined durability barrier. No root node
identity or root suppression was observed. No false session reference was
observed, but no positive session-reference/warm chain was produced, so that
criterion cannot be accepted from this run.

## Causal order and missing acceptance evidence

For the 16 durable sessions, the trace order was:

`build_complete → exact KV durable evidence → exact Mamba durable evidence → durability_barrier(combined_durable=true)`.

The required next edge, `residency_barrier(cold_residency=true)`, never
appeared. FIX4 therefore issued no warm request, and there is no causal
warm→restore chain, restore metrics, TTFT, or historical-recompute metric to
accept. The 25 builds and partial backup traffic are evidence of progress, not
evidence of durable full-storage restore.

## Stop and artifacts

- Vehicle PID `1031255`: SIGTERM, exited in the second wait interval.
- Engine PID `1030857`: SIGTERM, exited in the thirteenth wait interval.
- No matching engine/vehicle/launcher process remained after stop.
- Pre-stop and post-stop trace copies are byte-identical:
  `sha256=14fdf4144a8da2a7192330ef3b856269e59a942572f00bf52347ef5f94886724`,
  6243 lines, 7166051 bytes.
- Final trace: `/root/evidence-gate3-parked/p0-s25-v43-fix4-live-r11/raw/t38c-probe.log.poststop`
- Engine log: `/root/evidence-gate3-parked/p0-s25-v43-fix4-live-r11/engine/launcher.log`
- Vehicle log: `/root/evidence-gate3-parked/p0-s25-v43-fix4-live-r11/vehicle/vehicle.log`
- Hash manifests: `raw/sha256-final.txt`, `raw/md5-final.txt`,
  `raw/evidence-sha256-final.txt`
- Environment: `raw/launcher-env.txt`, `raw/proc-launcher-environ.txt`
- Process/disk evidence: `raw/processes-before-stop-final.txt`,
  `raw/processes-after-stop-final.txt`, `raw/df-after-stop.txt`
- r10 preservation check: `/root/evidence-gate3-parked/p0-s25-v43-fix1-live-r10/raw/evidence-sha256-final.txt` remained present.

## Followups

- Fresh Task ID required for any vehicle workload/churn change or rerun.
- Add an explicit post-build churn phase that drives the final build leaves
  through cold residency, while retaining the exact per-session KV+Mamba and
  barrier gates. Do not infer residency from fixed sleep or from backup counts.
- Re-run the frozen S=25 acceptance only after that vehicle change is
  independently gated.

## Open issues

1. The frozen vehicle does not provide enough post-build churn to complete the
   final-node residency chain for all 25 sessions.
2. Because no warm request was admitted, P0 restore success, historical
   recompute, TTFT, and full-storage residency cannot be evaluated.
3. The server log has 26 chat HTTP 200 responses but only 25 V3 build
   identities; the killed vehicle did not emit its final bundle, so the extra
   request cannot be mapped to an accepted warm/restore event. This is an
   accounting gap, not a synthesized success.

done
