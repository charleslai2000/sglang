# phase2-cap-gate3-deploy-devops-e1 — Gate D run 部署前置

- agent: devops-executor
- epoch: e1
- date: 2026-09-07
- task: phase2-cap-gate3-deploy-devops-e1
- note: 报告曾落错项目根（homenet .memory）；本文件为 orchestrator 落盘的 canonical 副本（内容一致），stray 副本保留在 homenet 待清理。

## status: done

## artifacts
- /root/gate3_capacity.py            (24052, 驱动, md5 5ecaef3c0a1849bb41a280edf3518560)
- /root/direct-launch-gate3-capacity.sh  (24052, 启动脚本, md5 f1e4ac6dac11ffbf52c4f6a0cd72126e, bash -n OK)
- /root/gate3-capacity-run.sh            (24052, runner,  md5 d678e35f971e72ce3069480c58a2b310, bash -n OK)

## evidence
- procedure:
  - 同步驱动 本地->24052 /root/gate3_capacity.py, 双端 md5 逐字节一致
  - dry-run 55k 档 / 裸跑 default 验证
  - 复制 direct-launch-cap-ratio.sh / cap-ratio-run.sh 蓝本 -> 按命参数改写两脚本
  - bash -n 两脚本语法校验
  - 只读环境快照 (GPU / /data / namespace)
- commands:
  - scp gate3_capacity.py -> /root/ ; md5sum 本地=远端=5ecaef3c0a1849bb41a280edf3518560
  - python gate3_capacity.py --dry-run --agents 4 --tier 55k   RC=0
  - python gate3_capacity.py --dry-run --agents 4               RC=0
  - bash -n direct-launch-gate3-capacity.sh / gate3-capacity-run.sh  SYNTAX_OK
- material_exit_status:
  - scp/scp+chmod + bash -n: 全部 0
- before_state:
  - GPU: 15MiB (瞬时空窗, ② 两阶段间) -> 后见 23671MiB ② 已占
  - /data: 28G 用 / 160G avail
- after_state:
  - 驱动+两脚本已就位于 24052 /root
  - ② (port 8024, MAMBA_RATIO=0.90, cap_ratio_driver c0) 正常占用 GPU 23671/24576 MiB
- verification:
  - 驱动 md5 双端一致: 5ecaef3c0a1849bb41a280edf3518560
  - dry-run 55k -> tokens=55138 (目标 55000, 差 138, tokenizer 截档, 容许区间内)
  - 裸跑 default=55k -> 不崩 invalid choice, RC=0
  - bash -n 两脚本均通过

## summary
驱动同步完成且逐字节核验一致; dry-run 两验证均 RC=0 (55k 解析 55138, 裸跑 default=55k
不再崩); 两脚本自既有蓝本零发明改写, r* 预填=0.43 单值可调点标注于文件头;
bash -n 通过。未启动引擎/未跑 ③/未建 namespace/未 kill 任何进程。

## followups
- ③ Gate D run: tester 语义校验直接-launch 参数与 runner CLI 后, 按需指定
  --agents N --tier H0 及驱动 COLD/WARM/STAGGER 参数实跑。

## open_issues
- r* (--mamba-full-memory-ratio) 现固定 0.43 (direct-launch-gate3-capacity.sh, --mamba-full-memory-ratio 行,
  以及 gate3-capacity-run.sh 内 MAMBA_RATIO=0.43)。② e7 定稿若异, 改此单值 (两处)。
- 驱动在 24052 的其它依赖: 真卡 (非 dry-run) 需 /root/common.py importable
  (脚本 sys.path 含 /root 与 /root/p2-0, gate3 既有确实依赖), 且从 /root 运行
  (driver 源码注释要求); envo KEY 明确: SGLANG_PORT/SERVED/MODEL_PATH/STORAGE_DIR。
- /data 剩余 160G, extent MAX_SIZE=200G 需注意: 200G extent 上限 > 当前 160G 可用,
  真卡 extent 分配是否 clamp 到 160G 由 tester 观察; 未在本任务内验证/改。
- 环境基线瞬时扰动: 首次采样 GPU 15MiB (② 两阶段间空窗), 后确认 ② 正常占 23671MiB;
  无 cap-gate3 namespace, 两脚本为 /root 下唯一 gate3-capacity 产物。