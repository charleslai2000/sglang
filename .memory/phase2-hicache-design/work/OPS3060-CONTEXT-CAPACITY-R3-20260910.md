# OPS3060-CONTEXT-CAPACITY-R3-20260910

## Profile and method

- RTX 3060 12 GB, one GPU; Qwen3.5-4B AWQ W4A16/Marlin.
- FP8 E4M3 KV, CUDA Graph decode/prefill enabled, chunked prefill 2048.
- HiCache enabled with file backend and write-through semantics.
- RH OFF for the capacity measurements (the `--enable-ready-horizon` flag was
  omitted); service was restored to RH-ON c1 afterward.
- File HiCache was explicitly redirected to `/hy-tmp/hicache-context-r3`.
  The default `/tmp/hicache` is on the 30G root overlay and is not safe for
  long-context experiments.
- Each point booted a fresh server and sent an exact pre-tokenized `input_ids`
  prompt with one generated token.

## Results

| Requested capacity | Actual `max_total_num_tokens` | Prompt tokens | Boot/graph | HTTP | Request wall | Outcome |
|---:|---:|---:|---|---:|---:|---|
| 64K | 65,536 | 64,000 | PASS | 200 | 36.79 s | completed |
| 128K | 131,072 | 128,000 | PASS | 200 | 105.49 s | completed |
| 192K | 193,294 | 192,000 | PASS | 200 | 205.27 s | completed |
| 256K | 193,294 | 256,000 | PASS | 400 | 0.17 s | rejected by max input length |

For the first three points, response metadata reported the exact requested
prompt length and one completion token. No OOM, fatal runtime error, or storage
write failure occurred after moving the file backend to `/hy-tmp`.

The 256K boot did not allocate 256K device tokens: the 3060 profile reached an
allocator ceiling of 193,294 tokens with approximately 1.67 GB available GPU
memory after model load. The server explicitly rejected the 256,000-token input
as exceeding the 193,288-token maximum allowed length. This is an admission
limit, not an OOM result.

## Boot evidence

- 64K: `available_gpu_mem=3.61 GB`, graph capture passed, startup tokenizer time
  42.11s.
- 128K: `available_gpu_mem=2.61 GB`, graph capture passed, tokenizer time 43.92s.
- 192K/256K: `available_gpu_mem=1.67 GB`, graph capture passed, tokenizer time
  45.30s/45.06s respectively.
- After restore, service health was HTTP 200, idle GPU sample was 8513 MiB used
  and 3525 MiB free; root disk was 55% used and `/hy-tmp` 77% used.

## Capacity interpretation

- Single-session tested context: 192K is the largest verified successful point
  in this run.
- 256K is not usable under the fixed 0.82 static-memory profile because the
  production allocator admits only about 193K tokens.
- The largest verified device-token pool is therefore approximately 193K
  nominal tokens, but the production-safe active capacity is not yet declared:
  concurrency pressure and durable restore still need separate tests.
- Long-context latency rises materially with exact cold prefill: 36.8s at 64K,
  105.5s at 128K, and 205.3s at 192K. These are cold full-prefill numbers, not
  warm-cache TTFT.

## Operational incident and containment

An initial invalid launch used an unsupported `--disable-ready-horizon` flag;
those four attempted boots are excluded from results. A subsequent long request
also exposed that the default file backend writes to `/tmp/hicache`; the exact
temporary cache directory was cleared after stopping the test request. No
Neuron process was touched. The service was restored with the data-disk storage
path and RH ON c1, health HTTP 200.

