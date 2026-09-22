# O001 — C6.4R storage-capacity preflight blocker

At C6.4R preflight, `/data/l3` resides on `/dev/sda1` with only 32 GiB available. The frozen Qwen HiCache contract uses `SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE=50GiB` and `MAX_SIZE=100GiB`. Canonical ExtentFileBackend does not reject startup when free space is below the watermark; instead every write considers this a pressure condition and synchronously evicts LRU entries until the watermark is met or the live index is exhausted. This makes a live-entry fixture unsafe/unreliable under current capacity.

No server was launched, no new root created, and no data was deleted or modified. The C6.1 root remains preserved. Resolution requires authorized capacity recovery or a production-approved storage mount with the same cache contract. Do not lower the min-free value or remove unrelated files as an experiment workaround.
