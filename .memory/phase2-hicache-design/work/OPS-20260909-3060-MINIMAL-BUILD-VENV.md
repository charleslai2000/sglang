# OPS-20260909-3060-MINIMAL-BUILD-VENV

Status: blocked
Task ID: D3060-OPS-070
Role: devops-executor
Execution time: 2026-09-09 (Asia/Shanghai)

## Summary

The operation was admitted, but the required exact-source precondition failed. The
available extracted tree was not the reviewed commit, so configure/build/test commands
were not run.

## Authorized procedure and scope

- Remote target: `root@i-1.gpushare.com:27460`
- Allowed source candidates: `/root/sglang-3060-12g-qwen35-4b` or the existing exact
  extracted tree `/root/sglang-3060-12g-hicache`
- Venv: `/root/sglang-env-3060-4b`
- Reviewed commit required: `a76cce39723654cb93ee186b9c3fb570961d7794`
- Only `/hy-tmp` build/log/dependency data permitted remotely; no 3090 branch or local
  product files were touched.

## Commands and observed evidence

1. Connected with BatchMode and the authorized key:

   `ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -o BatchMode=yes -p 27460 root@i-1.gpushare.com ...`

   Observed host: `I2aff9805ac001019d1`.

2. Preflight state at `2026-09-09T00:30:01+08:00`:

   - Memory: 125 GiB total, 115 GiB available, no swap.
   - `/hy-tmp`: 50G total, 43G available (16% used).
   - `/root/sglang-3060-12g-qwen35-4b`: absent.
   - `/root/sglang-3060-12g-hicache`: present.
   - `/root/sglang-env-3060-4b`: present.
   - Venv tool versions printed: CMake `4.4.3`; Ninja `1.13.2`.

3. Exact-source marker check:

   `cat /hy-tmp/d3060-source-backup-20260909-002742/SOURCE_SYNC_MARKER.txt`

   Output:

   ```text
   commit=d49214e59228a555dc9f878426928a8a628d8848
   archive_sha256=ee70f72dddd6a56d55ee1b44ed676b32f83caab5f730110182a603dd08341dc1
   ```

   This commit does not equal the authorized reviewed commit
   `a76cce39723654cb93ee186b9c3fb570961d7794`.

4. A transient process observed during preflight was an unrelated prior command:

   `uv build --wheel -Cbuild-dir=build-OPS-20260908-3060-AOT-DEPS-REMOTE-056`

   It was no longer running on the subsequent inspection. No process was stopped or
   modified.

## Changed resources

None. No remote source, build, dependency, log, or product files were changed. The only
write was this authorized local report.

## Verification

- Exact reviewed source: **not verified; failed** due to marker mismatch.
- Venv CMake/Ninja availability: verified.
- Configure: not run.
- Ninja compile: not run.
- Import/loadability: not run.
- Artifact path/size/hash: none.

## Followups

Provide or restore an exact extracted/archive source whose marker resolves to reviewed
commit `a76cce39723654cb93ee186b9c3fb570961d7794`, then issue a fresh Task ID for the
rerun.

## Open issues

- The available `/root/sglang-3060-12g-hicache` source is unauthorized for this task by
  commit identity.
- The requested build remains pending; no alternative source or procedure was selected.
