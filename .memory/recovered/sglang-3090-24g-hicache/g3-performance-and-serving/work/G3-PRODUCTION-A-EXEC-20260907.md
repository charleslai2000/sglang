ENTRY: ACCEPT

status: blocked

reason: NEEDS_REASONING — Production Profile A runner is deterministically OOM-killed. 3/3 C1 measured repeats each died at rc=137 with `anon-rss ≈ 42.6GB` (host total 48GB, 0 swap free), identical signature to the two prior-halt runs documented in runbook Section 0 item 18. Per runbook Section 5.5 (abort when any repeat exceeds ~8GB RSS; never measure under OOM; never retry in loop) and dispatch Step 2/5 (report blocked with full evidence on OOM; do NOT report done), I halted the wrapper, wrote HALTED.txt, kept all evidence, and restored a clean idle service state. No `result.jsonl` was produced for any repeat, so no measurement exists and none is claimable. Further progress requires diagnosing WHY the runner balloons to ~42.6GB and authorizing a changed execution method (the runbook's frozen command set cannot run on this host as-is).

artifacts:
- RUN_ID: prod-a-20260907-105255
- Remote artifact root: /data/qwen3-g3-baseline/prod-a/prod-a-20260907-105255/
- Wrapper: /data/qwen3-g3-baseline/prod-a/prod-a-20260907-105255/run-production-A.sh (sha256 70d6243cb4fff34af1d03cb4cf4f745949a7dd4c261246287237a471870c2969)
- HALTED.txt: /data/qwen3-g3-baseline/prod-a/prod-a-20260907-105255/HALTED.txt
- OOM evidence: /data/qwen3-g3-baseline/prod-a/prod-a-20260907-105255/oom-evidence-dmesg.txt
- Per-repeat evidence (all rc=137): C1/repeat-{1,2,3}/runner.exit-code.txt, runner.stderr.txt, command.txt, server-log-delta.txt, nvidia-smi-dmon.txt, loads-before/after.json
- progress.log: /data/qwen3-g3-baseline/prod-a/prod-a-20260907-105255/progress.log
- artifacts.sha256: /data/qwen3-g3-baseline/prod-a/prod-a-20260907-105255/artifacts.sha256
- service preflight/postflight: /data/qwen3-g3-baseline/prod-a/prod-a-20260907-105255/service/{preflight,postflight}/
- NO aggregate/prod-a-report.json (blocked before any measurement)

evidence:
- procedure: executed runbook Section 8 frozen 9-invocation set (C1/C4/C5 x 3 reps, random-ids + --tokenize-prompt, seed 42, warmup-3 + flush + measure each) via a copy of the frozen wrapper base /data/qwen3-g3-baseline/production-A-20260907/G3-PRODUCTION-A-20260907T100230Z/run-production-A.sh with ONLY the Appendix A / Section 8 documented modifications applied (no --tokenizer; --dataset-name random-ids + --tokenize-prompt; --warmup-requests 3 every repeat; guaranteed stop_telemetry via EXIT trap; --model <GGUF> per Section 8; per-repeat result.jsonl + Section 2 artifact set). Diff of modified wrapper vs frozen base reviewed; sha256 matches confirmed; bash -n passed.
- pre-execution hygiene: orphaned dmon PIDs 340306 (-> T101034Z/C1/repeat-3/nvidia-smi-dmon.txt) and 338006 (-> T100230Z/C1/repeat-3/nvidia-smi-dmon.txt) inspected via ps/fd (both PPID=1, cmd `nvidia-smi dmon -s pucvmt -d 1 -o DT`, no children) then TERM-killed and confirmed gone. No leftover benchmark/runner processes. PID 298123 alive, /health=200, GPU idle (0%, single resident compute app 315744 22778MiB), cmdline sha256 7832781e755152980cc32aafb518117a97cdfa0b08facd0f3611bd2c2b58e9bf == prior frozen snapshot (T100230Z expected-cmdline.sha256).
- wrapper launch: `setsid nohup bash <RUN>/run-production-A.sh > <RUN>/run-production-A.outer.log 2>&1 < /dev/null &` on the remote host (detached so transient SSH disconnect cannot kill measurement). Wrapper main PID 347612.
- material_exit_status: C1 repeat-1 rc=137, repeat-2 rc=137, repeat-3 rc=137. C4 repeat-1 INTERRUPTED (executor stop). No measured repeat completed; no result.jsonl anywhere (0 files).
- before_state: service healthy, GPU idle, cmdline frozen-hash intact.
- after_state: service PID 298123 alive, /health=200, GPU idle 0%, single resident compute app 22778MiB, cmdline sha256 STILL 7832781e... (frozen profile byte-identical, service-invariant.txt = pass for all 3 C1 repeats), no leftover runner/wrapper/dmon procs, HALTED.txt present.
- OOM evidence (dmesg, three kills matching the three C1 runners at uptime 152890-153014): PID 366533 total-vm:68260992kB anon-rss:42646340kB; PID 367021 total-vm:68261892kB anon-rss:42658948kB; PID 367646 total-vm:68260860kB anon-rss:42658552kB. (anonymous RSS ~42.6GB each; host 48GB RAM total, swap 0 free.)
- runner stderr (C1 repeat-1): `run-production-A.sh: line 162: 347720 Killed  PYTHONUNBUFFERED=1 "${runner[@]}"`
- executed command (byte-identical to frozen Section 8, C1 repeat-1; same form for all repeats):
  cd /data/sglang-qwen35
  PYTHONUNBUFFERED=1 /data/sglang-qwen35-env/bin/python -m sglang.benchmark.serving --backend sglang --base-url http://127.0.0.1:8035 --model /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf --dataset-name random-ids --random-input-len 2048 --random-output-len 512 --random-range-ratio 1.0 --request-rate inf --seed 42 --max-concurrency 1 --num-prompts 20 --tokenize-prompt --output-details --output-file <RUN>/C1/repeat-1/result.jsonl --flush-cache --flush-cache-timeout 60 --warmup-requests 3
- verification: no measurement produced (0 result.jsonl), so Section 10 completeness cannot be asserted; only the OOM-halt path was verified (HALTED.txt present, service unchanged, no leftover procs, telemetry files captured per repeat before the kill).

summary:
Production Profile A cannot be measured under the frozen binding on this host. The runner deterministically OOMs to ~42.6GB anonymous RSS (well above the runbook's ~8GB abort threshold) on every C1 repeat before any `POST /generate` reaches the server (C1 server-log-delta shows only GET /v1/loads + GET /v1/models, no POST). This exactly reproduces the two prior-halt runs (rc=137) recorded in runbook Section 0 item 18. I followed the abort protocol: stopped the wrapper process tree and its orphaned runner, wrote HALTED.txt with full evidence, captured service pre/postflight, and confirmed the service is byte-identical and healthy afterwards (PID 298123, /health 200, cmdline hash unchanged, GPU idle, one resident compute app). No service/model/frozen-profile change was made. Status is blocked, NOT done — no measurement was obtained and none is claimable.

followups:
- Orchestrator/devops: diagnose root cause of the runner's ~42.6GB anonymous-RSS OOM under the frozen binding (candidate areas, for the decision-owner to evaluate: unbounded tokenizer/transformers import on the no---tokenizer GGUF AutoTokenizer-from-pretrained path; HF/tokenizers cache; torch/transformers import memory; possible page/zone pressure in the 48GB container with 0 swap). This is a changed-method decision requiring authorization.
- If a memory-bounded execution method is authorized (e.g. cgroup/ulimit memory cap with graceful failure, or an alternate verified tokenizer resolution that stays length-faithful and byte-identical pre/post MMQ), a fresh RUN_ID under /data/qwen3-g3-baseline/prod-a/ must be dispatched and run; never retry in-place on the same RUN_ID.
- Independent reviewer: confirm service unchanged (cmdline hash 7832781e... still equals frozen snapshot), HALTED.txt absent only after a successful rerun, no result.jsonl in this halted run, and the OOM evidence in dmesg.

open_issues:
- Root cause of the runner OOM is NOT diagnosed (out of executor scope — requires devops/orchestrator reasoning + authorization for a changed method).
- No Production-A measurement exists for any point/repeat.
- The two prior-halt runs (T100230Z, T101034Z) and this run all OOM at C1 with the same signature, indicating a deterministic environmental/runner condition, not a transient spike.
