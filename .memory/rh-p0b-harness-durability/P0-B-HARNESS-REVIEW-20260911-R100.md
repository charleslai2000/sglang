status: done

artifacts:
- This report: `.memory/phase2-hicache-design/work/P0-B-HARNESS-REVIEW-20260911-R100.md`
- Reviewed canonical `work/R97-harness/` and R97 report.

evidence:
- R97 integrity/self-tests/compile/manifest pass, but semantic review rejects it.
- Critical defects: no exact event PID/profile equality binding; weak retry
  cache/generation/ordinal joins; malformed predecessor waits silently filtered;
  12 oracle entries instead of exact 11; per-request timeout can exceed global
  wall-clock bound.
- Plausible additional risks: mutable provenance manifest binding and weak
  finalization/READY RID/cache joins.
- No live execution or product changes.

summary:
- verdict: REJECT
- execution authorization: NOT AUTHORIZED
- Do not transfer or execute R97. P0-B remains NOT_VERIFIED.

followups:
- One repair invocation may address the named defects; then one fresh independent
  review. No parallel review/visibility loop.

open_issues:
- Product producer contract must confirm emitted PID/profile fields; absence is
  NOT_VERIFIED, not permission to weaken the join.
