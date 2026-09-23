Status: DONE
Work area: control / source-authority reconciliation
Objective: Reconcile /opt/sglang/opencodex-provider-2d4e33a832 against canonical commit ad63118354829f995b733ed0f5048caf8cda912e without copying the deployment tree or deleting it.
Inputs: /tmp/opt-missing.txt, /tmp/opt-diff.txt; canonical worktree; deployment scripts and service configuration.
Completion: Every non-generated /opt source-like path is classified; required runtime and operational content is present in canonical or explicitly proven superseded; a clean canonical commit records the evidence.
Result: `/opt` inventory completed: fresh enumeration found 239 missing and 43 differing paths (282 total; the prior 238 count omitted `.memory/phase2-hicache-design/authority.yaml`). All paths were classified. No required runtime or operational file was unique to `/opt`; no content was copied. The complete evidence and path-category rules are in `control/phase2-hicache-design/opt-c4-inventory.md`.
Remaining: None for C4. The then-active frozen DEV export was later confirmed down/unreferenced and removed during O003; O003 records that operational action.
