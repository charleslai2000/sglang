# phase2-hicache-design-tester-gate2-s32-e1 (Step② 32-slot controlled saturation)

## status
done

## artifacts
- Remote run: `/root/evidence-gate2-s32k8/run-20260904-173540/` (verdict.json, runs.csv, mid-run-metrics.txt, metrics-final.txt) + `/root/engine-gate2-s32k8.log`；status `GATE2_s32k8_COMPLETE rc=0`（17:32:59→17:41:27，~8min）。
- Config confirmed in engine log: `Mamba Cache is allocated. max_mamba_cache_size: 32, conv_state size: 0.04GB, ssm_state size: 1.55GB`；ExtentFileBackend 64G/96G（slots=1430）。
- 注意：先前 tester 首次派发在分析阶段因 API 502 中断；orchestrator 从原始 remote 日志补完分析并出本报告。run 本身完整、无重跑。

## evidence
- **pool fill（关键）**：`mamba_evictable` 全轨迹 1→**22**（峰值），从未到 32；shutdown 时 `mamba_available_tokens=27`、`mamba_used=0` → **池最高 ~22/32 ≈ 69% fill，从未饱和，末态近乎排空**。
- **L0 exact-restore = 0.9683**（n=24，prompt 439131 hit 425200）≥0.95。
- **extent_recycle = 0**。
- storage_hit>0 = 44/96 rows；L3 restore 正常读回。
- restore_disposition reason：denied 41 / hybrid_discard 15 / revoked:alloc 3 / **revoked:miss 317** / shortfall 84 / too_short 26。
- revoked:miss 分类（rid 匹配 runs.csv，54 行）：A storage>0 = 16（30%）、B dev/host partial = 27（50%）、C cold = 11（20%）。
- aggregate ratio 0.7709（<0.95，12-turn 负载形状正常，非 gate）。

## summary
**诚实结论：本轮并未真正测到 pool saturation cliff，因为池从未饱和。**
- pool=32 已配置并确认（engine log `max_mamba_cache_size: 32`，ssm_state 1.55GB），但 gate2 K=8 负载（8×4=32 distinct chain 的**假设**）并没有把设备 mamba 池压到满——`mamba_evictable` 峰值仅 22/32（69%），末态 available=27。**agents×4 的"32 distinct"并不等于"32 个同时在设备池存活的 checkpoint"**；实际并发存活远低于假设。
- 在此 69% fill 下：L0 exact-restore=0.9683（≥0.95）、recycle=0、无全冷 0-hit 断崖；class-A（storage>0 revoked:miss）16/54 ≈ 30%，与 106-pool K8 的 33% 量级一致——**没有随池缩小而放大成 cliff 的证据**，但也不能就此断言"无 cliff"。
- **因此"pool 接近 100% 是否出现结构性 cliff"仍未在真饱和下被回答。** 需要真正把 fill 压到 ~1.0 的负载（更多并发存活 checkpoint，而非只靠 distinct 链数假设），否则 32-slot 与 106-slot 都在~70% fill 下测得，无法区分池尺寸效应。

## followups
1. **真正压满池**的负载：不是增加 agents（K=8 已 8×4）而是提高**并发在设备池存活的 checkpoint 数**——例如提高 `--max-running-requests`、加大 mamba pool 驻留（`mamba_full_memory_ratio` / 池=16 更易满），或让 driver 在 Phase A 持有更多未释放的 session。目标：`mamba_available → 0` 持续、`evictable+used → pool`。
2. 若目标是"测 cliff"，最小改动 = 池降到 16 + 同样 K=8（8×4=32 ≥ 16 池）更可能真正压满 16/16；或直接接受"池在 24G/106 与 24G/32 都只能到 ~70% fill"这个现实——意味着当前 3090 内存配置下 mamba 池物理上很难真饱和，cliff 问题在 gate2 负载形状下实际不可达（此时门2 的 pool-saturation 担忧在本配置下无实据）。
3. class-A 30%（16/54）持续存在，独立于池尺寸——这是此前 ledger 中 coder-restore-hit0-e1 C 次因（mamba TRAILING/sidecar restore 折叠）的又一佐证，是 gate-3+ 的真实候选缺陷。

## open_issues
- **"真 pool saturation cliff" 结论未定**：本 run 在 69% fill 下无 cliff 证据，但未达 100% fill，不能证否。
- revoked:miss 日志行数（317）> runs.csv 匹配（54），含 HEALTH_CHECK 等非 agent 行，占比按匹配行计。
- 环境：3090 干净（无引擎、GPU 15MiB）；`/data/l3/p2io-gate2-s32k8` 保留为本次证据。
