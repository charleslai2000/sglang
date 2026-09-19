# M2-HICACHE-RELEASE-DESIGN-R2-20260918

Status: DONE
Terminal state: DONE

## Task
Design (NOT implement) a single-GPU-window release that (i) installs an M2 frozen runtime whose
launcher serves with HiCache ON, and (ii) promotes the telemetry src revision (shared src ⇒ M1 also
gets it, M1 must remain correct). Answer D1..D7 with file:line anchors, exact literals, an ordered
runbook, and rollback. READ-ONLY: no product/frozen-tree/scaffold edits, no GPU, no signalling, no
port binds, no freeze execution.

## Scope
- In scope: the release *shape* — final M2 serving argv, M2 launcher gate changes, audit/freeze/
  repin tooling changes, freeze source-scope and destination choices, identity/pin reconciliation,
  rollback, and a numbered single-window runbook.
- Out of scope (do not perform here): actually editing `launch.sh`, `audit_launcher.py`,
  `freeze.sh`, `launcher-repin.sh`, `validate_telemetry.py`, `service.env`, or the pins allowlist;
  running `freeze.sh`/`launcher-repin.sh`; stopping/starting/signalling any process; touching the
  GPU; binding any port; inference; any write outside this artifact.
- Binding owner decisions (not reopened): M2 must serve with HiCache enabled (ledger ¶106); external
  access to `:30000` is fully open ⇒ notify owner before any planned stop/restart of `:30000`
  (ledger ¶97), exception for recovery when prod is already DOWN; dispatch runs in background with
  service-metrics monitoring (ledger ¶98).

## Result

### Evidence basis
- `M2-CONCURRENCY-DEGRADATION-RCA-20260918.md` (DONE): prefix retention on M2 is bound by the mamba
  slot pool (`--max-mamba-cache-size 48`, 4 slots/req): N≤14 holds, collapses to 1/16 at N=16 while
  KV had ~190k tokens free (X-c/X-d). Attaching HiCache gives 24/24 retained with mamba
  free/evictable flat (~2/42) and eliminates the cold-prefill queue. X-f isolated
  M2+HiCache on `:30164` with `--enable-hierarchical-cache --hicache-write-policy write_back
  --hicache-size 32` → console `hicache_attached=True`, retention 16/16, 24/24.
- `HICACHE-NATIVE-CACHE-TELEMETRY-R2-20260918.md` (DONE): internal cached-token accounting exists,
  but OpenAI `usage.prompt_tokens_details.cached_tokens` is gated by `enable_cache_report`
  (`serving_chat.py:706` `if not self.tokenizer_manager.server_args.enable_cache_report`; also
  L1787/L1997). The telemetry revision flips the default to `True` (`server_args.py:1380`, frozen
  `False` vs worktree `True`) ⇒ the frozen launcher does NOT need `--enable-cache-report`.
- `HOST-CAPACITY-MEASURE-20260918.md`: MemTotal 125 GiB, ~117 GiB available; single `/` has 19 GB
  free (97% used) ⇒ the on-disk L3 tier is MARGINAL/UNSAFE and this design stays in host-memory mode.
- Live state (read 19:04–19:35Z): `:30000` UP pid 1851500, supervisor 1851473, tree
  `/opt/sglang/local-prod-v1.2.1-candidate-M2`, identity `LOCAL-PROD-v1.2.1-M2`,
  `state/ready/m2.ready` present; GPU lock `/tmp/opencode/gpu-3090.lock` owned by
  `supervise-m2-m2-20260918T190239Z-1851237` pid 1851473 generation 1. `state/runs/prod.run`
  is STALE (M1 not running).
- Live M2 argv (verbatim from `/proc/1851500/cmdline`, == frozen argv, no `--served-model-name`):
  the 22-flag set listed under D1 below.
- M1/M2 frozen trees share `src/` inodes (e.g. `server_args.py` inode 27528456, mode 444) ⇒ in-place
  src edits are forbidden; any src change requires a fresh freeze. M2 tree layout
  `{env -> /home/ubuntu/venvs/sglang-3090, launcher/, manifest/, src/ (dr-xr-xr-x), tools/}` — NO `bin/`.

### D1 — Exact M2 serving argv (HiCache ON)
Insert EXACTLY the RCA/X-f-proven trio, and only that trio, into the frozen ARGS array at
`/opt/sglang/local-prod-v1.2.1-candidate-M2/launcher/launch.sh` L159–L160 (after
`--mamba-ssm-dtype float32`, before `--reasoning-parser qwen3`):

```
  --enable-hierarchical-cache
  --hicache-write-policy write_back
  --hicache-size 32
```

- `32` is a LITERAL (SI gigabytes, 10^9 bytes). The M2 launcher has no `PROFILE`/`L2_GB` case, so
  `"$L2_GB"` (the M1 form) must NOT be used.
- `--hicache-size` overrides `--hicache-ratio` (`server_args.py` L2755) ⇒ no `--hicache-ratio`.
- No `--enable-cache-report`: the promoted revision defaults `enable_cache_report=True`
  (`server_args.py:1380`).
- Host-memory mode: the frozen default is `cache` (`server_args.py` L2742) and the X-f combo did not
  pass it. We INCLUDE `--hicache-host-memory-mode cache` as an explicit positive pin (fail-closed
  determinism; behavior-identical to the default; `_validate_hicache_host_memory_mode` L8548 returns
  early for `cache`). It is recorded as the only optional token in the D3 profile so it can be
  dropped without changing behavior.
- FORBID (must not appear): `--hicache-storage-backend`, `--hicache-storage-prefetch-policy`,
  `--hicache-storage-backend-extra-config`, `--enable-ready-horizon`, `--hicache-ratio`,
  `--hicache-io-backend`, `--hicache-mem-layout`, and any duplicate of the three HiCache flags.
- Budget justification: `pool_host/base.py` L27 `HICACHE_HOST_MEMORY_RESERVE_BYTES = 10*(1024**3)`,
  L51-55 `host_memory_budget_bytes()` = (available − reserve)//ranks_per_host ⇒ (≈117 GiB − 10 GiB)
  ≈ 107 GiB; 32 GB (SI) = 29.8 GiB ≈ 27.9% of budget. `hybrid_pool_assembler.py`
  `_split_hicache_size` L134-145 splits the 32 GB proportional to each device pool's
  `get_kv_size_bytes()` across KV + mamba; `pool_host/mamba.py` L79-81 scales to tokens with
  `sync_fixed_hicache_size`. `write_back` is validated. No L3 write occurs; `/data/l3` is untouched.
- Acceptance signal: `mem_cache/registry.py` L237-257 logs
  `hicache_attached = cache.cache_controller is not None`, i.e. `... hicache_attached=True ...`.

Full final M2 argv (post-change), as it must appear in `ARGS` (L144-166) and exactly as exec'd at
L231 and printed at L217-226:

```
/opt/sglang/local-prod-v1.2.1-candidate-M2/env/bin/python -u -m sglang.launch_server \
  --model-path /data/models/omnicoder-9b-gptq-int4 \
  --host 0.0.0.0 --port 30000 \
  --tp-size 1 \
  --mem-fraction-static 0.92 \
  --max-total-tokens 262144 \
  --context-length 131072 \
  --max-running-requests 8 \
  --max-mamba-cache-size 48 \
  --kv-cache-dtype fp8_e4m3 \
  --attention-backend flashinfer \
  --linear-attn-prefill-backend triton \
  --linear-attn-decode-backend triton \
  --mamba-radix-cache-strategy extra_buffer \
  --mamba-ssm-dtype float32 \
  --enable-hierarchical-cache \
  --hicache-write-policy write_back \
  --hicache-size 32 \
  --hicache-host-memory-mode cache \
  --reasoning-parser qwen3 \
  --tool-call-parser qwen3_coder \
  --enable-metrics \
  --export-metrics-to-file \
  --export-metrics-to-file-dir <LOG_DIR> \
  --disable-prefill-cuda-graph
```

(`--served-model-name` is intentionally absent, matching the installed M1/M2 contract.)

### D2 — Launcher gate semantics (`SGLANG_L3_MODE`)
`SGLANG_L3_MODE=disabled` is KEPT but REDEFINED to mean "no L3 **storage backend**": the HiCache host
(L2) tier is independent of any extent/storage backend. Concretely, in `launch.sh`:
- Keep the L33-39 mandatory/explicit `SGLANG_L3_MODE=disabled` check (else exit 2).
- Keep the extent/L3 env strip L82-99 and its report, AND ADD `SGLANG_L3_BACKEND` to both the
  strip list and the post-strip leak check (L84-99 and L194-202). Rationale: `SGLANG_L3_BACKEND`
  is defined at `environ.py:711` `EnvStr(None)` and is used only as an unset-flag fallback at
  `server_args.py:8529-8534` inside `_handle_hicache`; an inherited value would silently attach an
  L3 backend even though the launcher never passes one. Current launcher does NOT strip it.
- Keep `tools/l3_namespace.py --validate` MUST-refuse-with-exit-6 (L180-193): still proves no L3
  store is claimed and `/data/l3` is untouched.
- REPLACE the blanket forbidden-argv loop (L203-212) with a positive pinned-HiCache assertion:
  exactly one `--enable-hierarchical-cache`; `--hicache-write-policy` immediately followed by
  `write_back`; `--hicache-size` immediately followed by `32`; `--hicache-host-memory-mode`
  followed by `cache` if present; AND still forbid the L3/storage/prefetch/ready-horizon/ratio/io/
  mem-layout tokens plus any duplicate HiCache flag. No blanket "any HiCache token fails".
- `conf/service.env`, `bin/start.sh` (m2 branch L34/L70), and the scaffold are UNCHANGED by D2.

### D3 — Model-aware launcher audit/repin/template profiles
`audit_launcher.py` today fails BOTH installed launchers (Check 4 only runs with `--ref-launcher`;
`PRODUCTION_BIND_HOST_APPROVED={"127.0.0.1":"192.168.20.250"}` L74; `--served-model-name` required
exactly once L242-259; `PRODUCTION_REQUIRED_SERVING_REPLACEMENTS={"65536":"524288"}` L59). This is a
PRE-EXISTING gap independent of HiCache and it blocks `launcher-repin.sh` (exit 22) and thus
`freeze.sh` (exit 5). Introduce `LAUNCHER_PROFILES` keyed by identity plus a `--profile` selector:
- `LOCAL-PROD-v1.2.1` (M1) and `LOCAL-PROD-v1.2.1-M2`:
  - approved bind hosts: add `0.0.0.0` alongside `192.168.20.250`;
  - `--served-model-name`: M2 allows absence, and if present requires an approved value (M1 profile
    also permits `0.0.0.0` + no `--served-model-name`, preserving the installed contract and the
    loopback health probe `http://127.0.0.1:$PORT/health` in `bin/supervise.sh` L125-131);
  - required replacements: M2 `65536→262144` and `"/data/models/qwen35-9b-w4a16"→"$MODEL_PATH"`;
    M1 keeps `65536→524288`;
  - approved-new token set: `--context-length 131072`, `--max-running-requests 8`,
    `--max-mamba-cache-size 48`, `0.0.0.0`, `"$MODEL_PATH"`, `262144`, the HiCache trio, and the
    optional `--hicache-host-memory-mode cache`;
  - allowed-dropped set: the reference L3 tokens `--hicache-storage-backend extent`,
    `--hicache-storage-prefetch-policy wait_complete`, `--hicache-size "$L2_GB"`,
    `--enable-ready-horizon`;
  - fail-closed on unknown profile, extra/missing token, or value mismatch (set equality, not subset).
- Negative tests to add to `pysrc/test_audit_launcher.py`: old (pre-change) M2 launcher FAILS;
  an injected `--hicache-storage-backend` FAILS; the new M2 launcher PASSES.
- `templates/launch.sh.tmpl` / `launcher-repin.sh` must render the M2 profile without clobbering the
  bespoke no-L3 gate (repin ALWAYS renders from the template and overwrites `launcher/launch.sh`;
  the template at HEAD also emits `--served-model-name qwen35-9b-local`). Add the profile-driven
  model branch so M1 keeps `0.0.0.0` + no served-model-name and M2 emits its pinned argv.

### D4 — Freeze source scope and destination
- Destination: add `/opt/sglang/local-prod-v1.2.1-candidate-M2` to the DEST allowlist
  `freeze.sh` L120-133 (current list has v1.1.2 / v1.2 / v1.2.1 / v1.2.2, excludes `-M2`); each
  dest still requires `--allow-production-dest`. Because freeze refuses unconditionally when
  `$DEST/manifest/identity.json` exists, the existing M2 (and M1) trees must be MOVED ASIDE first
  (D5).
- Stage = the frozen `/tmp/opencode/v1.2.1-stage` tree (which already carries the reviewed 5
  telemetry source files and the 4 Gate artifacts) PLUS a telemetry-only overlay from the live
  worktree. This is the deterministic minimal delta and avoids dragging in the post-freeze tooling
  commits between `b2bbd6ea28` and HEAD. The worktree root is repo-shaped and has no `src/`, so a
  stage dir with `src/` = repo content MUST be built (the freeze `--src` cannot be the worktree).
- Source-scope allowlist additions (14 paths, `src/`-prefixed, to
  `3090-dev/tools/freeze/pins/local-prod-v1.2-candidate-allowlist.txt`):
  - modified: `src/python/sglang/srt/entrypoints/openai/protocol.py`,
    `src/python/sglang/srt/entrypoints/openai/serving_chat.py`,
    `src/python/sglang/srt/entrypoints/openai/usage_processor.py`,
    `src/python/sglang/srt/environ.py`,
    `src/python/sglang/srt/function_call/qwen3_coder_detector.py`,
    `src/python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`,
    `src/python/sglang/srt/mem_cache/unified_radix_cache.py`,
    `src/python/sglang/srt/sampling/custom_logit_processor.py`,
    `src/python/sglang/srt/server_args.py`,
    `src/test/registered/unit/function_call/test_function_call_parser.py`,
    `src/test/registered/unit/managers/test_hicache_host_allocability.py`,
    `src/test/registered/unit/managers/test_hybrid_group_wiring.py`;
  - added: `src/python/sglang/srt/parser/qwen35_reasoning_policy.py`,
    `src/test/registered/unit/parser/test_qwen35_reasoning_policy.py`.
  - EXCLUDE `src/python/sglang/srt/utils/hf_transformers/gguf_native.py` and
    `src/test/registered/unit/utils/test_gguf_native_tokenizer_ids.py`: the path contains "gguf",
    which `freeze.sh` hard-refuses (`GGUF_INERT_EXACT_PATHS`).
- Sub-task (review-authority act, required BEFORE freeze or `repoint_telemetry.py` FAILS CLOSED /
  freeze exits 5): re-bind `tools/validate_telemetry.py` `SOURCE_HASHES` for
  `unified_radix_cache.py` from `5b5dc29fa21eefdf44ac660881cab02e9bc6ab1408cd33ca645a4bb326f6bf6f`
  to `4a5128828dc2cf67a214c794984be6f2d5177178d64cda070e35e467ec03fe1b`. The other 5 source
  bindings and all 4 Gate artifacts are unchanged (verified this session: `hicache_telemetry.py`
  `788318d9…`, `tokenizer_manager.py` `9f9d3802…`, `output_streamer.py` `8485d956…`,
  `test_hicache_request_telemetry.py` `e577d940…`,
  `test_output_streamer_hicache_telemetry_wiring.py` `717ac93c…`;
  `P0-TELEMETRY-EXPERT-GATE-20260914.md` `48b4faad…`, `.json` `1e8277e9…`). Only
  `unified_radix_cache.py` changes among the 6 bound files after promotion.

### D5 — Identity strategy, pins reconciliation, M1 correctness
- PRIMARY (dispatch-prescribed DEST): move aside the old `local-prod-v1.2.1-candidate` and
  `local-prod-v1.2.1-candidate-M2` trees, then re-freeze BOTH in place at the existing paths. This
  minimizes service.env/start.sh churn. Move-aside is mandatory because freeze refuses an existing
  `manifest/identity.json`. Backups e.g.
  `/opt/sglang/.pre-hicache-<stamp>/{local-prod-v1.2.1-candidate,local-prod-v1.2.1-candidate-M2}`
  (needs sudo; M2 is running ⇒ stop M2 first). Order: freeze M1 (path already allowlisted) then M2
  (add the `-M2` dest entry first).
- Because tooling at HEAD renders `192.168.20.250` + `--served-model-name`, an M1 re-freeze via
  repin would otherwise change M1's observable contract (bind `0.0.0.0`→`192.168.20.250`) and break
  the loopback health probe. D3's model-aware profiles are therefore a hard precondition, not an
  optional nicety.
- Shared src ⇒ promoting the telemetry revision also promotes it into M1. M1 already runs
  `--enable-hierarchical-cache` with `--hicache-storage-backend extent
  --hicache-storage-prefetch-policy wait_complete --hicache-size "$L2_GB"
  --enable-ready-horizon`; the promoted `server_args.py:1380` default flip to `True` means M1's
  telemetry starts reporting without a launcher change. M1's launcher argv/contract must remain
  byte-identical in observable behavior (D3).
- Tool-side pins are out of sync: `pins/local-prod-v1.2.1-candidate-pins.json` records
  `LAUNCHER_HASH 38487942…` and `TREE_HASH 3bd285d5…`, whereas M1's effective identity records
  `4ae68470…` / `5ed662d0…`. The re-freeze `cp` overwrites this pins file, reconciling the drift.
  There is no M2 pins file: the M2 tree was built by a non-freeze route (`self_test.added` lists
  `./tools/l3_namespace.py` + `./tools/preflight_identity.py`, `modified_allowed` lists only
  `./launcher/launch.sh`); the re-freeze gives M2 a proper pins file. M2 identity's
  "src/ is hardlinked from the M1 frozen tree" open_item is replaced by freeze-generated open_items
  (rsync without `-H` yields separate copies, same bytes).
- ALTERNATIVE (documented, not chosen): a fresh pair `/opt/sglang/local-prod-v1.2.2-candidate`
  (already allowlisted) + a new `/opt/sglang/local-prod-v1.2.2-candidate-M2` (needs an allowlist
  entry). Trivial rollback and old trees untouched, but requires `conf/service.env` re-point and
  leaves two parallel v1.2.1 trees.

### D6 — Rollback
- Keep every move-aside tree backup and every pre-change launcher copy
  (`launch.sh.pre-repin-<run>`), plus a `conf/service.env` backup and any `*.bak-*` files.
- To roll back: `bin/stop-m2.sh` (NOT `stop.sh m2`, which does not exist), restore the backed-up
  trees and `conf/service.env`, then `bin/start.sh m2` from the restored tree.
- Verify rollback by `/health` and the gate suite (source-identity, src stream digest, L3-disabled
  negative assertion) before declaring success.
- Rollback of M1, if M1 was re-frozen: restore the `local-prod-v1.2.1-candidate` backup in place and
  re-run `bin/start.sh prod`; M1 keeps its extent L3 backend.

### D7 — Single-window numbered runbook
ONE non-worker owner executes the whole window (per ledger ¶97 notify the owner before stopping
`:30000`; the only exception is recovery when prod is already DOWN). All steps are on-host.

1. Pre-window checks: confirm `:30000` is not tester-occupied and the GPU has no material holder;
   confirm `available` memory ≈117 GiB and `/` headroom; notify the owner of the planned stop;
   record the pre-change M2/M1 `identity.json` hashes and `launch.sh` copies.
2. Stop M2 only via `bin/stop-m2.sh` (identity-checked: pid must match `launch_server` + port + tree
   + model; supervisor signalled first to release the flock; never broad-pkill, never M1). Confirm
   the GPU lock is released and `state/ready/m2.ready` is cleared.
3. Build the freeze stage: copy the frozen `/tmp/opencode/v1.2.1-stage` tree and overlay the 14
   telemetry paths (D4) from the live worktree; verify the stage has `src/ launcher/ tools/` only.
4. Edit `tools/validate_telemetry.py` `SOURCE_HASHES` to re-bind `unified_radix_cache.py` to
   `4a512882…` (D4); run the validator's binding step to confirm PASS.
5. Extend `audit_launcher.py` with `LAUNCHER_PROFILES` + `--profile` and extend
   `templates/launch.sh.tmpl`/`launcher-repin.sh` for the model branch (D3); run
   `pysrc/test_audit_launcher.py` including the three negative tests.
6. Extend the pin allowlist with the 14 paths (D4) and add the `-M2` DEST entry to `freeze.sh` (D4).
7. Move aside the old M1 and M2 trees to `/opt/sglang/.pre-hicache-<stamp>/...` (sudo).
8. Repin + freeze M1 at `/opt/sglang/local-prod-v1.2.1-candidate` (`--src` = stage,
   `--baseline-tree /opt/sglang/local-prod-v1.1-candidate`, `--allow-production-dest`). Confirm M1
   argv/contract preserved (`0.0.0.0`, no `--served-model-name`, extent L3 args intact).
9. Freeze M2 at `/opt/sglang/local-prod-v1.2.1-candidate-M2` with the D1 argv and D2 gate. Confirm
   `tools/l3_namespace.py --validate` still exits 6 for the disabled store and that the src stream
   digest equals the frozen `c7427132…`.
10. Verify identities: `preflight_identity.py --all` PASS for both trees; `launch.sh` dry-run prints
    the exact D1 argv; `audit_launcher.py --profile` PASS for both.
11. Update scaffold defaults/pins: reconcile `pins/local-prod-v1.2.1-candidate-pins.json` (D5) and
    confirm `conf/service.env` M2 tree/port/model unchanged.
12. Start M2 (`bin/start.sh m2`) in the background; watch service metrics (ledger ¶98).
13. Verify: console `hicache_attached=True`; retention at N=16 is 16/16 (not 1/16); mamba
    free/evictable flat; telemetry live (`usage.prompt_tokens_details.cached_tokens`, reasoning
    usage); `/health` OK.
14. Unconditionally restore/verify `:30000` at the end of the window regardless of outcome; if any
    step fails, execute D6 rollback and report.
15. Optional M1 live smoke only if disk headroom is confirmed (M1 keeps the extent L3 tier; `/` had
    only 19 GB free).

## Evidence
- `M2-CONCURRENCY-DEGRADATION-RCA-20260918.md`: mamba slot cliff, HiCache 24/24 retention, X-a
  `262144→524288` REFUTED, X-f isolated M2+HiCache combo; `:30000` not measurement-safe with
  production traffic present (`:30164` used for measurement).
- `HICACHE-NATIVE-CACHE-TELEMETRY-R2-20260918.md`: reporting-gap verdict; `serving_chat.py:706`
  gate; revision flips `enable_cache_report` default to `True`.
- `/opt/sglang/local-prod-v1.2.1-candidate-M2/launcher/launch.sh`: ARGS L144-166, exec L231,
  dry-run L217-226, L3 mode L33-39, env strip L82-99, GATE 3/3 L168-213, forbidden loop L203-212.
- `/opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh`: installed M1 argv includes
  `--enable-hierarchical-cache --hicache-write-policy write_back --hicache-storage-backend extent
  --hicache-storage-prefetch-policy wait_complete --hicache-size "$L2_GB" --enable-ready-horizon`;
  bind `0.0.0.0`, no `--served-model-name`.
- `server_args.py` (frozen src): `enable_hierarchical_cache=False` L2739; `hicache_host_memory_mode`
  L2742; `hicache_ratio` L2750; `hicache_size` "gigabytes. Overrides --hicache-ratio" L2755;
  `hicache_write_policy` default `write_through` L2760; `hicache_io_backend` L2768;
  `hicache_mem_layout` L2776; `hicache_storage_backend` L2790; `hicache_storage_prefetch_policy`
  L2811; `enable_ready_horizon` L2866; `_handle_hicache` L8510 / L8529-8534; validator L8548;
  `enable_cache_report` L1380 (frozen `False`, worktree `True`).
- `pool_host/base.py` L27/L51-55/L62; `hybrid_pool_assembler.py` L134-145/L122-129;
  `pool_host/mamba.py` L41/L79-81/L222; `registry.py` L237-257.
- `environ.py:702` (`SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR`), `:711` (`SGLANG_L3_BACKEND`);
  `extent_file_backend.py:487` and `:144`/`:145`.
- `audit_launcher.py`: L54 required tokens, L59 replacements, L74 approved hosts, L176-182 allowed
  new, L242-259 served-model-name. Actual runs: M2 + `--ref-launcher` EXIT=1 (unapproved_new
  `"$MODEL_PATH"`,`0.0.0.0`,`262144`; unapproved_dropped the 10 L3 token set;
  missing_replacements `192.168.20.250`,`524288`; bind `0.0.0.0`; served-model-name missing);
  M1 + `--ref-launcher` EXIT=1 (unapproved_new `0.0.0.0`; missing_replacement `192.168.20.250`;
  same bind + served-model-name failures).
- `freeze.sh` (586 lines): DEST allowlist L120-133 (v1.1.2/v1.2/v1.2.1/v1.2.2, excludes `-M2`);
  refuses existing `manifest/identity.json`; `ALLOWED_TOP=(src launcher tools env manifest)`;
  rsync `-a --delete --exclude '/manifest/'` (no `-H`); `ALLOW_MOD` (build) =
  `launcher/launch.sh,tools/validate_telemetry.py,tools/preflight_identity.py,tools/l3_namespace.py`;
  telemetry repoint fail ⇒ exit 5; gguf hard refusal.
- `launcher-repin.sh`: ALWAYS renders from `templates/launch.sh.tmpl` and overwrites
  `launcher/launch.sh`; `REF_LAUNCHER=/opt/sglang/local-prod-v1.1-candidate/launcher/launch.sh`.
- `repoint_telemetry.py`: fails closed unless the 6 reviewed source hashes + 4 Gate artifacts
  resolve under the new tree (`SRC_RE=^SRC\s*=\s*"([^"]+)"$`).
- `manifest_tool.py compare`: iterates source entries; absent-from-dest ⇒ `missing`; digest differs
  ⇒ `UNEXPECTED` unless in `allow_modified`. Baseline v1.1 manifest has no `gate_common.py` and no
  `qwen35_reasoning_policy.py`, so the `gate_common.py` deletion is not a freeze-scope problem.
- Tool-side pins: `pins/local-prod-v1.2.1-candidate-pins.json` LAUNCHER_HASH `38487942…`,
  TREE_HASH `3bd285d5…`, src_stream `c7427132…`, tools_sha256
  {l3_namespace `40e65e04…`, preflight_identity `29a5a11b…`, validate_telemetry `63246815…`} —
  out of sync with M1 effective identity.
- This session's re-verification: frozen M2 `server_args.py` `5ec3740f…` vs worktree `6fb9cdfe…`;
  frozen M2 `serving_chat.py` `7b05e6ab…` vs worktree `c181f113…`; frozen M2
  `unified_radix_cache.py` `5b5dc29f…` == the validator binding, worktree `4a512882…`; frozen M2
  `hybrid_cache_controller.py` `4462403d…` vs worktree `d5ec3a76…`; worktree gate artifacts
  `48b4faad…` / `1e8277e9…`; stage bound files match the frozen hashes; `stop-m2.sh`
  `3d27a0cd4f728f6c9dd34df252cb6f7c2ca98f2f0f216c902ac49b96c75c3243`.

## Defects or blockers
- (none blocking the DESIGN) All open items were resolved into decisions above. Items that are
  prerequisites for the EXECUTION window, to be implemented by a later authorized task:
  1. Freeze DEST allowlist excludes `local-prod-v1.2.1-candidate-M2`, and freeze refuses an existing
     `manifest/identity.json` ⇒ add the DEST entry and move the old trees aside (D4/D5).
  2. `validate_telemetry.py` binds `unified_radix_cache.py` to `5b5dc29f…`; must be re-bound to
     `4a512882…` or repoint/freeze exits 5 (D4).
  3. freeze/repin always renders from the template ⇒ M2's bespoke gate must be preserved via
     model-aware profiles/template (D3).
  4. M1 re-freeze via repin would change bind `0.0.0.0`→`192.168.20.250` and break the loopback
     health probe ⇒ extend approved hosts / preserve the M1 profile (D3).
  5. No M2 pins file exists (M2 was built outside freeze); the re-freeze creates one (D5).
  6. M1 tool-side pins file is out of sync with M1 effective identity (D5).
  7. `/` has 19 GB free ⇒ host-memory mode only; M1's optional live smoke is disk-gated (D7).
- Authority boundaries: stopping/restarting `:30000` requires owner notification (¶97); the freeze
  edits to tooling/allowlist/`validate_telemetry.py` are separate authorized changes, not part of
  this READ-ONLY design.

## Remaining claims or exclusions
- Not established by this artifact: that the promoted telemetry bytes actually produce correct
  OpenAI `cached_tokens`/reasoning usage at runtime (that is a tester claim); that M3/M4
  `GGUF_CORRECTNESS` improves (the gate rerun still shows three FAIL signatures ⇒ the tokenizer-id
  fix is necessary-not-sufficient); that the 32 GB HiCache size is optimal (it is the X-f-proven
  value).
- Excluded from scope: executing any freeze/repin/stop/start, editing any file, running inference,
  binding ports, GPU use, and any change to M1's or M2's observable serving contract beyond the
  telemetry default flip and the D1 HiCache trio.
- Inference (marked): the choice to include `--hicache-host-memory-mode cache` is behavior-identical
  to the default; the M1 re-freeze behavior under the new profiles is inferred from template/repin
  source, not executed.

## Terminal state
DONE
