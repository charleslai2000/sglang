# M2-HICACHE-WIRING-RECON-20260918

Task: M2-HICACHE-WIRING-RECON-20260918
Scope: READ-ONLY reconnaissance of what must change to serve M2 with HiCache enabled, and to promote the shared-src telemetry revision into the frozen runtime identity.
Terminal state: DONE

## Task
Map exactly what must change, where, and in what order to make M2 serve with
`--enable-hierarchical-cache`, and to promote the shared-src telemetry revision into the
frozen runtime identity. Read-only: no edits, no process signals, no GPU, no port binds,
no inference.

## Scope
- Read-only reconnaissance on this host. No writes to `/opt`, `/data`, source tree, or
  service scaffold. No git mutation.
- Binding inputs (not re-litigated): ledger ¶105-106 owner decision — M2 enables HiCache
  AND telemetry release merges into the same GPU window; RCA (`M2-CONCURRENCY-DEGRADATION-RCA-20260918.md`)
  proved the mamba-slot N=16 cliff and the HiCache-ON retention fix (24/24).
- Authority limits: this artifact reports facts, locations, and a dependency-ordered change
  list. It does not implement, authorize, or verify any change.

## Result

### R1 — Where the M2 serving argv actually lives (Q1)

**M2 argv is a hardcoded Bash array in the frozen launcher, not in the scaffold/config.**
- `ARGS=(...)` at `/opt/sglang/local-prod-v1.2.1-candidate-M2/launcher/launch.sh` lines **144-166**;
  `exec "$PY" -u "${ARGS[@]}"` at line **231**. Dry-run prints the identical array (lines 217-226).
- Observed dry-run argv (read-only, `SGLANG_LAUNCH_DRY_RUN=1`, CUDA pinned to a non-existent
  device, no bind, no server):
  ```
  DRY-RUN argv: .../env/bin/python -u -m sglang.launch_server --model-path
  /data/models/omnicoder-9b-gptq-int4 --host 0.0.0.0 --port 30000 --tp-size 1
  --mem-fraction-static 0.92 --max-total-tokens 262144 --context-length 131072
  --max-running-requests 8 --max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3
  --attention-backend flashinfer --linear-attn-prefill-backend triton
  --linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer
  --mamba-ssm-dtype float32 --reasoning-parser qwen3 --tool-call-parser qwen3_coder
  --enable-metrics --export-metrics-to-file --export-metrics-to-file-dir <logdir>
  --disable-prefill-cuda-graph
  ```
  No HiCache flag present. `SGLANG_L3_MODE=disabled`.
- Scaffold `/tmp/opencode/prod-service-20260917/bin/start.sh` m2 branch (lines 34-41) only
  exports `SGLANG_L3_MODE="${SGLANG_L3_MODE:-$M2_L3_MODE}"` and
  `SGLANG_MODEL_PATH="${SGLANG_MODEL_PATH:-$M2_MODEL_PATH}"`, then execs the frozen launcher.
- `/tmp/opencode/prod-service-20260917/conf/service.env` defines only M2 identity/locator
  variables (lines 47-51: `M2_PORT`, `M2_TREE_DEFAULT`, `M2_IDENTITY_DEFAULT`,
  `M2_MODEL_PATH`, `M2_L3_MODE`; line 90 lists them in the env allowlist). **There is no
  `M2_EXTRA_ARGS`/`EXTRA_ARGS`.** Grep over `service.env`, `common.sh`, `start.sh` found none.
- `supervise.sh` execs `tree_launcher`; it does not build argv.

=> Adding HiCache is a **frozen-launcher edit**, not a service.env edit.

### R2 — Frozen gates that currently forbid HiCache (Q2)

Two independent gates must be inverted/extended:

**(a) Launcher GATE 3/3** — `/opt/sglang/local-prod-v1.2.1-candidate-M2/launcher/launch.sh`:
- lines 33-39: `SGLANG_L3_MODE` must be set explicitly and MUST equal `disabled` (else exit 2);
- lines 168-213: GATE 3/3 requires `tools/l3_namespace.py --validate` to **refuse with exit 6**
  (a store existing => exit 14; any other rc => propagate);
- lines 203-212: explicit forbidden-argv loop — `--enable-hierarchical-cache`,
  `--hicache-write-policy`, `--hicache-storage-backend`, `--hicache-storage-prefetch-policy`,
  `--hicache-size`, `--enable-ready-horizon` => exit 13 if present;
- lines 82-99: unsets inherited extent/L3 env vars.
This gate encodes the "M2 = no-L3/no-HiCache" policy, not a source-level limitation.

**(b) Freeze toolchain `audit_launcher.py`** — `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/tools/freeze/pysrc/audit_launcher.py`:
- reference = `/opt/sglang/local-prod-v1.1-candidate/launcher/launch.sh` (set by
  `launcher-repin.sh` line 37);
- `PRODUCTION_REQUIRED_SERVING_TOKENS` = only `--context-length 131072`,
  `--max-running-requests 8`, `--max-mamba-cache-size 48` (lines 54-58);
- approved bind host replacement `127.0.0.1 -> 192.168.20.250` (line 74);
  approved `--served-model-name` = only `qwen35-9b-local` (lines 79-81).
- Observed, read-only (`--ref-launcher /opt/sglang/local-prod-v1.1-candidate/...`):
  ```
  M2 REF AUDIT EXIT=1
  LAUNCHER-AUDIT FAIL: .../local-prod-v1.2.1-candidate-M2/launcher/launch.sh
    - serving flags differ ... unapproved_new=['"$MODEL_PATH"', '0.0.0.0', '262144']
      unapproved_dropped=['/data/models/qwen35-9b-w4a16', '--enable-hierarchical-cache',
      '--hicache-write-policy', 'write_back', '--hicache-storage-backend', 'extent',
      '--hicache-storage-prefetch-policy', 'wait_complete', '--hicache-size', '"$L2_GB"',
      '--enable-ready-horizon']
      missing_replacements=['192.168.20.250', '524288']
    - bind host must be one of the approved v1.2 hosts ['192.168.20.250'], found '0.0.0.0'
    - --served-model-name missing (exactly one approved value is required)
  ```
  The v1.1 reference launcher **does contain** the HiCache/ready-horizon flags, so adding
  HiCache to M2 **removes 10 dropped flags** from the delta. M2 still fails audit on
  model-path literal vs `$MODEL_PATH`, bind host `0.0.0.0`, missing `--served-model-name`,
  and `262144` vs required replacement `524288`.
- The same audit against the **M1** launcher also exits 1 (bind host + served-model-name,
  plus `0.0.0.0`/`524288`), i.e. these are pre-existing bespoke-launcher divergences, not
  HiCache-specific.
- `freeze.sh` does **not** call `audit_launcher.py` directly; `launcher-repin.sh` calls it
  (lines 117-121) and `freeze.sh` invokes `launcher-repin.sh` at line 242. `launcher-repin.sh`
  renders from `templates/launch.sh.tmpl`, which has **no M2 gates** and hardcodes
  `--model-path /data/models/qwen35-9b-w4a16`, `--host 192.168.20.250`,
  `--served-model-name qwen35-9b-local`, plus the full M1 HiCache flag set
  (template lines 145-165). Therefore the M2 launcher is **hand-installed, not
  template-derived**; a template repin would overwrite M2 semantics.

### R3 — HiCache does NOT require an L3/storage backend (Q3)

- `hicache_host_memory_mode` default = `"cache"` (`server_args.py` lines 2741-2750).
- `_validate_hicache_host_memory_mode` (lines ~8548+) requires `hicache_size > 0` or a
  resolved ratio; it does **not** require `hicache_storage_backend` in `cache` mode.
  Only `buffer_only` requires `--hicache-storage-backend`.
- `_handle_hicache` (lines 8510-8547): `SGLANG_L3_BACKEND` is used only as a fallback when
  `hicache_storage_backend is None` (lines 8531-8535). `SGLANG_L3_MODE` is not read by any
  M2 source file (observed shell-only).
- RCA working arm confirmed no backend: argv extra
  `--enable-cache-report --enable-hierarchical-cache --hicache-write-policy write_back --hicache-size 32`;
  console `Tree cache initialized: ... hybrid_ssm=True hicache_attached=True`.
- Minimal config per RCA: `--enable-hierarchical-cache --hicache-write-policy write_back
  --hicache-size 32` (+ `--enable-cache-report` for native cache telemetry).

### R4 — `--hicache-size` semantics and host-tier size (Q4)

- Unit = **SI GB (10^9), not GiB** — documented in M1 launcher comment line 47
  (`# NOTE: --hicache-size is SI GB (10^9), NOT GiB`). M1 profiles: perf `L2_GB=32`,
  capacity `L2_GB=48` (M1 launcher lines 49-50).
- `hicache_size` overrides `hicache_ratio` (field help lines 2755-2759); default ratio is
  resolved by `_handle_hicache_ratio_default` (lines 8490-8509): 2.0 cache / 1.2 buffer_only.
- Host tier = host RAM (L2). `/data/l3` is used only for a storage backend (extent/file);
  the RCA arm uses none.
- Allocation: `_split_hicache_size` (`mem_cache/hybrid_cache/hybrid_pool_assembler.py`
  lines 134-147) splits the host budget proportionally across device pools (full KV, SWA,
  mamba); consumed at hybrid_pool_assembler.py 360-362, 415, 711-713, 813;
  `mem_cache/hiradix_cache.py` 94-95, 112-113. Host-memory guard
  `HICACHE_HOST_MEMORY_RESERVE_BYTES` / `sync_fixed_hicache_size` in
  `mem_cache/pool_host/base.py`.
- Mutual exclusions: `--disable-radix-cache` (`server_args.py` 9388) and
  `--enable-int8-mamba-checkpoint` (line 7057).

### R5 — Frozen-identity re-pin surface (Q5)

M2 frozen pins currently (observed):
- `manifest/identity.json` — `LAUNCHER_HASH=9a557d5f…b21c4`, `TREE_HASH=e6e8de1c…c495a`,
  `l3_policy.mode=disabled`, `tree.tree_manifest_lines=14788`, `src_file_count=14784`,
  `srctree_stream_digest=c7427132…dafbc`, `frozen_at_utc=2026-09-18T11:40:00Z`,
  `freeze_tool=v1.1.2-freeze-20260917`.
- `manifest/identity-pins.json` — same LAUNCHER_HASH/TREE_HASH, `l3_mode=disabled`,
  `source_tree="/opt/sglang/local-prod-v1.2.1-candidate/src (hardlinked)"`.
- `manifest/TREE-SHA256.txt` — 14788 lines; line 1 = launcher; lines 14786-14788 =
  `tools/l3_namespace.py`, `tools/preflight_identity.py`, `tools/validate_telemetry.py`;
  the `env` symlink is not included.
- Tool-side pin copy for M2 does **not** exist. `ls 3090-dev/tools/freeze/pins/` shows
  `local-prod-v1.1-candidate-pins.json`, `local-prod-v1.1.2-candidate-pins.json`,
  `local-prod-v1.2.1-candidate-pins.json` (M1), but **no M2 file**.
- Re-pin writers: `bin/freeze.sh --build-candidate` (writes `manifest/TREE-SHA256.txt`,
  `identity.json`, `identity-pins.json`, then copies to
  `pins/$DEST_NAME-pins.json`, line 535) and `bin/launcher-repin.sh` (render + audit +
  dry-run). `freeze.sh` **refuses** an existing `manifest/identity.json` (lines 143-144).
- `tools/validate_telemetry.py` in the M2 tree hardcodes
  `SRC = "/opt/sglang/local-prod-v1.2.1-candidate/src"` (M1 tree) and binds 6 source +
  4 gate hashes; it is not invoked by the M2 launcher. `pysrc/repoint_telemetry.py` exists to
  rewrite `SRC=`, `/opt/sglang/<tree>`, `LOCAL-PROD-*`.

Identity hardlink fact (blocks in-place src edits): M1 and M2 `src` are hardlinked —
`stat` shows `server_args.py` inode `27528456`, `nlink=2`, in both trees; `diff -rq` of the
two `src` trees exits 0. Working tree is a separate inode. Staging `/tmp/opencode/v1.2.1-stage/src`
== M1 frozen `src` (`diff -rq` exit 0). Editing M2 `src` in place would mutate M1.

### R6 — Rollback surface (Q6)

- Graceful stop: `/tmp/opencode/prod-service-20260917/bin/stop-m2.sh` validates pid cmdline
  (`launch_server`), port, tree, model before signalling.
- Byte backups already present:
  - M1 tree: `manifest/identity.json.bak-bindhost-20260917T211632Z`,
    `identity-pins.json.bak-bindhost-20260917T211632Z`,
    `TREE-SHA256.txt.bak-bindhost-20260917T211632Z`,
    `manifest/launch.sh.bak-bindhost-20260917T211632Z` (that launcher was `127.0.0.1`,
    sha `38487942…`, TREE_HASH `3bd285d5…`; current M1 launcher is `0.0.0.0`, sha `4ae68470…`,
    TREE_HASH `5ed662d0…`).
  - Scaffold: `conf/service.env.bak-20260918125106`,
    `conf/service.env.pre-f39-20260918T161154Z`, `bin/start.sh.bak-20260918125106`,
    `bin/start.sh.pre-f39-20260918T161154Z`.
- No `.bak` files exist under the M2 manifest dir today.
- Rollback = restore prior launcher bytes (`9a557d5f…`) and regenerate `manifest/*`
  (identity.json + identity-pins.json + TREE-SHA256.txt), or accept a fresh freeze.

### Live state at recon time (read-only)
- `state/gpu-owner.json`: `role/state=free`, `l3_namespace=""`, `note="m2-stopped"`,
  `updated_at_utc=2026-09-18T18:45:24Z`.
- `state/runs/m2.run`: `pid=1840571`, `port=30000`, `tree=…candidate-M2`,
  `run_id=m2-20260918T183744Z-1840331`, `cold_start_s=106.8` (historical record; process not found).
- `state/pids/` empty. No listener on 30000/3016x. The only running server is the M3/M4 GGUF
  smoke: pid 1846485, port 30165, tree `/opt/sglang/local-prod-v1` (unrelated to M2).
- `tools/l3_namespace.py --validate --task-id recon-20260918` returned exit **6** / `REFUSE`
  (no store at `/data/l3/recon-20260918`), confirming the GATE 3/3 precondition still holds.

### Dependency-ordered change list (what must change, in order)

Order is dictated by observed dependencies: the launcher must be consistent with whatever
`src`/pins exist, `src` edits cannot be in-place (hardlink), and the frozen-identity tools
validate launcher bytes against `src`.

1. **Telemetry revision → staged `src`** (do first; changes the stream digest and source hashes).
   Working tree (`/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`, HEAD `ea7b0e9b44`)
   has 10 modified files + 1 new file + tests. All 10 differ from frozen M1/M2 `src`:
   `entrypoints/openai/protocol.py` (+39/-?), `serving_chat.py` (+182),
   `usage_processor.py` (+34), `environ.py` (+6),
   `function_call/qwen3_coder_detector.py` (~416 changed), `mem_cache/hybrid_cache/hybrid_cache_controller.py` (+71),
   `mem_cache/unified_radix_cache.py` (+177), `sampling/custom_logit_processor.py` (+14),
   `server_args.py` (1 line: `enable_cache_report False -> True`), `utils/hf_transformers/gguf_native.py`
   (+22/-4), plus NEW `python/sglang/srt/parser/qwen35_reasoning_policy.py` (249 lines),
   3 modified tests (`test_function_call_parser.py`, `test_hicache_host_allocability.py`,
   `test_hybrid_group_wiring.py`) and 2 new tests (`test_qwen35_reasoning_policy.py`,
   `test_gguf_native_tokenizer_ids.py`). Must be promoted via a fresh freeze from an updated stage — **not** in-place
   (M1/M2 `src` share inodes).
2. **Freeze destination/scope gating.** `freeze.sh` exact-path DEST allowlist (line 127) covers
   `local-prod-v1.1.2-candidate|local-prod-v1.2-candidate|local-prod-v1.2.1-candidate|local-prod-v1.2.2-candidate`
   — **excludes `…candidate-M2`**; `freeze.sh` also refuses an existing `manifest/identity.json`.
   The source-scope allowlist `pins/local-prod-v1.2-candidate-allowlist.txt` (153 lines) contains
   only 4 `src/python/...` entries and **none** of the telemetry files; a GGUF path delta is a hard
   refusal unless in `GGUF_INERT_EXACT_PATHS` (freeze.sh lines 334-356).
3. **M2 launcher argv + gates edit** (frozen `launcher/launch.sh`): add the HiCache flags to `ARGS`
   and invert/extend the policy that currently requires `disabled` and forbids HiCache argv.
   This edits `launcher/launch.sh` (sha changes from `9a557d5f…`), which cascades to:
   `manifest/TREE-SHA256.txt` line 1, its self-digest (`TREE_HASH`), `identity.json`
   (`LAUNCHER_HASH`, `launcher.sha256`, `l3_policy`), `identity-pins.json` (`LAUNCHER_HASH`,
   `l3_mode`), and (if freeze-managed) the tool-side `pins/<name>-pins.json`.
4. **Re-pin identity** (order 3 before 4 because identity binds launcher/src bytes):
   regenerate `manifest/TREE-SHA256.txt` → `identity.json` → `identity-pins.json`; keep
   `identity.tree.tree_manifest_sha256_self` == sha256(TREE-SHA256.txt) (enforced by
   `preflight_identity.check_manifest`).
5. **Certify the pair.** `manifest/identity.json` and `TREE-SHA256.txt` mutually bind;
   `EXECUTED` launcher gate and `preflight_identity.py --all` must pass against the new digest.
6. **Freeze toolchain consistency (blocking)**: `audit_launcher.py` must accept the new M2
   launcher (or M2 must be given an explicit, owner-approved audit profile) — today both M1 and
   M2 fail on bind host `0.0.0.0` and missing `--served-model-name`, independent of HiCache.
   `launcher-repin.sh` cannot render the M2 launcher (template lacks M2 gates/hardcodes different
   model/host).

## Evidence

All evidence below is from read-only commands on this host.

1. M2 argv/exec: `/opt/.../candidate-M2/launcher/launch.sh` lines 144-166 (ARGS), 168-213
   (GATE 3/3), 231 (exec); dry-run output quoted in R1 with `SGLANG_LAUNCH_DRY_RUN=1`,
   `CUDA_VISIBLE_DEVICES=999`, `LOG_DIR=/tmp/opencode/recon-dryrun-log`; exit 0, no bind.
   `bash -n launch.sh` exit 0.
2. Scaffold: `bin/start.sh` 34-41; `conf/service.env` 47-51, 90; grep for
   `M2_EXTRA_ARGS|EXTRA_ARGS` over `service.env`/`common.sh`/`start.sh` => none.
3. Gates: launcher lines 33-39/168-213 (quoted); audit runs quoted with exit codes 1/1 for
   M2/M1; `audit_launcher.py` lines 54-81 (allowlists), 116-121 (repin call site);
   `launcher-repin.sh` lines 37, 88-121; `templates/launch.sh.tmpl` lines 145-165, 143-147;
   `freeze.sh` lines 242, 326-356.
4. HiCache backend: `server_args.py` 2741-2750 (host memory mode default `cache`),
   2755-2759 (size overrides ratio), 8490-8509 (ratio default), 8510-8547 (`_handle_hicache` +
   env fallback), 8548+ (`_validate_hicache_host_memory_mode`), 9388/7057 (exclusions);
   RCA `driver.log`/`launch_argv.txt` for `hicache-iso-30164-20260918T183141Z-1838693`:
   `extra=[--enable-cache-report --enable-hierarchical-cache --hicache-write-policy write_back --hicache-size 32]`,
   `RCA_UP … cold_start_s=98`; console `hicache_attached=True`.
5. Size semantics: M1 launcher line 47 (SI GB) + 49-50 (L2_GB 32/48);
   `hybrid_pool_assembler.py` 134-147 and consumers; `hiradix_cache.py` 94-95, 112-113.
6. Pins: `manifest/identity.json`, `manifest/identity-pins.json`,
   `manifest/TREE-SHA256.txt` (14788 lines; line 1 launcher; tail tools) read in full;
   `stat` inode/nlink evidence for hardlink; `diff -rq` M1-src vs M2-src exit 0;
   stage vs M1 `src` `diff -rq` exit 0.
7. Telemetry promotion surface: `git status --porcelain` and
   `git diff HEAD --stat` (10 files, +716/-251) from worktree HEAD `ea7b0e9b44`;
   file-level `diff -q` vs frozen `src` for all 10 => all DIFF; new parser absent from frozen;
   allowlist grep => MISSING for all 11 paths; `freeze.sh` 334-356 GGUF refusal.
8. Rollback/live state: `state/gpu-owner.json`, `state/runs/m2.run`, empty `state/pids/`,
   no listener on 30000; `ss`/`ps` show only M3 smoke on 30165; `l3_namespace.py --validate`
   exit 6; backup filenames listed in R6.

### Incidental diagnostics artifacts (disclosure)
Read-only commands produced small diagnostic outputs outside the workspace:
`/tmp/opencode/recon-diff.txt` (`diff -rq` result), `/tmp/opencode/recon-audit-m2.txt`,
`/tmp/opencode/recon-audit-m2-ref.txt`, `/tmp/opencode/recon-audit-m1.txt`,
`/tmp/opencode/recon-audit-m1-ref.txt`. These contain no secrets, are not in the source
repository, and no product/service state was modified. `SGLANG_LAUNCH_DRY_RUN=1` exits before
`mkdir -p "$LOG_DIR"`, so no log dir was created.

## Defects or blockers

1. **`SGLANG_L3_MODE` is shell-only.** No M2 source reads it (grep finds nothing). Any
   "turn on HiCache via SGLANG_L3_MODE" route is a no-op at the runtime; the real levers are
   the frozen launcher ARGS and (optionally) `SGLANG_L3_BACKEND` (env fallback only when
   `--hicache-storage-backend` is unset).
2. **Posture conflict is structural.** The M2 launcher encodes "no-L3/no-HiCache" as a
   fail-closed policy; it must be edited together with its identity pins. A launcher edit
   without a pin regeneration fails GATE 1/3 and the freeze preflight.
3. **Hardlink coupling.** M1 and M2 `src` share inodes (`nlink=2`); in-place `src` edits
   mutate M1. Telemetry promotion requires a fresh freeze from an updated stage (or an
   equivalent copy-on-write plan), not in-place edits.
4. **`freeze.sh` cannot target the M2 tree as-is.** DEST allowlist excludes `…-M2`
   (line 127); it also refuses an existing `manifest/identity.json` (lines 143-144).
5. **Telemetry files are not in the approved source scope.** `pins/local-prod-v1.2-candidate-allowlist.txt`
   has no entry for any of the 10 modified telemetry files or the new parser; `freeze.sh`
   would exit 8 (source scope not approved). The working tree also modifies
   `python/sglang/srt/utils/hf_transformers/gguf_native.py`, which is a **hard refusal**
   unless removed or placed in `GGUF_INERT_EXACT_PATHS`.
6. **`audit_launcher.py` fails the M2 (and M1) launcher today** — bind host `0.0.0.0`
   vs approved `192.168.20.250`, missing exactly one approved `--served-model-name`,
   `$MODEL_PATH`/`262144` vs required literals/replacements. `launcher-repin.sh` cannot
   render M2 (template lacks M2 gates and hardcodes a different model/host/argv), so there
   is no automated re-pin path for M2; it is hand-installed.
7. **`tools/validate_telemetry.py` in M2 points at the M1 tree** (`SRC=…v1.2.1-candidate/src`)
   and is not invoked by the M2 launcher. If telemetry must be validated in M2, the tool's
   `SRC`/hash bindings need repointing (`pysrc/repoint_telemetry.py`).

## Remaining claims or exclusions

- Not verified: that HiCache-ON M2 retains 24/24 **under the frozen launcher's exact argv**
  (the RCA arm used port 30164 and a scratch driver; the frozen launcher adds
  `--tool-call-parser`, metrics export, etc., and starts on 30000). Runtime revalidation is a
  GPU-window activity and was out of read-only scope.
- Not verified: whether `/data/l3` capacity matters for the chosen config. With
  `hicache_host_memory_mode=cache` (default, no storage backend) the host tier is host RAM;
  `/data/l3` is not used. This artifact did not measure host RAM headroom.
- Not verified: test pass/fail for the telemetry revision; only file-level delta vs frozen
  `src` was established.
- Not established: an authoritative owner-approved exact flag set/values for M2 beyond the
  RCA-minimal set. `--hicache-size 32` is the RCA working value; M1 capacity profile used 48.
  The artifact reports the RCA value as evidence, not as a decision.
- Excluded by scope: any edit, freeze, repin, service restart, or GPU run; verification of
  M1 behavior; auditing memory files outside the enumerated evidence.
- Search limits: reconnaissance was targeted (named files, greps, read-only `diff`/`stat`/
  `git status`); no recursive scan of unrelated private memory or user data was performed.
  `git log`/history was not traversed. `nvidia-smi`/`ss`/`ps` were used only to establish the
  current live state.

## Terminal state: DONE
