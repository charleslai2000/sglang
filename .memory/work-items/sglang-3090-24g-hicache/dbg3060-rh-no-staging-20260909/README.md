# DBG3060-RH-NO-STAGING-20260909

- **工作标题：** DBG-20260909-RH-NO-STAGING
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/DBG-20260909-RH-NO-STAGING.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/DBG-20260909-RH-NO-STAGING.md`：**
The RH-ON flags were parsed and the scheduler's RH pass did execute.  The
failure is not an HTTP/API path that bypasses the scheduler, nor does this
policy require a separate prediction signal.  Rather, the direct `/generate`
path eagerly calls the ordinary storage prefetch **before** the request enters
the waiting queue.  The RH maintenance pass runs only afterwards.  Under this
five-way burst, the requests therefore entered the RH pass already
`RESTORING` or `WAIT_CAPACITY/PREFETCH_BUDGET`; `RESTORING` is explicitly out
of the RH staging funnel, and the ordinary reconciliation path consumes
`PREFETCH_BUDGET` waits before the RH pass gets an effective speculative
opportunity.
The eventual `HOST_ALLOC` waits are a separate, confirmed physical
allocability failure.  The host-alloc epoch mechanism did run and emitted
request-correlated decisions.  It correctly did **not** wake y/q/w because
the required KV generation never advanced: each required 54,976 KV units,


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/DBG-20260909-RH-NO-STAGING.md` → `.memory/phase2-hicache-design/work/DBG-20260909-RH-NO-STAGING.md`; SHA256 `113e3d9647754a42c929bd6f390a1c3f8bf0d731e5a5f3c733a323104aeb4232`; source state `tracked`
