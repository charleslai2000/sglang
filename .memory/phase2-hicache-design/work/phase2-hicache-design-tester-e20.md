# P2-1 收尾：K=16/32 scale smoke（M1/M2 修复版）— tester e20 报告

## 1. status

**blocked（重要发现）** — K=16 smoke **完整通过**（128/128、18.5 分钟、OOM=0、五项全过）；**K=32 smoke 5 分钟 OOM 崩溃复发**（16384-token 半池锁链，与 e15 K=8 崩溃同形）——**M1/M2 修复未覆盖深度 32 触发的 evict 死锁路径**。归因曲线完整记录（K=8/16/32 对比），五项确认逐项结论见下。需协调人裁决：evict 锁链第三轮修复或接受 K=32 为已知 scale 边界。

## 2. artifacts

- /root/evidence-p2b0-2a/：run-20260831-065016（K=16：**128/128 http 200**、0 failed、elapsed 1112.9s）、run-20260831-070916（K=32：47 http 200 + 209 failed、elapsed 386.8s——5 分钟 OOM 崩溃）、k16-driver.log、k32-driver.log、MD5SUMS（7 项）
- /root/engine-p2b0-2a.log（K=32 OOM traceback + 锁链 dump 完整）
- 磁盘清理记录：df 9.4G→173G→**154G 可用**（2a 已写 19G）；0c 完好 15G/273,040 files
- **md5（M1/M2 版，启动前核对）**：a2721792 / b77e23ac / 7305eb0b ✓

## 3. summary

### 3.1 K=16 smoke：完整通过
128/128 成功、elapsed 1112.9s、OOM=0、签名 128/128 一致（0 mismatch）、run 后引擎存活
- 归因：recompute 294（miss 178 + timeout 116）；dispositions revoked:miss 177 + alloc_failed 1 ↔ miss 178（1:1 可解释）；too_short 50 / shortfall 97 / denied 66 / hybrid_discard 37
- frontier_wait 94 / wake **82（87%）**、restore_ready 134、wait rids 90 / **orphan 0**
- L3 写链：2a 写入 18G/326K 文件（fresh ns 一轮 run）

### 3.2 K=32 smoke：5 分钟 OOM 崩溃（关键发现）
- 崩溃形态与 e15 K=8 完全同形：`Available full tokens: 16384 (10 + 16374 evictable)` 分配 2048 失败；**dump 再现 16384-token 半池锁链**（[9]→[22]→[1502]→[1607]→…，locked sum=16384）
- 崩溃前状态：queue-req 31、**pending-token 776K**（32 agents 全入队）——深度 32 的容量竞争触发锁链保护 → evict 回收 0 → OOM
- 归因（崩溃前窗口）：recompute 141（miss 31 + timeout 110）；revoked:miss 30 + alloc_failed 2 ↔ miss 31（可解释）；wait 25 / wake 20（80%）；wait rids 25 / **orphan 1**（引擎崩溃截断的 in-flight 未决——非 bookkeeping 失效）
- 签名：47/47 一致 ✓

### 3.3 五项确认逐项
| 项 | K=16 | K=32 | 结论 |
|---|---|---|---|
| 1. no unknown disposition | ✓（294 全归因） | ✓（141 全归因，崩溃前） | **通过** |
| 2. no orphan WAIT | ✓（90/0） | ✗（25/1，崩溃截断后果） | K16 通过；K32 orphan 是崩溃后果非 bookkeeping |
| 3. no OOM | ✓（1113s） | **✗（387s 崩溃）** | **K=32 复发** |
| 4. bookkeeping 随 depth 不失效 | ✓ | ✓（wake 率稳定、清理正常） | **通过**（wake 率 8/16/32 = 85/87/80%） |
| 5. degradation curve 可解释 | ✓ | ✓ | **通过**（见 3.4） |

### 3.4 归因构成随 K 变化（M1/M2 版）
| K | 请求 | recompute/req | miss 占比 | timeout 占比 | wake 率 |
|---|---|---|---|---|---|
| 8（e17 终判） | 96 | 0.5 | 54% | 46% | 85% |
| 16（2a fresh） | 128 | **2.3** | 61% | 39% | 87% |
| 32（崩溃前） | 47+ | **3.0** | 22% | **78%** | 80% |
- 解释：深度 ↑ → recompute/req ↑（0.5→2.3→3.0）；K=16 fresh ns 写链期 miss 占比高（revoked:miss 主导）；**K=32 timeout 占 78%**（并发 32 容量竞争，60s 等待超时主导）——degradation 形态随 K 单调可解释
- 注：K=16/32 为 fresh ns 2a（无链预热），K=8 为 0c 复用链——基数不同，形态对比仅供参考

### 3.5 判据
- K=16：签名 0 ✓（128/128）、优雅退场 ✓（run 后引擎存活）、0 残留 ✓、GPU 15MiB ✓
- K=32：签名 0 ✓（47/47 成功行）、优雅退场 ✗（OOM 崩溃）、0 残留 ✓、GPU 15MiB ✓
- CHAIN_GAP：2a fresh ns 无 0 起点链语义（grow 写链目标达成：19G/326K+ 文件）；0c 完好未受影响

## 4. followups

1. **协调人裁决（关键）**：K=32 evict 锁链死锁复发（16384 半池锁链，与 e15 同形）——M1/M2 修复未覆盖。选项：(a) evict 锁链第三轮修复（方向：locked 链保护的子树 evict 策略/锁释放时机——同 e15 定位）；(b) 接受 K=32 为已知边界（K≤16 稳定）
2. 若修：建议先 K=1 回归 + K=16 复测 + K=32 重测（本次 K=32 崩溃归因可作为修复前后对比基线）
3. collect_metrics l3_to_h_wait/quota 三项 missing 依旧（跨 run 未解决，非阻塞）

## 5. open_issues

- K=32 深度 evict 锁链死锁（OOM 复发，5 分钟崩溃）——唯一阻塞项
- K=32 崩溃导致 209 请求 failed + 1 orphan（截断后果）
