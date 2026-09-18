# PROD-MODELID-GOLIVE-DECISION-20260918

## Task

Bounded diagnostic to determine if the model-id mismatch (`/data/models/qwen35-9b-w4a16` vs consumer-expectation `qwen35-9b-local`) blocks a consumer request, and to resolve how the served model name is determined.

## Scope

- READ-ONLY except for exactly 2 HTTP probes to 127.0.0.1:30000
- No restart/stop/start/signal, no config edits, no git mutation, no GPU lock, no server launch
- Source inspection of `/opt/sglang/local-prod-v1.2.1-candidate/src` for served model name resolution
- Produce single artifact: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/PROD-MODELID-GOLIVE-DECISION-20260918.md`

## Result

NOT-A-BLOCKER: The consumer's expected model id `qwen35-9b-local` works without error (HTTP 200).
Recommended fix: Option G (cheapest) — update the gateway's model registry to the advertised id; no prod restart needed.

## Evidence

### Decisive probe
```
curl -sS -w '\n%{http_code}\n' -X POST http://127.0.0.1:30000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen35-9b-local","messages":[{"role":"user","content":"ping"}],"max_tokens":4}'
```

Response:
```
200
{"id":"60676270b0894e67b5ec59b68f36e7b9","object":"chat.completion","created":1789682593,"model":"qwen35-9b-local","choices":[{"index":0,"message":{"role":"assistant","content":"","reasoning_content":"Thinking Process:\n\n","tool_calls":null}...}
```
HTTP 200, body includes `"model":"qwen35-9b-local"`. Service accepts the consumer id; mismatch is not a blocker.

### Control probe
```
curl -sS -w '\n%{http_code}\n' -X POST http://127.0.0.1:30000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"/data/models/qwen35-9b-w4a16","messages":[{"role":"user","content":"ping"}],"max_tokens":4}'
```

Response:
```
200
{"id":"583d201fadc648009fa2b61be5b2067a","object":"chat.completion","created":1789682593,"model":"/data/models/qwen35-9b-w4a16","choices":[{"index":0,"message":{"role":"assistant","content":"Okay, the user"
```
HTTP 200, body includes `"model":"/data/models/qwen35-9b-w4a16"`. Advertised id works.

### How served model name is determined (file:line)
- `/opt/sglang/local-prod-v1.2.1-candidate/src/docs/docs/advanced_features/server_arguments.mdx` line 1102:  
  `--served-model-name` (CLI argument) overrides the model name returned by `v1/models`. Defaults to `--model-id` when set, otherwise `--model-path`.
- Request log example: `GET /get_model_info` → model name comes from server_args.served_model_name (see `/docs/references/multi_node_deployment/deploy_on_k8s.mdx` line 251 and `/docs/sglang-diffusion/api/cli.mdx` line 78).
- Runtime priority: CLI override (frozen at freeze time) → model-id is internal routing; the exposed public name in `/v1/models` is the `--served-model-name`.

No runtime/env mechanism to set served model name without editing the frozen launcher (no env var or config file). Mechanism: CLI-only.

## Defects / blockers

None. Service is UP, `/health` 200, `/v1/models` 200, and both model ids work at runtime.

## Remaining claims / exclusions

- Unknown from this host: gateway-side discovery policy (how 192.168.1.203 decides which ids to expose to consumers); whether a different gateway could enforce strict id matching.
- Not investigated: the internal `/server_info` endpoint's `served_model_name` field may differ from the OpenAI `v1/models` name; remains unobservable.

## Terminal state: DONE
