# Source-authority consolidation — independent review result (2026-09-17)

Reviewer entry verdict: **ACCEPT**. All seven claims VERIFIED, no HIGH findings.
Reviewed identity: branch `3090-24g-opt`; `git diff --stat 27eb994b79 HEAD -- python/sglang test rust`
was empty, so the product-byte conclusions hold at both named and current HEAD.

| claim | verdict | decisive evidence |
|---|---|---|
| C1 tree == frozen v1.1.2 with exactly one seam diff | **VERIFIED — VALID FOR `b26bd39ece` / `928604a3f0305a80` ONLY** | filtered `diff -rq` returns exactly one line (the seam file); independent compare over 6167 deploy files: zero other diffs; `_version.py` and all 3 `.so` identical |
| C2 Option-C and native coexist | **VERIFIED** | `_append_relocation_commit`=2, `plan_relocation`=1, `_NATIVE_WRITE_ENV`=2, checkpoint watermark=2 |
| C3 no silent revert to regressed lineage | **VERIFIED** | HEAD rotation site carries the 3-line watermark block; archived regressed copy has count 1 |
| C4 Option-C bytes == GPU-exercised bytes | **VERIFIED — VALID FOR `63f7eff612` / `b26bd39ece` ONLY** | sha256 match for all 3 files vs deploy tree; corroborated by the frozen tree's own `TREE-SHA256.txt` |
| C5 l3wal crate real and buildable | **VERIFIED** | crate dir identical to Gate-B scratch; offline `cargo build --release --locked -p l3-native-wal` exit 0; native oracles ran real Rust |
| C6 no unreviewed commit leaked | **VERIFIED** | `a207b567fe` is an ancestor of the chain BASE, not introduced; only the 24 intended prod files touched |
| C7 test evidence real | **VERIFIED** | arm A 115 OK; arm B 115 with exactly the 4 documented mock-shape errors (they monkeypatch arm-A-only seams) |

Falsification-strength bonus (C1): applying the archived seam patch to a copy of the
deploy `extent_file_backend.py` reproduces HEAD's hash `928604a3f0305a80…` exactly.

## MEDIUM findings — both orchestrator-reproduced

**M1 — native write path writes its build cache INTO the repo.**
`extent_file_backend.py:178` hardcodes `cache_dir=workspace.parent / "rust-cache"`,
i.e. `<repo>/rust-cache`. Reproduced: `du -sh rust-cache` = **67M**, untracked
(now gitignored at `.gitignore:236`). Every native-arm run recreates it.
This violates the host rule that build output belongs on the large volume, not the
source workspace. Non-production-reachable: the frozen deploy tree is read-only, has
no `l3wal` workspace member, and sets no `SGLANG_L3_NATIVE_WRITE_PATH`, so the native
arm loads only from a dev tree.

**M2 — the Gate-B binary is not byte-reproducible from the repo.**
Repo `rust/Cargo.toml` `[profile.release]` is `lto=true, strip=true, codegen-units=1`
and is PRE-EXISTING repo config; the Gate-B scratch workspace used
`lto=false, strip=false, codegen-units=16`. Rebuilding from the consolidated tree
therefore yields a different binary (578,264 B vs Gate-B 4,320,976 B).
Sources are byte-identical and all oracle tests pass, so this is **not** a correctness
blocker.

## Owner correction to M2 (supersedes the reviewer's and the orchestrator's framing)

The earlier statement "repo profile is stronger, so Gate-B PASS is conservative" was an
**unmeasured inference and is retracted.** `lto=true / codegen-units=1` is plausibly
faster but can also change code generation, thread behaviour, and FFI timing. The old
Gate-B performance conclusion belongs **strictly to that scratch binary** and nothing
about it transfers without measurement.

Ruling:
* Do NOT attempt to reproduce the old 578 KB / 4.3 MB binary. Keep the old Gate-B
  artifact plus its build flags **as historical evidence only**.
* Production uses the repo's release profile.

## Planning consequence

* Correctness/durability conclusions transfer: sources are byte-identical and the
  oracles are green at HEAD.
* M2 is a **measurement-provenance** note, not its own gate.
* When the native seam is finally enabled in the production candidate, ONE 128K
  Gate-B cell MUST be run with **the actual production commit and the actual repo
  build profile** — so the shipped binary is the measured binary. This is added to the
  existing single final campaign, not a new perf layer:

      provider-stop
      -> final campaign = Gate A/F1/F2 + native 128K Gate-B cell + canary
      -> provider-start

  Existing hard gates unchanged: aggregate/L1-hot >= 0.85; plateau/L1-hot >= 0.85;
  stalls ~ 0; inter-forward gap near the healthy value.
* M1 must be fixed (see below); it is a source-hygiene fix folded into the current
  cleanup closeout, not a new workstream.

## M1 fix (owner-authorized)

The native build cache must NOT be written to `<repo>/rust-cache`
(`extent_file_backend.py` currently hardcodes `cache_dir=workspace.parent / "rust-cache"`).
Move it outside the source tree, e.g. `/data/cache/sglang-rust/`, or honor an explicit
`CARGO_TARGET_DIR`/env override.

RESOLVED (owner ruling): the fix was reduced to the minimal one-line change —
`cache_dir=workspace.parent / "rust-cache"` -> `cache_dir=None` — reusing the existing
`SGLANG_CACHE_DIR -> loader._cache_root()` mechanism. The interim
`SGLANG_L3_NATIVE_WRITE_CACHE_DIR` env var was removed (it was a redundant second
configuration layer).

Because this deliberately changes the bytes of that one file, the C1/C4 byte-identity
results are **VALID FOR `b26bd39ece` / `928604a3f0305a80` ONLY**. New HEAD is the new
production identity and must be recorded by its own hash. Do NOT claim it is
byte-identical to the old Gate-B bytes.

## Baseline (supersedes all earlier authority statements)

`/opt/sglang/local-prod-*` is **historical provenance only**, NOT a source authority.
The current development baseline is:

    3090-24g-opt@<HEAD>
