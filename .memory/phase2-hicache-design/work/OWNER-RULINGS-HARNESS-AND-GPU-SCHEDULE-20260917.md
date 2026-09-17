# Owner rulings — harness evidence + GPU scheduling (2026-09-17)

Applied without opening new workstreams. These are binding.

## R1 — HIGH-1 accepted: unsupported README claim
`3090-dev/gates/production/README.md` claimed the harness "reproduces exactly this"
on the preserved campaign WAL (`wrap_observed = true`, `victim slot 1, 953 live refs
/ 64 MiB`, refusal headroom `49,201,152 B`).

Orchestrator-verified: false as a claim of a produced artifact.
* `gateA-F1/store-snapshot-post-sweep-f1-20260917T082421Z-302181` **does** exist,
  and `wal-membership-post-sweep.json` **is** real — but it contains none of
  `wrap_observed`, `953`, `live_refs`, or the headroom bytes.
* The only occurrences of `wrap_observed` are the harness source itself and a
  synthetic unit-test string.

ACTION: downgrade the wording to `expected behavior; covered by synthetic
regression`. Do NOT fabricate an artifact to preserve the stronger wording.

## R2 — HIGH-2 accepted: no separate GPU validation job
Do NOT run a GPU job merely to validate the repaired harness.
The next real final Gate A/F1/F2 campaign **is** the post-fix harness E2E
validation. A result is valid only if it carries the repaired-harness evidence:
* host-pool sizing/preflight (`hc_size_gb` or equivalent)
* deterministic unique-prefix identity/seed evidence
* strict flush success
* F1 victim/generation/relocation evidence where applicable
Missing new fields => INVALID / wrong harness identity.

## R3 — FIX2 dead field
`"mode":"unique_unrelated_prefixes"` is inert metadata (never read) and must not
remain as misleading evidence. Remove it. Document the ACTUAL mechanism:
per-request deterministic RNG seed `random.Random(180000 + i)`.
Do not add another configuration layer.

## R4 — GPU scheduling
* DEV provider (port 30000, M1, L3 OFF) may run and stay available while CPU-side
  production reconciliation continues.
* Do NOT interrupt it for a harness-only validation.
* Final sequence once the real production candidate is ready:
      provider-stop
      -> ONE final Gate A/F1/F2 campaign
      -> short canary
      -> provider-start
  This single campaign validates both product correctness and repaired-harness
  runtime behavior. No additional GPU validation layer.

## Pending mechanical edits (from R1, R3)
Target files (both under `3090-dev/gates/production/`):
* `README.md`                       — downgrade the unsupported claim (R1), document
                                      the real seeding mechanism (R3)
* `gate_a_f1_cold_l1.py:143`        — remove the dead `"mode"` field (R3)
Serialized behind the active cleanup writer (single branch writer) to avoid a
concurrent git index operation on `3090-24g-opt`.
