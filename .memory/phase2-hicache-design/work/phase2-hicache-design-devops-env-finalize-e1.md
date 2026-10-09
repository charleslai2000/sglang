# sglang 3090 环境收尾报告

## status
done

## artifacts
- 目标机器: 175.155.64.171:22151 (RTX 3090, 24GB)
- SSH 免密: 已配置（ed25519 公钥写入 /root/.ssh/authorized_keys）
- Conda env: `sglang-patch` (python 3.10.21)
- Editable install: `pip install -e /root/sglang-b1-continuity/python/` (SGLANG_BUILD_RUST_EXTS=none)
- 报告文件: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-hicache-design-devops-env-finalize-e1.md`

## evidence

### 1. SSH 免密配置
- 22151 原始状态: 无 SSH 密钥，sshpass 密码 `K0@dx` 可用但每次需交互
- 操作: `sshpass -p 'K0@dx' ssh ... "mkdir -p /root/.ssh && cat >> /root/.ssh/authorized_keys"` 将本地 ed25519 公钥写入 22151
- 验证: `ssh -p 22151 -i /home/charles/.ssh/id_ed25519 -o BatchMode=yes root@175.155.64.171 "echo SSH_KEY_AUTH_OK"` → 输出 `SSH_KEY_AUTH_OK`，exit 0

### 2. sglang editable 安装
- 命令: `SGLANG_BUILD_RUST_EXTS=none pip install -e /root/sglang-b1-continuity/python/`
- 退出码: 0（Successfully installed sglang-0.0.0.dev0）
- 验证: `python -c "import sglang; print(sglang.__file__)"` → `None`（namespace package，可接受）
- 验证: `python -c "import sglang.srt; print(sglang.srt.__path__)"` → `_NamespacePath(['/root/sglang-b1-continuity/python/sglang/srt'])` — 正确指向源树
- .pth 文件: `/root/miniconda3/envs/sglang-patch/lib/python3.10/site-packages/__editable__.sglang-0.0.0.dev0.pth` 存在
- Finder: `__editable___sglang_0_0_0_dev0_finder.py` 存在，MAPPING 指向 `/root/sglang-b1-continuity/python/sglang`

### 3. 完整导入验证
```
python -c "import sglang, flashinfer, triton, torch; print('ALL_IMPORTS_OK')"
→ ALL_IMPORTS_OK
```
```
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
→ True NVIDIA GeForce RTX 3090
```
```
python -c "import sgl_kernel; print(sgl_kernel.__file__)"
→ /root/miniconda3/envs/sglang-patch/lib/python3.10/site-packages/sgl_kernel/__init__.py
```
```
python -c "import flashinfer; print(flashinfer.__file__)"
→ /root/miniconda3/envs/sglang-patch/lib/python3.10/site-packages/flashinfer/__init__.py
```
```
python -c "import triton; print(triton.__file__)"
→ /root/miniconda3/envs/sglang-patch/lib/python3.10/site-packages/triton/__init__.py
```

### 4. sgl_kernel .so 文件（无需从 24052 补传）
22151 上 sgl_kernel 目录已包含所需 .so：
- `flash_ops.abi3.so`
- `flashmla_ops.abi3.so`
- `infllm_ops.cpython-310-x86_64-linux-gnu.so`
- `spatial_ops.abi3.so`
与 24052 对比一致，无需额外传输。

### 5. 模型 Qwen3.5-9B-w4a16 状态
目录: `/root/models/Qwen3.5-9B-w4a16/`
文件:
- `chat_template.jinja` (7756 B) — 存在
- `model_mtp.safetensors` (99186176 B / ~95MB) — 存在
- `tokenizer.json` (19989343 B / ~19MB) — 存在
- **`model.safetensors` — 缺失**（任务中已指出：之前传输不完整，只有 model_mtp.safetensors）

按任务纪律：不下载、不传输，等 orchestrator 决策源。

### 6. 24052 对比（参考部署机）
24052 上 sglang 也是 editable 形态，`sglang.__file__` 同样为 `None`，`sglang.srt.__path__` 指向 `/root/sglang-b1-continuity/python/sglang/srt`。22151 行为一致。

## summary
- sglang editable 安装完成，import 全部正常，sglang 源树正确指向 `/root/sglang-b1-continuity/python/sglang`
- CUDA/RTX 3090 确认可用
- sgl_kernel .so 文件齐全，无需从 24052 补传
- SSH 免密已配置，后续操作无需密码
- 模型 `Qwen3.5-9B-w4a16` 缺失 `model.safetensors`，待 orchestrator 决策
- 环境整体可用（缺模型文件）

## followups
1. 模型 `model.safetensors` 传输由 orchestrator 决策，devops 不执行下载/传输
2. 后续如需启动 sglang 推理引擎，需另行派发（不在本任务范围）

## open_issues
- 无
