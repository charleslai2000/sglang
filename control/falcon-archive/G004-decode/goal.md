# G004 — Falcon-H1 decode saturation profiling

## Goal
Explain Falcon-H1 GPTQ-Marlin decode throughput saturation on one RTX 3090 near B=12–16 / approximately 480–500 aggregate output tok/s, and identify the next 1–2 most valuable profiling-backed optimization hypotheses without changing execution behavior.

## Frozen baseline
- Model: `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`
- GPU: RTX 3090 24GB
- GPTQ-Marlin; Mamba BF16; Mamba radix `extra_buffer`
- CUDA graph: prefill disabled, decode full
- HiCache OFF
- speculative decoding OFF
- context 8192

## Scope
- Re-establish decode-heavy B=1/2/4/8/12/16 baseline with fixed prompts, seed, one warmup, and three measured reps; optionally retain B=20/24.
- Distinguish client concurrency from actual scheduler decode batch size.
- Capture actual decode-batch distribution and steady-window GPU utilization, memory/DRAM utilization, power, clocks, and VRAM where available.
- Attribute B=8/12/16 with kernel/runtime and scheduler/CPU-gap evidence, using profiler runs only for attribution and not as benchmark TPS.

## Exclusions
- No optimization patch, scheduler tuning, kernel rewrite, Mamba strategy change, 3-slot Mamba, skip-decode-lock, extra_buffer_lazy, KV FP8, speculative decoding, HiCache benchmark, or 32K validation.
- Allowed source changes are only default-off, marker-gated, read-only counters/traces/histograms.
- Benchmark and profiling artifacts remain under this Goal's control directory.

## Completion
A report gives B=1/2/4/8/12/16 three-rep means, actual decode-batch distributions, B=8/12/16 attribution data, a supported bottleneck classification or `ROOT CAUSE NOT YET RESOLVED`, and 1–2 next candidate validations. Then stop.
