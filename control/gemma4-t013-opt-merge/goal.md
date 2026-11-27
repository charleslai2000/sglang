# gemma4-t013-opt-merge — goal

Merge-accept the GPU optimisations that were already qualified separately, on the T012
close-out source (`7ed79dab11`), instead of developing anything new:

* restore T011's accepted FA2 Forward-level plan reuse as an **independent opt-in**,
  unchanged algorithm, default off;
* keep T012's Humming post-load opt-in (`SGLANG_CTWNA16_HUMMING`);
* measure the two combinations — **A** Humming + Triton, **B** Humming + FA2 — on the
  original C-8 L1-only load, the production three-tier HiCache stack, and the T010
  long-context load, with the model, request load, KV capacity and cache configuration
  fixed;
* confirm peak memory, decode CUDA Graph, numerical correctness and real L3 restore
  correctness, reusing the T009/T010/T011/T012 evidence and filling only the gaps the
  merge creates;
* retain the combination(s) that are stable and effective, keep production defaults
  conservative, and record the decision.

Out of scope: new algorithms, new telemetry frameworks, new scheduling mechanisms, any
change to decode, SWA, KV capacity, cache policy, checkpoint or quantization maths.
