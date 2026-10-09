# DEVOPS-20260908-REMOTE-EXPERIMENT-MACHINE-CLEANUP-FIX1

status: blocked
target: root@175.155.64.171:24052

## Summary

Executed the authorized disposable-scope cleanup. No sglang/launcher/vehicle/python-engine process was running before or after cleanup. The engine was not started.

## Commands and evidence

- Baseline: `/` had 13G available; `/data` had 122G available.
- Deleted only: `/root/evidence-*`, `/root/.cache/*`, `/mnt/l3/*`, `/tmp/t38c-*`, `/root/miniconda3/pkgs/*`, `/root/miniconda3/nsight-compute-2025.1.1`.
- Post-cleanup: `/` has 24G available (75%); `/data` remains 122G available (36%).
- Required paths passed: `/root/models/Qwen3.5-9B-w4a16`, `/root/miniconda3/envs/sglang-patch/bin/python`, `/root/sglang-b1-continuity`.
- Absolute Python check passed: `transformers import PASS 5.12.1`.
- No residuals remained in the authorized glob scopes immediately after deletion; SSH login recreated `/root/.cache/motd.legal-displayed`, which was removed in the same verification session.
- Final process check: `NONE`.

## Open issues

The required checkout/git verification is not satisfied: `/root/sglang-b1-continuity` is readable and source files were read successfully, but `git -C /root/sglang-b1-continuity rev-parse --is-inside-work-tree` reports `fatal: not a git repository` because no `.git` directory is present. No action was authorized to reconstruct or alter the checkout metadata.

## Followups

NEEDS_REASONING: clarify whether source readability alone satisfies the checkout acceptance criterion, or provide an authorized method/metadata location for Git verification.
