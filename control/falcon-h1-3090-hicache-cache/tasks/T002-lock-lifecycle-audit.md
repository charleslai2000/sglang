Status: DEFERRED
Work area: experiments
Objective: Independently diagnose and qualify StreamingSession request/session_params IPC routing and Req→SessionSlot lock Receipt lifecycle.
Inputs: `../goal.md`, `../plan.md`; `membership-fix-probe.jsonl`, server logs; tokenizer, IPC, Scheduler, StreamingSession code and focused tests.
Completion: Exact tokenizer→IPC→scheduler field routing is evidenced; one actual StreamingSession admission transfers one Receipt to SessionSlot, later turn does not acquire a second lock, active slot remains protected, close releases the exact saved FULL/MAMBA receipt, and regression tests pass. No false correctness claim.
Result: Ordinary Request lock lifecycle is separately proven: node26 FULL path and MAMBA ref each 1 before Finished and 0 after. StreamingSession runs instead recorded scheduler `session_id=None`, ordinary acquisition/release each turn, turn2 cached 0, and no slot-transfer event. A speculative tokenizer fallback did not resolve runtime observation and must remain unqualified; no fix accepted. User explicitly removed this issue as an L2/L3 prerequisite.
Remaining: Resume only as independent investigation. Trace serialized tokenized object through `_send_one_request`/IPC/scheduler receive, determine exact field loss, then test runtime slot transfer/close. Do not block ordinary Request L2/L3 on this task.
