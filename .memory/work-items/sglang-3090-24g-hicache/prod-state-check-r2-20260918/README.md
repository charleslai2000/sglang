# PROD-STATE-CHECK-R2-20260918

- **工作标题：** PROD-STATE-CHECK-R2-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/PROD-STATE-CHECK-R2-20260918.md`：**
Establish current GPU 3090 (24576 MiB) production service state. Verify port 30000 health, model endpoint availability, and production supervisor state. Report process status, HTTP endpoints, GPU utilization, and lock file ownership.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`phase2-hicache-design/agents/PROD-STATE-CHECK-R2-20260918.md`：**
**Port 30000 Status: UP**
- All HTTP codes return 200 (loopback: /health=200, /v1/models=200)
- LAN endpoint /health: 200
**GPU Status: BUSY**
- GPU: NVIDIA GeForce RTX 3090 (24576 MiB)
- GPU Memory Usage: 23009 MiB used / 24576 MiB total = 93.6% used
- GPU Utilization: 100%
- Free VRAM: 1567 MiB (24576 - 23009)
- PIDs using GPU:
  - 1654119: /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python (LD) 300 MiB
  - 1654601: sglang::scheduler (LD) 22634 MiB
**Canonical Lock File: HELD**
- File: /tmp/opencode/gpu-3090.lock
- Owner: supervise-prod-prod-20260917T211800Z-1653969

### 报告列出的产物/证据
- `phase2-hicache-design/agents/PROD-STATE-CHECK-R2-20260918.md`：**1. HTTP Health Checks:**
```
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30000/health -> 200
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30000/v1/models -> 200
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.20.250:30000/health -> 200
```
**2. Port State (ss -ltnp):**
```
LISTEN 0      2048         0.0.0.0:30000      0.0.0.0:*    users:(("python",pid=1654119,fd=68))
```
**3. Process State:**
```
ps -eo pid,ppid,lstart,etimes,cmd | grep -Ei 'sglang|launch_server|supervise|gate|smoke' | grep -v grep…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/PROD-STATE-CHECK-R2-20260918.md` → `.memory/phase2-hicache-design/agents/PROD-STATE-CHECK-R2-20260918.md`; SHA256 `47ff64fde2d69e47e6e59020827a55595a7216916ae6fe1064dcfef0089e9630`; source state `tracked`
