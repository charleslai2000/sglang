status: done

artifacts:
- Report: `.memory/phase2-hicache-design/work/P0-C-RECONCILE-RESTART-20260911-R72.md`
- Evidence bundle: `.memory/phase2-hicache-design/work/P0-C-RECONCILE-RESTART-20260911-R72.artifacts/`
- Product manifest: `10_local_python_sglang.sha256`; remote before/after manifests
  and verification files in the bundle.
- Remote rollback backup: `/root/sglang-3060-12g-hicache-backups/R72-20260911T055428Z/`

evidence:
- Authorized host: `I2aff9805ac001019d1`; RTX 3060 12 GiB/SM86, driver
  550.144.03; dependencies verified.
- Authoritative source: local `sglang-3090-24g-opt`, branch
  `3060-12g-qwen35-4b`, HEAD `4f41f5bab562b99562f30c67540eb05344d13637`.
- Full product manifest: 4568 files, digest
  `262a9362e345df15d93049301d2b0e60990ba65d80c3bbc5209fb4cdab140e2d`;
  remote verification 4568 OK/0 failed.
- Old server PID 218072 stopped cleanly; port freed; no checkout-cwd orphans;
  GPU usage dropped 8897 MiB -> 2 MiB.
- New server PID 251004 started `2026-09-11T05:52:33Z`, health HTTP 200 after
  bounded 52-second wait; final port has only PID 251004, children 251162/251163.
- R60 profile values match: device KV 65536, Mamba 53, host KV 131073/2.15 GB,
  host Mamba 5.51 GB, page size 1, RH watermarks 55000/110000, budgets
  65536/39321, mem_fraction_static 0.82.
- Marker updated with manifest digest; nine legacy backup files retained but
  excluded from authoritative manifest.

summary:
- Source-mixture/process-provenance ambiguity eliminated; the 3060 now runs a
  freshly started hash-pinned profile against authoritative source.
- This is P0-C provenance/profile evidence only and does not close P0-B.

followups:
- Run P0-B live-chain procedure against PID 251004.
- Preserve R72 bundle and rollback backup.

open_issues:
- No remote Git metadata; provenance is manifest-pinned.
- Initial backup `sha256sum -c` path invocation failed, but direct hash comparison
  succeeded and is documented.
- P0-B remains NOT_VERIFIED.
