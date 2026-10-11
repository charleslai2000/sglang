# G3-PROFILE-C-C8-DECODE-20260908

- **工作标题：** G3-PROFILE-C-C8-DECODE-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
对已 admission 的 Profile C8 候选（并发上限 8、Mamba pool 40、decode graph max 8）执行三次固定长度 native decode benchmark，并保留吞吐、延迟、load 与 GPU telemetry。

## 实际改了什么
远端 benchmark 执行；候选 PID 497622/loopback 18037，使用 native serving runner、`random-ids` + tokenizer、ISL/OSL=1024/256、C=8/N=64、seed 42、每次 flush，三次测量。无 product/source 改动、外部数据集或模型下载。

## 生成结果与验收
三次均 rc=0，64/64 成功，无 runner HTTP failure；output TPS 为 36.61/36.56/36.54，total TPS 183.07/182.79/182.68 tok/s。报告指出 stderr 有 non-fatal `multiprocess.resource_tracker` traceback，结果与请求仍成功。原始 JSONL、日志、loads、PID/args、query 与 dmon artifacts 保存在报告列明的目录。该项是 C8 的实际 decode 测量；不单独构成跨 C1/C6/C8 的最终优化结论，且验证报告另记有证据限制。


### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-PROFILE-C-C8-DECODE-20260908.md`：Remote: `/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c8-python-20260908/measure/`
Local: [raw artifacts](./raw/g3-profile-c8-python-20260908/)
SHA-256 is recorded in `raw/g3-profile-c8-python-20260908/SHA256SUMS.txt`.
The three runner JSONL hashes are:
`repeat1 44759604dbcc23fd99fc761dd297757088593761e8ba927cbe19766fedcb38af`,
`repeat2 6644ab4d75f22b0d6b02d21383879f6678459b93e56f296d88d6d8df15c451ff`,
`repeat3 81aeaf95b0a28d32eb4c37b5d329eb4dbe0b2c473783e37125097e69a5d43330`.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C8-DECODE-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C8-DECODE-20260908.md`; SHA256 `728ea29a1b0a03566a51a47a90f3c369cbcbe57635f89edaf6ee08844119195d`; source state `local-only`
