# M3M4-GATE-RERUN-20260918

Terminal state: DONE

## Task
Re-run the GGUF sampled-contract gate for M4 then M3 on the CURRENT working tree (which contains the
verified tokenizer id-binding fix), record report.json verdicts, and restore production to a verified
UP state.

## Scope
- ONE bounded GPU window, one owner (debugger-deep).
- In scope: run `3090-dev/gates/gguf-sampled-smoke/run_sampled_smoke.sh` (cpu-smoke -> m4 -> m3,
  port 30165, canonical flock), read per-model report.json, stop/start production M2 via
  identity-checked bin scripts, verify health.
- Out of scope: editing product source, tests, gates, /opt/**, /data/**; committing/staging; any other
  GPU work. No product source was edited; nothing was committed or staged.

## Result

Both goals are complete. The gate was re-run on the CURRENT working tree and produced validated
post-fix verdicts; production was restored and independently verified UP.

**(a) M4_GATE_VERDICT = FAIL** (verdict from `m4/report.json`; status=completed).
- criterion 2 (`short_deterministic_semantics`) = **FAIL** (pass=false)
- criterion 6 (`sampled_ge512_coherent_content`) = **FAIL** (pass=false; `passing_probes=[]`)

**(b) M3_GATE_VERDICT = FAIL** (verdict from `m3/report.json`; status=completed).
- criterion 2 (`short_deterministic_semantics`) = **FAIL** (pass=false)
- criterion 6 (`sampled_ge512_coherent_content`) = **FAIL** (pass=false; `passing_probes=[]`)

The FAIL is NOT the previous pre-fix FAIL re-observed: this run demonstrably exercised the fixed
bytes. `step2b_tokenizer_crosscheck.tokenizer_vocab_size = 248320` (post-fix) in both reports, versus
`248293` (pre-fix) in the prior reports. The two failing criteria are unchanged in kind, but the
verdict now stands on post-fix evidence.

**(c) Was the fixed module sha256 the one actually exercised?** — The fixed tokenizer module
(`gguf_native.py`, sha256 `0f3c8fb9...`) IS in the exercised source tree:
`GGUF_GATE_SRC` was the default `<repo>/python` (NOT overridden), `source_preflight` resolved sglang
inside it (`structural_identity_ok=True`, `ok=True`), and the server's `/proc/<pid>/environ`
`PYTHONPATH=<repo>/python`. The gate's recorded `actual_module_sha256` is
`d51d5441064c13cb90da9af7399c067e072182e7bc8c362e72ea4ba6a11e3941` — but note this field fingerprints
the gate's own norm-fold module `python/sglang/srt/models/qwen3_5_text.py`, not `gguf_native.py`. The
positive proof that the FIXED tokenizer bytes ran is the post-fix vocab size **248320** recorded in
both reports. `GGUF_GATE_MODULE_SHA256` was unset (`expected_module_sha256=""`), so identity mode was
`structural+recorded_sha256` (structural gate, observed hash recorded). GGUF_GATE_SRC=<repo>/python.

**(d) PRODUCTION_RESTORED = yes.** Observed HTTP codes: loopback `/health`=200, loopback `/v1/models`
=200, LAN `http://192.168.20.250:30000/health`=200, LAN `/v1/models`=200. Served by M2 pid 1851500
under supervisor/lock-holder 1851473; canonical lock held by that supervisor; no listener on :30165.

## Evidence

- WORKING-TREE MODULE (tokenizer id-binding fix): `python/sglang/srt/utils/hf_transformers/gguf_native.py`
- sha256 = `0f3c8fb9f2e6c3eb2bdcf0a3640f26880a88179bb0b4a3f41674fbfaf8202ade` (mtime 2026-09-17 16:58:54Z).
  Re-checked AFTER the gate: unchanged (same sha256). No product source edited by this task.
- Gate fingerprint module `python/sglang/srt/models/qwen3_5_text.py` sha256 =
  `d51d5441064c13cb90da9af7399c067e072182e7bc8c362e72ea4ba6a11e3941` (same as the prior reports' recorded
  `source_preflight.actual_module_sha256`).
- GGUF_GATE_SRC default `<repo>/python`; gate python `/opt/sglang/local-prod-v1/env/bin/python`
  (Python 3.12.3); port 30165 (never 30000); runroot `/mnt/data/nerun-dev/gguf-sampled-smoke-20260917/runs`.

### E0. Pre-window state (recorded before touching production)
`ss -ltnp | grep -E ':30000|:30165'`:
```
LISTEN 0      2048         0.0.0.0:30000      0.0.0.0:*    users:(("python",pid=1840571,fd=68))
```
(no :30165 listener)

`pgrep -af 'sglang.launch_server|sglang::scheduler'`:
```
1840571 /opt/sglang/local-prod-v1.2.1-candidate-M2/env/bin/python -u -m sglang.launch_server --model-path /data/models/omnicoder-9b-gptq-int4 --host 0.0.0.0 --port 30000 --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 262144 --context-length 131072 --max-running-requests 8 --max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer --linear-attn-prefill-backend triton --linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 --reasoning-parser qwen3 --tool-call-parser qwen3_coder --enable-metrics --export-metrics-to-file --export-metrics-to-file-dir /tmp/opencode/prod-service-20260917/logs/m2-20260918T183744Z-1840331 --disable-prefill-cuda-graph
1841198 sglang::scheduler
```
`nvidia-smi`: pid 1840571 (300 MiB) + 1841198 sglang::scheduler (18752 MiB); 19067/24576 MiB used.
Canonical lock `/tmp/opencode/gpu-3090.lock`:
```
{"owner": "supervise-m2-m2-20260918T183744Z-1840331", "pid": 1840544, "generation": 1, "acquired": "2026-09-18T18:37:45Z"}
```
Live supervisor pid 1840544 (`bash .../bin/supervise.sh m2 ...`, fd 9 -> gpu-3090.lock); server pid 1840571.
Gate preconditions checked: both model files present; gate python present; runroot present;
`--print-plan` confirmed src=<repo>/python, port=30165, order m4->m3.

### E1. Prior (PRE-FIX) report fingerprints for contrast
- `m4/report.json` (mtime 1789658304 = 2026-09-17 15:18Z): verdict=FAIL, status=completed,
  `source_preflight.actual_module_sha256=d51d5441...`, `step2b_tokenizer_crosscheck.tokenizer_vocab_size=248293`,
  failures=['2_semantics','6_sampled_coherence'].
- `m3/report.json` (mtime 1789658901 = 2026-09-17 15:28Z): same shape; `tokenizer_vocab_size=248293`; FAIL.
- Pre-fix vocab_size = 248293 (the pre-fix bytes the earlier FAIL was recorded against).

### E2. Production stopped (identity-checked) — window freed
```
$ cd /tmp/opencode/prod-service-20260917 && bash bin/stop-m2.sh
[18:45:18] m2 identity check PASS: pid=1840571 is launch_server on port 30000 for /opt/sglang/local-prod-v1.2.1-candidate-M2 model /data/models/omnicoder-9b-gptq-int4
[18:45:18] m2: terminating supervisor pid=1840544 (SIGTERM; it will release the GPU lock)
[18:45:18] m2: stopping owned server pid=1840571 (SIGTERM, graceful)
[18:45:24] m2 stopped; GPU released; state published as free
STOP_RC=0
```
Post-stop: `ss` -> no :30000/:30165 listeners; `pgrep sglang` -> none;
`nvidia-smi --query-compute-apps` -> empty; GPU 1 MiB / 0%; `lock_is_held` -> `null`;
`gpu_material_holder` -> empty.

### E3. Gate driver stdout (`bash run_sampled_smoke.sh`, 18:45:39Z -> 19:02:09Z)
Saved verbatim at `/tmp/opencode/M3M4-GATE-RERUN-20260918/gate.stdout.log`:
```
=== gguf-sampled-smoke gate ===
source tree : /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python
python      : /opt/sglang/local-prod-v1/env/bin/python
port        : 30165   (never 30000)
runroot     : /mnt/data/nerun-dev/gguf-sampled-smoke-20260917/runs
order       : m4 (control) -> m3 (IQ3-specific risk)

=== step 0: CPU contract smoke Fri Sep 18 18:45:39 UTC 2026 ===
CPU_SMOKE_RC=0

=== step 1: M4 (control) Fri Sep 18 18:45:40 UTC 2026 ===
M4_RC=5  Fri Sep 18 18:53:41 UTC 2026

=== step 2: M3 (IQ3-specific risk) Fri Sep 18 18:53:41 UTC 2026 ===
M3_RC=5  Fri Sep 18 19:02:09 UTC 2026

=== per-model verdicts ===
--- M4 (m4): verdict=FAIL status=completed
      1_finite_logits          PASS
      2_semantics              FAIL
      3_cuda_graph             PASS
      4_fp8_kv                 PASS
      5_no_fallback            PASS
      6_sampled_coherence      FAIL
      diag:greedy_ge512        {'contract': {'temperature': 0.0, 'top_p': 1.0, 'top_k': -1, 'min_p': 0.0, 'seed': 20260916, 'max_tokens': 640, 'chat_template_kwargs': {'enable_thinking': False}}, 'per_probe': {'function_csv': {'classification': 'EMPTY_CONTENT', 'content_loop_w4': 0.0, 'full_loop_w4': 0.0, 'n_completion_tokens': 1, 'passes_gate': False}, 'longform_water': {'classification': 'DEGENERATE', 'content_loop_w4': 0.9607, 'full_loop_w4': 0.9607, 'n_completion_tokens': 640, 'passes_gate': False}, 'explain_tcp': {'classification': 'TOO_SHORT', 'content_loop_w4': 0.0, 'full_loop_w4': 0.0, 'n_completion_tokens': 4, 'passes_gate': False}}}
      diag:thinking_on         {'classification': 'EMPTY_CONTENT', 'content_loop_w4': 0.0, 'full_loop_w4': 0.0, 'n_completion_tokens': 27}
      failures=['2_semantics', '6_sampled_coherence']
--- M3 (m3): verdict=FAIL status=completed
      1_finite_logits          PASS
      2_semantics              FAIL
      3_cuda_graph             PASS
      4_fp8_kv                 PASS
      5_no_fallback            PASS
      6_sampled_coherence      FAIL
      diag:greedy_ge512        {'contract': {'temperature': 0.0, 'top_p': 1.0, 'top_k': -1, 'min_p': 0.0, 'seed': 20260916, 'max_tokens': 640, 'chat_template_kwargs': {'enable_thinking': False}}, 'per_probe': {'function_csv': {'classification': 'TOO_SHORT', 'content_loop_w4': 0.0, 'full_loop_w4': 0.0, 'n_completion_tokens': 2, 'passes_gate': False}, 'longform_water': {'classification': 'TOO_SHORT', 'content_loop_w4': 0.0, 'full_loop_w4': 0.0, 'n_completion_tokens': 2, 'passes_gate': False}, 'explain_tcp': {'classification': 'TOO_SHORT', 'content_loop_w4': 0.9938, 'full_loop_w4': 0.9938, 'n_completion_tokens': 640, 'passes_gate': False}}}
      diag:thinking_on         {'classification': 'EMPTY_CONTENT', 'content_loop_w4': 0.0, 'full_loop_w4': 0.0, 'n_completion_tokens': 42}
      failures=['2_semantics', '6_sampled_coherence']
=== gate end Fri Sep 18 19:02:09 UTC 2026 ===
DRIVER_RC=5
```

Per-model gate logs (`m4.stdout.log` / `m3.stdout.log`):
```
[2026-09-18T18:45:40Z] canonical GPU lock acquired (attempt 1)
[2026-09-18T18:45:55Z] m4: source-identity preflight OK (sglang -> patched copy)
[2026-09-18T18:45:55Z] m4: server launched pid=1844395, waiting for health
[2026-09-18T18:45:55Z] m4: /proc/1844395/environ PYTHONPATH is patched copy: True
[2026-09-18T18:51:51Z] m4: healthy in 356.1s, vram=18008 MiB
[2026-09-18T18:51:54Z] m4: KV gate OK (torch.float8_e4m3fn, tokens=8192)
[2026-09-18T18:53:40Z] m4: harness completed, vram=18054 MiB
[2026-09-18T18:53:40Z] wrote /mnt/data/nerun-dev/gguf-sampled-smoke-20260917/runs/m4/report.json
```
```
[2026-09-18T18:53:42Z] canonical GPU lock acquired (attempt 1)
[2026-09-18T18:53:56Z] m3: source-identity preflight OK (sglang -> patched copy)
[2026-09-18T18:53:56Z] m3: server launched pid=1846485, waiting for health
[2026-09-18T18:53:56Z] m3: /proc/1846485/environ PYTHONPATH is patched copy: True
[2026-09-18T19:00:27Z] m3: healthy in 391.1s, vram=17760 MiB
[2026-09-18T19:00:30Z] m3: KV gate OK (torch.float8_e4m3fn, tokens=16384)
[2026-09-18T19:02:07Z] m3: harness completed, vram=17998 MiB
[2026-09-18T19:02:07Z] wrote /mnt/data/nerun-dev/gguf-sampled-smoke-20260917/runs/m3/report.json
```
Driver touched `sampled_smoke.done`; gate released the canonical lock (post-run lock owner was
`gguf-sampled-smoke-gate-20260917`, pid 1846415) and left no server/GPU holder.

### E4. M4 report.json — provenance + raw criteria (`/mnt/.../runs/m4/report.json`)
- started_utc 2026-09-18T18:45:40Z, finished_utc 2026-09-18T18:53:40Z; verdict=FAIL; status=completed.
- source = `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python`.
- source_preflight.actual_module_sha256 = `d51d5441064c13cb90da9af7399c067e072182e7bc8c362e72ea4ba6a11e3941`;
  expected_module_sha256 = `""`; identity_mode = `structural+recorded_sha256`; ok = true;
  structural_identity_ok = true; resolved_sglang_file = `<repo>/python/sglang/__init__.py`;
  fold_helpers_present = ['_gguf_fold_absolute_norms','_gemma_norm_param_names'];
  fold_call_wired_in_load_weights = true.
- proc_environ.PYTHONPATH = `<repo>/python`; pythonpath_is_patched_copy = true.
- step2b_tokenizer_crosscheck.tokenizer_vocab_size = **248320** (post-fix).
- Raw per-criterion dicts:
```
1_finite_logits: {"name":"finite_logits_no_nonfinite","pass":true,"detail":{"p1":{"http":200,"n_logprob_values_checked":72,"n_nonfinite":0,"pass":true},"p2":{"http":200,"n_logprob_values_checked":126,"n_nonfinite":0,"pass":true}}}
2_semantics: {"name":"short_deterministic_semantics","pass":false,"detail":{"chat_arithmetic":{"expects":"51","http":200,"observed":false,"pass":false},"chat_capital":{"expects":"Paris","http":200,"observed":false,"pass":false},"chat_code":{"expects":"code compiles","http":200,"observed":true,"pass":true},"chat_tool":{"expects":"get_weather(city=Paris)","http":200,"observed":false,"pass":false}}}
3_cuda_graph: {"name":"cuda_graph_capture_and_replay","pass":true,"detail":{"capture_log_lines":62,"graph_error_lines":[],"decode_batch_replay_http":{"bs2":[200,200],"bs4":[200,200,200,200]}}}
4_fp8_kv: {"name":"fp8_e4m3_kv_confirmed","pass":true,"detail":{"dtype":"torch.float8_e4m3fn","tokens":8192,"reason":null}}
5_no_fallback: {"name":"no_quant_or_kernel_fallback","pass":true,"detail":{"fallback_count":0,"not_implemented_count":0,"fallback_samples":[],"not_implemented_samples":[]}}
6_sampled_coherence: {"name":"sampled_ge512_coherent_content","pass":false,"contract":{"temperature":1.0,"top_p":0.95,"top_k":20,"min_p":0.0,"seed":20260916,"repetition_penalty":1.0,"max_tokens":640,"chat_template_kwargs":{"enable_thinking":false}},"detail":{"function_csv":{"http":200,"classification":"EMPTY_CONTENT","n_completion_tokens":1,"finish_reason":"stop","content_loop_w4":0.0,"full_loop_w4":0.0,"content_n_chars":0,"reasoning_n_chars":0,"content_empty":true,"contains_replacement_char":false,"n_alpha_words":0,"pass":false},"longform_water":{"http":200,"classification":"DEGENERATE","n_completion_tokens":640,"finish_reason":"length","content_loop_w4":0.9735,"full_loop_w4":0.9735,"content_n_chars":2300,"reasoning_n_chars":0,"content_empty":false,"contains_replacement_char":false,"n_alpha_words":334,"pass":false},"explain_tcp":{"http":200,"classification":"DEGENERATE","n_completion_tokens":94,"finish_reason":"stop","content_loop_w4":0.9574,"full_loop_w4":0.9574,"content_n_chars":371,"reasoning_n_chars":0,"content_empty":false,"contains_replacement_char":false,"n_alpha_words":46,"pass":false}},"passing_probes":[]}
```
- criterion_report.failures = `['2_semantics','6_sampled_coherence']`; all_pass=false; verdict_failures same.
- diagnostics: `greedy_ge512` (longform_water DEGENERATE content_loop_w4=0.9607), `thinking_on` (EMPTY_CONTENT).

### E5. M3 report.json — provenance + raw criteria (`/mnt/.../runs/m3/report.json`)
- started_utc 2026-09-18T18:53:42Z, finished_utc 2026-09-18T19:02:07Z; verdict=FAIL; status=completed.
- source_preflight.actual_module_sha256 = `d51d5441064c13cb90da9af7399c067e072182e7bc8c362e72ea4ba6a11e3941`;
  expected_module_sha256 = `""`; identity_mode = `structural+recorded_sha256`; ok=true;
  structural_identity_ok=true; fold_helpers_present present; fold_call_wired_in_load_weights=true.
- proc_environ.PYTHONPATH = `<repo>/python`; pythonpath_is_patched_copy = true.
- step2b_tokenizer_crosscheck.tokenizer_vocab_size = **248320** (post-fix).
- Raw per-criterion dicts:
```
1_finite_logits: {"name":"finite_logits_no_nonfinite","pass":true,"detail":{"p1":{"http":200,"n_logprob_values_checked":72,"n_nonfinite":0,"pass":true},"p2":{"http":200,"n_logprob_values_checked":126,"n_nonfinite":0,"pass":true}}}
2_semantics: {"name":"short_deterministic_semantics","pass":false,"detail":{"chat_arithmetic":{"expects":"51","http":200,"observed":false,"pass":false},"chat_capital":{"expects":"Paris","http":200,"observed":false,"pass":false},"chat_code":{"expects":"code compiles","http":200,"observed":true,"pass":true},"chat_tool":{"expects":"get_weather(city=Paris)","http":200,"observed":false,"pass":false}}}
3_cuda_graph: {"name":"cuda_graph_capture_and_replay","pass":true,"detail":{"capture_log_lines":61,"graph_error_lines":[],"decode_batch_replay_http":{"bs2":[200,200],"bs4":[200,200,200,200]}}}
4_fp8_kv: {"name":"fp8_e4m3_kv_confirmed","pass":true,"detail":{"dtype":"torch.float8_e4m3fn","tokens":16384,"reason":null}}
5_no_fallback: {"name":"no_quant_or_kernel_fallback","pass":true,"detail":{"fallback_count":0,"not_implemented_count":0,"fallback_samples":[],"not_implemented_samples":[]}}
6_sampled_coherence: {"name":"sampled_ge512_coherent_content","pass":false,"contract":{"temperature":1.0,"top_p":0.95,"top_k":20,"min_p":0.0,"seed":20260916,"repetition_penalty":1.0,"max_tokens":640,"chat_template_kwargs":{"enable_thinking":false}},"detail":{"function_csv":{"http":200,"classification":"DEGENERATE","n_completion_tokens":640,"finish_reason":"length","content_loop_w4":0.9929,"full_loop_w4":0.9929,"content_n_chars":2917,"reasoning_n_chars":0,"content_empty":false,"contains_replacement_char":false,"n_alpha_words":320,"pass":false},"longform_water":{"http":200,"classification":"TOO_SHORT","n_completion_tokens":8,"finish_reason":"stop","content_loop_w4":0.0,"full_loop_w4":0.0,"content_n_chars":25,"reasoning_n_chars":0,"content_empty":false,"contains_replacement_char":false,"n_alpha_words":5,"pass":false},"explain_tcp":{"http":200,"classification":"TOO_SHORT","n_completion_tokens":7,"finish_reason":"stop","content_loop_w4":0.0,"full_loop_w4":0.0,"content_n_chars":25,"reasoning_n_chars":0,"content_empty":false,"contains_replacement_char":false,"n_alpha_words":2,"pass":false}},"passing_probes":[]}
```
- criterion_report.failures = `['2_semantics','6_sampled_coherence']`; all_pass=false; verdict_failures same.
- diagnostics: `greedy_ge512` (function_csv TOO_SHORT 2 tokens; longform_water TOO_SHORT 2 tokens;
  explain_tcp TOO_SHORT 640 tokens content_loop_w4=0.9938), `thinking_on` (EMPTY_CONTENT).

### E6. Production restored (identity-checked) and verified
```
$ cd /tmp/opencode/prod-service-20260917 && bash bin/start.sh m2
[19:02:21] preflight PASS: /opt/sglang/local-prod-v1.2.1-candidate-M2   (P2 manifest, P3 launcher, P4/P5 gates, P6/P7)
[19:02:39] port 30000 free
[19:02:39] L3 DISABLED for m2 (SGLANG_L3_MODE=disabled): no namespace allocated; /data/l3 untouched
[19:02:39] supervisor pid=1851473 (holds the canonical GPU lock for the server lifetime)
[19:04:33] === m2 UP ===  cold_start_s=111.8  lock_generation=1
pid=1851500 supervisor_pid=1851473 port=30000 tree=/opt/sglang/local-prod-v1.2.1-candidate-M2 run_id=m2-20260918T190239Z-1851237
START_RC=0
```
Post-restore verification:
```
loopback /health                              -> 200
loopback /v1/models                           -> 200
LAN http://192.168.20.250:30000/health        -> 200
LAN   http://192.168.20.250:30000/v1/models   -> 200
/v1/models body: {"object":"list","data":[{"id":"/data/models/omnicoder-9b-gptq-int4","object":"model","created":1789758278,"owned_by":"sglang","root":"/data/models/omnicoder-9b-gptq-int4","parent":null,"max_model_len":131072}]}
ss :30000: LISTEN 0 2048 0.0.0.0:30000 0.0.0.0:* users:(("python",pid=1851500,fd=68))
ss :30165: (no listener)
pgrep: 1851500 launch_server (M2) ; 1851964 sglang::scheduler
/proc/1851500/environ: PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate-M2/src/python
                         CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587
nvidia-smi compute: 1851500 (300 MiB) + 1851964 sglang::scheduler (18752 MiB)
lock: {"owner": "supervise-m2-m2-20260918T190239Z-1851237", "pid": 1851473, "generation": 1, "acquired": "2026-09-18T19:02:39Z"}
gpu-owner.json: role=m2 state=held pid=1851500 port=30000 tree=/opt/sglang/local-prod-v1.2.1-candidate-M2 identity=LOCAL-PROD-v1.2.1-M2 note=serving
```
Note: `start.sh` preflight logs a P6 LANDMINE warning that a bare `import sglang` would resolve to the
stale workspace copy; the launcher sets PYTHONPATH itself and the live server's `/proc` env confirms it
runs the frozen M2 tree, not the workspace. This is the scaffold's expected fail-closed behavior, not
a defect of this window.

## Defects or blockers

### D1 (dispatch defect, reconciled by substitution): `bin/stop.sh m2` does not exist
The dispatch authorizes `bash /tmp/opencode/prod-service-20260917/bin/stop.sh m2`, but that script's
case only accepts `prod|test|all`. Observed directly:
```
$ bash /tmp/opencode/prod-service-20260917/bin/stop.sh m2
[18:42:39] FATAL: unknown target 'm2' (want prod|test|all) 2
RC=2
```
Root cause: the F39 campaign added the `m2` role to `bin/start.sh` and `conf/service.env` but never to
`bin/stop.sh`; the M2-specific stop that WAS written, hash-pinned and installed is `bin/stop-m2.sh`
(sha256 `3d27a0cd4f728f6c9dd34df252cb6f7c2ca98f2f0f216c902ac49b96c75c3243`, matching the expected hash
recorded in `M2-FROZEN-TREE-INSTALL-20260918.md` E3/S12). `stop-m2.sh` implements exactly the required
safety contract: it identity-checks the recorded pid (cmdline must contain `launch_server`, port
`30000`, the M2 tree, and the M2 model), signals the supervisor first so it releases the canonical
flock, uses only graceful SIGTERM (SIGKILL only after a 240 s timeout), and never uses broad pkill.
The recorded pid/supervisor were pre-verified to satisfy those tokens.
**Decision (material, recorded):** to satisfy the dispatch's stated safety intent (identity-checked, no
pkill, never kill an unidentified process), production was stopped with the installed identity-checked
`bin/stop-m2.sh` rather than the non-existent `bin/stop.sh m2`. Restart used the authorized, proven
`bin/start.sh m2`. The safety contract was preserved; the literal command name differed. Orchestrator
should reconcile (implement `stop.sh m2` or correct the dispatch template).

### D2 (observation, not this task's to fix): the FAIL reproduces on post-fix bytes
Both models still FAIL criteria 2 and 6 with the fixed tokenizer in place (vocab_size=248320). This is
a real post-fix verdict, not a stale one. Root-causing those criteria is outside this window's
authority (gate result only). Two distinct signatures are notable: M4 criterion 6 shows
EMPTY_CONTENT for the function-call probe plus DEGENERATE long-form loops (content_loop_w4 0.957–0.974);
M3 criterion 6 shows TOO_SHORT outputs on two probes and a DEGENERATE loop on the third (0.9929).
Criterion 2 fails identically on both: chat_code passes, chat_arithmetic/chat_capital/chat_tool fail.

### D3 (gate configuration note): the gate does not pin `gguf_native.py`
`GGUF_GATE_MODULE_SHA256` was unset, so the gate records the norm-fold module
(`qwen3_5_text.py`) hash and does not hash-pin the tokenizer fix module. The tokenizer fix is proven
exercised indirectly via `tokenizer_vocab_size=248320` and PYTHONPATH resolution. If exact pinning of
the tokenizer bytes is required, the gate would need a tokenizer-module pin (gate change — out of
scope here).

## Remaining claims or exclusions
- ESTABLISHED: M4 and M3 post-fix gate verdicts are FAIL, read directly from the gate's own
  `report.json` (`verdict=FAIL`, `status=completed`, six criteria each, failures listed above).
- ESTABLISHED: the fixed tokenizer bytes were exercised (vocab_size 248320, GGUF_GATE_SRC default,
  PYTHONPATH in server `/proc`); the fixed module hash `0f3c8fb9...` was unchanged before and after.
- ESTABLISHED: production was identity-checked-stopped, then restored and verified UP (all four HTTP
  probes 200; GPU held by M2 supervisor/server; no :30165 scratch server).
- NOT ESTABLISHED / EXCLUDED: root cause of the M4/M3 criterion-2 and criterion-6 failures; whether
  the failures are tokenizer-related, sampling-contract-related, or model/quantization-related. This
  window only ran the gate and recorded its verdict. No product source, test, gate, /opt, or /data was
  edited; nothing was committed or staged. No `pkill`/`killall` was used; no unidentified process was
  signalled.
- DEVIATION: used `bin/stop-m2.sh` instead of the literal (non-existent) `bin/stop.sh m2`; see D1.

## Terminal state: DONE
