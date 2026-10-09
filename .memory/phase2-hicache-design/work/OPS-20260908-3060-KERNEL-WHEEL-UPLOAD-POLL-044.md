# OPS-20260908-3060-KERNEL-WHEEL-UPLOAD-POLL-044

- Task ID: D3060-KERNEL-WHEEL-UPLOAD-POLL-044
- Orchestration epoch: 20260908-3060
- Role: devops-executor
- Status: done
- Scope: read-only inspection of `/hy-tmp/sglang_kernel-0.4.6.post1.whl` and transfer processes on `root@i-1.gpushare.com:27460`.

## Command

Executed over SSH (password supplied privately; not recorded):

```sh
ssh -p 27460 root@i-1.gpushare.com \
  'p=/hy-tmp/sglang_kernel-0.4.6.post1.whl; if [ -e "$p" ]; then stat -c '\''exists=1 size=%s mtime=%y type=%F'\'' "$p"; if [ -f "$p" ]; then sha256sum "$p"; fi; else echo '\''exists=0'\''; fi; echo '\''processes:'\''; ps -eo pid=,user=,stat=,etime=,args= | grep -E '\''[s]cp|[s]sh.*(scp|sglang_kernel-0.4.6.post1.whl)|[s]sh.*i-1.gpushare.com'\'' || true'
```

## Output and evidence

```text
exists=1 size=377094734 mtime=2026-09-08 22:40:08.894113101 +0800 type=regular file
5fee1007113c988bf6d448eca4706f7959631d449a429eb790a70bf89ab0ef04  /hy-tmp/sglang_kernel-0.4.6.post1.whl
processes:
  19973 root     Ss         00:03 bash -c ...inspection command...
  19978 root     S          00:00 grep -E ...inspection filter...
```

The wheel is present as a regular file, size `377094734` bytes, with mtime `2026-09-08 22:40:08.894113101 +0800`. SHA-256 is `5fee1007113c988bf6d448eca4706f7959631d449a429eb790a70bf89ab0ef04`; hashing completed successfully. No independent `scp`/SSH transfer process was observed. The listed shell and grep entries are the inspection command itself.

## Changed resources

None. No remote or local resource was modified.

## Verification

- Remote `stat` confirmed existence, regular-file type, byte size, and mtime.
- Remote `sha256sum` returned a complete digest.
- Remote process listing found no transfer process beyond the inspection shell/filter.

## Followups

None.

## Open issues

None.
