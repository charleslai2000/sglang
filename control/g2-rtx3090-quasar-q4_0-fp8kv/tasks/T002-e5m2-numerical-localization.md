Status: DONE
Work area: Repo-root implementation and verification
Objective: 定位固定4K QUASAR Q4_0 E5M2 KV相对BF16的最终logits/top-1分歧，区分合法精度效应、生产缺陷与未解决风险。
Inputs: HEAD `b3b337f5882ef495c0c803441eae65c0cdf3aaf6`；fixture `/data/sglang-hicache/g2-quasar-runs/e5m2-milestone-20261102T184505Z/4k-prompt.json`；exclusive lock `/tmp/f1-r16b-gpu-exclusive.lock`。
Completion: 完成真实L17 cache-format reverse→suffix反事实与no-op验证；综合冻结BF16/E5M2 4K证据并按原目标作有界数值裁决；服务/锁清理。
Result:
- **PASS — 诊断任务完成；FP8产品数值门 NO-GO / NOT ACCEPTED。** 详细简明裁决见`control/g2-rtx3090-quasar-q4_0-fp8kv/T002-numerical-verdict.md`。
- 冻结BF16/E5M2 final chunk完整logits总差relL2 `.291054`、P99 `3.013479`、max `4.937507`，top1=`128870/236187`。同GGUF SHA256 `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`、source HEAD `b3b337f...`、同prompt IDs（final chunk hash `3d6604...`）、BF16 model dtype、context4608、chunk2048、Triton、page1、graphs disabled、greedy sampler；配置KV dtype为主要受控模式变量。外部`random_seed`不同（18439608 vs343913761），不宣称所有内部状态完全同态；同配置E5M2复跑的final logits/top-k逐值相同，支持复现。此对照作KV模式总效应估计，不当作单算子分解。
- L4 position4095有效SWA窗口`[3584,4095]`不读prefix；production replay的完整current K/V crossover精确复现relL2 `.008345655`、max `.03125`，单换prefix pool不改变输出。观察差异由跨run current K/V输入变化解释。
- L17真实路径`Gemma4Attention→RadixAttention→TritonAttnBackend.forward_extend→extend_attention_fwd`。在真实backend同次capture输入及完整参数下，BF16和E5M2同cache replay均逐元素复现live；no-op injection均逐元素复现final logits。独立pool下仅交换prefix cache representation，实际注入tensor与真实kernel反事实逐元素相等。
- L17 BF16 upstream切换到E5M2 prefix：局部Attention relL2 `.0092772`/max`.0234375`；suffix logits relL2 `.1053791`/max`2.394367`，top1 `128870→236761`，margin `.0587215`。E5M2 upstream切回BF16 prefix：局部Attention relL2 `.0112956`/max`.03125`；suffix logits relL2 `.1406416`/max`2.525362`，top1仍`236187`，top2 `106`，margin `1.279818`。仅是position4095/L17给定upstream下的条件效应，不相加、不外推为全部量化误差。
- 未发现解释数据的production Attention defect。任务数值归因条件已完成；**没有可适用的用户授权任务级质量阈值/质量语料，故模型质量不能PASS；E5M2 NO-GO / NOT ACCEPTED，需用户裁决quality threshold。** 无需为全层误差分解延长T002，不启动容量/性能。
- GPU服务停止，GPU `1 MiB/0%`、exclusive lock可得。保留共享dirty。未commit/push：唯一生产hook/capture修改在预先dirty的`python/sglang/srt/models/gemma4_causal.py`和`python/sglang/srt/layers/attention/triton_backend.py`，不能安全整文件提交；自有control证据留在dirty/untracked目录，记录SHA无新增提交。
