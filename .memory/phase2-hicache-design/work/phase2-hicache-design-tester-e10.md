# phase2-hicache-design-tester-e10 — P2-1 集成验证（M1b+M2）

## status
**blocked**（K=1 基线回归失败：M1b+M2 状态机 capacity 死循环 bug——restore_retry 83 万次
cause=capacity 无限重试，阻塞全部请求；现场已保存，等待协调人修复）

## 部署确认
- M1b+M2 插桩确认在引擎树：scheduler.py 2953-3069（frontier_wait / restore_retry
  cause=frontier|capacity / restore_recompute cause=timeout|miss / restore_ready）、
  unified_radix_cache.py（frontier waiter 注册/丢弃）✓；引擎未启动（验证时）

## K=1 基线回归（失败）
- driver 16:35:26 启动 → **4+ 分钟只完成 2 请求**（join 2 行）→ 截断 SIGTERM
- **根因（阻塞性）**：HEALTH_CHECK 请求（driver health-check，prompt 极短）进入 restore
  状态机 WAIT_CAPACITY（reason=REVALIDATE）→ cause=capacity 重试**无逃逸路径** →
  无限循环占满所有调度 pass → 正常请求无法推进
- 循环规模：restore_state **1,668,734** 次、restore_retry **834,363** 次（100%
  cause=capacity）、restore_disposition 834,367 次（RECOMPUTE/too_short）
- 真实请求路径（对照，正常）：e04b9498（16:34:00 WAIT_CAPACITY → 60s → restore_recompute
  cause=timeout ✓）；ffeaf753 frontier_wait node=27（16:35:34）→ 60s → restore_recompute
  cause=timeout（M2 注册发生但 wake 未发生）
- restore_recompute 共 3（1 miss + 2 timeout）；restore_ready **0**；frontier_wake **0**；
  prefetch_issued 1 / prefetch_revoke 1

## 判据
- 签名 0（OOM/KeyError/RecursionError/SchedulerException）✓；SIGTERM 优雅退场 ✓（1 轮询
  退出）；进程 0 残留 ✓；GPU 19019→15 MiB ✓
- CHAIN_GAP=0 语义：未测（K=1 未完成，L3 1b 近乎空——chain_check 不可行，记录原因：
  阻塞在状态机）

## 三判据对照（K=8 未执行——K=1 已阻塞，按"发现阻塞 bug 停止"纪律终止）
- recompute 1.87M→接近 0：**未测**（阻塞）
- restore-served 上升：**未测**
- turns/s 与 p95：**未测**

## 42ms-gap 场景（M2 验证）部分观测
- frontier_wait 注册**发生了 1 次**（ffeaf753，node=27，16:35:34——42ms-gap 场景在
  K=1 顺序 churn 中自然出现）→ **frontier_wake 0 次** → 60s 超时 restore_recompute
  cause=timeout
- 结论：M2 的 wait 注册路径工作（对照 M1 前 skip 不登记），但 wake 依赖 ancestor
  backup ACK——本 run 中未触发 wake（frontier 持久化未在 60s 内完成或 waiter 唤醒条件
  未满足），需修复 capacity 死循环后复测

## 交付物（/root/evidence-p2b0-1b/）
- p2a-lines.txt（3,337,470 行）、state-machine-lines.txt（2,503,101 行：restore_retry/
  state/recompute/ready + frontier_wait/wake 全量）
- k1/run-20260830-163526（join 2 行）、k1-driver.log、MD5SUMS（15 文件）
- engine log：/root/engine-p2b0-1b.log（完整循环轨迹 + 3 个 recompute 时间线）

## followups
1. **修复建议（阻塞项）**：restore_retry cause=capacity 需逃逸路径——WAIT_CAPACITY 加
   超时上限（同 timeout 路径 60s）或对 HEALTH_CHECK 类短 prompt 请求跳过 restore 状态机；
   当前 834K 次循环说明 capacity 条件永不满足且无上限
2. HEALTH_CHECK 请求进入 restore 状态机本身可疑（health-check 应无 restore 语义）——
   建议在调度侧排除非推理请求
3. frontier_wake=0 待 capacity 修复后复测（42ms-gap 场景需完整跑通：wait→wake→restore）
4. K=8 三判据与 deny/width 对照待 K=1 恢复后执行

## open_issues
- restore_state 的 WAIT_CAPACITY REVALIDATE 循环是否还会影响其他请求类型（L2/L3 退化体
  请求同样短 prompt）——修复前无法判定
- 1b namespace 近乎空（K=1 未完成）——修复后建议 fresh namespace 重跑全套
