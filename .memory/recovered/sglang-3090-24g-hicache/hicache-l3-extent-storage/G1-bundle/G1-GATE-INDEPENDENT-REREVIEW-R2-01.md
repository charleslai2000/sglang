# G1 gate — FINAL independent adversarial re-review of R2 (reviewer-deep), 2026-09-12

Task `G1-GATE-INDEPENDENT-REREVIEW-R2-20260912` (read-only). HEAD
`4f41f5bab562b99562f30c67540eb05344d13637`; extent sources clean at HEAD.

Reviewed digests (self-computed; all match dispatch):
```
a729d540a50ada09a510b83f8a24477c7ef51192859b27f243aac640a6987455  G1-CRASH-CONSISTENCY-CONTRACT-01.md
31ae778040dbd495ccaca9d7cf6e76117bd646730a0e844288ec9a8fe399313d  G1-RESTART-REBUILD-NOVEL-MECHANISM-01.md
37b03a07a1dce9cecd75370a55e9840ac05577cbef077970e2bdf1f86a2d25ec  G1-RESTART-REBUILD-PATTERN-INTAKE-01.md
1ef35a39a667d2099fdc4b5e50dd040aef687e354ea59cd99e33f9786d6a39ea  G1-GATE-REPAIR-RESPONSE-01.md
```

## VERDICT: BLOCKED (narrow)

All eleven R1 findings genuinely addressed; NEW-10 rejection upheld (os.open:368,
os.ftruncate:370). R2 introduced NEW-11 (moderate, correctness) and NEW-12 (minor,
traceability). Design may not be frozen: correctness (NEW-11) + authority (D1/D3/D7).

## R1 closure

NEW-1 CLOSED — arithmetic re-derived for cases (i) destination-only, (ii) in `passed`
re-packed, (iii) GC victim not in `passed`: `ref.gen == _generations[extent_id]` after
`apply_drops` in all three. Disjointness is asserted but made provable by the
"as-if-dropped (cursor 0, slot empty)" rule; if overlap ever occurred the primary
formula double-counts. Unified fallback (§7:691-694) correct for count<=1.
Recommendation (non-blocking): mandate unified form unconditionally, or state the
as-if-dropped invariant as a hard precondition and delete the "passed branch only"
sentence (presently the prose contradicts the formula).
NEW-2..NEW-9, NEW-10 (rejection upheld), §0.2, W5 (R1 scope): CLOSED.

## NEW-11 — `wal_floor` / gate-release vs rotation: lost-write window (moderate; correctness)

§6:601-602 allows releasing `_write_gate` after step 4; §6:611 sets
`wal_floor = G_active+1`; writers then append `seq > L` to the still-active
`G_active` segment, which now lies below `wal_floor`. On crash before step-5
rotation: reopen computes range `[wal_floor, G_active] = [6,5]` -> empty; the
active gen5 (holding ACKed 101/102) is never opened -> ACKed writes lost
(violates NM-INV-03/04). Even the default exclusive-hold path yields the inverted
range; benign only because all gen5 records are <=L, and the design never states how
an empty/inverted range is handled. §6:624 ("not opened") and §6:629-630
("recovery replays them") are mutually contradictory.

Fix (choose one): (a) delete the gate-release optimization (hold through step 6);
(b) rotate (step 5) BEFORE releasing the gate; (c) define `wal_floor <= G_active`
conservatively and decouple the unlink rule from `max_seq<=L`. Also correct
§6:624/629-630.

## NEW-12 — R2 traceability not propagated (minor)

`NM-INV-19`/`NM-F-21` appear only at intake:488 (App. B claim); intake §8 has no
`NM-INV-19` row and never mentions `NM-F-21`; contract §12 oracle table lists
`NM-F-01..20` only while §4.3:467 references `NM-F-21` (defined only in novel §6:250).
This contradicts intake `every_invariant_has_pattern_and_test: true` (:446).
Fix: add the rows to intake §8 and contract §12; correct App. B.

## Minor residuals (not blockers alone)

* D1 vs §13:867-868 asserts a cold start for "pre-existing data file + no metadata",
  overlapping §5:513/581 OPEN DECISION D1 — reconcile.
* `_write_gate` does not exist at HEAD (only `self._lock`,
  `extent_file_backend.py:346`); declare it new and pin lock order
  `_write_gate -> _lock`.
* Orphan re-create `O_TRUNC`/offset-0 overwrite for a same-generation partial-header
  orphan must be stated (§6:614).
* `commit_install` failure atomicity (§4.3:404-407) unstated.
* `wal_active_gen` staleness post-rotation — recovery must not treat as corruption.
* Failed-group WAL truncation boundary must be after the last retained `DROP_SLOT`
  (§4.4:489-492).

## Falsifications attempted, no defect found

apply_drops vs in-flight readers (snapshot/verify `:1054-1100`,`:545-590`); reuse-clobber
with the split; gate-off shim double-drop; checkpoint resurrection; segment
referenced-but-missing (create->header fsync->dir fsync before `.wal.current`); torn frame
in a non-active segment (impossible).

## Freeze?

NO. NEW-11 is the only newly introduced correctness blocker; after its repair + NEW-12
cleanup the remaining blockers are authority-only (D1/D3/D7, novel acceptance,
authority-manifest pin — the latter now created by the orchestrator as `authority.yaml`;
the intake/novel `authority_manifest:` fields must be repointed in R3).
