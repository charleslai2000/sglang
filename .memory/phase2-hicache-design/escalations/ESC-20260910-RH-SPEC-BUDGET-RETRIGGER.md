# ESC-20260910-RH-SPEC-BUDGET-RETRIGGER

- stable_task_id: D3060-RH-SPEC-BUDGET-RETRIGGER-20260910
- invocation_id: INV-20260910-DEBUG-RH-SPEC-BUDGET-R1
- epoch: 20260910-rh
- current_level: L2
- target_level: L2 diagnosis; return owner: coder
- owner: debugger-deep
- decision question: Why does a Ready Horizon candidate parked after a speculative-budget exhaustion retain `negative_cursor=0` after the post-issue speculative counter is 54999, and what is the minimal safe re-trigger fix?
- constraints: only RH causal bookkeeping; preserve storage/restore semantics; no broad budget or watermark redesign; add a focused regression; 3090 production-candidate behavior must remain unchanged.
- confirmed evidence: 3060 live blocker+A/B trace; RH ON emitted one `rh_stage.v2` for A; B was eligible then parked `SPEC_BUDGET`; event records show speculative used 54999, later spec budget 0, B still `negative_cache` with `negative_cursor=0`, no second stage, `cached_tokens=0`; RH OFF restored B from L3 with 54976 storage-hit tokens.
- source hypothesis: post-issue `_park_ready_decline` receives the pre-issue `epochs` snapshot, whose `spec_budget` is 0; the parked cursor therefore cannot be cleared by the later 0 transition. This is a hypothesis pending independent diagnosis.
- attempted approaches: default RH two-session trace (50% pre-admission Host-ready); blocker-horizon trace (same 50%, isolates prediction horizon); source inspection located the post-issue park calls and `policy_epoch_value`.
- error cost: incorrect fix can reintroduce per-pass RH retry/spin, duplicate prefetch, or storage churn; require unit regression and fresh live same-trace gate.
- immutable references: `OPS3060-RH-QUEUE-COMPARE-R1-20260910.md`; remote `/tmp/sglang3060-rh-horizon-r1/on.log`; local `python/sglang/srt/managers/scheduler.py` lines 4870-4887 and `scheduler_components/ready_horizon.py` `entry_cleared`/`epoch_event`.

