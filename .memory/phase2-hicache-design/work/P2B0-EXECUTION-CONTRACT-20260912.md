# P2-B0 execution contract — 3090 / ExtentFileBackend era (2026-09-12)

```yaml
schema: phase2-hicache-p2b0-execution-1
artifact_id: P2B0-EXECUTION-CONTRACT-20260912
task_id: P2-B0-20260912
role: orchestrator
repo: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
head: 4f41f5bab562b99562f30c67540eb05344d13637
supersedes_framing_of: P2-B0-CONTRACT-20260911-R71 (keeps its frozen semantics)
classification: MEASUREMENT (scorecard), not a correctness gate
```

## 1. Authority and scope

User ruling 2026-09-12: E-phase PASS/CLOSED; production L3 =
ExtentFileBackend + RAM-authoritative index; **E4a is the new baseline**;
R129 legacy figures are scalability-failure evidence and are excluded from
production performance comparison. User directive: **enter P2-B0 immediately**
and measure cache-induced GPU idle, RH OFF/ON aggregate TPS, TTFT/TFTT, L3->L2
stage distribution (n >> 2), whether queue lead covers the ~300 ms stage, and
C1/C4/C5/C6/C8.

P2-B0 is a scorecard/capacity measurement phase. It produces no product code.

## 2. Frozen semantics carried from R71 (still binding)

- `C<n>` = nominal client **concurrency level** n; `C2` is sanity-only and
  excluded from the main matrix. Engine `--max-running-requests = C<n>`.
- `total_throughput` is **`not computable`** (R71 option T4) until the user
  supplies an explicit numerator/denominator/window. It MUST NOT be filled with
  `aggregate_output_tps` or any derived number. (Surfaced to the user in
  writing.)
- Missing/sparse data is `not computable`, never 0. Gains only from matched
  completion sets. Every row binds the complete profile + a per-row source/args
  hash. Drift ⇒ stop the cell.
- Scenario classes: `L1-hit`, `L2-restore`, `RH-staged-L3`, `cold-L3`
  (cold-L3 reported but not held to <1 s). TTFT P95 from real streaming
  first-token timestamps.

## 3. Profiles (two variants, one frozen base)

Base = `launch-e-20260912.sh` (`--hicache-storage-backend extent`; sha
`d24195b9a66c832226d8956ac6c79c168fbc92c4b67de44c0e1485847ab3c651`).

- **RH-ON**: base as-is.
- **RH-OFF**: identical except the three RH flags are removed
  (`--enable-ready-horizon`, `--ready-horizon-frontier-n`,
  `--ready-host-watermark-low/high`). Everything else, including
  `--enable-session-radix-cache`, is identical.

Per-cell the only other varying flag is `--max-running-requests = C<n>`
(the P2-B concurrency axis). The frozen profile value is 1; raising it per cell
is the intended axis, recorded per row. `--max-mamba-cache-size` stays 53 unless
a cell proves it caps concurrency (then report actual vs nominal and flag it,
never silently change it).

## 4. Cells (mandatory)

`{C1, C4, C5, C6, C8} x {RH-ON, RH-OFF}` = 10 cells, run serially on the single
3090 lock. Each cell: prime/warm phase (populate L2/L3 and make the measure
phase hit-dominated) then a steady-state measure window. Minimum completed
requests per cell for statistical claims: >= 40; otherwise mark the cell
`under-sampled`.

## 5. Metrics per cell (with seam)

| Metric | Definition | Seam |
| --- | --- | --- |
| `aggregate_output_tps` | sum output tokens / measure window | client streaming + server `realtime_tokens_total{mode=decode}` cross-check |
| `request_throughput` | completed requests / window | client 200 + terminal finish |
| `ttft_p50/p95` by scenario | first-token timestamp - request send | client streaming (`stream: true`) |
| `tftt_p50/p95` | last-token ts - first-token ts (decode/streaming window) | client streaming |
| `stage_q2` distribution | ready_mono - prefetch_issue_mono | probe M2 + `ready_host` |
| `queue_lead_q1` | admission_mono - enqueue_mono | probe M1 + `admission.v2` |
| `cache_induced_gpu_idle` | time with GPU idle **while runnable work is queued** | `nvidia-smi` timeline (sub-second) joined with `/metrics` `num_queue_reqs`/`num_running_reqs` |
| `gpu_idle_total` | time GPU util < idle threshold / window | `nvidia-smi` timeline |
| completion set | count, finish reasons, bad HTTP | client |

`cache_induced_gpu_idle` is a GPU-timeline metric; report duration + fraction of
window and reconcile with `restore_wait/queue_wait/compute/decode`. Any term
without a seam is `not computable`. Do not use `load_back_duration_seconds` as
isolated `restore_wait`.

### Measurement authorisation

The user explicitly requested `cache-induced GPU idle`, which authorises a
read-only GPU busy/idle timeline. The mechanism is external and non-invasive:
`nvidia-smi` sampling (sub-second) + the server's existing `/metrics` endpoint.
No product code, hooks, interception, or scheduler change is introduced.

## 6. Deliverables

1. `work/P2B0-bundle/` driver + GPU/metrics sampler (self-contained; no
   `common.py`), with a CPU-only `--dry-run` self-test.
2. Per-cell raw windows + `join.jsonl` (one row per request) under
   `/mnt/data/nerun-dev/p2b0/` (large bytes) with a compact extract in the
   bundle.
3. `work/P2-B0-SCORECARD-20260912.md`: the 10-cell scorecard, RH ON vs OFF
   delta, scenario TTFT, stage distribution (n >> 2), queue-lead coverage, idle
   split + reconciliation residual, and the capacity note.
4. An explicit statement that `total_throughput = not computable` pending the
   user's definition.

## 7. Acceptance

Measurement completeness, not a pass/fail correctness gate: every cell either
has a complete measure window or is marked `under-sampled`/`not computable`
with the reason. No fabricated zero. Correctness side-condition: 0 bad HTTP
and no full-prefix recompute on measured hits.

## 8. Out of scope

G1 restart-rebuild (production hard gate; needs Pattern Intake + Novel Mechanism
first). G3/G4/G5 hardening. Any product/code/test change.

## 9. Device-budget constraint and the split of the two axes (clarification)

The frozen profile fixes `--max-total-tokens 65536` (device KV pool in tokens).
A running request holds its live sequence in device KV, so the concurrency sweep
and a large per-session context are mutually exclusive under this profile:
`C<n> x H + output_budget <= 65536`.

Resolution (no profile change):

- **Concurrency sweep (`C1/C4/C5/C6/C8`, RH ON/OFF)** uses a **fixed**
  per-session history `H = 6000` tokens so concurrency is the only variable:
  `C8 x 6000 = 48000`, plus small output budgets, fits within 65536.
- **Context/capacity ladder (`H in {55K,64K,128K,192K}`)** is a **C1-only**
  capacity axis reported separately in the capacity note; it cannot be crossed
  with C>1 without raising `--max-total-tokens`, which is a P0-C profile change
  and is out of scope here.

If a cell proves `--max-mamba-cache-size 53` or another pool caps effective
concurrency below nominal, report actual vs nominal and flag the cell; do not
silently change the flag.

## 10. USER RULING (2026-09-12) — throughput naming and re-sample scope

**Drop the ambiguous `total_throughput`.** The scorecard reports four
independently named metrics; no field named `total_throughput` is emitted.

| Metric | Formula | Role |
| --- | --- | --- |
| `aggregate_output_tps` | `sum(output_tokens) / wall_time` | main user-facing throughput |
| `request_tps` | `completed_requests / wall_time` | request rate |
| `effective_compute_tps` | `(sum(uncached_prefill_tokens) + sum(output_tokens)) / wall_time` | real compute throughput; **uncached prefill only** |
| `served_context_tps` | `(sum(all_prompt_tokens) + sum(output_tokens)) / wall_time` | product capacity ("context served/s"), NOT compute |

Hard rule: do NOT count L1/L2/L3-hit prefix tokens as input throughput —
counting cached prefixes would inflate the number as hit rate rises.
`served_context_tps` is a product/capacity indicator, explicitly not GPU
compute throughput.

**Proxy labeling rule:** any `queue_lead_q1` fallback (e.g.
`enqueue -> prefetch_issued`) MUST be emitted as its own clearly named field
(e.g. `prefetch_lead_proxy`) with its exact definition, and MUST NOT be merged
into, aliased with, or presented as the real `enqueue -> admission` duration.

**Re-sample scope (user):** do NOT re-run all 10 cells. After the sampler fix,
re-sample only **C4/C5/C8 x {RH-ON, RH-OFF}** (6 cells) — these cover
no-pressure -> RH turning point -> high pressure.

**Primary target of the re-sample:** `cache_induced_gpu_idle` fraction using the
corrected `running+queue` (and the precise restore-interval variant). If C5/C8
show RH materially lowering this idle **and** it moves in the same direction as
the TPS uplift, the P2-B0 core causal chain is closed.
