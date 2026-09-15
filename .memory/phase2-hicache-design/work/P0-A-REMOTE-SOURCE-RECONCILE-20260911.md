status: done

artifacts:
- `/root/sglang-3060-12g-hicache` updated with the complete local tracked working-tree source (8596 tracked paths), excluding `.git` by transport design.
- Two relevant untracked P0-A test files were additionally transferred:
  - `3090-dev/test_prefetch_gate_skip_regression.py`
  - `3090-dev/test_rh_contract_dependency_free.py`
- Remote backup: `/root/sglang-3060-12g-hicache-backups/P0-A-20260911T173752Z-overwritten-paths.tar.gz` (30,544,201 bytes; verified non-empty).
- This report: `.memory/phase2-hicache-design/work/P0-A-REMOTE-SOURCE-RECONCILE-20260911.md`

evidence:
- Authorized local source: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`; branch `3060-12g-qwen35-4b`; local HEAD `4f41f5bab562b99562f30c67540eb05344d13637`.
- Authorized remote: `root@i-1.gpushare.com:27460`, key `/home/dev-codex/.ssh/sglang_3060_ed25519`, target `/root/sglang-3060-12g-hicache`.
- Remote identity after transfer: hostname `I2aff9805ac001019d1`; GPU `NVIDIA GeForce RTX 3060`, 12288 MiB, compute capability 8.6, driver `550.144.03`; system Python `3.11.11`; `/root/sglang-env-3060-4b/bin/python` `3.11.11`.
- The remote target has no `.git` directory, so no remote revision was asserted. Source identity is established by the requested file hashes and the deterministic tracked-path transfer manifest.

procedure:
1. Probed the authorized SSH endpoint and target prerequisites; command exit `0`.
2. Created a timestamped remote tar backup of the existing tracked-path set before overwrite:
   ```text
   ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com 'set -eu; test -d /root/sglang-3060-12g-hicache; mkdir -p /root/sglang-3060-12g-hicache-backups; cd /root/sglang-3060-12g-hicache; tar --null --files-from=- --ignore-failed-read -czf /root/sglang-3060-12g-hicache-backups/P0-A-20260911T173752Z-overwritten-paths.tar.gz'
3. Transferred the complete tracked path set without `.git` using `git ls-files -z | tar --null -T - -cf - | ssh ... 'cd /root/sglang-3060-12g-hicache; tar -xf -'`; exit `0`.
4. Transferred the two additional relevant untracked P0-A test files with a second null-delimited tar stream; exit `0`.
5. Performed remote identity/hash verification only; no pytest command and no server launch was run; verification command exit `0`.

verification:
```text
4565319de153ea31f4e5c14d628d9a33203b34687e1383a4040d59734fdbc540  3090-dev/test_ready_horizon_unit.py
6acc94fa1b99174dcd954520a4f1217d58e948c7df6eb9dc7a9184fdc428ebcd  3090-dev/test_ready_horizon_partition.py
8f66e2cad45dbd5978cc721f6017ead10df89255a4d8272dda0d320064af537f  3090-dev/test_prefetch_budget_split_unit.py
e2887aecc92c0689c21a47e2bde587e10447212a950e9d381fdb37d14c9e52a1  3090-dev/test_hicache_restore_scheduler_feed.py
9d9e684c7af5096b690c0b2cc71f7410d44e2ada4e387a51cbd70681aaa082af  3090-dev/test_prefetch_gate_skip_regression.py
7dfd47a4219e0aee7cae322386dcba89a554d636cd8c361130d8985a45230799  3090-dev/test_rh_contract_dependency_free.py
a41e623a2d6e462720d6584af992da290ba54e0cb3766df794117b87678b656f  python/sglang/srt/managers/cache_controller.py
18c39a18aa7f8c672ce5a2373f9bcdd68058933ae8c2ec16a6b14e0b47488a0a  python/sglang/srt/managers/scheduler.py
954161ce4d32ef2d376a735ccc4315b4300e1874792e4dd11ef467dfc705aeda  python/sglang/srt/managers/scheduler_components/ready_horizon.py
35fae989ddfca0d457009f810e16d0e8a56f05416a5bfb1ec3a99e9a9937ffe4  python/sglang/srt/mem_cache/unified_radix_cache.py
```
- All six requested P0-A test-file hashes match local and remote.
- All four modified product-source files present in the local diff match local and remote. The local worktree contains four modified product-source files, not five; no fifth modified product-source path was observable, so no hash was invented.
- Remote postcondition: all ten verification paths are present (`ALL_PRESENT`).
- Local postcondition: branch and dirty worktree unchanged by the transfer; no local source, test, Git, review, storage, or environment file was modified.

summary:
- The authorized remote source identity blocker was reconciled successfully and reversibly.
- The remote now contains the local tracked source plus the two relevant untracked P0-A tests, with matching SHA256 evidence for the six target tests and all locally modified product-source paths.
- Only GPU/environment identity and file-manifest/hash verification were performed. Tests and server execution were explicitly not performed.

followups:
- P0-A regression execution may now use the synchronized remote checkout, under a fresh task/invocation and the existing P0-A test procedure.
- If the requirement truly expects five modified product-source files, identify the missing path before claiming five-file verification.

open_issues:
- Remote checkout remains non-Git (`.git` absent), so local commit identity cannot be verified through remote Git metadata.
- The dispatch says five modified product-source files, while the observed local diff has four; the four observed product files were verified and the discrepancy is recorded above.
