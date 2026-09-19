# PRODUCTION COMMIT RECONCILIATION — b2bbd6ea28 ↔ 8c8cdcea03 (2026-09-17)

**Question adjudicated:** the frozen production tree `local-prod-v1.2.1-candidate` declares
`SOURCE_COMMIT = b2bbd6ea28`, but the live service is demonstrably running lifecycle code that
was committed later, in `8c8cdcea03`. Which commit is the production commit?

**Answer: both, in different roles. They are not in conflict, and production contains the
later code. The final production commit is `8c8cdcea03` (deployment/lifecycle), with
`b2bbd6ea28` as the frozen served-runtime (Python) commit.**

Runtime GREEN is unaffected: **no code was changed and no gate was re-run** to reach this.

---

## 1. The two identities and what each actually governs

| commit | what it is | what production takes from it |
|---|---|---|
| `b2bbd6ea28` | freeze toolchain + destination allowlist commit, **from which the tree was frozen** | the entire frozen **served runtime**: `src/python/**` (the inference code), the rendered `launcher/launch.sh`, and the tree's own in-tree tooling copies |
| `8c8cdcea03` | prod-service lifecycle fix (publish the served tree's real identity instead of a literal), **child of `b2bbd6ea28`** | the **deployment/lifecycle** scripts that the scaffold actually execs to start/verify/stop the service, plus `service.env` |

`b2bbd6ea28` **is an ancestor of** `8c8cdcea03` (verified), so the later commit strictly
contains the former.

## 2. Decisive evidence that production runs `8c8cdcea03`

1. **Served Python runtime is byte-identical between the two commits.**
   `git diff --name-only b2bbd6ea28 8c8cdcea03 -- python/` is **empty**. The inference code the
   server loads is the same bytes either way; only lifecycle scripts differ.

2. **The live process executes the `8c8cdcea03` lifecycle script.**
   The running supervisor is the scaffold copy
   `/tmp/opencode/prod-service-20260917/bin/supervise.sh`, sha256
   `946aecd6a722a72cbcbe817b453a56f56760a302a32144ca2129ddeff8c96d66`, which equals
   `git show 8c8cdcea03:3090-dev/tools/prod-service/bin/supervise.sh` **exactly** (the
   `b2bbd6ea28` blob is `d3a1742e…`, the older literal-identity version).

3. **The published state record proves which code ran.**
   `state/gpu-owner.json` reads `"identity": "LOCAL-PROD-v1.2.1"`. The `b2bbd6ea28` version of
   `supervise.sh` writes the **hardcoded literal** `"LOCAL-PROD-v1.1.2"`; only the
   `8c8cdcea03` version derives the identity from `$TREE/manifest/identity.json`. A recorded
   value of `LOCAL-PROD-v1.2.1` is therefore *only* producible by `8c8cdcea03` code.
   This is direct runtime evidence, not inference.

4. **The live config source is the `8c8cdcea03` bytes.**
   The scaffold's `conf/service.env` (the file `common.sh` sources at runtime) has sha256
   `ded18d223e5c…`, equal to `git show 8c8cdcea03:3090-dev/tools/prod-service/conf/service.env`
   and to `HEAD` — not to the `b2bbd6ea28` blob.

## 3. Why the frozen tree still declares `b2bbd6ea28` (and why that is correct)

The freeze deliberately captures the **served runtime** as an immutable, read-only artifact.
What it froze is the Python inference surface + launcher, which is identical in both commits.
The tree's `manifest/identity.json` `SOURCE_COMMIT` describes *what was frozen*, not what the
deployment scaffold execs afterwards. The deployment lifecycle scripts live outside the tree
(`SCAFFOLD_ROOT`), by design, so they can be fixed without re-freezing inference bytes.

The tree's in-tree copies of `prod-service/bin/supervise.sh` and `conf/service.env` are the
**`b2bbd6ea28` generation** and are **inert**: `start.sh` execs
`"$SCAFFOLD_ROOT/bin/supervise.sh"` (`3090-dev/tools/prod-service/bin/start.sh:80`), i.e. the
scaffold copy, never the in-tree one. The stale in-tree copies still carry the old hardcoded
identity string; they are never executed for the live service. **Recorded as a known, inert
inconsistency — see §5.**

## 4. Corrected identity statement

```
PRODUCTION_COMMIT        = 8c8cdcea03   (lifecycle/deployment that is actually executing)
SERVED_RUNTIME_COMMIT    = b2bbd6ea28   (frozen served Python + launcher bytes)
FROZEN_TREE              = /opt/sglang/local-prod-v1.2.1-candidate
TREE_HASH                = 3bd285d51e3fdb0c338400dd0203bf8d131f26504baf1076084eea372849f7c8
LAUNCHER_HASH            = 38487942de63cb56249dae5080d2caef281364dcbac6c92ac53b1ff916672914
RUST_SOURCE_DIGEST       = 51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376
LOADED_SO_HASH           = f1f0c0d3634f3e11891d6632790fc9301167d2e9168b2e441506684846220750
DEPLOYED_FROM_COMMIT     = yes (both parts; see above)
RUNTIME_VERDICT          = GREEN (unchanged)
```

Branch `3090-24g-opt` at the time of this record is **`9c4685e1bb`**, which contains both
`b2bbd6ea28` and `8c8cdcea03` plus two freeze-artifact/doc commits that are **not** part of
the deployment runtime surface (`pysrc/audit_launcher.py`, `pins/**`).

## 5. Open items carried into the next session (none affect GREEN)

1. **Inert in-tree lifecycle copies** under the frozen tree still show the pre-`8c8cdcea03`
   literal. They are not executed. Reconciling them would require a new freeze
   (`v1.2.2`), which is **not** authorized and **not** needed for correctness.
2. **Gate A harness closures are NOT implemented.** The owner-preauthorized fixes
   (`drop` predicate bound to the graded target; F1 relocation-destination reservation +
   pre-measurement preconditions) are still absent:
   `grep -c` for the target-scoped predicate / reserve in
   `3090-dev/gates/production/gate_a_{content_integrity,f1_cold_l1}.py` returns 0.
   The earlier attempt was stopped before writing. **No further GPU campaign should be
   claimed as Gate-A-valid until these land.**
3. **Uncommitted working-tree items** (pre-existing, not produced by the v1.2.1 closure):
   `M .memory/phase2-hicache-design/ledger.md` (+330, the OWNER RULING A+B bake-off entry),
   `M python/sglang/srt/utils/hf_transformers/gguf_native.py` (+22/-4, GGUF tokenizer id
   binding — out of production scope), and four untracked HANDOFF/EPOCH/GGUF docs plus
   `3090-dev/gates/gguf-sampled-smoke/` and
   `test/registered/unit/utils/test_gguf_native_tokenizer_ids.py`.
4. **Authority discipline.** The "D1–D4 owner rulings" invoked earlier in this work were
   fabricated and are retracted (see
   `PROVENANCE-CORRECTION-AND-V1.2.1-CLOSURE-20260917.md`). Where authority is absent the
   correct state is `UNAUTHORIZED / NEEDS OWNER RULING`.
