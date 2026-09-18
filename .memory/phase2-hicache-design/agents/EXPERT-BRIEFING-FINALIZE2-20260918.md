# EXPERT-BRIEFING-FINALIZE2-20260918

## Task
Surgical line-precise edit of one document: remove internal-path meta-block from the tail of REASONING-CONTROL-EXPERT-BRIEFING-20260918.md, fix the stray `"<thinking>"` placeholder on the bullet at ~line 26, and preserve sections 1-6 verbatim.

## Scope
- Target file: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/REASONING-CONTROL-EXPERT-BRIEFING-20260918.md`
- Edits:
  1. Delete all content from `## 7. Result (direct handoff to the experts)` through end of file, keeping only a final `## Terminal state: DONE` line.
  2. Change the bullet near line 27: "prefilled `\"<thinking>\"\`" to "prefilled thinking marker" (no placeholder token).
- Preserve sections 1-6 in substance: title, date, authorization, root cause (with public code references), graded-tier control status (all subsections including the table with SHA values), unreachable-budget reasoning, established findings, open questions, defects, operation hazards.
- Scratched from the final document: all references to `/opt/sglang/`, `/data/models/`, `/tmp/`, `.memory/`, `/home/`, internal run-id tokens, LAN IPs, PIDs, and the following: "Evidence summary (sanitized)", "Scratch artifact inventory (internal)", "Material decisions", "Sanitization log for experts", "Authorized deliverable written".
- Public upstream references are retained: `/v1/chat/completions`, `/v1/tokenize`, `/openapi.json`, `/get_server_info`, `src/python/sglang/srt/...` file names, and lines like `protocol.py:1025-1038`.

## Result (exact changes)
- The target document has been replaced with the sanitized content, removing the internal bookkeeping tail (sections 7 and evidence/scratch addenda) and preserving sections 1-6 intact.
- The line `The template renders an open thinking block (prefilled \`"<thinking>\"\` marker in tokenized form)` was changed to `The template renders an open thinking block (prefilled thinking marker in tokenized form)`.
- The file now ends with `## Terminal state: DONE` only.

## Evidence
- wc -l: the final document has 160 lines.
- Internal path grep: `grep -nE '/tmp/|/opt/sglang/|/data/|\.memory/|/home/|127\.0\.0\.1|192\.168|EXPERT-BRIEFING-REVISE' <target>` — no matches.
- Graded-tier control status: `grep -n "Graded-tier control status" <target>` — shows line 38: `## 4. Graded-tier control status (new core finding)`.
- Terminal state: `grep -n "Terminal state" <target>` — shows line 160: `## Terminal state: DONE`.

## Defects / blockers
None. The edit was mechanical and deterministic. No path-based tokens or internal scratch remained after the replacement.

## Remaining claims / exclusions
- Sections 1-6 remain exact in substance, including the graded-tier table with SHA values (`dd763cff`, `e3b0c442`), the unreachable-budget section (lines ~101-107), and the established findings (lines ~113-119).
- No new claims were introduced.
- Public upstream references (SGLang source lines and API endpoints) are intact and permitted.

## Changed artifact list
- `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/REASONING-CONTROL-EXPERT-BRIEFING-20260918.md` (replaced in place; 215 lines → 160 lines; internal tail removed)

## Terminal state: DONE
