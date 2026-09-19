# PROD-LIVENESS-CHECK-20260918

Status: DONE

## Task
Ultra-small READ-ONLY liveness probe of the production SGLang service on port 30000, using the exact
commands specified in the dispatch.

## Scope
Read-only observation. No writes outside this artifact. No process start/stop/signal. No GPU
allocation. No inference requests (only the specified GETs on `/health` and `/v1/models`). Commands
run as given.

## Result
SERVICE_ONLINE = yes
HTTP codes: 127.0.0.1:30000/health = 200, 127.0.0.1:30000/v1/models = 200, 192.168.20.250:30000/health = 200
Serving pid: 1851500 (`sglang.launch_server`, scheduler child pid 1851964)
Served model: `/data/models/omnicoder-9b-gptq-int4` (max_model_len 131072)
Observation timestamp (UTC): 2026-09-18T19:56:35Z

## Evidence
Raw command output, in dispatch order.

1. `curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1:30000/health`
```
200
```

2. `curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1:30000/v1/models`
```
200
```

3. `curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://192.168.20.250:30000/health`
```
200
```

4. `date -u`
```
Fri Sep 18 19:56:35 UTC 2026
```

5. `ss -ltnp | grep -E ':30000|:30164|:30165'`
```
LISTEN 1      2048         0.0.0.0:30000      0.0.0.0:*    users:(("python",pid=1851500,fd=68))
```
(Only :30000 matched; :30164 and :30165 had no listeners.)

6. `pgrep -af 'sglang.launch_server|sglang::scheduler'`
```
1851500 /opt/sglang/local-prod-v1.2.1-candidate-M2/env/bin/python -u -m sglang.launch_server --model-path /data/models/omnicoder-9b-gptq-int4 --host 0.0.0.0 --port 30000 --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 262144 --context-length 131072 --max-running-requests 8 --max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer --linear-attn-prefill-backend triton --linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 --reasoning-parser qwen3 --tool-call-parser qwen3_coder --enable-metrics --export-metrics-to-file --export-metrics-to-file-dir /tmp/opencode/prod-service-20260917/logs/m2-20260918T190239Z-1851237 --disable-prefill-cuda-graph
1851964 sglang::scheduler
1858494 /bin/bash -c pgrep -af 'sglang.launch_server|sglang::scheduler'; echo "---GREP_EXIT:$?"
```
(The third line is the probe's own shell, not a service process.)

7. `cat /tmp/opencode/prod-service-20260917/state/gpu-owner.json`
```
{
  "gpu": "GPU-2e3ed202-3655-d919-0a64-259209bc6587",
  "role": "m2",
  "state": "held",
  "pid": 1851500,
  "port": 30000,
  "run_id": "m2-20260918T190239Z-1851237",
  "l3_namespace": "",
  "tree": "/opt/sglang/local-prod-v1.2.1-candidate-M2",
  "identity": "LOCAL-PROD-v1.2.1-M2",
  "lock_generation": 1,
  "updated_at_utc": "2026-09-18T19:04:31Z",
  "note": "serving"
}
```

8. `cat /tmp/opencode/gpu-3090.lock`
```
{"owner": "supervise-m2-m2-20260918T190239Z-1851237", "pid": 1851473, "generation": 1, "acquired": "2026-09-18T19:02:39Z"}
```

9. `nvidia-smi --query-gpu=memory.used,memory.free,utilization.gpu --format=csv`
```
memory.used [MiB], memory.free [MiB], utilization.gpu [%]
19067 MiB, 5058 MiB, 0 %
```
`nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv`
```
pid, process_name, used_gpu_memory [MiB]
1851500, /opt/sglang/local-prod-v1.2.1-candidate-M2/env/bin/python, 300 MiB
1851964, sglang::scheduler, 18752 MiB
```

Supplementary (body of the already-authorized `/v1/models` GET, read to determine the served model;
no additional network endpoint was called):
```
{"object":"list","data":[{"id":"/data/models/omnicoder-9b-gptq-int4","object":"model","created":1789761398,"owned_by":"sglang","root":"/data/models/omnicoder-9b-gptq-int4","parent":null,"max_model_len":131072}]}
```

## Defects or blockers
- None. All nine specified commands executed successfully (exit 0) on the first attempt.
- `ss` showed only a :30000 listener; there were no listeners on :30164 or :30165. This is an
  observation, not a defect, since those ports were not documented as required by this probe.
- No unreadable-path errors occurred; both state files were read successfully.

## Remaining claims or exclusions
- This probe establishes only HTTP liveness/reachability and process/GPU presence at the observation
  timestamp. It makes no claim about inference correctness, latency, throughput, or model output
  quality.
- No inference request was sent, so serving health under load is not established.
- GPU utilization 0% and the 300 MiB launcher usage are reported as-is; no claim is made about
  whether the service was actively serving a request at the sampled instant.
- The external-interface check (192.168.20.250) confirms reachability from this host only.
- No process, lock, or GPU state was modified; the service was left exactly as found.

## Terminal state
DONE
