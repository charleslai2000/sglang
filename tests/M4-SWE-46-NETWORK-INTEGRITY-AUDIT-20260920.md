# M4 SWE 46-task Network / Benchmark Integrity Audit

日期：2026-09-20  
对象：`M4-SWE-46-BASELINE-20260920.md`  
结论状态：**clean corrected baseline = 33/46 (71.7%); 本轮原始 35/46 为 contaminated historical result**

## 1. 审计结论

对 46 条 trajectory 的实际 assistant tool actions、tool outputs、response metadata 和 benchmark parquet 元数据进行窄审计后，确认：

- 至少 2 个 task 成功访问包索引并下载未来版本的同项目发行包；
- 下载后解包、读取或 diff 了与当前 issue 直接相关的源码；
- 这两项属于 **CONTAMINATED**，不能纳入可信 clean SWE correctness baseline；
- 1 个 task 访问外部 URL 仅用于复现自身网络/URL 解析 bug，分类为 **ENV-ONLY / REPRO-EXTERNAL-URL**，未发现答案源码下载；
- 其余 43 个 task 在已审计的实际命令中未发现成功获取外部项目源码或外部答案；
- 因此当前 35/46 应保留为原始 verifier 事实，但只能报告为 **provisional 35/46**，不能报告为 clean baseline。

官方原始 verifier：

```text
/home/ubuntu/swe-round1/evidence/m4-ab-20260920/verify46/openai__swift-qwen38-27b-q3_k_m.swebench-m4-46-20260920.json
```

原始结果：

```text
submitted=46
resolved=35
unresolved=11
infra_failures=0
errors=0
```

## 2. 分类摘要

| 分类 | task 数 | 任务 |
|---|---:|---|
| CONTAMINATED | 2 | `sympy__sympy-23413`, `django__django-15563` |
| ENV-ONLY / REPRO-EXTERNAL-URL | 1 | `psf__requests-5414` |
| 未发现成功外部源码/答案获取 | 43 | 其余任务 |
| UNKNOWN | 0（就已取得的 trajectory/action 日志） | — |

“未发现”不是网络隔离证明；它只表示在现有 trajectory 的实际 tool actions 和输出中没有找到成功外部答案获取。VM/container 本身显然允许出网，因此不能把这 43 项宣称为网络隔离下的 clean task。

## 3. 明确污染任务

### 3.1 `sympy__sympy-23413` — CONTAMINATED

Benchmark 元数据：

```text
repo: sympy/sympy
version: 1.11.dev
base_commit: 10de1a18a0efac0b19b611e40c928250dda688bf
```

实际命令和结果：

```text
pip download sympy==1.9 --no-deps -d /tmp/syam
# 成功下载 sympy-1.9-py3-none-any.whl

pip download sympy==latest --no-deps -d /tmp/symlatest
pip download "sympy<99" --no-deps -d /tmp/sym2
# 成功下载 sympy-1.14.0-py3-none-any.whl

unzip -o -q sympy-1.14.0-py3-none-any.whl \
  'sympy/polys/matrices/normalforms.py'

sed -n '/def _hermite_normal_form/,/def _hermite_normal_form_modulo_D/p' \
  sympy/polys/matrices/normalforms.py
```

该 issue 的 patch 正好修改：

```text
sympy/polys/matrices/normalforms.py
```

并涉及 `_hermite_normal_form`。Benchmark 是 `1.11.dev`，agent 读取的是未来的 `1.14.0` 实现。虽然当前 trajectory 中未证明整个 patch 是逐字复制，但已经满足“获取并查看同项目未来相关实现”的污染条件。

判定：**CONTAMINATED；必须在 network-off 条件下重跑该 task。**

### 3.2 `django__django-15563` — CONTAMINATED

Benchmark 元数据：

```text
repo: django/django
version: 4.1
base_commit: 9ffd4eae2ce7a7100c98f681e2b6ab818df384a4
```

实际命令和结果：

```text
pip download Django==4.2.28 -d /tmp/dj --no-deps
# 成功下载 django-4.2.28-py3-none-any.whl

unzip -o -q /tmp/dj/django-4.2.28-py3-none-any.whl \
  'django/db/models/sql/*'

diff /testbed/django/db/models/sql/subqueries.py \
     /tmp/djx/django/db/models/sql/subqueries.py

diff /testbed/django/db/models/query.py \
     /tmp/djx/django/db/models/query.py
```

该 issue 的最终 patch 修改：

```text
django/db/models/sql/compiler.py
django/db/models/sql/subqueries.py
```

Benchmark 是 Django `4.1`，agent 下载并查看的是未来 `4.2.28` 源码，并明确在 reasoning 中寻找 upstream fix。即使下载的版本未必包含最终同一 patch，也足以构成高风险答案污染。

判定：**CONTAMINATED；必须在 network-off 条件下重跑该 task。**

## 4. 外部 URL 但未发现答案污染

### `psf__requests-5414` — ENV-ONLY / REPRO-EXTERNAL-URL

执行了：

```text
requests.get('http://.example.com')
```

以及多个 `PreparedRequest.prepare_url()` 测试 URL。上下文是复现 requests 自身的 URL 校验行为；没有发现 pip 下载、外部项目源码读取、GitHub/Git clone 或答案 patch 获取。

判定：不计为 answer contamination，但证明容器具有外网路径，不能称为 network-isolated execution。

## 5. 重要边界

SWE-bench 的 Docker 镜像准备阶段需要网络，这与 agent execution 阶段不同。本审计关注的是：任务容器启动后，agent 是否可以获取未来项目实现或外部答案。

本轮实际启动的任务容器命令没有显示 `--network none`，且 pip 下载成功，因此 execution 阶段不是 deny-by-default 网络隔离。

## 6. 对当前分数的处理

原始联网结果：

```text
35/46 = 76.1%
```

该结果保留为 provisional/contaminated 观测。两项明确污染任务随后在 `--network none` 下使用同一 scaffold、prompt、reasoning effort、timeout 和 verifier 重跑，结果均为 unresolved：

```text
django__django-15563：unresolved
sympy__sympy-23413：unresolved
```

因此 corrected clean 主结果冻结为：

```text
33/46 = 71.7%
```

这是对外/内部决策应使用的主数字。`33/44 = 75.0%` 仅作为未污染原始子集辅助信息，不替代 33/46。`35/46 = 76.1%` 仅保留为历史 contaminated result。

这不是把全部 46 题作废，而是从原始 35 个 resolved 中剔除两项被未来源码污染且无法在 network-off 下复现 resolved 的任务。未污染子集本身为：

```text
33/44 = 75.0%
```

官方离线重跑结果：

```text
/home/ubuntu/swe-round1/evidence/m4-ab-20260920/verify-integrity-rerun/openai__swift-qwen38-27b-q3_k_m.swebench-m4-integrity-rerun-20260920.json
```

不建议把 33/46 外推为完整 50-task 结果，因为仍有 4 个任务镜像缺失。

## 6a. 冻结决策与 telemetry 口径

M4 当前冻结为默认 coding worker 的第一候选；M3 保留为超长上下文/高保真 fallback。后续更有价值的验证是进入真实 OpenCodex canary，而不是再次运行完整 SWE。

原始 46-task run 的：

```text
7h06 / 1316 requests / 250146 thinking tokens
```

应称为 **original 46-task operational telemetry**，不是严格 clean-run performance baseline。两项污染任务的原始 trajectory 没有被 network-off rerun 替换；correctness 已修正为 33/46，但 telemetry 仍来自原始联网 run。

## 7. 必须的后续 clean run 约束

agent execution 阶段必须显式禁网，例如：

```bash
docker run --network none ...
```

并且在正式 run 前做 negative control：

```bash
pip download sympy==1.14.0
curl -I https://github.com
python -c 'import urllib.request; urllib.request.urlopen("https://pypi.org")'
```

三者均应失败。镜像、任务依赖和 verifier 数据必须在容器启动前准备完成。

clean run 还应：

1. 固定同一 46-task manifest；
2. 固定同一模型、prompt、tools、reasoning effort、turn limit、workers；
3. 记录每个容器的 network mode；
4. 保留所有 tool actions；
5. 任一外部源码获取命中即标记 task contaminated；
6. 对 M3 和 M4 使用完全相同的网络策略。
