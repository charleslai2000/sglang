# HANDOFF — 2026-09-17 — 生产优先 / RTX 3090 DEV+PROD

接管入口。本文档自包含：先读 §1（最高优先级裁定）、§2（当前实况）、§3（生产 blocker），
再按 §6 的下一步执行。所有路径为绝对路径。

---

## 1. OWNER 裁定（最高优先级，覆盖一切与之冲突的排序）

1. **生产优先。**
2. **生产在线期间，DEV provider 不允许上线、不允许占用 GPU。**
3. 端口分工（owner directive，权威文件 `3090-dev/deploy/conf/service.env` 头部注释）：

   | 端口 | 角色 |
   |---|---|
   | **30000** | **PRODUCTION** |
   | **30001** | **DEV provider**（本 session 修正后） |
   | 30164 | TEST / diagnostic |
   | 30165 | GATE HARNESS（reserved，scaffold 拒绝使用） |
   | 30100–30199 | 实验保留区 |

**历史错误（已纠正，勿重犯）**：DEV provider 的 `BIND_PORT` 曾被设为 **30000**（=生产端口），
自 commit `ab59311dcc` 引入起一直如此。已由 `7d08fb26f8` 改为 `30001`。

---

## 2. 当前实况（截至 2026-09-17 16:25 UTC）

| 项 | 状态 |
|---|---|
| GPU RTX 3090 | **空闲**（1 MiB used / 24124 MiB free） |
| 端口 30000 (PROD) | **无监听（DOWN）** |
| 端口 30001 (DEV) | **无监听（DOWN）** |
| 任何 sglang server | **无**（全部已停） |
| canonical lock `/tmp/opencode/gpu-3090.lock` | **陈旧记录**：`owner=supervise-prod-prod-20260917T162230Z-1480769, pid=1481118`，该 pid **已死**（上次生产启动失败后未清理） |
| DEV provider state | `role=free, port=30001, health=down, note=stopped` |
| prod scaffold state | `role=free, state=free, note=supervisor-exit, lock_generation=1` |

**结论：当前无任何服务在线。生产与 DEV 都是 DOWN。**

Repo：`/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`，branch `3090-24g-opt`，
HEAD = **`7d08fb26f8`**（`fix(deploy): separate DEV provider from production port`）。

工作树有 3 个未提交项（本 session 在制品，非污染）：
```
M  .memory/phase2-hicache-design/ledger.md
?? .memory/phase2-hicache-design/work/GGUF-ARTIFACT-PROVENANCE-20260917.md
?? 3090-dev/gates/gguf-sampled-smoke/
```

根锁定/GPU 约定（本机特性，勿推断）：
- 单卡 RTX 3090 24576 MiB，UUID **`GPU-2e3ed202-3655-d919-0a64-259209bc6587`**。
- **NVML index 与 CUDA ordinal 相反**——只能按 UUID pin，绝不用裸 index。
- canonical lock `/tmp/opencode/gpu-3090.lock`（flock + bounded backoff，**绝不 signal/kill 在位者**）。
- GPU 直接持有者：`nvidia-smi` 会显示；跑任何模型前必须先确认无 material holder。

---

## 3. 生产 blocker（三条，都阻塞上线）

> **2026-09-17 17:30 UTC — 本节的重大更正（orchestrator）**
>
> 本节初版把生产 blocker 归因为「workload geometry 让请求一直命中 device/L1」，
> **这是错误归因，且漏掉了首因**。经 owner 指出并对照一手证据复核，正确结论是：
>
> **首要 blocker = 生产候选树本身是过期的、由 scratch 冻结的，不是从 commit 构建的。**
> `/opt/sglang/local-prod-v1.1.2-candidate` 的 `extent_file_backend.py` = `b284ec2a710d2afb`，
> **native/GIL-free writer 引用数 = 0**（`SGLANG_L3_NATIVE_WRITE_PATH` = 0、`native_write` = 0），
> 而 repo HEAD 同文件 = `a5c99fd1cc32b645`、`native_write` = 28。
> 即 §1 要求的 native L3 writer **根本不在这棵树的代码里**，照它上线必然得到假 GREEN。
> 其 `manifest/identity.json` 自述 `source_tree = /tmp/opencode/v1.1.2-optionC-20260917`
> ——**scratch 冻结，非 commit**。这正是 owner §0「禁止从 `/opt`、旧 scratch 跑最终验收」所防的坑。
> 权威记录：`.memory/phase2-hicache-design/work/PROD-TAKEOVER-AUTHORITY-AND-GATE-A-20260917.md`。

### 3.A — 首要：生产候选树过期 / 来源非 commit（必须先解决）

候选树与 repo HEAD 的**真实源码差异仅 3 个文件**（其余全部一致）：

| 文件 | HEAD | 候选树 | 判定 |
|---|---|---|---|
| `srt/mem_cache/storage/extent/extent_file_backend.py` | `a5c99fd1cc32b645`（native_write **28**） | `b284ec2a710d2afb`（native_write **0**） | **候选缺 GIL-free native L3 writer** |
| `srt/models/qwen3_5_text.py` | `d51d5441064c13cb`（含 `4501e59f88` norm-fold） | `c140253b8125df0a` | 候选**早于** norm-fold 修复 |
| `srt/utils/hf_transformers/gguf_native.py` | 同名 hash | 同名 hash | 相同（GGUF，生产范围外） |

**必做**：从**已提交的 commit** 确定性地重建最终候选（不是从 `/opt`、不是从 scratch），
再做最终验收。§4 各项在 HEAD 的提交状态：
WAL/checkpoint 修复 **committed**；native L3 writer（`b26bd39ece`，HEAD 祖先）**committed**；
Option-C relocation（`63f7eff612`）**committed**；`cache_dir=None` **committed**；
final gate harness **committed**；**provider lifecycle（`supervise.sh`）修复尚未提交**（见 3.C）。

**同时**：`/opt/sglang/local-prod-*` 一律只作历史证据，**不得**作为最终验收来源。

### 3.B — Gate A 的 INVALID 已裁定为 **harness bug（H-A）**，非产品缺陷

**权威裁定**：`PROD-TAKEOVER-AUTHORITY-AND-GATE-A-20260917.md` §2。
方法：用 harness **自带的只读 oracle**（`wal_forensics.py --mode membership`）打在
静态 aborted store `/data/l3/phase9-gates-final-20260916/gateA-gateA-20260917T165123Z-1500213`
上，输入是 run 真实的 `prompt_A.json` / `prompt_B.json` id（非日志字符串推断）。

决定性证据（orchestrator 已独立复核，对上一手数据一致）：
1. **零持久丢失**：`drop_slot_frames = {n: 0, slots_dropped: []}`、
   `slot_state_replay.n_drop_slot_frames = 0`（vs `n_set_frames = 93`/`51`）。
   extent store 的 WAL 里**一条 `DROP_SLOT` 帧都没有** ⇒ 从未有已落 L3 的页被删。
2. **graded target 的持久 ref 存在**：prompt A `n_present = 52672`、`first_present_index = 0`、
   head present、`n_runs = 2`（`[0,51200)` + `[63488,64960)`），散布在**全部 52 个 slot**。
3. **drop 告警来自另一层**：`write_back: KV subtree dropped without backup` 出自
   `python/sglang/srt/mem_cache/unified_radix_cache.py:3247`（`_drop_subtree_no_host`），
   是 **device→host 备份失败**路径 = L1 缓存层决策，**不是** extent store，且未移除任何 L3 index 项。
4. **relocation 拒绝是产品正确 fail-closed**：`victim = slot 0`、`live_bytes = 61079552`、
   `relocation_headroom_bytes = 49201152`、`reclaim_relocatable = false`；
   `61079552 > 49201152` ⇒ Option-C 需要一个 victim 之外的 destination，而**测试几何没留**出足够空间。
   失败原因是 `ExtentFileBackend` 的 fail-closed，属正确行为。
5. **filler 从不持久化**：filler 0/1 的 `n_present = 0`。

**结论**：该 INVALID 是 harness artifact —— drop 判据过宽（收集任意
`without backup due to host memory pressure` 行，而 harness README 本意只针对 graded prefix），
且几何把 store 填到接近 100% live、没留 relocation destination。gate **从未跑到** L3/RECOVERED 测量臂。

**owner 已预授权的 harness 修正**（未实施）：
- drop 判据**只绑定 graded target**；filler 标为 disposable（filler 掉落不得 INVALIDate target，
  但**任何 target 页/ref 掉落必须 fail-closed**）；
- 显式**预留 relocation destination**；不要把 store 填到 ~100% live 再要求 relocation 成功；
  也不要靠把 store 做得极大来回避 wrap；
- 几何必须触发 circular reclaim，且 victim slot 持有 target live refs 并有真实 recycle 事件；
- 在**任何测量请求之前**预断言 §3 前置条件：Gate A = target 在 Extent index、DEVICE miss、
  HOST miss、STORAGE-hit candidate、host pool sized；F1 = victim slot id 已知、
  victim 持有 target live refs、relocation destination 容量存在、真实 recycle 事件、
  victim generation 改变、target relocation count > 0。缺任一 ⇒ `INVALID`，且**不烧 GPU**。

### 3.C — final campaign 的 storage-tier 缺失（初版 3.A 的内容，降级为次要）

权威 verdict：`.memory/phase2-hicache-design/work/FINAL-CAMPAIGN-VERDICT-20260917.md`
（终态 `PRODUCTION BLOCKED`，"M1 is NOT GREEN"）。证据目录：
`/var/log/sglang/local-prod-v1.1/phase9-gates-final-20260916/final-campaign-20260917/`

| Gate | 结果 | 原因 |
|---|---|---|
| Gate A | **INVALID** (rc=2) | 内容相等性 HELD，但 L3 臂 `cached_tokens_details={device:64960, storage:0}`；`prefetch_revoke storage_hit=0`。按 owner 硬规则 `storage>0` 必须成立，否则 **INVALID 而非 PASS** |
| Gate A-F1 | **未 exercise** | `sweep.recycle_events=0`，`slot0_recycles=[]`。确定性 wrap 触发没产生 slot recycle |
| F2 | **FAIL** | primer 的 `pre_restart_storage_positive` 失败（`storage=0`，同因） |
| short canary | **PASS** | 32/32，但 `storage_hit=0`、`device_hit=63488` — 同样没走 storage |

**状态更正**：上述 `final-campaign-20260917/`（07:41 run）是**旧几何**下的结果。
**新 r2 run（16:51，`final-campaign-20260917-r2/`）已首次真正走上 L3 storage tier**：
host pool 由 19904 tokens（mis-sized，带 smaller-than-device 警告）修正为
**79615 ≥ required 69096**（无警告）；即 host-pool 修复**已生效**。
r2 的 Gate A 于 16:54 报 `INVALID :: kv subtree dropped without backup ... (7 events) after 16000
filler tokens; the host pool is still mis-sized for the graded...`——该判据即 §3.B 裁定为过宽的那个。
故 r2 亦**未**跑到 L3/RECOVERED 臂；按 §3.B 修 harness 后重跑。

参考：owner 的 R2 明令——**不单独跑 GPU 验证 job**；下一次真实 final Gate A/F1/F2 campaign
**本身就是** post-fix harness 的 E2E 验证。结果必须携带修复后 harness 的证据字段
（`hc_size_gb` 或等价、确定性 unique-prefix seed、strict flush、F1 victim/generation/relocation），
**缺新字段即 INVALID / wrong harness identity**。

### 3.D — 生产 scaffold 的 supervisor 时序竞态（本 session 首次真实启动才暴露；**已修，未提交**）

**事实**：`/tmp/opencode/prod-service-20260917/` 这份生产 scaffold 是 **SCAFFOLD ONLY**
（其 README 自述 "No server was started"）。本 session 于 16:22:09 做了**首次真实启动尝试**，
preflight PASS 后在 supervisor 阶段失败。

**失败现象**（日志：`/tmp/opencode/prod-service-20260917/logs/prod-20260917T162230Z-1480769/supervisor.log`）：
```
[16:23:41] canonical GPU lock ACQUIRED generation=1 owner=supervise-prod-... pid=1481118
[16:23:41] supervisor launching prod on port 30000 (tree=/opt/sglang/local-prod-v1.1.2-candidate)
[16:23:44] /proc/1481569/environ PYTHONPATH= CUDA_VISIBLE_DEVICES=
[16:23:44] FATAL: runtime PYTHONPATH not inside tree: '' 1
[16:23:44] WARN: supervisor exiting rc=1; releasing GPU lock
```
（同一 console 里另有 `libavutil.so.56` / libtorchcodec 的告警，那是已知的良性噪声，**不是**本失败因。）

**根因（已定位，已修但未提交）**：`bin/supervise.sh` 与 launcher 的时序竞态。
- `supervise.sh:51` `SERVER_PID=$!` 拿到的是 `setsid env ... bash launch.sh` 的 PID。
- `supervise.sh:63` 只 `sleep 3`，随后读 `/proc/$SERVER_PID/environ` 的 `PYTHONPATH`。
- 但 `launcher/launch.sh:69` 的 `export PYTHONPATH=...` 是 **bash 变量导出，不会更新
  `/proc/<bash-pid>/environ`**；只有到 `launch.sh:180` 的 `exec "$PY" ...` 时，进程映象才替换、
  environ 才带上 PYTHONPATH。
- 而 `launch.sh` 在 `exec` **之前**要先跑 fail-closed identity gate（tree hash ~7 s + import ~10 s，
  `launch.sh:97`），合计约 **17–20 s**。
- 因此 3 s 时读到的 `PYTHONPATH` 为空 => supervisor 误判 FATAL，服务被杀。

**修复状态（2026-09-17 16:57 复核）：已修，但尚未提交 git。**
`3090-dev/deploy/bin/supervise.sh` 与 `3090-dev/tools/prod-service/bin/supervise.sh` 均已改为
**有界轮询**（56→ `PROC_PYTHONPATH=""` 初始化 + 轮询至非空且位于 `$TREE/src/python` 内；
`ENV_POLL_TIMEOUT_S` 超时仍 fail-closed；两条 identity 断言逐字保留）。各 +40/-6。
已由 CPU rig 验证：`bash -n` rc=0、**OLD-fails / NEW-passes / timeout-failclosed / happy-path 不变**。
**待办：把该修复提交进 `3090-24g-opt`**（生产必须先有已提交的 provider lifecycle 修复）。
**注意不要放宽 identity gate 本身。**

**注意**：不要为了绕过它而直接手工 `launch_server`——launcher 自带 fail-closed source-identity gate，
且它自己会设置 PYTHONPATH；直接调用会踩 editable-install 地雷（见 §5）。

---

## 4. 另一条独立线（bake-off；与生产争同一张卡，需排序）

目标：四模型 bake-off —— M1 Qwen3.5-9B W4A16 / M2 OmniCoder-9B GPTQ-INT4 /
M3 Qwen3.8-27B IQ3_S GGUF / M4 Swift-Qwen3.8-27B Q3_K_M GGUF，跑同一 compute/eval contract。
按 owner 裁定 **A+B 顺序执行**（先修 GGUF runtime 正确性，再评估），且 **M4 先、M3 后**。

### 4.A — GGUF 退化的**决定性根因（本 session 新发现，已双重取证）**

**结论：GGUF tokenizer 的 special-token id 冲突。SGLang 把对话回合标记编码到了模型里的 PAD 行。**

证据 1（离线判别，`/tmp/opencode/gguf-residual-diag-20260917/evidence_DECISIVE_m4.txt`）：
```
渲染后的 prompt 字符串与 llama.cpp --jinja 完全一致：
  '<|im_start|>user\n...<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
SGLang 实际送出的 token ids 含：[248294, ..., 248295, 198, 248294, ...]
模型实际看到的（按 GGUF 语义解码）：
  '[PAD248294]user...them.[PAD248295]\n[PAD248294]assistant\n<think>\n\n</think>\n\n'
正确的 GGUF id：<|im_start|>=248045  <|im_end|>=248046  <|endoftext|>=248044
SGLang 编码：encode('<|im_start|>')=[248294]、encode('<|im_end|>')=[248295]
```

证据 2（orchestrator 直接读 GGUF 元数据，独立复核）：
```
id 248044 = '<|endoftext|>'      id 248045 = '<|im_start|>'      id 248046 = '<|im_end|>'
id 248293 = '[PAD248293]'        id 248294 = '[PAD248294]'       id 248295 = '[PAD248295]'
id 248068 = '<think>'            id 248069 = '</think>'
id 248058 = '<tool_call>'        id 248059 = '</tool_call>'
vocab size = 248320
```

**为什么这解释了全部现象**：
- 模型收到的是 `[PAD248294]` 而非 `<|im_start|>`、`[PAD248295]` 而非 `<|im_end|>`
  => 回合结构对模型完全无效 => 重复循环、`</think>` 泄漏到 content、tool_calls 缺失。
- 同时也解释了 `<think>`/`</think>` 被拆成普通文本 token（`encode('<think>')=[13314,741,29]`
  而 GGUF 单 id 是 248068），以及 thinking-off 仍出现游离 `</think>`。
- 与 criterion 2（短确定性语义）在 greedy 臂同样失败一致：**与采样值无关**。
- **llama.cpp 连贯**（M4 loop_w4=0.0552、M3=0.1029）正是因为 llama.cpp 用 GGUF 自己的
  id（248045/248046）。=> 这**不是** GGUF/量化本身的问题，是 SGLang 的 GGUF tokenizer 绑定问题。

**修复范围（未实施）**：GGUF 模型的 tokenizer 必须把 special/added tokens 绑定到 **GGUF 词表
自身的 id**（248045/248046/248044/248068/248069/248058/248059…），而不是 HF tokenizer 自动分配
的 id（248294/248295/248293…，那些位置在 GGUF 里是 `[PAD*]`）。
相关：`python/sglang/srt/utils/hf_transformers/gguf_native.py`、
`python/sglang/srt/utils/hf_transformers/tokenizer.py`、model 的 chat template 路径。
**注意**：已提交的 `4501e59f88`（norm inverse-fold）是**另一个、独立且仍然正确**的修复；
它已由 CPU 单测验证并被正式提交，不要回退。

### 4.B — bake-off 的既有已验证成果（勿丢弃）

- `4501e59f88` — GGUF GemmaRMSNorm 逆折叠（isolated correctness commit，2 文件，测试 6 passed，
  HF 路径 inert）。已在 `3090-24g-opt`。
- sampled-contract gate 已建好并经 CPU 验证：
  `3090-dev/gates/gguf-sampled-smoke/`（`server_harness_sampled.py`、`run_sampled_smoke.sh`、
  `README.md`、`llamacpp-discriminator.md`、`cpu_smoke.out.json`）。
  其 `_ngram_analysis` 与旧审计 harness **逐字节相同**（loop_w4 数值可比）。
- 正确采样契约（来自两 GGUF 的 `general.sampling.*` 元数据）：
  `temp=1.0, top_p=0.95, top_k=20, min_p=0.0`（M4 另有 `penalty_repeat=1.0`）。
  **旧的 "sampled 也修不好" 证据用的是 0.7/0.8/20 —— 取值错误，勿引用。**
- CPU-only llama.cpp 判别器已建好：
  `/mnt/data/nerun-dev/llamacpp-discriminator-20260917/llama.cpp/build-cpu/bin/llama-cli`
  （commit `b49650adb31f2e49a0d76113aeb1792134fd8413`，无 CUDA 库）。
- E 的完整证据：`/mnt/data/nerun-dev/gguf-sampled-smoke-20260917/{runs,discriminator}/`。
- M3 artifact 已在盘（无需下载）：`/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`，
  sha256 `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810`，
  provenance `ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF` @ `d562806dbafae37109975e970aae91b43e73b440`。
- IQ3 MMQ 优化**继续 HOLD**（须待 M3 语义正确性 PASS）。
- 四模型 common compute matrix 继续 gated 在 GGUF correctness 之后。

---

## 5. 关键地雷 / 约定（违反会浪费大量时间）

1. **editable-install 地雷**：venv `/home/ubuntu/venvs/sglang-3090` 里有
   `__editable___sglang_*_finder.py` 把 `sglang` 映射到 repo 工作树。任何启动**必须**先证明
   `sglang.__file__` 在指定树内 + `/proc/<pid>/environ` 的 PYTHONPATH 正确，否则读的是错代码。
   生产 launcher 自带该 fail-closed gate（`launch.sh:9-19`）。
2. **STORE NAMESPACE**：one task/run → one unique L3 store namespace。
   共享 store `/data/l3/local-prod-v1.1` **只读、绝不 clear**。PRODUCTION 必须走
   `bin/start.sh prod`（它用 tree 自带 policy 工具分配每-run 唯一 namespace）。
3. **`/opt/sglang/local-prod-v1.1.2-candidate` 不是有效生产来源（见 §3.A）**：
   它自述 `source_tree = /tmp/opencode/v1.1.2-optionC-20260917`（scratch 冻结），
   且 `extent_file_backend.py` 缺 native writer（0 引用）。
   其 digest `cf32a429…` / launcher `6e57bc57…` 只是**这棵过期树**的自洽身份，
   `preflight.sh` 对它报 PASS **不代表**它可作为最终验收来源。最终候选必须**从 commit 重建**。
   `/opt/local-prod-*` 一律只作历史证据。
4. **AUTH**：owner 裁定私网 LAN 不需 API key ⇒ AUTH OFF 可接受；launch path **不得**传 `--api-key`。
5. **不要用 `pkill -f`**；不要 signal 你不拥有的进程；停服务只用其自带脚本。
6. **/tmp 可弃**；`/var/log/sglang` 只读参考；大工件放 `/mnt/data`（NVMe）。

---

## 6. 下一步（按优先级）

**P0（生产优先）**
1. 清理陈旧 lock 记录（`/tmp/opencode/gpu-3090.lock` 的 pid 1481118 已死）——
   确认无 flock 实际持有者后再动该文件。
2. **把已完成的 provider lifecycle 修复（`supervise.sh` 有界轮询）提交进 `3090-24g-opt`**
   （§3.D；工作树里已修、已验证，仅未提交）。
3. **从已提交的 commit 确定性地重建最终生产候选**（§3.A）——不得从 `/opt`、不得从 scratch。
   必须含：native L3 writer（`b26bd39ece`）、Option-C relocation（`63f7eff612`）、
   norm-fold（`4501e59f88`）、`cache_dir=None`、WAL checkpoint、已提交的 gate harness 与 supervise 修复。
4. 按 §3.B 的 owner 预授权修正 harness（drop 判据只绑 graded target + 预留 relocation destination +
   recycle 几何 + 测量前预断言）。
5. 跑**一次** final campaign：
   `DEV provider-stop`（确认 GPU/端口清空）→ 用**新重建的**候选 →
   Gate A / F1 / F2（+ 已授权范围内的 native 128K Gate-B）→ short canary →
   **GREEN 则保持 PRODUCTION UP on 30000，DEV 保持 DOWN**；否则两者皆 DOWN 并报唯一 blocker。
6. 生产验证：`/health` 200、`/v1/models`、一次真实 `/v1/chat/completions` 200。

**P1（bake-off，需 GPU 时按 `provider-stop → lock → 实验 → release → provider-start`）**
7. 按 §4.A 修 GGUF tokenizer 的 special-token id 绑定（**已在进行**：工作树
   `python/sglang/srt/utils/hf_transformers/gguf_native.py` 已改 +22/-4、
   `test/registered/unit/utils/test_gguf_native_tokenizer_ids.py` 已建）→ 重跑
   `3090-dev/gates/gguf-sampled-smoke/`（M4 先、M3 后，port 30165）。
8. GGUF correctness PASS 后，再评估 IQ3 MMQ A/B（M4 为 control）。
9. 然后四模型 common compute matrix → SWE R1 → Top-2 long-context fleet。

> **更权威的当前台账**：`.memory/phase2-hicache-design/work/EPOCH-RESUME-20260917-R2.md`
> 记录了 R2 session 的一手复验结果与 W1–W5 活跃工作。若与本文件冲突，以该文件为准。

**报告格式（owner 要求）**
```
NORM_FOLD_COMMIT= / M4_SAMPLED_LONGFORM= / M3_SAMPLED_LONGFORM= / GGUF_CORRECTNESS=
LLAMACPP_DISCRIMINATOR= / IQ3_MMQ_STATUS= / M2_SMOKE= / M3_ARTIFACT= / NEXT_GPU_SLOT=
```
生产线另有：`PRODUCTION_CAMPAIGN / GATE_A / F1 / F2 / CANARY / PRODUCTION_SERVICE /
PROD_HEALTH / DEV_AFTER / SINGLE_BLOCKER`。

---

## 7. 权威文件索引

| 用途 | 路径 |
|---|---|
| 持久 ledger（append-only，接管必读） | `.memory/phase2-hicache-design/ledger.md` |
| 上下文/计划 | `.memory/phase2-hicache-design/{context.md,plan.md}` |
| 生产 verdict | `.memory/phase2-hicache-design/work/FINAL-CAMPAIGN-VERDICT-20260917.md` |
| owner 端口/调度裁定 | `.memory/phase2-hicache-design/work/OWNER-RULINGS-HARNESS-AND-GPU-SCHEDULE-20260917.md` |
| GGUF provenance | `.memory/phase2-hicache-design/work/GGUF-ARTIFACT-PROVENANCE-20260917.md` |
| 生产 scaffold | `/tmp/opencode/prod-service-20260917/`（`bin/`, `conf/service.env`） |
| DEV provider 脚本 | `3090-dev/deploy/`（`provider-start/stop/status`、`conf/provider.env`） |
| sampled gate | `3090-dev/gates/gguf-sampled-smoke/` |
| GGUF 根因证据 | `/tmp/opencode/gguf-residual-diag-20260917/evidence_DECISIVE_m4.txt` |
| E 的 GPU 证据 | `/mnt/data/nerun-dev/gguf-sampled-smoke-20260917/` |
| 128K-C8 profile 证据 | `/mnt/data/nerun-dev/c8-profile-20260917/` |
| llama.cpp 判别器 | `/mnt/data/nerun-dev/llamacpp-discriminator-20260917/` |
| 冻结候选 | `/opt/sglang/local-prod-v1.1.2-candidate`（只读） |

---

_本文档由 orchestrator 于 2026-09-17 撰写，依据一手取证（非仅采信子 agent 报告）。
未提交 git；如需固化请显式 `git add` 本文档路径后提交。_
