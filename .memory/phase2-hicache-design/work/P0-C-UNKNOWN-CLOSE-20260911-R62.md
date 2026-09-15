# P0-C Residual-Unknown Close R62

- Task ID: `P0-C-UNKNOWN-CLOSE-20260911-R62`
- Invocation: `ses-p0c-unknown-close-r62-20260911`
- Epoch: `2026-09-11`
- Role: `scout` (read-only)
- Status: **done**
- Claim boundary: local read-only source inspection. This report closes the two
  actionable R60 residuals with source evidence and records the exact diagnostic for
  the third. It is **not** production acceptance and does **not** satisfy or bypass the
  P0-B hard gate.

## ENTRY / input validation

- `ENTRY: ACCEPT`.
- Scope honored: **local** repository read-only inspection only. No remote host was
  contacted; no product/test/gate/storage/Git file was modified. The only write is this
  report artifact.
- Source of truth used: local git checkout
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache` (branch
  `3060-12g-qwen35-4b`), which contains the deployed revision `9213ee01…`.
- Parent inputs read: `P0-C-PROFILE-FREEZE-20260911-R60.md` and its artifacts; plus
  sibling `P0-C-PROFILE-RECON-20260911-R59.md`, `P0-C-PROFILE-REVIEW-20260911-R61.md`,
  `P0-C-AMEND-20260911-R64.md` to avoid duplicating already-answered items.

## Revision binding of the source inspected

| Ref | Value | Command |
|---|---|---|
| Local repo HEAD | `0a725c6385805f21138111e09bf69464ec29f1dc` (branch `3090-24g-hicache`) | `git -C … rev-parse HEAD` |
| 3060 branch tip | `4f41f5bab562b99562f30c67540eb05344d13637` (branch `3060-12g-qwen35-4b`) | `git rev-parse 3060-12g-qwen35-4b` |
| Deployed revision commit | `9213ee01d90ba3925e7fe928e80cc41354ee4fff` "fix(hicache): repair RH match telemetry joins" | `git rev-parse 9213ee01…` |
| 9213 vs 3060 tip | 9213 is an **ancestor**; branch tip has 4 commits on top (`4f41f5ba`, `a96dc148`, `1a887975`, `03a170ef`) | `git merge-base --is-ancestor …` |

The three files that define target (1) are **byte-identical** between the deployed
revision `9213ee01` and the worktree, so the constants below are those in force for the
frozen 3060 profile:

```
git -C 3rdparty/sglang-3090-24g-hicache diff 9213ee01d90ba3925e7fe928e80cc41354ee4fff -- \
  python/sglang/srt/mem_cache/storage/file/lru_file_evictor.py \
  python/sglang/srt/mem_cache/hicache_storage.py \
  python/sglang/srt/environ.py            # -> empty
git -C … cat-file -e 9213ee01…:python/sglang/srt/mem_cache/storage/file/lru_file_evictor.py  # EXISTS
```

---

## Target 1 — HiCache file-backend max-size / min-free semantics (CLOSED)

### 1a. Class and plumbing

| What | Location |
|---|---|
| `class HiCacheFile(HiCacheStorage)` | `python/sglang/srt/mem_cache/hicache_storage.py:368` |
| ctor signature / storage dir resolution | `hicache_storage.py:370-373` (`envs.SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR.get() or file_path`) |
| evictor constructed (all size accounting) | `hicache_storage.py:429-440` → `LRUFileEvictor(...)` |
| `class LRUFileEvictor` | `python/sglang/srt/mem_cache/storage/file/lru_file_evictor.py:56` |

### 1b. Exact defaults and parsing (file:line)

| Config | Default declaration | Resolution |
|---|---|---|
| `SGLANG_HICACHE_FILE_BACKEND_MAX_SIZE` | `python/sglang/srt/environ.py:693` `EnvStr(None)` | parsed by `_parse_size_to_bytes` → `None` ⇒ **0 bytes** (`lru_file_evictor.py:42-43`) |
| `SGLANG_HICACHE_FILE_BACKEND_MIN_FREE_SPACE` | `python/sglang/srt/environ.py:695` `EnvStr("0")` | parsed by `_parse_size_to_bytes` → `"0"` ⇒ **0 bytes** (`lru_file_evictor.py:47-48`) |
| `SGLANG_HICACHE_FILE_BACKEND_EVICTION_RATIO` | `python/sglang/srt/environ.py:694` `EnvFloat(0.9)` | `lru_file_evictor.py:140-148`, clamped to `(0,1]`, invalid ⇒ 0.9 |
| `_parse_size_to_bytes` semantics | `lru_file_evictor.py:39-53` | `None`/empty/`"0"` ⇒ 0 (disabled); accepts SI/IEC suffix via `human_readable_int`; invalid ⇒ 0 + warning |
| `extra_config` precedence | `lru_file_evictor.py:127-141` (`_cfg`: extra key wins over env) | frozen profile extra config is `{"hicache_storage_pass_prefix_keys": true}` ⇒ none of `max_size`/`min_free_space`/`eviction_ratio` present ⇒ **env fallback** |

### 1c. Effective values under the frozen 3060 profile

Frozen extra config (`r60_evidence.txt:26`; R60 §frozen table row "Storage backend"):
`--hicache-storage-backend-extra-config '{"hicache_storage_pass_prefix_keys":true}'`.
Only `SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/hy-tmp/hicache-rh-clean-20260910` is
exported by the launcher (`r60_evidence.txt:26`). Therefore **no cap and no free-space
watermark are configured**:

```
max_size_bytes   = 0      # MAX_SIZE unset -> _parse_size_to_bytes(None) == 0  (unbounded)
min_free_bytes   = 0      # MIN_FREE_SPACE default "0" -> 0 (watermark disabled)
eviction_ratio   = 0.9    # declared default; only consulted if max_size_bytes > 0
_eviction_configured = (0 > 0 or 0 > 0) == False   # lru_file_evictor.py:93
_eviction_enabled    = False                       # lru_file_evictor.py:94
```

Consequences, from the code contracts:

- The evictor is **inert**: `reserve()` returns `True` unconditionally when
  `not self._eviction_configured` (`lru_file_evictor.py:176-177`). The module docstring
  states this explicitly: "When eviction is not configured the evictor is inert: reserve
  always admits … the backend behaves as unbounded storage." (`lru_file_evictor.py:20-21`).
- `touch`/`commit`/`abort`/`clear` also early-return when not enabled
  (`lru_file_evictor.py:226-227, 233-234, 243-244`).
- No LRU scan, no cap accounting, and no `_enforce_free_space_locked` run
  (constructor returns at `lru_file_evictor.py:101-102` before the scan/log block).
- **Naming correction:** there is no "free-ratio" in this backend. `min_free_space` is an
  **absolute byte watermark**; `max_size` is an **absolute byte cap**. The only ratio is
  `eviction_ratio=0.9`, applied post-trigger as `target = int(max_size * ratio) - needed`
  (`lru_file_evictor.py:383-388`) — unreachable at `max_size=0`.
- The file backend is therefore bounded **only by filesystem free space** at the OS level
  (`/hy-tmp`). Disk exhaustion surfaces as OS `ENOSPC` handled in `HiCacheFile.set`
  (`hicache_storage.py:542-554`), not as an eviction.
- `HiCacheFile` never logs the resolved values itself; this is source-resolved, not
  log-resolved.

### 1d. Residual caveat on the effective runtime value

The runtime process environment was **never dumped**. `r60_evidence.txt` contains no
`/proc/218072/environ` section, and R61 F4 item 6 explicitly flags this
(`P0-C-PROFILE-REVIEW-20260911-R61.md:133-136`). The "no `*_MAX_SIZE` /
`*_MIN_FREE_SPACE` is set" statement currently rests on:

1. the launcher's own `export SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=…` only
   (`r60_evidence.txt:26`), and
2. the OPS3060 deploy env list (`OPS3060-DEPLOY-9213-RH-OFF-20260909.md:67-69`).

Neither proves the inherited container environment lacked those two vars. Therefore the
statement above is **"defaults apply"** and the exact bounded command that makes it
first-hand evidence is:

```
ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
  -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com \
  "tr '\0' '\n' < /proc/218072/environ | grep -E 'SGLANG_HICACHE_FILE_BACKEND_(MAX_SIZE|MIN_FREE_SPACE|EVICTION_RATIO)' || echo '(none set)'"
```

Expected if the defaults hold: no `MAX_SIZE` / `MIN_FREE_SPACE` / `EVICTION_RATIO` lines.

---

## Target 2 — checkout revision banner / build identifier (CLOSED, negative)

### 2a. What identifiers exist

| Candidate identifier | Present? | Location / value |
|---|---|---|
| Deploy marker file `.codex-deployed-revision` | **Yes — remote checkout only** | `/root/sglang-3060-12g-hicache/.codex-deployed-revision` = `9213ee01d90ba3925e7fe928e80cc41354ee4fff` (`r60_evidence.txt:98-99`) |
| Same marker in the local git repo | **No** | `ls .codex-deployed-revision` → not found in `3rdparty/sglang-3090-24g-hicache` |
| SGLang git-revision banner printed at server startup | **No** | bounded grep of the captured live log `sglang3060-rh-clean-env-20260910.log` for `version/fingerprint/revision/commit/build` found only the `server_args` dump, the endpoint-deprecation lines, and no revision banner |
| Runtime `version` field on `/get_server_info` | Yes, but revision-agnostic | `0.0.0.dev0` (captured `r60_server_info.json`) |
| Rust-extension build fingerprint (`fingerprint_version`, source-digest sha) | Exists in code | `python/sglang/srt/rust_extensions/loader.py:35` (`_FINGERPRINT_VERSION = 1`), used at `:233`; not emitted by this profile (no rust extension configured; backend flashinfer/triton) |

### 2b. Source of the runtime version

- `/get_server_info` (deprecated alias) and `/server_info` both return
  `"version": __version__`:
  - routes: `python/sglang/srt/entrypoints/http_server.py:792-799` and `:802-803`;
  - field: `http_server.py:825` `"version": __version__` (imported at `:187`).
- `python/sglang/version.py:1-23`: try `sglang._version` → try
  `importlib.metadata.version("sglang")` → try `setuptools_scm.get_version` with
  `fallback_version="0.0.0.dev0"` → final literal `"0.0.0.dev0"`.
- `python/pyproject.toml:243-248`:
  ```
  [tool.setuptools_scm]
  root = ".."
  version_file = "sglang/_version.py"        # absent in the checkout
  git_describe_command = ["python3", "scripts/release/get_version_tag.py"]
  fallback_version = "0.0.0.dev0"            # <- what the live server reports
  ```
  `python/sglang/_version.py` does not exist in the checkout. Combined with the remote
  checkout **not being a git repo** (R60:45), the version degrades to the fallback.

### 2c. Conclusion and the exact bounded commands

- The checkout contains **one** revision banner: the deploy marker
  `.codex-deployed-revision`. It is written by deployment tooling and is **never read or
  emitted by SGLang**, so it labels the tree on disk but cannot be compared to the
  in-memory process from within the process.
- SGLang emits **no git-revision/build identifier** at server startup. The only runtime
  identifier, `version=0.0.0.dev0`, is the `setuptools_scm` fallback and is
  revision-agnostic.
- Therefore R60 followup #3 ("a bounded fresh start … would print the loaded revision")
  is **not supported by the code**: a fresh bounded start of the same profile would also
  print `0.0.0.dev0`. The only way to bind the live process to a revision is per-file
  content hashing against the known `9213ee01` digests.

Exact bounded commands (read-only) that print the identifier on the 3060:

```
# (i) the only revision banner in the checkout
ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
  -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com \
  'cat /root/sglang-3060-12g-hicache/.codex-deployed-revision'
# -> 9213ee01d90ba3925e7fe928e80cc41354ee4fff

# (ii) the live process's own reported version (revision-agnostic)
ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
  -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com \
  "curl -s http://127.0.0.1:30000/get_server_info | /root/sglang-env-3060-4b/bin/python -c 'import sys,json;print(json.load(sys.stdin)[\"version\"])'"
# -> 0.0.0.dev0

# (iii) true binding: hash the seven deployed runtime files and compare to revision 9213
#       (digests are listed in OPS3060-DEPLOY-9213-RH-OFF-20260909.md:46-54)
ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
  -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com \
  'cd /root/sglang-3060-12g-hicache && sha256sum \
     python/sglang/srt/managers/schedule_batch.py \
     python/sglang/srt/managers/scheduler.py \
     python/sglang/srt/managers/scheduler_components/hicache_restore.py \
     python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py \
     python/sglang/srt/mem_cache/hybrid_cache/hybrid_pool_assembler.py \
     python/sglang/srt/mem_cache/pool_host/group.py \
     python/sglang/srt/mem_cache/unified_radix_cache.py'
```

Local comparison anchor for (iii): `git show 9213ee01…:<path> | sha256sum` in
`3rdparty/sglang-3090-24g-hicache`.

Deployment-scope caveat: OPS3060 says only **seven runtime files** were streamed from
`git archive` at `9213ee01` (`OPS3060-DEPLOY-9213-RH-OFF-20260909.md:29-31`), so the
marker does not prove the entire checkout tree is at `9213ee01` — only those seven files
are guaranteed. This further limits any whole-checkout revision claim.

---

## Target 3 — `nvidia-smi` empty process list vs 8897 MiB (diagnostic recorded)

### 3a. Observed facts (from R60 artifact, first-hand lines)

| Fact | Evidence |
|---|---|
| Device reports `8897MiB / 12288MiB` used | `P0-C-PROFILE-FREEZE-20260911-R60.artifacts/r60_evidence.txt:15` |
| `nvidia-smi` process table is **empty** | `r60_evidence.txt:20-24` (header only, no rows) |
| Same shell sees the server PIDs | `ps` lists `218071`/`218072` (`r60_evidence.txt:26-27`) |
| Same shell reads `/proc/218072/cmdline` | `r60_evidence.txt:30-92` |
| Same shell resolves PID → socket | `ss -tlnp` → `users:(("python",pid=218072,fd=59))` (`r60_evidence.txt:94`) |

### 3b. Corrected attribution

Because the capturing shell could enumerate `/proc/218072` and resolve PID `218072`
through `ss`, the process **is** in the same PID namespace as the shell that ran
`nvidia-smi`. R60's stated cause — "Container/PID-namespace visibility quirk"
(`P0-C-PROFILE-FREEZE-20260911-R60.md:108`, `:171`) — is therefore **not supported by the
captured bundle**. The gap is in NVML's per-process enumeration
(`nvmlDeviceGetComputeRunningProcesses` path used to populate the `nvidia-smi` table),
not in procfs/PID-namespace visibility. This report records the command that settles the
remaining ambiguity rather than asserting a new cause.

### 3c. Exact read-only reconciliation command (run on the 3060)

Single bounded SSH line; all reads, no `-k`, no service action:

```
ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
  -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com '
  echo "== pid namespaces (shell | server) =="; readlink /proc/self/ns/pid /proc/218072/ns/pid;
  echo "== device holders via procfs (bypasses NVML) =="; fuser -v /dev/nvidia* 2>&1;
  echo "== server nvidia fds =="; ls -l /proc/218072/fd 2>/dev/null | grep -ci nvidia;
  echo "== server nvidia maps =="; grep -c "/dev/nvidia" /proc/218072/maps 2>/dev/null;
  echo "== NVML compute-apps =="; nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader;
  echo "== device memory =="; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader'
```

Interpretation:

1. **Namespaces identical** (`/proc/self/ns/pid` == `/proc/218072/ns/pid`) rules out
   PID-namespace invisibility, matching the R60 bundle.
2. **`fuser -v /dev/nvidia*` shows only PID `218072`** (or its `python` children) and
   `/proc/218072/fd` contains `/dev/nvidia*` entries ⇒ the 8897 MiB is attributable to
   the running server; the empty `nvidia-smi` table is an NVML enumeration restriction.
3. **`fuser` shows other PIDs** not in the server tree ⇒ the memory belongs to another
   context/tenant on the same device; the server's own usage is the smaller residual.
4. **`/proc/218072/fd` has no `nvidia` entry** ⇒ the server is not the holder and the
   attribution must switch to the `fuser` PIDs.
5. `/proc/218072/maps` count corroborates the device mapping count in (2)/(4).

Supporting (optional) read-only probes if (2)/(3) disagree:

```
nvidia-smi -q -d MEMORY,PIDS          # device-level truth + NVML PID section
for p in /proc/[0-9]*; do ls -l "$p"/fd 2>/dev/null | grep -q /dev/nvidia && \
  printf '%s %s\n' "$p" "$(tr '\0' ' ' <"$p"/cmdline 2>/dev/null | cut -c1-80)"; done
```

---

## Search limits and unknowns

- Search was confined to the local workspace `3rdparty/sglang-3090-24g-hicache` and
  `.memory/phase2-hicache-design/work/`. No remote host was contacted.
- The 3060 runtime process environment dump is absent from all captured artifacts
  (confirmed: no `/proc/218072/environ` section anywhere under `work/`). Target 1's
  "effective" value is therefore source-resolved with the exact confirmation command
  given in §1d.
- The local repo does not contain the remote deploy marker, and no local file was found
  that generates it; the marker's writer is not in the inspected trees.
- No whole-checkout revision claim is possible: only seven files are revision-pinned by
  the deployment record, and the checkout is not a git repo.
- Target 3 is a recorded diagnostic, not an executed result; the remaining cause
  ambiguity is explicitly left to the command in §3c.

## Artifacts

- This report: `.memory/phase2-hicache-design/work/P0-C-UNKNOWN-CLOSE-20260911-R62.md`
- Source files cited (read-only): `hicache_storage.py`, `lru_file_evictor.py`,
  `environ.py`, `http_server.py`, `version.py`, `python/pyproject.toml`.
- Consumed (not modified): `P0-C-PROFILE-FREEZE-20260911-R60.md` and its
  `R60.artifacts/` bundle.

## Evidence

- `lru_file_evictor.py:20-21, 39-53, 93-102, 127-148, 165-177, 226-244, 383-388`
- `hicache_storage.py:368, 370-373, 429-440, 542-554`
- `environ.py:691-699`
- `http_server.py:187, 792-803, 825`
- `version.py:1-23`; `python/pyproject.toml:243-248`
- `r60_evidence.txt:15, 20-24, 26-27, 30-92, 94, 98-99`
- `r60_server_info.json` → `"version":"0.0.0.dev0"`
- `git diff 9213ee01… -- <the three files>` → empty; `git cat-file -e 9213ee01:…lru_file_evictor.py` → exists
- `OPS3060-DEPLOY-9213-RH-OFF-20260909.md:29-31, 46-54, 67-69`
- `P0-C-PROFILE-REVIEW-20260911-R61.md:133-136` (environ-not-dumped corroboration)

## Summary

1. **Target 1 closed.** The file backend delegates all sizing to `LRUFileEvictor`.
   Declared defaults are `MAX_SIZE=None`→0, `MIN_FREE_SPACE="0"`→0,
   `EVICTION_RATIO=0.9` (`environ.py:693-695`), parsed by `_parse_size_to_bytes`
   (`lru_file_evictor.py:39-53`). The frozen extra config contains none of these keys, so
   env defaults govern. Under the frozen 3060 profile the evictor is **unconfigured and
   inert**: no cap, no free-space watermark, no LRU eviction — the store is bounded only
   by filesystem free space. The only residual is the never-captured process environment;
   the exact confirmation command is given (§1d).
2. **Target 2 closed (negative).** The checkout's only revision banner is the remote
   deploy marker `.codex-deployed-revision = 9213ee01…`; SGLang emits no git-revision
   banner, and its runtime `version` is the `setuptools_scm` fallback `0.0.0.dev0`
   (`http_server.py:825`, `pyproject.toml:243-248`). A fresh bounded start would **not**
   print the revision; only per-file sha256 against the seven pinned runtime files can
   bind the live process.
3. **Target 3 recorded.** The R60 bundle shows the same shell could read
   `/proc/218072`, so the PID-namespace explanation is unsupported; the exact read-only
   command in §3c (`readlink …/ns/pid`, `fuser -v /dev/nvidia*`, `/proc/218072/fd`,
   NVML `--query-compute-apps`) reconciles the 8897 MiB with the empty process table.
4. No product/test/gate/storage/Git change; read-only throughout.

## Followups

1. If the P0 workstream needs first-hand runtime confirmation of the file-backend
   defaults, run the §1d `environ` grep (read-only) under a fresh authorization.
2. If exact live-process revision binding is required, run §2c(iii) and diff against the
   seven digests in `OPS3060-DEPLOY-9213-RH-OFF-20260909.md`.
3. If the 8897 MiB attribution must be settled, run §3c; this is a remote read-only probe
   and needs a fresh remote-authorized dispatch.

## Open issues

- The runtime process environment (`/proc/218072/environ`) has still never been captured,
  so target 1's effective value is source-resolved with the confirmation command pending.
- `nvidia-smi` per-process enumeration is empty on the 3060 while the shell can read the
  server's `/proc`; the cause (NVML enumeration restriction vs other tenant) remains open
  pending §3c. R60's container/PID-namespace attribution is not supported by the bundle.
- The remote checkout is not a git repo and only seven files are revision-pinned to
  `9213ee01`; whole-checkout revision equality cannot be established from the marker.
- R60 followup #3 ("a bounded fresh start would print the loaded revision") is not
  supported by the code — a fresh start prints `0.0.0.dev0`.
- This report is P0-C evidence only and does not constitute production acceptance or
  satisfy the P0-B hard gate.
