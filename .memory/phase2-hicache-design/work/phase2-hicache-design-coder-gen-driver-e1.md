# Phase-2 Decode/Mamba benchmark generation-shaped load driver — coder report

## status: done

Task: 实现阶段② Decode/Mamba benchmark 生成型负载驱动（并行准备，不执行实验）。
仅写代码 + 静态验证；未启动引擎、未跑任何负载、未占用 GPU、未修改任何已有文件。

---

## Artifacts（交付物，均在目标机 175.155.64.171）

| 路径 | 内容 |
|------|------|
| `/root/gen_load.py` (17499 B) | 新驱动：固定 trace 语义 + max_tokens 注入 + 阶段②指标采集 + `--dry-run` |
| `/root/gen-payloads/p01.json..p16.json` (16 个) | 固定 prompt 集（中文/英文混合短指令，无 max_tokens，由脚本注入） |

未修改：引擎源码、`/root/gate2_load.py`、`/root/p2-0/common.py`、`/root/gate3_soak.sh`、已有 wrapper 引擎参数。

### py_compile 结果（静态验证）
- 本地（用户机器）：`python3 -m py_compile gen_load.py gen_payloads.py` → rc=0
- 远程（目标机 sglang-patch env）：`/root/miniconda3/envs/sglang-patch/bin/python -m py_compile /root/gen_load.py` → rc=0（`REMOTE_ENV_PY_COMPILE_OK`）
- 远程 dry-run（不触引擎/不跑负载）：`cd /root && .../python /root/gen_load.py --dry-run --max-new 256 --agents 8 --turns 10` → `DRY_RUN_OK payloads=16 max_new=256 agents=8 turns=10`

### 逻辑自测（本地，stub common 模块，未触引擎）
- `inject_max_tokens`：身体含 `max_tokens=256, temperature=0`，不突变源 payload，不带 streaming/stream 字段
- `discover_payloads`：恰 16 个，按文件名排序
- trace 确定性：agents/turns/N=16 下每 agent 序列跨 cell 逐字节一致
- 全流程回合模拟（2 agents × 3 turns，stub run_request）：runs.csv 16 列 6 行、verdict.json（requests_total=6 / generation_tokens_total=768）、turns/ 产物（.headers/.body/.meta.json/.payload.json）、mid-run-metrics.txt 采样快照、join.log 行全部符合预期
- `gen_parse_metrics`：13 个阶段②指标解析自标签化 prometheus 文本，全部正确（gen_throughput=120、decode=159937、prefill_compute=22688629、mamba_usage/used/available/evictable=17/17/89/5、cuda_graph_passes decode=61500 等）

---

## 设计说明

### 固定 trace 怎么保证（跨 cell 完全一致的硬要求）
1. **payload 集固定**：`/root/gen-payloads/p01.json..p16.json`，文件名排序为固定顺序；不在 payload 文件里炸 max_tokens。
2. **每 agent 固定序列**：agent a (1-based) 的第 t 次请求使用 payload idx = `(a + t - 2) mod N`。N=16 时每 agent 前 16 次不重复；agents/turns 给定的整条序列跨 cell 逐字节一致。
3. **max_tokens 在 POST 时注入**：不流式、`temperature=0` 减小采样随机性。
4. **产物可复验**：每一步请求的实际 body 由 `common.run_client_inproc` 原样写回 `<prefix>.payload.json`，执行的 trace 可从证据字节级核对。

### max_tokens 注入方式
#### Why not common.py 改：共同模块被禁止修改（"禁止修改 /root/p2-0/common.py"）。
实测 `common.run_request(payload_path, out_prefix, opts, metrics_lock)` →
`run_client_inproc` 直接 `json.load(open(payload_path))` 原样 POST + 把相同 JSON 原样写回 `<prefix>.payload.json`。
所以驱动在调用 run_request 前先自行写好 `<prefix>.payload.json`（已注入 max_tokens/temperature），
并以该文件路径为 payload_path 传给 run_request —— 请求体与证据记实体一致，common.py 零改动。
gate2 无 max_tokens 默认 64 的 premise 也已由现有证据复核（meta.json usage 显示 max_tokens=64、finish_reason=length）。

### 指标采集
- **per-request 行**（runs.csv + verdict.json）：agent_id、turn、payload、prompt_len、completion_tokens、total_tokens、finish_reason、ttft_s、wall_s、http、finished、rid、ts_start/end + 每请求 counter 增量（mamba/evictable 等，经 common.metrics_delta）。
- **mid-run 采样**：采样线程每 --snapshot-interval 秒抓一次 /metrics，导入自有扩展解析 `gen_parse_metrics`（common.parse_metrics 覆盖不到的 decode/mamba 前缀）：
  `gen_throughput`、`realtime_tokens_total{mode=decode|prefill_compute|prefill_cache}`、`prefill_effective_tokens_total{mode=input|device_hit|host_hit|storage_hit}`、`cuda_graph_passes_total{mode=...}`、`mamba_usage/used_tokens/available_tokens/evictable_tokens`、`num_running_reqs/num_queue_reqs`、`startup_available_gpu_memory_gb`。
  全部原始快照落盘 mid-run-metrics.txt，供执行者按 mode = label 抽取。
- 结束：正常退出 rc=0；verdict.json 输出总请求/完成/总 generation tokens/平均 wall；stdout 打印 `GEN_DRIVER_DONE run_dir=... requests=... completed=... gen_tokens=...`。

### argparse CLI（先 --dry-run 做静态验证）
```
--agents N  --max-new M(256..512)  --turns T  --budget SEC(默认900)
--evidence-dir DIR  --stagger 0.0  --client-max-time 580  --snapshot-interval 5.0  --payload-dir /root/gen-payloads
```

---

## 使用说明

### 每 cell 命令示例（阶段②，引擎须已由执行者先按 cell 配置启动）
pool=32/64/80/96 × Graph OFF/ON（以阶段①安全区间为准）：

```bash
SGLANG_PORT=8024 STORAGE_DIR=/data/l3/p2io-gen-<cell> \
  /root/miniconda3/envs/sglang-patch/bin/python /root/gen_load.py \
  --agents 8 --max-new 256 --turns 10 \
  --evidence-dir /root/evidence-gen-<cell>
```

### 产物结构
```
/root/evidence-gen-<cell>/run-<ts>/
  runs.csv            per-request 行（含 completion_tokens/finish_reason/ttft/wall）
  join.log            JSONL 同 runs.csv
  mid-run-metrics.txt {"ts": .., "metrics": {全量阶段②指标快照}} 每 5s
  verdict.json        status/requests_total/completed/generation_tokens_total/avg_wall/elapsed
  turns/agent-N/tN.pNN.{payload.json,headers,body,meta.json}
```

### 如何从产物计算指标（执行者侧）
| 指标 | 计算 |
|------|------|
| 稳态 gen_throughput | mid-run-metrics.txt 中 `sglang:gen_throughput`（=last_gen_throughput, token/s）在批次满载窗口内的中位数；或 `realtime_tokens_total{mode="decode"}` 在稳态窗口的 delta 速率 |
| TPOT | runs.csv：`wall_s / completion_tokens`（prompt 短，prefill 占 wall 可忽略） |
| ITL | `(wall_s - ttft_s) / (completion_tokens - 1)`；引擎逐 token 时间戳可用时直接用 |
| decode batch size | mid-run 中 `num_running_reqs` 稳态水平（引擎 --max-running-requests 8） |
| Mamba slot usage | mid-run 中 `mamba_usage` / `mamba_used_tokens` / `mamba_available_tokens` / `mamba_evictable_tokens`（阶段②核心问题：并发 decode 是否触及 SSM 池容量） |
| Graph passes | `cuda_graph_passes_total{mode="decode_cuda_graph"}` / `{mode="prefill_cuda_graph"}` 窗口增量 → Graph ON 时 decode 步由 CUDA graph 服务的比例 |

---

## open_issues

1. **payload prompt token 数（预估）**：中文 ~40-90 tokens、英文/代码 ~150-220 tokens；因此 prefill 占 wall 少于 ~10%，可近似全 decode，但 TPOT 的 per-request 精度按"短 prompt 近似"处理，最终由 phase 2 执行者的实测 usage.prompt_tokens 校准。
2. **单个 cell 时长估算**：8 agents × 10 turns × max_new=256，若稳态 decode ~100-400 tok/s 且 max_running=8 → ~1.3-4 个请求并发吞吐 ~100-400 tok/s → 8×10×256 ≈ 20480 tokens ≈ 50-200s + 启动开销；max_new=512 翻倍（~1-7 分钟）。`--budget 900`（默认，task 口径）足够覆盖，建议实际跑前用阶段①的实测 decode TPS 重算。
3. **`--stagger` 与批次满载**：锁步（default 0）下第一批 8 请求同时进入 → 批次满载稳态最快到达；若执行者观测到 prefill 风暴（tokenizer 竞态），可加 `--stagger 0.2-0.5` 纯缓解，但 trace 序不变。
4. **gen_throughput 仪器化**：driver 只能采样该 gauge，不能保证它在该引擎的每个 cell 配置下都发射（阶段③/执行者 dry-run 时若缺失，降级用 `realtime_tokens_total{mode=decode}` 全程速率，两种算法规格已在 docstring 写明）。
5. **mid-run 采样窗口**：采样线程在引擎重启/换 cell 期间可能抓空（empty {}），已 try/except 容忍；稳态窗口选取由执行者用多次样本自定。

## 纪律确认
- 远程只新增 `/root/gen_load.py` 与 `/root/gen-payloads/`，未改任何已有文件（引擎源码、gate2_load.py、common.py、gate3_soak.sh、wrapper 引擎参数均未动）。
- 禁止的行为未发生：未 ssh 到 s7070/192.168.20.211/223/k3s；未启动引擎；未跑任何负载/请求（对 8024 仅只读 /metrics 轮询，未发 chat/completions POST）；未占 GPU；未用跨距正则；未用 pkill -f；无 rm / 无破坏性 git。
- 工作集预算内的离线完成；报告已写盘。