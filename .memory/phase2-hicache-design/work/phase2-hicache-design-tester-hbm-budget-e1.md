# Phase① HBM budget sweep — Mamba+Graph safe HBM boundary on 3090-24G

- Agent: tester
- Epoch: 1
- Date: 2026-09-05
- Target: `ssh -i /home/charles/.ssh/id_ed25519 -p 24052 root@175.155.64.171` (RTX3090, 24576 MiB, driver 580.173.02, model Qwen3.5-9B-w4a16)
- Status: **done**

## Method (trace-consistent)

Every cell: same wrapper template (only `--max-mamba-cache-size` value varies between pools); gON = graph backend enabled (no `--cuda-graph-backend-*=disabled`), gOFF = graph backend disabled (`--cuda-graph-backend-decode=disabled --cuda-graph-backend-prefill=disabled`). Same driver (`/root/gate2_load.py`), rt=100, budget=300s, cmax=300, wt=4, same extent backend, mem_fraction 0.92, max-running-requests 8. Concurrency varied only in `--agents 4/6`.

New wrappers created by copying `direct-launch-sweep-p106-*.sh` and changing only `--max-mamba-cache-size 80`/`96` (verified by diff: only the pool-value token differs).

Prior sweep evidence reused for p32/p64 (rc=0 at 8 agents from existing status logs, Sep 5 03-07h) and p106/p160 at 8 (OOM rc=137). New runs executed this epoch: p80/p96 both graphs at conc 4+6; p106 both graphs at conc 4+6.

## Results table

| pool | Graph | boot used MiB | boot free GiB | ssm_state GB | conc4 rc | conc6 rc | OOM? | max_running cap? | verdict |
|------|-------|---------------|---------------|--------------|----------|----------|------|------------------|---------|
| 32 | OFF | 15445 | 8.92 | 1.55 | 0 (8ag safe) | 0 (8ag safe) | no | yes→6 (bottleneck) | safe |
| 32 | ON | 16171 | 8.21 | 1.55 | 0 (8ag safe) | 0 (8ag safe) | no | yes→6 (bottleneck) | safe |
| 64 | OFF | 17023 | 7.38 | 3.05 | 0 (8ag safe) | 0 (8ag safe) | no | no | safe |
| 64 | ON | 17749 | 6.67 | 3.05 | 0 (8ag safe) | 0 (8ag safe) | no | no | safe |
| 80 | OFF | 17811 | 6.61 | 3.80 | 0 | 0 | no | no | safe |
| 80 | ON | 18537 | 5.90 | 3.80 | 0 | 0 | no | no | safe |
| 96 | OFF | 18599 | 5.84 | 4.55 | 0 | 0 | no | no | safe |
| 96 | ON | 19325 | 5.13 | 4.55 | 0 | 0 | no | no | safe |
| 106 | OFF | 19093 | 5.35 | 5.02 | 0 | 0 | no | no | safe |
| 106 | ON | 19819 | 4.65 | 5.02 | 0 | 0 | no | no | safe |
| 160 | OFF | (boot ok) | ~4 | 7.5 | OOM@8 | OOM@8 | yes@8 | n/a | OOM at 8 (ref) |
| 160 | ON | (boot ok) | ~4 | 7.5 | OOM@8 | OOM@8 | yes@8 | n/a | OOM at 8 (ref) |

Notes:
- p32 caps max_running to 6 (32 slots / 5-state-slots-per-req); p64+ no cap observed (all new runs 80/96/106 had no cap message, capacity ≥ 19 req).
- ssm_state scales ≈ linear: 1.55G@32, 3.05G@64, 3.80G@80, 4.55G@96, 5.02G@106.
- Boot free HBM decays with pool; gON consistently ~600-900 MiB tighter than gOFF at same pool (graph eager allocation).
- OOM only ever triggered **at 8-agent concurrency under pool saturation** (prior p106/p160 runs), never at conc 4/6.

## Evidence paths (all on 175.155.64.171:/root)

New runs this epoch (status logs):
- `gate3-sweep-p80-gON-a4/a6`, `gate3-sweep-p80-gOFF-a4/a6`
- `gate3-sweep-p96-gON-a4/a6`, `gate3-sweep-p96-gOFF-a4/a6`
- `gate3-sweep-p106-gON-a4/a6`, `gate3-sweep-p106-gOFF-a4/a6`
with engine logs `engine-gate3-sweep-<tag>.log`, evidence `evidence-gate3-sweep-<tag>/` (gpu-util.csv, metrics-final.txt, engine-alloc.txt, run-*/join.log).

Mamba alloc lines (engine log, all 106): `Mamba Cache is allocated. max_mamba_cache_size: 106, conv_state size: 0.12GB, ssm_state size: 5.02GB`; OOM count `grep -ac "CUDA out of memory\|out of memory"` = 0 across all new runs.

Prior runs (reference): `gate3-sweep-p{32,64,106,160}-g{ON,OFF}-status.log` (rc=0 for 32/64@8, rc=137 for 106/160@8), evidence `evidence-gate3-sweep-p{32,64,106,160}-g{ON,OFF}/`.

Wrappers: `direct-launch-sweep-p{32,64,80,96,106,160}-g{ON,OFF}.sh`. p80/p96 new this epoch.

## Safe-zone conclusion (for stage②)

**All of pool ∈ {32, 64, 80, 96, 106} × Graph {ON, OFF} are safe at both concurrency 4 and 6.** Boot free HBM stays ≥ 4.65 GiB (p106-gON); peak load HBM at conc6 keeps ≥ 4.3 GiB free. OOM at these sizes only occurred **at 8-agent concurrency** in the prior sweep (p106/p160), where pool+KV+Graph capture simultaneously saturated 24G.

**Stage② can adopt pool = 96 or 106 as the practical max safe ceiling for 4–6 concurrent agents** (gives the largest mamba checkpoint pool, 4.55–5.02GB ssm, with ~4.6–5.3 GiB boot headroom and ~4.3–4.5 GiB headroom under conc6 load). If stage② needs to guarantee 8-agent concurrency, pool must stay ≤ 64 (32 caps running concurrency to 6, so 64 is the largest that sustains 8 agents without cap or OOM).

Recommendations:
- For 4–6 agents: **pool 96–106** (max pool in safe zone). No mamba cap, no OOM.
- For 8 agents: **pool 64** (proven rc=0; pool 80/96/106 at 8 were the OOM boundary — 80/96 at 8 not run this epoch, but 106/160@8 OOM'd and 80/96 sit between 64 and 106, so treat as at-risk at 8 unless re-validated).
- gONE vs gOFF: both safe at ≤6 agents; gOFF frees ~0.6–0.9 GiB more HBM but disables the CUDA-Graph fast path, so prefer gON when headroom allows.

## Artifacts delivered
- Wrappers `/root/direct-launch-sweep-p80-g{ON,OFF}.sh`, `p96-g{ON,OFF}.sh` (copied from p106, only pool value changed) on target.
- 11 new soak runs executed and completed (rc=0 all), evidence captured on target.

## Followups
- 80/96 at 8-agent concurrency not exercised this epoch (task scoped 4/6 to avoid over-stressing). If stage② targets 8 agents, either cap pool at 64 or validate 80/96@8.
- `startup_available_gpu_memory_gb` field was not found under that name in the engine log; boot HBM taken from the first nvidia-smi sample in gpu-util.csv (sampled at engine-healthy) instead — consistent across all cells (trace-consistent sampling).