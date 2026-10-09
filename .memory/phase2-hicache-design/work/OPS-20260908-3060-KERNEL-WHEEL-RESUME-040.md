# OPS-20260908-3060-KERNEL-WHEEL-RESUME-040

status: blocked
task_id: D3060-KERNEL-WHEEL-RESUME-040
epoch: 20260908-3060
role: devops-executor

## Summary

The requested wheel resume could not complete because the RTX3060 host repeatedly failed TLS handshakes to files.pythonhosted.org (`curl` error 35, unexpected EOF). No installation or runtime verification was performed.

## Authorized procedure and evidence

- Connected to `root@i-1.gpushare.com:27460`; remote hostname reported `I2aff9805ac001019d1`.
- Read repository `AGENTS.md`; no conflicting procedure was found.
- Existing matching partials found and preserved:
  - `/tmp/pip-unpack-plosyort/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl`: 17,301,504 bytes (largest selected)
  - `/tmp/pip-unpack-1m77l4l8/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl`: 17,039,360 bytes
- Official PyPI metadata identified:
  - URL: `https://files.pythonhosted.org/packages/d9/d9/d9d9fd8d0b81f6e14bb1f5afcdbe99e7cd8a3862b7b70450660217ad70df59ee/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl`
  - Size: 377.1 MB (PyPI page); expected SHA256: `5fee1007113c988bf6d448eca4706f7959631d449a429eb790a70bf89ab0ef04`
- Copied the largest partial to `/hy-tmp/sglang_kernel-0.4.6.post1.whl`.
- Ran bounded `timeout 600 curl -fL --retry ... -C -` twice, including IPv4/HTTP1.1 retry. Both failed before receiving additional bytes with `curl: (35) ... unexpected eof while reading`.
- Destination remains the preserved partial at 17,301,504 bytes. No source build, Torch upgrade, model/server/benchmark action, 3090 action, or deletion was performed.

## Changed resources

- Created/overwrote `/hy-tmp/sglang_kernel-0.4.6.post1.whl` with the selected partial copy, same 17,301,504-byte length.
- Existing `/tmp/pip-unpack-*` partials were not modified or deleted.

## Verification

Not reached: full-size check against the PyPI size, SHA256, `unzip -t`, pip install, `import sgl_kernel`, package metadata, and torch op loading. The preserved partial is not a complete wheel.

## Followups

Retry the same authorized curl resume after the host's TLS connectivity to files.pythonhosted.org is restored.

## Open issues

- Remote TLS transport to files.pythonhosted.org consistently terminates with OpenSSL unexpected EOF; installation remains pending.
- Extra work or alternate download mechanisms require a new Task ID.
