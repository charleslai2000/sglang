# T013 — merge acceptance of existing GPU optimisations

Status: DONE — both opt-ins retained; combo B (Humming + FA2) better on all three loads

## Scope
Baseline `7ed79dab11` (T012 close-out). Restore T011's accepted FA2 Forward-level plan reuse
as an independent opt-in (`SGLANG_FA2_RAGGED_EXTEND`), keep T012's Humming post-load opt-in
(`SGLANG_CTWNA16_HUMMING`), and accept the two combinations on unchanged model, request load,
KV capacity and cache configuration:

* **A — Humming + Triton** (`SGLANG_CTWNA16_HUMMING=1`, FA2 flag off)
* **B — Humming + FA2** (both flags on)

Workloads: original C-8 L1-only, the production three-tier HiCache stack, and the T010
long-context load (96 clients × 6 rounds × 5000-token turns, 36.5K final context).

## Rules
- Restore the archived candidate verbatim; no FA2 algorithm change, no new algorithm,
  telemetry framework or scheduling mechanism.
- Both opt-ins stay independent and default off; Triton/Marlin remain the defaults.
- Reuse existing evidence (T011 operator/integration checks, T012 weight identity and
  correctness, T009/T010 restore proofs) and only add what the merge itself needs:
  peak memory, decode CUDA Graph, combo-level numerical equality, real L3 restore.
- Retain only combinations that are stable and effective; otherwise keep the flag off.

## Result

| workload | A Humming+Triton | B Humming+FA2 | gain | extend device | peak GPU |
|---|---:|---:|---:|---:|---|
| C-8 L1-only | 737.55 (735.92 / 739.17) | 760.17 (760.48 / 759.87) | **+3.07%** | 155.9 → 147.4 s | 24,098 → 24,124 MiB |
| three-tier HiCache | 624.85 | 644.21 | **+3.10%** | 168.5 → 160.3 s | 23,982 → 24,102 MiB |
| T010 long-context | 116.51 | 135.22 | **+16.06%** | 1073.9 → 908.7 s | 23,798 → 23,896 MiB |

Every cell completes with an identical payload multiset, KV capacity is byte-identical
(1,443,628 tokens, SWA 65,536) and the decode CUDA Graph is captured and replayed in both arms.
Correctness: glue check 9.16e-4 vs the production Triton kernel with one plan per Forward, and a
real L3 restore round trip in a fresh process (`disposition=RESTORE ... reason=full`, 10,304 of
10,305 tokens) with identical greedy completions in both arms.

Retention: both switches stay independent and default off; the deployment recommendation is
`SGLANG_CTWNA16_HUMMING=1 SGLANG_FA2_RAGGED_EXTEND=1` with the frozen argv unchanged. FA2 remains
extend-only for Gemma4-shaped layers (head_dim 512, page_size 1, TP-local head counts), and the
128 MiB transient-prefix ceiling bounds the gain on short-context bursts. Full report:
`runs/T013-MERGE-ACCEPTANCE.md`.

## Layout
- `runs/t013_fa2_glue_check.py` — real-backend glue check for the restored path.
- `runs/20261127T-combo/` — combo driver (`run_combo.sh`), intent, status and evidence.
- `runs/t013_correctness.py` — A/B greedy equality and real L3 restore probe.
- `runs/T013-MERGE-ACCEPTANCE.md` — final report.
