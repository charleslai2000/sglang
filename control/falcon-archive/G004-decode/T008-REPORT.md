# G004 / T008 — Marlin Template / Register / Work-Mapping Investigation

## Verdict

```text
T008: PASS
B=16 RESOURCE INCREASE: TEMPLATE/WORK-MAPPING DEPENDENT
EXISTING LEGAL ALTERNATIVE SPECIALIZATION: YES, but not selected by current dispatch
```

No code, dispatch, kernel, serving configuration, CUDA graph policy, benchmark,
or NCU run was changed or executed.

## 1. Exact dispatch reason

The selection occurs in `gptq_marlin.cuh` inside `marlin_mm`:

```cpp
int rest_m = prob_m;
int max_thread_m_blocks = 4;
while (rest_m) {
  ...
  int prob_m_split = ... ? ... : rest_m;
  int thread_m_blocks = min(div_ceil(prob_m_split, 16), max_thread_m_blocks);
  int m_block_size_8 = prob_m_split <= 8;
  ...
  get_marlin_kernel(..., thread_m_blocks, ..., m_block_size_8, ...)
}
```

For the reproduced exact shapes:

```text
B=8:
  prob_m = 8
  prob_m_split = 8
  thread_m_blocks = 1
  m_block_size_8 = true

B=16:
  prob_m = 16
  prob_m_split = 16
  thread_m_blocks = 1
  m_block_size_8 = false
```

The rest of the major dispatch parameters remain unchanged:

```text
threads = 256
thread_m_blocks = 1
thread_n_blocks = 8
thread_k_blocks = 8
pipe_stages = 4
group_blocks = 8
is_zp_float = false
```

The template identity therefore differs only in the `m_block_size_8` boolean:

```text
B=8:
Marlin<..., 256, 1, 8, 8, true, 4, 8, false>

B=16:
Marlin<..., 256, 1, 8, 8, false, 4, 8, false>
```

## 2. Concrete code differences caused by `m_block_size_8`

The flag changes actual mathematical work mapping and storage behavior; it is
not merely a naming distinction.

### Effective M tile and parallel mapping

In `marlin_template.h`:

```cpp
constexpr int m_block_size = m_block_size_8 ? 8 : (16 * thread_m_blocks);
```

Thus:

```text
B=8:  m_block_size = 8
B=16: m_block_size = 16
```

The `prob_m > m_block_size` path and subsequent slice/parallel mapping operate
on these different effective M tile sizes.

### A shared-memory read and fragment shape

The shared A read layout changes:

```cpp
a_sh_rd = ... (16 / (m_block_size_8 ? 2 : 1)) ...
```

The register load changes from two to four matrix rows/fragments:

```cpp
ldsm<m_block_size_8 ? 2 : 4, scalar_t>(...)
```

### Tensor-core MMA path

The core accumulation path changes:

```cpp
if constexpr (m_block_size_8) {
  mma_trans(frag_a, frag_b0, frag_b1, frag_c);
} else {
  mma(frag_a, frag_b0, frag_c);
  mma(frag_a, frag_b1, frag_c);
}
```

The B=8 path uses the transposed two-fragment form; the B=16 path uses two
separate MMA operations and retains two result fragments. This directly changes
instruction mix and accumulator/register footprint.

### Reduction and accumulator layout

The reduction loops use different strides:

```cpp
for (...; j < 4 * 2; j += (m_block_size_8 ? 2 : 1))
```

The B=8 path processes fewer output fragments per iteration; B=16 processes
both halves. The output/reduction path also has separate `m_block_size_8`
addressing and masking branches.

### Global output staging and stores

The store path changes its output index calculation:

```cpp
if constexpr (m_block_size_8) {
  c_gl_wr = ... ((threadIdx.x % 4) * 2) ...;
} else {
  c_gl_wr = ... ((threadIdx.x % 32) / 4) ...;
}
```

The temporary shared reduction writes also differ:

```cpp
B=8:  writes scalar components into two separated shared locations
B=16: writes a scalar pair as one scalar_t2
```

The final global-store loop count changes from two iterations for the M=8 path
to `thread_m_blocks * 4` iterations for the non-M=8 path.

### Scale/dequant and masks

The scale fragment handling has a B=8-specific path, while B=16 performs the
additional second accumulator scaling operations. Output masking and temporary
reduce load/store loops also branch on the flag.

These are concrete work-mapping, fragment, instruction, accumulator, and store
changes. They explain why the two template variants have different register
allocation; the source does not provide a single isolated register-only switch.

## 3. Explaining 96 → 148 registers/thread

T004 observed:

```text
B=8:  96 registers/thread
B=16: 148 registers/thread
```

The source supports a strategy-dependent explanation:

```text
B=8:
  m_block_size = 8
  ldsm.x2-style A fragments
  mma_trans path
  fewer accumulator/reduction fragments
  B=8-specific store/reduction loops

B=16:
  m_block_size = 16
  ldsm.x4-style A fragments
  two separate MMA accumulations
  larger fragment/accumulator live state
  B=16-specific reduction/store loops
```

The extra live fragment and accumulator state, together with the separate B=16
unrolled paths, is the concrete source-level reason for the register increase.
A ptxas/SASS register-lifetime dump was not required to establish this causal
path and was not run; the authoritative observed allocation remains T004 NCU.

## 4. Relationship to T004 behavior

T004 observed:

```text
B=8:
  duration: 34.11–56.35 us
  SM throughput: 25.74–29.15%
  DRAM: 70.25–81.45%
  eligible warps/cycle: ~0.39
  math-pipe throttle: ~1.21
  long scoreboard: ~1.26

B=16:
  duration: 39.55–69.86 us
  SM throughput: 27.13–30.51%
  DRAM: 61.52–66.88%
  eligible warps/cycle: ~0.30
  math-pipe throttle: ~3.63
  long scoreboard: ~0.49
```

The evidence is consistent with the B=16 specialization carrying more live
accumulator/fragment state:

```text
more registers/thread
same low occupancy ceiling
fewer eligible warps
higher math-pipe throttle
long-scoreboard pressure lower than B=8, not higher
```

This is not proof that register pressure alone causes the entire B=16 duration
increase. The specialization simultaneously changes MMA grouping, A-fragment
loads, reductions, stores, and M work mapping. The supported classification is
therefore:

```text
B=16 RESOURCE INCREASE: TEMPLATE/WORK-MAPPING DEPENDENT
```

## 5. Existing legal alternative

```text
YES — the existing `m_block_size_8=true` specialization exists for the same
major N/K/thread configuration.
```

The dispatch macro family explicitly instantiates both variants for
`thread_m_blocks=1`, including the same `(thread_n_blocks, thread_k_blocks,
threads) = (8, 8, 256)` family.

However, current dispatch derives `m_block_size_8=false` for `prob_m=16`. Using
the B=8 specialization for B=16 would require a dispatch/work-mapping change;
it is not an accidental or already-selected alternative.

A clean next candidate is therefore:

```text
Candidate: force/route the existing m_block_size_8=true specialization for
representative B=16 M=16 through its existing parallel/work mapping, while
keeping K=3072, N=12288, BF16, GPTQ uint4b8, group size 128, and all serving
behavior out of scope.
```

This is not executed here. It must first be validated for its M=16 mapping and
output correctness; the candidate cannot simply reinterpret an M=16 input as
M=8 without preserving all rows.

Expected differences before execution:

```text
registers/thread: likely closer to B=8's 96 than B=16's 148
M tile/work mapping: changes from m_block_size=16 to m_block_size=8
M parallelism: may become two M=8 work units
occupancy: potentially higher only if register/live-state reduction is realized
DRAM: may increase because of duplicated/repartitioned staging or stores
math-pipe: may decrease per kernel if accumulator pressure falls
correctness risk: high until exact M=16 output mapping is proven
```

The existing alternate `(thread_k, thread_n, threads)` configurations also exist
in the source, but selecting them changes tile decomposition and is a broader
work-mapping experiment. They are not preferred over the isolated
`m_block_size_8` candidate.

## 6. Classification and next step

```text
B=16 RESOURCE INCREASE: TEMPLATE/WORK-MAPPING DEPENDENT
EXISTING LEGAL ALTERNATIVE: YES
```

The source shows that `m_block_size_8` changes multiple tightly coupled paths;
it is not a clean register-only axis. Nevertheless, it is the smallest existing
specialization difference directly tied to the observed 96→148 register change
and is the most focused next isolated A/B candidate.

No candidate was forced, compiled, profiled, or benchmarked in T008.
