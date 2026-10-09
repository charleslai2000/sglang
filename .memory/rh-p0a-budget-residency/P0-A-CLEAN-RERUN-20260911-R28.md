status: done

artifacts:
- .memory/phase2-hicache-design/work/P0-A-CLEAN-RERUN-20260911-R28.md
- .memory/phase2-hicache-design/work/P0-A-CLEAN-RERUN-20260911-R28.transcript
- Remote backup: /root/sglang-3060-12g-hicache/p0a-backup-20260910T214626Z

evidence:
- Authorized target only: root@i-1.gpushare.com:27460, checkout /root/sglang-3060-12g-hicache.
- Local exact hashes matched required values; all required local symbols present.
- Remote backup hashes and post-transfer destination hashes matched each other and local hashes.
- All eight commands executed via argv/list-based generated Python runner, from the exact remote checkout, with required PYTHONPATH and executable.
- Results: focused ready 13 passed/61 deselected; focused budget 9 passed/15 deselected; full ready 74 passed; full budget 24 passed; restore feed 46 passed; partition 18 passed; prefetch gate 2 passed; dependency-free 19 passed. All exit 0.
- Transcript SHA256: 7dfe4b10f27d135fb8db169bb417c75513b038e61cea131f3ed13c49f9d19c61

summary:
- P0-A VERIFIED DONE: clean run passed all eight commands with consistent file provenance.

followups:
- None required by this invocation.

open_issues:
- None.
