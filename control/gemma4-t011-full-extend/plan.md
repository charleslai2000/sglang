# T011 Full Attention Extend plan

Status: DONE — the explicitly requested head_dim=512 Full Extend candidate is inapplicable to the frozen production checkpoint.

## Established result
Frozen baseline `c102ccbc5cfd17b510f896b23107204daf5ed0d7`, production source `a76206a5fb`. The actual model has Full head_dim=256, GQA 8 query / 2 KV heads, Full IDs `[5,11,17,23,29,35,41]`; final shared Full owners resolve to layer 23. SM86 Triton Full Extend uses BLOCK_M/N 64/64. Existing `(1,8,128)` trace row is 63 launches / 2708.544 ms, structurally 8192 query rows at that tile size, but does not expose layer/type or context per launch and cannot be safely attributed beyond that.

Because the production checkpoint has no Full head_dim=512 case, no synthetic 512 test would qualify the target. Candidate stopped before GPU run, without source changes, oracle, acceptance, or cache restore. No performance or memory claims. Full result in `runs/T011-FULL-EXTEND-FA2-QUALIFICATION.md`; task state in `tasks/T011-full-extend-fa2.md`.

## Reopen condition
Only on explicit scope change to actual Full head_dim=256, or on provision of a frozen production checkpoint whose Full Attention is head_dim=512. No replacement algorithm selected.
