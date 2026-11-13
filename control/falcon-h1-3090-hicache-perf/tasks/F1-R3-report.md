# F1-R3 stage report — 2026-10-09

## 1. Commit and GPU resource/window
- Branch `3090-24g-hicache`, baseline `601158469`; CPU tests/control-plane changes committed as `fd93a2ec2` (`test(hicache): cover promotion budgets and Mamba extent groups`). Three unit test files only; untracked `AGENTS.md` and `control/` deliberately not staged.
- Reproducible SM86 Python/DSO test overlay: `../SM86-CPU-TEST-ENV.md`.
- User explicitly confirmed GPU was unused. Follow-up read-only checks at 07:15 UTC showed RTX 3090 `1 MiB / 0%`, no compute PID and no listener on 30126; prior sibling initcheck PID had exited. Proceeded only with this user's local, loopback-bound Falcon experiments; did not inspect/change sibling files or processes.
- The first launch exposed the known editable finder/DSO import-path issue before model load. The successful runtime used the documented ephemeral SM86 overlay (checkout AOT Python + genuine installed DSO), without venv changes.
- Run `R3-20261009T0715Z`: first service came ready with IEC suffix sizes rejected (`max_size=0`, `min_free=0`) and default 64GiB geometry; stopped before requests. Second attempt on that directory used a 4GiB geometry and was correctly rejected against its 64GiB manifest. Both attempts and metadata are preserved, not cleaned.
- Run `R3-20261009T0728Z`: correct 4GiB Extent config on fresh directory; model loaded, `/health` 200, greedy request repeated with identical output IDs. Metrics/admin were initially omitted; service stopped normally.
- Run `R3-20261009T0735Z`: `--hicache-size 2` allocated only 7 usable MAMBA host states, too small for useful lifecycle; stopped.
- Run `R3-20261009T0750Z`: fixed 8GiB host pool (KV 94,879 tokens / 4.27GB, MAMBA 27 usable states / 3.76GB), Extent 64MiB/4GiB geometry and metrics enabled. Two repeated short smoke requests matched exactly. Then 120 sequential distinct 22–24-token prompts completed; target revisit output IDs matched its reference. This is **inference smoke only, not a cache lifecycle pass**: exact metrics show 2,679 effective input tokens, `device_hit=0`, `host_hit=0`, `storage_hit=0`; `hicache_host_used_tokens=0`, host-pressure drops=0 and no backup/load-back/L3 writes; the Extent data file stayed preallocated and WAL stayed 28 bytes. Prompts were below the model's 256-token MAMBA chunk, and made no reusable radix material. Do not repeat this short-prompt shape.
- Server was gracefully stopped at 07:50 UTC; port 30126 closed, RTX 3090 returned to `1 MiB / 0%` with no compute process.

## 2. Falcon L3/MAMBA GPU correctness
- Falcon GPTQ-Marlin weight load, health and ordinary greedy GPU inference: **PASS**; repeated 8-token output IDs matched exactly. Not a restored-inference result.
- FULL+MAMBA D→H→L3→H→D, actual L1/L2 eviction, L3 matching/read/restore, GPU sidecar integrity, cancellation/failure cleanup, and post-restore inference: **NOT_RUN / BLOCKED on an effective checkpoint-aware lifecycle driver**. The one 120-request diagnostic is explicitly **NOT_ACCEPTANCE**: all requests were only 22–24 tokens vs `mamba_chunk_size=256`; cache and migration counters stayed zero.

- CPU finding: FULL load-back rejection came from exact production gate `(locked=0,reserved=0,restore=2,capacity=256,margin=2048)`. Expanded test fixture only, preserving 2048 margin. FULL L2/load-back and L3 write/prefetch/device restore unit tests PASS.
- CPU MAMBA component transfer-spec PASS. Real Extent KV+MAMBA group visibility/readback, missing-sidecar rejection, injected WAL pwrite failure (exception propagated; neither member visible), and crash/reopen metadata tests PASS. These do not certify GPU D↔H or recurrence.

## 3. Three-configuration concurrency comparison
- **NOT_RUN / BLOCKED:** GPU-only, GPU+Host, GPU+Host+Extent; no concurrency sweep, repeated steady-state runs, saturation point, or TTFT/TPOT/E2E distributions. No throughput/hit-rate comparison claimed.

## 4. Bottleneck evidence
- No current Falcon profiling evidence. Prefill/decode, Host and physical Disk bottlenecks and physical device I/O are **NOT_RUN**. Backend `pread` counts from CPU tests are not evidence of physical media reads; Linux page cache remains a confound. Earlier host device identity was QEMU HARDDISK, not confirmed physical NVMe.

## 5. Remaining / next action
- GPU use was authorized by the user's explicit confirmation and the GPU is now released. Do not restart CPU certification. Next implement/use a checkpoint-aware driver: tokenize with the frozen Falcon tokenizer; make fixed-prefix conversation turns with enough actual decode/prefill length to reach the model's 256-token MAMBA checkpoint boundary; request per-response `return_cached_tokens_details`; assert device eviction plus FULL/MAMBA D→H counters before revisiting; then require H→D success counters and exact greedy token equality. Only after that do isolated L3 writes, force both component evictions, require storage source hits and actual read/restore evidence, and verify post-restore output. Keep `--hicache-size 8` as the last known bounded setting (KV 94,879 tokens, 27 MAMBA host checkpoints); no more capacity tuning without evidence. Then validate cancellation/failure/reclaim and proceed to matched low-reuse/host-reuse/>L2 workload comparisons.
- **Stage acceptance: NOT ACCEPTED / BLOCKED**, not F1 PASS.
