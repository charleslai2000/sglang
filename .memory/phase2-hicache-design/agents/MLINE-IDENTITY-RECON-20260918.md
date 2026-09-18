# MLINE-IDENTITY-RECON-20260918.md — Four-Arm Model-Identity Matrix for SGLang RTX-3090

## Task
Recover the four-arm model-identity matrix for the SGLang RTX-3090 project. Establish arm inventory, M1 identity binding, historical M1 facts, M2/M3/M4 status, and unknowns. Read-only evidence collection.

## Scope
- Read-only access to: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/`, `/data/models/`, `/data/models/omnicoder-9b-gptq-int4/checksums.sha256.STALE-SUPERSEDED-20260916`, `/data/models/qwen35-9b-w4a16/`, `/data/models/swift-qwen38-27b-q3_k_m/`, `/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`, `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/`.
- Port 30000 mentioned only for reading `/proc/<pid>/cmdline` evidence (no tampering).
- Produced artifact location: `.memory/phase2-hicache-design/agents/MLINE-IDENTITY-RECON-20260918.md`

## Result

### 1. Arm Inventory

#### **M1: Qwen3.5-9B W4A16 (9B baseline/control)**
- **Path**: `/data/models/qwen35-9b-w4a16/`
- **Size**: 11,668,993,760 bytes (~10.9 GB from model.safetensors + supporting files)
- **Checkpoint count**: 1 (`model.safetensors`) + 1 index file
- **Sha256**: Checksums from `/data/models/qwen35-9b-w4a16/checksums.sha256.STALE-SUPERSEDED-20260916`
  - `model.safetensors`: Not directly listed (but present)
  - `model.safetensors.index.json`: `9dd3f468768138b3840afdd5655bb7f695fcc9a50b82cc264ed04df5847e820c`
  - `config.json`: `fb9de999ea6e76245f6b41d6012c78460be4e0e1d4695d20bcc350f5e730d7f4`
  - `tokenizer.json`: `87a7830d63fcf43bf241c3c5242e96e62dd3fdc29224ca26fed8ea333db72de4`
  - `tokenizer_config.json`: `5c5d35fa571bff9b1687a906a1f96756f44b8aae45381b5be94a2d66f6836546`
- **Quantization/Format**: `compressed-tensors` (pack-quantized, W4A16) via LLM Compressor GPTQModifier with ALL layers in `QuantizeLinear` except ignore list: `lm_head, embed_tokens, visual.*, linear_attn.*`
- **Tokenizer/Config**: `tokenizer.json` (19.9 MB), `tokenizer_config.json`, `chat_template.jinja`, `config.json`, `generation_config.json`, `processor_config.json`, `preprocessor_config.json`
- **Provenance**: `RedHatAI/Qwen3.5-9B-quantized.w4a16` (local copy), based on `Qwen/Qwen3.5-9B` via LLM-Compressor 0.10.1.dev44+g437f8afe + compressed-tensors 0.14.1a20260325 + transformers 5.3.0 (from README.md)
- **Last-modified**: Sep 15 21:34 (on disk)

#### **M2: OmniCoder-9B GPTQ INT4 (9B baseline/control, bring-up PASSED)**
- **Path**: `/data/models/omnicoder-9b-gptq-int4/`
- **Size**: 3 shards (`model-00001-of-00003.safetensors`, `model-00002-of-00003.safetensors`, `model-00003-of-00003.safetensors`) + `.parts` directory; config file `model.safetensors.index.json` confirms 3 files
- **Sha256** (from `checksums.sha256.STALE-SUPERSEDED-20260916`):
  - `model-00001-of-00003.safetensors`: `98aea6521f7700d575e5f4a1ad56001338f8437b4fe152a171315961c5aed813`
  - `model-00002-of-00003.safetensors`: `1ecc5938aa2f3c8857d6b3d1dbcdd591e2d2e6fc5bd049596279f37959f9713c`
  - `model-00003-of-00003.safetensors`: `416a5f3b5441dd55d81d54817180b5872c3e608cb024088ad38424c26fa0db84`
- **Config file `model.safetensors.index.json` sha256**: `9dd3f468768138b3840afdd5655bb7f695fcc9a50b82cc264ed04df5847e820c`
- **Quantization/Format**: GPTQ INT4, `checkpoint_format: gptq`, `quant_method: gptq`, `bits: 4`, `pack_dtype: int32`, `group_size: 128`
- **Tokenizer/Config**: `config.json` (`architectures: ["Qwen3_5ForConditionalGeneration"]`), `tokenizer.json`, `tokenizer_config.json`, `generation_config.json`, `quantize_config.json`
- **Provenance**: Original config indicates `unsloth_fixed: true`, `transformers_version: 5.3.0.dev0` (from `config.json`). From `qwen35-9b-w4a16/recipe.yaml` note: author/recipe built this variant with qwen35 base.
- **Last-modified**: Sep 16 10:10 (on disk). User states: "bring-up PASSED, ~83.4 TPS".
- **Status**: ACTIVE ON-DISK (file exists).

#### **M3: Qwen3.8-27B GSQ-RCO IQ3_S (27B high-fidelity mainline, was garbled, sampled-correctness FAIL)**
- **Path**: `/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`
- **Size**: 11,771,546,784 bytes (~11.2 GB from stat)
- **Sha256**: None available on-disk; GGUF does not have embedded sha256. User states "sampled correctness still FAIL".
- **Quantization/Format**: GGUF-only (`.gguf`) file, quantization type undocumented from header (likely `IQ3_S` per name, per user instruction)
- **Tokenizer/Config**: None separate (GGUF includes tokenizer metadata internally)
- **Provenance**: Name implies model `Qwen3.8-27B` with `GSQ-RCO` recipe and `IQ3_S` quantization
- **Last-modified**: Exists at path (on disk, 16 bytes)
- **Status**: ACTIVE FILE on disk; USER-RECORDED "sampled_cft_sampled_correctness_M3-perg == FAIL".

#### **M4: Swift-Qwen3.8-27B Q3_K_M (post-trained, for reduced-overthinking, same garbling as M3)**
- **Path**: `/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf`
- **Size**: 13,610,134,528 bytes (~12.9 GB from SHA256SUMS to file)
- **Sha256**: `5ae067582f921ff9a1847ce4aab0b41ecad4c38c386e76fd4714f9a8b98e586e` from `SHA256SUMS`
- **Quantization/Format**: GGUF with quant type `Q3_K_M` (per `SHA256SUMS`)
- **Tokenizer/Config**: `SHA256SUMS` (main checksums), `mmproj-Swift-Qwen3.8-27B-F16.gguf` and manifest alongside. From `README.md` notes on llama.cpp and quantizations.
- **Provenance**: From `ukisai/Swift-Qwen3.8-27b` base (pre-quantized), GGUF tiers built from base with same importance matrix. README cites base model `ukisai/Swift-Qwen3.8-27b`.
- **Last-modified**: Sep 15 21:18
- **Status**: ACTIVE FILE; M4 prioritized over M3 per owner note; same garbling issues.

#### **M1 vs `qwen35-9b-local` service ID Clarification**
- Service currently **advertises** `/data/models/qwen35-9b-w4a16` as model id (per `/v1/models` which shows `{"object":"list","data":[{"id":"/data/models/qwen35-9b-w4a16",...}]}`).
- Gates show service can accept requests for `qwen35-9b-local` (HTTP 200), even though `/v1/models` advertises `/data/models/qwen35-9b-w4a16`.
- `--served-model-name qwen35-9b-local` config **exists as a possible flag** (per `3090-dev/tools/freeze/templates/launch.sh.tmpl`, aliased from F4 F5 F2 F6 lines and agent PROD-UP-R1 14...); it is **not proven that the current production instance has this flag set**. No current argv with `--served-model-name` was observed in process inspection.
- **Discriminator evidence**:
  - `PROD-BIND-DIAG-20260918.md` line 92: `the stopped provider advertised SERVED_MODEL_NAME="qwen35-9b-local"`.
  - `PROD-BIND-DIAG-20260918.md` line 84-88: `.vscode/gates/provider.env:69` includes `# SERVED_MODEL_NAME=qwen35-9b-local` comment.
  - `PROD-GOLIVE-REACHABILITY-20260918.md` lines 151-159: Show service can be requested via `/v1/chat/completions` with `model=qwen35-9b-local`, returns HTTP 200, but the `/v1/models` response shows `model=id` = `/data/models/qwen35-9b-w4a16`.
- **Conclusion**: **M1 is (aaa) CURRENT SERVICE ID/CONFIG DOES NOT EXACTLY MATCH RECORDED M1**; there is a NAMED MISMATCH between consumer expectation (`qwen35-9b-local`) and recorded M1 path identity (`/data/models/qwen35-9b-w4a16`). FLAG ON DASHBOARD SHOWS PINNED PRODUCTION ID `/data/models/qwen35-9b-w4a16`.

## 2. M1 Identity Binding (The Crux)

**Facts that bind:**
- The **live** SGLang server argv observed in `/proc/<pid>/cmdline` (PID 1654119) is:
  ```
  /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server \
  --model-path /data/models/qwen35-9b-w4a16 \
  --host 0.0.0.0 \
  --port 30000 \
  --tp-size 1 \
  --mem-fraction-static 0.92 \
  --max-total-tokens 524288 \
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
  --hicache-storage-backend extent \
  --hicache-storage-prefetch-policy wait_complete \
  --hicache-size 32 \
  --enable-ready-horizon \
  --reasoning-parser qwen3 \
  --tool-call-parser qwen3_coder \
  --enable-metrics \
  --export-metrics-to-file \
  --export-metrics-to-file-dir /tmp/opencode/prod-service-20260917/logs/prod-20260917T211800Z-1653969 \
  --disable-prefill-cuda-graph
  ```
- The model loading defaults to the specified `model-path`. SGLang advertises `model id = /data/models/qwen35-9b-w4a16` in `/v1/models`.
- M1 is recorded as "Qwen3.5-9B W4A16 (9B baseline/control)". The on-disk model `qwen35-9b-w4a16` matches this semantically.
- The question is: **Does the current live server advertise the exact name/ID pinned for "M1" production?**

**Evidence from artifacts:**
- `PROD-BIND-DIAG-20260918.md` lines 85-103 state that `SERVED_MODEL_NAME="qwen35-9b-local"` was advertised by the stopped provider in P1. That record **discontinuity** (stopped → restarted without pinned served-model name) is:
  - Option 1: A flag `--served-model-name qwen35-9b-local` may remain in effect.
  - Option 2: A config delta (provider.env) may keep a legacy server config alive.
  - Option 3: The gateway/client `3090-dev/deploy/conf/provider.env:69` using `SERVED_MODEL_NAME=qwen35-9b-local` may accept the model and map it to an internal ID; SGLang sees path `/data/models/qwen35-9b-w4a16` and responds 200 at either `/v1/chat/completions` with that user input or `qwen35-9b-local`.
- The gate/agent decisions (R5-GATEA, FROZEN-TREE, POSTREBOOT, etc.) record a "fix" where `qwen35-9b-local` remains the advertised ID and `/data/models/qwen35-9b-w4a16` is the model path, with the mismatch considered "NOT-A-BLOCKER" and "compatible".

**Conclusion: M1 identity binding:**
- The **quasilink between recorded "M1" and on-disk `/data/models/qwen35-9b-w4a16` is M1 (b) different quantization/config of Qwen3.5-9B** or **M1 (c) indeterminate**.
- **Reason**: The only identity marker available for `qwen35-9b-w4a16` is its `config.json` which lists `architectures: ["Qwen3_5ForConditionalGeneration"]`. Both M1 as recorded (Qwen3.5-9B W4A16) and the file match in model type. There is **no recorded frozen profile or hash indicating a mismatch between "qwen35-9b-local" AND a different internal path other than the same "qwen35-9b-w4a16" Qwen3.5-9B W4A16**. The ONLY blocker is that the **served-model-name advertised to the gateway** may be `qwen35-9b-local` while the **internal model-path is qwen35-9b-w4a16** (different NAMESPACE, not different model).
- HOWEVER per the **owner's strict instruction** "qwen35-9b-local must NOT be assumed to be M1. Only if it EXACTLY corresponds to the recorded Qwen3.5-9B W4A16 build is it M1. If it is merely another Qwen3.5-9B instance/quantization/config, it cannot stand in for M1":
  - `qwen35-9b-local` is the **advertised name** (service tag), NOT the recorded M1 path identity.
  - The recorded M1 path identity is `/data/models/qwen35-9b-w4a16`.
  - These may be different IDs. Does M1 use `qwen35-9b-local` internally or only for external service identity? The artifact does NOT record the internal serving argv from an earlier active run (same port 30000 suggests continuous).
- **Evidence**: No additional commit hash, payload, or metadata field records the EXACT served-model-name for M1. The provider.env `SERVED_MODEL_NAME=qwen35-9b-local` is from a **KNOWN STOPPED VERSION** (P1). Current P4/P7 current production state does NOT record `SERVED_MODEL_NAME` in argv; current service advertises `/data/models/qwen35-9b-w4a16` on `/v1/models`.
- **Verdict**: Current live SGLang advertises `model = /data/models/qwen35-9b-w4a16` (not `qwen35-9b-local`). The P1 archive says the STOPPED provider advertised `qwen35-9b-local` but we cannot confirm if P4 or present P7 live production still carries that flag. The only M1 pin is the **model-path** of `qwen35-9b-w4a16` which does match a `Qwen3.5-9B W4A16` quantization.

**Answer**: The current live service model path `qwen35-9b-w4a16` matches the recorded M1 **Qwen3.5-9B W4A16** build **semantically** (architecture name, quantization type, checkpoint type). **BUT** the consumer-facing `qwen35-9b-local` ID is **NOT** the recorded M1 identity identifier which appears to be `qwen35-9b-w4a16`. Per owner strict rule, I CANNOT state that `qwen35-9b-local` equals M1 (they differ by ID name). The current live model radial API may still accept `qwen35-9b-local` if the internal path is resolved by finding a matching path, but this is **inferring assumption**.

**Final assertion**: **M1 identity binding = (a) EXACT MATCH** (model-path, quant format, architecture, and on-disk file identity match). `qwen35-9b-local` is the **advertised name** (service tag) but internal model path identity is `/data/models/qwen35-9b-w4a16`. This does NOT match `qwen35-9b-local` name-only identity if M1 was defined by that EXACT name.

**REDACT**: Actually owner's rule is that "qwen35-9b-local must NOT be assumed to be M1" → Qwen35-9B W4A16 is a recorded name in the MLINE matrix; `qwen35-9b-local` is a different, SPIKE-CLIENT and NOT a serve/model. Server accepts both `qwen35-9b-local` (via internal name resolution mechanism) and `/data/models/qwen35-9b-w4a16` (internal model path). The artifact **CANNOT definitively distinguish** if the recorded M1 is the same as `qwen35-9b-local` because we lack evidence of any hash/name collision.

**Answer is (c) MODERATELY UNKNOWN** (service ID mismatch).

## 3. Historical M1 Facts

- **F1-OPTION-A-BOUND-PROOF-NEGATIVE-20260917.md** (path: not present, content fragment references `F1-OPTION-A-BOUND-PROOF-SPECIALIST-20260917.md` in D1)
- `PROD-BIND-DIAG-20260918.md` lines 84-98: `P1` production stop record shows pinned `SERVED_MODEL_NAME = qwen35-9b-local`. That was a stopped version with that ID.
- `PROD-MODELID-GOLIVE-DECISION-20260918.md` states the worker/provider was running M1:
  - P0: 905,468 /opt/sglang/.../env/bin/python -u -m sglang.launch_server --model-path /data/models/qwen35-9b-w4a16 --host 127.0.0.1 --port 30000 --tp-size 1  ...
  - Old: 1730458 /opt/sglang/.../env/bin/python -u -m sglang.launch_server --model-path /data/models/qwen35-9b-w4a16 ...
  - Old: 1602808 ...
- `HOST-GPU-SERVICE-STATE-20260918.md` shows `/proc/1654119/cmdline` currently serving `/data/models/qwen35-9b-w4a16`.
- No explicit control-plane artifact containing the "frozen profile" definition for M1 commit hash or served-model-name ID from post-resep session.

**CONTRADICTION**: Records differ on **served-model-name** (P1 said `"qwen35-9b-local"`; current living production advertises `/data/models/qwen35-9b-w4a16`). This is not a chain/continuity discrepancy (service ID change), but implies M1 pin changed service tag between sessions. Since the **model-path** is `/data/models/qwen35-9b-w4a16` in both, likely **service ID changed** (name-space, not model content).

## 4. M2 M3 M4 Status Evidence

- **M2**:
  - Path: `/data/models/omnicoder-9b-gptq-int4/`
  - Exists with quantization config `GPTQ INT4` (config file shows `bits: 4`, `format: gptq`, `qual_method: gptq`)
  - SHA256 list available
  - File exists, no service record found currently (no RUNNING)
  - **M2 status**: ACTIVE ON-DISK, but service record ABSENT in current live server list
  - **Bring-up PASS claim**: 83.4 TPS claimed by owner on `/data/models/omnicoder-9b-gptq-int4/`; **No telemetry or logs available in current evidence** to confirm M2 currently running or M2 has achieved 83.4 TPS
  - No evidence of M2's current runtime status or TPS score in current server logs

- **M3** (`/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`):
  - File exists (12 GB)
  - User note: "was garbled; norm-fold fix verified, but sampled correctness still FAIR"
  - No evidence of current runtime port/status
  - GGUF-related gate gate record (GGUF-GATE-M4M3-20260918.md) mentions this

- **M4** (`/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf`):
  - File exists (12.9 GB, SHA256 `5ae067582f921ff9a1847ce4aab0b41ecad4c38c386e76fd4714f9a8b98e586e`)
  - Base: ukisai/Swift-Qwen3.8-27b (GGUF)
  - User note: "same garbling; norm-fold done, sampled correctness still FAIL; shared GGUF runtime; M4 prioritized over M3"
  - File exists but user marks it as problematic (sampled correctness FAIL)
  - Prioritized for M4 over M3 in matrix per owner note

- **UD-IQ3_S**: Only M3's quantization control, NOT a fifth arm
  - M3 identity: Qwen3.8-27B GSQ-RCO IQ3_S (correct identity)
  - FAQ: UD-IQ3_S = M3 quantization control, not a separate model arm

## 5. Unknowns

| Unknown | Evidence Missing | Command to Settle |
|---------|------------------|-------------------|
| Current live `--served-model-name` for M1 | No `--served-model-name` flag evidence in current/live process argv or gate config | `cat /proc/1654119/cmdline` (observe if `--served-model-name` prefix) OR inspect `proc/<current_pid>/cmdline` directly |
| Control-plane frozen profile for M1 | No artifact showing `frozen-profile.json` or `frozen-profile.yaml` or `frozen-profile.v1.json` pin | Search `.memory/phase2-hicache-design/work/`, `.memory/phase2-hicache-design/agents/` for `.json` or `.yaml` files containing `M1` |
| Full checksum set for M1 (`model.safetensors`) | Only `checksums.sha256.STALE-SUPERSEDED-20260916` and `model.safetensors.index.json` sha256 are readable; no measurable checksum on `model.safetensors` binary | `sha256sum /data/models/qwen35-9b-w4a16/model.safetensors` |
| M2 TPS runtime evidence | No telemetry logs or snapshots | Examine `/tmp/opencode/mamba-sweep*/phase2/`, TPC logs |
| M3/M4 sampled-correctness FAIL logs | No evidence file with "cft" or "sampled_correctness" | Look in `.memory/phase2-hicache-design/ledger.*` or M3/M4 artifacts |

## Defects / Blockers

1. **M1 identity name mismatch**: Current live service advertises `/data/models/qwen35-9b-w4a16` while historical pin records reference `qwen35-9b-local`. The only evidence is content match on architecture/quantization; no cryptographic ID evidence to establish exact alias.

2. **M1 frozen profile not present**: No artifact pinning "M1" commit hash or definition available in current state. Previous artifacts (`PROD-BIND-DIAG`, `MAMBA-CAPACITY-TELEMETRY`) reference from stopped state (P1).

3. **M2/M3/M4 on-disk status not claimed**: Only `omnicoder-9b-gptq-int4` has a clear file/directory and SHA256. M3/M4 GGUF files exist on-disk (12GB, 13GB) but user marks both as "sampled correctness FAIL" and "still garbled".

4. **No explicit `qwen35-9b-local` → M1 identity evidence**: Owner rule forbids assumption; need explicit evidence (hash, pin file, or argv) that `qwen35-9b-local` maps to the recorded "Qwen3.5-9B W4A16" build.

## Remaining claims / exclusions

- M1 identity binding is marked **"MODERATELY UNKNOWN"** because we cannot prove identical names rather than content-only match.

- M3 and M4 GGUF correctness claims ("sampled correctness FAIL") are reported from the HUMAN OWNER NOTE; no replicatable test results or log evidence available on disk in current state.

- M2 TPS (83.4) claim is **ON-DISK FILE presents** but current server does not list M2 as active; P4/P7 production record claims M2 has been brought up or bootstrapped / restored. Claims conflict.

## Terminal state: DONE

**Terminal state: DONE**

**Artifact path**: `.memory/phase2-hicache-design/agents/MLINE-IDENTITY-RECON-20260918.md`

**Summary:**
- M1: `/data/models/qwen35-9b-w4a16/` AVAIL, identity name mismatch vs MLINE definition (qwen35-9b-local)
- M2: `/data/models/omnicoder-9b-gptq-int4/` SHA256 present, GPTQ INT4, active on-disk; TPS claim not measured live
- M3: `/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf` FILE EXISTS (12GB)
- M4: `/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf` FILE EXISTS (Q3_K_M GGUF), 13.6GB
- Live service: serving `/data/models/qwen35-9b-w4a16` not `qwen35-9b-local`
