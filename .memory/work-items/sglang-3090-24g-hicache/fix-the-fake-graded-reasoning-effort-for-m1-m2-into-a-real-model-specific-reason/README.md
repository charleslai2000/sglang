# Fix the fake graded `reasoning_effort` for M1/M2 into a real, model-specific reasoning

- **工作标题：** REASONING-EFFORT-POLICY-IMPL-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/REASONING-EFFORT-POLICY-IMPL-20260918.md`：**
policy for the Qwen3.5 family, using a narrow policy plus the existing SGLang thinking-budget
infrastructure. This is a runtime policy, NOT a native model capability and NOT a claim that the
weights were trained to obey it.
- Date: 2026-09-18
- Role: `debugger-deep` under an explicit owner-authorized edit grant limited to the write domain below
- Tree edited: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`
- Served tree (`/opt/sglang/local-prod-v1.2.1-candidate`) was read-only reference and is byte-unchanged
- Terminal state: **DONE**

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。

### 报告列出的产物/证据
- `phase2-hicache-design/agents/REASONING-EFFORT-POLICY-IMPL-20260918.md`：Real `sha256sum` BEFORE -> AFTER for each changed file (hashes are the real output):
| File | BEFORE | AFTER |
|---|---|---|
| `serving_chat.py` | `7b05e6ab1d09a71ce253040c9cd62ea7c55a52020b44cf9b76d91c8df9e23240` | `7069e941fe3525a9fae230989fcbddf1c14c4f80711cf43a97f3295adbe713f2` |
| `custom_logit_processor.py` | `e0e0ab65e2ded8975a9d161a52c92cb61f2a8a02a6af485b37912cad1171e23d` | `2106810601b65f488d5b4972d7628e1aae201713cb8cd370ba909255d1bf8693` |
| `environ.py` | (git HEAD) | `dd97145e844a61ce00654daf915b291a69d6f7c90730b74ff184fa595e8779dd` |
| `qwen35_reasoning_policy.py` | ABSENT | `968bea87d50db29351a2156187fa2c782fa76e5ed896abeb92b4f1f8a452e22d` |…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/REASONING-EFFORT-POLICY-IMPL-20260918.md` → `.memory/phase2-hicache-design/agents/REASONING-EFFORT-POLICY-IMPL-20260918.md`; SHA256 `7ca43339d30fb19938042d22fce9d1f39c4be88dfac161590b3e4390ae727af4`; source state `tracked`
