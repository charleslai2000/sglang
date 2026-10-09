status: blocked

artifacts:
- Remote backup: `/root/sglang-3060-12g-hicache/.p0a-backup-P0-A-REMOTE-EXACT-20260911-R18`
- Executor transcript: `.memory/phase2-hicache-design/work/P0-A-REMOTE-EXACT-20260911-R18.transcript` (reported by child)

evidence:
- Exact local paths existed and were transferred to the authorized 3060 checkout.
- Local and remote hashes matched: ready `696ef7b89d8bec8f58c9c2751e24ca67b0540ac94571114ed953eacf7fc7ecfa`; budget `82b4be92355c48de2e990404c5cd57216a98bfa47f08dad11639d07ba569e1c0`; restore `c46abd775e2f115172c94ace9d1fc5e6bcc59921a27e4164a18ae430fc3ce607`.
- The pre-execution symbol gate incorrectly required `_t38c_node_context_index` in `test_ready_horizon_unit.py`, where that fixture symbol is not expected. The current local ready file has the relevant ready-horizon API symbols; `_t38c_node_context_index` is a budget-cache fixture symbol.
- No pytest was executed due to this over-broad orchestrator gate.

summary:
- R18 was blocked by an invalid verification condition, not by the code or remote environment.
- P0-A remains NOT_VERIFIED.

followups:
- Re-run with per-file symbol gates: ready file only requires typed result/status, `origin`, and `host_release`; budget file requires `_t38c_node_context_index`, `_t38c_request_contexts`, `_t38c_residency_lock`, `speculative_release_epoch`, and `trace_context`; restore file requires `origin` and `pop_host_alloc_failure`.

open_issues:
- Eight-test corrected-source result remains unknown.
