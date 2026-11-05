Status: DONE
Work area: repo-root implementation and verification
Objective: 在E5M2 KV存储不变的条件下，实验验证BF16 Q/K/V/P attention计算对QUASAR 4K full Forward和代表性任务质量的恢复效果；不得改变生产默认策略，T002保持结案、E5M2仍NOT ACCEPTED。
Inputs: T002固定BF16 upstream capture/reverse-cache反事实；独立E5M2 prefix capture；GPU lock `/tmp/f1-r16b-gpu-exclusive.lock`；现有4K logits注入机制。
Completion: 审计Triton Extend/Decode实际dtype；完成匹配capture上的A/B/C真实kernel replay，suffix logits/top1/margin分析；安全记录结果，不修改共享生产源码。
Result: 完成。证据见`control/g2-rtx3090-quasar-q4_0-fp8kv/T003-L17-ABC-results.md`。固定 BF16 upstream（L17 position4095），A/B/C分别为BF16 cache+BF16 kernel、E5M2 cache+生产FP8 kernel、相同E5M2 bytes/真实scale一次反量化到独立BF16 cache+既有BF16 kernel。A exact复现live，B exact复现T002同upstream counterfactual；A/B/C局部Attention差异relL2=`.009277203/.006859339/.006385191`（A-B/B-C/A-C）。4K suffix top1=`128870/236761/107`，margin=`.05904579/.05872154/.14828825`；A logits exact frozen BF16 baseline，B/C相对A relL2=`.10537908/.05361957`、max abs=`2.394367/.1.133786`。三臂实际注入tensor均与离线replay逐元素相同。结果表明operand precision独立影响该层及suffix，但C不恢复A的局部输出或logits/top1；不把A/C残差纯归于存储量化。所有测试服务停止，GPU回到1MiB；未做容量/性能，无生产源码修改。FP8 E5M2仍NOT ACCEPTED。
Remaining: 本task完成；整体质量gate仍未通过，按G2原控制门不得启动容量/性能。
