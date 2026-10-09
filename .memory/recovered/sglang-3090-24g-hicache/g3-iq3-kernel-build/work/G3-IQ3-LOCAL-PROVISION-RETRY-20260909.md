# G3-IQ3-LOCAL-PROVISION-RETRY-20260909

Invocation: `INV-G3-IQ3-LOCAL-PROVISION-002`  
Status: **pending**

## Executed

Offline installation used exactly:

```text
/mnt/data/qwen3-g3-baseline/venv/bin/python -m pip install --no-index --require-hashes --find-links=/mnt/data/qwen3-g3-baseline/wheels -r /mnt/data/qwen3-g3-baseline/artifacts/torch-cu130-wheelhouse-requirements.txt
```

The wheelhouse installation completed successfully; raw output is in
`raw/g3-iq3-local-provision-retry-20260909/pip-install.log`. Installed versions include
`torch 2.13.0+cu130` and `triton 3.7.1`. The requirements are the root-provided hash-pinned
set; no external index was used.

The approved model URL from `artifacts/model-url.txt` was resumed with curl `-C -` into the
existing file. No file was removed or replaced. The download remains active (curl PID 400700,
parent shell PID 400698) and the file is currently `6,389,214,791 / 11,771,546,784` bytes.
Raw output: `raw/g3-iq3-local-provision-retry-20260909/model-download.log`.

## Validation

With `CUDA_VISIBLE_DEVICES=''`, torch imported successfully and reported
`2.13.0+cu130`; `torch.cuda.is_available()` was not reached because the editable SGLang import
stopped at the missing `numpy` dependency. `sglang` therefore did not import. `transformers`
and `flashinfer` were not validated. Raw output is in `imports.log`.

No GPU process was started and no repository product file was changed. `git diff --check`
passed. Wheelhouse checksum-record checksum:
`cb681a283d5b54c1166a871a82d10db5830cc9cf60b1dfc651eb0d7573ce3865`.

## Open issues / follow-up

- Model download must finish at exactly `11,771,546,784` bytes, then be SHA-256 checked against
  `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810`.
- The wheelhouse does not include the editable SGLang runtime dependencies (`numpy`,
  `transformers`, `flashinfer`, and others reported by pip); installing them requires a fresh
  authorized provision task or an expanded root-prepared wheelhouse. No unpinned/network install
  was attempted.

The model remains actively downloading; final size/hash and imports are pending.

`torchvision 0.29.0+cu130` was installed from the official PyTorch cu130 index with
`--no-deps`, preserving `torch 2.13.0+cu130`; installation succeeded. A no-GPU import verified
torchvision, while editable SGLang advanced to its next missing dependency: `IPython`. Raw logs:
`torchvision-install.log` and `sglang-import-after-tv.log`.

`IPython 9.17.1` and its direct dependencies were then installed. With
`CUDA_VISIBLE_DEVICES='' PYTHONPATH=python`, both `torchvision 0.29.0+cu130` and editable
`sglang 0.5.20.dev16+g5c5f5e3b2` import successfully. Raw logs are
`ipython-install.log` and `sglang-import-ipython.log`.

The approved GGUF download is still active (curl PID 414878), now at
`10,458,937,528 / 11,771,546,784` bytes. Final exact-size and SHA-256 verification remain
pending.

## Follow-up provision

Per the fresh provision instruction, a non-Torch dependency install was started with:

```text
CUDA_VISIBLE_DEVICES='' /mnt/data/qwen3-g3-baseline/venv/bin/python -m pip install --timeout 60 --retries 3 numpy transformers==5.12.1 'flashinfer-python[cu13]==0.6.17' watchfiles xgrammar==0.2.1 xxhash zstandard
```

It is still active (PIDs 407399/407401); raw output is in
`raw/g3-iq3-local-provision-retry-20260909/non-torch-install.log`. It has not installed
the requested packages yet. The model had reached `7,742,340,679 / 11,771,546,784` bytes at
the latest poll. No GPU allocation or product-file modification occurred.
## Finalization

The approved GGUF reached exactly `11,771,546,784` bytes. The final SHA-256 is
`64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810`, matching the approved
expected hash. The curl process has exited; the final hash is recorded in
`raw/g3-iq3-local-provision-retry-20260909/model-sha256-final.txt`.

Final no-GPU import verification passed with `CUDA_VISIBLE_DEVICES=''` and editable
`PYTHONPATH=python`: torch `2.13.0+cu130`, torchvision `0.29.0+cu130`, numpy `2.5.3`,
transformers `5.12.1`, flashinfer `0.6.17`, xgrammar (version unavailable), and sglang
`0.5.20.dev16+g5c5f5e3b2`. Raw output: `final-imports.log`.

Invocation status: **done**. No service was started and no GPU was allocated.
