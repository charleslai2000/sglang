ENTRY: ACCEPT

status: blocked
task_id: OPS3060-RH-FINAL-ON-RESTART-20260909
orchestration_epoch: 20260909-rh-ab36
role: devops-executor

## Summary

The authorized RH-ON restart was attempted. The RH-OFF PID `107356` was
gracefully stopped after preflight confirmed it was the sole listener on
`127.0.0.1:30000`. The corrected RH-ON launch reached scheduler startup but
terminated with a runtime fatal before readiness; port `30000` is currently
unbound. No source, git, gate, or protected storage resource was modified.

## Commands and evidence

- Explicit SSH key: `/home/dev-codex/.ssh/sglang_3060_ed25519`, target
  `root@i-1.gpushare.com:27460`, BatchMode enabled.
- Preflight PID: `107356`; listener and `/health` were present, HTTP `200`.
- Preflight seed: `SGLANG_SEED=586963985`, `PYTHONHASHSEED=586963985`,
  `--random-seed 586963985`, `CUDA_VISIBLE_DEVICES=0`.
- Preflight PATH began `/root/sglang-env-3060-4b/bin`.
- Preflight protected storage baseline: `23051071488` bytes and `550080`
  regular files.
- Preflight runtime hashes matched the deployment record:
  `dc94b91af41786f5704901435ae4b846344717fb9399b2b16b898e6684fd30f8`,
  `c9e4dd7795c5df6dd9b1ed07f67dbd51ff65d301e1d60a15fad3d99259089a03`,
  `92f4404de4935be47bddf4df3d24388a39fe3fb53b44371defa67f7564f8a5b2`,
  `afa00fcc921ab78a46aa96fec5a1f3232eaaab3eaea9eec7bab53795b6a407d7`,
  `bac2bd08b91897e608a9cd1df215c4b278d03d3227587eac38654d441a185633`,
  `beace6d3c6a92dcfb424794267e9cb33a346cea04b2918bf9588d438fb78f20f`,
  `482ee59f938110a8bee228beede55d8d4aa8dffabbf706110345b8ff463d966f`.
- SIGTERM was sent only to PID `107356`; it exited within the bounded poll.
- Launch log: `/tmp/sglang3060-rh-final-on-restart-20260909.log`.
- RH-ON arguments supplied: `--enable-ready-horizon`,
  `--ready-horizon-frontier-n 8`,
  `--hicache-prefetch-speculative-fraction 0.6`; retained profile included
  max-running `1`, FP8 KV, graph settings, ratio `2.0`, `wait_complete`, and
  retry settings.
- Launch PID `110348` exited during initialization. Fatal log evidence:
  `AttributeError: 'Req' object has no attribute 'staging_eligible'` in
  `scheduler.py` `_ready_horizon_pass`.
- Final verification: no listener on `127.0.0.1:30000`; `/health` connection
  refused. Required readiness, RH runtime parse, and post-restart seed/hash
  verification therefore did not pass.

## Changed resources

- Only `/tmp/sglang3060-rh-final-on-restart-20260909.log` was created/updated.
- The known listener PID `107356` was stopped. The failed launch process exited.
- No unrelated GPU process was signalled; protected storage was not altered.

## Followups

- A fresh Task ID is required for any diagnosis, source change, rollback, or
  alternative runtime action.

## Open issues

- RH-ON service is not healthy and is not listening on port `30000`.
- Runtime fatal: `Req.staging_eligible` missing during ready-horizon startup.
