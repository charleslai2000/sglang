# E001 results

Status: ACTIVE — capacity gate passed; runtime fixture not yet launched.

## OBSERVED

- Canonical branch `3090-24g-opt` at `8b804d2fe20fddd90e0c26cb6a7e044aa244566c` after correcting the 50 GiB interpretation.
- No SGLang service/GPU process was active before cleanup; no server or listener on the selected test ports.
- User explicitly authorized removal of runtime HiCache data under `/data/l3`. All 37 immediate child runtime roots other than `/data/l3/c61-qwen-20260922-220343` were checked unlocked and removed. No non-L3 data was touched.
- The C6.1 root remains intact (39 GiB actual usage; manifest/data/WAL present).
- Available space increased from 32 GiB to 215 GiB on `/dev/sda1`; `/data/l3` is writable.
- `/mnt/data` remains an ordinary directory, not a mountpoint in this process namespace; the usable capacity is currently on `/dev/sda1`.
- Production settings remain unchanged: perf profile, `MAX_SIZE=100Gi`, `MIN_FREE_SPACE=50Gi`, extent backend, write_back, wait_complete, host cache, Qwen W4A16, fp8_e4m3, TP=1.
- The checked-in launcher template is not a runnable frozen launcher: it contains unresolved `@@TREE@@` placeholders and fails its source-identity gate (`@@TREE@@/env/bin/python` absent). It was run only in dry-run mode and created no runtime state. Do not claim its source identity gate passed.

## INFERRED

- Capacity precondition passes with ample headroom; no need to lower the min-free watermark or delete model/source/evidence files.
- Runtime launch still requires selecting the canonical live source execution path and recording identity/argv explicitly; avoid claiming a frozen launcher identity when no resolved launcher exists in this worktree.

## UNRESOLVED

- Exact request body and server-side token sequence/cache key capture.
- Minimal fixture population and direct pre-shutdown live manifest/index association.
- Graceful stop, fresh process reopen, exact replay, L3 read/restore evidence.

## Bounded answer

`STORAGE_CAPACITY_GATE=PASS`: 215 GiB available, C6.1 preserved, and all other user-authorized runtime L3 roots removed. This is not a HiCache restore acceptance result; no runtime fixture has yet been launched. Continue only with canonical source provenance, exact fixture artifacts, live-key capture, and restart proof.
