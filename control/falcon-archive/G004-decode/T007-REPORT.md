# G004 / T007 — Marlin Shared-Memory / Tile-Staging Controlled A/B

## Verdict

```text
T007: BLOCKED
SHARED-MEMORY PATH: NOT YET RESOLVED
```

No valid experimental variant reached correctness or performance profiling. No
optimization was integrated, no serving benchmark was run, and no production
execution semantics were changed.

## Source mapping before intervention

The production Marlin template allocates one dynamic shared-memory object:

```cpp
extern __shared__ int4 sh[];
```

The major regions are laid out as:

```text
sh_b       : B weight staging pipeline
sh_g_idx   : act-order group-index staging
sh_zp      : zero-point staging, when applicable
sh_s       : scale staging / act-order scale region
sh_a       : activation staging
sh_red     : reduction/output staging, overlaid with sh_b when possible
```

Relevant source facts:

```text
pipe_stages = 4
sh_b_size = stages * b_sh_stage
g_idx region = stages * g_idx_stage
sh_s_size = act_s_max_num_groups * s_sh_stride for act-order
sh_a follows the scale region
shared reduction is overlaid with the larger B staging region
```

The pipeline is coupled to asynchronous fetch and synchronization:

```text
cp.async commit/fetch pipeline
cp.async_wait<stages - 2>()
__syncthreads()
```

The current ~101.38 KiB allocation is therefore not a single disposable buffer;
it is a coupled B/A/scale/group-index staging layout plus reduction overlay,
with lifetimes and synchronization tied to the compile-time stage count.

## Controlled intervention attempted

The smallest single-axis intervention selected was:

```diff
- static constexpr int pipe_stages = 4;
+ static constexpr int pipe_stages = 3;
```

No tile dimensions, dispatch selection, register strategy, work mapping,
quantization layout, or external interface was changed.

## Result

The existing source contains a compile-time safety assertion in
`marlin_template.h`:

```cpp
static_assert(
    thread_m_blocks * 16 * thread_n_blocks * 16 / 8 <= stages * b_sh_stage);
```

With `stages=3`, the JIT compilation failed for multiple instantiated Marlin
configurations, including the B=8/B=16-relevant template family. The compiler
reported 22 static-assert failures. Representative failure:

```text
marlin_template.h(648): error: static assertion failed
```

The failure occurred before kernel execution. Consequently:

```text
correctness: not run for experimental variant
NCU metrics: not collected for experimental variant
kernel duration comparison: unavailable
occupancy comparison: unavailable
```

This is a source-level feasibility failure, not a negative performance result.
It establishes that a global stage-count reduction is not a valid one-variable
change across the compiled template family.

## Restoration and integrity

The source was immediately restored:

```text
pipe_stages = 4
```

No other source file was changed. No serving process was started. No production
configuration or kernel behavior remains modified by T007.

## Baseline control retained

T006 remains the valid control:

```text
B=8:
  exact production Marlin variant reproduced
  relative mean absolute error: 1.90e-6
  NCU report valid

B=16:
  exact production Marlin variant reproduced
  relative mean absolute error: 2.07e-6
  NCU report valid
```

## Conclusion

```text
SHARED-MEMORY PATH: NOT YET RESOLVED
```

The source mapping confirms shared-memory staging is coupled to compile-time
pipeline and reduction constraints, but the first minimal stage-count
intervention is rejected by the existing static assertion. No evidence supports
claiming benefit, neutrality, or regression.

Candidate #2 remains frozen. A future task would need to define a more narrowly
scoped shared-memory experiment that preserves the assertion and all stage
lifetime/synchronization invariants, or explicitly authorize moving to the
B-dependent template/register/work-mapping candidate. T007 does not choose that
next task.
