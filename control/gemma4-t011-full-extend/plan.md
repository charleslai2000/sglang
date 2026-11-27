# T011 Full Attention Extend plan

Status: DONE — corrected geometry is applicable, but the fixed FA2 FP8 E5M2 large-head path is unsupported on RTX 3090 SM86.

## Established result
Frozen production baseline remains `c102ccbc5cfd17b510f896b23107204daf5ed0d7`, source `a76206a5fb`. Current Fork parser in `python/sglang/srt/utils/hf_transformers/config.py` preserves the base config's `head_dim=256` as `swa_head_dim`, then maps `global_head_dim=512` to runtime `head_dim`; it likewise handles global KV heads when provided. Checkpoint weight shapes independently confirm Full layer 5 q/k/v rows 4096/1024/1024, q/k norm 512; SWA layer 4 rows 2048/512/512 and norm 256. This implies Full head_dim=512, Q/KV heads 8/2 and SWA head_dim=256. The prior report's applicability STOP is revoked and being amended.

## Result
The corrected production geometry is Full head_dim=512 / GQA 8/2 and SWA head_dim=256; the prior geometry-mismatch STOP is superseded. The requested FA2 qualification reached `paged.plan()` and failed before any timing: FlashInfer 0.6.17 selects only CUDA major architectures 10/11/12 for one-byte KV with head_dim>256, while the target RTX 3090 is SM86. Exact exception and source evidence are recorded in `runs/T011-FULL-EXTEND-FA2-QUALIFICATION.md`. Thus all three required comparisons, accuracy, memory, and end-to-end effects are unmeasured; no production edit was made. The specified candidate is stopped as unsupported. Resumption requires a material change to supported hardware/library or KV representation, outside this fixed scope.
