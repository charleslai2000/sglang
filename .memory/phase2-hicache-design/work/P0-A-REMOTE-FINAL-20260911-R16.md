status: blocked

artifacts:
- Remote backup: `/root/sglang-3060-12g-hicache/3090-dev/.p0a-remote-final-r16-backup-20260910T194635Z`
- Executor transcript: `.memory/phase2-hicache-design/work/P0-A-REMOTE-FINAL-20260911-R16.transcript` (reported by child)

evidence:
- Transfer procedure completed on authorized 3060 and backup contains exactly the three authorized test files.
- Remote hashes matched the hashes observed by that invocation: ready `bd87b5b1165ae2e21d3c652f908af37b18ce3714fb6ff1d30b09221362f83e64`, budget `59da7cb4d706585e41cd5d9d81849601f8b91bb1f76135f1a635a0ba8eeb6ee0`, restore `e725e9730ad4a22de8add159bf7e22cc0bf6b0c19614f240329d51b1c44b219d`.
- Symbol gate reported `_t38c_node_context_index` count `ready=0` and stopped before pytest.
- Current local files now visibly contain the intended R11/R12 symbols and hashes: ready `696ef7b89d8bec8f58c9c2751e24ca67b0540ac94571114ed953eacf7fc7ecfa`, budget `82b4be92355c48de2e990404c5cd57216a98bfa47f08dad11639d07ba569e1c0`, restore `c46abd775e2f115172c94ace9d1fc5e6bcc59921a27e4164a18ae430fc3ce607`.

summary:
- R16 correctly stopped at the symbol gate, but the reported remote hashes still correspond to a stale source set inconsistent with the current local files; no pytest result is valid.
- P0-A remains NOT_VERIFIED.

followups:
- Resolve child transfer provenance/path issue by using a direct orchestrator-controlled transfer or have executor print source-file hashes before scp and destination hashes after scp from the same absolute paths.
- Do not proceed to P0-B/P1.

open_issues:
- Why remote hashes differ from current local hashes despite claimed transfer remains unresolved.
