# p2io-coder-e19

- **工作标题：** p2io-coder-e19
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-coder-e19.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/p2io-coder-e19.md`：**
两处 P0 修复完成。Fix 2 根因：writeback 分配经 `getattr(...,"alloc_writeback",...)` 在
HostPoolGroup（无此方法）上静默回退到 reserve 封锁的 alloc，reserve 成黑洞——已加 group facade +
margin floor（writeback cap C−margin，可侵入 reserve；normal 仍 cap C−reserve−margin；RH 不变）。
Fix 1：三事件本就在且可达，B_ep/B_fin 不可测是容量后果；补 `restore_success` issued→satisfied
等价物 + metric_compare 双口径解析。全门 327 绿。

### 报告列出的产物/证据
- `phase2-hicache-design/work/p2io-coder-e19.md`：- `python/sglang/srt/mem_cache/pool_host/group.py` — 新增 `HostPoolGroup.alloc_writeback(...)`：
  D→H writeback 分配的 facade。这是 Fix 2 的**根因**——两个 host cache controller 的 `write()`
  用 `getattr(mem_pool_host, "alloc_writeback", mem_pool_host.alloc)` 选分配器，而 HiCache 栈的
  `mem_pool_host` 是 HostPoolGroup（无 `alloc_writeback` 方法）→ 静默回退到 reserve 封锁的
  `group.alloc(writeback=False)`。reserve 因此成为"永久禁用容量"，writeback 通道也消费不了它
  （解释 22.9K reserve 保留但 writeback 仍因只剩 46 tokens 失败）。新方法转发 `alloc(writeback=True)`。
- `python/sglang/srt/mem_cache/pool_host/base.py` — `alloc_writeback` 增加 **margin floor**：
  冻结语义 `D→H writeback occupancy ≤ C − margin`（writeback 可侵入 reserve，但不得耗尽 margin）。
  原实现无 margin 检查。…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-coder-e19.md` → `.memory/phase2-hicache-design/work/p2io-coder-e19.md`; SHA256 `e72ec4a34ae2d1dbcfddd870304f9f232d65e0c3c2cb5319fc9b8b0131ac5636`; source state `tracked`
