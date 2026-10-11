# G3-PROFILE-C-C1-DECODE-RETRY2-20260908

ENTRY: ACCEPT

Invocation status: done

Executed on `175.155.64.171:22109`, loopback candidate `127.0.0.1:18035`, PID `478926`. Health was 200 and loads idle before execution; port 8035 was not touched. Candidate args included `--max-running-requests 4 --max-mamba-cache-size 20 --cuda-graph-max-bs-decode 4`.

Native command (repeated three times, warmup requests `3,0,0`):

```text
/data/sglang-qwen35-env/bin/python -m sglang.benchmark.serving --backend sglang --base-url http://127.0.0.1:18035 --model /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf --tokenizer /data/models/Qwen3.8-27B-GSQ-RCO-GGUF --dataset-name random-ids --tokenize-prompt --random-input-len 1024 --random-output-len 256 --random-range-ratio 1.0 --request-rate inf --seed 42 --max-concurrency 4 --num-prompts 32 --output-details --output-file <repeat>.jsonl --flush-cache --flush-cache-timeout 60 --warmup-requests <3|0>
```

Offline environment variables were set (`HF_HUB_OFFLINE=1`, `HF_DATASETS_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, proxies empty, `NO_PROXY=*`). No audit hooks or product edits were used. Runner version was `0.5.10.dev0`.

## Outcomes

All repeats completed RC 0 with 32/32 successful requests and no HTTP errors or timeout/zero-progress signal.

| repeat | duration s | output tok/s | total tok/s | median TTFT ms | median TPOT ms | median E2E ms | observed concurrency |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 241.21 | 33.96 | 169.81 | 4547.03 | 98.72 | 30173.43 | 3.99 |
| 2 | 241.65 | 33.90 | 169.50 | 4757.99 | 99.37 | 30199.79 | 3.99 |
| 3 | 241.60 | 33.91 | 169.54 | 4754.20 | 99.47 | 30205.26 | 3.99 |

Input was 32,768 tokens and requested output 8,192 per repeat. Runner reported peak concurrent requests 8 despite nominal C=4; this is preserved verbatim and requires independent reconciliation. Median aggregate output throughput is 33.91 tok/s. The recurring `multiprocess.resource_tracker` destructor traceback occurred after successful RC 0 and is preserved.

## Artifacts

Remote: `/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c1-decode-retry2-20260908/`

Local: `.memory/g3-baseline-20260907/work/raw/g3-profile-c1-decode-retry2-20260908/`

Artifacts include runner JSONL/logs, driver log, service PID/args, health, per-repeat `/v1/loads?include=all` snapshots, and `nvidia-smi dmon -s pucvmt` plus query telemetry. Local JSONL hashes:

```text
c172f6deddf06d66ac12b1d016d9bc8fb9efd5a1c0cf5aabbd7d074c8f5fc883  runner/repeat-1.jsonl
dc27ce7b102674b9d86d25da33ae80b886f7fc85ee5acf1ff43730a0b8b08899  runner/repeat-2.jsonl
9fc6804a3d2b23fd176821709411daded16deebfe1292678d1f76393b540cad8  runner/repeat-3.jsonl
```

Candidate was intentionally left running for separate restore.

## Followups and open issues

- Independent verification should reconcile reported peak concurrency 8 against loads and raw records.
- Restore PID 478926 via the separate restore task; this invocation did not stop or reconfigure it.
- Resource-tracker traceback is a preserved runner limitation, not a failed benchmark.

