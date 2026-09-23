# B5-INT Result

VERDICT: PASS

## Configuration

Same production configuration as Formal B5:

```text
Falcon-H1-7B-Instruct-GPTQ-Int4
RTX 3090 24GB
Mamba extra_buffer, BF16
prefill CUDA graph disabled
decode CUDA graph full
HiCache ON, ratio=2, write_through, FULL + MAMBA
L3/storage OFF
context length 8192
max running requests 16
```

The server used the worktree runtime and the only startup correction was replacing
an obsolete ambiguous `--cuda-graph-backend full` spelling with the explicit
current equivalent `--cuda-graph-backend-decode full`; no behavior/configuration
change was made.

## Part A — True Immediate Device Reuse

Target session: A = session 001.

Ordering was genuinely sequential:

```text
A turn1 submitted and completed
A turn2 submitted immediately afterward
no other request was submitted between them
```

Recorded monotonic timestamps:

```text
turn1 completion: 478153.058886241
turn2 submission: 478153.072161596
```

Token lengths and oracle:

```text
turn1 prompt: 2528 tokens
turn2 prompt: 2565 tokens
turn1: CODE=5233, correct
turn2: CODE=5233, correct
```

Turn 2 response metadata:

```text
cached_tokens: 2304
```

Metrics delta from the A-before to A-after snapshot:

```text
prefill device_hit: +2304
prefill host_hit: +0
```

Gate A: PASS.

The 2304-token device hit is consistent with page/alignment semantics for the
reusable prefix and is positive under the same production server/configuration.

## Part B — Dormant Host Reuse

Target session: B = session 002, kept separate from A.

After B turn1, distinct pressure sessions were submitted in batches. Pressure
stopped after 48 distinct requests when host occupancy reached:

```text
114,923 / 290,773 host tokens
```

At that point device evictions had occurred:

```text
evicted_tokens_total: 4,853
```

No host-pressure drops occurred:

```text
KV: 0
MAMBA: 0
```

B turn2 was then submitted immediately, without additional pressure.

B oracle:

```text
turn1: CODE=3152, correct
turn2: CODE=3152, correct
```

B turn2 metadata:

```text
cached_tokens: 2304
```

Counter deltas from immediately before to immediately after B turn2:

```text
host_hit: +2304
FULL/KV H→D: +256 tokens
MAMBA H→D: +2 states
```

Read-only durable probe supplied the authoritative residency/restore evidence:

```text
load_back_snapshot_before:
  FULL:  device_present=false, host_present=true, host_slot_count=256
  MAMBA: device_present=false, host_present=true, host_slot_count=1

load_back_issued:
  FULL/KV: 256 tokens
  MAMBA: 2 state transfers

load_back_completed:
  FULL/KV: 256, success=true
  MAMBA: 2, success=true

load_back_snapshot_after:
  FULL:  device_present=true, host_present=true
  MAMBA: device_present=true, host_present=true
```

This proves the requested host-only → H→D restore path for both components.

Gate B: PASS.
Gate C: PASS.
Gate D: PASS.

## Runtime Stability

```text
all diagnostic responses correct: yes
wrong-session code: 0
CUDA/runtime error: 0
OOM: 0
deadlock: 0
host-pressure drops: 0
num_running_reqs after drain: 0
```

The full diagnostic used 48 pressure requests plus the four target requests;
no 1000-turn Formal B5 replay was performed.

## Acceptance Matrix

| Gate | Result | Evidence |
|---|---:|---|
| A: true immediate device_hit > 0 | PASS | sequential A; +2304 device-hit tokens |
| B: dormant host_hit > 0 | PASS | B revisit; +2304 host-hit tokens |
| C: FULL H→D > 0 | PASS | +256 tokens; completion success=true |
| D: MAMBA H→D > 0 | PASS | +2 states; completion success=true |
| E: correctness | PASS | A/B 4/4 responses correct |
| F: runtime stability | PASS | no CUDA/runtime/OOM/deadlock evidence |

## Final Recommendation

```text
B5-INT: PASS
B5: PASS
B6: now unblocked by the B5 diagnostic closure,
subject to the separately specified B6 authorization/execution transition.
```

B6 was not run.

## Artifacts

```text
control/G003-phase2b-hicache/b5_int.py
control/G003-phase2b-hicache/runs/b5-int/result.json
control/G003-phase2b-hicache/runs/b5-int/a-before.txt
control/G003-phase2b-hicache/runs/b5-int/a-after.txt
control/G003-phase2b-hicache/runs/b5-int/b-before-revisit.txt
control/G003-phase2b-hicache/runs/b5-int/b-after-revisit.txt
control/G003-phase2b-hicache/runs/b5-int/b-pressure-048.txt
/tmp/t38c-probe.log (marker-gated read-only probe)
```
