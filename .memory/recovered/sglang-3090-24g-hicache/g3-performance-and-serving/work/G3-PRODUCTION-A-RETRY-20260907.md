ENTRY: ACCEPT

status: pending

run_id: prod-a-20260907-121530
remote_root: /data/qwen3-g3-baseline/prod-a/prod-a-20260907-121530/

The fresh detached Production Profile A wrapper is running the authorized C1/C4/C5 matrix. At last observation C1/repeat-1 was active after initial warmup, 8/20 requests complete, runner RSS 1,608,960 KiB, with service PID 298123 healthy and unchanged. No abort condition, OOM/rc137, or invariant failure observed. Completed repeats: 0/9.

The exact command is preserved at each repeat's command.txt and uses the required runner, source root, model, random-ids, --tokenize-prompt, C1/C4/C5 bindings, --flush-cache, and no --tokenizer. The wrapper was copied from the settled runbook wrapper into the fresh run and adjusted only for the fresh run ID and warmup sequencing (warmup_requests=3 on repeat 1, 0 thereafter).

Final medians, hashes, artifact paths, service postflight, and done/blocked status require the detached matrix to finish. No further local files are authorized.
