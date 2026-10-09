# G3-IQ3-SM86-BUILD-ACCEL-20260908

ENTRY: ACCEPT

Status: paused/pending

Authorized isolated build:
`175.155.64.171:22109`, `/data/qwen3-g3-baseline/g3-iq3-sm86-isolated-build-20260908/cmake-build`.

The existing Ninja process was verified as PID 555601 under the isolated CMake
build (parent PID 555600). Only those identified build processes were terminated;
the CMake cache and object files were preserved. The production v1 service PID
503601 on port 8035 was not touched.

Exact resume command:
```sh
cd /data/qwen3-g3-baseline/g3-iq3-sm86-isolated-build-20260908/cmake-build
/data/sglang-qwen35-env/bin/cmake --build . --parallel 8
```

It was launched detached with output redirected to:
`/data/qwen3-g3-baseline/g3-iq3-sm86-isolated-build-20260908/logs/cmake-build-accel-20260908.log`.
Resume wrapper PID 566317; CMake PID 566318; Ninja PID 566319.

Observed progress before pause: Ninja active, `[2/484] Building CUDA object .../kvcacheio/transfer.cu.o`.
At the user's pause request, only the identified isolated build tree PIDs
566319 (Ninja), 566318 (CMake), and 566317 (wrapper) were sent SIGTERM. A
post-stop check found all three absent. PID 503601 and port 8035 production v1
were unchanged. No final exit status or `common_ops*.so` was available; final
status remains pending. Raw status evidence is in
`work/raw/g3-iq3-sm86-build-accel-20260908/status.txt`.

Open issue: if resumed under a fresh authorization, record build outcome,
final shared-object paths, and hashes. Existing cache, objects, and log were
retained. No deployment or service restart was performed.
