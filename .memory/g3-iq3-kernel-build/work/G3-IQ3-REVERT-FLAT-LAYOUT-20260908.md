# G3-IQ3-REVERT-FLAT-LAYOUT-20260908

## Invocation

- Task ID: `G3-IQ3-REVERT-FLAT-LAYOUT-20260908`
- Role: executor
- Status: `done`
- Scope: remove only the flat-storage patch from `gguf.py` and its newly added test.

## Actions

Restored `python/sglang/srt/layers/quantization/gguf.py` to its pre-flat-storage
working-tree content using `apply_patch`. This removed `_pack_gguf_shards`,
`_gguf_shard_view`, packed 1-D `qweight` construction, storage-map metadata,
and the packed-view call site, restoring the original padded 2-D parameter and
`.contiguous()` call.

Deleted only:

`test/registered/expert_pack/test_gguf_shard_layout.py`

No remote host, kernel, benchmark, report, review-gate, or unrelated modified
file was changed.

## Evidence

Commands run from the repository root:

```text
git diff --check
git status --short
git diff -- python/sglang/srt/layers/quantization/gguf.py
test ! -e test/registered/expert_pack/test_gguf_shard_layout.py
```

Observed:

```text
DIFF_CHECK_RC=0
TEST_REMOVED
```

`git status --short` retained the unrelated pre-existing changes:

```text
 M python/sglang/benchmark/serving.py
 M python/sglang/srt/entrypoints/openai/protocol.py
 M python/sglang/srt/entrypoints/openai/serving_chat.py
 M python/sglang/srt/entrypoints/openai/serving_completions.py
 M python/sglang/srt/sampling/custom_logit_processor.py
 M test/registered/unit/sampling/test_custom_logit_processor.py
?? .memory/
?? AGENTS.md
?? CODEX_DPRIME_STATIC_REVIEW.md
?? CODEX_HANDOFF.md
?? HANDOFF-G3-2026-09-07.md
?? review/
```

The target `gguf.py` no longer appears in status output, and the deleted test
does not exist.

## Open issues

None within this invocation. IQ3_S MMQ work requires a separate Task ID.
