# P0-A Remote Regression Rerun R7

- Task ID: `P0-A-REMOTE-RERUN-20260911-R7`
- Invocation: `ses-p0a-remote-rerun-r7-20260911`
- Epoch: `2026-09-11`
- Status: done

## Scope and authorization

Executed only on remote `root@i-1.gpushare.com:27460`, checkout
`/root/sglang-3060-12g-hicache`, Python
`/root/sglang-env-3060-4b/bin/python`, RTX 3060 experiment. No product edits,
3090/production, server/P1/P0-B, or local git edits were performed.

## Commands and evidence

Complete stdout/stderr is preserved at:
`/home/dev-codex/.local/share/opencode/tool-output/tool_08cb0b27e001uJfRV7XmrsWySE`

Probe command executed over SSH: `hostname; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader; python --version; python -m pytest --version`.
Evidence: hostname `I2aff9805ac001019d1`; GPU `NVIDIA GeForce RTX 3060, 12288 MiB`; Python `3.11.11`; pytest `9.1.1`.

Remote backup was created before transfer, exactly for the three authorized files,
without deletion: `.p0a-backup-20260911T025850+0800`.

The three authorized files were transferred with `scp`. Remote hashes after
transfer (none match the supplied expected local hashes):

```text
bd87b5b1165ae2e21d3c652f908af37b18ce3714fb6ff1d30b09221362f83e64  3090-dev/test_ready_horizon_unit.py
59da7cb4d706585e41cd5d9d81849601f8b91bb1f76135f1a635a0ba8eeb6ee0  3090-dev/test_prefetch_budget_split_unit.py
e725e9730ad4a22de8add159bf7e22cc0bf6b0c19614f240329d51b1c44b219d  3090-dev/test_hicache_restore_scheduler_feed.py
```

Expected hashes were respectively `696ef7b89d8bec8f58c9c2751e24ca67b0540ac94571114ed953eacf7fc7ecfa`,
`a5e1aa2367e68f472cf892ea3752c253269fcb67350340a6e0d26d2d31094bd7`, and
`c46abd775e2f115172c94ace9d1fc5e6bcc59921a27e4164a18ae430fc3ce607`.

All eight requested pytest commands executed with the required `PYTHONPATH` and
interpreter. Exit codes: selected ready `1`; selected split `1`; ready full `1`;
split full `1`; restore full `1`; partition `0`; gate skip `0`; dependency-free
contract `0`. The complete failure trace and test summaries are in the evidence
artifact above. Key summaries include selected-ready failures, split-full `4
passed, 20 failed`, restore-full `6 passed, 1 failed`, partition `18 passed`,
gate-skip `2 passed`, and contract `19 passed`.

## Summary

The authorized remote procedure executed successfully, so this invocation is
`done`. P0-A does **not** pass: not all commands passed, and the transferred
file hashes differ from the supplied expected hashes. Failures include missing
`host_release` constructor arguments, assertion mismatches, and test doubles
rejecting the `origin` keyword argument.

## Followups

- Orchestrator should treat P0-A as failed for this rerun and investigate the
  hash/source discrepancy and reported test failures in a separately authorized
  task.
- Preserve the remote timestamped backup; no rollback was authorized or needed.

## Open issues

- All three remote hashes differ from expected local SHA256 values.
- Five of eight commands exited nonzero; exact traces are in the complete output
  artifact.
