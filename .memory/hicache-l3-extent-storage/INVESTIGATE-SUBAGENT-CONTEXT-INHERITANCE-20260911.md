# OpenCode child-session context investigation

status: done

## artifacts

- This report only: `.memory/phase2-hicache-design/work/INVESTIGATE-SUBAGENT-CONTEXT-INHERITANCE-20260911.md`.
- Database inspected read-only through Python `sqlite3` URI `mode=ro`; no database or project files were modified by the inspection.

## evidence

### Schema and parent/child graph

Verified in `/home/dev-codex/.local/share/opencode/opencode.db`:

- `session(id, project_id, workspace_id, parent_id, ..., metadata, agent, model, ...)` stores the parent relationship. The target parent is `ses_f73c120d3ffeCzXP7I6yRR9YpQ`.
- `message(id, session_id, ..., data)` and `part(id, message_id, session_id, ..., data)` are per-session transcript rows. `part.message_id` is the direct message relationship; `part.session_id` is also populated with the owning session.
- `session_context_epoch(session_id, baseline, snapshot, baseline_seq)` exists, but there is no row for the parent or any of its 15 direct children.
- `session_message` and `session_input` exist but have zero rows for the parent and every direct child examined.

The target has 15 direct children and no deeper descendants in the recursive graph. Every child has `session.parent_id = ses_f73c120d3ffeCzXP7I6yRR9YpQ`; no child row was found with a copied parent transcript.

Direct child IDs (all `agent` values and titles are stored in `session`):

| child session | agent | message rows | part rows | first user message / part |
|---|---:|---:|---:|---|
| `ses_f73ab362dffeqI04bDs84QKBzy` | scout | 12 | 66 | `msg_08c54c9da001TybGvSHtgAu4i2` / `prt_08c54c9df001btXYrh3LfPsVal` |
| `ses_f73a8b62fffePTp9MOLJ82Bmp3` | test-runner | 18 | 81 | `msg_08c5749d6001SEKEWFb3BRbLN4` / `prt_08c5749dc0011M03EazJvsYLSE` |
| `ses_f73a469e4ffeGPAWiiqDhRZpuq` | doc-writer | 10 | 39 | `msg_08c5b96210010KWfdCpVGm60cm` / `prt_08c5b9626001p4mY5PBz6u8T3a` |
| `ses_f73a2ab75ffeRvDiGqmmEhldDs` | doc-writer | 12 | 47 | `msg_08c5d549000139XRO5EqwXjeHa` / `prt_08c5d5494001qOZ2f7hrfy1aVA` |
| `ses_f73a0115effesxl8geURsFbd33` | test-runner | 13 | 69 | `msg_08c5feea700116678H9JoMECCC` / `prt_08c5feeab001t1wUrLHCwsx6VB` |
| `ses_f739dad57ffePVDe6QyRnBMey3` | scout | 10 | 56 | `msg_08c6252ad001PPR6UGhlhl4e1w` / `prt_08c6252b1001myd8IUNL1CSBez` |
| `ses_f739b7922ffewc8cP9OCdHofP4` | devops-executor | 10 | 44 | `msg_08c6486e2001riUSW7FeJY67X8` / `prt_08c6486e6001zC9ce83r2s1AXn` |
| `ses_f7397a621ffeCTqHFJT6bdzgyL` | test-runner | 10 | 38 | `msg_08c6859e3001A0pjjU4Prx7Nyf` / `prt_08c6859e6001ISrssycfE6kFRl` |
| `ses_f7396179fffecM1JWJygDYANgh` | test-runner | 8 | 29 | `msg_08c69e8690017Cf1lkfDaP6gRe` / `prt_08c69e86f001X0Pnm2zCE4h4vS` |
| `ses_f7394b925ffeOH8ucG4lZwLFkm` | test-runner | 11 | 40 | `msg_08c6b46df001sI9kwsfFu7nh85` / `prt_08c6b46e3001opIIKKpR29nepA` |
| `ses_f73914bfeffeVQBvSXlFnZM0WQ` | debugger-deep | 18 | 90 | `msg_08c6eb4060016YPp4i0XUz7yrw` / `prt_08c6eb40b001g6jwMNlbOKc9PP` |
| `ses_f738e70f0ffeCMTHzBaMRzbPQn` | coder | 26 | 110 | `msg_08c718f150010eeIL7WWuIi9CF` / `prt_08c718f1a00178Hcnpz4ZAwwJN` |
| `ses_f738ba3f6ffeob0xJpImsZ9cvg` | reviewer | 15 | 62 | `msg_08c745c0f001tSGkwKQFbpRm1s` / `prt_08c745c15001Iqroez2qzI2Akv` |
| `ses_f7389fafcffeqMB1aH83Zvz8Wu` | test-runner | 28 | 108 | `msg_08c76050d001g495FWpM3cPs28` / `prt_08c760513001IpZoezGsmo54aa` |
| `ses_f7372b8dfffeDhaZo4jYluEdTs` | scout | 9 | 34 | `msg_08c8d47280015YZvUELkTC8P55` / `prt_08c8d472d0013DdhyXoryMxgeE` |

The parent itself has 91 messages and 323 parts. Its 10 user messages are distinct rows, including the original handoff and later questions. Child rows are not aliases: each child starts with its own `role=user` dispatch message whose JSON has `parentID: null`, followed by an assistant message whose JSON `parentID` points to that child’s own dispatch message. Subsequent assistant messages point to that same child-local user message.

### What is and is not present in child transcripts

Verified by enumerating all `message.data` and `part.data` rows for the parent and children:

1. **No copied parent messages/parts:** no child has a `message.session_id` equal to the parent, and no child part has a `message_id` belonging to a parent message. Child transcript rows are separate and self-contained.
2. **No parent-session reference in ordinary child JSON:** the target parent session ID does not occur in any child `message.data` or `part.data` for 14 of 15 children. The current investigation child (`ses_f7372b8dfffeDhaZo4jYluEdTs`) has 5 occurrences in its own tool/assistant part JSON because the dispatch explicitly names the parent session ID; these are injected task text/inspection output, not database inheritance links.
3. **Child dispatch is injected context:** each first user part is a single text part containing the explicit `ENTRY: ACCEPT`, task ID, role/goal/scope, and project paths/constraints. Examples are the first-user part IDs in the table above. The first assistant message then contains the child’s role/mode/agent/model metadata and `parentID` to the child’s first user message.
4. **Parent metadata is linked only at session level:** child `session.parent_id` is the durable parent relationship. Child `session.metadata` is NULL in the inspected rows; there is no session-context snapshot row carrying parent transcript data.
5. **One incidental exact text duplicate:** child `ses_f73ab362dffeqI04bDs84QKBzy` contains part `prt_08c550fe8001MNOJB1sOTGmnNL` with the same reasoning text `**Locating hidden .memory directory**` as parent part `prt_08c541b9e001jvPC6yJcoSgkEn`. This is identical generated reasoning text, not a shared part/message ID or parent reference. No other exact non-empty parent part-text matches were found in the other child transcripts.

### Quantification

- Parent transcript: 91 messages / 323 parts / 18,466 characters across non-empty text parts.
- Direct children: 15 sessions, 210 messages total, 1,013 parts total. (Message/part counts are sums of the per-child table.)
- Exact copied/shared parent database rows: **0** message rows and **0** part rows. Shared IDs were not observed.
- Exact duplicate parent text parts in children: **1** matching text value, described above; this does not establish context copying.
- Stored session token counters: parent `(input 2,302,040; output 21,957; reasoning 4,982; cache_read 2,232,832; cache_write 0)`. Children summed `(input 3,865,802; output 61,877; reasoning 12,085; cache_read 1,390,080; cache_write 0)`. These counters are usage accounting, not proof of which prompt material was supplied.

## summary

**Verified conclusion:** OpenCode persists the parent-child relationship as `session.parent_id`, but the SQLite evidence shows that child sessions do not inherit/copy the parent’s stored message or part transcript. Each child has its own injected dispatch as its first user message and then its own assistant/tool transcript. The parent’s full transcript is absent from child `message`/`part` rows; there is no `session_context_epoch` snapshot/baseline row for these sessions and no `session_message`/`session_input` evidence either.

The only durable parent-context metadata visible in these tables is the child’s `session.parent_id` plus child-local session fields (`agent`, `model`, title, directory, etc.). Any context supplied to a child at runtime but not persisted in these tables cannot be established from this database alone. The dispatch text itself can include selected parent/project facts and paths; that is explicit injected context, not automatic transcript inheritance.

## followups

- If runtime prompt assembly must be proven beyond persisted SQLite rows, inspect the OpenCode source/runtime request payload or capture an explicitly authorized, non-secret prompt-debug artifact; this report did not do that.

## open_issues

- **NOT_ESTABLISHED:** Whether the OpenCode runtime sends additional ephemeral system/developer text, summarized parent state, or hidden provider-side context that is not persisted in `session`, `message`, `part`, `session_message`, `session_input`, or `session_context_epoch`.
- **NOT_ESTABLISHED:** Whether the single duplicate reasoning sentence arose from model generation coincidence or an internal prompt/context reuse mechanism. Database IDs and ownership prove it is not shared storage.
- Credential/account tables were not queried beyond schema discovery, to avoid exposing secrets.
