# RTX 3090 生产机 22151 模型目录补齐报告 — devops model-fill e1

## status
done

## artifacts
- 目标机: root@175.155.64.171:22151 (pytorch-8802)
- 源机: root@175.155.64.171:24052 (pytorch-4402)
- 补齐目录: `/root/models/Qwen3.5-9B-w4a16/`（22151 侧）
- 报告文件: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-hicache-design-devops-model-fill-e1.md`

## 执行摘要
从 24052 经 **24052→22151 直连免密 tar 流**一次性传输 10 个文件（9 个缺失元数据 + 覆盖替换 `model_mtp.safetensors`），未触碰 `model.safetensors`。传输后逐文件 md5 与源侧比对，全部一致。

## evidence

### 传输前状态确认
- 24052 直连 22151 免密验证通过（24052 上有 `~/.ssh/id_ed25519`，`ssh -p 22151 root@175.155.64.171` → DIRECT-OK / pytorch-8802）。
- 22151 `/` overlay 可用 31G，足够承载 ~490MB 增量。
- 22151 源目录此前仅 4 个文件：`chat_template.jinja` / `model.safetensors` / `model_mtp.safetensors`(95MB, 99186176B) / `tokenizer.json`；缺 config.json 等全部元数据。

### 传输方式
单条 tar 流命令（24052 打包 → 管道 → 22151 解包）：
```
24052: tar cf - <10文件> | 22151: tar xf -  (到 /root/models/Qwen3.5-9B-w4a16)
```
返回 TRANSFER-DONE。

### md5 比对表（源=24052，目标=22151）
| 文件 | 24052 md5 | 22151 md5 | 一致 |
|---|---|---|---|
| config.json | 35f633aa460b76c5913961c5425aa98f | 35f633aa460b76c5913961c5425aa98f | YES |
| model.safetensors.index.json | d1310ec4ec36d84fe69c241079065f67 | d1310ec4ec36d84fe69c241079065f67 | YES |
| generation_config.json | 2606793e95f127bb4eb798ac69d14f58 | 2606793e95f127bb4eb798ac69d14f58 | YES |
| tokenizer_config.json | 0aef52fe21513d2cdbe5b6f534b15248 | 0aef52fe21513d2cdbe5b6f534b15248 | YES |
| processor_config.json | 3163c73d3625a10c9e843ec377a1298a | 3163c73d3625a10c9e843ec377a1298a | YES |
| README.md | fa21d1f6ac7db4215e8ca4bfccf5125d | fa21d1f6ac7db4215e8ca4bfccf5125d | YES |
| .gitattributes | 5be3844453f6d3f47982557869da27de | 5be3844453f6d3f47982557869da27de | YES |
| recipe.yaml | dae758d64736bcb11aec821b964666d1 | dae758d64736bcb11aec821b964666d1 | YES |
| configuration.json | 5fe4ea05313adfc3e8f6c194d380f6a9 | 5fe4ea05313adfc3e8f6c194d380f6a9 | YES |
| model_mtp.safetensors | 50767e137d5a8a4885c065fcd0f29e81 (486582848B) | 50767e137d5a8a4885c065fcd0f29e81 (486582848B) | YES |

### 关键校验点
- **config.json** 含 `model_type` 字段：grep 命中 `"model_type": "qwen3_5"`（另有 `qwen3_5_text`）——生产 crash 直接根因已消除。
- **model_mtp.safetensors**：22151 现为 486582848B，md5=`50767e137d5a8a4885c065fcd0f29e81` 与 24052 完全一致；原 95MB 不完整版（99186176B, md5=9276a22c…）已被完整版覆盖。
- **model.safetensors 未动**：md5=`5e6de91cf0e7f52575f37033683c6ef2`，size=10950193416B —— 与派发声明一致，未触碰。
- **目录清单一致**：22151 与 24052 均为 13 个文件（12 个 ls 可见 + 隐藏 `.gitattributes`），逐名比对完全相同。

### 约束遵守
- 未修改 `/root/models` 外任何内容；未改动 24052 任何文件。
- model.safetensors 全程未传输、未覆盖。
- 传输用前台阻塞式单命令，未丢后台返回。

## summary
22151 生产机模型目录 `Qwen3.5-9B-w4a16` 已补齐至与参考机 24052 完全一致（13 个文件）。缺失的 9 个元数据文件与不完整的 `model_mtp.safetensors` 均从 24052 经直连免密传输并逐文件 md5 校验一致；`model.safetensors` 保持原样。生产启动 crash（`ValueError: Unrecognized model ... should have a model_type key`）的直接根因已消除。

## followups
1. 重跑生产部署（脚本/配置已就绪，L3=160G 决策已定）：`env L3_BACKEND=extent STORAGE_DIR=/data/l3/hicache-prod MAX_SIZE=160G MIN_FREE=10G SGLANG_PORT=8024 bash /root/direct-launch-gate1.sh`，验证 sglang 正常启动。

## open_issues
- 无。模型目录完整性已达成；启动验证属后续部署任务。
