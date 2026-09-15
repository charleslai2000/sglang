# P1 closure record (FROZEN) — SPEC_BUDGET causal chain + HOST_ALLOC liveness fix

- task_id: `P1-CLOSURE-20260912`
- epoch: 2026-09-12
- authority: **user ruling** (accepted Option 1, 2026-09-12). This closure is
  a user decision, not a self-graded PASS.
- repo: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
  (branch `3060-12g-qwen35-4b`, HEAD `4f41f5bab5`, intentionally dirty)
- server under test: PID 3082643 (scheduler child 3086752), port 30000,
  `scheduler.py` sha256 `892efc25e2a9ef7c5ebb4afa09cf6914182b1467981d14cd76c53eea5d8de9d7`

## Frozen status

> **P1 = VERIFIED / CLOSED**
> **HOST_ALLOC 新 clause = VERIFIED by unit + frozen real-event replay; not
> live-decisive exercised.**

### Control-plane freeze

| item | state |
| --- | --- |
| P0-A | VERIFIED |
| P0-B | CLOSED (A′) — R116 storage-backed reducer is closure authority |
| P0-C | CLOSED — R117 immutable freeze + R124 new-build re-freeze |
| P1 full RH causal chain | **CLOSED / VERIFIED** |
| HOST_ALLOC liveness fix | **VERIFIED** (unit + frozen real-event replay + live regression) |
| decisive live execution of the new clause | **residual, NON-BLOCKING** |
| next stage | **P2-A** |
| P2-A/B, P3, Q | gated only by their own execution order, not by P1 |

## Frozen residual (verbatim; NON-BLOCKING for P1 or P2-A)

> `Residual: no post-fix live workload exercised the new capacity-satisfied /
> generation-unchanged clause as the deciding grant branch. The clause is
> covered by unit tests and deterministic replay of the frozen R121 real event
> where OLD=false and NEW=true.`

## Why this is sufficient for P1 (rationale of the ruling)

P1's claim is the **system-level causal chain and liveness**, not that every
internal conditional branch must become a live "deciding branch" under some
workload. The evidence satisfies that claim:

1. **Full live chain, 4× on the fixed build** —
   `durable -> nonresident -> park -> release -> wake -> full KV+Mamba restore
   -> generation`:
   R125 run1 (`work/R125-bundle/raw.log:2,:12,:73,:78,:40800,:128043,:271087`)
   and R126 runs 1-3 (Gates 0/1/3 PASS in every run).
2. **Restore is FULL at the durable boundary** on every passing run:
   `restore_hybrid_finalize kv_expected=27328 kv_fetched=27328`, Mamba
   `1/1`, `all_or_nothing=true`; `durable-prefix recompute == 0`;
   `hybrid_discard == 0`; HTTP 200.
3. **The new predicate is unit-covered** — 18 unit tests
   (`test/registered/unit/managers/test_hicache_host_allocability.py`, incl. the
   4 mandated classes: wake→alloc-fail→re-park no-spin, etc.); focused regression
   green (lineage 8, scheduler_feed 46, drain_reentry 31, ready_horizon 74,
   storage_regression 126 exit 0, prefetch_budget_split 24).
4. **The decisive evidence — the frozen real R121 event where OLD=false and
   NEW=true** (`work/R121-bundle/raw.log:270076`, park `:224765`): the ACTUAL
   fixed `_host_alloc_wait_eligible` flips `hold_no_generation` -> eligible/grant.
   This is not a synthetic case: it is the real production-path bug state
   (mamba generation unchanged `1853->1853` while capacity-satisfied
   `free+evictable 76 >= 1`, kv `1229->1230`), reproduced by running the fixed
   code against the recorded snapshots
   (`/mnt/data/nerun-dev/tmp/r124-replay/replay_r121_event.py`).

R126 is **regression evidence, not a failed attempt**: it proves the new
predicate does not misfire on the normal path — it **holds** while KV is
genuinely blocked (`free+evictable 6212 < 27328`) and **grants normally** when
the generations advance together. The narrow window required to make the new
clause live-decisive (KV advances, Mamba does not, Mamba capacity satisfied) is
not worth engineering a workload to manufacture; doing so would construct a
branch rather than observe one, with very low information gain.

## Evidence binding (sha256)

| artifact | sha256 |
| --- | --- |
| `P1-DURABLE-PREFIX-REPLAY-20260912-R125.md` | `e496a3ce75d71d7bfae44d46c480891d2c8361b0b4fc497fa5033666429e7c27` |
| `P1-DURABLE-PREFIX-REPLAY-20260912-R126.md` | `23ed5d488d66a84f5e52c35601161b714b328c4c1be0811547345bb2830267e2` |
| `P1-TEMPORAL-DISCRIMINATION-R121.md` | `a457c91c7f03ddd27604f7b51f50c52e2fe6d74ff4de523e6229f3b1d34642a9` |
| `P1-HOST-ALLOC-WAKE-ELIGIBILITY-SOURCE-NOTE.md` | `1b40782d1e4601591d919fe232db98ae5653a3684fb5324b5f91def7ba2bd211` |
| `R125-bundle/P1-R125-DURABLE-PREFIX-REPLAY-CONTRACT.md` | `f78a2fc698de375de612ace8c023e4a6518a6781c155c2f5e92b66dd521f3c1f` |
| `R126-bundle/P1-R126-FAITHFUL-REPLAY-REPLICATION-CONTRACT.md` | `13ba59c06902d9e7cb2bc205ee7b9118776122e67f3eee107980ce8fdc1667b7` |
| `R121-bundle/P1-R121-CONTROLLED-EVICTION-CONTRACT.md` | `2ac86b5a54264fad46d049e2c32e3cc37c125f8c778a38dfb14e840a37be3b3b` |
| `R123-bundle/P1-R123-TEMPORAL-WAKE-GATE-CONTRACT.md` | `bf7b09ee67f40a3f9c5e58b89d54e091b028fae1a96c853bdebfcadd1145e1f8` |
| `R122-bundle/P1-R122-HEADROOM-GATE-ADDENDUM-v2-CORRECTION.md` | `cbd1cf5748146a6bf1e77bedb6586d99019ea48ccd791a9b0d0f2a47555decce` |
| `R124-bundle/R124-ORCHESTRATOR-CORRECTION.md` | `c57905ffbb0338a86fc5e91fc47add9023ce5c29a3228beb36a52abacd413cd2` |
| `R124-profile/P0-C-3090-PROFILE-REFREEZE-20260912.md` | `cbdc2202ca2c913795d9103d76cf9e5ff7f61d0ea0f082da587b8ccbbcee267d` |
| `python/sglang/srt/managers/scheduler.py` (fix) | `892efc25e2a9ef7c5ebb4afa09cf6914182b1467981d14cd76c53eea5d8de9d7` |

## Frozen P1 acceptance predicate set (the oracle for this closure)

P1 was accepted iff ALL of:

1. **NON_RESIDENT** — target T `device_hit_tokens==0 AND host_hit_tokens==0`.
2. **SPEC_BUDGET park** — `wait_reason='SPEC_BUDGET'` / negative cursor > budget
   (39321).
3. **Exactly-once release** — the spec-budget release epoch advances by exactly
   +1, and T's RH issue epoch >= the release epoch (no premature consumption).
4. **RH issue** — `prefetch_issued(rid=T)` and `ready_stage result=issued`.
5. **HOST_ALLOC wait -> wake** — T parks in `HOST_ALLOC` and is woken by a grant
   (the new clause decides when its condition appears; else the generation
   branch decides — both acceptable for the system-level claim).
6. **FULL durable-boundary restore** — `restore_hybrid_finalize
   kv_fetched==D_req`, Mamba sidecar complete, `all_or_nothing=true`.
7. **No recompute / no discard** — `durable-prefix recompute == 0`,
   `hybrid_discard == 0`; HTTP completed; identity continuous.
8. **Liveness** — `t_feasible < t_deadline` when the wait completes.

Predicate outcomes are recorded per run in R125/R126. Predicates 1-5,7,8 held in
R125 run1 and R126 runs 1-3; predicate 6 held at the durable boundary. Predicate 5
was satisfied by the generation branch in every live run, and by the **new
capacity clause** in the frozen real-event replay. This is the accepted closure
basis and the residual.

## Explicit non-claims

- No claim that the new clause was ever the live deciding grant branch (see
  residual).
- No claim about P2-A lead-time/critical-path numbers (next stage).
- No product, test, profile, or R121-R126 artifact was modified to produce this
  closure.
