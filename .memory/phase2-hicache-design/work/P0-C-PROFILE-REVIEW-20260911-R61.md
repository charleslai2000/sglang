# P0-C Profile/Capacity Freeze — Independent Review R61

- Task ID: `P0-C-PROFILE-REVIEW-20260911-R61`
- Invocation: `ses-p0c-profile-review-r61-20260911`
- Role: `reviewer` (private, independent of the R60 implementer)
- Epoch: `2026-09-11`
- Status: **done**
- ENTRY: ACCEPT
- Reviewed artifact: `.memory/phase2-hicache-design/work/P0-C-PROFILE-FREEZE-20260911-R60.md`
  and `.artifacts/` (log, `r60_server_info.json`, `r60_model_info.json`, `r60_evidence.txt`,
  `SHA256SUMS.txt`). Cross-check input: `P0-C-PROFILE-RECON-20260911-R59.md` (appeared after R60
  completed; see F5).
- Scope honored: read-only; no remote access, no edits to the reviewed artifact, no
  product/test/gate/storage/Git changes. This is the only file written by this invocation.
- Claim boundary: this review is P0-C evidence only. It does **not** satisfy, replace, or bypass
  the P0-B hard gate.

## Method

All verification was performed locally against the frozen artifacts:

1. Recomputed SHA256 of every file and validated `SHA256SUMS.txt` with `sha256sum -c`.
2. Parsed the `server_args` dump (log line 6) as Python literal, and parsed
   `r60_server_info.json` top-level plus `internal_states[0]`, diffing them key-by-key.
3. Cross-read each "Frozen" row of the R60 table against the startup log, the live
   `/get_server_info` JSON, the P3 posture-change telemetry lines, and (where available)
   `P0-C-PROFILE-RECON-20260911-R59.md`.
4. Checked boundary/derived arithmetic (token budgets, pool totals).

## 1. Artifact hash verification — PASS

`sha256sum -c SHA256SUMS.txt` returned **OK for all four artifacts**; recomputed digests equal the
digests quoted in the R60 report and in `r60_evidence.txt:96`.

| Artifact | Bytes | SHA256 (first 16) | In report | In SHA256SUMS | Recomputed |
|---|---|---|---|---|---|
| `sglang3060-rh-clean-env-20260910.log` | 94437 | `01bcfa12bf286872` | `01bcfa12…a9ff3` | present | OK |
| `r60_server_info.json` | 33083 | `1854d8ff2c549b76` | `1854d8ff…7dc19` | present | OK |
| `r60_model_info.json` | 1164 | `01bc764229cec59a` | `01bc7642…5877a5` | present | OK |
| `r60_evidence.txt` | 6014 | `c6085655e51dd966` | `c6085655…f705cb` | present | OK |

The local log digest also equals the remote digest recorded in `r60_evidence.txt:96`, so the local
copy is a faithful capture of the remote log at capture time (31 h uptime, `r60_evidence.txt:1-4`).
Limit: no remote re-capture was in scope, so hashes establish **internal bundle integrity**, not
remote provenance.

## 2. Cross-source consistency of frozen values — no conflicts in the frozen set

Every capacity-critical value in the R60 "Frozen" table is corroborated by at least two of
{startup log, live `/get_server_info`, proc cmdline, P3 telemetry}. Spot-verified pairs:

| Dimension | R60 value | Log | `/get_server_info` | Cmdline / P3 |
|---|---|---|---|---|
| device KV tokens | 65536 | `log:30,42` | top `max_total_num_tokens=65536`; `memory_usage.token_capacity=65536` | `evidence:47-48` |
| device KV footprint | K 0.50 + V 0.50 GB | `log:30` | `memory_usage.kvcache=1.0` | — |
| KV dtype | fp8_e4m3 | `log:30` (`torch.float8_e4m3fn`) | `kv_cache_dtype='fp8_e4m3'` | `evidence:54-55` |
| mem fraction / free mem | 0.82 / 3.61 GB | `log:31,42` | `mem_fraction_static=0.82`; `startup_available=3.61` | — |
| weight load | 3.80 s / 3.85 GB | `log:27` | `startup_time.load_weight=3.7967`; `memory_usage.weight=3.846` | — |
| device Mamba slots | 53 | `log:29` | `internal.max_mamba_cache_size=53` | `max_mamba_cache_size=None` (auto) |
| Mamba footprint | 0.06 + 2.53 GB | `log:29` | (derived) | — |
| host KV pool | 131073 tok / 2.15 GB | `log:44` | `hicache_ratio=2.0`, `hicache_size=0` | P3 `host_headroom=131073` (`log:61`) |
| host Mamba pool | 5.51 GB, page_first | `log:45` | `hicache_mem_layout='page_first'` | — |
| host pool total | ≈7.66 GB | `2.15+5.51` (`log:44,45`) | — | — |
| pool topology | KV+MAMBA, transfer 32, hybrid_ssm | `log:43,48,49` | — | — |
| physical budget | 65536 | P3 `log:61` | — | `int(0.5×131073)` = 65536 (R59:22-23) |
| speculative budget | 39321 | P3 `log:61` | — | R60 `floor(0.6×65536)=39321` verified; R59:24 |
| RH watermarks | 55000/110000 | `log:51` | `ready_host_watermark_low/high` | `evidence:89-92` |
| storage backend/dir | file, `/hy-tmp/hicache-rh-clean-20260910` | `log:46,47` | `hicache_storage_backend='file'` | `evidence:26` export |
| ready-horizon flags | frontier 8, margins | `log:6` | all fields present | `evidence:86-92` |
| scheduler limits | 1 / 2048 / 16384 / fcfs / length | `log:42` | top-level fields present | `evidence:46-53` |
| CUDA graph | decode full [1]; prefill breakable [4,8,16,32] | `log:35-41` | `cuda_graph_config` matches | `evidence:75-85` |
| architecture | Qwen3_5ForConditionalGeneration / qwen3_5 | — | — | `r60_model_info.json` |
| sidecar | none | — | `sidecar=None`, `sidecar_args=None` | `evidence` absent / top-level |
| speculative algo | None (mtp unused) | — | `speculative_algorithm=None` | — |

Arithmetic checks pass: `int(0.5 × 131073) = 65536`; `floor(0.6 × 65536) = 39321`;
`2.15 + 5.51 = 7.66`. `r60_model_info.json` independently confirms
`architectures=["Qwen3_5ForConditionalGeneration"]`, `model_type="qwen3_5"`.

**No frozen capacity value conflicts across the captured sources.** One non-frozen key diverges
(F1) and one capacity-relevant value is omitted (F2).

## 3. Findings

Findings are issues to fix; questions are separate (§4).

### F1 — MEDIUM — R60's blanket "No conflicts were found" is contradicted by a real cross-source divergence

- Location: R60 lines 65-67 ("cross-consistent across three independent sources… No conflicts were
  found") and "Verification" line 139-140.
- Evidence: the startup `server_args` dump says `disable_chunked_prefix_cache=False`
  (`sglang3060-rh-clean-env-20260910.log:6`), while the live JSON reports
  `internal_states[0].disable_chunked_prefix_cache=True` (`r60_server_info.json`). A programmatic
  key-diff of `server_args` vs `server_info` found this plus three other runtime-derived
  divergences (`pp_max_micro_batch_size` None→1, `max_mamba_cache_size` None→53,
  `disaggregation_decode_retraction_backup` None→`cpu_tensor`).
- Acceptance impact: none of these keys is in the R60 frozen table, so the **capacity freeze still
  stands**. The defect is the over-broad "no conflicts" wording, which is not literally true and
  should be scoped to "no conflicts in the frozen set."

### F2 — MEDIUM — capacity-relevant omission: effective input length is 65530, not 262144

- Location: R60 "Context length" row (line 79) and "Device KV pool" row (line 80).
- Evidence: live `r60_server_info.json` reports `max_req_input_len=65530` (and
  `max_total_num_tokens=65536`), while the string `262144` does **not** occur anywhere in
  `r60_server_info.json`; it appears only in `log:42` (and per R59, the model config).
- Acceptance impact: R60's `context_len=262144` is the model-context ceiling; the usable
  single-request input is bounded by the 65536-token KV pool (reported 65530). A capacity consumer
  reading only the frozen table could over-estimate usable context by ~4×. Recommend recording
  `max_req_input_len=65530` in the frozen table.

### F3 — LOW — "three independent sources" overstates independence

- Location: R60 line 65-67, 139-140.
- Evidence: two of the three cited sources (the `server_args` dump at log line 6 and the
  device/host-pool allocation lines at log lines 27-49) are the **same log file**, so they are not
  independent of each other. Genuine independence exists between log / `server_info` / proc
  cmdline. The cross-checks still hold, but the claim should be corrected to avoid implying three
  separate evidence channels.

### F4 — LOW — values asserted without cross-source support inside the captured bundle

No `config.json`, no model-directory listing, and no `/proc/<pid>/environ` dump were captured, so
these asserted values rest on a single source or on no artifact at all:

1. `model.safetensors` = 5,052,218,552 B — claimed source "model dir" (not captured).
2. `model_mtp.safetensors` = 241,200,704 B — same.
3. Quantization internals "pack-quantized, W4 group_size=128 symmetric int" — claimed from
   `config.json`; the log only proves `quant=compressed-tensors` (`log:27`).
4. `context_len` provenance from `text_config.max_position_embeddings=262144` — `config.json`
   not captured; `server_info` contains no `262144`.
5. "32 layers of `linear_attention`/`full_attention`" — only `transfer_layer_num=32` is supported
   (`log:48`); the per-layer type list is not in any captured artifact.
6. `SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR` as "env of PID 218072" and the claim that no
   `*_MAX_SIZE`/`*_MIN_FREE_SPACE` env is set — `environ` was not dumped; the dir is only
   indirectly supported by the parent export (`r60_evidence.txt:26`) and `log:47`.
7. Preflight "not a git repo", Python 3.11.11 / torch 2.6.0+cu124 / `cuda.is_available()=True`,
   `/proc/218072/exe`, `VIRTUAL_ENV`, `nvcc` absence — not in the captured evidence.
- Acceptance impact: low. Items 1-5 are non-capacity metadata. Items 6-7 are now independently
  corroborated by R59 §2 (Python/torch/no-git) from the R32 bundle, but the R60 bundle itself
  does not carry the raw proof. Recommend a follow-up capture of `config.json`, a model-dir
  listing, and `environ`.

### F5 — INFORMATIONAL — the missing R59 input was genuinely absent at R60 runtime; it now exists and corroborates

- Evidence: R59's inode was created `2026-09-11 13:42:41` (Birth = Modify), i.e. **after** the R60
  artifacts (`13:40:44`) and report (`13:41:26`). R60's statement that R59 did not exist at
  execution time is consistent with the filesystem timeline.
- R59 is now present and independently re-derives the same profile and budgets
  (`physical=65536=int(0.5×131073)`, `speculative=39321=int(0.6×65536)`, host KV 131073/2.15 GB,
  host Mamba 5.51 GB, Mamba 53, watermarks 55000/110000, page 1) from the R32 raw bundle, which
  **strengthens** the R60 freeze. No R60 rework is required for this item.

### F6 — INFORMATIONAL — several "frozen" numbers are runtime-derived and may drift

- Location: R60 lines 80-88 (`available_gpu_mem`, Mamba 53, host-pool GB).
- Evidence: `max_mamba_cache_size=None` in args (auto), resolved to 53; R59 open issue #2 flags
  that auto-derived pool sizes can drift with environment/driver changes.
- Acceptance impact: none today; the R60 table does label the source as "auto". This is a
  durability caveat, not a conflict.

## 4. Questions (not findings)

- Q1: Does P0-C require the freeze to state the **usable** input cap (`max_req_input_len=65530`)
  in addition to the model `context_len=262144`? (F2 recommends yes.)
- Q2: Should R60 be amended in place for F1/F3 wording, or superseded by a corrected freeze
  report? Orchestrator call; this reviewer did not edit the artifact.
- Q3: Is recording `model.safetensors` byte sizes and quantization inner params (group_size) in
  scope for P0-C, or should they move to a model-provenance task? (F4.)

## 5. Verdict

**VERIFIED** — the P0-C profile/capacity freeze recorded in R60 is **complete and correct for all
capacity-critical frozen values**. Every capacity dimension cross-checks across the startup log,
the live `/get_server_info` JSON, the P3 telemetry, and/or the recovered launch argv; the derived
arithmetic is correct; and all four artifact hashes verify against `SHA256SUMS.txt`.

Verdict scope and residual caveats (non-blocking):

- R60's claim of "no conflicts" is literal-true only for the frozen set; a non-frozen key
  (`disable_chunked_prefix_cache`) does diverge (F1).
- `max_req_input_len=65530` should be added, since `context_len=262144` alone can mislead (F2).
- The "three independent sources" wording overstates independence (F3).
- Six groups of non-capacity metadata are asserted without in-bundle cross-source support (F4);
  R59 now corroborates part of them (F5).

These caveats affect completeness of the *reporting*, not the correctness of the frozen capacity
profile, so the freeze is accepted as VERIFIED with the amendments listed.

## 6. P0-B gate

This review is not production acceptance and does **not** satisfy the P0-B hard gate, which
remains NOT_VERIFIED. Nothing here demonstrates the park→allocability-change→wake→restore
transition; that is P0-B execution scope.

## Summary

I independently reproduced the R60 freeze: all four artifact digests match `SHA256SUMS.txt`; the
log vs `/get_server_info` vs P3 telemetry cross-check confirms every capacity value
(65536 device tokens, 1.0 GB fp8 KV, Mamba 53, host KV 131073/2.15 GB, host Mamba 5.51 GB,
≈7.66 GB total, 0.82 mem fraction, 3.61 GB free, physical budget 65536, speculative 39321,
watermarks 55000/110000) and the launch argv. I found no conflict among frozen values, but I did
find (F1) a non-frozen runtime divergence that makes R60's "no conflicts" wording too broad,
(F2) an omitted capacity-relevant `max_req_input_len=65530`, (F3) an overstated independence
claim, and (F4) a list of metadata asserted without in-bundle support. R59, which post-dates R60,
now exists and independently corroborates the profile. Verdict: VERIFIED (capacity freeze) with
amendments recommended.

## Artifacts

- This report: `.memory/phase2-hicache-design/work/P0-C-PROFILE-REVIEW-20260911-R61.md`

## Evidence

- Verified hashes: `sha256sum -c P0-C-PROFILE-FREEZE-20260911-R60.artifacts/SHA256SUMS.txt` → all
  four OK.
- `sglang3060-rh-clean-env-20260910.log:6,27,29,30,31,42,43,44,45,46,47,48,49,51,61`.
- `r60_server_info.json` (top-level `max_total_num_tokens`, `kv_cache_dtype`,
  `mem_fraction_static`, `page_size`, `hicache_ratio`, `hicache_size`, `max_req_input_len=65530`,
  `startup_time`, `internal_states[0].max_mamba_cache_size=53`,
  `internal_states[0].memory_usage`, `internal_states[0].disable_chunked_prefix_cache=True`).
- `r60_model_info.json` (architectures / model_type).
- `r60_evidence.txt:1-4,26,46-55,75-85,86-92,96-99`.
- `P0-C-PROFILE-RECON-20260911-R59.md` §2-§5 (independent re-derivation; inode birth 13:42:41 >
  R60 completion 13:41:26).

## Followups

1. Amend the R60 freeze (or issue a corrected successor) to scope the "no conflicts" claim to the
   frozen set (F1) and to add `max_req_input_len=65530` (F2). Owner: freeze author; new invocation.
2. Capture a follow-up bundle with `config.json`, a model-directory listing, and
   `/proc/<pid>/environ` to close F4 items 1-6.
3. Keep the P0-B hard gate closure separate; do not cite this review as gate evidence.

## Open issues

- F1 wording divergence (non-frozen key) not yet corrected in the reviewed artifact (not edited by
  this reviewer).
- F2 `max_req_input_len` omission.
- F4 unsupported metadata values.
- P0-C freeze is process-captured, not declared by a reviewed launch script (inherited from R59);
  auto-derived values may drift.
- P0-B remains NOT_VERIFIED.
