# OPS-20260908-3060-KERNEL-WHEEL-LOCAL-041

status: blocked
task_id: D3060-KERNEL-WHEEL-LOCAL-041
epoch: 20260908-3060
role: devops-executor

## Summary

The authorized local download did not complete. The exact official URL from
`OPS-20260908-3060-KERNEL-WHEEL-RESUME-040` returned HTTP 404 on the local
network path. No alternate URL, remote host, package installation, product
source change, or deletion was performed.

## Procedure and evidence

- Read the referenced resume report and local `AGENTS.md`.
- Target path checked before download:
  `/tmp/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl`
  was absent.
- Official URL used exactly as reported:
  `https://files.pythonhosted.org/packages/d9/d9/d9d9fd8d0b81f6e14bb1f5afcdbe99e7cd8a3862b7b70450660217ad70df59ee/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl`
- Expected SHA256 from the referenced report:
  `5fee1007113c988bf6d448eca4706f7959631d449a429eb790a70bf89ab0ef04`.
- Expected size was recorded in the referenced report only as rounded
  `377.1 MB`; no exact byte count was available there.

## Commands and outputs

1. Header probe, bounded to 60 seconds:

   `curl --fail --location --head --connect-timeout 20 --max-time 60 <official-url>`

   Output included: `HTTP/2 404`, `content-length: 0`,
   `reason: Incorrect project bucket`.

2. Bounded download, maximum 600 seconds, two retries:

   `timeout 600 curl -fL --retry 2 --retry-delay 2 --retry-all-errors --connect-timeout 20 --max-time 600 -o <target> <official-url>`

   Output: three attempts each ended with
   `curl: (22) The requested URL returned error: 404`; final
   `curl_exit=22`; `artifact_absent`.

## Changed resources

- No artifact was created or changed.
- No product source, remote host, installed package, or existing file was modified.

## Verification

Not reached because the official URL returned 404 and no artifact exists:
full expected-size check, SHA256 check, and `unzip -t`.

## Followups

Retry the same exact authorized URL only after its availability is restored,
under a new Task ID if additional work is requested.

## Open issues

- The supplied official URL currently returns HTTP 404 (`Incorrect project bucket`).
- Exact expected byte size is not present in the referenced report; only `377.1 MB`
  is recorded.
- Download and verification remain pending.
