# T003 — 服务、桥接与功能验证

Status: DONE
Work area: ops
Objective: 启动 OpenAI-compatible 服务，验证监听、health/models、真实生成及 harness 连接。
Inputs: CLI 验证、服务启动、网络桥接、SWE harness recon 与 smoke 记录。
Completion: 服务在 `0.0.0.0:8080` 监听，真实请求成功，明确公网失败与隧道替代路径。
Result: DONE。SSH 隧道路径工作；公网路径不可用但未影响 harness 验证。
Remaining: None。
