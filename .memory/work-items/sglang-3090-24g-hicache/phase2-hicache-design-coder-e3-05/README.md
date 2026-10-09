# phase2-hicache-design-coder-e3-05

- **工作标题：** phase2-hicache-design-coder-e3-05
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-coder-e3-05.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-coder-e3-05.md`：**
- **client 选型 = urllib（stdlib）**：driver-design.md §8 #5 由 05 定，选 urllib 而非 httpx——3090 宿主机无 httpx 依赖保证，urllib 零依赖且 ThreadingHTTPServer 冒烟已验证流式 SSE 解析（readline 循环、HTTPError/URLError/timeout 分支、curl 语义 rc）。进程内 client 替换 udg_client_l3.py 子进程（K 并发子进程 = K×60-80MiB 不可行，§4.1）；产物 meta.json rec 字段与 udg_client_l3 完全同构。
- **轨迹**：TEMPLATE 12 行按 §2.2 规范模板；variant ring = (模板索引 + group) mod 3（R4，K=32/64 同 session 多 agent 错峰）；session 分配 K≤16 一一对应、K>16 按 (aid-1)%16+1 共享（§1.3）；--turns 截断模板（K=64 降载 8）。
- **R3 降级**：阈值 = meta.json service_scope_tokens_est − 32768（L2=2087、L3=10788，与设计冻结值一致，meta 缺失时回退冻结常量）；检查"同 session 最近成功 turn"的 sglext device+host+storage 合计（session 状态共享 + per-session 锁，多 agent 共享前缀竞争语义）；http≠200/finished=false 不更新 session 状态；降级 payload = 本 agent 的 L0-V<ring[0]>（恒可行，R2）。
- **并发模型**：无全局信号量，引擎队列即背压（in-flight=K，running≤8，queue=K−8）；/metrics 拉取全局锁串行化（§4.1）；join 写锁同 micro_qwen35 同构；失败 turn 记 failed 不阻塞循环；超时强制 verdict（status=blocked，rc=2）。
- **dry-run**：容量核算表 5 行（K=1 基线 + 4 个实验 K），device/host/mamba/L3/RAM 数学按 §1.1/§1.3/§4.2，K=64 硬占用 14.4-17.5G < 31G；同时打印轨迹与 payload 存在性校验。
- **schema 一致性自检**（对照 §6.1-§6.3）：join 行字段名/类型/顺序逐一比对（v2 八字段 + v1 全保留 + delta）；level 为 "0".."3" 字符串（模板 "L0" 显示名与 join 字段分离，发现并修复过 level="L0" 的错误）；mid-run-metrics `{"ts": float, "metrics": {name{labels}: int}}`；agent json/runs.csv/verdict 字段与 §6.3 一致（engine_log_path 留空占位由 tester 填）。
- 直方图 _sum 行（float）不注册解析前缀 → 快照保持 int 类型（§6.2），bucket+count 足够 06 做分位数派生。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-coder-e3-05.md`：| 文件 | 变更 | 说明 |
|---|---|---|
| `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/agent_driver.py` | 新建（~590 行） | K agent 线程 + metrics 采样线程 + join 写锁；12-turn 轨迹模板（R1-R5）；join.log v2 行；--dry-run 容量核算表；verdict/runs.csv/agent-<id>.json/END-BANNER |
| `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/common.py` | 新建（~400 行） | micro_qwen35 复用点落地（metrics 快照/delta、extract_sglext、payload 助手、docker_cat/read_probe_events）+ 进程内流式 SSE client（urllib）+ run_request |
| `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/test_local_smoke.py` | 新建（单元测试，mock 引擎） | 本地端到端冒烟：ThreadingHTTPServer 模拟 /health /metrics /v1/chat/completions SSE，20 项断言全过 |…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-coder-e3-05.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-coder-e3-05.md`; SHA256 `b7912a4ccec23814b7633f67186ce007d2a6ff0459e97f8fd19fcf4a072672a2`; source state `tracked`
