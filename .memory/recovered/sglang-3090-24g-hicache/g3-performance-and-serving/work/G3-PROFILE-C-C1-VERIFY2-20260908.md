# G3-PROFILE-C-C1-VERIFY2-20260908

ENTRY: ACCEPT

task_id: G3-PROFILE-C-C1-VERIFY2-20260908
epoch: E4
role: tester
invocation_status: done
verification_verdict: PASS_WITH_EVIDENCE_LIMITATION

## Scope and method

This was an independent read-only verification of the completed C1 decode
artifacts. No workload was run, no product file was changed, and no audit
hook, tracing mechanism, download, or new telemetry process was introduced.
The authorized host/artifact directory was read over:

```text
ssh -o BatchMode=yes -o ConnectTimeout=10 -p 22109 root@175.155.64.171
/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c1-decode-retry2-20260908/
```

The same files were independently parsed from the local copy. The remote
manifest was checked with `sha256sum -c sha256sums.txt`; all entries passed
except the manifest entry for the dmon file, described below.

## Artifacts

Remote:

```text
/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c1-decode-retry2-20260908/
```

Local:

```text
.memory/g3-baseline-20260907/work/raw/g3-profile-c1-decode-retry2-20260908/
```

Key hashes (SHA-256, verified against the local copy and remote content):

```text
c172f6deddf06d66ac12b1d016d9bc8fb9efd5a1c0cf5aabbd7d074c8f5fc883  runner/repeat-1.jsonl
dc27ce7b102674b9d86d25da33ae80b886f7fc85ee5acf1ff43730a0b8b08899  runner/repeat-2.jsonl
9fc6804a3d2b23fd176821709411daded16deebfe1292678d1f76393b540cad8  runner/repeat-3.jsonl
7f6a24802960697685f59e051c5f37cc1ff0a6f4880fd6a11cdf3c675c1a2227  runner/repeat-1.log
420bbeae5082765301336694c5e32e23c03f72fbb395386922f00f7e3e729b22  runner/repeat-2.log
7238b1445614195545c290e6af403ed29b37a2a2e75ce37098044131d457a581  runner/repeat-3.log
d942b247998370d67f4dd53daebde27b17f70e8189f1279681bb44620d91dd6a  driver.log
941d3d11157246683d5639c2d1253f635df130cdb0b165202a90574be7ca83ae  loads.before-r1.json
c714301834fc79fb6026fe31b0483941c20ca5d7559beeb65e37630b937e03e9  loads.after-r1.json
b1f3181c7be68eefd13fdd86ffb2887f18235a1d2db0f4647a65b34081e4546c  loads.before-r2.json
283eeda593cff83b25650ecaeb32e900ec3db6a33202465f593adbf36720210d  loads.after-r2.json
2da9b236098cfc04e71b87d95e41522c0499d5f866f9d285991e02042113beac  loads.before-r3.json
d874675077789c2a14401cb866a50d2bc3c419c75f1788a2fc0c4362b3756422  loads.after-r3.json
77961c61836849ecae71356ff592b7a064723b688545a82d9078c2cd58fbd05a  loads.after.json
ada9e1573dc8b99b6ff8acc88458992f12a2a84f7475e6a3825afec536dec423  telemetry/nvidia-smi-query.csv
ebd5943579f172106553c2e364a08ee8182632270b07e6fa8ef0f590564ce9fb  telemetry/nvidia-smi-dmon.txt
ddb37b8116a928d633933d7f51cf7d09e8bbb04e0f4ffbc090358024a3f964c9  service.ps.txt
a68f37a5cec2ba9f5d8c3a2d174045e67c06f60de18b391cc502f1e5c9e8fc45  service.ss.txt
```

The remote `sha256sums.txt` records
`6bcb600af892bb4ffe68e8bb5330728d14b5178244717e1a1d9274b8b6f3f37` for the
dmon file, but the actual remote file hashes to
`ebd5943579f172106553c2e364a08ee8182632270b07e6fa8ef0f590564ce9fb`.
The remote and local dmon files match each other; only the manifest entry is
stale or incorrect. No raw file was changed.

## Runner and workload verification

All three runner logs independently show runner version `0.5.10.dev0` via the
server/load identity and the same native command shape:

```text
/data/sglang-qwen35-env/bin/python -m sglang.benchmark.serving \
  --backend sglang --base-url http://127.0.0.1:18035 \
  --model /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf \
  --tokenizer /data/models/Qwen3.8-27B-GSQ-RCO-GGUF \
  --dataset-name random-ids --tokenize-prompt \
  --random-input-len 1024 --random-output-len 256 \
  --random-range-ratio 1.0 --request-rate inf --seed 42 \
  --max-concurrency 4 --num-prompts 32 --output-details \
  --flush-cache --flush-cache-timeout 60 --warmup-requests 3|0
```

Streaming and ignore-EOS disabling flags were omitted. The runner logs show
`dataset_name=random-ids`, `tokenize_prompt=True`, ratio `1.0`, seed `42`,
`request_rate=inf`, and `max_concurrency=4` for every repeat. Offline flags
and empty proxy variables are recorded by the executor report; there is no
download or dataset access error in the raw output.

The parsed JSONL summaries each contain exactly 32 input lengths, all exactly
1024, and exactly 32 output lengths, all exactly 256. Each has 32 TTFT values,
32 ITL arrays, `completed=32`, and 32 empty error strings. Thus the requested
fixed-length workload and completion count are independently supported.

## Repeat outcomes

| repeat | warmup | RC | completed | duration (s) | output tok/s | total tok/s | concurrency | median TTFT (ms) | median TPOT (ms) | median E2E (ms) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3 | 0 | 32/32 | 241.21 | 33.9625 | 169.8123 | 3.9934 | 4547.03 | 98.72 | 30173.43 |
| 2 | 0 | 0 | 32/32 | 241.65 | 33.9000 | 169.5002 | 3.9946 | 4757.99 | 99.37 | 30199.79 |
| 3 | 0 | 0 | 32/32 | 241.60 | 33.9076 | 169.5380 | 3.9947 | 4754.20 | 99.47 | 30205.26 |

Other reported percentiles, preserved in each JSONL/log, include:

```text
repeat 1: TTFT p95/p99 5823.19/5845.88 ms; TPOT p95/p99 107.51/110.45 ms;
          E2E p95/p99 30229.21/30230.20 ms
repeat 2: TTFT p95/p99 5835.03/5842.83 ms; TPOT p95/p99 105.78/108.90 ms;
          E2E p95/p99 30257.49/30307.42 ms
repeat 3: TTFT p95/p99 5832.06/5839.53 ms; TPOT p95/p99 105.76/108.97 ms;
          E2E p95/p99 30259.62/30320.06 ms
```

Per-repeat totals are 32,768 input tokens and 8,192 generated tokens. The
runner also reports 7,759 retokenized output tokens; this discrepancy is
preserved, not corrected or interpreted as a failed completion. No HTTP error,
timeout, or zero-progress signal appears in the logs. The only recurring
stderr is the post-success `multiprocess.resource_tracker` destructor
traceback (`AttributeError: '_thread.RLock' object has no attribute
'_recursion_count'`), while every benchmark exits RC 0.

## Service invariants and cache flush evidence

Captured candidate identity (`service.ps.txt`) is PID 478926 on loopback
127.0.0.1:18035 with:

```text
--max-running-requests 4
--max-mamba-cache-size 20
--cuda-graph-max-bs-decode 4
--kv-cache-dtype fp8_e4m3
--mamba-radix-cache-strategy extra_buffer_lazy
--reasoning-parser auto
--tool-call-parser qwen3_coder
--default-chat-template-kwargs {"preserve_thinking": false}
```

The runner-reported service identity independently resolves to load format
`gguf`, KV dtype `fp8_e4m3`, max running requests 4, Mamba cache size 20,
decode graph max batch size 4, and `hicache_size=0` with hierarchical cache
disabled. `/v1/loads?include=all` before and after each repeat reports
`max_running_requests=4`, `max_total_num_tokens=148053`, and idle
`num_running_reqs=0` at snapshot time. Allocated memory fields are stable at
weights 11.857 GB, KV cache 4.518 GB, and graph 1.9 GB.

Each repeat command includes `--flush-cache`; the before-repeat snapshots have
`num_used_tokens=0` and the driver records warmups `3,0,0`. This supports the
authorized flush-before-repeat sequence. The snapshots are idle endpoint
observations, not an in-flight concurrency trace.

## Concurrency anomaly and telemetry limitations

The runner reports `Peak concurrent requests: 8` in all three summaries even
though nominal `max_concurrency=4`, server `max_running_requests=4`, and
average measured concurrency is 3.99. The endpoint snapshots were taken only
before/after each repeat and all show idle, so they cannot independently
validate an in-flight peak. The evidence supports an effective admission cap
of 4 and average occupancy near 4, but does not support treating the runner's
peak value 8 as actual service concurrency. It should be retained as a
runner metric anomaly for the parent report.

The dmon file contains 747 numeric samples spanning 03:04:43 through
03:17:45, including the three benchmark windows. Correctly interpreted dmon
columns give these window averages:

```text
repeat 1 (254 rows): power 330.9 W, temperature 69.1 C, SM 92.8%, MEM 57.4%, FB 22984.4 MiB
repeat 2 (247 rows): power 332.3 W, temperature 70.8 C, SM 93.1%, MEM 57.7%, FB 22994.6 MiB
repeat 3 (248 rows): power 331.1 W, temperature 70.7 C, SM 92.7%, MEM 57.8%, FB 22995.2 MiB
```

The dmon stream has short sampling gaps (not every second is present in the
raw file); these are reported as-is. The query CSV contains 10 one-second
samples from 03:04:43–03:04:52, before/during the start of repeat 1, but no
post-repeat query samples. Therefore query telemetry cannot independently
provide a complete three-repeat window; dmon remains the usable raw GPU
telemetry for this run.

No prefill/decode-specific throughput fields are emitted by this runner, so
those fields are unavailable rather than inferred. HiCache device/host/
storage fields are N/A because HiCache is disabled; the regular radix cache was
flushed between repeats.

## Independent conclusion

**PASS for C1 measured workload and repeat outcomes, with two evidence issues:**

1. The runner's peak-concurrency field is internally inconsistent with the
   service cap and must not be interpreted as actual C8 behavior.
2. The remote hash manifest has one stale dmon digest, while the actual remote
   and local dmon bytes agree. Query sampling is also incomplete after the
   first repeat window.

The C1 benchmark itself is reproducible from preserved raw JSONL/logs,
completed 96/96 measured requests across three repeats, and produced no
request failure. No unsupported percentile, prefill/decode, cache-device, or
client-RSS value is claimed.

## Followups

- Parent may proceed with the already authorized C2/C3 sweep only after its
  normal serialized launch/restore gates.
- Preserve the dmon file and stale-manifest discrepancy; do not rewrite the
  raw manifest as if the original artifact had a different hash.

Final status: **done**
