# P0-A Remote Transfer R8

- Task ID: `P0-A-REMOTE-TRANSFER-20260911-R8`
- Invocation: `ses-p0a-transfer-r8-20260911`
- Epoch: `2026-09-11`
- Status: blocked

## Scope

Authorized endpoint only: `root@i-1.gpushare.com:27460`, checkout
`/root/sglang-3060-12g-hicache`, key
`/home/dev-codex/.ssh/sglang_3060_ed25519`. No 3090/production, product files,
or local Git changes were touched.

## Procedure and evidence

The prior R7 report and transcript were read before changes. A remote stat/read/hash
precheck was performed. The three remote files initially had hashes:

```text
bd87b5b1165ae2e21d3c652f908af37b18ce3714fb6ff1d30b09221362f83e64  test_ready_horizon_unit.py
59da7cb4d706585e41cd5d9d81849601f8b91bb1f76135f1a635a0ba8eeb6ee0  test_prefetch_budget_split_unit.py
```

The local hashes were confirmed as the three supplied expected values. A new
reversible remote backup was created before overwrite:

```text
/root/sglang-3060-12g-hicache-backups/P0-A-R8-20260910T190312Z-three-tests.tar.gz
size: 16897 bytes
```

The three files were transferred with `scp` to the explicit absolute remote
directory `/root/sglang-3060-12g-hicache/3090-dev/`. Immediate remote hashes
then exactly matched all three expected values:

```text
696ef7b89d8bec8f58c9c2751e24ca67b0540ac94571114ed953eacf7fc7ecfa  3090-dev/test_ready_horizon_unit.py
c46abd775e2f115172c94ace9d1fc5e6bcc59921a27e4164a18ae430fc3ce607  3090-dev/test_hicache_restore_scheduler_feed.py
```

## Blocking issue

Pytest was not run. The available R7 durable report and complete output preserve
test headings and results but do not preserve the eight exact command lines or
selectors. Running reconstructed commands would violate the instruction to run
the exact R7 procedure, so execution stopped after the successful hash gate.

## Summary

Transfer diagnosis and repair succeeded; all three hashes are exact and backup
is reversible. P0-A remains unverified because the exact eight R7 commands were
not available as executable procedure text.

## Artifacts

- This report: `.memory/phase2-hicache-design/work/P0-A-REMOTE-TRANSFER-20260911-R8.md`
- R7 report: `.memory/phase2-hicache-design/work/P0-A-REMOTE-RERUN-20260911-R7.md`
- New remote backup listed above.

## Followups

- Dispatch a fresh invocation containing the eight exact R7 command lines (or
  restore them from the original dispatch transcript), then run them only after
  repeating the hash gate if required by that procedure.

## Open issues

- Exact R7 pytest command lines/selectors are absent from the available durable
  report/transcript artifact; no test result can be claimed.
