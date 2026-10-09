# p2io-tester-e3 — P2-IO M2 重跑（bf16 修复后）：同步/单测完成，重跑被磁盘环境阻塞（/data 满）

## 1. status

**blocked** — 同步与单测已完成（双侧一致、74 tests OK）；重跑**未启动**：3090 /data 磁盘可用空间
9.3 GiB < extent 后端 min_free=10G，且本负载写入需求 ~19.9G（file 基线实测）。冻结参数下运行必然：
(a) 每次写路径全量驱逐缓存（pressure 永不可满足）→ 零缓存驻留 → restore 全 miss → 判据全部无法裁决；
(b) ~9.4G 累计写入后 pwrite ENOSPC → 写入失败 → 环境级联（与 e2 根因 1 级联链同型）→ 污染
"根因 2 是否正常负载复发"观察。已用真实后端代码模拟实证（见 evidence §3）。需先释放磁盘空间
（用户确认，见 followups 1）再重跑；3090 其余全部就绪（进程/GPU 已确认空闲）。

## 2. artifacts

**同步（完成，双侧 md5 逐字节一致）**：
| 文件 | 本机 md5 | 3090 部署树 md5 | 一致 |
|---|---|---|---|
| python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py | ffb56bff89da9fe94c299243836577d2 | 同左 | ✓ |
| test/registered/unit/mem_cache/test_extent_file_backend_unit.py | 5cce63b8ff887fe938eb19235601e0ff | 同左 | ✓ |

- 3090 覆盖前旧版本已备份：/root/p2io-m2sync-bak/{extent_file_backend.py, test_extent_file_backend_unit.py}
  （md5 7ab80c08… / 0788ae97…，即 get_stats 修复版，bf16 修复前）。
- 引擎核心 + 关联文件 13 个双侧 md5 全部一致（scheduler/cache_controller/schedule_batch/schedule_policy/
  unified_tree_core/unified_radix_cache/hiradix_cache/hybrid_cache_controller/extent_allocator/__init__/
  backend_factory/environ/server_args）——引擎核心零差异，修复面恰为 2 文件。
- 修复内容在位确认：extent_file_backend.py:75/:93 `value.contiguous().cpu().view(torch.uint8)`（bf16 fix）。

**单测（完成，3090）**：`PYTHONPATH=python:test /root/miniconda3/envs/sglang-patch/bin/python -m unittest
registered.unit.mem_cache.test_extent_file_backend_unit registered.unit.mem_cache.test_hicache_file_lru_unit`
→ `Ran 74 tests in 0.903s OK`（EXIT=0），含新增 7 例 TestExtentTensorPages（bf16 写→读 round-trip）。

**重跑（未启动，环境阻塞）**：/root/p2io-extent-run.sh 已审读（参数：L3_BACKEND=extent、STORAGE_DIR=/data/l3/p2io-extent、
max_size=20G、min_free=10G、K=8 96 请求、nohup 化自跑、io-after 快照步骤在位——上次缺失系引擎崩溃后
scheduler 进程已死所致，非脚本缺陷）。状态文件 EXTENT_STAGE_COMPLETE 为上一轮（e2 FAIL 轮）遗留，
本轮未动。

**环境实证模拟（本机，真实后端代码直驱）**：/tmp/p2io-m2-evict-sim.py + 输出（见 evidence §3）。

## 3. evidence（真实命令与输出）

**同步核对**：
- 本机：`md5sum extent_file_backend.py test_extent_file_backend_unit.py` → ffb56bff… / 5cce63b8…
- 3090 部署树：`md5sum …/extent_file_backend.py …/test_extent_file_backend_unit.py` → ffb56bff… / 5cce63b8…
- 备份：`md5sum /root/p2io-m2sync-bak/*` → 7ab80c080393b15ac8092cbe9de47322 / 0788ae972f532a0260626f0b140ea047
- 引擎核心 13 文件：双侧逐字节一致（md5 列表见本报告 §2，双侧输出逐字段相同）。

**单测（3090）**：
```
$ PYTHONPATH=python:test …/python -m unittest registered.unit.mem_cache.test_extent_file_backend_unit registered.unit.mem_cache.test_hicache_file_lru_unit
Ran 74 tests in 0.903s
OK
EXIT=0
```

**磁盘状态（3090，当前）**：
```
$ df -B1 /data
/dev/sdb  210779160576  191098810368  10000007168  96% /data
$ python3 -c "import os; st=os.statvfs('/data'); print(st.f_bavail*st.f_frsize/2**30, st.f_bfree*st.f_frsize/2**30)"
f_bavail*f_frsize = 9.3 GiB      # 引擎 statvfs 判据用 f_bavail
f_bfree*f_frsize  = 18.3 GiB     # 含 root 预留块
```
- min_free=10G（引擎日志实证）：`[18:48:32] ExtentFileBackend: file=/data/l3/p2io-extent/hicache.data… extent=67108864 B slots=1024 max_size=20000000000 min_free=10000000000`。
- **f_bavail=9.3G < 10G min_free：压力条件从启动即成立**。

**写入需求 ~19.9G（file 基线实证，同负载同引擎）**：
```
$ du -sb /data/l3/p2io-file → 19919192064  (348,535 个 .bin，启动时 existing=0 entries)
$ grep -c "refusing" /root/engine-p2io-file.log → 9   （仅 9 次拒绝 → 19.9G ≈ 真实写入需求，未被磁盘显著截断）
$ grep "refusing" … 首条: [18:13:27] … would fall below min_free=10000000000 B … refusing … avoid OOM/ENOSPC
```

**压力驱逐行为（本机模拟，真实 ExtentFileBackend 代码，monkeypatch statvfs）**：
```
Case A (min_free 压力 ON = 当前 3090 状态；max_size=0):
  batch  (ok, used_bytes, this-batch-survivors)
    (True, 393216, 4)
    (True, 393216, 4)      # used_bytes 恒 = 单批大小，先前写入被全量驱逐
    (True, 393216, 4)
    (True, 393216, 4)
  key from batch 1 still present: False      # 第 1 批 key 在第 2 批写入后已不存在
Case B (无压力，对照):
  (True, 393216, 4) (True, 786432, 4) (True, 1179648, 4) (True, 1572864, 4)
  key from batch 1 still present: True       # 正常驻留
```
代码路径（extent_file_backend.py:522-544 `_gc_evict`）：`pressure = used > max×ratio 或 f_bavail < min_free`；
min_free 压力无法靠驱逐解除（驱逐不释放文件块）→ while 循环驱逐全部 live slot 至空，再写当前批。
分配器（extent_allocator.py plan/commit）游标单调前进（仅在 64GiB 环绕后复用旧槽）→ 累计真实块占用 ≈
累计写入量 ~19.9G > 可用 9.3G → 约 9.4G 处 pwrite ENOSPC（root 可用上限 f_bfree≈18.3G，仍 < 19.9G）。

**3090 当前空闲态（可随时启动）**：进程仅系统 jupyter（PID 883）；nvidia-smi = 15 MiB / 24576 MiB；
/data/l3/p2io-extent/hicache.data… 仍为 64GiB 稀疏（du 4.0K）。

## 4. summary

- 修复同步与验证：**全部完成且双侧一致**。bf16 修复（2 文件）已上 3090 部署树，备份在位；引擎核心 13
  文件双侧逐字节一致；3090 单测门 74 tests OK（含 bf16 真实张量 7 用例）——组件级修复验证 GREEN。
- 重跑：**未启动，环境阻塞**。三份独立证据链闭合：
  1. 磁盘：f_bavail 9.3G < min_free 10G（引擎启动即恒压）；
  2. 写入需求：同负载 file 基线实测 19.9G（仅 9 次拒绝，未被磁盘截断），extent 游标单调推进 → 必 ENOSPC；
  3. 行为实证：真实后端代码模拟证明恒压下每次写入先全量驱逐缓存 → 驻留=1 批 → restore 全 miss。
  运行必然产生 NO DATA / 环境性 FAIL 并可能环境级联崩溃（e2 根因 1 级联链同型），且污染"根因 2 正常
  负载复发"观察——故不启动，如实上报。
- 结论：M2 重跑需先释放磁盘（至少 ~30G：10G min_free 底线 + ~19.9G 写入需求 + 余量；建议更多），
  其余一切就绪，3090 空闲可立即续跑。

## 5. followups

1. **释放磁盘（阻塞项，需用户确认）**：/data/l3/p2b0-4a（48.6G）/4b（54.0G）/4c（52.5G）为已完结
   4 系列实验的 L3 .bin 缓存（ledger 冻结决议在案；证据在 /root/evidence-* 与引擎日志，缓存可再生）。
   释放其一（建议 4b，54G）即可满足 ~30G 门槛；三目录共 156G。tester 无删除权限（Boundary 6），
   需 orchestrator/用户确认后由 devops 或授权方执行。释放后即可按冻结参数直接重跑（其余步骤全就绪）。
2. 重跑执行预案（解阻塞后立即执行）：launch /root/p2io-extent-run.sh（nohup 自跑）→ 前台阻塞等待
   （timeout 580 bash -c 'while pgrep -f p2io-extent-run.sh >/dev/null; do sleep 60; done'，超时续提交）
   → 判据逐项裁决（<1s / p50≤0.6s / open-read 数量级 / storage_hit 与 recompute 归因 / sha16 S4-L0-V1 t1、
   S6-L1-V1 t2 复检 / K=8 0 OOM 0 corruption 0 崩溃 + 根因 2 观察 / SIGTERM 清理）→ 补写 e3 判据节。
3. io-after 快照：脚本第 6 步写 /root/p2io-extent-io-after.txt 在位（e2 缺失系引擎崩溃致 scheduler 进程
   死亡）；重跑后确认存在，并以采样器 syscr 增量交叉验证。
4. 磁盘水位：重跑后 extent 文件将占 ~19.9G 实块；min_free 压力将在写入段后期复现——若判据要求全程
   无压力，建议解阻塞时释放 ≥30G 以上余量（如 4b+4a）。

## 6. open_issues

- **ENOSPC 前的压力驱逐已足以使判据失效**（驻留=1 批，restore 全 miss），与 ENOSPC 是否最终触发无关；
  即使 root 预留块（f_bfree=18.3G）使 ENOSPC 延后，实验结论仍不可用——故不可"先跑跑看"。
- extent 数据文件为 64GiB 稀疏预分配（非 fallocate），引擎 init 不占块；重跑将按写入量增长。
- 上一轮 EXTENT_STAGE_COMPLETE 标记为 e2 FAIL 轮遗留；解阻塞重跑后状态文件追加新标记，勿混淆。
- 本机分析副本策略同 e2（3090 原件不动，分析文件在 /tmp/p2io-e2/ 基础上续增）。

## 7. 判据节（追加，2026-08-31 21:1x 解阻塞重跑后裁决）

**重跑执行摘要**：/root/p2io-extent-run.sh 于 20:57:47 启动（detached，setsid nohup），20:59:39 healthy，
driver 20:59:39→21:08:50 rc=0（elapsed 549.8s），21:09:12 引擎 SIGTERM，证据
/root/evidence-p2io-extent-01/run-20260831-205940/。96 请求 **0 失败** / 7 downgraded（file 基线 0/1）。
前台阻塞等待（anchored pgrep `^bash /root/p2io-extent-run\.sh`，避开自匹配）一次返回 rc=0。

### 7.1 重跑结果表（extent run-20260831-205940）

| 项目 | 值 |
|---|---|
| 请求 | 96：成功 96 / 失败 0 / downgraded 7 |
| driver elapsed | 549.8s（file 基线 983s，1.79×） |
| 引擎崩溃 | 0（"Scheduler hit an exception"=0；driver rc=0） |
| backup_thread 异常 | 0（首跑为 1 次 bf16 TypeError） |
| 数据文件 | /data/l3/p2io-extent/hicache.data…=64GiB，du **60G 实块**（首跑 4.0K 稀疏）→ 写入真实发生 |
| 写侧计量 | backuped_tokens_total=1,541,809；write_bytes +93,079,855,104（93G）；syscw +28,152（≈3.3MB/次聚合写）；后端 0 拒绝 0 错误 |
| 读侧计量 | **prefetch_io_finished=0、restore_served=0、storage_hit=0**；read_bytes Δ≈0.7MB；syscr Δ=+3,666（91,210→94,876） |
| [P2A] 归因 | prefetch_issued=366 / revoke=366（全部，14ms 内）；restore_state 369 RESTORING + 314 WAIT_CAPACITY + 368 NONE；restore_disposition 375 RECOMPUTE + 3 WAIT；restore_recompute 368（miss 366 + timeout 2）；restore_retry 312（capacity 302 + frontier 10）；promotion 86/86；DEVICE_QUOTA 278 |
| host/device 命中 | device_hit=529,578 + host_hit=393,153（=922,731 tokens，file 基线 548,482） |
| dropped tokens | 2,049（file 基线 93,720，45× 低）；"KV subtree dropped without backup" 仅 1 次（首跑 225） |
| restore turns（24） | ttft p50=36.5s / max=65.6s（file 66.4s / 139.2s）；warm 19（device/host）/ 整链重算 5 / storage 命中 0 |
| OOM | dmesg 0（grep oom/killed process 无匹配） |
| 采样器 | /root/p2io-extent-samples.jsonl 240,750 行，PID 170227（scheduler），端点与 io-before/after 一致 |

### 7.2 file vs extent 对照表

| 指标 | file 基线 | extent（本轮） | 对照 |
|---|---|---|---|
| 请求成败 | 96：0 失败 / 1 降级 | 96：0 失败 / 7 降级 | 均 0 失败；降级 7 vs 1（观察项） |
| elapsed | 983s | 549.8s | 1.79× 快 |
| storage_hit tokens | 648,718 | 0 | 语义不同：file 靠 storage 服务；extent storage 从未被读（0 次咨询） |
| device+host 命中 | 363,338+185,144=548,482 | 529,578+393,153=922,731 | RAM 命中 +68% |
| restore_recompute | 92（70 miss+22 timeout） | 368（366 miss+2 timeout） | 探针级计数更多；请求级 5 次整链重算 |
| dropped tokens | 93,720+48 | 2,049+1 | −45×（host 压力大幅下降） |
| scheduler syscr | 1,501,305（累计） | Δ+3,666 | ~400× 下降 |
| restore turn ttft p50 | 66.4s | 36.5s | 1.8× 快（warm 命中，prefill 主导，非 storage IO） |
| 引擎崩溃 / OOM | 无 | 无 | 均通过 |

### 7.3 判据逐项 verdict

1. **写入必须发生（数据文件非稀疏、io_finished>0、restore_served>0）**：**部分通过**。非稀疏 ✓（4K→60G
   实块）；写侧全链绿色 ✓（backuped 1,541,809 tokens、write_bytes 93G、syscw 28,152 次聚合写、后端 0 拒绝
   0 异常——bf16 修复在集成级验证成功）；**io_finished=0 / restore_served=0 ✗**——二者是读侧计数，本轮
   0 次存储读，读侧从未发生。
2. **核心判据（restore 服务时间 <1s、纯 IO 窗口 p50≤0.6s）**：**NO DATA（第二次，原因与首跑截然不同）**。
   全程 0 次 storage read（io_finished=0、restore_served=0、storage_hit=0、read_bytes Δ≈0.7MB）→ 无任何
   extent restore 服务时间样本。系统级正向结果：0 失败、elapsed 1.79× 快、restore turn ttft p50 36.5s
   （warm device/host 命中 + prefill 主导）——但这不是 storage IO 成绩。
3. **open-read 数量级下降（vs file 1,501,305 syscr）**：**通过（有保留）**。scheduler syscr Δ=+3,666 →
   ~400× 下降；extent 写侧 open=1（单持久 fd），syscw +28,152 / 93G = 3.3MB per syscall（聚合写生效）。
   保留：本轮 0 次 extent 读，读侧 syscall 形状与"≤32 open/state"设计目标仍无数据（读从未发生）。
4. **storage_hit / recompute 归因（应明显优于 file 648,718 / 92）**：**名义指标未优于，机制已解释**。
   storage_hit 0 vs 648,718——storage 从未被咨询（0 次读尝试），非"命中率 0%"；device+host 命中 922,731
   vs 548,482（RAM 更暖）。restore_recompute 368 vs 92 为探针级计数（~3.8/请求，与 prefetch 配对），
   请求级仅 5 次整链重算（65s，状态已离 RAM 且被 extent 18G LRU 窗口驱逐）；backuped 状态驻留窗口
   ≈107s（18G @170MB/s），turn 间隔分钟级 → 大多数被写入循环（60G ≫ 18G）驱逐后才到 restore。
5. **sha16 复检**：S6-L1-V1 t2（agent-6 t2）= **b45b370f8ff06f41，与 file 基线一致 ✓**（首跑 15c267… 未复现）。
   S4-L0-V1 t1（agent-4 t1）= 947b38ee3347e85b，第三值（file f14fd904…/首跑 a73fab60…）；payload 三跑
   逐字节一致（aa744917…，temperature=0）→ 三跑三值 = 生成级非确定性（batch 组合），该路径 0 存储读，
   无 corruption 实证。
6. **K=8 短回归**：**通过**。0 OOM（dmesg 无匹配）；0 corruption 实证；0 崩溃（driver rc=0、引擎无
   AssertionError）；**根因 2（unified_tree_core.py:1948）未复发**——无 assert 崩溃、无 kill_process_tree
   异常路径、host 压力大幅下降（dropped 2,049 vs 首跑 225 次 drop 风暴）。观察项：downgraded 7 vs file 1
   （如实记录，非失败）。
7. **引擎 SIGTERM 清理**：**通过**。进程树清零（仅系统 jupyter 常驻 PID 883）；nvidia-smi = 15 MiB/24576 MiB；
   engine log kill_process_tree（21:08:58）后无残留。

### 7.4 机制解释与开放项

- **为什么 0 次存储读**：extent 聚合写（3.3MB/次 pwritev vs file 每 key 3 syscall）→ backup 快速排空 →
  host/device 驻留健康（dropped 2,049 vs 93,720）→ 19/24 restore turn 直接 RAM 命中，storage 读从未被
  需要；离 RAM 的状态（5 次整链重算）其 backup 已在 18G LRU 窗口（≈107s）内被 60G 写入循环驱逐。
  归因链：写快 → 更暖的 RAM → storage 读路径零触发。这不是读路径损坏的证据（74 单测含 v1/v2 读回
  round-trip；引擎读侧 key 构造与 file 共用，file 读成功），而是**读路径集成级仍未被真实负载触达**。
- **M2 核心判据的达成条件**：需要"强制离 RAM"场景（降低 host 容量或提高 K/并发）使状态真正依赖
  L3 读回，才能测到 storage restore 服务时间。本轮数据表明 extent 写路径达标（93G 零错误），读路径
  待专项场景验证。
- **LRU 窗口 vs turn 节奏**：max_size=20G×0.9=18G 驻留 vs 93G 写入需求 → 备份状态平均 ~107s 后驱逐，
  而 turn 间隔分钟级。若 M2 目标是 storage-assisted restore，需调大 max_size 或降低 eviction_ratio
  （或依赖 allocator 64GiB 环绕复用）——参数建议交 orchestrator/architect 决策。
- **遗留**：读侧"≤32 open/state"、O_DIRECT 标定、restore 服务时间样本——全部依赖一次真实读触发场景。

## 8. M3 读路径强制覆盖测试 + 定向 read-back 用例（追加，2026-08-31 22:1x 裁决）

### 8.1 M3 运行摘要（host 20G→5G，K=8 96 请求，证据 /root/evidence-p2io-extent-m3/run-20260831-212536/）

- 配置生效确认：server_args `hicache_size=5`（host_total_tokens 42,784 vs M2 的 98,305 ≈ 5G vs 12.5G）；
  dropped tokens **12,294**（vs M2 2,049，6×，host 压力如预期制造）；backuped 1,709,354；write_bytes +114G。
- 96 请求 0 失败 / **26 downgraded**（M2 7 / file 1）；driver elapsed 591.9s。
- **读侧依旧全零**：prefetch_issued=440 / revoke=440（全部）、prefetch_io_finished=0、restore_served=0、
  storage_hit=0；syscr Δ+3,188；read_bytes Δ≈1MB。restore turns 24：20 整链重算 + 4 部分命中。
- **DIRECT_IO：实证未生效**。env 开启后引擎仅记录保留警告（"SGLANG_HICACHE_EXTENT_BACKEND_DIRECT_IO is
  reserved for the O_DIRECT calibration tier; this slice uses buffered IO"）；fd flags 实测
  **02100002 = O_RDWR|O_LARGEFILE|O_CLOEXEC，无 O_DIRECT 位**（before/after 一致）。结论：本 slice 无
  O_DIRECT 实现（代码仅保留入口），页面 31KB 非 4K 对齐问题因此未触发 EINVAL——**O_DIRECT 为 coder
  跟进项**（整 extent 对齐方案），本轮如实记录，未硬绕过。
- 判据 1-7 与 M2 同口径：写入 ✓（非稀疏、1.71M tokens backuped、0 写失败）；核心 <1s / p50≤0.6s NO DATA
  （读侧零触发）；syscr ~470× 下降；storage_hit/recompute 名义更差（机制解释同 M2 + host 压力加剧）；
  sha16：S6-L1-V1 t2=15c267c4（与 M2-FAIL 轮同值，file 轮 b45b370f 未复现——四跑三值，非确定性维持）、
  S4-L0-V1 t1=947b38ee（M2 轮同值）；0 OOM / 0 崩溃 / 根因 2 未复发；清理 ✓（GPU 15 MiB）。

### 8.2 定向 read-back 用例（回退判据：restore_served 仍=0 → 不升 K，构造定向单用例）

- **v1（4 链）**：a1..d1(S1-S4)+a2 → a2 ttft=0.445s（**warm**）——A 全程未离 RAM（device 65,536 容 3 链、
  host 42,784 容 2 链），L3 从未被需要；prefetch 4 次全 revoked:miss。
- **v2（5 链）**：a1..e1(S1-S5)+a2 → a2 ttft=0.533s（warm）——A 仍在 host（A+B=36,216<42,784）。
- **v3（7 链）**：a1..g1(S1-S7)+a2 → a2 ttft=5.501s（**完全冷重算**）——A 彻底离 RAM；写 6.3G（<18G 水位
  零驱逐，A 的 L3 副本应在），但 a2 的整链查询（prefetch_length=20910）仍 storage_hit=0 → 8/8 prefetch
  revoked:miss、0 io_finished、0 restore_served。
- 结论：**不是 workload 未稳定制造 L3 revisit——是 backend 读路径确定性问题**（见 8.3）。

### 8.3 根因定位：extent 后端 v1 写 / v2 查 key scoping 不一致（决定性证据链）

1. **插桩实证（3090 部署副本临时诊断日志，已还原）**：一次 v3 定向运行中 **batch_set 818 次、
   batch_exists(v1) 0 次**——引擎命中查询从未走 v1；prefetch_thread 每 op 均 processed
   （terminated=False, tokens_len=20910, query done storage_hit_count=0）。
2. **代码定位**：引擎写 = backup_thread→`_generic_page_set`→**batch_set(v1, 裸 key)**；引擎查询 =
   HybridCacheController._storage_hit_query（hybrid_cache_controller.py:596）——本模型 prefetch 必带
   sidecar pool_transfers（aux_xfers）→ 走 **batch_exists_v2**；extent 的 batch_exists_v2
   （extent_file_backend.py:333）查 `_storage_key(key)` = **key + config_suffix**
   （"_qwen3.5-9b-gptq_0_1"）——**v2 查带后缀 key，v1 写入裸 key → 永不匹配**。
3. **file 基线为何命中**：HiCacheFile 的 v1 set/exists/get 与 v2 全部应用同一后缀（双侧一致）→ 一致命中
   648,718 tokens。extent 的 v1 裸 key 是唯一不一致面。
4. **本地 RED 复现（真实代码直驱）**：config_suffix="_qwen3.5-9b-gptq_0_1" 时
   batch_set(v1)→batch_exists(v1)=1（命中）→batch_exists_v2=**0（miss）**；
   任意非空后缀（含最小 "__0_1"）均复现 → **单测缺口**：现有 74 例只做 v1↔v1、v2↔v2 同路径 round-trip，
   从不跨 v1写→v2查，故全绿但真实引擎零命中。
5. 影响面：M2（366 prefetch）/M3（440）/定向（8）全部 revoked:miss 的同一机制；restore_recompute、
   storage_hit=0、5 次整链重算等全部由此解释。写入侧、bf16 修复、引擎核心均无问题。

### 8.4 判据逐项 verdict（M3 完整口径）

1. restore_served > 0：**FAIL（0）**——非 workload，backend v1/v2 key scoping bug（8.3）。
2. 640MB 等价 restore p50≤0.8s：**NO DATA**（读侧从未触发）。
3. 聚合读取 ≤32 syscall/state：**NO DATA**（0 次读）；写侧聚合已验证（3.3MB/syscall）。
4. O_DIRECT：**未生效**（保留 tier 无实现；fd flags 实证无 O_DIRECT 位；EINVAL 未触发因为未以 O_DIRECT
   打开——对齐问题为 coder 跟进项，非本轮可验证项）。
5. correctness / sidecar：sha16 四跑三值维持非确定性结论（payload 逐字节一致、0 存储读路径）；mamba
   sidecar 池随 KV 链一致行为（v2 查询同样受后缀影响）；无 corruption 实证。
6. backup_failed / drop_declined / OOM / zero-progress：**通过**（0 写失败、dropped 仅计数非失败、dmesg
   0 OOM、无 zero-progress 停滞——restore 全走 recompute 路径但请求全部完成）。
7. wall time 不要求（5G 人为压力）：elapsed 591.9s 如实记录。

### 8.5 followups（本次核心交付）

1. **extent 后端 v1/v2 key scoping 修复（P0，coder）**：方向 = 使 v1 写读（set/get/exists/batch_*）与 v2
   查询共用同一 key 变换（对齐 HiCacheFile：v1 也应用 _storage_key），或 v2 KV 路径改裸 key（需评估
   mamba _component_key 隔离语义）。补单测：非空 config_suffix 下 v1写→v2查 跨路径 round-trip（本次 RED
   复现脚本 /tmp/p2io-v1v2-key-repro.py 可直接转单测）。
2. 修复后重跑 M2/M3 判据链（届时才首次有真实 storage restore 服务时间样本）。
3. O_DIRECT tier（coder，独立）：整 extent 对齐实现 + EINVAL 验证。
4. 3090 部署树已还原（插桩全撤，74 tests OK 复核）；launch 脚本保留 HICACHE_SIZE 支持（实验驱动）。

## 9. P0 修复后 M3 重跑判据节（追加，2026-08-31 22:3x 裁决）——key scoping 修复首次真实 restore 服务时间样本

### 9.1 同步与门禁（步骤 1-2）

- 同步 2 文件 → 3090 部署树：`extent_file_backend.py`（ffb56bff→**1977607d**）+
  `test_extent_file_backend_unit.py`（5cce63b8→**3f7ed883**），md5 双侧一致；旧文件备份
  `*.bak-v1v2fix`。
- 引擎核心一致性复核：cache_controller **2e4e479b** / hybrid_cache_controller **3bb6ae94** /
  hicache_storage **7081bed4** 双侧 md5 全同——引擎核心零改动；本地独立复验：复现脚本
  `/tmp/p2io-v1v2-key-repro.py` 反转 `MISMATCH: False`（含最小后缀 `__0_1` 用例）。
- 3090 单测：`Ran 80 tests in 0.900s OK`（extent 46 = 原 40+新 6，file LRU 34），EXIT=0。
- 代码级确认：v1 六入口（get/set/exists/batch_get/batch_set/batch_exists）全部 `_storage_key`；
  v2 三入口不变；IO 核心 `_read_pages`/`_write_pages` 不做变换（避免双重后缀）——对称性闭环。

### 9.2 M3 重跑（host 5G，K=8 96 请求，run-20260831-222152，elapsed 801.9s）

- 96 请求 0 失败，**downgraded=5**（修复前 M3=26）；driver rc=0，无 zero-progress。
- **restore_served 转正：93 次**（prefetch_io_finished=93 = restore_ready=93，与
  prefetch_issued 486 - revoke 393 精确守恒）；共恢复 **841,301 tokens ≈ 25.5GB 等价**
  （31KB/page），单次 granted min=363 / p50=6,573(≈199MB) / p90=22,528(≈682MB) / max=29,858(≈905MB)。
- storage 查询：486 次 prefetch → 93 完成 IO（19.1%）+ 393 revoke（377 miss + 7 alloc_failed +
  9 insufficient）；非零 storage_hit 16 次（最高 29,858）——v1写→v2查 已命中（修复生效证据）。
- 物理读：read_bytes Δ+10.05GB，**磁盘读突发 2,391 次中 2,384 次落在 restore 窗口内**；
  写 Δ+122.3GB；/data 48G 余量。

### 9.3 判据逐项 verdict

1. **restore_served > 0 且数量足够成分布：PASS**——93 个样本，tokens 363–29,858 连续分布
   （p50 6.5k / p90 22.5k）。**注意**：多为部分链授予（avg 9,050/请求 20,910），restore 轮
   ttft p50=44.5s ≈ 重算级（见 9.4 解释）。
2. **640MB 等价 restore p50 ≤ 0.8s：FAIL**——L3 读服务时间（issued→io_finished）n=93：
   p50=**1.579s** / p75=2.445 / p90=8.601 / max=14.198 / min=0.342 / mean=2.835。按实测
   7.9ms/MB 折算 640MB ≈ 5s。对比 file 基线（640MB 纯 IO 窗口 p50=25.4s）**每 MB 快 3–5×**，
   但绝对目标未达；瓶颈=QEMU 虚拟盘 IO + prefetch 队列串行 + 循环文件覆盖导致部分链。
3. **聚合读取 ≤32 syscall/state：PASS（设计级）**——`_read_pages` 每 64MB extent 一次 pread，
   640MB 全链 ≈ 11 次（10–20 目标带内）。测量级：2ms 采样聚合窗口 raw p50=65/restore 窗口
   （含 IPC/HTTP 等引擎背景读，窗口外基线 6.4/s；**per-tid io 计数器为空无法精确剥离**，
   已如实记录为测量限制）。
4. **O_DIRECT：未生效（如实记录）**——fd flags 02100002 无 O_DIRECT 位，保留档警告照常；
   buffered IO，挂账 coder 跟进，未硬绕过。
5. **correctness + sidecar：PASS**——确定性会话（S1/S2/S3/S8）grow=restore sha16 **逐字节相等**
   （如 a1-t5=b140e9da=a1-t1），跨 run 48/73 tag 全同；S4-S7 输出体差异为**前置非确定性**
   （修复前零存储读的 M3 轮同 tag 同样跨 run 换值——非存储路径引起）；grow/restore 请求
   payload md5 双侧相同；mamba sidecar 池随链一致。无存储引入损坏证据。
6. **backup_failed / drop_declined / OOM / zero-progress = 0：PASS**（0/0/0/0）；另观测
   forced_drop_to_miss=2、hollow_evict=8（内部驱逐事件，2048 tokens/次，非计数路径，
   与 dropped 指标 0 不矛盾）。
7. **L3 read service vs request WAIT 区分（新口径已提供）**：backend 侧 L3 读服务
   p50=1.58s（9.3.2）；请求端 WAIT：ttft p50=50.2s（受 8-agent 引擎排队主导，
   sched→start 仅 p50=59ms）；restore 轮 ttft p50=44.5s——恢复未转化为请求加速，
   因授予为部分链 + 5G host 驱逐压力（recompute 400 事件）。
8. wall time 不要求：elapsed 801.9s 如实记录（修复前 591.9s，工作负载排队所致）。

### 9.4 行为解读（修复生效但收益受限）

- 修复确认生效：93 次真实 L3 读 + 10GB 物理读 + 部分授予 16 次命中，v1/v2 key 闭环达成。
- 但 24 个 restore 轮仍基本重算：根因 = **循环文件覆盖**——122GB 写入灌入 64GiB 循环文件，
  链在 replay 轮到来前大多被覆盖 → 授予多为部分链（avg 9k/20.9k tokens）→ 引擎判定不满足
  整链恢复。restore 服务时间样本（p50=1.58s）为**部分链**样本，非整链 640MB 样本；
  整链 640MB 样本需规避覆盖（扩容文件 / 分层 / 定向单链用例）。
- 下一步建议（followup）：定向 read-back v3 单链用例（写后立读、无覆盖干扰）获取
  整链 640MB 级服务时间真实样本；或加大 extent 文件/多文件轮换。

### 9.5 清理确认（步骤 6）

- 引擎 SIGTERM 后：进程树清零（sglang::/launch_server/p2io 均无），GPU 15 MiB，dmesg
  OOM=0；sampler 已止（350k 样本留存 /root/p2io-extent-m3-samples.jsonl）；证据
  run-20260831-222152 完整（8 agent json + join.log + turns/ + mid-run-metrics）。
- 3090 部署树保持修复态（1977607d / 3f7ed883），备份 .bak-v1v2fix 在位。

## 10. A' 定向 640MB 整链 cold read + 裸带宽标定 + 口径厘清 + p90 拆解（追加，2026-08-31 23:2x 裁决）

### 10.1 同 VM、同路径裸顺序带宽对照（A' 第 3 项，先做，无引擎干扰）

- 目标文件 = extent 后端同一文件 /data/l3/p2io-extent/hicache.data_qwen3.5-9b-gptq_0_1
  （64GiB 非稀疏，QEMU 虚拟盘 ROTA=0，/data 余 48G）。
- **drop_caches 不可用**（/proc/sys/vm/drop_caches 挂只读）→ cold 方法改用
  `os.posix_fadvise(POSIX_FADV_DONTNEED)` 逐次驱逐文件页缓存（已验证有效），如实记录。
- 结果（各 ×3）：
  - cold buffered（fadvise 后 python 读）：**1MB/4MB/16MB 块 ≈ 1.43–1.45 GB/s**；
    单次 640MB 大读 0.88–0.94 GB/s（大缓冲分配开销）。
  - O_DIRECT（dd iflag=direct）：首轮冷 1.0–1.1 GB/s，稳态 **2.6–3.6 GB/s**。
  - warm buffered（dd，页缓存命中）：2.9–4.8 GB/s（非 cold 对照）。
- **结论：专家假设的 ~127MB/s 不成立——本 VM 顺序读冷上限 ~1.43 GB/s（buffered）/ ~3.2 GB/s（O_DIRECT）；640MB 物理下限 ≈ 0.45s（buffered）/ 0.20s（O_DIRECT）→ 0.6–0.8s 目标设备可达。**

### 10.2 定向 640MB 整链 cold read-back（A' 第 1-2 项，engine 5G host）

- 构造（无 ring overwrite）：9 链分 3 批写（S1,S2,S3 / S4,S5,S6 / S7,S8,S1V2），累计
  ~5.6GB 写入 64GiB arena——测试链（S1/S2/S3）始终未被循环覆盖；5G host（42,784 tok）
  + device（65,536 tok）驱逐级联驱动 L3 落盘。cold = 每次读前 sync + fadvise(DONTNEED)。
- 序列：W1(A,B,C) → [fadvise] R1(A) → W2(D,E,F) → [fadvise] R2(B) → W3(G,H,I) →
  [fadvise] R3(C)。全部 12 请求 200，0 失败。
- **样本（两次真实 cold 整链 restore，read_bytes 实证冷盘）**：
  - **R3(C)：16,384/20,910 tokens（508MB-equiv，磁盘读 +750MB）：issued 23:13:52.77 →
    io_finished 23:13:59.42 = 6.66s**（restore_ready 紧随，prefill 用 16,384 缓存 tokens，
    ttft 8.89s）。
  - **重试（全链 20,864 tokens ≈ 647MB，磁盘读 +~650MB）：issued 23:14:09.06 →
    io_finished 23:14:17.37 = 8.31s**——首个整链 640MB 级 cold restore 服务时间样本。
  - 授予 16,384 = 128 batch × 128 页 精确数——R3 查询与备份在途竞态（备份按
    128 页/batch 原子可见，查询只看到已落盘 batch；restore_retry=1 于 ~10s 后拿到全链）。
- **R1(A)/R2(B) miss 原因（非 backend bug）**：A+B+C=62,733 < device 65,536 →
  W1 阶段三链全部驻留 device、零驱逐 → L3 落盘只在 W2/W3 写入的驱逐级联后才发生
  （A 的 L3 副本 ~23:13:16-22 落盘，晚于 R1 查询 23:13:10；B 类似晚于 R2）——
  定向设计的 device 容量疏忽（测试缺陷，如实记录），但不影响两个有效样本。

### 10.3 计数口径厘清（附加 1：4.3MB/read 之谜，探针实证）

- **strace 不可用**（3 个标准路径均无）→ 授权插桩路线（M3DBG 先例）：临时给 3090
  部署树 `_read_pages` 加 EXTENT_READ_PROBE（每次 pread：ts_ms/extent/req_len/dur_ms），
  测后还原 + md5 复核（1977607d 复原，0 残留）。
- 实测 312 次 pread（2 次 restore 共 1.15GB）：**4MB×271、1–2MB×34、0MB×2、49–53MB×3**。
  粒度来源 = **引擎 restore 循环按 128 页/batch 调 batch_get(_v2)**（STORAGE_BATCH_SIZE=128，
  128×31KB≈4MB）——不是 Linux 拆分大读，是引擎批大小；backend 的 extent 聚合仅在单批内
  生效（批内跨 extent 时一次 pread 覆盖跨度，实测 53MB@30ms）。
- **三层口径**：engine read-op = 128 页/batch（4MB）；syscall = 每批每 extent 一次 pread
  （≈批内 extent 数，全链 ~11–16 次/640MB）；physical byte = read_bytes 冷读实证
  （R3 +750MB / 重试 +~650MB，总量 1.4GB 吻合）。
- **M3 的 4.3MB/burst 解释**：10GB/2,384 磁盘突发 ≈ 4MB/batch 的 2ms 采样切片——采样器
  恰巧切出了真实批粒度，此前误判为采样伪影。≤32 syscall/state 判据按此口径重审：
  **单 state 全链 640MB = ~11–16 次 pread（syscall 级达标 ≤32）**，但服务时间被引擎批
  循环开销主导（见 10.4）——口径已厘清，判据按"引擎批粒度 4MB + 后端 syscall 粒度
  extent"两层如实陈述。

### 10.4 p90=8.6s 拆解（附加 2：四段分解，探针 + [P2A] 事件对齐）

- 全链 restore（8.31s）四段：
  - **storage queue wait**：issued→首个 pread = **48ms（0.6%）**——队列本身不阻塞。
  - **submit+device**：pread 实际耗时合计 **516ms（6%）**，单次 4MB pread 2–4ms
    （≈1.3–1.8 GB/s——设备侧带宽达标，与 10.1 标定一致）。
  - **引擎侧 per-batch 开销**：read span 8,230ms − 设备 516ms ≈ **7.7s（93%）**，
    平均 ~44ms/批（175 批）——批间非 IO 工作（host 页分配、GIL/调度竞争、批循环）。
  - **finalize**：末 pread→io_finished ≈ 0ms（fin 后 4ms 即 restore_ready）。
- **结论（专家怀疑证实并量化）**：8.6s 不是磁盘慢（设备 1.3–1.8 GB/s），是 storage
  worker 每 128 页批次的 ~44ms 引擎侧串行开销 × 批数（640MB ≈ 160 批 ≈ 7.2s）。
  0.8s 目标物理可达（10.1），当前 restore 路径有效吞吐仅 ~78MB/s（设备上限 1.43 GB/s
  的 5.4%）——**修复方向（coder followup）：restore 批大小 128→整链（或 512–1024 页），
  预期 640MB ≈ 0.5–0.8s**；写入侧备份同粒度（在途竞态证据 10.2），一并跟进。

### 10.5 判据逐项 verdict

1. 定向 640MB 整链 cold read：**PASS（两个样本：6.66s/508MB 部分 + 8.31s/647MB 全链）**，
   无 ring overwrite、cold 实证（read_bytes +1.4GB）。
2. 裸带宽对照：**1.43 GB/s（cold buffered）/ 2.6–3.6 GB/s（O_DIRECT）**——127MB/s 假设
   否定；0.6–0.8s 目标设备可达。
3. 口径厘清：**完成**——引擎批粒度 4MB（128 页）× 批数；syscall 粒度 per-extent pread；
   ≤32 syscall/state 按 syscall 口径成立（全链 ~11–16 次），但受 10.4 批循环开销制约。
4. p90 拆解：**完成**——queue wait 48ms / 设备 516ms / **引擎侧批开销 7.7s（93%）**。
5. O_DIRECT 状态：不变（buffered，预留档无实现，fd flags 02100002 复核）。
6. 清理：探针还原（md5 1977607d 双侧复核）、引擎进程树清零、GPU 15 MiB。
7. A' 不关闭 P2-IO：物理上限已标定，backend 修复空间明确（批大小），判据链待修复后重测。

## 11. M4 v1 zero-copy 验证 + IOV_MAX 根因 + 分离诊断（追加，2026-09-01 00:2x 裁决）

### 11.1 同步与门禁（步骤 1-2）

- 4 文件同步 → 3090：extent_file_backend.py **3c770f1f** / hicache_storage.py **22348ed0** /
  cache_controller.py **0d63a8e8** / test_extent_file_backend_unit.py **35b21b2a**，md5 双侧一致；
  旧版 .bak-m4 备份。
- 引擎核心一致性复核：hybrid_cache_controller 3bb6ae94 / unified_radix_cache b436952e /
  unified_tree_core 8e15bd81 / hiradix_cache a92be0d3 / backend_factory 1fddea7b /
  storage_attachment d73b7a1f / mmap_allocator e789081d / mamba 4ddd183b —— **8 文件双侧全同**。
- 3090 单测：`Ran 100 tests in 1.085s OK`（extent 66 + file LRU 34），EXIT=0。
- 接线确认：cache_controller.py:668-669 名单含 "extent" → page_get/set_func =
  _page_get/_set_zero_copy（v1 zero-copy 生效路径）。

### 11.2 M4 运行（v1 名单接线，host 5G，K=8 96 请求，run-20260901-002442？——证据
/root/evidence-p2io-extent-m4/run-20260831-234916，elapsed 588.4s，downgraded 26）

- **主判据 FAIL（NO DATA）**：授予全为小部分链（832–7,330 tokens，无 ≥10,000）；
  restore_served=15（vs M3 的 93）。服务时间样本 0.32–1.58s（小授予）。
- **根因（决定性证据链）**：V1_WRITE_PROBE 仅 386 次成功调用（≈395k 页 ≈12.2GB），
  **`Write page to storage: 1024 pages failed` ×1,495 + `pwrite failed ... [Errno 22]
  Invalid argument` ×1,495**——v1 写路径每批 1024 页 × 2 块（k/v）= **2,048 iovecs 超
  Linux IOV_MAX(1024) → pwritev EINVAL**。3090 实测边界：1,024 iovecs OK / 1,025 EINVAL /
  2,048 EINVAL（/tmp/iovmax-test.bin 实验，逐字输出在报告 11.3 下）。
- 影响量化：备份需求两侧持平（hicache_backup kv：M4 3,392,535 ≈ M3 3,299,157），但
  成功量 backuped_tokens_total = **288,738 vs M3 1,896,932（-85%）** → 存储只有 21% KV
  → batch_exists_v2 命中稀薄 → 授予全部分链。读侧 v1 本身工作正常：V1_READ_PROBE
  39 次调用 requested==physical（放大 1.0×）、preads=3–4/批、两探针间隔 19ms
  （1024 页批）——**zero-copy 消除了 per-page 引擎侧成本**。
- 事件守恒：339 issued = 324 revoke + 15 io_finished ✓；restore_ready=15。

### 11.3 分离诊断（步骤 5：名单临时还原 → generic 1024，run-20260901-000728，elapsed 731.9s）

- 备份恢复满载：**0 pwrite 失败**（generic 1 iovec/页 ≤ IOV_MAX）、backuped 1,812,162
  （≈M3）；授予 **89 次**（prefetched 502,791 tokens），其中**整链（≥20,000）16 次**。
- **44ms 归因（关键结论）**：整链服务时间 2.39–13.97s（12/16 在 2.4–7.0s，p50≈4.5s）；
  A' generic-128 整链 8.31s → generic-1024 ~4.5s（仅 ~1.8× 改善）。探针（1,621 合并区间）：
  区间 15–32MB、单次 pread 5.5–17ms（设备 1.4GB/s 达标）、批内区间 gap 0.1–0.6ms →
  **成本与页数成正比（~0.2–0.34ms/页，引擎侧 per-page 处理），非固定每批 44ms**；
  e5 的 1024 批只摊薄固定部分。v1 zero-copy 每批 19ms（0.019ms/页）→ 整链估算
  ~0.9s（21 批 + 设备 0.46s）→ **0.8s 目标在 v1 下可达，但被 11.2 写 bug 阻断验证**。
- 服务/WAIT 分离：M4D L3 服务 p50=1.55s（89 授予，混合大小）；请求端 ttft restore
  p50=46.1s（8-agent GPU 串行主导，sched→start 无变化）——同 M3 口径。
- sha16：M4D 确定性会话（S1/S2/S3/S8）13/16 与源轮逐字节一致，False 均为已知非确定性
  会话（S4–S7，M3 已证前置）或 a1-t12 跨 run 稳定值（c71201d3 与 M3 同值，非损坏）。
  M4 同签名（13/24）。backup_failed=0（M4D）/ OOM=0 / zero-progress=0（96/96）。
- 事件守恒：505 = 416 + 89 ✓。

### 11.4 判据逐项 verdict（M4 口径）

1. 640MB 整链 cold restore p50 ≤ 0.8s：**FAIL（NO DATA）**——v1 写 IOV_MAX bug 使整链
   授予为零；修复后需重测（估算 ~0.9s，接近目标）。
2. L3 service vs WAIT：分离保留——M4 15 次小授予 0.32–1.58s；WAIT ttft p50=40–46s。
3. 引擎侧开销：v1 读侧每 1024 页批 ~19ms + 设备 ~1.4GB/s → per-page 成本已消除
   （对比 generic 的 0.2–0.34ms/页）；整链样本被写 bug 阻断，无法给出终值。
4. 事件守恒：✓（339=324+15；M4D 505=416+89）；restore_served 数量 M4=15 不足
   （bug 所致），M4D=89 充足。
5. ≤32 syscall/state：**未达（实测）**——v1 每批 preads=3–4（合并区间数），整链 21 批
   ≈ 63–84 次 preadv（推断，基于探针每批值）；generic-1024 整链 ~42 次。单次 preadv
   传 15–32MB。判据目标需每批 1 区间（连续落盘）或更大合并。
6. 读放大 physical/requested：**PASS**——v1 探针 requested==physical（1.0×）；
   generic 合并区间 exact-range（e4 生效，区间 15–32MB）。
7. correctness：**PASS**——确定性会话字节一致（M4D 13/16，M4 13/24，False 全部为
   已知非确定性模式，无新损坏签名）。
8. backup_failed：M4 **FAIL**（1,495 次 EINVAL 备份失败=本次根因）；M4D 0 ✓。
   drop_declined=0 / OOM=0 / zero-progress=0（两轮均 96/96 完成）。
9. 清理：两轮 SIGTERM 后进程树清零、GPU 15 MiB（M4D wrapper 瞬时 3 进程/327MiB 为
   宽限期内将死进程，事后复核清零）；探针全部还原 + md5 复核（4 文件回到 11.1 值，
   0 探针残留），100 tests 复核 OK。

### 11.5 followups

1. **v1 写 IOV_MAX 修复（P0，coder）**：batch_set_v1 每 extent pwritev 的 iovecs
   （页数×2）>1024 → EINVAL。方向：pwritev 分片循环（每片 ≤512 页）或同 extent 内
   按 1,024 iovecs 切段；加单测：1025+ iovecs 边界（本地实验已给出阈值）。
2. 修复后 M4 重测（tester）：整链 p50 ≤0.8s 终裁 + syscall/state 实测（预期每批
   1–2 合并区间）。
3. v1 读侧每批 3–4 区间（链落盘分散）——若整链 63–84 次 preadv 成新瓶颈，下轮
   归因落盘连续性与 allocator 打包。
4. 证据路径：M4 /root/evidence-p2io-extent-m4/run-20260831-234916、M4D
   /root/evidence-p2io-extent-m4d/run-20260901-000728、IOV_MAX 实验日志在 3090
   /tmp/iovmax-test.bin（实验输出见 11.2）。

## 12. M4 终裁重测（IOV_MAX 修复后，e7）五门 + 两观察项（追加，2026-09-01 00:4x 裁决）

### 12.1 同步与门禁

- 2 文件同步：extent_file_backend.py **534683c6**（e7）+ test **73369487**（e7），md5 双侧
  一致；e5 hicache_storage 22348ed0 / e6 cache_controller 0d63a8e8 已在 3090 复核未动；
  引擎核心其余文件上轮已复核。
- 3090 单测：`Ran 104 tests in 1.092s OK` EXIT=0（extent 70 + file LRU 34）。
- 运行：M4F（host 5G，K=8 96 请求，run-20260901-002715，elapsed 609.2s，downgraded 5），
  探针版本临时加 V1_READ/WRITE_PROBE（测后还原，末轮误还原 e6 已当场修正重同步 + 复核）。

### 12.2 五门逐项 verdict（用户 2026-09-01 口径）

| 门 | 判据 | 实测 | verdict |
|---|---|---|---|
| a | 整链 restore p50 ≤ 1.0s | **1.320s**（n=20 整链 ≥20k tokens：p75 1.482 / p90 1.727 / max 1.844 / **min 0.563，5/20 ≤1.0s**）；全授予 p50=0.972s（n=100，326–31,149 tokens） | **FAIL**（差 32%；路径已证可行——5 样本 <1.0s） |
| b | 读放大 ≈1.0× | **physical/requested = 1.0000**（33,412.7MB == 33,412.7MB，1,087 读批） | PASS |
| c | 无 backup failure | **0 pwrite 失败 / 0 "pages failed"**；backuped_tokens_total=1,788,692（vs M4 288,738，+6.2×；= M3 1.9M / M4D 1.81M 健康平台值）。注：需求计数 hicache_backup 3.39M 为累计口径（含重复落盘），任何健康 run 均不相等（M3 57% / M4D 53% / M4F 53%）——以"零失败 + 平台值"判 PASS | PASS |
| d | syscall 稳定可解释 | preads/批 p50=**2**、p90=3、max=5（1,087 批共 1,975 次 preadv 搬 33.4GB ≈ 16.9MB/次）；整链 ≈ 21 批 × 2–3 ≈ 42–63 次/state——碎片所致、可解释、稳定 | PASS（如实测口径） |
| e | correctness | sha16 10/24 匹配；分歧全部落入已知非确定性家族：**同轮内纯重算 t1 vs t12 本已分歧**（前修复轮零存储读即 b140e9da vs c71201d3）→ 输出多模式是模型固有；新值（a1-t5=c71201d3、a8-t5=973d57cd）在恢复服务下出现但均为跨 run 稳定模式；无乱码/截断/损坏签名 | PASS（带注意：建议定向对照定论，见 followup 2） |

- 事件守恒：487 = 387 revoke + 100 io_finished ✓；restore_ready=100。
- **授予归属发现（12.4 详述）**：100 次授予中 79 属 grow 轮（t2/t3/t4 前缀命中——同会话
  链递进共享前缀已在存储），16 属 restore 轮、5 属 downgrade；restore 轮 24/24 发出
  prefetch、23 被 revoke（storage_hit>0 如 16,384/18,861 但部分覆盖未达阈值）。

### 12.3 两观察项（不许跳过）

- **A. 落盘碎片归因**：读写两侧同构——写侧 pwritev 调用/批（extent 块数）p50=**2**、
  max=3；读侧合并区间（preads）/批 p50=2、p90=3、max=5（1024 页批）。即每 32MB 批
  落 2–3 段连续区（allocator 打包 + extent 边界交错）。**结论：碎片存在但有限——若
  单区间化：整链 21 次 preadv（≤32 达标）+ 每批省 ~5–10ms → "还有 ~0.1–0.2s 可挖"
  （1.32 → ~1.1s 附近，仍不足以单独到 1.0s）**。
- **B. Host copy/scatter 线性度**：1024 页批间隔 p50=**37ms**、p90=102ms（1,052 个批间
  gap），不随批序/整链增长（线性、无超线性项）；37ms ≈ 设备 32MB@1.4GB/s(~23ms) +
  引擎侧 ~14ms/批（稳定）。整链 21 批 × 37ms ≈ 0.78s + finalize/队列 ≈ 与实测 p50
  1.32s 吻合。M4 的 19ms 双样本偏低（页缓存温尾，非稳态值）；修正口径
  ~0.036ms/页 引擎侧（仍优于 generic 的 0.2–0.34ms/页 ~8×）。

### 12.4 行为解读

- **IOV_MAX 修复生产生效**：v1 写路径 0 失败、存储满载（12.2GB→~35GB KV）、restore
  查询普遍命中（storage_hit 16,384/18,861…）。备份/恢复管线首次全链路贯通。
- **整链授予的归属**：grow 轮前缀命中（79/100）说明存储已能服务增量链共享前缀——这是
  v1 修复的直接收益（M3/M4 时代 grow 轮全 miss）。restore 轮 23/24 被 revoke 因部分
  覆盖（链在环形 arena 中被后续写入部分覆盖/在途竞态）——与 M3 同机制，非读侧失败。
- **gate a 差距定位**：1.32s = 21 批 × 37ms（设备 23ms 主导 + 引擎 14ms）+ 批间队列。
  0.8s 优化门需引擎侧批管线（14ms/批）与碎片（A）双管齐下；1.0s 可行性门差 32%，
  但 min 0.563s 证明设备路径本身可达 <0.6s（页缓存暖 + 低队列时）。

### 12.5 清理确认

- 探针还原（534683c6，0 残留）+ 104 tests 复核 OK；进程树清零、GPU 15 MiB、
  /data 48G 余量。证据：run-20260901-002715（agent json + mid-run-metrics +
  engine-p2io-m4f.log 探针全量）。

### 12.6 followups

1. **gate a 逼近（coder，可选优化）**：allocator 打包连续化（单区间/批）+ 引擎批管线
   14ms/批归因（预取线程与调度器 GIL/调度竞争）→ 1.32s → ~1.0–1.1s；0.8s 优化门需
   引擎侧更深改动。
2. **sha16 模式切换定论（tester/coder）**：定向单链对照——同链 restore-served vs
   fresh-serve 各 ×3，逐字节对比（A' 构造复用，S1 载荷），排除/确认存储路径影响。
3. **restore 轮部分覆盖归因**：环形 arena 覆盖 vs 备份在途竞态的占比（整链授予的
   restore 轮仅 16 次），决定下一轮是否扩容/分层。
4. 证据路径：M4F /root/evidence-p2io-extent-m4f/run-20260901-002715。

## 13. 时间守恒 profiling（M4T，2026-09-01 01:1x 裁决）——0.54s 未解释时间定位

### 13.1 实验与插桩

- M4T 短实验（同 M4F 配置：host 5G，K=8 96 请求，v1 路径，run-20260901-010143，
  elapsed ~670s，96 请求 0 失败）。插桩（临时改 3090 部署树副本，测后还原 + md5 复核）：
  - cache_controller.py：`restore_io_start`（aux 线程受理）、`kv_batch_start/done`
    （每批 kv_ms + kv-derived sidecar_ms，按 rid 归属）。
  - hybrid_cache_controller.py：`sidecar_start/done`（non-KV/Mamba 阶段，KV 后串行）。
  - extent_file_backend.py：batch_get_v1 每次 preadv 计时（preadv_ms 累计）。
- 事件守恒：544 issued = 453 revoke + 91 io_finished ✓；91 次 restore 全部有
  sidecar 阶段；55 个 restore 完成、平均 1.7 次尝试/rid（max 4）。

### 13.2 八段耗时表（整链 ≥20,000 tokens，7 样本，attempt 窗口 = io_start→fin）

| rid | tok | attempt | S1a(admit) | Σkv_ms | Σpreadv | Σv2 | gaps | mamba | finz |
|---|---|---|---|---|---|---|---|---|---|
| 9e6528fa | 24,856 | 0.548 | 0.517 | 0.515 | 0.345 | 0.001 | 0.008 | 0.008 | 0.000 |
| d3a8023c | 24,143 | 5.716* | 0.222 | 2.286 | 1.642 | 0.014 | 3.332* | 0.078 | 0.000 |
| 8a4d482d | 22,526 | 6.098* | 0.906 | 1.622 | 0.575 | 0.002 | 4.387* | 0.080 | 0.000 |
| 3c2b3cce | 22,957 | 6.234* | 0.601 | 0.859 | 0.598 | 0.002 | 5.295* | 0.076 | 0.001 |
| cc91a0b7 | 20,480 | 20.743* | 0.571 | 2.108 | 1.215 | 0.006 | 18.517* | 0.105 | 0.000 |
| 0da7bb8e | 30,718 | 40.264* | 0.589 | 2.109 | 1.443 | 0.004 | 38.050* | 0.092 | 0.001 |
| 3024cf23 | 31,149 | 46.431* | 0.554 | 2.413 | 1.753 | 0.003 | 43.913* | 0.090 | 0.001 |

\* 带星号样本的 "gaps" 经事件序列核查 = **重试间隔**（同 rid 多次尝试之间），非批间间隙：
0da7bb8e 实际 4 次尝试（0.70s / 0.55s / 0.17s / 0.92s，每次批间 0–3ms 背靠背）。

### 13.3 守恒检查与未解释时间定位

- **attempt 窗口守恒：精确**（Σ段 vs attempt 差 ≤0.016s，0.03–2.9%，±5% 达标）。
- **聚合统计（全部 91 次尝试）**：attempt p50=**0.411s** / p90=0.860s / max=1.913s；
  批 kv_ms p50=22.6ms（preadv ~12–18ms 设备 + ~4–8ms backend 开销）；**批间 gap
  p50=0.0ms / p90=1.0ms**——v1 下批间引擎侧开销≈0（对比 A' generic-128 的 44ms）；
  查询周期（issued→revoke）p50=13ms / p90=604ms；**重试等待（revoke→next issued）
  p50=15ms / p90=15.7s / max=33.5s**。
- **0.54s 未解释（专家问的账）定位**：M4F 的 1.32s（issued→fin）≈ 查询/重试相位
  （batch_exists_v2 周期 13ms–1.2s + 重试退避 15ms–33.5s）+ 读相位（21 批 × 22.6ms
  ≈ 0.47s，与模型 0.78s 同量级）+ mamba（0.08s）——**不在读侧**。慢样本（9.7–49.7s）
  = 重试循环等备份追平（链未全量落盘时反复部分查询，备份在途竞态的放大形式）。
- **14ms/batch 构成修正**：v1 下批间 gap ≈0ms；批周期 22.6ms = 设备 preadv 主导
  （12–18ms）+ backend 锁内开销（snapshot/verify ~4–8ms）+ 0.05ms kv-derived v2。
  M4F 的 37ms 与 A' 的 44ms 均为完整批周期（含设备），非纯引擎侧——引擎侧每批成本
  v1 下已可忽略。

### 13.4 结论与 followups

- 时间守恒达成；八段中读相位（attempt 0.41s p50）与 mamba（0.08s）均小；**剩余优化
  空间集中在查询/重试相位**（0.6–33.5s 的查询与重试等待 = 备份在途竞态）与 backend
  锁内开销（~8ms/批 → 整链 ~0.17s）。
- followup 1（coder）：重试相位压缩——备份完成感知（batch_exists_v2 命中率阈值
  触发等待而非轮询重试）或 restore 查询与备份队列互斥等待；预期整链 p50 从 1.32s
  降至 ~0.9s（attempt 0.41 + 查询 0.2 + mamba 0.08 + 边际）。
- followup 2（coder，可选）：backend 锁内开销 8ms/批（snapshot+verify 持锁）——
  批外预取 refs / 批量 verify 可再省 ~0.1–0.2s。
- 清理：三文件探针还原（0d63a8e8 / 3bb6ae94 / 534683c6 md5 复核、0 残留）、
  104 tests OK、进程树清零、GPU 15 MiB。证据：/root/engine-p2io-m4t.log +
  /root/evidence-p2io-extent-m4t/run-20260901-010143。
