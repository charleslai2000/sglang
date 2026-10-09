# P0-B focused rerun R52

status: done
task_id: P0-B-FOCUSED-RERUN-20260911-R52
invocation: ses-p0b-focused-r52-20260911
epoch: 2026-09-11 (execution timestamp reported by host: 20260910T230735Z)

## Scope and target

Executed only against `root@i-1.gpushare.com:27460`, using key
`/home/dev-codex/.ssh/sglang_3060_ed25519`, checkout
`/root/sglang-3060-12g-hicache`. No product edits, dependency installation,
new harness, instrumentation, 3090 target, or production target was used.

## Preparation evidence

Environment command verified `/root/sglang-env-3060-4b/bin/python` imports
`orjson`, `msgspec`, `torch`, and `pytest`; output included
`imports=ok 2.6.0+cu124`.

Exact local SHA-256 hashes:

```text
0d2194e5b49efc636f4518a70d8ba283556fc0cd3540e7a7cb12d36abc985b82  test/registered/unit/managers/test_hicache_host_allocability.py
20a7c2e101ca99aac7866b6629faa3668cd56d93ffe534dfc11d2543d5a554af  3090-dev/test_drain_reentry.py
```

Backup directory (outside checkout):
`/root/P0-B-FOCUSED-RERUN-20260911-R52-backup-20260910T230735Z`.
Each destination was individually copied and hashed before transfer. Backup
hashes matched the pre-transfer remote hashes. Exact files were transferred
with `scp` to their absolute authorized destinations, then remote hashes
matched the local hashes above.

## Commands executed

The exact shell command used `ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519
-p 27460 root@i-1.gpushare.com`, `scp` with the same key/port, and these
argv-equivalent pytest invocations from the checkout:

```text
/root/sglang-env-3060-4b/bin/python -m pytest /root/sglang-3060-12g-hicache/test/registered/unit/managers/test_hicache_host_allocability.py -rA
/root/sglang-env-3060-4b/bin/python -m pytest /root/sglang-3060-12g-hicache/3090-dev/test_drain_reentry.py -rA
/root/sglang-env-3060-4b/bin/python -m pytest 3090-dev/test_hicache_restore.py -k 'host_alloc or alloc_failed or wait_capacity or restore' -rA
```

All three commands were run regardless of prior exit status. The selector
was non-empty and test execution was verified.

## Results

1. `test_hicache_host_allocability.py`: 9 collected, 9 passed, exit 0.
2. `test_drain_reentry.py`: 31 collected, 31 passed, exit 0.
3. `test_hicache_restore.py -k ...`: 92 collected, 92 passed, exit 0.

Overall exits: `0,0,0`. Final remote and backup hashes remained equal to the
local hashes. Full stdout/stderr, warnings, pass IDs, commands, and exits are
in the execution transcript at:
`/tmp/P0-B-FOCUSED-RERUN-20260911-R52-20260910T230735Z.transcript`.

## Classification

The approved focused suite executed successfully and produced evidence.
This is only a focused-suite classification; it is **not** a P0-B pass claim
and makes no live-chain claim.

followups: none
open_issues: none
