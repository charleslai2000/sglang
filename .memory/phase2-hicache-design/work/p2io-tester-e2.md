# p2io-tester-e2 — P2-IO M2 extent 实验分析收尾（实验 FAIL：extent 写入 bug 导致零服务，判据无法裁决）

## 1. status

done（分析收尾完成）。**M2 验证结论 = FAIL**：extent 首次运行引擎崩溃（65/96 请求失败），根因链已实证，四项判据均无法按冻结决议口径裁决或判 FAIL。extent 后端存在一个单测未覆盖的写入 bug（bf16），修复后必须重跑。

## 2. artifacts

**状态文件摘要（/root/p2io-m2-status.log，3090）**：`EXTENT_STAGE_COMPLETE rc=0`（18:52:23 出现）——extent 自跑已完成，无需等待。driver rc=0 但 **failed=65 / downgraded=12**。引擎 18:51:55 崩溃（Scheduler hit an exception），18:52:00 driver 结束（elapsed 191s），18:52:23 脚本 SIGTERM 引擎、GPU 15MiB。

**extent 运行统计表（证据 /root/evidence-p2io-extent-01/run-20260831-184849/）**：

| 项目 | 值 |
|---|---|
| 请求 | 96：成功 31 / 失败 65（http=None，引擎崩溃后 Connection refused）/ downgraded 12 |
| 分阶段 | warmup 32（ok 27）、steady 56（ok 2）、drain 8（ok 0） |
| restore turns | 24 个：23 失败 + 1 成功（S6-L0-V1 t5，device_hit=1152 纯 device 命中，非 storage restore） |
| storage_hit | **0（全程）** vs file 基线 648,718 tokens |
| host_hit / device_hit 累计 | 63,987 / 36,561 |
| [P2A] 归因 | prefetch_issued=92、prefetch_revoke=92（全部 revoked:miss）、**prefetch_io_finished=0 / io_finished=0 / restore_served=0**、restore_recompute=99（miss 89 + timeout 10）、restore_retry=150（capacity）、restore_disposition=92 revoked + 3 too_short、forced_drop_to_miss=29、promotion_release=1（cause=exception） |
| scheduler 累计 io | syscr delta **6,806**（91,207→98,013，采样器 18:48:48→18:52:00）、read_bytes +0.32GB、syscw delta 4,952 |
| extent 数据文件 | /data/l3/p2io-extent/hicache.data_qwen3.5-9b-gptq_0_1 = 64GiB **稀疏**（du 4.0K，0 数据块）——零写入实证 |
| ttft（成功请求） | p50=27.7s / p95=72.6s / max=75.3s（warmup 冷 prefill 排队，非 restore 数据，不作判据输入） |
| OOM / corruption | dmesg 无 OOM 记录；无 corruption 实证（见 sha16 小节） |

**根因 1（P2-IO 引入，M2 阻塞，已定位未修）**：`extent_file_backend.py:67 _page_byte_view` → `value.numpy()` 对 **bf16 CPU tensor** 抛 `TypeError: Got unsupported ScalarType BFloat16`（配置 kv_cache_dtype=bf16）。backup_thread（Thread-4）18:49:07 首次 batch_set 即抛异常、线程死亡（engine log 行 821-843），此后 **extent 写入完全停滞** → storage 永远 miss → 全链归因如下。`_target_byte_view`（行 73-82，读回路径）同款 numpy() 代码——读路径也有同型隐患（本次未触发：读取从未到达 batch_get）。

**根因 2（引擎核心既有竞态，被根因 1 级联触发）**：`unified_tree_core.py:1948 assert device_value is not None` 崩溃（Scheduler hit an exception，engine log 行 2522-2565）。路径：evict_for_alloc → writing_check(write_back=True) → _flush_pending_storage_writes → write_backup_storage → build_backup_spec，此时节点 device_value 已被释放。前置：host 内存压力 225 次 "KV subtree dropped without backup" + 29 次 forced_drop_to_miss。级联链：写入全失败 → storage 空 → restore 全 miss → KV 滞留 host → host 超压 → drop 风暴 → pending write flush 竞态 → 崩溃。P2-IO 未触碰 unified_tree_core.py（既有代码路径）；file 基线 983s 未触发（storage 正常、restore 慢速排空）。

**sha16 交叉验证（file vs extent，同 payload）**：22 个可比 warmup grow turn（payload.json md5 逐字节一致、temperature=0）中 **20 一致 / 2 不一致**：S4-L0-V1 t1（extent a73fab60c6489342 vs file f14fd90415c02f84）、S6-L1-V1 t2（extent 15c267c48b025ed3 vs file b45b370f8ff06f41）。两例均发生在**无存储读的冷 prefill/grow 路径**（extent 存储空、读取从未发生），不经过 extent 后端读路径，不能归因于 extent 数据损坏；不排除 batch 组合相关的生成级数值非确定性，待重跑确认。

**引擎清理确认**：脚本自行 SIGTERM（18:52:23，run log 记录 remaining procs=1、gpu_mib=15 MiB）；复核 ps 无 sglang/python3 引擎进程（仅系统 supervisord/fail2ban/jupyter 常驻），nvidia-smi = **15 MiB / 24576 MiB**。GPU 已释放。✓

## 3. evidence（真实命令与输出）

- 状态文件：`EXTENT_STAGE_COMPLETE rc=0`；driver banner `requests=96 failed=65 downgraded=12 elapsed=191s (budget 3600s)`。
- 崩溃证据（engine log 尾部）：`Scheduler hit an exception: ... unified_tree_core.py line 1948, in _build_backup_spec / assert device_value is not None / AssertionError`，随后 `SIGQUIT received`、`kill_process_tree called: parent_pid=167221`。
- 写入 bug 证据（engine log 行 821-843）：`Exception in thread Thread-4 (backup_thread_func): ... extent_file_backend.py line 67, in _page_byte_view / arr = value.numpy() / TypeError: Got unsupported ScalarType BFloat16`；同文件仅此 1 处（线程首次即死）。
- 零写入实证：`du -sh /data/l3/p2io-extent/` = 4.0K；数据文件 68719476736 字节（稀疏预分配）。
- 零服务实证：`grep -c evt=prefetch_io_finished` = 0、`evt=restore_served` = 0；join.log `metric storage_hit: last=0 max=0`；restore_recompute causes `{'miss': 89, 'timeout': 10}`。
- open-read 实证：samples.jsonl（84951 行，挂在 scheduler 167260）io 序列 syscr `91207 -> 98013`（delta 6,806）、read_bytes +322,441,216 B、syscw delta 4,952；起点与 /root/p2io-extent-io-before.txt 逐字段一致。**io-after 快照缺失**（/root/p2io-extent-io-after.txt 不存在，脚本未写入；以采样器终点替代）。
- sha16 实证：`md5sum .../turns/agent-4/t1.grow.payload.json` 双侧 `aa744917764700e0b45ee785140b76c6` 一致；agent-6/t2.grow 双侧 `54197fe8708e9f78bb4b8b50177fdbf6` 一致；payload `temperature=0.0 max_tokens=64`（双侧同）。
- 单测缺口实证：test_extent_file_backend_unit.py 头注释 "The backend is driven with bytearray pages end-to-end (no torch import): suite runs torch-free on CPU"——62/67 单测全绿但从不传 torch tensor，`.numpy()` bf16 分支零覆盖。
- dmesg：`grep -i oom` / `grep -i "killed process"` 均无匹配（rc=1）。
- file 基线对照（/root/evidence-p2io-file-01/run-20260831-180853/runs.csv）：restore turns n=24，ttft p50=66.4/p95=106.2/max=139.2s，wall p50=70.2/max=143.7s；96 请求 0 失败 1 降级；storage_hit 合计 648,718 tokens；scheduler syscr=1,501,305。

## 4. summary

- 判据逐项 verdict：
  1. **核心（~640MB restore 11–12s → <1s）：NO DATA（无法裁决）**——extent 后端零次成功 restore（io_finished=0、restore_served=0、storage_hit=0），无任何 extent restore 服务时间可测。失败原因不是性能，是写入 bug 导致功能未就绪。
  2. **p50 ≤ 0.6s：NO DATA**（同上，无纯 IO 窗口样本）。
  3. **open-read 数量级下降：部分证实但语义为空**——extent 后端实测 0 次 pread/pwrite（写入死于 numpy 转换、读取从未到达，数据文件 0 数据块）；scheduler syscr delta 6,806 vs file 1,501,305（~220×）但这是"存储 IO 从未发生"的空转数字，不是正常工作的 extent 后端的 syscall 形状；"≤32/state" 设计目标无法用本次数据验证。
  4. **K=8 短回归（0 OOM / 0 corruption / 无 regression）：FAIL**——引擎崩溃（AssertionError）+ 65/96 失败（回归性劣化 vs file 0 failed）；dmesg 无 OOM（该项通过）；corruption 无实证（2/22 sha16 不一致发生在无存储读的 warmup 路径，与 extent 后端无关，不能归因 corruption，待重跑确认）。
- 为什么失败：根因 1（bf16 numpy 写入 bug，P2-IO 新代码、单测类型契约缺口）→ storage 全空 → 根因 2（既有核心竞态）被 host 超压级联触发 → 引擎崩溃 → 65 请求失败。修复根因 1 后必须重跑，并单独验证根因 2 是否仍可在正常负载下触发。
- 本次运行仍有正向产出：get_stats 契约修复后引擎正常启动（该修复有效）；warmup 阶段 27 个请求完成、sha16 20/22 一致（基线正确性未退化）；清理流程完整（SIGTERM/GPU 释放）。
- 已用证据补齐 e1 遗留缺口：scheduler 侧 syscr 精确值（采样器正确挂载，delta 6,806）、io-after 缺失的替代证据、extent 存储状态（稀疏文件）。

## 5. followups

1. **修复根因 1（必做，阻塞 M2）**：`_page_byte_view` / `_target_byte_view` 对 torch tensor 改用 bit 级字节视图（如 `value.contiguous().view(torch.uint8).numpy()`）或显式 bf16→uint8 转换，避免 `.numpy()` 的 bf16 限制；补单测：bf16 CPU tensor 直驱 batch_set/batch_get（模拟 host 池 flat page 真实 dtype）+ 建议集成级验证（引擎内真实写入路径）。位置：python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:55-82。需 coder 执行（超出 tester 验证范围）或 orchestrator 授权。
2. **根因 2 上报（pre-existing，引擎核心）**：unified_tree_core.py:1948 build_backup_spec assert——pending storage write flush 与节点 drop（host 压力）竞态；建议 flush 前校验 device_value 为 None 则跳过该 pending write（并释放对应索引），或 flush 前恢复 device_value。位置：python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:1945-1948 + unified_radix_cache.py:1995-2030。待 orchestrator 决策（既有核心改动）。
3. **重跑计划**：修复根因 1 后重新同步双侧 → 单测（新增 bf16 用例）→ 重跑 extent 实验（同一脚本 /root/p2io-extent-run.sh）→ 按本报告口径重做四项判据；重跑时确认 io-after 快照写入（脚本缺陷）。
4. sha16 两例不一致：重跑后优先复检 S4-L0-V1 t1 / S6-L1-V1 t2；若重跑稳定复现且 payload 仍逐字节相同，则升级为 corruption 调查。
5. e1 遗留未变：get_stats 修复未提交本地 git（两个文件：extent_file_backend.py + test_extent_file_backend_unit.py，md5 见状态文件 §2）；unified 门 112 例 ninja 失败（环境缺口，待 devops）。

## 6. open_issues

- **O_DIRECT 标定：未验证**——本次 extent 读路径从未执行（零 restore），O_DIRECT 大块读的实际性能、对齐约束、与 64MB extent 的交互全部未知；修复后重跑是第一次真实读数。
- **extent 大小（64MB/1024 slots/20G max/10G min_free）：未验证**——配置在位（engine log 18:48:32 ExtentFileBackend init 行）但零写入，参数有效性无数据。
- **B1-B5 设计开放项**：未涉及（本次连正常读写都没有）。
- 崩溃竞态（根因 2）即使修复根因 1 后仍可能被高 host 压力负载触发——重跑需关注 host_pressure 指标（本次 225 次 drop 是极端压力场景）。
- extent 后端 stats_snapshot 的 io 计数未在引擎日志 dump——若后续需要精确 open/pread/pwrite 计数，建议在重跑脚本中显式调用 stats_snapshot() 落盘（本次以采样器 syscr + 稀疏文件佐证）。
- 本机分析副本：/tmp/p2io-e2/{engine-p2io-extent2.log, join.log, runs.csv, verdict.json, samples-extent.jsonl, runs-file.csv}（3090 原件未动）。
