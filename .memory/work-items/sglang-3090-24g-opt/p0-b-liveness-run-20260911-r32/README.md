# P0-B-LIVENESS-RUN-20260911-R32

- **工作标题：** P0-B-LIVENESS-RUN-20260911-R32
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P0-B-LIVENESS-RUN-20260911-R32.md`：**
artifacts:
- Executor report: `.memory/phase2-hicache-design/work/P0-B-LIVENESS-RUN-20260911-R32.md`
- Raw evidence: `.memory/phase2-hicache-design/work/R32-artifacts/`
- Report SHA256: `a6ddc7a99a8446462b14a34141d3f50f6d962ddd99f9ae6c57a45a629e19d1f4`
evidence:
- Authorized remote confirmed: RTX 3060 12 GiB, compute capability 8.6.
- Dependencies verified: Python 3.11.11, pytest 9.1.1, orjson 3.12.0,
msgspec 0.21.1, torch 2.6.0+cu124/CUDA 12.4.

## 实际改了什么
在授权 RTX 3060 远端核实环境/以 SHA256 对齐无 `.git` checkout 后运行 focused suites；无 3090/production、产品/test/gate/storage/Git/server changes。另保存 R32 raw evidence bundle。

## 生成结果与验收
三组结果：focused suite 262 pass/11 fail；exact HOST_ALLOC unit 7/9 pass；targeted terminal/wake/full-span 6/7 pass，均有非零失败。无 dedicated HOST_ALLOC live driver；既有 log 中 `rid`、`attempt_id`、`causal_rid` 为 null，不能相关联出 FIFO retry、full KV+Mamba restore 与 READY 的硬链。结论 **P0-B NOT_VERIFIED**；这是真实证据阻塞，不是生产证据。远端无 `.git`，虽按 SHA256 对齐，revision 无 Git-verifiable identity。

各测试失败率、日志缺少关联以及 NOT_VERIFIED 结论已按原报告列明；无 live-chain pass。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-B-LIVENESS-RUN-20260911-R32.md` → `.memory/rh-p0b-harness-durability/P0-B-LIVENESS-RUN-20260911-R32.md`; SHA256 `585a0499c8a2e2c15542beaaa1d65c92a8f45d4ac8ad8e60047582678e7ae45d`; source state `tracked`
