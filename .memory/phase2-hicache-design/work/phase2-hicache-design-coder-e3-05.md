# P2-0-05 N-agent driver 实现报告（coder e3-05）

## status

done

## artifacts

| 文件 | 变更 | 说明 |
|---|---|---|
| `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/agent_driver.py` | 新建（~590 行） | K agent 线程 + metrics 采样线程 + join 写锁；12-turn 轨迹模板（R1-R5）；join.log v2 行；--dry-run 容量核算表；verdict/runs.csv/agent-<id>.json/END-BANNER |
| `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/common.py` | 新建（~400 行） | micro_qwen35 复用点落地（metrics 快照/delta、extract_sglext、payload 助手、docker_cat/read_probe_events）+ 进程内流式 SSE client（urllib）+ run_request |
| `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/test_local_smoke.py` | 新建（单元测试，mock 引擎） | 本地端到端冒烟：ThreadingHTTPServer 模拟 /health /metrics /v1/chat/completions SSE，20 项断言全过 |

实现规格唯一依据 driver-design.md 已全读；9 个复用点映射按 §4.3 落地：
#1 BASE/SGLANG_PORT → common.py:54-57；#2 metrics 五函数+清单 → common.py METRIC_CUM/GAUGE/HIST + 函数（扩展 R8/R9/R10/R12a）；#3 extract_sglext → common.py:188-242；#4 payload_est_tokens → common.py:259-268（+payload_attrs）；#5 write_join_row → agent_driver.py v2 扩展；#6 docker_cat/read_probe_events → common.py:381-423；#7 run_dir/turns_dir/join_fh/join_lock → agent_driver.py main；#8 parse_args → agent_driver.py（增量 --agents/--turns/--stagger/--snapshot-interval/--final-chain-check）；#9 verdict/runs.csv/END-BANNER → agent_driver.py 扩展 agent 维度；"改"（子进程 client → 进程内 SSE）→ common.py run_client_inproc；"弃"（triple-state 状态机）→ 未移植。

## evidence

- `python3 -m py_compile common.py agent_driver.py test_local_smoke.py` → exit 0（三文件）。
- `python3 agent_driver.py --dry-run`（及 --agents 8/32/64）→ exit 0，输出容量核算表（K=1/8/16/32/64 五行的 agents/session、turns、in-flight、queue、L3 驻留域、budget、client-max、RAM 核算 14.2-17.5G < 31G、verdict）+ 12-turn 轨迹（t1 grow L0-V1 冷启动 → t3/t4/t9/t11 R3 条件 turn 带阈值 2087/10788 → t5/t8/t12 restore）——不连引擎。
- `python3 test_local_smoke.py`（mock SSE 引擎，本地，无真实引擎）→ **20/20 断言 PASS**：
  - 冷 mock（cached=0）：join.log 12 行（2 agents×6 turns），4 个 downgrade 行（t3/t4）payload=同 session L0-V1、level="0"、new_tokens_est==prompt_len；warm mock（cached=prompt）0 downgrade；
  - 全部行含 v2 字段 agent_id/turn/turn_kind/phase/session/level/variant/ts_sched/new_tokens_est + v1 字段全保留 + delta 字典；phase 按 turn 序 t1-4=warmup/t5=steady/t6=drain；tag=a<id>-t<turn>-<kind>；http=200/finished=true；rid=mock-N（body id，header x-request-id 也可用）；
  - mid-run-metrics.txt JSONL 行 {ts, metrics}，含 num_running_reqs/kv_used/kv_available/mamba_evictable/max_total 等 gauge + load_back_duration_seconds_bucket/count 直方图行；
  - agent-1.json（turns_total/completed/failed/downgraded/intervals 序列/session/group/variant_ring）、runs.csv 表头与 §6.3 一致、verdict.json（agents=2/turns_per_agent=6/requests_total=12/requests_failed=0/status=done/blocked=None）、END-BANNER.txt 均落盘；
  - turns 产物命名 `turns/agent-<id>/t<turn>.<kind>.{body,headers,meta.json,payload.json}` 与 §6.3 一致。
- 自检扫描：无 TODO/FIXME/XXX/HACK；无 `import re`/跨距正则（grep 命中均为 "backpressure."/"before.get" 子串误报）；无硬编码密钥；唯一 print 为 log() 与 dry-run 输出。

## summary

- **client 选型 = urllib（stdlib）**：driver-design.md §8 #5 由 05 定，选 urllib 而非 httpx——3090 宿主机无 httpx 依赖保证，urllib 零依赖且 ThreadingHTTPServer 冒烟已验证流式 SSE 解析（readline 循环、HTTPError/URLError/timeout 分支、curl 语义 rc）。进程内 client 替换 udg_client_l3.py 子进程（K 并发子进程 = K×60-80MiB 不可行，§4.1）；产物 meta.json rec 字段与 udg_client_l3 完全同构。
- **轨迹**：TEMPLATE 12 行按 §2.2 规范模板；variant ring = (模板索引 + group) mod 3（R4，K=32/64 同 session 多 agent 错峰）；session 分配 K≤16 一一对应、K>16 按 (aid-1)%16+1 共享（§1.3）；--turns 截断模板（K=64 降载 8）。
- **R3 降级**：阈值 = meta.json service_scope_tokens_est − 32768（L2=2087、L3=10788，与设计冻结值一致，meta 缺失时回退冻结常量）；检查"同 session 最近成功 turn"的 sglext device+host+storage 合计（session 状态共享 + per-session 锁，多 agent 共享前缀竞争语义）；http≠200/finished=false 不更新 session 状态；降级 payload = 本 agent 的 L0-V<ring[0]>（恒可行，R2）。
- **并发模型**：无全局信号量，引擎队列即背压（in-flight=K，running≤8，queue=K−8）；/metrics 拉取全局锁串行化（§4.1）；join 写锁同 micro_qwen35 同构；失败 turn 记 failed 不阻塞循环；超时强制 verdict（status=blocked，rc=2）。
- **dry-run**：容量核算表 5 行（K=1 基线 + 4 个实验 K），device/host/mamba/L3/RAM 数学按 §1.1/§1.3/§4.2，K=64 硬占用 14.4-17.5G < 31G；同时打印轨迹与 payload 存在性校验。
- **schema 一致性自检**（对照 §6.1-§6.3）：join 行字段名/类型/顺序逐一比对（v2 八字段 + v1 全保留 + delta）；level 为 "0".."3" 字符串（模板 "L0" 显示名与 join 字段分离，发现并修复过 level="L0" 的错误）；mid-run-metrics `{"ts": float, "metrics": {name{labels}: int}}`；agent json/runs.csv/verdict 字段与 §6.3 一致（engine_log_path 留空占位由 tester 填）。
- 直方图 _sum 行（float）不注册解析前缀 → 快照保持 int 类型（§6.2），bucket+count 足够 06 做分位数派生。

## followups

- p2-0-07（tester）K=2 引擎 smoke 注意点：
  1. 首跑前先验 open issue 4：单发 1 个 L2 冷请求看引擎行为（挂起 vs 拒绝 vs 分块）——若拒绝而非挂起，R3 降级可放宽（设计 §8 #4）；driver 已按 R3 默认降级路径实现，不受影响。
  2. 引擎日志由 tester 存盘（driver 不读引擎日志，§7 ④）；driver 只记录 b15/t38c 探针可读性（--probe-container 默认 sglang-l3-3090，--no-probe 可关）。
  3. 证据目录默认 /root/evidence-p2b0-01（tester 以 root 写，§6.3）；K=16/32 用 --evidence-dir /root/evidence-p2b0-02，K=64 用 03。
  4. --final-chain-check 默认关；K=1 基线跑时开（chain_check --expect-mamba 硬编码 3090 hybrid 语义，exit 4 接受）。
  5. auto budget/client-max 按 §2.3 表（K=2 → 取 K=8 档 3600s/580s）；K=64 若超时用 --turns 8 降载。
  6. join 行 rid = header x-request-id 优先、body id 回退（T14a 语义）；b15 探针 pa_lb_init 关联按 rid，pb_load_done 无 rid 按 ts 序+n_tokens 推断（§7 已知缺口）。
  7. 与 Phase-1 证据同口径对照：t38rs3 cached=20864/storage=20855/input_delta=47 在 K=1 跑对应 turn 5/8/12（restore L0）行。
- p2-0-06（collect_metrics.py）：join.log v2 行直接 json.loads 即可；mid-run-metrics _sum 行不存在（有意排除）；K≥8 的 per-turn delta 有并发叠加（§6.1 注记），per-request 精确量用 sglext 派生（new_tokens_est/三档 hit）。

## open_issues

- ttft_s 口径微差：进程内 client 的 ttft = 首个含 choices/usage chunk 到达时刻（curl 的 time_starttransfer 是首字节时刻）——同数量级，K=1 对照时注意（设计未要求 curl 级兼容）。
- size_download 为 body 行字节和（近似 curl %{size_download}），无下游使用。
- p2-0-05 验收中的 "K=2 smoke → join.log ≥4 行" 由本任务的 mock 测试覆盖（12 行），真实引擎端到端验证归 p2-0-07。
- /tmp/ev-check 与 /tmp/dryrun8.txt 为本地验证临时文件（不在交付物内）；p2-0/__pycache__ 为 py_compile 副产物。
