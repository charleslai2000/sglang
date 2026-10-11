# M3M4-GATE-RERUN-20260918

- **工作标题：** M3M4-GATE-RERUN-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/M3M4-GATE-RERUN-20260918.md`：**
Re-run the GGUF sampled-contract gate for M4 then M3 on the CURRENT working tree (which contains the
verified tokenizer id-binding fix), record report.json verdicts, and restore production to a verified
UP state.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`phase2-hicache-design/agents/M3M4-GATE-RERUN-20260918.md`：**
Both goals are complete. The gate was re-run on the CURRENT working tree and produced validated
post-fix verdicts; production was restored and independently verified UP.
**(a) M4_GATE_VERDICT = FAIL** (verdict from `m4/report.json`; status=completed).
- criterion 2 (`short_deterministic_semantics`) = **FAIL** (pass=false)
- criterion 6 (`sampled_ge512_coherent_content`) = **FAIL** (pass=false; `passing_probes=[]`)
**(b) M3_GATE_VERDICT = FAIL** (verdict from `m3/report.json`; status=completed).
- criterion 2 (`short_deterministic_semantics`) = **FAIL** (pass=false)
- criterion 6 (`sampled_ge512_coherent_content`) = **FAIL** (pass=false; `passing_probes=[]`)
The FAIL is NOT the previous pre-fix FAIL re-observed: this run demonstrably exercised the fixed
bytes. `step2b_tokenizer_crosscheck.tokenizer_vocab_size = 248320` (post-fix) in both reports, versus
`248293` (pre-fix) in the prior reports. The two failing criteria are unchanged in kind, but the
verdict now stands on post-fix evidence.
**(c) Was the fixed module sha256 the one actually exercised?** — The fixed tokenizer module
(`gguf_native.py`, sha256 `0f3c8fb9...`) IS in the exercised source tree:

### 报告列出的产物/证据
- `phase2-hicache-design/agents/M3M4-GATE-RERUN-20260918.md`：- WORKING-TREE MODULE (tokenizer id-binding fix): `python/sglang/srt/utils/hf_transformers/gguf_native.py`
- sha256 = `0f3c8fb9f2e6c3eb2bdcf0a3640f26880a88179bb0b4a3f41674fbfaf8202ade` (mtime 2026-09-17 16:58:54Z).
  Re-checked AFTER the gate: unchanged (same sha256). No product source edited by this task.
- Gate fingerprint module `python/sglang/srt/models/qwen3_5_text.py` sha256 =
  `d51d5441064c13cb90da9af7399c067e072182e7bc8c362e72ea4ba6a11e3941` (same as the prior reports' recorded
  `source_preflight.actual_module_sha256`).
- GGUF_GATE_SRC default `<repo>/python`; gate python `/opt/sglang/local-prod-v1/env/bin/python`…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/M3M4-GATE-RERUN-20260918.md` → `.memory/phase2-hicache-design/agents/M3M4-GATE-RERUN-20260918.md`; SHA256 `8f9d03b92d958198133a933f4c6176e42d7a55123847ffd9474edaba2f9aed1f`; source state `tracked`
