# phase2-hicache-design-devops-prod-deploy-e1

- **工作标题：** phase2-hicache-design-devops-prod-deploy-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-devops-prod-deploy-e1.md`：**
blocked

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-devops-prod-deploy-e1.md`：**
生产部署**未启动成功**。冻结脚本与参考机一致、admin key 已就位、L3=160G 容量决策已确认（ledger 冻结基线），但 22151 的模型目录 `Qwen3.5-9B-w4a16` 不完整——缺少 `config.json`（含 `model_type`），`AutoConfig.from_pretrained` 直接抛错；`model_mtp.safetensors` 亦与参考机不一致（95MB vs 486MB）。属于模型完整性问题，非部署参数问题。按派发约束（不改 /root/models）不代传/修复，如实 blocked。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-devops-prod-deploy-e1.md`：- 目标机: root@175.155.64.171:22151 (pytorch-8802, RTX 3090 24GB, /data 295G)
- 冻结启动脚本: `/root/direct-launch-gate1.sh`（未改动，模式 644 未加执行位，经 `bash` 调用）
- 启动日志: `/root/prod-deploy/launch-prod-160G.log`
- L3 extent 目录已建: `/data/l3/hicache-prod`
- admin key 已就位: `/opt/sglang/l3-admin-key`（从 24052 复制，md5=ae50d85fe2ebd3cc8c12982a2406b579 与参考机一致）
- 报告文件: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-hicache-design-devops-prod-deploy-e1.md`

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-devops-prod-deploy-e1.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-devops-prod-deploy-e1.md`; SHA256 `6ff0cada0e01dd4468f5484159453df31d83cd4d5c1b77b5ca2bb1d4bd7d4ed4`; source state `tracked`
