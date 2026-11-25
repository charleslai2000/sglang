# R3 Extent Reclaim Refusal — Recovery Findings

## Scope

This note records what is and is not established about the failed `candidate-identity-r3` C-8 run. It is a storage correctness investigation, not a completed C-8 benchmark result.

## Observed failure

The r3 server log reports: `reclaim relocation of 4 live refs refused: no destination capacity outside victims [0]`, followed by failed write-through pages and `kv_set_failed`. The configured Extent geometry was 512 slots × 64 MiB (32 GiB total). The refusal is fail-closed: live references were not overwritten when relocation could not reserve a safe destination.

## WAL and manifest limits

- The active WAL was CRC-verified as 11,297 frames: 4,494 SET, 4,494 BATCH_COMMIT, and 4,494 GROUP_COMMIT; no DROP_SLOT frame was present in that active segment.
- The manifest checkpoint LSN is 0 and does not contain the missing allocator cursor/slot-selection state.
- A standalone streaming scanner folded durable SET/group commits and found 861,674 installed entries at its reconstructed terminal point, four final slot-0 live refs ending at byte 100,352, a global maximum live-ref end of 67,106,816 bytes, and an inferred final `_next_slot` of 509. These terminal summaries are not historical allocator state and do not reconstruct the operation-time cursor, `_next_slot`, relocation plan, victim/drop set, or staged reservations at the failing operation (previously referred to as operation 3493).
- The production `replay_records` attempt did not complete within its bounded 600-second run. The standalone scanner is not a substitute for validating production replay semantics.

Therefore the exact r3 operation-time allocator geometry and root cause beyond the logged no-destination-capacity refusal remain unproven. Do not derive slot-0 historical high-water or cursor from the scanner's terminal live references, and do not weaken fail-closed relocation based on this incomplete reconstruction.

## Evidence classification

The regression `test_reclaim_refusal_when_wrapped_batch_exhausts_all_tail_space` uses constructed geometry; it is not an exact replay of r3. `TestExtentV1.test_circular_wrap_relocates_live_refs_or_fails_closed` additionally verifies unchanged WAL offset on refused wrap and readability of retained boundary keys across slots.

## C-8 run disposition

r2, r3, and later candidate-identity runs are incomplete diagnostic runs, not performance evidence. Preserve their manifests, WALs, logs, request hashes and lifecycle records. Extent data files from a fully stopped incomplete candidate can be regenerated and may be removed only after recording identity/hash and verifying no process or open handle uses them; do not remove data from completed or unrelated runs.
