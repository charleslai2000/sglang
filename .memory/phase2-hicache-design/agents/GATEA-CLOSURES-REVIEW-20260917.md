# GATEA-CLOSURES-REVIEW-20260917 — adversarial review of the Gate-A/F1 closures

- terminal state: **DONE**
- verdict: **APPROVE-WITH-CONDITIONS**
- role: reviewer-deep (independent, adversarial; read-only)
- task_id: `GATEA-CLOSURES-REVIEW-20260917`
- repo: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt` (branch `3090-24g-opt`)
- reviewed artifact (implementer): `.memory/phase2-hicache-design/agents/GATEA-CLOSURES-IMPLEMENT-20260917.md`
- authority: dispatch `GATEA-CLOSURES-REVIEW-20260917`; read-only, CPU only, no git mutation.

## Task

Independently and adversarially validate the harness-only Gate-A/F1 closures under
`3090-dev/gates/production/`: (1) target-scoped drop predicate, (2) F1 relocation-destination
reserve preflight, (3) required pre-assertions return INVALID not FAIL and are proven without
re-warming the graded target. Every mandatory item A–I must end PROVEN-SOUND or a NAMED DEFECT.
The disqualifying failure class is **false-PASS** (a real graded-target durable page/ref loss
reported PASS); false-INVALID (conservative over-blocking) is acceptable if labeled.

## Scope

- Files under review: `3090-dev/gates/production/{gate_common.py, gate_a_content_integrity.py,
  gate_a_f1_cold_l1.py, f2_restart_recovery.py, test_gate_helpers.py, README.md}` and
  `wal_forensics.py` (claimed unchanged).
- Read-only: no edits, no fixes, no `git add/commit/checkout/stash`, no GPU, no server launch,
  no port binding, no live gate run. CPU tests + read-only offline replay only.
- `wal_forensics.py --mode membership` was run against a **`/tmp` copy** of the preserved r2
  store metadata; the live store (`/data/l3/...`) and `/var/log` were only read.

## Result

The closure is substantively correct and fail-closed on the cases I could reach: hashes match,
diff is confined, the decorative boolean is gone, CPU tests pass on the real functions, the F1
reserve preflight precedes the measured request, and the preserved r2 console independently
replays to `refs_intact=False -> INVALID`. I found **no confirmed, reachable false-PASS**.
I found one real permissiveness of ≤1% (inherited threshold reused for a predicate whose stated
standard is "ANY loss"), one falsified soundness claim (node-id ordering bound), one stale-evidence
call site (F1 cold window), and two latent fail-open traps. These are named below with conditions.

## Evidence

### A. Hashes / diff confinement — PROVEN-SOUND

Recomputed `sha256sum` in the working tree; all seven match the implementer's "after" hashes exactly:

```
e57e09806cbc92fa0a9c51ff30863022379ff8aa9147d6ddaa0c509e526ca542  gate_common.py
fa7121d8244b63399556d5dac249bcd5235bb63ffbf3f11f2a8865070e4d48d8  gate_a_content_integrity.py
8d95450e2e0ceffb556209a0cb09970a6826aa3d80196d2d433d5c4279c49cb7  gate_a_f1_cold_l1.py
4c51277db75f89d8ae6ae5487521c2ce24f42ffd425d34eeb8940fe2505c6017  f2_restart_recovery.py
30472c11127006788a9c248f46d2ed36803e9224fd4f548be086a9f0e9f217fe  test_gate_helpers.py
0687fa5d949238683df433ea859039b9a56c23e2f302865eb2647200773d09fe  README.md
f8ed297f10df81105747b2838ea412b94d9b6f5d54a9de69562bca608730f8bb  wal_forensics.py
```

`git show HEAD:3090-dev/gates/production/<f> | sha256sum` reproduces every claimed "before"
hash exactly (incl. `wal_forensics.py` = `f8ed…`, i.e. HEAD == working tree → byte-identical).
`git diff --stat` touches only the six listed harness files; `wal_forensics.py` unchanged.

### B. Reachability / ordering attack — PROVEN-SOUND (for persist/primer); see C3 for the cold window

Parsing → evidence → verdict ordering (drop parse first, membership second, verdict third):
- `gate_a_content_integrity.py:560` parses console window; `:566-570` offline membership; `:577-580`
  `refs_intact`; `:581-583` classify. `off` is fixed at `:288`, so `ev` is cumulative; membership is
  queried **after** the drops in the window, so `refs_intact` is a post-drop state, not a pre-drop one.
- `gate_a_f1_cold_l1.py:617-632` (persist) and `f2_restart_recovery.py:314-340`: same ordering
  (parse `ev` → membership snapshot → `refs_intact` → classify). Membership is a live replay taken
  after the drop lines were emitted.
- Consequence: within persist/primer the verdict cannot be stale *before* the drop it classifies.
  A cumulative-window drop is re-evaluated each iteration against the then-current membership; if the
  target refs are restored later, the final durable set is intact, which is the predicate's semantics.
- `refs_intact is None` (missing membership) routes to the node-id fallback; missing membership with
  drops present is not reachable because drops force a membership snapshot, and a snapshot failure
  returns `None` → `gate.invalidate` (`gate_a_content_integrity.py:566-569`, `f1:620-624`).
- **Exception (NAMED DEFECT C3):** the F1 *cold* window uses `cold_pre_target_still_indexed` — a
  snapshot taken at `f1:516-526`, **before** the measured cold request at `f1:534` — as `refs_intact`
  at `f1:546-549`. That verdict is stale relative to cold-window drops.

### C. Every `refs_intact is True => foreign` call site — PROVEN-SOUND modulo C1/C3

| site | `refs_intact` source | target set | loss routed to `foreign`? |
|---|---|---|---|
| `gate_a_content_integrity.py:577-583` | membership of A **and** B, post-drop | both targets | only if all targets ≥ threshold → no demonstrable durable loss |
| `gate_a_f1_cold_l1.py:627-632` | membership of the single chain, post-drop | chain | no |
| `gate_a_f1_cold_l1.py:782-783` (sweep) | `refs_intact=None` (bound-only) | chain | bound is unsound in general (D) |
| `gate_a_f1_cold_l1.py:546-549` (cold) | **pre-request** check (stale) | chain | yes for a cold-window drop → C3 |
| `f2_restart_recovery.py:336-340` | membership, post-drop | chain | no |

Empty/missing membership: `all(...)` over an empty `membership` dict returns `True`
(`gate_a_content_integrity.py:579`). Not reachable today (`_membership_both` always returns one entry
per target or `None`→invalidate), but it is a latent fail-open (see Defects, latent L1).

### D. Node-id bound soundness — NAMED DEFECT (soundness of the stated proof; not demonstrated reachable)

The rule `root_id > max_target_node_id ⇒ foreign` (`gate_common.py:916-921`) rests on the comment at
`gate_common.py:817-819`: "a parent is allocated before its children, so a subtree rooted at R contains
only node ids >= R". This invariant is **false** in the tree under test:
`python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:1126-1160` `_split_node` allocates
`new_node` (`:1129`, id assigned at `:132-133`, monotonically increasing) and then makes it the
**parent** of the pre-existing `child` (`:1148`), which keeps its **older, lower** id. Hence a subtree
rooted at `R` can contain a descendant `D` with `D.id < R.id`.

Consequence: a drop rooted at a split-created parent `R` with `R.id > max_target_node_id`, whose
subtree contains a lower-id target descendant `D`, would be classified `foreign`.

Reachability attempt (falsification): in F1 the bound is only consulted in `_sweep_to_wrap`
(`f1:782`, `refs_intact=None`). The single F1 chain's first token is `248045`
(`prompt_A.json`); all fillers/cold fillers are drawn from `random.randrange(1000,60000)`
(`f1:1008-1012`), so **no filler can descend into (split) the target path** — I found 0 of 160
sweep fillers sharing the target's first token. Splits among filler nodes only produce foreign
subtrees. Gate A's A/B prompts share a 3-token prefix, but that site computes `refs_intact`
(bound unused). F2 computes `refs_intact` too. I therefore could **not** construct a reachable
target-loss→`foreign` sequence. Residual risk is confined to the ≤1% tolerance (C1) and the
reopen condition below.

Reopen condition: any change that lets a filler/cold request share the target's leading token(s)
(target first token in `[1000,60000)`, changed `_filler_ids`, or prompt_builder change) makes the
bound misfire. The stated proof is invalid and must not be relied on as written.

### E. r2 replay adjudication — PROVEN-SOUND for the conclusion, NAMED DEFECT for the presented evidence

The implementer's prose says the r2 offline membership verdict is `refs_intact=False`, while the
pasted replay shows only `refs_intact=None` (`n_unknown=7, ok=false`) and `refs_intact=True`
(`n_foreign=7, ok=true`). I adjudicated by independently replaying the **preserved r2 store**
(metadata copied read-only to `/tmp`, `wal_forensics.py --mode membership`, prompt_A, window 64999):

```
n_present = 52672   n_absent = 12327   first_absent_index = 51200
min_present = ceil(0.99 * 64999) = 64350
refs_intact = 52672 >= 64350 = FALSE
scope_drop_events(..., refs_intact=False) -> n_target=7, ok=false, target_roots=[83..77]
```

So the **actual value is `False`**, and the NEW predicate's r2 verdict is **INVALID** — the
report's substantive interpretation is accurate. The pasted replay is incomplete/misleading (it
never shows the `False` case), and the stated reason ("drops happen before the targets are durable")
is contradicted by the console timeline (target `restore_backup` at 16:53:53–16:54:03 precedes the
drops at 16:54:15–18). The report's `None`/`True` cases are a sensitivity demonstration, not the
actual run. This is an evidence-presentation defect, not a wrong conclusion.

### F. F1 reserve — ordering PROVEN-SOUND; failure class = false-INVALID (labeled in artifact, not README)

Ordering: `pre_sweep_relocation_reserve` is computed at `f1:360` **before** `_sweep_to_wrap` at
`f1:382`; `assert_preconditions` for `fixed` runs at `f1:369-377` before the sweep; `post_reserve`
(on `pre_victim`, pre-reclaim state) at `f1:467-471` runs before the measured cold request at
`f1:534`. So the reserve is established before the measured reclaim/request. `--reloc-reserve-slots`
adds a bounded whole number of empty slots to `FILE_SIZE` (`f1:119-137`, default 2, tested
`test_gate_helpers.py:213-222`), and does not pass `reserve_bytes` (stays 0) — it raises geometry
headroom only.

Does passing imply a destination at the wrap moment? **No.** `relocation_headroom_bytes` is the max
single non-victim free tail, while the product's `plan_relocation` fits the aggregate free tail; the
sweep then packs trailing slots before it wraps. This can only produce **false-INVALID**
`victim_target_relocation_count_positive` event (`f1:432-436`), so a PASS requires a real relocation
that by construction had a destination; a refusal/recycle-only path invalidates at `f1:473-497`.
It **cannot** produce a false-PASS from the reserve itself. Class named: **false-INVALID**.
Condition C4: the reviewer-facing README does not label this conservatism (the implementer artifact
does, `GATEA-CLOSURES-IMPLEMENT-20260917.md:176-184`).

### G. Decorative boolean removal — PROVEN-SOUND

`grep -rn "persist_no_drop_without_backup" 3090-dev/gates/production` → **0 hits**. All remaining
drop checks are computed target-scoped verdicts: `gate_a_content_integrity.py:676`
(`scoped_ok["ok"]`), `gate_a_f1_cold_l1.py:685` (`scoped_ok["ok"]`), `f2:345`
(`scoped_ok["ok"]`); plus `pre/post/cold` scoped checks. No literal `True`. The old names/booleans in
Gate A/F1/F2 were replaced (verified in `git diff`).

### H. Test integrity — PROVEN-SOUND (with untested boundaries)

Raw rerun (from `3090-dev/gates/production`):
```
$ CUDA_VISIBLE_DEVICES="" python3 -m unittest test_gate_helpers
----------------------------------------------------------------------
Ran 60 tests in 2.094s
OK            (rc=0)
```
The new tests call the **real** functions (`gc.parse_drop_no_backup`, `gc.target_node_evidence`,
`gc.scope_drop_events`, `gc.drop_scope_ok`, `gc.relocation_reserve_check`, `gc.assert_preconditions`,
`f1._reclaim_evidence`, `f1.compute_geometry`), not a reimplementation. The OLD-fails/NEW-passes
demonstration (`test_gate_helpers.py:643-657`) uses the real NEW predicate plus a 2-line inline
reimplementation of the removed "any drop" predecessor on the same event stream — non-vacuous for
the predicate semantics, though the OLD branch is not the prior artifact. `test_no_evidence_is_fail_closed`,
`test_root_at_or_below_bound_is_unknown_fail_closed`, `test_refs_lost_is_target`,
`test_unparsed_without_refs_verdict_is_unknown`, and the assert-preconditions INVALID tests cover the
fail-closed boundary.

Untested failure modes on the fail-closed boundary: (i) stale `refs_intact` in the F1 cold window
(C3); (ii) the split-inverted node-id invariant (D); (iii) `all()` over empty membership (L1);
(iv) `drop_scope_ok` on raw unclassified rows (L2).

### I. Scope-leak check — PROVEN-SOUND (no harness-attributable product/service edits)

`git status --porcelain`:
```
 M .memory/phase2-hicache-design/ledger.md
 M 3090-dev/gates/production/README.md
 M 3090-dev/gates/production/f2_restart_recovery.py
 M 3090-dev/gates/production/gate_a_content_integrity.py
 M 3090-dev/gates/production/gate_a_f1_cold_l1.py
 M 3090-dev/gates/production/gate_common.py
 M 3090-dev/gates/production/test_gate_helpers.py
 M python/sglang/srt/utils/hf_transformers/gguf_native.py
?? .memory/phase2-hicache-design/HANDOFF-20260917-PRODUCTION-PRIORITY.md
?? .memory/phase2-hicache-design/agents/
?? .memory/phase2-hicache-design/work/EPOCH-RESUME-20260917-R2.md
?? .memory/phase2-hicache-design/work/GGUF-ARTIFACT-PROVENANCE-20260917.md
?? .memory/phase2-hicache-design/work/PROD-TAKEOVER-AUTHORITY-AND-GATE-A-20260917.md
?? 3090-dev/gates/gguf-sampled-smoke/
?? test/registered/unit/utils/test_gguf_native_tokenizer_ids.py
```
Attribution: the six `3090-dev/gates/production/*` entries are this change. `python/…/gguf_native.py`
(mtime 16:58, +22/-4) and the `gguf-sampled-smoke/` + `test/registered/…/test_gguf_native_tokenizer_ids.py`
are the separate GGUF workstream (mtime 15:29/17:26); the source ledger itself lists them as
pre-existing uncommitted worktree items (`.memory/phase2-hicache-design/ledger.md` tail). `ledger.md`
(mtime 20:27, +671) is memory/ledger bookkeeping, not a reviewed harness file. `find /opt/sglang
-newermt "2026-09-17 19:00"` → **0 files**; no service script or `/opt`/`/data` write is attributable
to this change.

## Defects / blockers

Ordered by severity to the fail-closed boundary.

**C1 — NEW permissiveness: `refs_intact` (and the stage membership checks) inherit
`--min-index-fraction 0.99`, so up to ~1% of the graded target's durable pages can be dropped and
still classified `foreign`/ok.** false-PASS class, bounded.
- Files: `gate_common.py:911-921` (`refs_intact=True ⇒ FOREIGN`); threshold sites
  `gate_a_content_integrity.py:546,577-580`, `gate_a_f1_cold_l1.py:318,600,629`, `f2:317,336`;
  defaults `gate_a_content_integrity.py:77`, `gate_a_f1_cold_l1.py:95`, `f2:69`.
- Failure sequence: target 65000 tokens → `min_present = ceil(0.99*64999) = 64350`. A
  `dropped without backup` that removes up to 649 target pages leaves `n_present ≥ 64350` →
  `refs_intact=True` → scope `foreign` → `persist_no_target_drop_without_backup=True` AND
  `persist_target_in_extent_index=True` → persist proceeds; no other check re-queries the target.
- Note: this is bounded and consistent with the gate's own pre-existing `persist_target_in_extent_index`
  acceptance, so it does not manufacture a pass beyond what the campaign already accepts. It is a
  **conflict with the authorized intent** ("ANY graded-target durable page/ref loss must FAIL CLOSED"),
  not a reachable >1% false-PASS.
- Clearing evidence: owner ruling that 0.99 is the intended target-identity tolerance for the drop
  predicate, **or** change `refs_intact` to require full presence (`n_present == window_len`) for the
  drop verdict and add a test asserting a one-page target loss → INVALID.

**C2 — NAMED DEFECT (soundness): the node-id ordering bound's proof is false; reachability not
demonstrated.**
- File: `gate_common.py:817-819` comment + `:916-921` classify; falsified by
  `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:1129-1160` (`_split_node` makes a
  higher-id new node the parent of an older lower-id child).
- Failure sequence (if a filler can touch the target path): target node `D` (id ≤ bound) is split by
  filler insertion → new parent `R` (id > bound) on the target path → a later D-leaf drop rooted at
  `R` is classified `foreign`, though its subtree contains `D`. I could not reach it with the current
  `_filler_ids` range (target first token 248045 ∉ [1000,60000)); the F1 sweep is the only
  bound-using site (`f1:782`).
- Backstop: post-sweep `post_target_in_index` (`f1:451-454`, `f1:485`) catches losses above the
  C1 tolerance.
- Clearing evidence: prove/guard filler-vs-target leading-token disjointness for every bound-using
  site, or remove the bound fallback (treat `refs_intact=None` as `unknown` → INVALID; conservative).

**C3 — NAMED DEFECT (stale evidence): F1 cold-window drop predicate uses a pre-request membership
verdict.** false-PASS *risk*; no demonstrated pass.
- File: `gate_a_f1_cold_l1.py:546-549` uses `cold_pre_target_still_indexed` from `:516-526`, taken
  **before** the measured cold request at `:534`; there is no post-cold membership snapshot
  (`:574` classifies with the post-sweep `post_mem`).
- Failure sequence: cold request drops a target-page copy (root ≤ bound) → `refs_intact=True` (stale)
  → `cold_window_no_target_drop_without_backup` passes even though a drop occurred. A **durable**
  loss still surfaces via the FIXED oracle (`cold_storage==0` → `gate.fail`, `f1:934-953`), and the
  UNFIXED oracle expects a destructive reclaim — hence risk, not confirmed false-PASS.
- Clearing evidence: use `refs_intact=None` for the cold window (bound/fail-closed) or add a
  post-cold membership re-check asserted before the fixed classification.

**C4 — Documentation gap (minor): the README does not label the F1 reserve preflight as
conservative (false-INVALID possible).**
- File: `README.md` reserve section (~`:240-247`, new). The artifact labels it; the reviewer-facing
  doc states only "INVALID in fixed mode". Clearing: add the max-single-tail-vs-aggregate caveat.

**C5 — Evidence-presentation defect (minor): the r2 replay block omits the actual
`refs_intact=False` case and states a contradicted timing rationale.**
- File: `GATEA-CLOSURES-IMPLEMENT-20260917.md:134-149`. Actual value independently recomputed as
  `False` (n_present 52672 < 64350) → INVALID; conclusion correct, presentation incomplete.
  Clearing: paste the `False` case and correct the "before durable" wording.

**Latent (not reachable as a false-PASS today; record only):**
- L1 `all()` over empty iterable defaults `True` at `gate_a_content_integrity.py:579`
  (unreachable: `_membership_both` returns per-target entries or the caller invalidates).
- L2 `drop_scope_ok()` on raw `dropped_scopes` (no `scope` key) returns `ok=True` with `n_total>0`
  (`gate_a_content_integrity.py:696`, `gate_a_f1_cold_l1.py:697`); both are in `ok=False`
  failure-return dicts, not consumed as a pass.
- L3 A/B length skew in Gate A: `min_present` is computed from `target_n=max(len)` while each
  target's `n_present` is compared to it (`gate_a_content_integrity.py:545-580`), a false-INVALID
  if the prompts are not equal-length (both were 65000 in r2).

## Remaining claims / exclusions

- No GPU, no live gate, no server launch, no product/runtime edit was performed or authorized.
- Not verified: product-side runtime behavior at GPU; the campaign's `fixed`/`unfixed` oracles
  under real host-pressure dynamics; whether the r2 store's final WAL is bit-identical to the
  state at the 16:54:18 drop moment (I replayed the preserved final store read-only; the missing
  12327 pages are far larger than any torn-tail truncation).
- Not independently audited: the pre-existing `wal_forensics` membership oracle beyond its use here
  (it reproduced a coherent 51200-page prefix + 1472-page tail; `sglang.__file__` resolved inside the
  tree under test).
- Owner decision left open (reported, not resolved): whether the ≤1% membership tolerance satisfies
  the "ANY loss" standard (C1) and whether the node-id bound fallback should be retained (C2).

## Verdict

**APPROVE-WITH-CONDITIONS.** No confirmed, reachable false-PASS was found; the closures meet the
authorized intent on the reachable cases, and the preserved r2 console replays to INVALID for the
target-scoped reason. The conditions below are required before treating the harness as the standing
go/no-go oracle:
1. C1 — owner ruling on the 0.99 threshold for the drop predicate (or tighten `refs_intact` to full
   presence). This is the only finding in the disqualifying (permissive) class; it is bounded to
   ≤1% and inherited, hence a condition, not a rejection.
2. C2 — resolve the falsified node-id invariant (prove disjointness or remove the bound fallback).
3. C3 — remove the stale `refs_intact` in the F1 cold window (use `None` or re-check post-cold).
4. C4/C5 — label the reserve conservatism in README and correct the r2 evidence block.

False-INVALID (conservative; campaign-blocking, verdict-safe): F1 reserve headroom
(single-tail vs aggregate) and reserve-consumed-at-wrap; A/B length skew (L3). No false-PASS of the
>1% kind was demonstrated.

## Terminal state: DONE
