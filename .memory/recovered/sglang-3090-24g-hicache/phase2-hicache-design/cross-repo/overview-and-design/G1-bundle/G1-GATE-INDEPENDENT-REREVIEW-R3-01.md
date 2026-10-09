# G1 gate — FINAL independent adversarial re-review of R3 (reviewer-deep), 2026-09-12

Task `G1-GATE-INDEPENDENT-REREVIEW-R3-20260912` (read-only). HEAD
`4f41f5bab562b99562f30c67540eb05344d13637`; extent sources clean.

## VERDICT: ACCEPT-WITH-CONDITIONS — design mechanism SAFE TO FREEZE

Remaining implementation blockers are AUTHORITY-ONLY (D1/D3/D7 + novel acceptance).
Conditions: four minor documentation alignments N-1..N-4 (do not change the mechanism).

Reviewed digests (self-computed; match the authority.yaml pins):
```
1e643efc3f345a88c401e46c3bd0aa5272b9610b13ed230ccd35def1fdd5ef13  G1-CRASH-CONSISTENCY-CONTRACT-01.md
61e459c9cc3c40370b1f97cec99fda682788ae420baf4a163e2b388e13c4af95  G1-RESTART-REBUILD-NOVEL-MECHANISM-01.md
783471557be9bd2daef665995b3a9777a632f25be533f49d7b21e4028c12cebd  G1-RESTART-REBUILD-PATTERN-INTAKE-01.md
9617ca1a5e85e233747a55bf7ae4a6d7a48496d169a40588f3303c5b2265bdd2  G1-GATE-REPAIR-RESPONSE-01.md
```

## R2-finding closure

NEW-11 CLOSED — `_write_gate` held exclusively through step 6, released step 7
(contract:641-653,663-681); "release after step 4" deleted; unlink = strictly
< wal_floor (:675-679); range/promotion (:539-550, table :620-621).
NEW-12 CLOSED — contract §12 NM-F-21 row (:891) and §4.3 ref (:481) resolve;
intake §8 NM-INV-19 row (:358); App. B corrected (:500); all 19 invariants
enumerated, no missing/dup.
Hardening CLOSED — unified form mandated (contract:390-401,741-756, §8:765, §10:821);
precondition/prose deleted.
Minor residuals CLOSED — §13 D1-conditional (:936-941); `_write_gate` NEW + lock
order (:69-73, §11:841-850) with `self._lock` correctly at extent_file_backend.py:348
(R2's :346 was off by two); same-gen orphan O_TRUNC ( §5:557-566, table :622, §6:672);
commit_install all-or-nothing ( §4.3 step 6:415-420); wal_active_gen validation-only
(§3:230, §5 table:623, §6:707-709); failed-group truncation post-drop offset
(§4.4:504-513, §12:881) — with N-1 a novel-side doc nit.
R1 NEW-2..NEW-10/§0.2/W5 spot-checked: still CLOSED. NEW-10 :368/:370 confirmed.

## NEW-11 re-derivation (independent)

(a) unlink set = strictly below wal_floor, provably identical to {g: max_seq(g)<=L}
under the exclusive barrier. (b) pending-rotation window: G_active holds only
seq <= L; promotion replays only the empty new generation; nothing ACKed skipped;
wal_floor > G_active+1 fail closed; manifest-absent [G_active,G_active].
(c) unified generation form correct for all four cases incl. both passed and GC victim
(single bump); packed guard bounds passed.count <= 1.

## ACKed-loss / resurrection interleaving search: NONE FOUND

Attempted: crash at every step boundary (2/3/5/6), checkpoint crash before 4 / 4-5 /
5-6 / during 6, concurrent reader on reused slot, failed-group truncation crash,
D-07 durable-drop retained, cross-run incomplete group, clear vs BATCH/GROUP_COMMIT,
same-generation partial-header orphan, leftover below-floor segment,
`.wal.<wal_floor>` valid-header leftover. None loses an ACKed record; none resurrects a
dropped/cleared/never-committed entry.

## New defects (minor; doc/coherence)

| id | sev | issue | fix |
|---|---|---|---|
| N-1 | minor | novel §6:248 `NM-F-11` still says truncate to "pre-group offset" scoped "no slot reused"; doesn't mirror the contract's reuse-group post-drop boundary. | reword novel NM-F-11 to the contract rule (post-drop offset; pre_group_offset only when the group emitted no DROP_SLOT). |
| N-2 | minor | novel :21 / NM-R-11 :401 and intake :25 / §7:334 claim the authority manifest "still names the R2 digests". FALSE: authority.yaml pins R3 for all four. | reword to "repinned to R3; verify pins before gate movement." |
| N-3 | minor | authority.yaml `decisions:` omits D5 (contract §15:978 lists it open). | add D5 (PENDING, non-blocking). |
| N-4 | minor | authority.yaml `code_freeze_requires` names "R2 independent re-review". | change to R3. |

Plausible risks (pre-existing, not R3, not blockers): contract §11:849
"`fdatasync(WAL)` runs with neither held" is imprecise — write steps 2/5 hold
`_write_gate` and release only `_lock`; clarify to "outside `_lock`". Manifest-absent
with existing WAL segments / `.wal.current`-absent only partially specified — worth an
explicit fail-closed sentence (covered by D1/D3).

## Authority checks

intake `status: blocked`, `implementation_authorized: false`, `classification:
NOVEL_MECHANISM` — unchanged. Novel `status: proposed`, `acceptance_decision_id:
PENDING` — unchanged. `authority_manifest:` fields point to `.memory/phase2-hicache-design/authority.yaml`.

## FREEZE

Safe to freeze now, subject to N-1..N-4 (documentation only). Implementation blockers:
D1, D3, D7 + orchestrator acceptance of the novel declaration.
