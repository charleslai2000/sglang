# env-backup-20260827 — sglang B0 缺陷修复环境备份

备份日期 2026-08-27。来源：AutoDL 实例 223.109.239.36:27520（ubuntu24），容器 `sglang-b0`
关闭前全量测试环境资产快照。镜像 `lmsysorg/sglang:dev-qwen38-27b-dflash2`
（sha256: 616a3e97f45191af975896cfa644279096cb31bd408a071c2e99ca7209c3cafe）。

完整环境快照（docker inspect JSON、pip-freeze、实验数据 /opt/b0-data、模型摘要）存放于：
- s7070: `/home/admin/b0-env-backup-20260827/`（主存）
- Mac: `/Users/charleslai/Workspaces/server/.memory/b0-env-backup-20260827/`

## 清单与 md5

| 文件 | md5 |
|---|---|
| srt/managers/schedule_policy.py（B0-F2 + FS-2 终态） | 1dbbdc95623cc545f02fae6228b28632 |
| srt/managers/schedule_policy.py.bak-b0f2（B0-F2 前） | d3343db22ff3a8e1e2914333c6da38df |
| srt/managers/schedule_policy.py.bak-b0fs（FS-2 前） | 4937ca89a1b27912c8d4e953db148948 |
| srt/managers/schedule_batch.py（FS-3/FS-4 终态） | e60712acee738062d10e3e7efaa17623 |
| srt/managers/schedule_batch.py.bak-b0fs（FS-3/FS-4 前） | b7cc0f500550ca16d1609e3224bb0a41 |
| srt/mem_cache/unified_radix_cache.py（b2a 探针终态） | b9868f3f0f3ec48c90ea9414b828d417 |
| srt/mem_cache/unified_radix_cache.py.bak-b2a（探针前） | 935628d2a0f1acb8d0fdc293df249e5c |
| launch-b0.sh（完整 docker run 启动参数） |  |
| scripts/apply-b0f2.py | 783a020cd1e10ae755551729968fff26 |
| scripts/apply_b2a_probe.py | 43a1af6e18e344ec81037c92ae4aa13b |
| scripts/apply_b0_forced_shape.py | b50d3bd97bb7c0a9843ed2e531faf5c7 |
| scripts/gen_payloads.py | ed92c164ebf29d09822843d7235eeab4 |
| scripts/anchors2.py | b1c2be51ca57bb4d104ea0447239ed03 |
| scripts/verify_tok.py | 4c940796ae4ba368bec381f606db4159 |
| scripts/verify_tok2.py | 28528c83fb4a10b2f84748f7667b65ea |
| scripts/verify_tokens.py | ec75c522580a9419faea0c871f9457ee |

容器关键包版本：sglang==0.0.0.dev1+g5f55db35e、torch==2.13.0+cu130、flashinfer(-python)==0.6.17、
safetensors==0.8.0、fastapi==0.141.1、openai==2.6.1（完整清单见 s7070/Mac 备份 pip-freeze.txt）。

## 恢复步骤

### 1. 重建容器（docker run 参数 = launch-b0.sh 全文，要点）

```
IMAGE=lmsysorg/sglang:dev-qwen38-27b-dflash2
docker run -d --name sglang-b0 --runtime nvidia --gpus all --ipc host \
  -p 8021:30000 \
  -v /root/models/Qwen3.8-27B-NVFP4-RTX5090:/model:ro \
  -e CUDA_VISIBLE_DEVICES=0 -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e SGLANG_ENABLE_UNIFIED_RADIX_TREE=1 \
  --entrypoint python3 "$IMAGE" -m sglang.launch_server \
  --model-path /model --served-model-name qwen3.8-27b-nvfp4-b0 --trust-remote-code \
  --tp-size 1 --host 0.0.0.0 --port 30000 --kv-cache-dtype fp8_e4m3 \
  --attention-backend triton --linear-attn-prefill-backend triton --linear-attn-decode-backend triton \
  --mem-fraction-static 0.92 --max-running-requests 1 --cuda-graph-max-bs 1 \
  --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 --max-mamba-cache-size 8 \
  --max-total-tokens 262144 --reasoning-parser qwen3 --tool-call-parser qwen3_coder --enable-metrics
```

### 2. patch 重放（若重建的是原始镜像；备份的终态文件也可直接拷回并 md5 校验）

重放顺序（每个脚本自带 .bak 备份 + md5 校验，可独立回滚）：

1. `python3 /tmp/apply-b0f2.py` — 打到 schedule_policy.py（B0-F2 checkpoint 边界拆分；回滚 = 拷回 .bak-b0f2）
2. `python3 /tmp/apply_b2a_probe.py apply` — 打到 unified_radix_cache.py（只读探针，追加 /tmp/b2a-cache.log；回滚 = `apply_b2a_probe.py restore` 或拷回 .bak-b2a）
3. `python3 /tmp/apply_b0_forced_shape.py` — 打到 schedule_policy.py（FS-2）+ schedule_batch.py（FS-3/FS-4）；运行期由 /tmp/b0-fs/{split,nobranch,notrack} 标志文件开关（存在=启用）；回滚 = 拷回 .bak-b0fs 并重启容器

代码落位路径（容器内）：
- `/sgl-workspace/sglang/python/sglang/srt/managers/schedule_policy.py`、`schedule_batch.py`
- `/sgl-workspace/sglang/python/sglang/srt/mem_cache/unified_radix_cache.py`
- 脚本放容器 `/tmp/`（apply-b0f2.py 仅容器内有；其余脚本宿主 /tmp 与容器 /tmp 各一份）

### 3. 数据落位（自 s7070 备份恢复）

- `/opt/b0-data/` 全量 → 实例 `/opt/b0-data/`（b0_client.py、gen_b0_payloads.py、各 payload/meta、
  b1/、b2a/、b2a-fs/ 实验产物；b2a-fs 备份时为 tester 运行中产物，为最后快照）
- `/tmp/b2a-payloads/`（10 个 payload）、`/tmp/b2a-cache.log`（探针原始日志）
- 宿主 `/tmp/` 脚本与 b2a-sanity.* / parse_b2a.py / run_b2a.sh / show_anchors2.sh

### 4. 模型（本体未备份，记录路径即可）

- `/root/models/Qwen3.8-27B-NVFP4-RTX5090/`（NVFP4 权重，13GB+；AutoDL 关机保留数据盘，原路径仍可用；
  来源：HuggingFace 上 Qwen3.8-27B NVFP4/RTX5090 专用权重）。清单与 config.json sha256 见 model-summary.txt。
- `/root/models/Qwen3.8-27B-DSpark-BF16/` 同目录存在（未备份本体）。

### 5. 校验与启动

```
md5sum -c 对照上表   # 或 md5sum <file> 与上表比对
bash launch-b0.sh    # 启动；健康检查 http://localhost:8021/v1/health
```
