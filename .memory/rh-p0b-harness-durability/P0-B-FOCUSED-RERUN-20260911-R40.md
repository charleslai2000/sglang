status: blocked

artifacts: []

evidence:
- R40 stopped before remote access because its child-visible workspace did not
  contain the phase2 memory or exact R32 related-test selections.
- No SSH, backup, transfer, product/test modification, or pytest occurred.
- No P0-B or live-chain claim was made.

summary:
- R40 is a dispatch-context/materialization failure, not a test result.
- The exact focused HOST_ALLOC commands are known from R39, but the additional
  R32 dependency-free selection must be materialized explicitly before retry.

followups:
- Materialize R31/R35/R36/R39 and exact R32 command selections in the active
  memory workspace, then dispatch a fresh background run.

open_issues:
- Child workspace visibility continues to block deterministic execution.
