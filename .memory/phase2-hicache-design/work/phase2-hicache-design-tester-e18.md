# P2-1 收尾：K=16/32 scale smoke — tester e18 报告

## 1. status

**blocked（环境前置）** — K=16/K=32 smoke 无法启动：**/data 磁盘 96%（剩 9.4G）低于 L3 storage backend 的 min_free_space=10G 写入阈值**（launch 脚本 :112 `"min_free_space": "10G"` 冻结参数）——fresh ns p2b0-2a 的写链会被拒绝，"grow 写链 + 重访"路径失效，smoke 判据（归因/写链覆盖）无效。需协调人授权清理历史实验 ns（见 followups 1）后重跑。

## 2. artifacts

- /root/evidence-p2b0-2a/：已建目录（空）；/data/l3/p2b0-2a 已建（0 文件）
- **md5 核对（e17 基线，3/3 未变）**：unified_tree_core.py **fb931e5c** / unified_radix_cache.py **d992a972** / scheduler.py **7305eb0b** ✓（coder 并行部署未覆盖）
- 环境干净：NO_ENGINE / NO_DRIVER / GPU 15MiB

## 3. summary

### 3.1 阻塞证据
- `df -h /data`：197G 总量，**已用 178G（96%），剩余 9.4G**
- min_free_space=10G（冻结参数）→ free 9.4G < 10G → **storage backend 拒绝一切新 L3 写入**（写链 0 文件可证）
- /data/l3 178G 全部为历史实验 ns（无备份/系统数据）：

| ns | 大小 | 说明 |
|---|---|---|
| p2b0-01 | 18G | P2-0 早期批次 |
| p2b0-02 | 17G | P2-0 早期批次 |
| p2b0-0c | 15G | 0c 复用链（P2-1 终判用） |
| p2b0-0a/0b | 各 15G | 早期 |
| t38rs3/t38f1/p2b0-1c | 各 14G | t38/中间链 |
| t38sb/t38patch3/t38f2/t38rs2 | 各 11-12G | t38 系列 |
| 其余（1a/1b/1d/1e/1f/1g/1h/1i 等） | <11G | 各轮 run ns |

### 3.2 为何不自行处理
- Deletion discipline（50-forbidden）：无用户/协调人确认不删任何文件——历史 ns 保留原样
- 改 min_free_space 属冻结参数变更——不越权

## 4. followups

1. **协调人裁决磁盘清理**（释放 ≥5G 即可）——建议清理早期实验 ns：p2b0-01+02（35G）或 t38 系列（t38sb/t38patch3/t38f1/t38f2/t38rs2/t38rs3 ≈ 77G）；保留 0c（终判链）。授权后我可继续 smoke（清理命令由协调人/用户执行或明确授权我执行）
2. smoke 设计（已就绪，待磁盘解锁）：K=16 × 8 turns（128 请求）+ K=32 × 8 turns（256 请求，25 分钟护栏，必要时截断）；fresh ns 2a；五项确认（no unknown disposition / no orphan WAIT / no OOM / frontier bookkeeping 深度对比 / degradation curve 归因解释）；判据签名 0 / 优雅退场 / 0 残留 / GPU
3. K=32 RAM 核算（沿用 driver-design 容量表）：31G RAM——256 请求 × ~80KB 请求对象 ≈ 20MB，KV 池 32768 tokens 上限不变（调度排队），无 RAM 风险；磁盘是唯一前置

## 5. open_issues

- 磁盘 96%（剩 9.4G）< min_free 10G——fresh-ns 写链阻塞（唯一阻塞项）
- 引擎基线 fb931e5c/d992a972/7305eb0b 已核对未变（coder 并行部署尚未落地）
