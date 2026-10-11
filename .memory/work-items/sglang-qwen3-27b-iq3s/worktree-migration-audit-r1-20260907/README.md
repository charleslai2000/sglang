# WORKTREE-MIGRATION-AUDIT-R1-20260907

- **工作标题：** audit
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
只读比较待退役的旧 linked worktree 与当前 clone，核对 Git 身份/差异、源文件与 memory/evidence 是否需要迁移、敏感材料边界及安全退役前提。

## 实际改了什么
只读 reviewer audit；没有修改 product file、Git ref、worktree、remote、process 或 benchmark。生成 `.memory/worktree-migration-20260907/work/audit.md`，并保存比较证据/哈希。报告明确指出旧 worktree 无 old-only 非忽略文件；current-only 任务记忆应保留；`serving.py` 有当前独有的 GGUF guard，不应被旧树覆盖；credential-related 文件按元数据识别并保密，不读取内容。

## 生成结果与验收
Audit 完成，产出迁移 disposition：共同文件无需同步；旧树五个修改路径与 current 字节相同；唯一源码分歧应保留 current 版本；忽略缓存不迁移。审计发现旧 linked worktree dirty，正常 remove 会拒绝，不能直接删除目录，否则可能留下 stale metadata。该项是退役前审计，不等同于后续退役已执行。

### 报告列出的产物/证据
- `worktree-migration-20260907/work/audit.md`：Key commands run read-only:
```text
git show -s --format='%H %T %P %s' HEAD
git merge-base HEAD origin/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s
git status --porcelain=v1 --untracked-files=all
git diff --name-status <old-HEAD> <current-HEAD>
git worktree list --porcelain
git ls-files; git ls-files --others --exclude-standard
cmp -s <old>/<path> <current>/<path>
sha256sum <modified-or-untracked-path>
```
Final audit status: **done**. No sync, deletion, Git mutation, remote access,
or benchmark action was performed.

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `dac6db1ebabdb80209b757fd063cf53e05c091e7`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `worktree-migration-20260907/work/audit.md` → `.memory/g3-worktree-migration/work/audit.md`; SHA256 `6c5d8021a04b463d0862c7dce1e93307b7c9c1dab5671f04d74b31f3c82e94fd`; source state `local-only`
