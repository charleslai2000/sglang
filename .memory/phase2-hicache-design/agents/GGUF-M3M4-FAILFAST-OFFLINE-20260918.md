# GGUF-M3M4-FAILFAST-OFFLINE-20260918

Terminal state: DONE

## Task
Bounded CPU-only diagnosis of exactly two questions:
- **Q1:** Is the working-tree `gguf_native.py` fix CLOSED — does `build_gguf_tokenizer` on the REAL M3 and REAL M4 GGUF files encode each of the five canonical markers (`<|endoftext|>`=248044, `<|im_start|>`=248045, `<|im_end|>`=248046, `<think>`=248068, `</think>`=248069) to its canonical id, with no `[PAD*]` collision?
- **Q2:** Was the recorded `GGUF_CORRECTNESS=FAIL` obtained BEFORE or AFTER the fix bytes? Establish from on-disk artifacts, not guessing, and state the discriminator.

## Scope
CPU-only. No product-source edits. No GPU/CUDA. No server start/stop. No port bind. Read-only git.
Probes used the already-authorized interpreter `/opt/sglang/local-prod-v1/env/bin/python` with `PYTHONPATH=<repo>/python`.

## Result
- **Q1 = YES, the fix is CLOSED on both real GGUF artifacts.** All five markers encode to their canonical single ids on M3 and M4. No `[PAD*]` collision. Real in-tree unit test 10/10 PASS; harness `--cpu-smoke` `ok=True`, all checks pass.
- **Q2 = the FAIL was obtained BEFORE the fix bytes (pre-fix).** The gate ran 2026-09-17 15:08:28–15:28:21Z against a tree whose `gguf_native.py` was byte-identical to the pre-fix HEAD blob; the fix file was last modified 2026-09-17 16:58:54Z. The gate's own recorded tokenizer fingerprint is pre-fix (`tokenizer_vocab_size = 248293`), which the pre-fix module reproduces exactly and the fixed module does not (`248320`).
- **No remaining defect in the tokenizer id-binding** was found. See "Remaining claims or exclusions" for the untested post-fix model-behavior question.

## Evidence

### E0. File identity and timeline (read-only)
```
$ sha256sum python/sglang/srt/utils/hf_transformers/gguf_native.py
0f3c8fb9f2e6c3eb2bdcf0a3640f26880a88179bb0b4a3f41674fbfaf8202ade  python/sglang/srt/utils/hf_transformers/gguf_native.py

$ git show HEAD:python/sglang/srt/utils/hf_transformers/gguf_native.py | sha256sum
c5f2e9730c88f589bcc7809e09b5d5857f8ebb99fe8a92bc966c3db82e97ef65  -

$ stat -c '%y %n' python/sglang/srt/utils/hf_transformers/gguf_native.py
2026-09-17 16:58:54.973278545 +0000 python/sglang/srt/utils/hf_transformers/gguf_native.py

$ stat -c '%y %n' python/sglang/srt/models/qwen3_5_text.py
2026-09-17 14:16:22.644703637 +0000 python/sglang/srt/models/qwen3_5_text.py
```
`git status --short` shows ` M python/sglang/srt/utils/hf_transformers/gguf_native.py` — fix is **uncommitted**; HEAD carries the pre-fix blob `c5f2e973…`. The gate evidence's "worktree tip 116afefbbe" resolves to the same pre-fix blob:
```
$ git show 116afefbbe:python/sglang/srt/utils/hf_transformers/gguf_native.py | sha256sum
c5f2e9730c88f589bcc7809e09b5d5857f8ebb99fe8a92bc966c3db82e97ef65  -
$ git show 4501e59f88:python/sglang/srt/utils/hf_transformers/gguf_native.py | sha256sum
c5f2e9730c88f589bcc7809e09b5d5857f8ebb99fe8a92bc966c3db82e97ef65  -
```
Gate timing (`report.json`): M4 `started_utc 2026-09-17T15:08:28Z`, `finished_utc 15:18:24Z`; M3 `started_utc 15:18:26Z`, `finished_utc 15:28:21Z`. The fixed file mtime (16:58:54Z) is ~1.5 h **after** the gate finished.

### E1. Q1 — real-artifact encode probe (post-fix working tree)
Command (logic pasted verbatim into `/tmp/opencode/gguf_probe2.py`; this is CPU-only metadata/tokenizer work):
```
PYTHONPATH=/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python \
  /opt/sglang/local-prod-v1/env/bin/python /tmp/opencode/gguf_probe2.py
```
Output:
```
MODEL M4 /data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf
vocab_size: 248320 | len(tokenizer): 248320 | base-only get_vocab_size: 248320
total rows: 248320 token_type counts: {1: 248044, 3: 27, 4: 6, 5: 243}
  '<|endoftext|>'  gguf_row=248044 type=3 encode=[248044] base_vocab_id=248044 CANON=248044 MATCH=True
  '<|im_start|>'   gguf_row=248045 type=3 encode=[248045] base_vocab_id=248045 CANON=248045 MATCH=True
  '<|im_end|>'     gguf_row=248046 type=3 encode=[248046] base_vocab_id=248046 CANON=248046 MATCH=True
  '<think>'        gguf_row=248068 type=4 encode=[248068] base_vocab_id=248068 CANON=248068 MATCH=True
  '</think>'       gguf_row=248069 type=4 encode=[248069] base_vocab_id=248069 CANON=248069 MATCH=True
  ALL-FIVE-CANONICAL: True
  _added_tokens_decoder marker entries: {248044: ('<|endoftext|>', True), 248045: ('<|im_start|>', True), 248046: ('<|im_end|>', True), 248068: ('<think>', False), 248069: ('</think>', False)}
  defect-binding probe: encode('<|im_start|>') -> [248045] | encode('<|im_end|>') -> [248046]
    row 248294 = '[PAD248294]' type=5 (would be PAD-bound defect target)
    row 248295 = '[PAD248295]' type=5 (would be PAD-bound defect target)
==============================================================================
MODEL M3 /data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf
vocab_size: 248320 | len(tokenizer): 248320 | base-only get_vocab_size: 248320
total rows: 248320 token_type counts: {1: 248044, 3: 27, 4: 6, 5: 243}
  '<|endoftext|>'  gguf_row=248044 type=3 encode=[248044] base_vocab_id=248044 CANON=248044 MATCH=True
  '<|im_start|>'   gguf_row=248045 type=3 encode=[248045] base_vocab_id=248045 CANON=248045 MATCH=True
  '<|im_end|>'     gguf_row=248046 type=3 encode=[248046] base_vocab_id=248046 CANON=248046 MATCH=True
  '<think>'        gguf_row=248068 type=4 encode=[248068] base_vocab_id=248068 CANON=248068 MATCH=True
  '</think>'       gguf_row=248069 type=4 encode=[248069] base_vocab_id=248069 CANON=248069 MATCH=True
  ALL-FIVE-CANONICAL: True
  _added_tokens_decoder marker entries: {248044: ('<|endoftext|>', True), 248045: ('<|im_start|>', True), 248046: ('<|im_end|>', True), 248068: ('<think>', False), 248069: ('</think>', False)}
```
Round-trip (`skip_special_tokens=False`) returns the literal marker for all five; CONTROL markers are `special=True` (stripped when `skip_special_tokens=True`), USER_DEFINED markers are `special=False` (survive), which is exactly what the reasoning/tool parsers require. The `[PAD248294]`/`[PAD248295]` rows still exist (type=5) but are **not** the encode targets. Note: the five canonical ids are the real GGUF rows (matching `tokenizer.ggml.tokens` indices), not the PAD tail.

### E2. Q1 — pre-fix control reproduction (from HEAD blob, read-only)
```
$ git show HEAD:.../gguf_native.py > /tmp/opencode/gguf_native_prefix.py   # sha256 c5f2e9730c88…ef65
$ PYTHONPATH=<repo>/python /opt/sglang/local-prod-v1/env/bin/python /tmp/opencode/prefix_probe.py
MODEL M4 PRE-FIX vocab_size: 248293
   '<|endoftext|>'  encode=[248293] canonical=248044 MATCH=False
   '<|im_start|>'   encode=[248294] canonical=248045 MATCH=False
   '<|im_end|>'     encode=[248295] canonical=248046 MATCH=False
   '<think>'        encode=[13314, 741, 29] canonical=248068 MATCH=False
   '</think>'       encode=[510, 26003, 29] canonical=248069 MATCH=False
MODEL M3 PRE-FIX vocab_size: 248293
   '<|endoftext|>'  encode=[248293] canonical=248044 MATCH=False
   '<|im_start|>'   encode=[248294] canonical=248045 MATCH=False
   '<|im_end|>'     encode=[248295] canonical=248046 MATCH=False
   '<think>'        encode=[13314, 741, 29] canonical=248068 MATCH=False
   '</think>'       encode=[510, 26003, 29] canonical=248069 MATCH=False
```
The pre-fix defect is exactly the described one: CONTROL rows removed from the base vocab shift `<|endoftext|>/<|im_start|>/<|im_end|>` onto ids 248293/248294/248295, and USER_DEFINED `<think>/</think>` fall out of the vocab and BPE-split into text.

### E3. Unit test (real in-tree test, post-fix working tree)
```
$ /opt/sglang/local-prod-v1/env/bin/python -m pytest \
    test/registered/unit/utils/test_gguf_native_tokenizer_ids.py -q
..........                                                               [100%]
10 passed, 15 warnings in 17.68s
```
Coverage includes canonical encode ids, zero added/base collisions, base vocab owning every canonical id, bos/eos metadata match, CONTROL stripped vs USER_DEFINED surviving detokenization, and HF (non-GGUF) tokenizer path inert.

### E4. Harness offline step (CPU-only, no server/CUDA)
```
$ cd 3090-dev/gates/gguf-sampled-smoke
$ /opt/sglang/local-prod-v1/env/bin/python server_harness_sampled.py --cpu-smoke
HARNESS_EXIT=0
ok = True
check keys: ['request_body_m4', 'request_body_m3', 'ngram_metric_identical_to_prior',
 'gate_threshold_is_content_w4_0.27', 'gating_predicate_semantics',
 'real_send_path_pins_sampled_contract', 'per_criterion_reporting',
 'ngram_identical_to_live_prior_harness']
all checks pass: True
```
`--cpu-smoke` proves contract/metric wiring only; it does not exercise the tokenizer id binding. Output captured to `/tmp/opencode/cpu_smoke_rerun.json`. The pre-existing repo copy `cpu_smoke.out.json` (mtime 2026-09-17 15:04:55Z, sha256 `04959784208ec793df57acbbcd0a276d2b3581fa4eaa7ac60a685d87312562ab`) is byte-identical to `/mnt/data/nerun-dev/gguf-sampled-smoke-20260917/runs/cpu_smoke.json`; no repo file was modified by this probe.

### E5. Q2 — the decisive on-disk discriminator
The gate records no sha256 of `gguf_native.py` (its pinned/observed sha256 is for `qwen3_5_text.py`; grep for `gguf_native` in `/mnt/data/nerun-dev/gguf-sampled-smoke-20260917/` and the gate dir returns only the harness import line). So the sha-equality test requested in the task is **not directly available** for this module. However, the gate records a functional fingerprint of the tokenizer it actually built, in both arms' `step2b_tokenizer_crosscheck`:
```
$ python -c "... report.json ... d['step2b_tokenizer_crosscheck'].get('tokenizer_vocab_size')"
m4 tokenizer_vocab_size = 248293
m3 tokenizer_vocab_size = 248293
```
- Pre-fix `build_gguf_tokenizer` (HEAD blob `c5f2e973…`, which is also the gate-time tip `116afefbbe`) → `vocab_size = 248293` (E2).
- Post-fix working-tree `build_gguf_tokenizer` (`0f3c8fb9…`) → `vocab_size = 248320` (E1).

The gate's own recorded value **248293** matches the pre-fix module and not the fixed one. This fingerprint is corroborated by the independent timeline: gate window 15:08:28–15:28:21Z vs fixed-file mtime 16:58:54Z.

**Discriminator used:** the gate's recorded `step2b_tokenizer_crosscheck.tokenizer_vocab_size` (248293) matched against a controlled re-execution of the pre-fix HEAD module (248293) and the fixed working-tree module (248320) on the same real GGUFs, plus the file mtime/gate-window ordering. **Conclusion: Q2 = pre-fix.** The FAIL verdict is therefore not evidence against the fix.

## Defects or blockers
None blocking. The tokenizer id-binding defect is fixed and verified closed on the real artifacts. The only evidence gap for Q2 is that the gate never recorded a `gguf_native.py` sha256 (noted under E5); the functional fingerprint + timeline resolve the question without it.

## Remaining claims or exclusions
- **Not claimed:** that the post-fix tree will now PASS the gating `GGUF_CORRECTNESS` criteria 2 and 6 on GPU. That is a GPU behavioral question explicitly out of this CPU-only scope; the fix removes a proven tokenizer id-binding defect but the pre-fix FAIL was recorded, so no post-fix GPU verdict exists.
- **Not claimed:** that the id-binding fix is the sole cause of the recorded M3/M4 loops. The prior CPU llama.cpp discriminator (M4 loop_w4=0.0552, M3=0.1029) and the fact that the tokenizer vocab size recorded at gate time was pre-fix (`248293`) are consistent with the fix possibly mattering, but this task did not test generation quality.
- **Excluded:** GPU/CUDA, server lifecycle, ports, any product-source edit. No commit was made; the fix remains uncommitted in the working tree.
- The `--cpu-smoke` result is a wiring/contract check only and is not evidence about tokenizer id binding.

## Terminal state: DONE
