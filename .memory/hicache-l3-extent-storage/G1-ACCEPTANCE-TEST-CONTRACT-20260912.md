# G1 acceptance test contract (independent tester)

Owner: tester (independent). Authority: USER-RULING-20260912-G1 (D1=b / D3=a / D7=a; D2=a /
D4=b / D6=a; NM-EXTENT-RESTART-REBUILD-01 ACCEPTED). Frozen design R5-ruled.
`implementation_authorized: true`.

## What "done" means

1. `TestHiCacheSpecExtentStorage` transitions RED (pre-fix) -> GREEN (post-fix); the `file`
   variant stays GREEN.
2. The SIGKILL crash/reopen oracles NM-F-15..22 pass with a real killed subprocess (not an
   in-process `close()` mock).
3. The user's 8 acceptance points hold (contract §12.3). Specifically:
   1. pre-SIGKILL ACKed + GROUP_COMMIT durable -> present after restart;
   2. uncommitted / torn active tail -> no resurrection;
   3. committed corruption -> fail closed;
   4. stale generation -> no resurrection;
   5. KV + Mamba group -> all-or-nothing;
   6. new process uses a new namespace epoch, no seq collision with old runs;
   7. `TestHiCacheSpecExtentStorage` RED -> GREEN;
   8. RAM index restart-rebuild byte/identity equivalent.

NOTE: the crash oracle is SIGKILL/process-restart ONLY. Do NOT present it as power-loss
durability (D1(b); NM-INV-20).

## E2E oracle (acceptance point 7/8)

- Test: `test/registered/hicache/test_hicache_spec_file_storage.py::TestHiCacheSpecExtentStorage`
  (`:88-158`), inheriting `HiCacheSpecStorageMixin`.
- Oracle: `python/sglang/test/hicache_spec_storage_common.py:228-272`
  `_run_storage_loadback_keeps_spec_accept_length`: after a REAL process restart, assert
  `storage_cached_tokens >= input_token_len - 2*page_size` and
  `cached_details["storage_backend"] == "ExtentFileBackend"`.
- Pre-fix expectation: RED for the extent variant (extent L3 is cold after restart; the `file`
  variant re-scans the dir and is warm). Capture the RED output as baseline evidence.
- Post-fix expectation: GREEN.

## Crash/reopen oracles (acceptance points 1..6)

Run the real SIGKILL subprocess oracles (NM-F-15..22 in
`work/G1-bundle/G1-CRASH-CONSISTENCY-CONTRACT-01.md` §12 and the novel §6). Each must:
* launch a real process writing the extent metadata/WAL;
* SIGKILL it mid-flight at the specified step (after step-2 invalidation fsync; after the
  clobber; after the data-plan fsync; during install; during checkpoint/rotation);
* reopen in a NEW process and assert the expected recovery (present / absent / fail-closed).
Capture: the kill point, the on-disk artifact state, and the reopen verdict.

## GPU / resource protocol (binding)

- Acquire the GPU only via: `exec 9>/mnt/data/gpu/3090.lock; flock -w <N> 9`. Hold only for the
  run; STOP the server before releasing.
- `CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587` (RTX 3090 24G).
- Host-RAM gate: HiCache host pools need `available >= ~22 GiB`; check before launching and record
  it (measurements are non-stationary; a low-RAM launch is not a valid cell).
- Env: `source /mnt/data/neuron/envs/sglang-3090-opt/activate-sglang-3090.sh`; pytest is NOT
  installed (use `python -m unittest` / direct-file run).
- NEVER `pkill -f` (self-matches the shell cmdline — footgun). Kill explicit PIDs only; do not
  kill unrelated workloads (`verify_kb.py replay`).
- Generated logs/artifacts -> `/mnt/data/nerun-dev/g1/` (large bytes off the repo).

## Evidence required

- exact commands + exit status;
- RED baseline output and GREEN output for the E2E oracle;
- per-oracle: kill point, artifact state, reopen verdict;
- server logs kept read-only (do NOT overwrite `sglang-server-r112.log`/`-r124.log`).

## Stop / escalate

If a genuine crash-consistency violation is found, do NOT patch it; report reproduction + evidence
to the orchestrator. If the fix would require changing D1/D3/D7 semantics, STOP (authority gate).
