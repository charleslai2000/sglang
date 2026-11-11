# 当前计划

## 已有证据
- T006 冻结质量：BF16 1091/1319，E5M2 1098/1319；配对 delta +0.531 pp，95% CI [−0.834,+1.895]，不重跑质量评测。
- E5M2 c1/c4/c8/c16 已测；c1/c4/c16 可复用作为参照，c8 双峰不稳定不纳入本轮范围。原 E5M2 配置 max-running=16 池 Full/SWA=1,093,791/14,353。
- Overlay 精确 SHA `69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e` 等于当前 HEAD Git blob；共享 dirty kernel SHA 不同，不作为候选。

## 结论
T001 实测配对完成，报告 `experiments/g2-quasar-e5m2-bf16-ab/AB-RESULTS-20261111.md`。E5M2 Full pool 1,093,791 slots 对 BF16 528,954（2.068x）；两者实测均承载 c1/c4/c16 请求并完成 32 tokens。吞吐近似：BF16 9.008/33.797/114.163 tok/s；E5M2 8.329/33.733/114.371 tok/s，c1 E5M2 高波动，故不宣称性能优势。质量复用 T006：E5M2 83.245% 对 BF16 82.714%，配对 CI 跨越轻微负效应与收益；没有 Owner 阈值，仍 NOT ACCEPTED。

## 状态
Goal 完成。T001 实验、报告及独立控制文档已按精确文件提交并推送；共享工作树其他 dirty 文件保留未动，远端同步 SHA 已核验。