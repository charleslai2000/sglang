# RH Pressure Acceptance — pass 1 (C4/C5/C8 x ON/OFF), 2026-09-12

```yaml
schema: rh-pressure-summary-1
task_id: RH-PRESSURE-20260912
repo: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
head: 4f41f5bab562b99562f30c67540eb05344d13637
contract: work/RH-PRESSURE-ACCEPTANCE-CONTRACT-20260912.md (sha b9bb2e17...8919)
launcher: launch-p2b0m.sh sha 33d0cb99fc14b69ef41e8c1b41c345a4cefe12ddcfb82cc8a2fa61283bee0c72
status: PASS-1 data (valid) + METHODOLOGY CORRECTION; confirmation run2 in flight
```

Grading: `FACT` / `INFERENCE` / `OPEN` / `DECISION`.

## 1. Setup

`launch-p2b0m.sh` = frozen `launch-p2b0.sh` + `--enable-metrics` ONLY (needed to
expose the contract-authorized `/metrics` idle seam; changes no scheduling/KV
behavior). Cells `C in {4,5,8} x {RH-ON,RH-OFF}`, `MEAS=12` (target >=40
measure completions), `HIST=6000`, `DELTA=800` words, `SECS=240`, fresh extent
dir + fresh server per cell, serialized on `/mnt/data/gpu/3090.lock`. Run1 order
was ON(C4,C5,C8) then OFF(C4,C5,C8). Raw: `/mnt/data/nerun-dev/p2b0/run1/`.
0 bad HTTP in all 6 cells.

## 2. Results (run1)

| cell | n | window s | aggTPS | reqTPS | ctxTPS | idle_engine | gpu_idle | TTFT p50 | TTFT p95 | TFTT p50 | stage_q2 p50 ms | stage_q2 p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| on-c4 | 48 | 234.3 | 6.56 | 0.205 | 7309 | 0.423 | 0.424 | 5.33 | 51.9 | 2.98 | **4699.6** | **17654.6** |
| off-c4 | 48 | 109.3 | 14.05 | 0.439 | 15668 | 0.110 | 0.110 | 4.29 | 22.6 | 1.45 | **839.0** | **5462.1** |
| on-c5 | 60 | 227.2 | 8.45 | 0.264 | 9423 | 0.369 | 0.379 | 5.37 | 43.4 | 2.47 | - | - |
| off-c5 | 60 | 178.6 | 10.75 | 0.336 | 11987 | 0.345 | 0.345 | 4.90 | 32.1 | 1.92 | - | - |
| on-c8 | 82 | 328.9 | 7.98 | 0.249 | 8205 | 0.425 | 0.437 | 7.24 | 84.5 | 2.24 | - | - |
| off-c8 | 87 | 323.4 | 8.61 | 0.269 | 9036 | 0.465 | 0.468 | 11.53 | 86.0 | 1.82 | - | - |

`restore_recompute` counts (attempt-level, includes MISS_RECOMPUTE retries):
on-c4 123 / off-c4 121; on-c5 144 / off-c5 143; on-c8 193 / off-c8 134.
`ready_host`: on-c4 23 / off-c4 25; on-c5 63 / off-c5 80; on-c8 119 / off-c8 158.

## 3. FACT — the C4 mechanism (strongest signal)

`FACT`: at C4, RH-ON's L3->L2 stage (`ready_host - prefetch_issue`) is p50
**4.70 s** (p95 17.65 s) vs RH-OFF **0.84 s** (p95 5.46 s) — ~5.6x worse median.
`FACT`: RH-ON's `restore_state` mix shows many `WAIT_CAPACITY`/`MISS_RECOMPUTE`
and `ready_stage=56`; RH-OFF `ready_stage=0` (eager path does not emit
`ready_stage`).
`INFERENCE`: the eager path prefetches at **enqueue** (`scheduler.py:6068-6072`),
i.e. strictly earlier than the RH pass, so under ordinary pressure it gets a
longer head start and hides the stage better; RH's horizon pass runs later and
its stage is not hidden. This is consistent with R-HBA1's C1 result (RH matched
hot only because a long A supplied ~8 s of lead).
`FACT`: at C8 the two arms converge (aggTPS 7.98 vs 8.61; idle_engine 0.425 vs
0.465, ON marginally better); at C4/C5 RH-ON is clearly worse.

## 4. FACT — methodology correction (graded)

原结论 (P2B0 execution contract §9 / scorecard pass1): "concurrency sweep uses a
fixed per-session history H=6000 so concurrency is the only variable".
新证据 (`p2b0_driver.py:505-513`): the measure loop sets
`prompt_ctx["text"] = prompt_ctx["text"] + "\n\n" + make_delta(...,1000+turn)`
and then appends the previous output, so the prompt **grows every measure turn**
(~800 words ~= 1.0-1.1k tokens + output). At `MEAS=12` a session reaches
~18k+ tokens, so `C x H = 4 x 18k > 65536` at C4 — the device pool overflows and
the run stops being a fixed-H concurrency sweep. This also explains why run1's
windows (234-329 s) exceed `SECS=240` and differ strongly between arms.
因此修正为: the P2B0 driver is a **growing-context** workload, not a fixed-H
concurrency sweep; `C x H <= 65536` holds only for early turns. Any verdict must
either (a) hold context fixed (small/zero delta) for a true concurrency sweep, or
(b) explicitly analyse the growing-context pressure regime with order control.
This is a measurement-harness defect, not a product-code defect.

## 5. Confounds (explicit, not hidden)

1. **Order**: run1 executed all ON cells before all OFF cells. Ambient
   host-RAM/thermal drift could bias. -> run2 repeats each C **off->on**
   (reversed, interleaved).
2. **Growing context** (§4) makes the workload drift within a cell; window
   length is a consequence of per-request latency (driver is closed-loop), so
   `aggTPS` is meaningful but not comparable to pass1's `MEAS=8` numbers.
3. **`/metrics` seam** required the `--enable-metrics` delta; constant across
   both arms, so it cancels in the ON-vs-OFF contrast.

## 6. Preliminary finding (DECISION, pending run2)

`INFERENCE` (medium confidence, order confound open): under this pressure
profile RH-ON does **not** beat the RH-OFF eager prefetch; at C4/C5 it is
materially worse (later `ready_host`, higher TTFT p95, lower throughput), and at
C8 it is a wash. If run2 reproduces this direction with reversed order, the
pressure verdict is **NO NET RH ADVANTAGE / NEGATIVE at moderate C**, and the
product value of horizon-aware staging relative to the existing eager prefetch
is not demonstrated at this profile. This is a legitimate, reportable outcome —
NOT to be converted into a PASS.

## 7. Next

run2 (`/mnt/data/nerun-dev/p2b0/run2/`, order off->on per C, same MEAS=12)
-> compare direction; if stable, freeze the pressure verdict and update
ledger/plan.
