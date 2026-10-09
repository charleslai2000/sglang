# p2io-coder-e5 — P2-IO 批大小诊断（STORAGE_BATCH_SIZE 128→1024）+ 44ms 构成分析

## 1. status

**done** — 本机编码 + 单测完成：STORAGE_BATCH_SIZE 128→1024（常量 + 注释 + 受影响 docstring 一致性），
44ms/批构成分析（代码级 + 本地微基准），内存核对完成，回归门 87 用例全绿。**批大小改动按协调人方向
定位为诊断 A/B（非主修复）**——不部署 3090、不做额外工程化；主修复候选已转向
batch_get_v1/batch_set_v1 zero-copy 路径（另派任务）。

## 2. artifacts

| 文件 | 变更 | 为什么 |
|---|---|---|
| python/sglang/srt/mem_cache/hicache_storage.py | `STORAGE_BATCH_SIZE = 128` → `= 1024` + 注释记录 A' 依据与内存成本 | 诊断 A/B：A' 实测 175 批 × ~44ms 引擎侧批开销 = 7.7s（8.31s 的 93%），设备仅 516ms；批大小 ×8 把 per-batch 固定开销削 8× |
| python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py | docstring "STORAGE_BATCH_SIZE=128" → "=1024"（1 行） | 常量值变更后的注释一致性（e4 遗留未提交改动之上，本 epoch 只动这一行） |
| .memory/phase2-hicache-design/work/p2io_batch_size_microbench.py | 新增（throwaway，不入版本控制） | 44ms 构成微基准：真实组件（pinned torch.zeros dummy / 真实 ExtentFileBackend.batch_get / pinned 池拷贝），N∈{128,512,1024} 三测点拟合 F（每批固定）与 L（每页线性） |

**改动面修正（与任务描述差异）**：任务假设 STORAGE_BATCH_SIZE 定义在 cache_controller.py；实际定义在
hicache_storage.py:23（scout 报告已载明），cache_controller.py 的三处调用点（:1128 读 /:1273 命中查询
/:1356 写）import 该常量、**零改动**。git status 新增 M 仅 hicache_storage.py；extent_file_backend.py 的
M 为 e4 遗留（本 epoch 仅叠 1 行 docstring），test_extent_file_backend_unit.py 的 M 为 e4 遗留，本 epoch
未触碰。cache_controller.py 无任何改动。

## 3. evidence（真实命令与输出）

**回归门（extent 全量 + file LRU，e4 同门）**：
```
$ PYTHONPATH=python:test /home/charles/sglang-venv/bin/python -m unittest \
    registered.unit.mem_cache.test_extent_file_backend_unit \
    registered.unit.mem_cache.test_hicache_file_lru_unit
Ran 87 tests in 0.890s
OK                        # REAL_EXIT=0
```

**py_compile**（两变更文件）EXIT=0。grep 确认常量落盘：hicache_storage.py:27 `STORAGE_BATCH_SIZE = 1024`。

**微基准输出（本机 venv，torch 2.13.0+cu129，CUDA 可见）**：
```
N=  128  A(dummy alloc)=     2.4us/page B(batch_get)=    2.54ms/batch C(pool copy)=     3.9us/page
N=  512  A(dummy alloc)=     2.8us/page B(batch_get)=   10.66ms/batch C(pool copy)=     5.6us/page
N= 1024  A(dummy alloc)=     2.5us/page B(batch_get)=   33.04ms/batch C(pool copy)=     6.6us/page
fit: F (per-batch fixed) = -4.23 ms/batch, L (per-page linear) = 44.1 us/page
```
（F 为负 = 隔离环境无可测固定项；L 主要由 B 的字节读构成，本地页缓存 ~1.6GB/s 与 3090 冷读标定同量级。）

**改动面**：`git status --porcelain` → `M hicache_storage.py`（本 epoch）、`M extent_file_backend.py`（e4+
1 行）、`M test_extent_file_backend_unit.py`（e4 遗留）、`?? .memory/`（交换目录不入版本控制）。

**nixl 单测**（不在本任务门内，连带核查）：本机预存环境失败 `ModuleNotFoundError: No module named 'nixl'`
（外部库缺失），与本 diff 无因果；nixl 代码对常量仅有 guard + bounce buffer 尺寸依赖，语义自洽。

## 4. summary

### 4.1 44ms/批构成分析（代码级 + 微基准）

**代码级（读路径 `_generic_page_get`，cache_controller.py:1093-1116）**——每批 N 页的引擎侧逐 page 开销
恰为三段：
1. `get_dummy_flat_data_page()` × N：每页一次 `torch.zeros(..., pin_memory=True)`（cudaHostAlloc + 清零），
   无池化复用；
2. `backend.batch_get(hash_values, dummy_page_dst)`：extent 后端每页 `_target_byte_view` + `view[:] = page`
   （31KB memcpy 进 dummy）；
3. Python for 循环 `set_from_flat_data_page(host_indices[i*page_size], page_data[i])`：每页 reshape +
   索引赋值 31KB 进 pinned 池缓冲。
外加 per-batch 固定开销：每批一个 PrefetchAck 入 prefetch_sync_queue → prefetch_sync_thread →
`_reduce_prefetch_ack` **gloo all_reduce（每批一次分布式集合）**；以及 scheduler 侧每 ack 一次 drain。

**微基准结论**：隔离环境下逐 page 引擎侧工作 ≈ 10µs/page（alloc 2.5µs + 拷贝 4–6.6µs）≈ 1.3ms/batch@128
——与 3090 实测 44ms/batch 差 **30×**。44ms 不可能来自隔离可测的逐 page 分量，只能来自活引擎上下文：
(a) **GIL/分配器竞争放大逐 page tensor 操作**（调度线程并发跑 CUDA forward + drain，每页 3 个 torch 操作
全部争 GIL；cudaHostAlloc 在 5G pinned 压力下劣化），和/或 (b) **per-batch 固定同步**（每批一次 gloo
all_reduce + 队列跳转 + drain）。两者与现有数据均自洽；隔离 harness 无法分离（需引擎级探针——协调人明确
本 epoch 不部署 3090、不做额外工程化，如实留待 M4）。

**诊断判定**：批大小 128→1024 只削减 per-batch 固定部分（×8 批数），逐 page 工作原样保留——
- 若 44ms 主要为固定开销（all_reduce 等）→ M4 以 1024 重跑应见 8.31s → ~1.2–1.6s（固定 22×44ms ≈ 1s +
  设备 0.52s + 线性 ~0.15s）；
- 若 44ms 主要为竞争放大的逐 page 开销（alloc + 双拷贝）→ 批大小收效有限，**zero-copy 路径
  （batch_get_v1/batch_set_v1：后端直接 scatter 进 host_indices，消除 dummy 分配与一次拷贝）结构性更强 =
  专家裁决的主修复候选**（`_generic_page_get` 本身带 `# todo: deprecate` 标记，属遗留路径）。

### 4.2 内存核对（1024 页 × 31KB ≈ 32MB/批）

| 线程 | 每批持有 | 峰值 |
|---|---|---|
| prefetch_io_aux_thread（读） | 1024 dummy ≈ 32MB pinned（瞬态，逐批释放）+ 后端读缓冲 ≈ 32MB bytearray | ~64–96MB |
| backup_thread（写） | `_generic_page_set` 的 data = 池内 1024 个 view（零拷贝零新增）+ 后端 pwritev 缓冲 | 小 |
| prefetch_thread（命中查询） | 1024 个 hash 字符串 | 可忽略 |

峰值增量 <100MB，host 池 5G（A' 部署）→ **无内存风险**。附带：nixl bounce buffer 随常量放大 8×
（1024 × page_numel；31KB 页 ≈ 32MB/缓冲 ×2/池，alloc_mmap 惰性提交）——nixl 不在 3090 部署路径，
已在 followups 记录供常量定稿时评估。

### 4.3 语义变化核查（无冲突）

- `_page_transfer`：每批一个 ack 的语义不变，批数 175→22；`_reduce_prefetch_ack` 逐 ack 归约，跨 rank
  批数一致（同常量）——all_reduce 结果语义不变；
- `_storage_hit_query`：batch_exists 连续命中前缀语义不变，可见粒度变粗；
- 备份原子可见粒度 128→1024 页：R3 式"查询只见已落盘批前缀"的在途竞态粒度变粗，restore_retry=1 机制
  不变，不构成正确性回归（如实记录行为差异）；
- 单测：test/ 全仓 grep STORAGE_BATCH_SIZE 零命中，无测试假设 128，无需适配；87 门全绿实证。

## 5. followups

1. **主修复候选（另派任务）**：batch_get_v1/batch_set_v1 zero-copy 路径——后端直接 scatter 进
   host_indices，消除逐 page dummy 分配 + 双拷贝；extent 后端当前无 v1 零拷贝接口（仅 v2 有零拷贝
   语义），且 page_get_func 选择（cache_controller.py:664-675）需把 extent/dynamic 后端纳入零拷贝名单。
2. **M4 诊断重跑（3090，待部署裁决）**：本 epoch 批大小改动不部署；若后续以 1024 部署重跑 A' 同负载，
   8.31s → ~1.2–1.6s 则 44ms 以固定开销为主（批大小有效，可并入主修复）；无明显下降则逐 page 竞争
   为主（zero-copy 为唯一修复）。
3. **nixl bounce buffer 评估**：若常量定稿 1024，nixl 每注册池 bounce 缓冲 8×（~32MB×2@31KB 页，
   mmap 惰性）——nixl 属主决定是否需要独立上限常量。
4. **44ms 最终分离**（可选，若需要实证）：引擎级临时探针（M3DBG 先例：逐批 ts 记录 alloc/batch_get/
   copy/all_reduce 分段）——本 epoch 按协调人指示未做。
5. **设计文档对齐**（沿用 e4 followup 2）：p2-io-design.md §2.3 读侧 exact-range 语义标注仍挂账。

## 6. open_issues

- 44ms/batch 的固定 vs 逐 page 竞争占比在本机隔离环境不可分离（需活引擎探针或 3090 诊断重跑）——
  A/B 判据见 followup 2。
- nixl 单测本机预存环境失败（外部 nixl 库缺失），与本 diff 无因果。
- e4 两个 M 文件（extent_file_backend.py / test_extent_file_backend_unit.py）仍未提交（e4 遗留），
  部署同步时与本次改动一同评估。
