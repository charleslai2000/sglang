# G3-IQ3-LIVE-PATH-CHECK-20260908

- **工作标题：** G3-IQ3-LIVE-PATH-CHECK-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
只读核实 IQ3_S 的本地/部署 GGUF 源代码与已加载 kernel 身份，回答 dispatch 路径、sharded forward contiguous、Q8_1 activation quantization 机制是否存在；不运行 workload 或做性能归因。

## 实际改了什么
只读检查本地 checkout 与授权 host 上冻结 v1 PID 503601/8035 的 source/package/library identity；没有 workload、download、process change、instrumentation 或 source edit。checkout dirty 状态保留，未修改。

## 生成结果与验收
报告核实部署 `gguf.py` 与本地字节一致；IQ3_S 属于 MMVQ/imatrix 类型，超过按 qweight 输出行数决定的安全阈值时走 dequantize fallback；sharded `GGUFLinearMethod.apply` 含 `.contiguous()`，但是否每次分配取决于 slice shape/contiguity；CUDA wrapper 每次调用会创建 Q8_1 temporary 并量化。确认服务加载 `sgl_kernel 0.4.6.post1` 与 shared object 哈希。未取得实际 runtime shard shapes、每 forward allocation count，也无法恢复 deployed Git commit（无 `.git` metadata）；因此不声称实际分配频率、瓶颈占比或性能提升。


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `dac6db1ebabdb80209b757fd063cf53e05c091e7`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LIVE-PATH-CHECK-20260908.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LIVE-PATH-CHECK-20260908.md`; SHA256 `48929030bdf4a9df4a8e98668934acceaa4cd62b90ce6759c287c3914b9c6d54`; source state `local-only`
