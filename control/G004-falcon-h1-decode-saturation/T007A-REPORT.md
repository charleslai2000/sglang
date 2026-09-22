# G004 / T007A — Marlin Shared-Memory Feasibility Audit

## 1. Verdict

```text
T007A: PASS
```

This is a source and numerical feasibility audit only. No experimental variant
was compiled, no NCU was run, no serving process was started, and no production
code was modified.

Final decision:

```text
SHARED-MEMORY PATH NOT CLEANLY SEPARABLE — move to Candidate #2
```

## 2. Exact production template parameters

From the T004 symbols and the Marlin source template ordering:

```text
B=8:
  threads       = 256
  thread_m_blocks = 1
  thread_n_blocks = 8
  thread_k_blocks = 8
  m_block_size_8  = true
  stages          = 4
  group_blocks    = 8
  is_zp_float     = false

B=16:
  threads       = 256
  thread_m_blocks = 1
  thread_n_blocks = 8
  thread_k_blocks = 8
  m_block_size_8  = false
  stages          = 4
  group_blocks    = 8
  is_zp_float     = false
```

Exact symbols:

```text
B=8:
Marlin<__nv_bfloat16, 1125899907892224, 256, 1, 8, 8, 1, 4, 8, 0>(...)

B=16:
Marlin<__nv_bfloat16, 1125899907892224, 256, 1, 8, 8, 0, 4, 8, 0>(...)
```

For GPTQ `group_size=128`, the source derives:

```text
group_blocks = group_size / 16 = 8
```

The act-order input is sorted/reordered before the final full-K Marlin path;
the selected final kernel symbols use the `group_blocks=8` specialization.

## 3. Compile-time assertion evaluation

The relevant source invariant is:

```cpp
static_assert(
    thread_m_blocks * 16 * thread_n_blocks * 16 / 8 <= stages * b_sh_stage);
```

For both exact T006 shapes:

```text
LHS = 1 * 16 * 8 * 16 / 8
    = 256 int4 units
```

The B staging terms are:

```text
pack_factor       = 32 / 4 = 8
b_sh_stride       = ((thread_n_blocks * 16) * 16 / pack_factor) / 4
                   = ((8 * 16) * 16 / 8) / 4
                   = 64 int4 units
```

Correction: the source expression uses `b_thread_vecs`/packed layout in the
staging stride; for the exact `uint4b8` path the compiled source arithmetic is:

```text
b_sh_stride       = ((8 * 16) * 16 / 8) / 4 = 64 int4 units
b_sh_stage        = b_sh_stride * thread_k_blocks
                   = 64 * 8
                   = 512 int4 units
```

Therefore:

```text
stages=4 RHS = 4 * 512 = 2048 int4 units
stages=3 RHS = 3 * 512 = 1536 int4 units
```

Both exact B=8 and B=16 variants satisfy the assertion under either stages=4
or stages=3:

```text
256 <= 2048  PASS, stages=4
256 <= 1536  PASS, stages=3
```

The failed global `pipe_stages=3` build was not rejected by the B=8/B=16
assertion. It failed because the source eagerly instantiates the complete
Marlin dispatch family. Other compiled combinations, including larger
`thread_m_blocks`/`thread_n_blocks` configurations, violate the same invariant
when stages=3. The compiler reported 22 such instantiation failures.

Thus:

```text
production exact shapes: legal at stages=4 and mathematically legal at 3
whole existing dispatch family: not legal at global stages=3
```

## 4. Shared-memory footprint breakdown

The template lays out:

```text
sh_b       = sh
sh_red     = sh
sh_g_idx   = sh_b + max(sh_red_size, sh_b_size)
sh_zp      = sh_g_idx + stages * g_idx_stage
sh_s       = sh_zp + stages * zp_sh_stage
sh_a       = sh_s + sh_s_size
```

For the exact final `group_blocks=8`, `is_zp_float=false`, no-zp GPTQ path:

```text
sh_red_size = (2 * thread_n_blocks + 1) * 16 * thread_m_blocks
            = (2 * 8 + 1) * 16 * 1
            = 272 int4 units

b_sh_stride = 64 int4 units
b_sh_stage  = 64 * 8 = 512 int4 units
sh_b_size   = stages * b_sh_stage = 4 * 512 = 2048 int4 units

max(sh_red_size, sh_b_size) = 2048 int4 units

g_idx_stage = 0 because the final specialization has group_blocks != 0
zp_sh_stage = 0 because this GPTQ path has no zero points

s_sh_stride = 16 * thread_n_blocks / 8 = 16 int4 units
s_tb_groups = 1 because group_blocks < thread_k_blocks is false (8 < 8)
s_sh_stage  = 16 int4 units
sh_s_size   = stages * s_sh_stage = 64 int4 units

a_sh_stride = 16 * thread_k_blocks / 8 = 16 int4 units
```

Actual template-addressed storage estimate:

```text
B=8:
  max(reduction, B pipeline) = 2048 int4
  scale region               =   64 int4
  activation region          =  128 int4  (16 * m_block_size=8)
  total                     = 2240 int4
  bytes                     = 2240 * 16 = 35,840 bytes

B=16:
  max(reduction, B pipeline) = 2048 int4
  scale region               =   64 int4
  activation region          =  256 int4  (16 * m_block_size=16)
  total                     = 2368 int4
  bytes                     = 2368 * 16 = 37,888 bytes
```

Important distinction:

```text
T004 LaunchStats dynamic shared memory: 101.38 KiB/block
```

That value is the `max_shared_mem_new` launch argument. In `marlin_mm`, the
launch uses:

```cpp
host::LaunchKernel(blocks, num_threads, stream, max_shared_mem_new)(...)
```

and `max_shared_mem_new` is initialized from the device opt-in maximum
(`cudaDevAttrMaxSharedMemoryPerBlockOptin`), which is 101,376 bytes when
`blocks_per_sm == 1`. It is therefore a requested dynamic allocation ceiling,
not a direct measurement of the bytes addressed by the template's `sh_*`
regions. The source's actual addressed storage expression is much smaller than
the LaunchStats reservation.

This distinction invalidates the premise that simply reducing a compile-time
stage count automatically reduces the observed 101.38 KiB LaunchStats value.
A separate launch-allocation change would be needed, and that would be an
additional experimental axis.

## 5. Relevant constraints

The audit found these coupled constraints:

```text
- pipe_stages is a global compile-time constant in marlin.cuh.
- stages controls sh_b pipeline sizing and cp.async wait-group semantics.
- stages also sizes g_idx/zp/scale pipeline regions for applicable variants.
- cp.async_wait<stages-2>() requires a valid stage protocol.
- the static assertion must hold for every eagerly instantiated dispatch.
- the existing dispatch macros cover many M/N/K/template combinations.
- max_shared_mem_new is passed as the launch dynamic shared-memory size.
- changing that launch size separately affects the runtime allocation contract.
```

## 6. Legal candidate audit

### Candidate A — global stages=3

```text
Expected actual stage storage: lower for affected pipeline regions
Expected occupancy: potentially higher only if launch allocation is also reduced
Register pressure: not guaranteed to change
Template identity: changes globally
Work mapping: stage protocol changes
Compile status: INVALID for the complete eagerly instantiated dispatch family
Clean Candidate #1: NO
```

The exact B=8/B=16 assertion passes numerically at stages=3, but the complete
source does not compile. It cannot be used without narrowing dispatch
instantiation or adding per-specialization stage support, which is no longer a
single shared-memory-only change.

### Candidate B — existing alternate tile/template combination

The source already contains alternate configurations such as:

```text
thread_n_blocks/thread_k_blocks = (8,8), (8,4), (4,8), (16,4)
threads = 256 or 128
thread_m_blocks = 1..4
```

However, choosing one changes the Marlin template/work mapping and normally
register usage, grid/tile decomposition, and possibly reduction behavior. It is
not a clean shared-memory-only experiment. It is effectively Candidate #2
(B-dependent template/register/work mapping).

```text
Expected shared memory: shape-dependent; must be computed per alternate
Expected occupancy: may change
Registers: likely change
Template/work mapping: definitely changes
Clean Candidate #1: NO
```

### Candidate C — reduce launch dynamic allocation only

The source passes `max_shared_mem_new` to the kernel launch. Reducing that value
without changing the template buffer expression could lower the requested
LaunchStats reservation, but it does not reduce the actual addressed staging
regions and risks invalid shared-memory accesses if the value is too small.

```text
Expected shared memory: lower reservation only
Template identity: unchanged
Occupancy: potentially higher if safe
Correctness risk: high unless exact addressed expression and alignment are honored
Clean Candidate #1: NO, because it changes launch allocation contract rather than
                    the staging algorithm
```

No compile or runtime test was performed.

### Candidate D — lifetime reuse inside the existing layout

The source already overlays `sh_red` with `sh_b` through:

```text
max(sh_red_size, sh_b_size)
```

Further reuse would require proving non-overlapping lifetimes across async
fetches, register loads, reductions, and synchronization points. That is a new
kernel design change, not an existing supported template option.

```text
Clean Candidate #1: NO
```

## 7. Decision

No legal existing template option provides a clean shared-memory-only
intervention for the exact reproduced path:

```text
global stages reduction: rejected by other eager instantiations
alternate tile/template: changes work mapping/register strategy
launch allocation reduction: separate allocation-contract change with safety risk
additional lifetime reuse: new kernel design
```

Therefore:

```text
SHARED-MEMORY PATH NOT CLEANLY SEPARABLE — move to Candidate #2
```
