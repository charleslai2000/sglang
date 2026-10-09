# OPS-20260908-3060-FLASHMLA-DEPS-LOCAL-055

- Task ID: `D3060-FLASHMLA-DEPS-LOCAL-055`
- Orchestration epoch: `20260908-3060`
- Role: `devops-executor`
- Status: `done`
- Scope: local workstation only; public GitHub codeload access only

## Authorization and procedure

Authorized operation was to download the exact pinned commit archives from CMake/public
GitHub into `/tmp/d3060-aot-deps`, then verify file size, SHA256, and nonempty status.
No private 3060 host was accessed. No installation or product-source modification was
performed.

## Commands and outputs

Executed:

```sh
mkdir -p /tmp/d3060-aot-deps
curl -fL --retry 2 --connect-timeout 15 --max-time 300 \
  'https://codeload.github.com/sgl-project/FlashMLA/tar.gz/c1dee569a494b184811a08171a690ece21420262' \
  -o /tmp/d3060-aot-deps/FlashMLA-c1dee569a494b184811a08171a690ece21420262.tar.gz
curl -fL --retry 2 --connect-timeout 15 --max-time 300 \
  'https://codeload.github.com/NVIDIA/cutlass/tar.gz/147f5673d0c1c3dcf66f78d677fd647e4a020219' \
  -o /tmp/d3060-aot-deps/cutlass-147f5673d0c1c3dcf66f78d677fd647e4a020219.tar.gz
```

Download commands completed successfully (`curl` exit status 0).

Verification command:

```sh
test -s "$path"
actual=$(sha256sum "$path" | awk '{print $1}')
size=$(stat -c '%s' "$path")
test "$actual" = "$expected"
```

Verification output:

```text
/tmp/d3060-aot-deps/FlashMLA-c1dee569a494b184811a08171a690ece21420262.tar.gz|size=252084|sha256=77d3f1714b5903dc8f7a99fbc3a5d9a2b886e449f994b6c4b1d2feeacb467b1e|nonempty=PASS|sha256=PASS
/tmp/d3060-aot-deps/cutlass-147f5673d0c1c3dcf66f78d677fd647e4a020219.tar.gz|size=34013493|sha256=9f6c53320a85b4a570975e557918cde65168cd311f081920446c238437347dc6|nonempty=PASS|sha256=PASS
```

## Changed resources

Created/downloaded:

1. `/tmp/d3060-aot-deps/FlashMLA-c1dee569a494b184811a08171a690ece21420262.tar.gz`
2. `/tmp/d3060-aot-deps/cutlass-147f5673d0c1c3dcf66f78d677fd647e4a020219.tar.gz`

The directory contained pre-existing unrelated files named `repo-*.tar.gz`; they were
not touched and are outside this task's changed-resource set.

## Evidence and followups

- Both archives are nonempty.
- Both archive sizes were recorded above.
- Both SHA256 values exactly match the user-provided pins.
- No product source files were changed.
- No installation was performed.
- No rollback was required; the requested artifacts remain at the target paths.

## Open issues

None.
