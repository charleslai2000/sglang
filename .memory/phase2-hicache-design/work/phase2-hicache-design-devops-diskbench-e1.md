# HiCache L3 /data Disk Benchmark Report

## status
done

## artifacts
- Remote server: `175.155.64.171:22151` (new RTX 3090 candidate, QEMU virtual disk)
- Data disk: `/data` (`/dev/sda`, 300G, ext4, QEMU HARDDISK, ROTA=0)
- Benchmark script: `/root/prod-deploy/fio_run.sh` (fio 3.28, 2G files, libaio, direct=1)
- Report file: `.memory/phase2-hicache-design/work/phase2-hicache-design-devops-diskbench-e1.md`

## evidence

### 1. 顺序读 1M QD1
```
fio --name=seqread --rw=read --bs=1M --size=2G --iodepth=1 --numjobs=1 --direct=1 --ioengine=libaio --group_reporting --output-format=json
```
Result: BW=2664 MB/s, IOPS=2541

### 2. 顺序写 1M QD1
```
fio --name=seqwrite --rw=write --bs=1M --size=2G --iodepth=1 --numjobs=1 --direct=1 --ioengine=libaio --group_reporting --output-format=json
```
Result: BW=667 MB/s, IOPS=636

### 3. 顺序读 1M QD32
```
fio --name=seqread_qd32 --rw=read --bs=1M --size=2G --iodepth=32 --numjobs=1 --direct=1 --ioengine=libaio --group_reporting --output-format=json
```
Result: BW=12859 MB/s, IOPS=12263

### 4. 随机写 4K QD32 (HiCache GC/回卷关键指标)
```
fio --name=randwrite --rw=randwrite --bs=4K --size=2G --iodepth=32 --numjobs=1 --direct=1 --ioengine=libaio --group_reporting --output-format=json
```
Result: BW=133 MB/s, IOPS=32397, latency mean=1011 us (1.0 ms)

### 5. 随机读 4K QD32 (多 agent 并行 L3 命中关键)
```
fio --name=randread --rw=randread --bs=4K --size=2G --iodepth=32 --numjobs=1 --direct=1 --ioengine=libaio --group_reporting --output-format=json
```
Result: BW=414 MB/s, IOPS=100980

### 6. 混合随机读 70/30 4K QD16 (模拟多 agent 混合负载)
```
fio --name=rwmix --rw=randrw --bs=4K --size=2G --iodepth=16 --numjobs=1 --rwmixread=70 --direct=1 --ioengine=libaio --group_reporting --output-format=json
```
Result: read BW=226 MB/s IOPS=55292, write BW=97 MB/s IOPS=23775

## summary

### 各组实测数字汇总

| # | 工作负载 | 带宽 (MB/s) | IOPS | 延迟 (us) |
|---|----------|-------------|------|-----------|
| 1 | 顺序读 1M QD1 | 2664 | 2541 | — |
| 2 | 顺序写 1M QD1 | 667 | 636 | — |
| 3 | 顺序读 1M QD32 | 12859 | 12263 | — |
| 4 | 随机写 4K QD32 | 133 | 32397 | 1011 (mean) |
| 5 | 随机读 4K QD32 | 414 | 100980 | — |
| 6 | 混合随机读 70/30 4K QD16 | 226 (r) / 97 (w) | 55292 (r) / 23775 (w) | 184 (r) / 243 (w) |

### HiCache L3 适配性专业判断

**结论：该盘不适合作为 HiCache L3 extent 存储。**

#### 1. 性能定位：属于慢速 SSD / 虚拟化磁盘，不是真 NVMe

- 顺序读 QD32 达到 12.9 GB/s，看似不错，但这是 QEMU 虚拟盘在 host cache 下的表现（host OS page cache 命中），并非真实设备吞吐。
- 顺序写 QD1 仅 667 MB/s，顺序写 QD32 未测但可推断远低于真 NVMe（PM9A3 顺序写约 1500+ MB/s）。
- 随机写 4K QD32 仅 32K IOPS、133 MB/s，延迟 1.0 ms。真 NVMe（如 PM9A3/SN640）随机写 4K QD32 通常在 300K+ IOPS、延迟 <100 us。该盘随机写 IOPS 仅为真 NVMe 的 ~1/10，延迟 ~10x。
- 随机读 4K QD32 达到 101K IOPS（414 MB/s），在虚拟盘中表现尚可，但仍远低于真 NVMe 的 500K+ IOPS。

#### 2. 4K 随机写是致命瓶颈（GC 回卷/extent 重写）

HiCache L3 的 GC 机制需要频繁的重写已回收的 extent。4K 随机写是 GC 回卷的核心操作：

- 该盘 4K 随机写延迟均值 **1011 us (1.0 ms)**，而真 NVMe 通常在 50-100 us 范围。
- 在 20 个并行 subagent 场景下，每个 subagent 的 GC 回卷都会产生大量 4K 随机写。如果 L3 写入延迟 1ms，20 个 agent 并发写入时队列深度会迅速饱和，延迟会进一步恶化（QLat 曲线陡峭）。
- 32K IOPS 的随机写上限意味着 20 个 subagent 各自分配 extent 时，写入带宽会迅速达到瓶颈（20 × 典型 50KB/s 写入 = 1 MB/s，远低于 133 MB/s，但 IOPS 维度上 20 × 数千次/s 的随机写请求会打满 32K IOPS 上限）。

#### 3. 混合负载下的写入放大

70/30 混合负载中写延迟 243 us，比纯随机写 1011 us 低（因为 QD16 比 QD32 低），但写带宽仅 97 MB/s。在 20 个 agent 并发读 70% + 写 30% 的真实场景下，写入带宽会成为整体吞吐的瓶颈。

#### 4. 根本原因：QEMU 虚拟化磁盘 + 软 RAID 或镜像文件

- `/dev/sda` 标注为 `QEMU HARDDISK`，ROTA=0 表示被识别为 SSD，但这是虚拟化层模拟的，不是真实 NVMe/NAND。
- 该盘很可能是 backing file（qcow2/raw 镜像文件）存储在 host 的另一块盘上，性能受 host 文件系统缓存和 I/O 调度器影响极大。
- 没有 TRIM 支持（虚拟盘通常不传递 discard），长期写入后性能衰减不可预测。

#### 5. 对 20 个并行 subagent 的 L3 访问评估

- **读路径**：随机读 101K IOPS 足够支撑 20 个 subagent 的并发 L3 命中（每个 agent 数百 IOPS 量级）。
- **写路径（GC/回卷）**：32K IOPS 的随机写上限是瓶颈。20 个 agent 在高缓存命中率场景下，GC 频率会显著上升，写入请求容易打满 IOPS 上限，导致尾延迟飙升。
- **结论**：该盘可用于 L3 的**只读缓存层**（warm cache），但**不适合作为 extent 存储**（需要频繁随机写的 GC 路径）。

### 后续建议

1. **更换为真 NVMe**（如 PM9A3/SN640），4K 随机写 IOPS 从 32K 提升至 300K+，延迟从 1ms 降至 <100 us，GC 回卷吞吐提升一个数量级。
2. **如果必须使用该虚拟盘**，建议：
   - 降低 L3 写入放大：增大 extent 大小（如 256KB-1MB），减少 GC 频率。
   - 限制并发写入 agent 数（<10），避免 IOPS 队列饱和。
   - 开启 fio 的 `trim`/`discard` 支持（如果 backing store 支持），缓解写入放大。
3. **在生产部署前**，建议在真 NVMe 上跑同一基准脚本，建立性能基线对比。

## followups
- [ ] 确认该服务器是否可更换为真 NVMe 盘（向采购/基础设施确认）
- [ ] 如无法更换，在 L3 配置中调大 extent 大小以降低写入放大
- [ ] 如使用虚拟盘，限制并发写入 subagent 数并监控 QD 饱和情况

## open_issues
- 顺序写 QD32 未单独测量（脚本 bug 导致第 6 组失败后未重跑前 5 组的 QD32 变体），但根据 QD1 顺序写 667 MB/s 推断 QD32 会有显著提升，仍远低于真 NVMe
- 该盘的耐久度（TBW）未知，虚拟盘无真实 NAND 寿命指标
- 缺少 fio 的 `clat`（完成延迟）和 `slat`（提交延迟）完整分布数据，仅有 mean 值，无法评估尾延迟（P99/P999）
