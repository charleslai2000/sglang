# G3-PROFILE-C-C8-DECODE-20260908

status: done

## Scope and command

Authorized host `175.155.64.171:22109`; candidate PID `497622`, loopback
`127.0.0.1:18037`. Candidate args were verified before measurement and remained
unchanged: `--max-running-requests 8 --max-mamba-cache-size 40
--cuda-graph-max-bs-decode 8`, frozen v1 parser/KV/cache/template flags.

Each of three repeats used the native deployed runner
`/data/sglang-qwen35-env/bin/python -m sglang.benchmark.serving` with
`--backend sglang --dataset-name random-ids --tokenize-prompt
--random-input-len 1024 --random-output-len 256 --random-range-ratio 1.0
--request-rate inf --seed 42 --max-concurrency 8 --num-prompts 64
--output-details --flush-cache --flush-cache-timeout 60 --warmup-requests 0`.
Streaming and ignore-EOS disable flags were omitted. Offline environment
variables were set; no dataset/model download occurred. `random-ids` semantics
were preserved exactly for this checkout.

## Outcomes

All repeats completed with rc=0, 64/64 successful requests, 65,536 input and
16,384 requested output tokens. Runner aggregate output throughput was:

| repeat | output tok/s | total tok/s | median TTFT ms | median TPOT ms | median E2E ms |
|---|---:|---:|---:|---:|---:|
| 1 | 36.61 | 183.07 | 8213.47 | 185.98 | 55985.23 |
| 2 | 36.56 | 182.79 | 8974.25 | 184.35 | 55987.13 |
| 3 | 36.54 | 182.68 | 8988.59 | 184.44 | 56017.67 |

Runner logs report no request errors or HTTP failures. Per-run detailed raw
JSONL, logs, `/v1/loads?include=all` snapshots, server args/PID, query samples,
and 1-second `nvidia-smi dmon -s pucvmt` telemetry are preserved in the raw
directory below. The runner emitted a non-fatal Python `multiprocess` resource
tracker `RLock._recursion_count` exception during shutdown after successful
completion; it did not change rc or request results.

## Artifacts and hashes

Remote: `/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c8-python-20260908/measure/`

Local: [raw artifacts](./raw/g3-profile-c8-python-20260908/)

SHA-256 is recorded in `raw/g3-profile-c8-python-20260908/SHA256SUMS.txt`.
The three runner JSONL hashes are:

`repeat1 44759604dbcc23fd99fc761dd297757088593761e8ba927cbe19766fedcb38af`,
`repeat2 6644ab4d75f22b0d6b02d21383879f6678459b93e56f296d88d6d8df15c451ff`,
`repeat3 81aeaf95b0a28d32eb4c37b5d329eb4dbe0b2c473783e37125097e69a5d43330`.

## Final state

Candidate PID 497622 remained healthy on port 18037 after measurement for the
separately authorized restore task. No production service, product source,
model weights, or configuration was changed.

invocation_status: done
