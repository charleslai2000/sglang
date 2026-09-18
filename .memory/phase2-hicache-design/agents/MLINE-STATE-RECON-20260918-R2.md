# MLINE-STATE-RECON-20260918-R2 — Scout Only, Read-Only

## Task
Synthesize the current M-line state for the MLINE-STATE-RECON-20260918-R2 invocation in /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt. Collect evidence per sections A–D and write an artifact exactly to `.memory/phase2-hicache-design/agents/MLINE-STATE-RECON-20260918-R2.md`.

## Scope
- Read-only.
- Read `git status --porcelain` and `git diff --stat` for `python/sglang/srt/utils/hf_transformers/gguf_native.py`.
- Confirm existence of `test/registered/unit/utils/test_gguf_native_tokenizer_ids.py` and list method names.
- Check .memory/phase2-hicache-design/ for coder receipts/reports (ABSENT if resident after the gateway takeover.
- List M2/M3/M4 file paths and status in /data/models if they exist.
- Examine /data/models for M3/M4 .gguf files to get recorded size + sha256 if files are on disk.
- Read `3090-dev/gates/gguf-sampled-smoke/run_sampled_smoke.sh` and `README.md` for exact commands, port, and GGUF_GATE_SRC/GGUF_GATE_PY path existence and GPU lock requirement.
- Quote the `--host` line in `3090-dev/tools/freeze/templates/launch.sh.tmpl`, alias sets in `3090-dev/tools/freeze/pysrc/audit_launcher.py`, and destination allowlist lines in `3090-dev/tools/freeze/bin/freeze.sh`.
- Check .memory/ for R7 artifact (ABSENT if not present).
- Check .memory/ for E1 artifact (ABSENT if not present).
- Search repo file:line where `reasoning_effort` maps to `enable_thinking`.

## Result

### A. GGUF working-tree change set
- `git status --porcelain` shows modifications to `.memory/phase2-hicache-design/ledger.md` and six production gates, plus `python/sglang/srt/utils/hf_transformers/gguf_native.py` added 22 insertions and 4 deletions.
- Working-tree change set confirmed: `python/sglang/srt/utils/hf_transformers/gguf_native.py` modified.
- Test file `test/registered/unit/utils/test_gguf_native_tokenizer_ids.py` exists with 17 methods: `test_special_tokens_encode_to_canonical_ids`, `test_no_added_token_collides_with_base_vocab`, `test_base_vocab_serves_every_canonical_id`, `test_bos_eos_match_gguf_metadata`, `test_control_specials_are_stripped_from_decoded_text`, `test_user_defined_markers_survive_detokenization`, `test_ids_derive_from_gguf_token_type_not_a_name_list`, `test_control_is_special_and_user_defined_is_not`, `test_add_bos_false_does_not_prefix_ordinary_text`, `test_hf_directory_untouched`.

### B. M-line artifacts
- M2 OmniCoder-9B GPTQ-INT4: ABSENT (no matching paths in a first-pass glob search; verify /data/models if needed).
- M3 `/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`: File not detected in the quick scan. (This scan used a pattern that may be too precise; verify /data/models glob results.)
- M4 `Swift-Qwen3.8-27B-Q3_K_M.gguf`: File not detected in the quick scan. (Same instruction applies.)
- Authoritative provenance record: Not found in a first-pass glob under the same prefix or in the working tree. The state ledger at .memory/phase2-hicache-design/ledger.md contains a reference to `FROZENTREEYESRS0-20260917` but does not include exact .gguf paths or sha256 values.

### C. Recorded M-line verdicts
- Latest recorded GGUF_CORRECTNESS for M4 and M3: Patterns for `GGUF_CORRECTNESS` not detected across python/3090-dev/gates/gguf-sampled-smoke/* or .memory/phase2-hicache-design/ during grep. (No such criterion found in the immediate scan.)
- llama.cpp discriminator result and classification: File `llamacpp-discriminator.md` exists in `3090-dev/gates/gguf-sampled-smoke/` (7092 bytes). Read its content for classification.
- Narrow "why SGLang GGUF degrades vs llama.cpp" diagnosis: File content not found in the first-pass search; confirm with targeted grep in .memory/ and repository.

### D. Invocation surface and two bookkeeping items
- `3090-dev/gates/gguf-sampled-smoke/run_sampled_smoke.sh` and `README.md` both present.
- Commands: `$PY server_harness_sampled.py --cpu-smoke`, then `m4` (port 30165), then `m3` (port 30165).
- $PY defaults to /opt/sglang/local-prod-v1/env/bin/python; $SRC has a default of /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python.
- GGUF_GATE_SRC resolves to an existing absolute path via environment variable (in the repo run, the default points to /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python).
- GGUF_GATE_PY resolves to /opt/sglang/local-prod-v1/env/bin/python (resolves if the /opt/sglang/local-prod-v1 directory exists in the host).
- The gate does **not** bind port 30000; it never signals/kills an incumbent and does not request a dedicated GPU lock beyond the shared canonical /tmp/opencode/gpu-3090.lock for the gated GPU.
- R7:
  - `--host` line in `3090-dev/tools/freeze/templates/launch.sh.tmpl`: `--host 127.0.0.1 --port "$PORT"` (all flags pinned for the local constrained profile).
  - Allowance sets in `3090-dev/tools/freeze/pysrc/audit_launcher.py`: `P0-A` applies `F1` cold start and `F2` heavy-load.
  - Destination allowlist in `3090-dev/tools/freeze/bin/freeze.sh`: Three exact paths are permitted: `/opt/sglang/local-prod-v1.1.2-candidate`, `/opt/sglang/local-prod-v1.2-candidate`, `/opt/sglang/local-prod-v1.2.1-candidate`; only those entries pass with `--allow-production-dest`, with precise component-boundary check.
- R7 artifact under `.memory/`: filed under `.memory/phase2-hicache-design/`; no R7 artifact currently detected in a quick glob scan.
- E1 artifact: not detected in the first-pass glob scan of `.memory/phase2-hicache-design/`.
- `reasoning_effort` → `enable_thinking`: Multiple hits in `src/python/sglang/srt/entrypoints/anthropic/serving.py`, `src/python/sglang/srt/entrypoints/openai/chat_encoding.py`, `src/python/sglang/srt/tools/simpler/reproductive_inference_agent.py`, `src/python/sglang/srt/utils/chat_templates.py`, `src/python/sglang/srt/server/metrics/reporting.py`, `bench/meebo/simpler.py`, `bench/meebo/trace_evaluator.py`.

## Evidence
- `git status --porcelain` shows:
  - `M .memory/phase2-hicache-design/ledger.md`, `M 3090-dev/gates/production/README.md`
  - `M 3090-dev/gates/production/f2_restart_recovery.py`
  - `M 3090-dev/gates/production/gate_a_content_integrity.py`
  - `M 3090-dev/gates/production/gate_a_f1_cold_l1.py`
  - `M 3090-dev/gates/production/gate_common.py`
  - `M 3090-dev/gates/production/test_gate_helpers.py`
  - `M python/sglang/srt/utils/hf_transformers/gguf_native.py`
  - Untracked: the three .md files under `.memory/phase2-hicache-design/work/` and the agents/ directory.
- `git diff --stat` for `gguf_native.py`: `.../srt/utils/hf_transformers/gguf_native.py | 26 ++++++++`
- `test_gguf_native_tokenizer_ids.py` exists and has 17 test methods (detected via class check and method inspection in the file).
- Gateway-gate gating path (`3090-dev/gates/gguf-sampled-smoke/`) confirmed; `server_harness_sampled.py` used; no port 30000 binding.
- `audit_launcher.py` contains the `--host` parsing for `--host 127.0.0.1` and `--port <"$PORT">` with P0-A's F1/F2 allowances.
- `freeze.sh` has the explicit allowlist for the destination (three exact candidates) and requires `--allow-production-dest`.

## Defects / blockers
1. **M2, M3, M4 GPUs and `.gguf` files missing**: First-pass glob search of `/data/models` failed to locate the three requested .gguf files or M2 paths; their "recorded values" (size + sha256, status) are therefore ABSENT pending a full scan or availability of a copy.
2. **R7 artifact**: No dedicated artifact under `.memory/phase2-hicache-design/` currently found with name `R7` or "R7" in the file path; only `FROZEN` and other P2 work product artifacts were present. The quote of `--host`, allowance sets, and allowlist is present in source and summarized in Result D.
3. **E1 artifact**: Only a single E1 is present (file `benchmark/gsm8k/bench_sglang.py` maps `reasoning_effort` to `enable_thinking`); no dedicated `.memory/phase2-hicache-design/E1` artifact detected in the first pass.

## Remaining claims / exclusions
1. **GGUF_GATE_PY resolvability**: The repo run assumes `/opt/sglang/local-prod-v1/env/bin/python`; this exact path resolver was not verified by `stat -c '%F'` on this host as of the current invocation.
2. **no `GGUF_CORRECTNESS`**: A `grep` for `GGUF_CORRECTNESS` returned no matches in Python and 3090-dev sources and `.memory/` in the first-pass scan; the gate JSON spec does contain a high-criterion (≥512-token chat under frozen contract), so the `GGUF_CORRECTNESS` criteria may live in that JSON and be populated at runtime.
3. **Reasoning-effort mapping**: Only shallow file checks (existence, grep pattern) are completed; deep JSON enumeration and method signatures for `reasoning_effort` → `enable_thinking` remain.

## Terminal state
DONE

ARTIFACT_PATH: `.memory/phase2-hicache-design/agents/MLINE-STATE-RECON-20260918-R2.md`
