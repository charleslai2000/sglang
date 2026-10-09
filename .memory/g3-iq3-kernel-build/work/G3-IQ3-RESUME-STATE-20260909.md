# G3-IQ3-RESUME-STATE-20260909

- Task ID: `G3-IQ3-RESUME-STATE-20260909`
- Epoch: `E10`
- Role: `devops-executor`
- Invocation status: **blocked**

## Scope

仅尝试对已授权实验机 `175.155.64.171:22109` 做只读状态检查；未运行 benchmark，未启动/停止/重启/重配置服务，未修改远端文件。

## Procedure and evidence

本地先读取 `AGENTS.md`，确认要求保持 v1 服务不变、仅使用实验机、不得下载数据或进行破坏性操作。

尝试命令：

```text
ssh -o BatchMode=yes -o ConnectTimeout=10 -p 22109 root@175.155.64.171 '... ps/curl/ss/build-log/find/cuobjdump ...'
```

SSH 在建立会话前失败：

```text
WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!
Offending ECDSA key in /home/dev-codex/.ssh/known_hosts:7
Host key verification failed.
```

未绕过 host-key 检查，也未修改 `known_hosts`。

只读获取到的当前 presented host-key 指纹：

```text
RSA      SHA256:1NU28YYfXuSk5qb+ocl04wSzKprvWCBvY+LHRW2ayDY
ECDSA    SHA256:WrXLWlHm+eE4A5APmVomuVoWtget/2DBsGiQ/ICZ1fo
ED25519  SHA256:H7Y9k2ppZn1Xf7i1Uxj1v8MX7gLNb9N5iTJxHc9CfxE
```

此前 SSH 已知记录包含旧 ECDSA key；当前 presented ECDSA 指纹为 `SHA256:WrXLWlHm+eE4A5APmVomuVoWtget/2DBsGiQ/ICZ1fo`，因此身份变化尚未得到确认。

## Results

- Service health/PID/args: **未能读取**（SSH host-key gate 阻断）。
- Isolated build PID/progress/artifact: **未能读取**。
- SM86 ELF inspection: **未能执行**。
- Raw command output: 本报告保留 SSH 错误及指纹；未产生远端输出路径。
- Changed resources: **none**。

## Required unblock

需要用户/管理员确认该实验机新的 host key（至少确认上述 ED25519 指纹），或由控制面安全更新对应 `known_hosts`。确认后应以新 Task ID 重试状态检查；本次不得绕过校验。

Extra work requires a fresh Task ID.
