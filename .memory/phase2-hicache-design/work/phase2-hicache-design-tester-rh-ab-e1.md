# phase2-hicache-design-tester-rh-ab-e1 — RH recycle=0 决定性 A/B 阻断报告
status: blocked
epoch: 1
task: RH recycle=0 决定性 A/B（extent_recycle==0 下 RH OFF vs RH ON 四 Gate 对比）
owner: tester

## 0. 结论速览（BLOCKED — 两个独立阻断项）

本实验 **未启动、未产生任何运行产物、未对远程机做任何改动**。
请在派发级核实以下两个阻断项，二者均可独立阻断本实验：

1. **前提阻断：当前性能 sweep 未完成。** 单元格电池组只完成 cell-1(p32-gOFF)；
   cell-2(p32-gON) 因 ninja PATH bug 于 03:55 崩溃（FileNotFoundError: ninja），
   之后 devops 未续跑 cell-2..8；截至远程 04:43 无新证据/无进程/GPU 0%。
   按任务硬性要求"必须等 sweep 完全结束后串行启动"，条件未满足即不能启动。
   （sweep 当前"暂停中"而非"运行中"——若启动不会抢 GPU，但用户要求的是"结束后"，
   非"空闲时"。需 devops 先续跑完成，或用户明确豁免。）

2. **容量阻断：128G（乃至 192G）无法保证 extent_recycle==0，本盘可行性存疑。**
   extent allocator 的 recycle 由 cursor-wrap（累计写字节>文件容量）+ GC eviction
   （live>max_size×0.9 或磁盘<min_free 10G）触发。同 trace（agents8/wt4/rt400）下
   **pool=106（本实验强制配置）的写量**：
   - Run A (RH OFF, gate3-soak)：首 15 分钟 210 GB 累计写；
     2h 总写 1435 GB（39068 次 extent_write）。
   - Run B (RH ON, gate3-rhon)：首 15 分钟 174 GB 累计写。
   → **FILE_SIZE=128G 在首 15 分钟内就被累计写超过**，cursor-wrap recycle 必然在
   提前完成前出现（历史各轮首 recycle 均在写后 7-10 分钟：soak 19:00:01 /
   rhon 21:20:04 / sweep-p32 03:44:02，file=64M×1430=91.5G 时）。
   据此 128G 在本 trace 下 **提前必然触发 extent_recycle>0 → 硬性 INVALID**。

## 1. 执行记录（本 epoch）

| 阶段 | 结果 |
|---|---|
| 远程连通/nvidia-smi/进程扫描 | OK（GPU 0%,15MiB；无 sglang/gate2_load/gate3_soak 进程） |
| sweep 状态核查 | 见阻断项 1（cell-1 done，cell-2 ninja 崩溃，之后暂停） |
| 容量可行性计算 | 见阻断项 2（128G 首 15min 即被写超过） |
| wrapper 生成 | **未生成**（阻断项成立前不落地任何改动） |
| 两轮 A/B 运行 | **未运行**（不满足启动前提 + 容量硬条件无法保证） |
| 逐 key trace / 四 Gate 表格 | **未采集**（无有效运行） |

## 2. evidence 路径（全部只读，未改）

- 远程 3090 (root@175.155.64.171:24052) SSH key ~/.ssh/id_ed25519
  - sweep 状态：/root/gate3-sweep-p32-gOFF-status.log（cell-1 rc=0）
  - cell-2 崩溃：/root/engine-gate3-sweep-p32-gON.log（tail，FileNotFoundError: ninja）
  - Run A gate3-soak：/root/engine-gate3-soak.log（2h，39068 writes/1435GB，recycle 6454）
  - Run B gate3-rhon：/root/engine-gate3-rhon.log（recycle 36984）
  - 单 cell sweep-p32-gOFF：/root/engine-gate3-sweep-p32-gOFF.log（292 recycle）
  - 引擎源码：/root/sglang-b1-continuity/python/sglang/srt/mem_cache/storage/extent/
    extent_file_backend.py + extent_allocator.py（recycle 触发条件：_drop_slot /
    _gc_evict / plan cursor-wrap）
  - 磁盘：/data 197G，free 92G，leftover p2io-gate3-sweep-p32-gOFF 89G
- 本地 ledger：/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/
  phase2-hicache-design/ledger.md（L875-889 用户批准 A/B + 确定性核查）
- 本地 closeout：.../work/phase2-hicache-design-orchestrator-gate3-closeout-e1.md
  （Run A/B 2h 基线 + RH ON restore 失效 + 5.7x recycle 放大归因）

## 3. 关键数据（用于用户裁决）

### 3.1 写量（同 trace，pool=106 强制配置，python 精确窗口测量）
| 轮次 | RH | 首 15 分钟写量 | 2h 总写量 |
|---|---|---|---|
| Run A gate3-soak | OFF | **211 GB/writes=5837** | 1435 GB / 39068 |
| Run B gate3-rhon | ON | **174 GB/writes=4659** | 1372 GB / 37135 |
| sweep-p32(池32) | OFF | 155 GB/4353（~17min，rt=400 同 trace） | — |

结论：任一轮首 15 分钟写量都 >128G → 128G 提前必 recycle。

### 3.2 recycle 触发几何
- allocator file = extent_size(64M) × num_slots(1430) = 91.5G（gate1/gate3 默认 FILE_SIZE=96G）
- MAX_SIZE=64G + eviction_ratio=0.9 → live>57.6G 触发 GC eviction（sweep-p32 观测）
- cursor-wrap：累计写>91.5G（或 128G）即触发
- 两机制都 generation++ → batch_exists/read 侧 miss

### 3.3 首 recycle 时间（先于本次实验已存在，非新引入）
| 轮次 | 首 recycle | 距首写 |
|---|---|---|
| soak | 19:00:01 | ~+6min |
| rhon | 21:20:04 | +~2min |
| sweep-p32 | 03:44:02 | ~10.5min |

## 4. 裁决（三向中的判定——本轮无法定稿 A/B）

因无法启动，本 epoch **不产出 A/B 三向裁决**。仅产出阻断级结论：
- 并非"RH 独立状态机 bug vs 容量 thrashing 之争"的实验被执行——而是**实验前置条件
  与本盘物理容量冲突**，128G/192G 都无法保证 recycle=0。

## 5. 给用户/orchestrator 的候选路径（需用户拍板，我不擅自执行）

A. **缩短窗口**（如 rt=100~150，~10-12 min）使累计写 <128G 保 recycle=0 —— 属
   "缩短窗口"，红线需用户同意；且改变 trace 形状（偏离批准口径 rt=400）。
B. **修改负载/写密度** —— 违反"同 trace + 不改负载"红线，不推荐。
C. **扩容磁盘**：192G 需要 197G 盘删掉 89G leftover 后 ~181G 可用，仍 <192G；
   且 pool=106 写速率 ~14G/min，192G 也会在首 ~14min 后 cursor-wrap。
   结论：仅靠增大 FILE_SIZE 不解决，需配套缩短窗口。
D. **等 devops 先续跑完成性能 sweep**（cell-2..8），结束后再按用户对窗口/容量的
   裁定串行执行 A/B。

## 6. followups / open_issues
- [blocked] sweep cell-2..8 由 devops 续跑（ninja PATH 修复已知）。
- [需用户] A/B 的 recycle=0 可行性裁定：缩短窗口 vs 放弃 128G 目标 vs 换 trace。
- [需用户] 确认是否豁免"等 sweep 完全结束"（若豁免，容量阻断项 2 仍挡启动）。
- 本机 /data 已用 97G/197G，89G 属 leftover sweep ns；删除需用户批准（红线）。

## 7. 声明
本 epoch 对远程机零改动：未创建文件、未写 wrapper、未启引擎、未动 namespace、
未改引擎 .py/模型/负载/调度。没有任何运行产物被声称"已通过"。