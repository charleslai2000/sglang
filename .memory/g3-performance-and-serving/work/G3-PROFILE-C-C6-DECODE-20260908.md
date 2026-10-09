# G3-PROFILE-C-C6-DECODE-20260908

ENTRY: ACCEPT

## Status

done

## Scope and target

- Host: `175.155.64.171:22109` only.
- Candidate: PID `488839`, loopback `127.0.0.1:18036`.
- Effective profile: `max-running-requests=6`, `max-mamba-cache-size=32`, `cuda-graph-max-bs-decode=8`.
- Candidate remained running for the separately assigned restore step.
- No product files, service configuration, audit hooks, or external datasets were changed or used.

## Exact workload

Native command used for each repeat:

```text
/data/sglang-qwen35-env/bin/python -m sglang.benchmark.serving --backend sglang --base-url http://127.0.0.1:18036 --model /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf --tokenizer /data/models/Qwen3.8-27B-GSQ-RCO-GGUF --dataset-name random-ids --tokenize-prompt --random-input-len 1024 --random-output-len 256 --random-range-ratio 1.0 --request-rate inf --seed 42 --max-concurrency 6 --num-prompts 48 --output-details --output-file <repeat>/runner.jsonl --flush-cache --flush-cache-timeout 60 --warmup-requests 0
```

Three repeats completed with return code 0. Each repeat flushed cache immediately before measurement. No warmup requests were added; C1 had already established the initial warmup for this matrix.

## Results

| Repeat | Successful | Input tokens | Generated tokens | Aggregate output tok/s | Total tok/s | Median TTFT ms | Median TPOT ms | Median E2E ms | Concurrency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 48 | 49152 | 12288 | 35.04 | 175.20 | 6127.48 | 148.15 | 43901.00 | 5.99 |
| 2 | 48 | 49152 | 12288 | 34.93 | 174.66 | 6121.96 | 148.40 | 43965.60 | 5.99 |
| 3 | 48 | 49152 | 12288 | 34.96 | 174.80 | 6123.76 | 148.38 | 43960.46 | 5.99 |

All 144 requests completed successfully; no runner HTTP errors or timeout failures were recorded. Runner-reported peak concurrent requests was 12 (the request scheduler's observed peak field); effective average concurrency was 5.99.

Other available percentile fields are preserved verbatim in each raw stdout: E2E P90/P95/P99, TTFT P90/P95/P99, TPOT P90/P95/P99, ITL, and input/output throughput.

## Evidence

Remote artifact directory:

`/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c6-equals-20260908/measure/`

Local copy:

`.memory/g3-baseline-20260907/work/raw/g3-profile-c6-equals-20260908/`

The local raw copy contains launch metadata, process arguments, health/loads snapshots, runner help/version, per-repeat JSONL, stdout/stderr, per-repeat loads before/after, and 1-second `nvidia-smi dmon -s pucvmt` captures. JSONL SHA-256:

```text
repeat1 72159d670406555e948905f191e28f988ed39a6cd30e9c8d23f7b9e4c1a33bc8
repeat2 af772f099016305bd23014ce9e2d4e81b64e6af80ee7d136b360608b294ff686
repeat3 b3883c5bba1eccde38d85bc86cda01eb56bdf3630eaeb66dea5e9d38c8701ce5
```

## Open issues / follow-up

- Candidate restore is intentionally separate and remains outstanding to the restore owner.
- The runner emits a Python `resource_tracker` RLock AttributeError during shutdown in stderr after successful measurements; return codes are 0 and the request results are complete. This is preserved as raw evidence, not treated as a workload failure.
- This report does not claim C6 is the final optimum; compare against C1/C4/C8 after their independent measured evidence is available.

Invocation final status: done
