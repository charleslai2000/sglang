# Upstream Maintenance Discipline (upstream-maintenance)

> Source of authority: user adjudication 2026-09-04 (recorded in
> `.memory/phase2-hicache-design/ledger.md`). Applies to ALL agents working in
> this repo — the orchestrator dispatches and every specialist obeys it.
> Core split the user drew: **baseline advancement** and **problem-solving**
> are two different activities with two different upstream rules.

## 1. Two activities, two rules

- **Baseline advancement** (whole-branch version moves): governed by §2 — never
  against `main`.
- **Problem-solving** (fixing our OWN demonstrated defects): governed by §3 —
  borrowing from current `main` commits is EXPLICITLY allowed and encouraged.
- Do not conflate the two. Looking at `main` to solve our bug is not "chasing
  main"; merging/rebaseing the branch onto `main` is.

## 2. Baseline advancement — never main; stable release/tag only

- Do NOT `git merge upstream/main`, `git rebase upstream/main`, or
  forward-port the whole branch onto a newer `main`. `main` is mid-refactor of
  `UnifiedRadixCache` / HiCache L3 lifecycle (upstream #30145 ~2900-line
  strongly-coupled module, #31445 extra-pool prefetch abort, #22607
  consistency plan) — latest `main` is NOT "more stable".
- Whole-branch alignment may happen ONLY against a **stable release tag**, and
  only when a new one appears. Re-evaluation gate: a stable release >= v0.5.19
  whose commit postdates our fork point `b644771e07` (2026-08-28).
- **Grandfathered baseline**: our current base is `main` @ `b644771e07`
  (2026-08-28). That is a settled fact — do NOT try to retroactively re-anchor
  it to a release/tag. It stays the stable local development line, tagged
  (`hicache-3090-verified-*`).

## 3. Problem-solving — borrow from current main commits

When fixing a defect on our baseline, we MAY take the corresponding fix from
current `main` (cherry-pick whole, backport minimal hunk, or re-adapt to our
interfaces — our code has own adaptations, so verify interface drift).

- **Acceptance rule**: the borrowed fix must explain a CURRENT, concrete
  failure state we can demonstrate (reproducer first). It is never a "keep up
  with main" import.
- Classify the source commit:

| Class | Meaning | Action |
|---|---|---|
| A | independent correctness fix | cherry-pick whole commit |
| B | fix coupled to large refactor | backport minimal hunk only |
| C | pure refactor / metrics / feature | SKIP unless it directly gates a Gate |

- Per intake, in order: ① targeted reproducer ② regression suite ③ 3090 Gate.
- Example (current): `durable L3 write -> restore query -> kv_hit_pages=0`
  accepts only fixes touching hash/prefix key, storage index visibility,
  `batch_exists`, or the restore query — NOT large `ReqKvInfo` refactors or
  TreeCore rewrites. Candidate: #37503 (L3 storage prefetch lifecycle, a480f38).

## 4. Hygiene

- `.memory/` work data never enters git (repo-wide rule, ARTIFACTS).
- Push requires explicit user authorization (§50-forbidden / orchestrator).
- Commit messages must say whether the change is local-own vs upstream-borrowed
  (cite the source commit hash + upstream PR number).
