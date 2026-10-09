# phase2-hicache-design doc-writer prod-deploy e1

status: done
artifacts:
  - Docs: `3090-dev/prod-deploy-issues.md` — 22151 生产部署问题记录（4 项真实问题，问题/现象/根因/修复/教训 每节）
  - Script: `3090-dev/prod-deploy/relaunch-e1.sh` — Option B 重启脚本（env 层路径覆盖到 sglang-patch，冻结脚本零改动），逐字节按派发内容归档，mode 100755
  - README: `3090-dev/README.md` — 新增"生产部署（22151 实录）"章节（脚本清单 + 5 hard gates 验证要点表 + 22151 特定部署要求）
  - Commit: `5a76070743` on branch `3090-24g-hicache`（HEAD=fac8ccb4cf 之上，未 push）

evidence:
  - 全部素材来自 authoritative devops 报告（.memory/phase2-hicache-design/work/）：
    - phase2-hicache-design-devops-prod-deploy-e1.md（问题 1 启动 crash + 模型目录对比表）
    - phase2-hicache-design-devops-model-fill-e1.md（问题 1 修复：10 文件补齐 + 逐文件 md5）
    - phase2-hicache-design-devops-prod-deploy-22151-e1.md（问题 2/3 根因与修复、5 gates 全过、relaunch-e1.sh 原始内容）
    - phase2-hicache-design-devops-env-migrate-e1.md / env-finalize-e1.md（环境背景：sglang-patch env、ninja 路径）
    - ledger.md（冻结基线 pool64/Graph ON/c8/RH OFF/extent L3=160G；5 gates 判定；sglang-patch vs sglang-dev 根因确认；问题 4 /data 满警示）
  - 脚本内容与派发提供逐字节一致（CUDA_HOME/CPLUS_INCLUDE_PATH/LIBRARY_PATH/LD_LIBRARY_PATH/PATH + L3_BACKEND/STORAGE_DIR/MAX_SIZE/MIN_FREE/SGLANG_PORT + env 落盘 + bash 启动冻结脚本）
  - commit 仅含 3 个目标文件（README + prod-deploy-issues.md + relaunch-e1.sh），`.memory/` 未跟踪未 add（ARTIFACTS v5.2）；工作树仅剩 .memory/ untracked，分支 ahead 1 未 push

summary:
  - 完成 HiCache 生产部署问题记录基线封存：文档 + 归档脚本 + README 更新，commit `5a76070743` 到主分支 3090-24g-hicache，不 push（按派发约束）。
  - 文档严格按素材记录 4 项真实问题（现象/根因/修复/教训），未编造；内容与 devops 报告及 ledger 冻结事实一致。

followups:
  - gate5 631.4 tok/s（+5.9%）为短窗口噪声，待长窗口复核（已在 README gate5 行注明）。
  - 本机→22151:8024 网络连通性待确认放行（ledger 遗留项，非本文档范围）。

open_issues:
  - 无（本文档范围已完成并提交）。
  - 注：问题 4（24052 /data 100% 满）为环境警示非 22151 部署问题，已按素材如实记录为警示节，未作部署归因。
