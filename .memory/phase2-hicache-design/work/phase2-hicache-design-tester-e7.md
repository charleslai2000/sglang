# phase2-hicache-design-tester-e7 — 场景 A（prefetch 生命周期延迟链，P2-0a 补丁后）

## status
done（A1 空库签名复验一锤定音；A2 延迟链测量**被 I7 插桩 bug 阻断**——根因已定位，交付给协调人修复后重跑；判据全绿）

## A1（空库签名复验，K=8 短批 3 分钟截断）
- fresh /data/l3/p2b0-0b，引擎 14:05 起，driver 14:07:43 → 14:10:43 SIGTERM（3 分钟），32 请求完成（join 32 行）
- **签名确认**：prefetch_issued **8** → prefetch_revoke **8**（1:1 全 revoke），
  **io_finished = 0、finalize = 0** ✓（空库 revoke 在 IO 前，符合 P2-0a 定案）
- revoke 行完整字段：terminated=False、storage_hit=0、requested=20910（全部）
- issued→revoke 延迟：8 对，min 57ms / max 535ms（空库快速判定）
- A1 归因：PREFETCH_NO_HIT 8 + RECOMPUTE 24（fresh L3 全 miss，与 P2-0a 一致）
- 附带发现：A1 日志另有 1 个 TypeError（cache_controller.py:1318 _page_backup →
  get_data_page 的 kv_buffer NoneType subscriptable，写路径）——32 请求全部完成（未致命），
  记录为写路径观察项

## A2（预热→重访，核心）— 被插桩 bug 阻断
- 预热：K=1 12 turns（14:15:16 起）→ **0 请求完成**（driver 150s timeout 被杀）
- 重访：K=1 12 turns（14:17:52 起）→ **0 请求完成**（5.5 分钟后 SIGTERM 截断）
- 根因（已定位，证据 engine-a2.log L37086-37096）：
  **I7 插桩 bug**：cache_controller.py:1186 prefetch_io_aux_func 的
  `logger.info("[P2A] ... n_pages * self.page_size")` 在 n_pages=None 时抛
  `TypeError: unsupported operand type(s) for *: 'NoneType' and 'int'` →
  **prefetch IO 线程（Thread-2）崩溃死亡** → 该线程上的 prefetch 永不完成
  （无 io_finished/finalize）→ 请求永远等待 → admission 空转 1,316,229 次 →
  0 请求完成
- prefetch 时间线（A2）：
  - 14:15:17 issued 37a0a8e5（20910）→ 14:15:35 IO 线程 TypeError 崩溃 → 14:17:45
    abort_cleanup（预热 driver timeout 被杀时，pre_alloc=False）
  - 14:17:53 issued 8abb9e42（20910）→ 线程已死无执行 → 14:23:49 abort_cleanup（截断）
- **延迟链测量（issued→io_finished、io_finished→finalize、finalize→success）不可行**：
  IO 线程死亡导致无 io_finished 事件。revoke 残余：A2 无 revoke（挂起被 abort）

## 判据（两 run 均全绿，尽管 A2 实验被阻断）
- 引擎存活至截断（主线程存活，admission 空转即证据）；SIGTERM 优雅退出（kill_process_tree，
  无崩溃堆栈）；签名 grep（OOM/KeyError/RecursionError/SchedulerException）= 0；
  进程 0 残留；GPU 19027/18975 → 15 MiB

## 交付物（/root/evidence-p2b0-0b/）
- p2a-lines-a1.txt（11,403 行）、p2a-lines-a2.txt（1,316,234 行）
- engine-a1.log、engine-a2.log（完整副本，含两个 TypeError traceback）
- run-20260830-140743/（A1：join.log 32 行 + mid-run-metrics + turns）、prewarm/（0 完成）、
  run-20260830-141752/（A2 重访：join 0 行）
- attribution-a1.json（32 请求归因）
- MD5SUMS（152 文件）

## 延迟分布（可测部分）
- A1 issued→revoke：8 样本，min 57 / max 535 ms（空库判定，非 IO 延迟）
- A2 无完成事件对（阻断）

## followups（按优先级）
1. **I7 插桩修复（阻断项）**：cache_controller.py:1186 的 n_pages 需 guard（如 `(n_pages or 0) *
   self.page_size`）——修复后重跑 A2（预热→重访）才能测 issued→io_finished→finalize 延迟链；
   同文件 1318 行 _page_backup 的 NoneType（A1 写路径）建议一并排查
2. A2 重跑前确认 0b namespace 完整性（A1+预热写入 15G 链数据仍在，重跑无需重新预热——但
   建议 fresh 0c 保干净）
3. admission 空转 131 万次为 IO 线程死亡后的级联效应：请求等 prefetch 时 scheduler 无背压
   （每 pass 尝试 admission）——P2-1 admission 设计输入（等待 prefetch 的请求应暂停调度）
4. 预热/重访的 K=1 全 12 turns 轨迹含 L2/L3 超限拒绝（退化体）——若重跑建议确认不受影响

## open_issues
- A2 的 0 完成使"有货场景 prefetch 完整链"仍无数据：expected 签名（issued→io_finished→
  finalize→success）待 I7 修复后测
- A1 的 _page_backup TypeError 是否影响 L3 写完整性（32 请求完成但可能部分页未写入）——
  建议用 A2 重跑时顺带核对 L3 文件数与 write_back 计数
