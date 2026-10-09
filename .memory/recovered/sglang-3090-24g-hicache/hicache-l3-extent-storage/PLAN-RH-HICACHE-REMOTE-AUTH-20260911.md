# Remote 3060 authorization correction report

status: done

artifacts:
- `.memory/phase2-hicache-design/context.md`
- `.memory/phase2-hicache-design/plan.md`
- `.memory/phase2-hicache-design/ledger.md`
- `.memory/phase2-hicache-design/work/PLAN-RH-HICACHE-REMOTE-AUTH-20260911.md`

evidence:
- User dispatch `PLAN-RH-HICACHE-REMOTE-AUTH-20260911`, fresh invocation
  `doc-writer-20260911-02`, explicitly authorizes the remote 3060 12G
  experimental instance for P0/P1/P2/P3 experiment verification.
- Existing plan and ledger entries establish the execution order, fresh Task ID
  requirement, P0 hard gate, P1 causal-chain requirement, and the standing
  `query_storage_hit_length` and FP8 quality decisions.

summary:
- Corrected the persisted authorization boundary: the remote 3060 12G
  experimental instance may be used for P0/P1/P2/P3 experiment verification.
- Recorded that every execution needs a fresh Task ID, the instance is not
  production, and the P0 hard gate and P1 causal chain cannot be bypassed.
- Recorded that authorization does not extend to the 3090 or production
  environments.
- Preserved `query_storage_hit_length` as measurement-only and FP8 KV quality as
  an independent blocker for final quality sign-off.
- No product, test, gate, storage, or git artifacts were modified.

followups:
- Future experiment executions must receive fresh Task IDs and use only the
  authorized remote 3060 12G experimental instance under the recorded gates.

open_issues:
- RH verification versus HOST_ALLOC governance remains a separate sequencing
  question; this authorization correction does not resolve it.
