# P2-IO Phase 1 — T15 旁路化（e10）

## 1. status

done

按用户裁决 ①（T15 旁路化：保留实现+单测，默认 off，positive case，留档）与协调人
派发执行：`--hicache-restore-backup-park` 单点门控 `_backup_park_applies`，off = e8 前
基线（revoke 落到 `revoked_miss` → T9 genuine → recompute）；scheduler 侧 T15 与状态机
BACKUP_PENDING 分支保留为死路径（零删除）。本机全门 104+69+30+7+94 = 304 全绿；
RED→GREEN 已证明（无门控"恒 on"变体上 T15BypassOffTests 2/2 失败）。3090 同步与
p2io-design.md 6.8/ledger 文档由 orchestrator 执行。

## 2. artifacts

| 文件 | 改动 | 为什么 |
|---|---|---|
| `python/sglang/srt/server_args.py` | 新增 `hicache_restore_backup_park: A[bool, Arg(...), NS("memory")] = False`（:2853，插于 `hicache_restore_wait_timeout_s` 之后、`hicache_promotion_margin_tokens` 之前；CLI 自动派生 `--hicache-restore-backup-park`；无 env、不碰 environ.py） | T15 旁路的用户开关；默认 off 保持 e8 前基线 |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | ① `init_hicache`（:479）直读 `self.hicache_restore_backup_park = server_args.hicache_restore_backup_park`（构造期一次性，无 getattr）；② `_backup_park_applies`（:3016）函数体首行门控 `if not self.hicache_restore_backup_park: return False` | 单点门控：off 时 park 谓词恒 False，revoke 分类链（terminated → miss → insufficient → alloc_failed）与 drain 阈值上预检全部落回 e8 前既有分支 |
| `3090-dev/test_hicache_restore.py` | 64→69：`T15PositiveCaseTests`（flag on，3 项：park+span 注册 / ACK 推进 durable→backup_wait_ready / wake 链纯腿 RESTORING→READY）+ `T15BypassOffTests`（flag off，2 项：revoke 分类 miss 无 span / drain 预检不 park）；新增 `_drain_harness()` 惰性 import + 模块级 `_parked_cache(backup_park=...)`（协调人 6000/20000/20000 数值模型） | positive/negative case：off 语义被显式守卫；torch-free 纯套件与 cache 套件双模式（venv/stubenv）均可运行 |
| `3090-dev/test_drain_reentry.py` | 29→30：`_make_cache(tree_core, *, backup_park=True)` 参数化（harness 默认 on 保持既有 park 测试）；`_FakeController.mem_pool_host.alloc` 恒 None（off drain 测试走 pre-T15 路径不启动传输）；`_revoke` 加 `backup_park` 参数 + `test_flag_off_classifies_miss`（off 变体：同场景分类 miss） | harness 语义确认（协调人）：drain 默认 True；off 变体显式 False |
| `3090-dev/test_storage_regression.py` | `_make_cache` 加 `cache.hicache_restore_backup_park = True`（恒 True：该 harness 从不 park，但 revoke 路径读 flag） | 回归守卫不变（94 保持绿） |

未动：scheduler.py（T15 死路径保留）、hicache_restore.py 状态机（BACKUP_PENDING 行原样
保留）、feed 测试（`_restore_backup_wake_ready` 不读 flag）、extent/allocator/cache_controller。

## 3. evidence

RED（无门控"恒 on"变体 = 当前代码删去 `_backup_park_applies` 首行门控，即旧行为）：

```
$ python3 构建变体: /tmp/e9-red/unified_radix_cache_ungated.py（gate 行精确删除，count==1 断言）
$ DRAIN_TEST_MODULE_PATH=/tmp/e9-red/unified_radix_cache_ungated.py \
    PYTHONPATH=python:3090-dev python3 -m unittest 3090-dev.test_hicache_restore.T15BypassOffTests
  -> Ran 2 tests; FAILED (failures=2)
     AssertionError: 'revoked_backup_pending' != 'revoked_miss'（变体恒 on：park 了本应 miss 的场景）
```

GREEN（本机 venv = /home/charles/sglang-venv，torch 2.13.0+cu129；PYTHONPATH=python
强制本地树，`sglang.__file__ = .../python/sglang/__init__.py` 已验证）：

```
$ PYTHONPATH=python:test .../python -m unittest test_extent_file_backend_unit test_hicache_file_lru_unit
  -> Ran 104 tests OK
$ PYTHONPATH=python:3090-dev .../python -m unittest 3090-dev.test_hicache_restore
  -> Ran 69 tests OK   (64 + 5 新增)
$ PYTHONPATH=python:3090-dev .../python -m unittest 3090-dev.test_drain_reentry
  -> Ran 30 tests OK   (29 + 1 新增)
$ PYTHONPATH=python:3090-dev .../python -m unittest 3090-dev.test_hicache_restore_scheduler_feed
  -> Ran 7 tests OK
$ PYTHONPATH=python:3090-dev .../python -m unittest 3090-dev.test_storage_regression
  -> Ran 94 tests OK
$ PYTHONPATH=python:3090-dev python3 -m unittest 3090-dev.test_hicache_restore   （system python3，torch-free）
  -> Ran 69 tests OK   （纯套件 torch-free 承诺不破；新类经 stubenv 双模式验证）
$ .../python -m py_compile 5 个改动文件 -> COMPILE-OK
```

预存在失败（非本 epoch 引入，e8/e9 已记录）：test_unified_radix_cache_unittest
import-path quirk + GPU/MagicMock 错误，本轮未跑（未触碰相关文件）。

## 4. summary

T15 旁路化按用户裁决落地：机制实现（e9）+ 单测原样保留，默认 off 由
`--hicache-restore-backup-park` 单点门控。off 语义 = e8 前基线（正负用例双重守卫）：
park 谓词恒 False → revoke 分类与 drain 预检落回既有分支 → `revoked_backup_pending`
永不记录 → scheduler T15 分支不可达（死路径，零删除）→ 请求 recompute 或走
T6/T11 capacity 既有循环，行为逐字节等于 T15 引入前。启用时（flag on）T15 完整链路
（park → span → ACK 推进 durable → wake → demand re-issue → READY）由 positive case
守卫。RED→GREEN 以"无门控恒 on 变体"证明 off 测试确实守卫新行为（变体下 off 测试
2/2 失败）。

## 5. followups

- orchestrator：3090 同步（server_args.py、unified_radix_cache.py + 3 个测试文件，
  md5 双侧）；p2io-design.md 6.8 留档 + ledger append（Phase 0 文档）
- 3090 冒烟：flag 默认 off 下短 M4T run 确认无回归（对照 e5 B=1.158s）；
  可选 flag on 冒烟验证 T15 触发路径
- Phase 2（A−B 逐样本指标，tester）与 Phase 3（Ready Horizon v0）按主计划继续

## 6. open_issues

- flag 构造期读入点 init_hicache 在 storage 使能路径必然执行；若未来出现绕过
  init_hicache 的 storage 初始化路径，attr 缺失会 AttributeError（当前无此路径，
  harness 已显式补值）
- off 下 `_backup_wait_spans`/`_demand_restore_rids` 永不填充（死结构零开销）；
  启用 flag 时的 T15 行为仍受 e4 判据约束（park→full-hit >90% 等，3090 实测项）
- 预存在失败：test_unified_radix_cache_unittest 的 import-path quirk 与 GPU/MagicMock
  错误（e8/e9 已记录，排期待 tester/orchestrator）
