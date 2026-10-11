# phase2-mamba-sizing-tester-e1

- **工作标题：** phase2-mamba-sizing-tester-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-mamba-sizing-tester-e1.md`：**
artifacts:
- remote: /root/mamba-ratio/{launch.sh, run_one.sh, run_matrix.sh, matrix.txt, gate5.sh, workload60k.py}
- remote evidence: /root/mamba-ratio/evid-<tag>/* (alloc/capped/graph/nvidia-smi/status.log), engine-<tag>.log
- remote Gate-5 evidence: /root/mamba-ratio/evid-g5-r04/, /root/mamba-ratio/evid-g5-r05/
- remote workload results: /root/mamba-ratio/evid-g5-{r04,r05}/workload60k.json + workload.out
- this report: phase2-mamba-sizing-tester-e1.md
evidence:
- Full matrix boot/measurement table (below) from evid-* and engine-*.log

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-mamba-sizing-tester-e1.md` → `.memory/phase2-hicache-design/work/phase2-mamba-sizing-tester-e1.md`; SHA256 `7c510fe3d4fcb270598d73dfa09f78fd7e3fb81aef6a34adadab7cbf3886e4f0`; source state `tracked`
