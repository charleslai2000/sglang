# G1 gate — independent adversarial RE-REVIEW (reviewer-deep), 2026-09-12

Task `G1-GATE-INDEPENDENT-REREVIEW-20260912` (read-only; no artifact modified).
Target HEAD `4f41f5bab562b99562f30c67540eb05344d13637` (extent sources clean).

Reviewed digests:
```
31f742fd00f68a39af79bd36c1536a357f9e55dc75945c2af0a24f3a862d9a69  G1-CRASH-CONSISTENCY-CONTRACT-01.md
154033064b29a94941fd6e75d08cf616bfe6fb9afc31d9db98f6e21f3007abf9  G1-RESTART-REBUILD-NOVEL-MECHANISM-01.md
24f7078cd38a65f64a1572e07c939c5df2dbff1870b04cddd1d117b15a329e30  G1-RESTART-REBUILD-PATTERN-INTAKE-01.md
3a47cec9d850c7b3fddb84f871f3137c5c5e8a2fd93e0f5e5f89ab0cb8aa45c3  G1-GATE-REPAIR-RESPONSE-01.md
```

## VERDICT: BLOCKED (narrower than R0)

D-01 and D-03 genuinely CLOSED; default D-02 path closed. Two confirmed correctness
gaps remain in the repaired text (NEW-1 generation base for GC-recycled slots;
NEW-2 rotation-on-repair re-introduces W2), plus NEW-3 (D-05 fold vs incomplete
groups), NEW-4 (commit double-drop), and hygiene items NEW-5..NEW-10. Plus the
pre-existing authority blocks D1/D3/D7.

## Prior-defect closure

| id | status | residual |
|---|---|---|
| D-01 | **CLOSED** | §4.3:338-380; ordering line 367; W1 5a/5b re-derived sound for v1 `_read_pages:1068-1106`/`batch_get_v1:545-596` and v2 `:943-944`. |
| D-02 | **PARTIALLY-CLOSED** | default `ftruncate+fdatasync` correct; the allowed alternative "rotate to a fresh segment and abandon the partial tail" (§4.3:400, §5:449) leaves the torn frame in a non-active segment -> next restart classifies it interior -> FAIL CLOSED (NEW-2). |
| D-03 | **CLOSED (design)**; D7 open | §4.0:264-284; WAL frames self-describe epoch; re-mint coherent; minor: state epoch!=0 and replay uses frame epoch. |
| D-04 | CLOSED | §6:502-530 exclusive barrier + `max_seq<=checkpoint_lsn`. |
| D-05 | PARTIALLY-CLOSED | §5:466-471 correct direction; fold must exclude staged-but-discarded entries (NEW-3). |
| D-06 | CLOSED | §4.3:342-345, §11:630-644, §4.4:406-410; group_seq ownership ambiguous (NEW-9). |
| D-07 | CLOSED | §4.3 step 2 + D-07:384-388; NM-F-05/11 reworded. |
| D-08 | CLOSED (KV+sidecar) | §4.3:390-395, §9:596-598, NM-INV-08:206. |
| D-09 | CLOSED | §3.1:226-251; 13 PoolName values verified; `OTHER=255`. |
| D-10 | CLOSED | intake `status: blocked`; RP-RDB-036 row added; duplicate row NEW-7. |
| D-11 | CLOSED | §4.2 crc range `header[0..22)`. |
| A-01 | CLOSED | §0.1:64-97 verified vs HEAD; no residual worktree-only anchor (cosmetic off-by-one NEW-10). |
| A-02 | CLOSED | tightened ranges verified; `crash-matrix.md:8-9`. |
| W1..W4 | CLOSED | NM-F-15..19 are real kill/reopen or race oracles. |
| W5 | PARTIALLY-CLOSED | NM-F-20 real; enumeration mechanism still unspecified vs "named segments only". |

## NEW defects

| id | sev | issue | fix |
|---|---|---|---|
| NEW-1 | major | `plan` generation base for GC-victim slots: §7:556 still says `generation = _generations[slot] + passed.count(slot)`, but a GC victim not in `passed` yields `ref.gen = g` while step 2 sets `_generations[s]=g+1` and writes `DROP_SLOT(s,g+1)` -> entry born stale; next recovery fail-closed (§5:483). | base[s] = pending_gen[s] if s in pending_drops else _generations[s]; ref.gen = base[s] + passed.count(slot); DROP_SLOT.new_gen == pending_gen[s]. |
| NEW-2 | major | rotation-on-repair abandons a torn frame in a now-non-active segment -> next restart interior corruption -> FAIL CLOSED (re-introduces W2). | delete the rotate-and-abandon option, or `ftruncate(old_fd,last_valid_offset)+fdatasync(old_fd)` before publishing the new segment; or extend tolerance to a segment whose successor begins at expected base_lsn. |
| NEW-3 | moderate | D-05 fold may count `SET` for staged-but-discarded entries -> spurious fail-closed on a valid WAL ending in an incomplete group. | `SET` contributes to the fold only when its batch (and group) is COMPLETE, mirroring install. |
| NEW-4 | moderate | `commit` must not re-apply `passed` drops after step 2 (`extent_allocator.py:223-226`) else gen bumps twice -> misses + D-05 mismatch. | split commit into install-only (drops consumed by step 2). |
| NEW-5 | minor | `clear()` never stated to hold `_write_gate`; CLEAR interleaved with an in-flight group can diverge WAL order vs live RAM. | require clear()/detach/reset to acquire the writer sequencer, or document quiescent-only. |
| NEW-6 | minor/moderate | fence allows `O_CREAT|O_EXCL` (stale lock after crash blocks reopen). | pin `fcntl.flock LOCK_EX` (auto-release) + stale-lock handling. |
| NEW-7 | minor | duplicate RP-RDB-036 rows (intake:203 ADAPT vs :241 ADOPT). | keep one row. |
| NEW-8 | minor | NM-F-15 boundary wording describes the pre-repair interleaving. | reword to kill points at step 3/4/5 after the step-2 fsync. |
| NEW-9 | minor | group-id allocation owner ambiguous (novel §4:161 controller vs contract §9:584 backend). | pin one owner. |
| NEW-10 | minor | §0:33 anchor `:368-370` actual 369/371 (extent clean; off-by-one). | fix. |

## §0.2 determination

NOISE/unsubstantiated: the asserted `bytes`/`str` `_component_key` bug is not
present at HEAD (`PoolName.__str__` returns `.value`, `hicache_storage.py:84-85`;
`_storage_key` returns str). The "semicolon-separated multi-statement patch
block" has no file/anchor/oracle. Disposition: drop or convert to a tracked
implementation-phase item with a concrete oracle.

## Authority vs correctness

* Authority (unchanged): D1, D3, D7; plus non-blocking D2/D4/D6; missing run
  authority-manifest path; PENDING novel acceptance.
* Unresolved correctness (fix before freeze): NEW-1, NEW-2/D-02, NEW-3, NEW-4;
  NEW-5/NEW-6 should be pinned.
* Borderline asserted-while-open: D4 framed as the D-08 default (acceptable only
  if the orchestrator ratifies).
