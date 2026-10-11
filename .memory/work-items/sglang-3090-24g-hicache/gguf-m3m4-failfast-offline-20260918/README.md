# GGUF-M3M4-FAILFAST-OFFLINE-20260918

- **工作标题：** GGUF-M3M4-FAILFAST-OFFLINE-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/GGUF-M3M4-FAILFAST-OFFLINE-20260918.md`：**
Bounded CPU-only diagnosis of exactly two questions:
- **Q1:** Is the working-tree `gguf_native.py` fix CLOSED — does `build_gguf_tokenizer` on the REAL M3 and REAL M4 GGUF files encode each of the five canonical markers (`<|endoftext|>`=248044, `<|im_start|>`=248045, `<|im_end|>`=248046, `<think>`=248068, `</think>`=248069) to its canonical id, with no `[PAD*]` collision?
- **Q2:** Was the recorded `GGUF_CORRECTNESS=FAIL` obtained BEFORE or AFTER the fix bytes? Establish from on-disk artifacts, not guessing, and state the discriminator.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`phase2-hicache-design/agents/GGUF-M3M4-FAILFAST-OFFLINE-20260918.md`：**
- **Q1 = YES, the fix is CLOSED on both real GGUF artifacts.** All five markers encode to their canonical single ids on M3 and M4. No `[PAD*]` collision. Real in-tree unit test 10/10 PASS; harness `--cpu-smoke` `ok=True`, all checks pass.
- **Q2 = the FAIL was obtained BEFORE the fix bytes (pre-fix).** The gate ran 2026-09-17 15:08:28–15:28:21Z against a tree whose `gguf_native.py` was byte-identical to the pre-fix HEAD blob; the fix file was last modified 2026-09-17 16:58:54Z. The gate's own recorded tokenizer fingerprint is pre-fix (`tokenizer_vocab_size = 248293`), which the pre-fix module reproduces exactly and the fixed module does not (`248320`).
- **No remaining defect in the tokenizer id-binding** was found. See "Remaining claims or exclusions" for the untested post-fix model-behavior question.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/GGUF-M3M4-FAILFAST-OFFLINE-20260918.md` → `.memory/phase2-hicache-design/agents/GGUF-M3M4-FAILFAST-OFFLINE-20260918.md`; SHA256 `da5f0c90f67c51e09e538c784d56b667fad90ed0dab583aeb839faabff372a3c`; source state `tracked`
