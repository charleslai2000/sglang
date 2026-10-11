# PROD-BIND-DIAG-20260918

- **工作标题：** PROD-BIND-DIAG-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/PROD-BIND-DIAG-20260918.md`：**
Task ID: PROD-BIND-DIAG-20260918
Role: devops (read-only diagnosis; no service actions, no config edits)
Repo: /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt (branch 3090-24g-opt, HEAD 910e5a01c0)
Host clock at diagnosis: 2026-09-17T21:05–21:07Z (UTC, `date -Is`)

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** CONFIRMED — the production SGLang is loopback-only (

**`phase2-hicache-design/agents/PROD-BIND-DIAG-20260918.md`：**
**VERDICT: CONFIRMED — the production SGLang is loopback-only (`--host 127.0.0.1` hard-coded in the frozen launcher), so
192.168.20.250:30000 is unreachable. The causal attribution "the 03:08 restart changed it to loopback" is REFUTED:
every frozen production launcher (v1, v1.1, v1.1.2, v1.2, v1.2.1) has always hard-coded 127.0.0.1; the external
listener on :30000 was the separate opencodex DEV provider, which was moved to :30001 at 16:21:19Z (commit
7d08fb26f8) and then stopped at 16:30:12Z. Fix is FREEZE-REQUIRING (repo template + audit-allowance change + new
v1.2.2 freeze + prod restart). Not blocked by any host firewall.**
Corollaries:
- 192.168.20.250 IS an address of THIS host (`eth0`), hostname `sglang-build` = "VM 2500".
- No host firewall is filtering :30000; "Connection refused" is the expected signature of a loopback-only bind.
- The launcher audit (`audit_launcher.py`) fails closed on any `--host` value change vs the v1.1 reference; a bind
  change must be explicitly declared there before a new freeze can pass.

### 报告列出的产物/证据
- `phase2-hicache-design/agents/PROD-BIND-DIAG-20260918.md`：- Host: `hostname`, `hostname -I`, `ip -4 addr show`; `ss -ltnp`; `pgrep -af sglang.launch_server`;
  `ps -o pid,ppid,etime,cmd -p 1602781,1602808,1603222`.
- Config: `3090-dev/tools/freeze/templates/launch.sh.tmpl:146`;
  `/opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh:146` + sha256
  `38487942de63cb56249dae5080d2caef281364dcbac6c92ac53b1ff916672914`;
  `3090-dev/deploy/conf/provider.env:69,72,75`; `3090-dev/deploy/bin/provider-common.sh:251`;
  scaffold `conf/service.env`, `bin/supervise.sh:43-50`, `bin/start.sh:74-84`.
- Audit/freeze: `3090-dev/tools/freeze/pysrc/audit_launcher.py:53-66,83-95,150-190`;
  `3090-dev/tools/freeze/bin/launcher-repin.sh:37,88-121`;…（节选；见来源报告）

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `2d4e33a832`, `7d08fb26f8`, `910e5a01c0`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/PROD-BIND-DIAG-20260918.md` → `.memory/phase2-hicache-design/agents/PROD-BIND-DIAG-20260918.md`; SHA256 `eabaec2fe8ed36d48e2296dc85697e791b901cd5f1f8aa8e9ea08dd45f9d20dc`; source state `tracked`
