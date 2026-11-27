# T011 Full Attention Extend FA2 qualification

Date: 2026-11-27. Decision: **STOP — requested FA2 path is unsupported for this production dtype/geometry on the target GPU. No production integration.** The earlier applicability STOP was wrong: it used the unconverted source config instead of this Fork's runtime config. That ruling is revoked. Corrected runtime geometry was established, and the bounded operator qualification reached FlashInfer's architecture gate but could not compile the requested FP8 E5M2, head_dim=512 FA2 paged-prefix module for RTX 3090 SM86. This is a concrete blocker for the specified candidate, not a head-dimension applicability issue.

## Frozen identity and production geometry

- Baseline: `c102ccbc5cfd17b510f896b23107204daf5ed0d7`; production source: `a76206a5fbd65b81ddbb470ac8088a46cf78697a` (`a76206a5fb`). T011 control work is on top of the frozen source; no production changes were made.
- Current Fork config conversion preserves base `head_dim=256` as `swa_head_dim` and maps Gemma4 `global_head_dim=512` to runtime `head_dim=512`. Parsed model geometry: Full Q/KV heads 8/2, SWA head_dim=256; Full IDs `[5, 11, 17, 23, 29, 35, 41]`.
- Independent checkpoint tensor dimensions agree: Full layer 5 Q/K/V projection rows 4096/1024/1024 and q/k norms 512; SWA layer 4 rows 2048/512/512 and norms 256. The requested Full 512 geometry is applicable. The prior report's claim that it was absent is invalid and superseded.
- The existing T010 Nsight SQLite row `(1,8,128)` does not encode layer identity/type or context lengths, so it cannot be attributed to Full vs SWA. With current Full dimension 512, the frozen SM86 tile selection is `BLOCK_M/N=32/32`; structurally that grid corresponds to 4096 Q rows, not the earlier report's 8192. This geometry alone still does not establish which layer/phase emitted the row. No full recapture was performed.

## Isolated qualification and decisive failure

Durable artifacts: `runs/20261127T-fa2-op-r1/intent.txt`, `launch-manifest.txt`, `driver.log`, and `t011_fa2_operator.py`. The bounded driver was run under `/tmp/f1-r16b-gpu-exclusive.lock` with `PYTHONPATH=$PWD/python`, timeout 240s, on the RTX 3090 (SM86), FlashInfer 0.6.17, torch 2.13.0+cu129. It tested the first required shape setup `(new,prefix)=(1024,7168)`, actual GQA 8/2, BF16 Q/new K/V and FP8 E5M2 prefix KV, page size 1, with FP32 scaling and causal ragged extend. The failure occurs in `paged.plan()` before any timing or result; the three shapes were not measured.

Exact exception:

```text
RuntimeError: No supported CUDA architectures found for major versions [10, 11, 12]
```

Installed FlashInfer source `/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages/flashinfer/jit/attention/modules.py` shows `_fa2_head_dim_nvcc_flags`: when QK or VO dimension exceeds 256 and KV dtype is one byte, it requests supported major versions `[10,11,12]`, except the separately opted-in NVFP4 case. The requested E5M2 KV is not NVFP4; the SM86 device therefore has no supported architecture for this FA2 module. The 16-bit large-head path's SM80+ architecture set does not apply without changing the user's fixed FP8 KV format. The exception is retained verbatim in `driver.log`.

The GPU was checked after process exit: 1 MiB used, 0% utilization; project lock was free. No persistent GPU workload remains.

## Outcome and scope

- No FA2-vs-Triton timing for any of the three shapes; no measured operator speedup, memory overhead, or end-to-end effect is available.
- No production source was modified. No speculative override of FlashInfer's architecture gate, alternate attention algorithm, quantization change, synthetic 16-bit substitute, oracle comparison, C-8 acceptance, or three-tier restore was attempted. Such a substitute would violate the fixed candidate or fail to qualify production behavior.
- Candidate is stopped at the explicit unsupported condition. Further progress requires a material scope change (e.g. supported hardware/library path or altered KV representation), none of which is authorized by this task. Frozen production source remains `a76206a5fb`.
