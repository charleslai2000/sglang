# M1 closeout — native Rust cache out of the repo + source/binary identity chain

Baseline: `3090-24g-opt@792d89a058` (final M1 form).

Owner ruling applied: reduce M1 to the minimal one-line change. The interim
`SGLANG_L3_NATIVE_WRITE_CACHE_DIR` env var was a redundant second configuration layer
and was removed.

## Final change (one line)

`python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`
```
-                cache_dir=workspace.parent / "rust-cache",
+                # None defers to loader._cache_root() -> SGLANG_CACHE_DIR/rust_extensions,
+                # i.e. outside the source tree. Never default inside the repo.
+                cache_dir=None,
```
New file hash: `a5c99fd1cc32b645…` (HEAD `792d89a058`).

## Owner's hard gate
Prevent "new source HEAD + stale `.so` from an external cache" — i.e. source
identity and executed binary identity must not diverge. Four checks required.

## Result — all four PASS

**Check 1 — no cache in the repo.**
Pre-M1 stale `rust-cache/` (67M, mtime 12:06) predated the M1 commit (12:54), so it
was residue, not a regression. Removed. Then exercised the native load path
(`test_l3_native_wal_equivalence.py`, arm B) and re-asserted:
`<repo>/rust-cache` does **not** reappear.

**Check 2 — actual load path is outside the repo.**
```
workspace      : <repo>/rust
cache override : (unset -> SGLANG_CACHE_DIR/rust_extensions)
loaded .so     : /home/ubuntu/.cache/sglang/rust_extensions/artifacts/l3-native-wal/
                 51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376/
                 _l3wal.cpython-312-x86_64-linux-gnu.so
```
Loads from `~/.cache/sglang/...`, i.e. outside the source tree.

**Check 3 — cache key binds crate source + toolchain + build env (not a fixed dir).**
`sglang/srt/rust_extensions/loader.py` computes:
* `source_digest` = SHA256 over the crate's source files
* `fingerprint` = digest of `{fingerprint_version, package, library, python_module,
  source_digest, build_environment, python_abi, toolchain}`
* `target_fingerprint` = digest of `{build_environment, python_abi, toolchain}`
* artifact path = `cache_root/artifacts/<package>/<fingerprint>/<ext_suffix>`

So a changed crate source or toolchain produces a different fingerprint and therefore
a different artifact path — a stale `.so` cannot be silently reused. **The mechanism
already satisfied this requirement; only verification and recording were needed.**

Empirically confirmed: `source_digest` covers **95 files** of the `rust/` workspace
(`Cargo.toml` and `l3wal/src/lib.rs` present; `target/` excluded), and flipping
`lto = true` -> `lto = false` in `Cargo.toml` **changes the digest**
(`de26465d438f284d…` -> `05c5ab7c770bc068…`). The release profile is therefore bound
into the cache key.

## Owner-required verifications

**V1 — default with `SGLANG_CACHE_DIR` unset.**
`SGLANG_CACHE_DIR = /home/ubuntu/.cache/sglang`; loaded
`~/.cache/sglang/rust_extensions/artifacts/l3-native-wal/51ca2e73…/_l3wal…so`;
`in-repo? = False`; `<repo>/rust-cache` not created.

**V2 — explicit `SGLANG_CACHE_DIR` override.**
`SGLANG_CACHE_DIR=/tmp/opencode/m1-v2-cache-20260917` -> rebuilt from scratch and loaded
`/tmp/opencode/m1-v2-cache-20260917/rust_extensions/artifacts/l3-native-wal/51ca2e73…/_l3wal…so`;
override honored; repo clean.

Regression: arm A `115 OK`; arm B `115` with exactly the 4 documented mock-shape errors.

**Check 4 — identity chain recorded for the final production campaign.**
```
PRODUCTION_COMMIT   = 3090-24g-opt@<HEAD>            (to be fixed at campaign time)
RUST_SOURCE_HASH    = 51a64a33f93aed4fd2f4708af2d294f0b9303ce9f2ec19533dfa6b6b3b16d6a5
                      (sha256 over sorted rust/l3wal/{Cargo.toml,src/lib.rs})
CARGO_PROFILE       = [profile.release] lto=true strip=true opt-level=3 codegen-units=1
                      (repo profile — the shipping profile)
LOADED_SO_SHA256    = f1f0c0d3634f3e11891d6632790fc9301167d2e9168b2e441506684846220750
LOADED_SO_BYTES     = 578264
LOADED_SO_PATH      = ~/.cache/sglang/rust_extensions/artifacts/l3-native-wal/
                      51ca2e73.../_l3wal.cpython-312-x86_64-linux-gnu.so
```

Closing chain: `3090-24g-opt@commit -> build (repo profile) -> .so hash -> deployed process`.

## Consequence for the final campaign (owner ruling, unchanged order)
The gate to close is the **binary identity**, so the final 128K native Gate-B cell must
run on the native binary **built from the actual production commit with the repo release
profile**. That both satisfies R2 and retires the earlier scratch-binary provenance
problem (the old 578KB/4.3MB scratch binary is not reproduced; it stays as historical
evidence only).

The final campaign must therefore record the four identity fields above alongside its
Gate A/F1/F2 + native 128K + canary results.

## Repo state after M1
`3090-dev/` long-lived children are exactly: `evidence/`, `metrics/`, `gates/`, `tools/`,
`deploy/` (plus the pre-existing flat files at the `3090-dev/` root). No `harness/`,
`recovery/`, `residual/`, `scratch-archive/`, `reconcile/`, `prod-service/`.
