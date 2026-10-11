# G3-PROFILE-C-C6-RESTORE-20260908

- **工作标题：** G3-PROFILE-C-C6-RESTORE-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在 Profile C6 decode 测量完成后，身份核验并停止 C6 候选服务，按冻结 v1 参数恢复 8035 服务并核验 health/load/model/runtime identity。

## 实际改了什么
对授权 host 执行 C6 候选 PID 的精确身份检查与停止，随后启动 frozen v1；未改产品、模型或 benchmark inputs。远端 restore artifacts 留存在 C6 run 对应目录。

## 生成结果与验收
报告状态 done，v1 restore health HTTP 200、loads idle，8035 由 restore PID 503601 持有、C8/C6 候选端口不在本项范围；frozen flags 和 model identity 核对通过，详见报告。此为历史 restore 结果，不代表当前服务状态或额外 benchmark 通过。

## 生成结果与验收
- **原报告状态：** done

**`g3-baseline-20260907/work/G3-PROFILE-C-C6-RESTORE-20260908.md`：**
Restored the unchanged frozen v1 service after the completed C6 candidate
measurement. No product files, model files, profile flags, or benchmark inputs
were changed.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C6-RESTORE-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C6-RESTORE-20260908.md`; SHA256 `d9beb73c3094c8cf9d5ef9f1ee324a93d5ebe22b97f10d79aa19830be2505acb`; source state `local-only`
