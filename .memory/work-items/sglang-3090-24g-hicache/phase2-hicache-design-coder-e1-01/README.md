# phase2-hicache-design-coder-e1-01

- **工作标题：** phase2-hicache-design-coder-e1-01
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-coder-e1-01.md`：**
**done** — 12 项指标可得性矩阵完成，17 条 grep 验证命令实际执行全部命中，交付
metric-availability.md。只读勘察（未修改任何引擎/工具文件），仅新增交付文档 + 本报告。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-coder-e1-01.md`：**
12 行矩阵逐项落在四类来源（/metrics、引擎日志、b15 探针、driver 产物）上：8 行
direct 由注册点+递增点+driver 解析链三重证据支撑；2 行 derived 给出修正后公式与
同周期保证；2 行 absent 给出缺失原因与 P2-1 依赖登记（D1/D2）。勘察最重要的新发现：
① 本 checkout 无 t38sb 观察到的 "HiCache prefetch success" 日志行（部署差异，07 需
实测引擎实际日志形态）；② prefetch 预算门（prefetch_rate_limited）拒绝路径静默
（cache_controller.py:1212 → hiradix_cache.py:1499 return 0 无任何可观测输出）；
③ pa_lb_init 探针缺 mem_quota 字段但 host_hit_length 够分类用；④ mamba 池总容量
gauge 缺失。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-coder-e1-01.md`：- **新建** `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/metric-availability.md`
  —— 12 行可用性矩阵（R1-R12）+ 专项核实 4 项 + 验证命令汇总 V1-V17 + P2-1 依赖登记
  D1-D6 + open issues。任务唯一交付物。
- 本报告 `phase2-hicache-design-coder-e1-01.md`。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-coder-e1-01.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-coder-e1-01.md`; SHA256 `11b605d623a6b266703cfffd0b3133c0c343985913e6bc38a393debd6db48bea`; source state `tracked`
