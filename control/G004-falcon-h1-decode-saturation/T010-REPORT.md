# G004 / T010 — Marlin Existing-Template Bounded Search

## Verdict

```text
T010: PASS
MARLIN EXISTING-TEMPLATE SEARCH: CURRENT TEMPLATE PARETO-BEST
```

No production dispatch, serving configuration, CUDA graph policy, quantization
layout, or kernel source was left modified. Candidate dispatch substitutions
were temporary offline-only changes and were restored after each run.

## Search space and static selection

The existing source exposes these small-batch configurations:

```text
(thread_k, thread_n, threads)
(128, 128, 256)
(64,  128, 128)
(128, 64,  128)
```

The production control is the first configuration:

```text
threads=256
thread_m_blocks=1
thread_n_blocks=8
thread_k_blocks=8
m_block_size_8=false
pipe_stages=4
group_blocks=8
```

Two alternate existing configurations were tested; no new tile shape or kernel
design was introduced:

```text
Candidate A: thread_k=64,  thread_n=128, threads=128
  template: threads=128, thread_m_blocks=1, thread_n_blocks=8,
            thread_k_blocks=4, m_block_size_8=false

Candidate B: thread_k=128, thread_n=64,  threads=128
  template: threads=128, thread_m_blocks=1, thread_n_blocks=4,
            thread_k_blocks=8, m_block_size_8=false
```

Both preserve the same M=16 operation, BF16 path, GPTQ uint4b8 layout,
group_size=128, act-order semantics, and one complete work unit.

## Correctness and timing candidates

All candidates used the same deterministic M=16 shape and reference as T006/T009.

| Candidate | Exact work units | Relative mean abs error | Deterministic | Mean total time | Min–max |
|---|---:|---:|---|---:|---:|
| Current control `(256, 128, 128)` | 1 | 2.001e-6 | yes | 113.89 us | 97.28–176.83 us |
| Candidate A `(128, 64, 128)` | 1 | 2.043e-6 | yes | 120.65 us | 104.45–166.88 us |
| Candidate B `(128, 128, 256)` | control/current | 2.001e-6 | yes | 113.89 us | 97.28–176.83 us |

The first row is the current production configuration. Candidate B was already
the current control and was not a distinct alternative.

Both distinct existing alternatives passed correctness but were slower than the
current control in the isolated timing sample. The differences are within some
sample overlap, so timing alone was not treated as decisive. The faster-looking
candidate A was therefore selected for the only targeted NCU comparison.

## Targeted NCU: current vs Candidate A

### Current control

```text
symbol:
  Marlin<..., 256, 1, 8, 8, false, 4, 8, false>

grid/block:                82 x 1 x 1 / 256 x 1 x 1
registers/thread:         148
dynamic launch allocation: 101.38 KiB
duration:                  39.62 us
achieved occupancy:        16.66%
active warps/SM:           8.00
eligible warps/scheduler:  0.29
SM throughput:             26.62%
DRAM throughput:           62.58%
DRAM bandwidth:            569.24 GB/s
L2 throughput:             37.37%
```

Stalls:

```text
barrier:            0.92
long scoreboard:    0.57
math-pipe throttle: 3.52
wait:               0.94
not selected:       0.16
```

### Candidate A

```text
symbol:
  Marlin<..., 128, 1, 8, 4, false, 4, 8, false>

grid/block:                82 x 1 x 1 / 128 x 1 x 1
registers/thread:         132
dynamic launch allocation: 101.38 KiB
duration:                  38.69 us
achieved occupancy:        8.33%
active warps/SM:           4.00
eligible warps/scheduler:  0.23
SM throughput:             27.22%
DRAM throughput:           64.26%
DRAM bandwidth:            584.77 GB/s
L2 throughput:             38.23%
```

Stalls:

```text
barrier:            0.25
long scoreboard:    0.25
math-pipe throttle: 1.55
wait:               0.73
not selected:       0.00
```

Candidate A lowers registers and math-pipe/barrier/scoreboard stall metrics, but
also halves block size and achieved occupancy, lowers eligible warps, and
slightly increases DRAM/L2 pressure. Its single NCU launch is only 0.93 us
faster than the current single launch, while the isolated complete-operation
sample is slower (120.65 vs 113.89 us). The evidence does not establish a
repeatable complete-operation improvement beyond run-to-run noise.

## Selection decision

```text
No existing alternate specialization demonstrated a clear complete M=16
operation improvement over current production control.
```

Candidate A's mixed resource changes are not a coherent improvement:

```text
registers:          148 → 132       improvement
math-pipe throttle: ~3.52 → ~1.55   improvement
barrier/scoreboard: lower           improvement
occupancy:          16.66 → 8.33%  regression
eligible warps:     0.29 → 0.23    regression
DRAM/L2:            slightly higher regression
complete timing:    slower in isolated sample
```

Candidate B is the current control, not a winner.

Therefore:

```text
MARLIN EXISTING-TEMPLATE SEARCH: CURRENT TEMPLATE PARETO-BEST
```

This means Pareto-best within the searched existing family and tested exact
shape, not a proof of global Marlin optimality.

## Recommendation

Do not run a production-dispatch canary for either searched alternative. End the
current Marlin existing-template tuning branch unless a new, separately
authorized hypothesis or broader system-level attribution justifies reopening
it. The next highest-value work should return to G004 system-level attribution
or another explicitly authorized optimization surface, not parameter guessing.

No optimization was executed.
