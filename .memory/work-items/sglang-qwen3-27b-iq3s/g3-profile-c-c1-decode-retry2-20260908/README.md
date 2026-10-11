# G3-PROFILE-C-C1-DECODE-RETRY2-20260908

- **工作标题：** G3-PROFILE-C-C1-DECODE-RETRY2-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在已 admission 的 Profile C1 候选服务（并发上限 4）上执行三次独立 decode 测量，使用固定 1024/256 random-ids workload、每次 cache flush 与单次 warmup 规则，保存原始结果和 telemetry。

## 实际改了什么
这是远端 benchmark 执行任务，无产品文件改动。向 loopback 18035 候选 PID 478926 连续运行三次原生 `sglang.benchmark.serving`，离线/no-proxy，C=4、N=32、seed 42、random_range_ratio=1.0、tokenize-prompt、显式 tokenizer sidecar；warmup 为 3/0/0，逐次 flush。

## 生成结果与验收
三次皆 RC 0，32/32 成功，无 HTTP error/timeout/zero-progress。报告各轮 output TPS 约 33.96/33.90/33.91，total TPS 约 169.81/169.50/169.54；该测量报告不是对数据的独立审查，独立核验卡另行说明限制。远端 RUN_ID、原始 JSONL、日志与 telemetry 路径见报告。不得把 runner 声称 peak concurrency 8 当作有效服务并发证明。
ENTRY: ACCEPT
Invocation status: done
Executed on `175.155.64.171:22109`, loopback candidate `127.0.0.1:18035`, PID `478926`. Health was 200 and loads idle before execution; port 8035 was not touched. Candidate args included `--max-running-requests 4 --max-mamba-cache-size 20 --cuda-graph-max-bs-decode 4`.
Native command (repeated three times, warmup requests `3,0,0`):
```text
/data/sglang-qwen35-env/bin/python -m sglang.benchmark.serving --backend sglang --base-url http://127.0.0.1:18035 --model /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf --tokenizer /data/models/Qwen3.8-27B-GSQ-RCO-GGUF --dataset-name random-ids --tokenize-prompt --random-input-len 1024 --random-output-len 256 --random-range-ratio 1.0 --request-rate inf --seed 42 --max-concurrency 4 --num-prompts 32 --output-details --output-file <repeat>.jsonl --flush-cache --flush-cache-timeout 60 --warmup-requests <3|0>
```
Offline environment variables were set (`HF_HUB_OFFLINE=1`, `HF_DATASETS_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, proxies empty, `NO_PROXY=*`). No audit hooks or product edits were used. Runner version was `0.5.10.dev0`.


### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-PROFILE-C-C1-DECODE-RETRY2-20260908.md`：Remote: `/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c1-decode-retry2-20260908/`
Local: `.memory/g3-baseline-20260907/work/raw/g3-profile-c1-decode-retry2-20260908/`
Artifacts include runner JSONL/logs, driver log, service PID/args, health, per-repeat `/v1/loads?include=all` snapshots, and `nvidia-smi dmon -s pucvmt` plus query telemetry. Local JSONL hashes:
```text
c172f6deddf06d66ac12b1d016d9bc8fb9efd5a1c0cf5aabbd7d074c8f5fc883  runner/repeat-1.jsonl
dc27ce7b102674b9d86d25da33ae80b886f7fc85ee5acf1ff43730a0b8b08899  runner/repeat-2.jsonl
9fc6804a3d2b23fd176821709411daded16deebfe1292678d1f76393b540cad8  runner/repeat-3.jsonl
```…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C1-DECODE-RETRY2-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C1-DECODE-RETRY2-20260908.md`; SHA256 `8e2272145741d62899743e3788161dc3a67c79c5f783341cbbeb286aaf652cfc`; source state `local-only`
