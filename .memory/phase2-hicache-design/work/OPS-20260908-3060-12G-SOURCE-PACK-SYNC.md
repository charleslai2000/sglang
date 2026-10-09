# OPS-20260908-3060-12G-SOURCE-PACK-SYNC

ENTRY: ACCEPT  
Task ID: OPS-20260908-3060-12G-SOURCE-PACK-SYNC  
Orchestration epoch: phase3-3060-4b-navigator/2026-09-08  
Role: devops-executor

## Status

done

## Summary

Created a tracked-files-only Git archive from the required local branch and commit,
uploaded it to the RTX3060 host, extracted it into the requested target without
`--delete` or broad deletion, and wrote commit/archive markers. No CUDA kernel was
compiled, no model was downloaded, and no service or benchmark was started.

## Baseline and archive

- Local repository: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- Branch: `3060-12g-qwen35-4b`
- HEAD: `d49214e59228a555dc9f878426928a8a628d8848`
- Local archive: `/tmp/sglang-3060-12g-qwen35-4b-d49214e5.tar`
- Archive size: `117862400` bytes
- Local SHA-256: `ab81942c043a48a38241f511946e036672deb8fa76ab19732416d92e9088b9b3`
- Archive entries: `9868`
- Archive prohibited-pattern check: zero matches for `.git`, `.memory`,
  `__pycache__`, `build`, `dist`, `logs`, `evidence`, credentials, `.pem`, or `.key`.

## Remote resources

- Host: `i-1.gpushare.com:27460`, user `root`
- Remote staged archive: `/tmp/sglang-3060-12g-qwen35-4b-d49214e5.tar`
- Remote target: `/root/sglang-3060-12g-hicache`
- Commit marker: `/root/sglang-3060-12g-hicache/.source-commit`
- Archive marker: `/root/sglang-3060-12g-hicache/.source-archive-sha256`
- `SETUP_ONLY.md`: present after extraction

## Commands and evidence

1. Ran `git archive --format=tar --prefix=... d49214e5...` with explicit exclusions
   for prohibited tracked paths, then `sha256sum` and `tar -tf` checks.
2. Uploaded with `scp -P 27460` to the remote `/tmp` staging path. The completed
   transfer was verified remotely with:
   `sha256sum /tmp/sglang-3060-12g-qwen35-4b-d49214e5.tar`
3. Extracted with `tar -xf ... -C /root/sglang-3060-12g-hicache
   --strip-components=1 --no-overwrite-dir`; no `--delete` was used.
4. Remote verification output:

   - `ARCHIVE_HASH=ab81942c043a48a38241f511946e036672deb8fa76ab19732416d92e9088b9b3`
   - `COMMIT=d49214e59228a555dc9f878426928a8a628d8848`
   - `MARKER=ab81942c043a48a38241f511946e036672deb8fa76ab19732416d92e9088b9b3`
   - `SETUP_ONLY=present`
   - Key files present: `README.md`, `python/sglang/__init__.py`,
     `python/sglang/srt/server_args.py`
   - Remote target file count after extraction: `8636`

## Open issues

The pre-existing remote target retained 53 prohibited-pattern files, including
`3090-dev/evidence/...` and Python `__pycache__` files. They were not removed because
the authorized procedure requires preserving existing content and forbids destructive
or broad deletion. The newly created archive contains none of those entries.

## Followups

None. Kernel compilation, installation, model download, service startup, and benchmark
execution remain intentionally unperformed.
