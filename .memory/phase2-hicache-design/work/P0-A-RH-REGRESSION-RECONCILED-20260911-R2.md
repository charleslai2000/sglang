status: blocked

artifacts:
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/P0-A-RH-REGRESSION-RECONCILED-20260911-R2.md`
- Authoritative source-reconcile report inspected: `P0-A-REMOTE-SOURCE-RECONCILE-20260911.md`
- Prior regression report inspected: `P0-A-RH-REGRESSION-20260911.md`

evidence:
- The dispatch required remote checkout `/root/sglang-3060-24g-hicache` on `root@i-1.gpushare.com:27460`.
- The pre-test SSH verification command was:
  ```text
  ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com 'set -eu; test -d /root/sglang-3060-24g-hicache; ...'
  ```
- This command did not reach the hash checks because `/root/sglang-3060-24g-hicache` is absent; the shell exited nonzero (the captured command stopped after `REMOTE_IDENTITY_AND_HASHES`).
- A read-only remote path probe confirmed:
  ```text
  MISSING /root/sglang-24g-hicache
  MISSING /root/sglang-3060-24g-hicache
  FOUND /root/sglang-3060-12g-hicache
  NVIDIA GeForce RTX 3060, 12288 MiB, 8.6
  Python 3.11.11
  ```
- The authoritative reconcile report states that the synchronized checkout is `/root/sglang-3060-12g-hicache`, not the exact dispatch target `/root/sglang-3060-24g-hicache`.
- Local SHA256 values were read-only inspected for the six target tests and four observed modified product files. They were not compared against the required 24g checkout because that checkout does not exist.
- No pytest test command was executed. No server, live OFF/ON trace, source/test mutation, Git mutation, gate mutation, or storage mutation was performed.

summary:
executed: read-only SSH remote path/GPU/interpreter probe; local target-file SHA256 listing
passed: 0 P0-A tests; remote target path precondition did not pass
failed: 0 test cases; required remote checkout/path verification failed
skipped: all focused RH tests, focused budget split tests, partition/restore-feed/host-allocability tests, and full `3090-dev/test_ready_horizon_unit.py`
not_executed: all requested pytest commands and any server/live trace

followups:
- Provide or authorize the exact remote checkout `/root/sglang-3060-24g-hicache` with the required synchronized source, then rerun the mandated hash gate before testing.
- Do not substitute `/root/sglang-3060-12g-hicache` for the requested 24g path without a fresh dispatch explicitly authorizing that target change.

open_issues:
- P0-A remains unverified and blocked at the remote-target/source-identity gate.
- The authoritative reconcile report and this dispatch disagree on the remote checkout path (`3060-12g` versus `3060-24g`); this invocation did not resolve that discrepancy.
- This report makes no claim about P0-B, P0-C, P1, production behavior, or final quality acceptance.
