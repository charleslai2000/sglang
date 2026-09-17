# 精准目录与源码清单 — 2026-09-17 10:35Z

## 0. 结论先行
我的工作目录**一直是正确的**:
`/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`(git repo),`.memory/` 就在 repo 内
(421 个已 tracked,64 个未提交)。

**但存在一个真实的治理缺口**:生产源码有 25 个文件与 repo HEAD 不同,其中 **9 个补丁只存在于
`/opt/sglang/**` 冻结树** —— 任何 git 分支都没有,工作树也没有。

---

## 1. THE REPO(唯一 repo,我的工作目录)
```
path      /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt
branch    3090-24g-opt @ ad749d6f28 (2026-09-16 04:33 +0800)
remotes   origin   git@github.com:charleslai2000/sglang.git
          upstream git@github.com:sgl-project/sglang.git
worktrees 仅此一个
.memory   421 tracked / 64 uncommitted
worktree  8 modified files (+1745/-82) + 66 untracked entries
size      2.3G
```

## 2. `/home/ubuntu/workspaces`(你指定的起点)—— 只有两个子目录
```
/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt   <- THE REPO
/home/ubuntu/workspaces/local-prod-baseline-v1/testlib  <- vendored pytest,无 .git,不是 sglang 树
```
**没有其他东西。** 之前我说"好多乱七八糟的目录"是把 `/home/ubuntu` 顶层当成了 workspaces —— 那些
(`sglang/`, `models/`, `venv/`, `build-aot/`, `fc-src/`, `wheels/`, `sglang-run/`)是**宿主预置**,
不在 workspaces 里。

## 3. 生产产物(在 /opt,不在 repo)
```
/opt/sglang/local-prod-v1              LOCAL-PROD-BASELINE-v1  (root:root, 冻结不解冻)
/opt/sglang/local-prod-v1.1-candidate  LOCAL-PROD-v1.1        f0ca9206...97ab7
/opt/sglang/local-prod-v1.1.2-candidate LOCAL-PROD-v1.1.2     cf32a429...44e5  (今日新建)
结构: src/  launcher/  manifest/  tools/  env -> /home/ubuntu/venvs/sglang-3090
```

## 4. 血缘:冻结树 = repo HEAD + 25 个文件
整个 `src/`(9,070 个非产物源码)对 repo HEAD 的比对:
```
HEAD                    identical 9045/9070  (99.7%)
origin/3090-24g-opt     identical 9045/9070  (99.7%)
origin/3090-24g-hicache identical 9001/9070  (99.2%)
origin/main             identical 7853/9070  (86.6%)
```
=> 冻结树**基本等于 repo HEAD**,差异是**局部的 25 个文件**,不是全面分叉。

## 5. 那 25 个文件的精确归类(这是核心)

### [A] 14 个 —— 生产补丁**已在工作树**,只是未提交
```
.dockerignore
.memory/.../ARTIFACT-CAPABILITY-INVENTORY-20260916.md
.memory/.../OPEN4-SHIM-NECESSITY-VERDICT-20260916.md
.memory/.../TOKENIZER-PROVENANCE-RESOLUTION-20260916.md
python/sglang/_version.py
python/sglang/srt/environ.py
python/sglang/srt/managers/scheduler_components/output_streamer.py
python/sglang/srt/managers/tokenizer_manager.py
python/sglang/srt/mem_cache/cpp_radix_tree/.clang-format
python/sglang/srt/mem_cache/unified_radix_cache.py
python/sglang/srt/observability/hicache_telemetry.py
sgl-model-gateway/LICENSE
test/registered/unit/observability/test_hicache_request_telemetry.py
test/registered/unit/observability/test_output_streamer_hicache_telemetry_wiring.py
```
=> 工作树内容 == 冻结树内容(哈希相同)。**只需 commit。**

### [B] 9 个 —— 补丁**只在 /opt 冻结树**,HEAD 和工作树都没有 ⚠️
```
python/sglang/srt/configs/qwen3_5.py
python/sglang/srt/layers/quantization/gguf.py
python/sglang/srt/mem_cache/storage/extent/extent_allocator.py
python/sglang/srt/model_loader/gguf_name_maps.py
python/sglang/srt/model_loader/loader.py
python/sglang/srt/model_loader/weight_utils.py
python/sglang/srt/models/qwen3_5.py
python/sglang/srt/models/qwen3_5_text.py
python/sglang/srt/utils/hf_transformers/gguf_native.py
```
=> **只能从冻结树导出。** 含 Option-C(allocator)、Qwen3.5/M1 模型支持、GGUF loader 改动。
**若 /opt 丢失,这些源码不可恢复。**

### [C] 2 个 —— 工作树是旧版,与两边都不同,需裁定
```
python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py   (WT 缺 :2163 WAL hunk,无 Option-C)
test/registered/unit/mem_cache/test_extent_file_backend_unit.py
```
=> 工作树比冻结 **v1.1** 还少 3 行(那个 checkpoint WAL 修复)。直接提交会回归。

## 6. 我的 scratch 与源码树(全部在 /tmp/opencode,13G)
含 `python/sglang` 的树:
```
/tmp/opencode/isolate-wal-runtime-tree-20260916  555M
/tmp/opencode/l3-native-src-20260916             238M
/tmp/opencode/m3-m4-normfix-src-20260916         126M
/tmp/opencode/l3-ablation-src                    125M
/tmp/opencode/l3-cadence-src                     124M
/tmp/opencode/l3-v1-inst-src                     125M
/tmp/opencode/l3-native-ab-inst-20260916          95M
/tmp/opencode/fixprobe
/tmp/opencode/v1.1.2-f1fix-20260916/src
/tmp/opencode/v1.1.2-optionC-20260917/src        <- 与 frozen v1.1.2 的 11 个差异文件 11/11 匹配
```
证据目录:`/var/log/sglang`(108G,含 phase6/7/8/9 各 gate 运行记录)。

## 7. editable-install 地雷(已定位到文件)
```
/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages/__editable___sglang_*_finder.py
   maps sglang -> /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang  (REPO!)
```
三个冻结树的 `env` **全部 symlink 到同一个 venv**。所以不设 `PYTHONPATH` 时 `import sglang` 加载
**repo 工作树**,而不是冻结树。所有 gate 现已硬断言 `sglang.__file__`。

## 8. 磁盘
```
/            484G total, 359G used, 125G free (75%)
/data        167G  (models 72G + l3 95G)
/var/log/sglang 108G
/tmp/opencode    13G
/home/ubuntu     52G  (venvs 19G + venv 13G + sglang 150M + ...)
```
launcher `perf` 档需 `L3_MAX=100Gi` + `MIN_FREE_SPACE=50Gi`;当前 125G free,store 实际上限约 75G。

## 9. 治理裁定:这允许吗?
* 部署产物在 git 外 —— **允许**(等同于 release tarball / container image)。
* **但我们这个情况不同**:17+ 个实质生产补丁的**源码**只存在于 `/opt`,不在任何分支。
* 补偿控制:freeze manifest(`TREE-SHA256.txt` + `identity.json` + pins + launcher preflight)
  => **按哈希可验证、可复现**,这是真的控制。
* **缺口**:无法评审(无 PR/diff)、无法用 git 复现或回滚、**/opt 丢失即源码丢失**。
* **修法**:把 [A] commit、[B] 从冻结树导出 patch 后 commit、[C] 裁定 provenance。即对齐 repo → 冻结树。

---

## 10. 修复产物已产出并经 orchestrator 独立验证 (2026-09-17 10:40Z)

`/tmp/opencode/reconcile-20260917/`:
| 文件 | 内容 |
|---|---|
| `B-frozen-only.patch` (29 KB) | 9 个文件的 unified diff (HEAD -> frozen v1.1.2) |
| `C-provenance.patch` (17 KB) | 2 个文件的 diff (worktree -> frozen v1.1.2) |
| `file-status.json` | 每个文件在 HEAD/worktree/frozen-v1.1/frozen-v1.1.2/optionC 的哈希 |
| `B-per-file-summary.json` | 每个补丁做什么 |
| `REPORT.md` | 完整报告 |

### Orchestrator 独立应用测试 (未触碰工作树,在 /tmp 副本上做)
```
B patch: git apply --check  -> CLEAN
         应用后 9/9 文件 sha256 == frozen v1.1.2   (0 mismatch)

C patch: 从 worktree 基线应用 -> APPLIED
         应用后 2/2 文件 sha256 == frozen v1.1.2   (0 mismatch)
         (含 :219 的 self._wal_recovered_next_seq = self._wal_next_seq,即那 3 行 WAL 修复)
```

### 覆盖算术
```
frozen-v1.1.2 与 repo HEAD 的全量差异 = 25 个文件
  [A] 14 已在工作树(未提交)          -> 只需 commit
  [B]  9 由 B-frozen-only.patch 覆盖  -> 已验证字节一致
  [C]  2 由 C-provenance.patch 覆盖   -> 已验证字节一致
=> commit[A] + apply[B] + apply[C] 之后,repo 源码 == 冻结生产源码
```
Option-C 交叉核对:frozen v1.1.2 的 9 个 [B] 文件与 `/tmp/opencode/v1.1.2-optionC-20260917/`
**11/11 SHA256 一致**;`extent_allocator.py` = `fdbd9e4965b5f0613ff7e12c539995233403f9567d7e7b54f5bb4d93bef10d13`。

### 执行计划(需 owner 授权;未执行)
1. `git add -A && git commit`  — 提交 [A](LOW)
2. `git apply B-frozen-only.patch` — (MEDIUM,实质代码)
3. `git apply C-provenance.patch` — (LOW-MED)
4. commit [B+C] — (LOW)
5. 合并 `origin/3090-24g-hicache` — 仅 3 个提交(合并提交 + 2 个纯文档)(LOW)

### DO-NOT-EXECUTE
所有 git 写操作、工作树修改、`/opt`/`/data`/`/var/log` 写入、GPU/端口占用、以及上述步骤本身
(在 owner 授权前)。

### fresh clone 仍 != production
`launcher/`、`manifest/`、`env`(symlink)、`tools/` 不在 repo 里 —— 这是**预期的**(部署层)。
按哈希可验证性由 freeze manifest 提供。
