# Control run-artifact archive

Generated run outputs are removed from this checkout. Textual Goal/Plan/Task records and concise human-authored run conclusions remain under `control/`; raw generated run files are retained outside the repository at:

- `/data/sglang-hicache/control-archive/`

The archive mirrors paths relative to `control/`. It contains 7,742 files copied from `control/**/runs/` and SHA-256 verified before the workspace copies were removed. The generated HiCache extent data files (`hicache.data_*`) are reproducible cache contents and were deleted rather than archived. Their manifests, summaries, and WAL data are archived where present.

The archive is on the same `/dev/sda1` filesystem as the checkout; it is a repository boundary, not a separate backup or independent failure domain. Do not treat it as a second backup. Any future run output must be directed outside the checkout (prefer `/data/sglang-hicache/<goal>/<run-id>/`) and summarized in the owning task/plan. Do not restore bulk run products under `control/`.
