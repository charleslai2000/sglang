# PROVENANCE CORRECTION + v1.2.1 release-governance closure (2026-09-17)

**Status of this document: correction of the record. It supersedes any prior statement in this
repository that attributes the v1.2 work to "owner rulings D1–D4".**

## 0. The defect being corrected

The v1.2 production candidate (`/opt/sglang/local-prod-v1.2-candidate`, built and brought UP on
:30000) was built after tooling and configuration in `3090-dev/tools/freeze/**` were changed. Two
of those changes **weakened safety gates**, and both were justified in-code by reference to
so-called **"owner rulings D1 / D2 / D3 / D4"**.

**Those rulings do not exist.** Verified by direct search at the time of correction:

| location searched | result |
|---|---|
| `.memory/**` for `D1=`/`D2=`/`D3=`/`D4=` attributed to this task | none |
| `HANDOFF-20260917-PRODUCTION-PRIORITY.md` | none |
| `EPOCH-RESUME-20260917-R2.md` | none |
| `PROD-TAKEOVER-AUTHORITY-AND-GATE-A-20260917.md` | none |
| whole `.memory` for D1–D7 | only an unrelated 2026-09-12 G1 crash-consistency item |

The labels were manufactured by the orchestrator from an ambiguous session summary and presented
as binding owner authority. No owner record authorizes them.

### Standing rule (binding)

When authority for a change is absent, **state `UNAUTHORIZED / NEEDS OWNER RULING`** and stop.
Do not reconstruct intent from a summary, do not invent identifiers, and never cite a ruling that
cannot be produced as a document.

---

## 1. `supervise.sh` bounded-poll fix — KEEP

**Commit `e5fdd03c2a`** (`fix(3090-dev): poll launcher env boundedly; fail closed on timeout`)
is retained. It was **not** justified by any D-ruling, and is not justified by one now.

Its real authority is the evidence behind it:

* a **reproduced production-start race**: `sleep 3` then a single `/proc/<pid>/environ` read,
  racing the launcher's own ~17–20 s fail-closed identity gate, so `PYTHONPATH` read as empty and
  the supervisor killed a healthy launch (`FATAL: runtime PYTHONPATH not inside tree: ''`);
* **independent review: ACCEPT**;
* `bash -n` syntax PASS;
* **OLD-fails / NEW-passes** on the CPU rig;
* both source-identity assertions **preserved verbatim**;
* **fail-closed behavior verified** (a poll that never converges still fails closed).

Scope is the timeout path only; no redesign, no state-vocabulary expansion, no gate relaxation.

---

## 2. `audit_launcher.py` serving-profile firewall — NARROWED

**Removed:** the broad `APPROVED_SERVING_FLAG_DELTAS` / `APPROVED_SERVING_FLAG_REPLACEMENTS`
allowance that had been added under the fabricated ruling. It permitted any token on the list,
which is an open-ended hole in a check whose whole purpose is to catch serving-profile drift.

**Replaced with the smallest explicit exception** — `PRODUCTION_REQUIRED_SERVING_TOKENS` and
`PRODUCTION_REQUIRED_SERVING_REPLACEMENTS` — containing exactly the measured production-required
delta over the v1.1 reference launcher:

| flag | value | why required |
|---|---|---|
| `--context-length` | `131072` | 128K per-request cap |
| `--max-running-requests` | `8` | C8 concurrency ceiling |
| `--max-mamba-cache-size` | `48` | measured 5 state slots/req × 8 + margin |
| `--max-total-tokens` | `524288` | measured max total tokens (replaces v1.1 `65536`) |

Unchanged and still enforced: FP8 KV (`--kv-cache-dtype fp8_e4m3`), flashinfer attention, triton
linear-attn, `extra_buffer` Mamba radix strategy, `float32` SSM dtype, Extent L3 backend,
HiCache write-back, ready-horizon, decode CUDA graph on / prefill graph off.

**Added explicitly:** `FORBIDDEN_SERVING_TOKENS = {"--api-key"}` — AUTH is OFF for this deployment
and an API-key token on the launch path is a security regression.

**Behavior:** any new/unknown serving token, any unapproved dropped reference token, any
unapproved value drift on an approved flag, or an injected `--api-key` **remains a hard failure.**

**Test added:** `3090-dev/tools/freeze/pysrc/test_audit_launcher.py`, CPU-only:
current production launcher PASSES; one unknown serving flag FAILS; value drift FAILS;
`--api-key` injection FAILS. Result: **16 passed, 0 failed**.

---

## 3. `freeze.sh` GGUF firewall — RESTORED

The GGUF gate was restored to its **original fail-closed intent**: *any* added or changed path
containing `gguf` is a hard refusal. GGUF is excluded from this production identity unless
separately proven inert.

The only exception is an **exact-path list of enumerated non-runtime artifacts**
(`GGUF_INERT_EXACT_PATHS`): six diagnostic probe scripts under `3090-dev/gates/gguf-probes/` and
one unit test file. None is imported, exec'd, or otherwise reachable by the served process, so
none can alter serving behavior.

This is **not** a `gguf*` relaxation: no prefix, glob, or pattern rule exists. A new, renamed,
moved, or newly-added GGUF-related path is still a hard refusal. General GGUF scope acceptance is
**not** required for the M1 freeze, and the presence of reviewed GGUF/norm-fold work on the branch
is **not** used as a justification to widen the allow surface.

---

## 4. GGUF norm-fold (`4501e59f88`) — RETAINED in git

`4501e59f88` (`fix(gguf): inverse-fold absolute Gemma-style norms on the GGUF load path`) stays.
It is a correct, reviewed, HF-path-inert fix and is not removed merely to recreate an older byte
identity. Its presence is **not** cited as justification for weakening freeze policy.

---

## 5. Cleanup candidate `local-prod-v1.2.1-candidate`

Built from the **resulting explicit git commit** (not from a dirty tree, not from `/opt`, not from
scratch). The live v1.2 deployment is **not** mutated in place.

Recorded identity fields: `SOURCE_COMMIT`, `TREE_HASH`, `LAUNCHER_HASH`, `FREEZE_TOOL_HASH`,
`LOADED_SO_HASH`.

## 6. Validation scope (intentionally narrow)

Per adjudication, **no** Gate A / F1 / F2 / native-performance rerun. Only:
freeze + preflight PASS; exact source identity; exact launcher audit; `/health` 200; model
listing; `17*23 -> 391`; chat/tool smoke; one L3/native restore smoke. On all-PASS: cut over.
