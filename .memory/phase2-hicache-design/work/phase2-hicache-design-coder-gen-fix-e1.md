# Phase-2 p32-c4 gen_load non-SSE parse fix — coder report

## status: done

任务：修复阶段② gen driver（`/root/gen_load.py` + `/root/p2-0/common.py`）的 non-SSE 解析 bug，
并在 runner 实机重跑 p32-c4-verify 验证。仅改 driver 侧，未动引擎 .py / wrapper 参数 / 现有负载。

---

## 改动点

### `/root/p2-0/common.py`（`run_client_inproc` 增加 non-SSE 分支）
- 新增共享解析辅助 **`parse_completion(rec, obj)`**：把单个 chat.completion JSON 对象折叠进 rec
  （usage / finish_reason / message.content → `content`、message.reasoning_content → `reasoning`、
  logprobs / request_id）；SSE chunk 与 non-SSE 整包共用同一代码路径（无重复逻辑）。
- 新增 **`parse_non_streaming(rec, text, t0)`**：non-SSE 分支。`json.loads` 整个 body，
  填 `usage`（prompt_tokens/completion_tokens）、`finish_reason`、
  `content`/`reasoning_content`、`finished`（finish_reason 非空或 choices 存在）、
  `ttft_s`（= 首次收到完整 body 的时间 - t0）。返回 True/False。
- `run_client_inproc` 读取循环：SSE 路径不变（`data:` 行判断保留）；增加 `saw_done` 标记；
  读取结束后 `if rc == 0 and not saw_done: parse_non_streaming(rec, blob, t0)`。
- 两处守护修复（SSE 与 non-SSE 共用，防退回归）：
  - `rec["ttft_s"] = t_first` 只在 `t_first is not None` 时覆盖（否则 non-SSE 分支已填的
    ttft_s 会被 None 覆盖 —— 被 TDD 测试抓到）。
  - `rec["request_id"] = _header_rid(...) or body_id` 只在 `rec["request_id"] is None` 时覆盖
    （否则 non-SSE 分支从 body id 填的 request_id 会被 headers 的 None 覆盖）。
- SSE 累计增加流重启保护：出现新 request id（id_changed）时清零旧窗口（stream_options /
  chat-template 重启场景）；对 `delta`/`message` 分支的类型判断修正（`or {}` shim 会绕过
  isinstance —— 也被 TDD 测试抓到）；logprobs 增加 `delta.logprobs` 回退。

### `/root/gen_load.py`（可选优化，同步做了）
- `inject_max_tokens` 现在显式注入 `"stream": False`：让引擎侧响应**确定非流式**
  （body 是单个 chat.completion 对象），配合 common.py 的 non-SSE 解析分支双保险。
- `_row` 的 `rid` 字段增加 `or meta.get("request_id")` 回退：non-SSE 的 request_id 在
  meta 里（body id），但 sx（extract_sglext 只扫 `data:` 行）拿不到 → runs.csv 的 rid 补全。
  （第一版验证已抓到此缺口：runs.csv rid 全空；更新后 40/40 非空。）

### 未改动
引擎源码 .py、`/root/gate2_load.py`、`/root/gate3_soak.sh`、wrapper 引擎参数
（`direct-launch-sweep-p32-gON.sh` 等）均未动。原始文件已备份：
`/root/p2-0/common.py.bak-p32c4-20260905-104212`（17118B，md5 与 git/远程原版一致）、
`/root/gen_load.py.bak-p32c4-20260905-104313`。

### py_compile 结果
- 本地（本机）：`python3 -m py_compile common.py gen_load.py` → rc=0
- 远程 runner（sglang-patch env）：`/root/miniconda3/envs/sglang-patch/bin/python -m py_compile /root/p2-0/common.py /root/gen_load.py` → rc=0（REMOTE_PY_COMPILE_OK）
- 远程 gen_load 静态 dry-run：`DRY_RUN_OK payloads=16 max_new=256 agents=4 turns=10` rc=0
- 部署校验：本地/远程 md5 逐字节一致
  - common.py = `9a96af05f2a0b32f9ee7e9e304e78e33`
  - gen_load.py = `cdf6b7b92451dd9a7c685a92bad7807d`

---

## TDD（本地 + runner 实机，均 GREEN）

测试脚本 `/tmp/test_nonsse.py`（本轮新建，非交付物，仅验证用）：
- **RED（修复前）**：`run_client_inproc` 对着真实证据 body
  `/root/evidence-gen-p32-c4/run-20260905-102043/turns/agent-1/t1.p01.body` → finished=False
  / usage=None / ttft_s=None / content=""（用 mock HTTP server 回放该 body，逐字段断言全部失败）。
- **GREEN（修复后）**：同一回放 → finished=True、usage.completion_tokens=256、
  finish_reason=length、ttft_s 为 float、reasoning 以 "Thinking Process:" 开头、
  request_id=body id。SSE 对称路径 + 流重启清零 + logprobs + extract_sglext 读回全部断言通过。
- 在 runner 上同样跑通（`TDD_GREEN_OK`，sglang-patch python，对着真实证据文件）。
- 原有 SSE 冒烟测试（`/root/p2-0/test_local_smoke.py`，mock SSE 引擎 + agent_driver 全流程）：
  本机 /root/p2-0 镜像下执行 → `RESULT: 0 checks failed`（RESULT: 0 checks failed，SSE 路径零回归）。

---

## 实机验证 p32-c4-verify（ns_ 命名空间，未污染正式证据）

### 运行环境
- 目标机 `175.155.64.171:24052`，RTX3090，GPU 空闲（15 MiB / 0%）、无引擎进程、8024 空闲。
- 引擎：`/root/direct-launch-sweep-p32-gON.sh`（已有 PATH fix：
  `export PATH="/root/miniconda3/envs/sglang-patch/bin:$PATH"` 在 exec 前）→ 启动后 /health 200。
- 环境：`MAX_SIZE=64G SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE=96G STORAGE_DIR=/data/l3/p2io-gen-p32-c4-verify L3_BACKEND=extent SGLANG_PORT=8024`。

### 第一遍（common.py 修复后，gen_load rid 修复前）
- `run-20260905-104615`：`GEN_DRIVER_DONE requests=40 completed=40 gen_tokens=10240`
  rc=0（driver.log）。
- verdict.json：requests_total=40、requests_completed=40、generation_tokens_total=10240、
  elapsed_s=32.3、avg_wall_s=3.05。
- runs.csv 40 行全部：finished=True、finish_reason=length、completion_tokens=256、
  ttft_s≈3.0s 非空、http=200、prompt_len 有值。
- 发现缺口：runs.csv 的 rid 列全空（meta 有 request_id=body id，但 _row 只取 sx.rid）→ 修复 gen_load `_row`。

### 第二遍（gen_load rid 修复后，最终验证）
- `run-20260905-105003`：`GEN_DRIVER_DONE requests=40 completed=40 gen_tokens=10240` rc=0。
- 全量断言（runner 上 python 脚本逐条）：
  - rows=40；all finished=True；all completion_tokens>0；all ttft_s 非空；all http=200；
    finish_reason 全为 length；**rid 非空 40/40**。
  - verdict：40/40/10240。
  - **40/40 个 `.body` 均为合法完整 JSON**（含 choices 与 usage），`t1.p01.body` 的
    usage.completion_tokens=256 —— `.body` 仍是完整 JSON，未被破坏。
  - join.log 40 行；mid-run-metrics.txt 8 个采样快照。
- mid-run 阶段②指标已采集（之前 shell 转义问题致显示 None，实为键带 label 已存在）：
  首个采样 `realtime_tokens_total{mode="decode"}=10250`（≈10240 生成 + 预热）、
  `prefill_effective_tokens_total{mode="input"}=1953`、`cuda_graph_passes_total{mode="decode_cuda_graph"}=2570`
  （Graph ON 的 decode 步）、`mamba_usage/used/available/evictable`、`num_running_reqs` 均在快照内。

### 收尾
- SIGTERM 引擎主进程（PID 412036，按 PID kill，未使用 pkill -f）→ 25s 后确认：
  无 engine/driver 进程残留、8024 释放、GPU 回到 15 MiB / 0%。
- 验证期间未跑其他 cell、未动正式证据目录。

---

## 结论

**gen_tokens=10240 > 0（40/40 请求完成，completion_tokens=256/每请求，ttft_s 全非空），
阶段② p32-c4 已验证可产生 decode 生成 —— 后续 8 个 cell 可续跑。**

即：`/root/p2-0/common.py` 的非 SSE 解析分支 + `/root/gen_load.py` 的 `stream:false` +
rid 回退已使驱动在引擎 non-SSE 响应下正确解析 usage/finish_reason/content/ttft_s/finished，
runs.csv 与 verdict.json 数据完备。

## followups
- 正式 p32-c4（及后续 cell）续跑命令按任务原始口径：
  `SGLANG_PORT=8024 STORAGE_DIR=/data/l3/p2io-gen-p32-c4 <py> /root/gen_load.py --agents 4 --max-new 256 --turns 10 --budget 900 --evidence-dir /root/evidence-gen-p32-c4`
  （引擎由执行者按 cell 配置启动；runner 现状：引擎已停、GPU 空闲）

## open_issues
1. **mid-run 采样中的 `gen_throughput` gauge 在该引擎此配置下恒为 0**（`gen_throughput{...}=0`，
   全采样快照均 0）。原因可能是引擎只在特定批满载窗口才发射 last_gen_throughput，或该字段未
   随 decode 更新。阶段②执行者计算稳态 gen_throughput 时应降级使用
   `realtime_tokens_total{mode="decode"}` 的窗口 delta（8 个采样点 5s 间隔，decode_total 从 0→10250）。
   这与 gen_load.py docstring 里已写的降级规则一致，不阻塞 cell 续跑。
2. **`num_running_reqs` 采样值在 4 agents × 256 tokens 下偏小**（本 cell decode 并发低，
   max-running=8 未被打满）。这不影响本修复；执行者评估 Mamba slot 压力时以正式 cell
   （conc 6/8）的采样为准。
3. **本验证只覆盖 non-SSE 解析路径的正确性**；引擎响应的 SSE 路径行为未在本轮实测触发
   （`stream:false` 后请求确定非流式）。若后续某 cell 需要流式请求，common.py 的原 SSE
   逻辑已被 smoke test 覆盖无回归。
4. **prefill_effective 计数含 label 全键**（`engine_type/.../tp_rank`），执行者抽取指标时需用
   `common.select_metric(..., label_contains='mode="input"')` 风格，或直接用快照全键。