# G3-PROFILE-C-C8-RESTORE-20260908

- **工作标题：** G3-PROFILE-C-C8-RESTORE-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在 Profile C8 candidate run 完成后，按冻结 v1 argv 恢复原服务，并以 PID/端口/health/loads/模型及参数身份核验还原。

## 实际改了什么
只进行授权 host 上的运维还原：身份核验后停止 C8 PID `497622` 及其子进程，随后启动冻结 v1。未改产品、模型或 benchmark inputs；restore evidence 保存在 C8 run 的 restore 目录。

## 生成结果与验收
报告状态 **done**，restore verification 通过：v1 health HTTP 200，loads idle，8035 由 restore PID `503601` 持有、C8 候选端口 18037 不再监听；冻结模型/parser/KV/Mamba/template 参数及哈希身份核验见报告。此为当时的 restore 结果，不表示当前服务状态。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C8-RESTORE-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C8-RESTORE-20260908.md`; SHA256 `e23143fa67721d5ab82176d72967ae0b161c0d6d5ece8a64d2ece0200605a76a`; source state `local-only`
