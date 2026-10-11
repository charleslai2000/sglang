# P0-C-3090-PROFILE-FREEZE-20260911-R117

- **工作标题：** P0-C-3090-PROFILE-FREEZE-20260911-R117
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P0-C-3090-PROFILE-FREEZE-20260911-R117.md`：**
Frozen profile summary (live 3090, `http://127.0.0.1:30000`):
- argv: exact 34-element PID-48746 cmdline; launch-r112.sh sha256 `2259d406...caaa3`; cwd `/home/dev-codex/workspaces`; env (UUID pin, CPATH/LIBRARY_PATH/LD_LIBRARY_PATH, SGLANG_HICACHE_FILE_*) from `/proc/48746/environ`.
- software: HEAD `4f41f5ba...d13637`; python 3.12.3; torch 2.13.0+cu130; triton 3.7.1; transformers 5.12.1; sglang 0.0.0.dev0 @ repo python path; CUDA runtime 13.0; driver 580.178.04.
- hardware: RTX 3090 GPU 1, UUID `GPU-2e3ed202-...6587`, SM86, 82 SMs, 24576 MiB; host Ryzen 5 3600X 12 CPU, RAM 32780588 kB.
- model: `/mnt/data/models/qwen35-gptq`, qwen3_5, GPTQ 4-bit; command/tokenizer hashes; model.safetensors 3803687648 B.
- capacity: mem_fraction_static 0.82; max_total_tokens 65536; max_running_requests 1; max_mamba_cache_size 53; chunked_prefill 2048; max_prefill_tokens 16384; kv_cache_dtype fp8_e4m3; page_size 1; context_len 262144.
- HiCache: cache/2.0/write_through/kernel/page_first/file/wait_complete/spec 0.6; ready-horizon on, frontier_n 8, watermarks 55000/110000.
- host KV pool 131073 tokens / 2.15 GB; host Mamba 5.51 GB (bytes); L3 dir 20455358464 B, 484747 files.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done (read-only; PID 48746/48806 unchanged, /health 200 at end).

没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4f41f5ba`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-C-3090-PROFILE-FREEZE-20260911-R117.md` → `.memory/rh-p0c-runtime-provenance/P0-C-3090-PROFILE-FREEZE-20260911-R117.md`; SHA256 `8d78174e3c6c67945d3ab6d66640f0253727d6f12afd10a21e0676dbac1f7ffb`; source state `tracked`
