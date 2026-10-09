# OPS-20260908-3060-STORAGE-MICROCHECK

- Task ID: D3060-STORAGE-MICROCHECK-027
- Orchestration epoch: 20260908-3060
- Role: devops-executor
- Status: done

## Scope

Executed only the authorized fast check against `root@i-1.gpushare.com:27460`:

1. Wrote a harmless marker to `/hy-tmp` and verified it was non-empty.
2. Queried the Hugging Face API for `LostGentoo/Qwen3.5-4B-AWQ`, revision `main`, with `curl --max-time 30`.
3. Removed only the created marker and verified it was absent.

## Commands and evidence

Remote command used (credentials omitted):

```sh
printf '%s' 'codex-storage-microcheck' > /hy-tmp/.codex-storage-microcheck-20260908-3060
test -s /hy-tmp/.codex-storage-microcheck-20260908-3060
curl -sS -L --max-time 30 -o /dev/null -w 'HF_STATUS=%{http_code}\nHF_CONTENT_LENGTH=%{size_download}\n' \
  'https://huggingface.co/api/models/LostGentoo/Qwen3.5-4B-AWQ/revision/main'
rm -f /hy-tmp/.codex-storage-microcheck-20260908-3060
```

Observed output:

```text
STORAGE_MARKER_WRITE=PASS
HF_STATUS=200
HF_CONTENT_LENGTH=10396
CURL_EXIT=0
STORAGE_MARKER_REMOVED=PASS
```

## Changed resources

- Created and removed only `/hy-tmp/.codex-storage-microcheck-20260908-3060`.
- No other resources were changed.

## Verification

- `/hy-tmp` writable: confirmed.
- Marker removed: confirmed by a subsequent remote `test ! -e` check.
- Exact HF API revision `main`: HTTP 200; response content length 10,396 bytes.
- No weights downloaded; `/hy-model` not touched; no server, benchmark, or source/3090 operation performed.

## Followups

- None.

## Open issues

- None.
