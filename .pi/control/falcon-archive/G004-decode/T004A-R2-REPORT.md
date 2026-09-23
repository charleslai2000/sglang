# G004 / T004A-R2 — CUDA-Graph-Compatible Marlin Qualification

## Verdict

```text
T004A-R2: PASS
T004: READY TO RESUME
```

This was a qualification-only capture. Formal B=8/B=16 deep profiling was not
performed, and no optimization or production source change was made.

## Workload

A clean minimal qualification run used:

```text
client concurrency: 1
request count: 1
max_new_tokens: 8
input: short fixed prompt
completion: HTTP 200, response received
client errors: 0
```

The server used the frozen runtime configuration:

```text
Falcon-H1-7B-Instruct-GPTQ-Int4
GPTQ-Marlin
Mamba extra_buffer
prefill CUDA graph disabled
decode CUDA graph full
HiCache off/default
speculative decoding off
```

The serving process was launched through privileged NCU launch mode in the
isolated VM so that NCU could access counters. This was a qualification-only
process and not a production benchmark. No SGLang source, scheduler, Marlin,
CUDA graph policy, driver, or module configuration was changed.

## CUDA graph evidence

Startup log:

```text
Capture target decode CUDA graph begin. backend=full
... bs=[1, 2, 4, 8]
```

Runtime log during the request:

```text
Decode batch, #running-req: 8, ... cuda graph: True, #queue-req: 0
```

The NCU-qualified serving run therefore retained decode CUDA graph execution;
there was no profiler-induced eager fallback observed.

## Target kernel and filter

Exact captured kernel:

```text
void Marlin<__nv_bfloat16, 1125899907892224, 256, 1, 8, 8, 1, 4, 8, 0>(
  const int4 *, const int4 *, int4 *, int4 *, const int4 *,
  const unsigned short *, const int4 *, const int *, int, int, int,
  int, int, int *, bool, bool, int)
```

The filter was:

```text
--target-processes all
--kernel-name-base demangled
--kernel-name 'regex:.*sglang::device::marlin::Marlin.*'
--launch-count 1
--set basic
```

NCU matched and captured the target with:

```text
Grid: 82 x 1 x 1
Block: 256 x 1 x 1
Device: CC 8.6
Context: 1
Stream: 25
```

Capture count is one report entry for the selected Marlin launch.

## NCU report

```text
path: control/G004-falcon-h1-decode-saturation/runs/t004a-r2/marlin-qual.ncu-rep
size: 14,123,377 bytes (~13.5 MiB)
```

NCU completed the basic collection and the imported report contains numeric
metrics. Representative values:

```text
Duration:                  55.78 us
Memory Throughput:         81.88%
DRAM Throughput:           81.88%
Compute (SM) Throughput:   29.16%
L1/TEX Cache Throughput:   23.35%
L2 Cache Throughput:       35.29%
Block Size:                256
Grid Size:                 82
Registers per Thread:      96
Dynamic Shared Memory:     101.38 Kbyte/block
Theoretical Occupancy:     16.67%
Achieved Occupancy:        16.66%
```

These values are qualification evidence only. They are not the formal T004
B=8/B=16 attribution result.

## Runtime status

```text
request completed: yes
HTTP status: 200
client errors: 0
CUDA/runtime errors: none observed in successful run
scheduler crash/deadlock: none observed
CUDA graph fallback: not observed
```

Earlier exploratory launch attempts were cleaned up. A stale previous NCU
process caused one intermediate OOM during an attempted second launch; that
attempt generated no report and was not used as qualification evidence. The
clean run above was performed after GPU/process cleanup and completed normally.

## Production changes

```text
NONE
```

No production tree, model, scheduler, Marlin kernel, CUDA graph policy, driver,
module parameter, symlink, or persistent permission configuration was changed.
No formal benchmark was run.

## T004 status

```text
T004A-R2: PASS
T004: READY TO RESUME
```

Formal T004 may now proceed as a separate authorized task using the proven
privileged NCU launch arrangement, with B=8 and B=16 and the exact Marlin target.
Stop here; this qualification did not execute formal T004.
