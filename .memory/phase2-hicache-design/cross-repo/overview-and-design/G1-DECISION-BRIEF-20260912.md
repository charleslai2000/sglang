# G1 restart-rebuild — authority decision brief (orchestrator)

Status: READY — design re-review returned ACCEPT-WITH-CONDITIONS ("mechanism safe to freeze").
The gate is now BLOCKED ON AUTHORITY ONLY. This brief is the decision set awaiting the user.
This brief does not approve the design and does not itself authorize code. It exists
so the user can rule on the authority decisions in one written pass when they return.

Final review: `G1-GATE-INDEPENDENT-REREVIEW-R3-01.md` (ACCEPT-WITH-CONDITIONS) after R3 repair of
NEW-11/NEW-12. The reviewer's independent ACKed-loss/resurrection interleaving search found none.
Four minor documentation alignments (N-1..N-4) are being applied; they do not change the mechanism.
Pins: `authority.yaml` (repinned to R3; to be repinned to R4 after the doc-align pass).

Revision note: bundle is at R3 (contract `1e643efc…`, novel `61e459c9…`, intake `78347155…`,
repair-response `9617ca1a…`); the R2 re-review closed NEW-1..NEW-10/§0.2/W5 and found NEW-11
(wal_floor/gate-release lost-write window) + NEW-12 (traceability), both repaired in R3 by
deleting the gate-release optimization and adding an explicit pending-rotation promotion rule.
The final R3 re-review is running. Pins live in `authority.yaml` (repinned to R3).

Gate state: BLOCKED. Two classes of block:
  (A) unresolved correctness in the design text (NEW-1..NEW-4 + hygiene) -> being
      repaired by the architect (R2) and then re-reviewed independently;
  (B) authority decisions this brief asks for (D1/D3/D7 blocking; D2/D4/D6 non-blocking).
No code will be written until (A) closes and (B) is ruled.

---

## Blocking decisions

### D1 — Allowed post-crash recovered prefix
What may legitimately be lost when the process crashes or power is lost.

| option | meaning | cost / consequence |
|---|---|---|
| (a) strict | every ACKed op is present after restart (needs data `fdatasync` per group + KV ACK only after `GROUP_COMMIT` + no pre-ACK eviction of ACKed entries) | highest durability; adds a data fsync per group; slows the write path; strongest `NM-INV-04` |
| (b) process-crash semantics (RECOMMENDED) | every WAL-durable ACKed op is present; power-loss data bytes best-effort | balances the restart oracle (`storage_cached_tokens >= input_token_len - 2*page_size`) against write cost; matches the E2E test's intent; power-loss data loss is bounded and detected by CRC/generation |
| (c) relaxed | recovered prefix = min over pools; sidecar shortfall tolerated | cheapest, but weakens the E2E oracle and the "no silent cold start" guarantee |

Recommendation: **(b)**. It is the only option that keeps the acceptance oracle
meaningful (L3 survives a real process restart) without paying a data fsync on every
group; power-loss byte loss stays detectable and fail-closed, not silent.

### D3 — Fail-closed vs salvage for a corrupt manifest/WAL

| option | meaning | consequence |
|---|---|---|
| (a) fail closed (RECOMMENDED) | corrupt manifest/WAL -> typed recovery error; no serving, no silent cold start | safest; a single corrupt frame can make L3 unusable until manual/next-run recovery; bounded because the torn-tail case is already tolerated |
| (b) salvage | truncate to last valid, discard corrupt suffix, cold-start if the manifest is lost | higher availability; risks resurrecting a partially-applied group or silently dropping the whole cache |
| (c) cold-start with a durable tombstone/signal | discard and record why | middle ground; needs an extra durable marker |

Recommendation: **(a)**, with the already-designed exception for a torn final frame of
the active segment (that is repaired, not failed). Corpus leaves this open
(`RDB-C10 best-efforts salvage — unresolved`), so this is genuinely user authority.

### D7 (NEW, from D-03) — Durable group-id identity / epoch
`operation.id` is a per-process counter reset at start (`cache_controller.py:259,283-284`),
so it cannot be a durable group id (would let run N+1's `GROUP_COMMIT` validate a
run-N leftover group; first op id=0 collides with "ungrouped").

| option | meaning | consequence |
|---|---|---|
| (a) per-run random 16-byte `namespace_epoch` + per-run `group_seq` from 1; persisted in the manifest; `(0,0)` = ungrouped (RECOMMENDED) | each run is opaque and durable; cross-run groups can never match | changes the hybrid KV+sidecar identity contract (adds epoch to group identity); opaque, no run-count leak |
| (b) persisted monotonic `run_seq` counter | simple, ordered | leaks run count; still needs a per-run group seq |
| (c) another identity contract | design rework | delays G1; the D-03 blocker returns |

Recommendation: **(a)**. It is the minimal identity change that closes W3/W4 and does
not require reworking the sidecar/KV group protocol.

NOTE: this is the one decision that changes a *product interface contract* (how a
KV+sidecar group is identified durably). It is why implementation is hard-blocked.

---

## Non-blocking decisions (recommend default, can proceed otherwise)

* **D2 — power-loss data durability:** (a) WAL `fdatasync` only; (b) also
  `fdatasync(data_fd)` per group. Recommendation: **(a)** now, with the code structured
  so (b) can be enabled later; upgrade only if D1(a) is chosen.
* **D4 — sidecar ACK semantics:** (a) sidecar ACKs at its own `BATCH_COMMIT`;
  (b) defer sidecar ACK to `GROUP_COMMIT`. Recommendation: **(b)**, which is already
  the D-08 visibility default; orchestrator ratifies it unless the user objects.
* **D6 — metadata IO accounting:** (a) separate metadata counters; (b) reuse existing
  `stats["opens"]/["preads"]`. Recommendation: **(a)** so the re-dispositioned unit
  oracles can assert `opens==1` without aliasing real data IO.

---

## Other authority items (no option set, just facts)

* ~~Missing run authority-manifest path~~ — RESOLVED by the orchestrator: created
  `.memory/phase2-hicache-design/authority.yaml` (orchestrator-owned run manifest) pinning
  the intake/novel/contract/repair digests, the corpus revision, and the D1/D2/D3/D4/D6/D7
  decision state. It records authority only; `implementation_authorized: false`. The intake
  and novel can only be repinned out of `status: blocked` after the design freeze + decisions.
  (Corpus pin checked: `pattern/`+`testing/` byte-identical between `1953397` and current
  storage HEAD `a6d97c12`; the G1 evidence base is unchanged.)
* Novel-mechanism declaration is `proposed`/`PENDING` — awaiting accept/reject.
  Classification: `NOVEL_MECHANISM` ("sidecar" absent from the corpus; no card covers
  an in-RAM index over a payload-only sparse extent file).

## What happens after the user rules

1. Architect R2 verified + independent re-review -> design frozen.
2. D1/D3/D7 (and D2/D4/D6) recorded as binding decisions in the contract.
3. G1 implementation (coder) -> orchestrator repin -> independent crash/reopen tester
   (real SIGKILL) -> reviewer; `TestHiCacheSpecExtentStorage` run before/after.
4. Then P3 (soak/restart/fallback).
