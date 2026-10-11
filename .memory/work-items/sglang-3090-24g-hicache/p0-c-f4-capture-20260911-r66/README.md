# P0-C-F4-CAPTURE-20260911-R66

- **工作标题：** P0-C-F4-CAPTURE-20260911-R66
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/P0-C-F4-CAPTURE-20260911-R66.md`：**
- Task ID: `P0-C-F4-CAPTURE-20260911-R66`
- Invocation: `ses-p0c-f4-capture-r66-20260911`
- Role: `devops-executor` (private)
- Epoch: `2026-09-11`
- Status: **done**
- ENTRY: ACCEPT
- Authorization: bounded **read-only** capture on the authorized disposable RTX 3060 12G
experiment only. 3090/production never touched.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/P0-C-F4-CAPTURE-20260911-R66.md`：**
I executed the bounded read-only R66 capture against the authorized RTX 3060 host and closed
**all** R61 F4 metadata gaps: `config.json` (served path resolved), full model-directory listing
with exact safetensors sizes, filtered `/proc/218072/environ` + full cmdline, python/torch/sglang
versions and `/get_server_info` banner fields, `262144`/rope settings, and quantization internals
(`compressed-tensors`, `pack-quantized`, W4A16, `group_size=128`, symmetric int) — all backed by
raw hashed artifacts. R60's asserted `model.safetensors` = 5,052,218,552 B and
`model_mtp.safetensors` = 241,200,704 B are confirmed exactly; `max_position_embeddings=262144`
provenance is confirmed at `config.json:245`; and the "32 layers `linear_attention`/`full_attention`"
line is corrected to **24 linear + 8 full**. The existing profile server was not restarted or
disturbed, and no product/test/gate/storage/Git change was made. This is P0-C evidence only; the
P0-B hard gate remains NOT_VERIFIED.

### 报告列出的产物/证据
- `phase2-hicache-design/work/P0-C-F4-CAPTURE-20260911-R66.md`：Local artifact directory:
`.memory/phase2-hicache-design/work/P0-C-F4-CAPTURE-20260911-R66.artifacts/`
| Artifact | Bytes | SHA256 |
|---|---|---|
| `00_identity.txt` | 1512 | `f3dbe10cfd6062d62c777ba4b9560c0f554176af72d754933de5a3b1f986a2ed` |
| `01_config.json` | 10677 | `44b4262b97b45d002c52f68bc72f7d9ba66bacea5868f3d3d3f6ed5c5b7fbd60` |
| `02_model_dir.txt` | 2969 | `5705dd88b38d299f986cd6e4dd2ed48f50d5736b155b1bfc714cdbfbb6110195` |
| `03_environ_filtered.txt` | 779 | `8daf8d9773bd2e69fe14555ea62d697d08370ea512a24e6d5996210d62224eaf` |
| `04_cmdline.txt` | 1091 | `265c2174cc9ed45a39f714e534d64e0497c96f7fd2bca2b768a9f4d09e325932` |…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-C-F4-CAPTURE-20260911-R66.md` → `.memory/phase2-hicache-design/work/P0-C-F4-CAPTURE-20260911-R66.md`; SHA256 `a173c0ef9201670ce8309c511cee68cd6d436ca885a5d16361c5ac2f124ba367`; source state `tracked`
