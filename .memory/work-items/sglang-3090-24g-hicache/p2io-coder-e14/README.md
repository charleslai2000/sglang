# p2io-coder-e14

- **工作标题：** p2io-coder-e14
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-coder-e14.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/p2io-coder-e14.md`：**
M3 按用户裁决重做完成：三修补（epoch_sig 排除+cooldown+decline-park）整体替换为 **per-rid causal negative-cache / event-driven eligibility**。每个 decline reason 订阅唯一能改变它的 causal epoch，cursor 方向性比较，确定性 miss 不再瞬态重试；cooldown 降级为 1s safety fuse（仅异常风暴 rate 上限，正确路径节奏是 causal epoch 推进而非等待）；每 rid 每 causal epoch 至多一次 staging attempt（cursor 记录天然保证）；v0 保守 staging 只对完整前缀（storage_hit==requested_prefix）进 READY 池，partial 不 stage。NO_L3 唯一清除事件：l3_publish 推进 / prefix 变 / generation 变 / fuse（保险丝，与订阅事件叠加）；普通 pass、running batch、READY pool 变化不解除。M1（headroom 模型 2x21K 链可达）与 M2（spec eviction=0）成果不动。ready_stage 日志保留 attempted/issued 区分。

### 报告列出的产物/证据
- `phase2-hicache-design/work/p2io-coder-e14.md`：- `python/sglang/srt/managers/scheduler_components/ready_horizon.py` — M3 按用户升级规格重做（替代 e14 之前的三修补 epoch_sig+cooldown+decline-park）：
  - 新 `DeclineReason(Enum)`：NO_L3 / NO_HEADROOM / SPEC_BUDGET（每 reason 订阅唯一 causal epoch：NO_L3→l3_publish、NO_HEADROOM→host_headroom、SPEC_BUDGET→spec_budget，`subscribed_epoch()` 订阅表）。
  - 新 `NegativeCacheEntry(msgspec.Struct)`：reason + 订阅 epoch cursor（decline 时刻）+ 请求身份指纹（prefix_len/generation）+ safety-fuse expiry。msgspec.Struct 符合 no-dataclasses 规则。…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-coder-e14.md` → `.memory/phase2-hicache-design/work/p2io-coder-e14.md`; SHA256 `bb75c925f8a77925207b6937676e3207da83bd3fb9900a10858ff7d3bc198523`; source state `tracked`
