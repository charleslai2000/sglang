# O003 — Swift canonical service and legacy provider cleanup

Date: 2026-09-23

## Swift service

- Model: `/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf`, size 13,616,388,192; SHA256 `5ae067582f921ff9a1847ce4aab0b41ecad4c38c386e76fd4714f9a8b98e586e`, matching the local SHA256SUMS. Companion mmproj exists and matches `daa1116c9422fa390cc8688495da0e91781f92841dfc3b31a378ff252571745a`.
- Installed systemd unit `/etc/systemd/system/sglang-swift.service` (source definition `3090-dev/tools/swift-service/sglang-swift.service`), launcher `3090-dev/tools/swift-service/bin/swift-server`, controls `swiftctl {start|stop|restart|status}`. Enabled at boot. Runtime metrics under `/var/lib/sglang-swift/metrics`.
- Model name `ukisai/Swift-Qwen3.8-27b`; bind `0.0.0.0:30000`; max total tokens 8192. Uses existing M4 GGUF flags: tp=1, mem fraction .85, fp8_e4m3 KV, FlashInfer, Triton linear-attention, mamba extra_buffer/float32, decode CUDA graph max bs 8, prefill graph disabled, max running requests 8, qwen3 reasoning/qwen3_coder tool parsers. No HiCache acceptance was run.
- Python `/home/ubuntu/venvs/sglang-3090/bin/python`, `PYTHONPATH=/home/ubuntu/workspaces/3rdparty/sglang/python`; imported `sglang.__file__` and `_server*.so` both resolve inside canonical tree. Process environment pins the 3090 UUID.
- `GET /health` 200, `/v1/models` lists the expected model. Chat completion returned exact `SWIFT-SGLANG-READY`. After `systemctl restart`, health returned 200 and a completion returned `SWIFT-RESTART-READY`.
- GPU: RTX 3090, 24,576 MiB total; service used about 18,012 MiB, about 6,113 MiB free at observation.

## Legacy cleanup

- Confirmed DEV provider was DOWN, its state was role=free, no process referenced the provider tree/run root, and port 30001 was not bound. Removed `/opt/sglang/opencodex-provider-2d4e33a832` (full source snapshot) and `/opt/sglang/opencodex-provider-run` (old logs/metrics/state). Removed 248 MiB stale `/tmp/opencode/prod-service-20260917/logs` and `/state` after verifying stale PIDs were absent and the shared flock was free; cleared stale owner JSON under flock, preserving the lock inode.
- At initial cleanup time, M3/M4 envelopes and six frozen prod/test/M2 snapshots were retained because active contracts referenced them. Phase D1 later retired those contracts and removed all six snapshots plus the envelopes; `/opt/sglang` is now empty.
- `LEGACY_PROVIDER_SOURCE_REMOVED=YES` and `LEGACY_RUNTIME_OUTPUT_REMOVED=YES` for the obsolete DEV provider source/runtime. Falcon/model files and configs/secrets were untouched.

## Verification and limits

- Systemd active/running after restart; HTTP readiness/completion succeeded.
- One initial failed startup was due to root-owned runtime metrics directory; ownership corrected to ubuntu and service recovered. A later reuse of the old M4 envelope launcher was rejected by its hardcoded old HEAD (`c3ef82e...`); it was not bypassed. The successful service is the independent canonical systemd unit, not that envelope.
- This record does not claim `OLD_SGLANG_SOURCE_REFERENCES=ZERO`: old provider paths remain in historical audit records as factual references. Production config still references preserved frozen service snapshots by design.
