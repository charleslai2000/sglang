status: done

artifacts:
- Durable report: `.memory/phase2-hicache-design/work/P0-A-HOST-RELEASE-RECONCILE-20260911-R27.md`

evidence:
- `host_release` is a valid required `CausalEpochs` field: constructed by `_epochs`, defined in `ready_horizon.py`, consumed for `NO_HEADROOM` clearing/causal events, produced by scheduler epochs, and covered by explicit tests.
- Current local and authorized remote ready-test hash both equal `696ef7b89d8bec8f58c9c2751e24ca67b0540ac94571114ed953eacf7fc7ecfa`; both contain `host_release`.
- R26's missing-symbol result was stale/mismatched or wrong-path/content selection.
- Hash `0f64c30c...` belongs to the budget test, not the ready test; other historical hashes belong to older/sibling states.

summary:
- Preserve `host_release` as a required ready-file gate.
- R26 did not run tests and remains invalid for P0-A.

followups:
- Fresh executor must hash each absolute path immediately before its own symbol gate and record the exact gate script/output.

open_issues:
- P0-A remains NOT_VERIFIED; a clean all-eight test execution is still required.
