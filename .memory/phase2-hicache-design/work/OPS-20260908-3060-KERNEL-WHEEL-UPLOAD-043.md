# OPS-20260908-3060-KERNEL-WHEEL-UPLOAD-043

status: blocked
task_id: D3060-KERNEL-WHEEL-UPLOAD-043
orchestration_epoch: 20260908-3060
role: devops-executor

## Summary

The verified local wheel was transferred resumably to the requested remote path and
the remote size/SHA256 matched the local artifact. The prescribed pip installation
did not start because the requested destination filename is not a valid wheel
filename: it omits the Python ABI/platform tags. No alternate rename or installation
method was attempted.

## Commands and outputs

Local verification:

    stat -c '%n %s bytes' /tmp/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl
    /tmp/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl 377094734 bytes

    sha256sum /tmp/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl
    5fee1007113c988bf6d448eca4706f7959631d449a429eb790a70bf89ab0ef04  /tmp/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl

Transfer command (resumable):

    rsync -av --partial --progress -e 'sshpass -e ssh -p 27460 ...' /tmp/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl root@i-1.gpushare.com:/hy-tmp/sglang_kernel-0.4.6.post1.whl

Transfer result:

    total size is 377,094,734
    speedup is 1.05

Remote verification:

    stat -c '%s' /hy-tmp/sglang_kernel-0.4.6.post1.whl
    377094734

    sha256sum /hy-tmp/sglang_kernel-0.4.6.post1.whl
    5fee1007113c988bf6d448eca4706f7959631d449a429eb790a70bf89ab0ef04  /hy-tmp/sglang_kernel-0.4.6.post1.whl

Prescribed install command:

    /root/sglang-env-3060-4b/bin/pip install --no-deps --force-reinstall /hy-tmp/sglang_kernel-0.4.6.post1.whl

Output:

    ERROR: Invalid wheel filename (wrong number of parts): 'sglang_kernel-0.4.6.post1'

## Changed resources

- Remote file created/updated: `/hy-tmp/sglang_kernel-0.4.6.post1.whl`
- Size: `377094734` bytes
- SHA256: `5fee1007113c988bf6d448eca4706f7959631d449a429eb790a70bf89ab0ef04`
- No package installation occurred, so no environment package state was changed by this task.

## Verification evidence

- Remote byte count equals local byte count.
- Remote SHA256 equals local SHA256.
- Pip metadata, `import sgl_kernel`, Torch CUDA, and an `sgl_kernel` op/module were not checked because installation was rejected by pip before those steps.

## Followups

Provide a fresh Task ID and authorization for a valid wheel filename/install path (for
example, preserving the full tagged wheel filename), then rerun the prescribed install
and post-install verification.

## Open issues

- The requested destination basename `/hy-tmp/sglang_kernel-0.4.6.post1.whl` is invalid for pip wheel parsing.
- Installation and runtime verification remain incomplete.
- No secret was written to this report.
