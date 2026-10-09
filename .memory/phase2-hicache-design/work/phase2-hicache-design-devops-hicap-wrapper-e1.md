# Phase-2 Hicache Wrapper — devops Report

## status
done

## 新建 wrapper 路径 + 与基线 diff

- **新建文件**: `/root/direct-launch-hicap.sh`（远程 3090 runner）
- **基线**: `/root/direct-launch-gate1.sh`（RH OFF 基线，conc=8）

### 改动 flag（diff 摘要）

| flag | 基线 gate1 | 新 wrapper hicap |
|------|-----------|-----------------|
| `--max-running-requests` | 硬编码 `8` | 可配置，默认 `32`（env `MAX_RUNNING_REQUESTS`） |
| `--cuda-graph-max-bs` | 硬编码 `8` | 可配置，默认 `32`（env `CUDA_GRAPH_MAX_BS`） |
| `PATH` | 无 | 新增 `/root/miniconda3/envs/sglang-patch/bin` 前缀（flashinfer JIT 需要） |
| 注释头 | gate1 专用说明 | Phase-2 hicap sweep 说明 + diff 列表 |

所有其他参数（pool/Graph/extent/RH OFF/write_back/attention flashinfer/线性attn triton/mamba 等）完全保留，未改动引擎行为。

## 验证命令 + 真实输出

### 1. bash 语法检查
```
ssh root@175.155.64.171 "bash -n /root/direct-launch-hicap.sh && echo SYNTAX_OK"
```
输出：`SYNTAX_OK`（exit 0）

### 2. 保守验证：conc=8（默认 pool 64 + Graph ON）
启动命令：
```
MAX_RUNNING_REQUESTS=8 CUDA_GRAPH_MAX_BS=8 STORAGE_DIR=/root/hicache-storage L3_BACKEND=file MAX_SIZE=20G SGLANG_PORT=8024 /root/direct-launch-hicap.sh
```

验证结果：
- **Engine healthy**: `grep "Engine startup timings" /tmp/hicap-launch.log` 确认启动完成
- **CUDA Graph decode 捕获**: `bs=[1, 2, 4, 8]`（与 gate1 基线一致，graph max_bs=8 生效）
- **单请求 smoke**: `curl http://localhost:8024/v1/chat/completions` → HTTP 200 + `finish_reason: length` + `total_tokens: 28`
- **GPU 显存**: `19819 / 24576 MB`（mem_fraction 0.92，24G 卡）
- **无 OOM**: 启动成功，无 CUDA OOM 错误

### 3. 高 conc 默认配置验证（conc=32, graph max_bs=32）
启动命令：
```
STORAGE_DIR=/root/hicache-storage L3_BACKEND=file MAX_SIZE=20G SGLANG_PORT=8024 /root/direct-launch-hicap.sh
```
（未设 env，使用默认值 MAX_RUNNING_REQUESTS=32, CUDA_GRAPH_MAX_BS=32）

验证结果：
- **Engine healthy**: 启动成功，`Uvicorn running on http://0.0.0.0:8024`
- **CUDA Graph decode 捕获**: `bs=[1, 2, 4, 8, 12, 16, 21]`（见下分析）
- **单请求 smoke**: HTTP 200 + `finish_reason: length` + `total_tokens: 28`
- **GPU 显存**: `19917 / 24576 MB`（略高于 conc=8，因更多 CUDA graph capture 缓存）
- **无 OOM**: 启动成功

### 4. Graph max_bs=32 是否可行的结论

**结论：可行，但实际捕获上限受 mamba 状态缓存限制。**

详细分析：
- wrapper 传递 `--cuda-graph-max-bs 32`，引擎解析并尝试 capture bs up to 32。
- 但引擎输出 `max_running_requests is capped to 21 by the mamba state cache (max_mamba_cache_size=106, 5 state slots per request)`。
- 因此实际 decode graph 捕获范围为 `bs=[1, 2, 4, 8, 12, 16, 21]`，而非 32。
- **没有 OOM**，显存充足（4.46 GB avail after decode graph capture）。
- 若要达到真正的 conc=32，需要调整 mamba 参数（`--mamba-full-memory-ratio` 或 `--max-mamba-cache-size`，或改用 `--mamba-ssm-dtype bfloat16` 减半状态大小）。

**max_bs=32 不会导致 OOM 或 capture 失败**；它只是被 mamba 缓存容量限制在 21。如果需要 conc>21 的真实 32 并发，需要调整 mamba 配置。

## 证据路径

- Wrapper 文件: `/root/direct-launch-hicap.sh` on 175.155.64.171
- Baseline diff: `diff /root/direct-launch-gate1.sh /root/direct-launch-hicap.sh` (exit code 1, 3 changed lines + 1 added PATH line)
- Syntax check: `bash -n /root/direct-launch-hicap.sh` → SYNTAX_OK
- Launch logs: `/tmp/hicap-launch.log` (conc=32) and `/tmp/hicap-conc8.log` (conc=8)
- Health check: `curl -s -o /dev/null -w '%{http_code}' http://localhost:8024/health` → 200
- Smoke test: `curl -s http://localhost:8024/v1/chat/completions ...` → HTTP 200, finish_reason=length, total_tokens=28
- GPU memory: `nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits` → 19819/24576 (conc=8), 19917/24576 (conc=32)

## open_issues

1. **mamba 状态缓存限制并发上限**: 默认配置下 `max_running_requests` 被 mamba 缓存 cap 到 21（106 slots / 5 per request）。若需测试 conc=32，需调整 `--mamba-full-memory-ratio` 或 `--max-mamba-cache-size`，或改用 `--mamba-ssm-dtype bfloat16`。这不影响 wrapper 本身的正确性，但影响 Phase-2 sweep 的并发上限。
2. **conc=8 基线对比**: gate1 基线（conc=8, graph max_bs=8）已通过同样流程验证（health 200 + smoke 200 + graph bs=[1,2,4,8]），确认 wrapper 在 conc=8 下与基线行为一致。
3. **CUDA Graph max_bs=32 capture**: 引擎实际只 capture 到 bs=21（受 mamba 限制），但 wrapper 正确传递了 max_bs=32 参数。若需要完整的 32-wide graph capture，需要调整 mamba 配置。
