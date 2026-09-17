# Gate harness fix audit — verdict (2026-09-17)

Independent reviewer audit of `3090-dev/gates/production/` (the 8 production gate
scripts) after the failed GPU campaign. Reviewer entry verdict: **ACCEPT**.
Orchestrator independently re-verified the two HIGH findings that matter.

## Per-fix verdict

| fix | verdict | enforcing mechanism |
|---|---|---|
| FIX1 host-pool sizing | **CLOSED** | `parse_host_pool()` parses the server's real allocation and hard-`invalidate`s before any measured request; `sizing_arithmetic()` is only a prediction record. Reproduces the historical failure: real `19904 tokens` console + `prompt=65000` -> `ok=False`. |
| FIX2 unique-prefix traffic + victim/reclaim proof | **CLOSED (code) / e2e UNVERIFIED** | real mechanism is per-index seeding (`random.Random(180000+i)`), NOT the `"mode":"unique_unrelated_prefixes"` string, which is inert metadata. Victim slot captured and fed to hard gates. |
| FIX4 strict flush | **CLOSED** | `flush_cache_strict` requires `status == 200` AND `"cache flushed"` in body; `HTTPError` captured with status; `invalidate` + return precedes the measured request. Old `flush_cache_executed` no longer exists (0 hits). |
| FIX5 victim/generation/relocation/refs evidence | **CLOSED (F1) / N-A by design (Gate A, F2)** | Gate A/F2 geometry deliberately avoids circular wrap. |

All 8 scripts `py_compile` clean; `test_gate_helpers.py` 42/42 OK. Deployed copies
under `/var/log/sglang/.../phase9-gates-final-20260916/*.py` are byte-identical to
the reviewed git bytes (`diff` SAME x8) — reviewed bytes == deployed bytes.

## HIGH findings

**HIGH-1 — unsupported README replay claim (evidence credibility).**
`README.md:245-247` asserts the harness "reproduces exactly this" on the preserved
campaign WAL (`wrap_observed = true`, `victim slot 1, 953 live refs / 64 MiB`).
**Orchestrator-verified:** no replay artifact exists. The only files containing
`wrap_observed` are the harness source itself and a synthetic unit-test string
(`test_gate_helpers.py:404`); no JSON anywhere under `/var/log/sglang` or
`3090-dev` contains `wrap_observed`/`reclaim_evidence`/`host_pool_actual`.
=> The claim must be backed by a replay artifact or downgraded to "expected".

**HIGH-2 — no post-fix end-to-end run exists.**
Every recorded result (`gate-a-result.json`, `gate-a-f1-result.json`, `f2-*`)
predates the deployed fix and still carries the old checks. No result JSON
carries `hc_size_gb` or the new keys. All four fixes are therefore verified
**statically + by CPU unit tests only**. No real gate invocation confirms the
sweep actually recycles a target slot, or that F1 reaches PASS/FAIL rather
than INVALID.

## Lower severity

* MEDIUM/LOW — `gate_a_content_integrity.py:391-395`: the Gate A s2 host-pool
  check has no `invalidate` (unlike s1 and both F2 sites), so a mis-sized s2
  yields FAIL(rc=1) instead of INVALID and the RECOVERED arm still executes.
  Cannot produce a false PASS. Classification inconsistency.
* LOW — `wrap_trigger.mode` and `sizing_check` are report-only; do not mistake
  them for the enforcing mechanism.

## What this changes for the main line

The harness is code-correct, but **"harness fixed, ready to rerun the campaign"
is NOT yet established**. Converting FIX1/FIX2/FIX4/FIX5 from static to runtime
evidence requires one real gate invocation. That is the smallest decisive step
on the main line and it needs the 3090 — so it runs after the DEV provider line
releases the GPU (main line has priority; provider may be interrupted).

Not yet done, deliberately (GPU contended / scope): real gate invocation at a
correct host-pool size; README claim correction; s2 invalidate decision.
