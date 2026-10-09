# G1 corpus recon — storage pattern/test corpus (read-only scout, 2026-09-12)

Source task: `G1-CORPUS-RECON-20260912` (scout). Corpus root
`/home/dev-codex/workspaces/nerun-dev/storage` @ HEAD
`1953397436683219e543e19dff89560d07fa3c6f` (E436); `pattern/`+`testing/` clean at HEAD.
Boundary: FoundationDB / RocksDB / TiKV(fail-rs, raft-engine); CockroachDB deferred.
Corpus is guidance, not authority (`pattern/README.md:3`);
`.memory/storage-pattern-corpus/PATTERN-INTAKE-NOVEL-MECHANISM-GATE.md:10-11`.

## A. Manifest/checkpoint/recovery-prefix/restart-replay

| id | anchor | mechanism | G1 bearing | hint |
|---|---|---|---|---|
| FDB-IMP-04 | foundationdb.md:70-87 | start role wrappers, collect recovery futures, signal stateful eligibility only after recovery | "index rebuilt before authoritative service" gate | ADOPT |
| FDB-IMP-05 | foundationdb.md:90-107 | ordered shutdown: cancel recovery -> clear refs -> signal stopping -> await filesClosed | restart handoff ordering | ADOPT |
| FDB-IMP-09 | foundationdb.md:170-187 | recorded log: size/payload/valid flag; recovery scans to end, zero-fills incomplete tail | torn-tail recovers to a prefix | ADOPT |
| FDB-IMP-11 | foundationdb.md:210-227 | write spill+recovery metadata, commit, set durable version, then erase old | manifest publication ordering; GC after durable marker | ADOPT |
| FDB-IMP-15 | foundationdb.md:290-307 | purge old log generations only after all consumer frontiers pass recover point | generation retirement for checkpoints | ADOPT |
| FDB-IMP-19 | foundationdb.md:370-387 | stage writes, mark durable version, await engine commit, publish under lock | two-phase durable publication | ADOPT |
| FDB-IMP-20 | foundationdb.md:390-407 | prefer reboot+reopen+replay over in-place rollback (liveness FIXME) | restart-and-replay strategy | ADAPT |
| RP-RDB-001 | rocksdb.md:10-30 | numbered teardown: gates, cancel/join bg, clear queues/WALs/handles, VersionSet, lock, dirs | manifest/WAL close ordering | ADOPT |
| RP-RDB-002 | rocksdb.md:33-53 | publish shutdown, unschedule, predicate-loop join | quiescent pre-checkpoint state | ADOPT |
| RP-RDB-031 | rocksdb.md:706-726 | lock + re-evaluate all predicates incl. error/cancel escape | rebuild wait must include error escape | ADOPT |
| TKV-CODE-006 | tikv.md:120-139 | system owns worker handles; broadcast shutdown then join | single restart/teardown owner | ADOPT |
| TKV-CODE-015 | tikv.md:318-337 | apply state written in same KV batch as mutations (rejects separate storage) | durable progress marker with data | ADOPT |
| TKV-CODE-016 | tikv.md:340-359 | ingest pending files -> KV batch -> persist apply state -> drain deletions | replay-safe order: sidecar/metadata/callbacks | ADOPT |
| TKV-CODE-024 | tikv.md:516-535 | close old writer, new file, write+sync header, sync directory, then publish | generation discriminator durable before publication | ADOPT |
| TKV-CODE-025 | tikv.md:538-557 | parallel chunk replay with serialized deterministic reducer | parallel index rebuild must merge deterministically | ADAPT |
| TKV-CODE-028 | tikv.md:604-623 | live append vs rewritten vs compacted ranges vs atomic groups distinct | recoverable compaction/rewrite metadata | ADAPT |
| TKV-CODE-029 | tikv.md:626-645 | exclusive directory LOCK for engine lifetime; second instance errors | single-writer fencing before mutate | ADOPT |

## B. WAL durability boundary / durable-ACK / ordering

| id | anchor | mechanism | hint |
|---|---|---|---|
| FDB-IMP-10 | foundationdb.md:190-207 | persist logical pop watermark before physical reclaim | ADOPT |
| FDB-IMP-12 | foundationdb.md:230-247 | append queue, advance in-memory version, wait queueCommittedVersion, then reply durable | ADOPT |
| FDB-IMP-13 | foundationdb.md:250-267 | quorum-minus-anti-quorum committed version | NOT_ADOPTED (single-process) |
| RP-RDB-007 | rocksdb.md:148-168 | narrow WAL serialization separate from DB state; documented lock subsets | ADAPT |
| RP-RDB-010 | rocksdb.md:219-239 | leader/follower group commit; one shared durable append | ADOPT |
| RP-RDB-011 | rocksdb.md:242-262 | compatibility predicate before group formation | ADOPT |
| RP-RDB-012 | rocksdb.md:265-285 | preprocess -> reserve seq -> WAL write/sync -> memtable -> publish last seq on success | ADOPT |
| RP-RDB-014 | rocksdb.md:311-331 | global max group bytes; bounded small-leader growth | ADAPT |
| RP-RDB-015 | rocksdb.md:334-354 | capture pre-write WAL size; scoped truncation on apply failure | ADOPT |
| RP-RDB-032 | rocksdb.md:729-749 | non-batch barriers join same writer order | ADOPT |
| TKV-CODE-014 | tikv.md:296-315 | callbacks matched by exact (term,index); stale retired; impossible order panics | ADOPT |
| TKV-CODE-020 | tikv.md:428-447 | intrusive writer list, one leader per group does physical append+sync | ADOPT |
| TKV-CODE-021 | tikv.md:450-469 | empty batch still syncs when sync=true (issue #395) | ADOPT |
| TKV-CODE-022 | tikv.md:472-491 | no-space: truncate partial append, rotate, TryAgain, bounded retry | ADOPT |

## C. Torn-write / truncation / corruption / generation / fencing / fail-closed

| id | anchor | mechanism | hint |
|---|---|---|---|
| FDB-IMP-18 | foundationdb.md:350-367 | version-ordered bounded apply; checksum/protocol error fails validation | ADAPT |
| RP-RDB-017 | rocksdb.md:380-400 | physical sync vs in-memory mark-synced vs manifest edit are distinct | ADOPT |
| RP-RDB-034 | rocksdb.md:780-800 | inject write failure/checksum mismatch/unsynced buffering/read corruption | ADOPT |
| RP-RDB-035 | rocksdb.md:803-823 | read merges target+unsynced tail; double-check if sync advanced | ADAPT |
| TKV-CODE-023 | tikv.md:494-513 | stale-index fallback: refresh logical index, retry, else original error | ADOPT |
| TKV-CODE-026 | tikv.md:560-579 | reader tracks verified valid_offset; broken entry = error or truncate to verified | ADOPT |
| TKV-CODE-027 | tikv.md:582-601 | consistency checker detects logical holes; reports, does not repair | ADOPT |

## D. GC / invalidation / tombstone / compaction recoverability

| id | anchor | mechanism | hint |
|---|---|---|---|
| FDB-IMP-14 | foundationdb.md:270-287 | physical safe pop = min across logical views | ADAPT |
| RP-RDB-022 | rocksdb.md:497-517 | ref-before-enqueue; drop check on dequeue; clear drains refs | ADAPT |
| RP-RDB-023 | rocksdb.md:520-540 | drop/destroy handle at async flush boundary; assert non-OK not hang | ADOPT |
| RP-RDB-027 | rocksdb.md:612-632 | reject compaction inputs overlapping in-progress ranges | ADAPT |
| RP-RDB-029 | rocksdb.md:658-678 | obsolete-file GC governed by reachability+protection, not age | ADOPT |
| TKV-CODE-004 | tikv.md:76-95 | registry replacement immediately closes displaced actor | ADAPT |

## E. Atomic groups / all-or-nothing / sidecar groups / ack boundaries

`FACT`: the term **"sidecar" does not appear anywhere in `pattern/*.md`**.

| id | anchor | mechanism | hint |
|---|---|---|---|
| FDB-IMP-02 | foundationdb.md:30-47 | re-entrant cleanup as explicit draining/terminal state machine | ADOPT |
| FDB-IMP-07 | foundationdb.md:130-147 | worker produces value; callback delivered on authoritative thread | ADAPT |
| FDB-IMP-17 | foundationdb.md:330-347 | normalize/copy mutations before mutating shared state | ADAPT |
| RP-RDB-004 | rocksdb.md:79-99 | handle holds owner ref; dropped CFs persist until refs release | ADAPT |
| RP-RDB-009 | rocksdb.md:196-216 | encode ordered mutations into one owned rep; apply at one boundary | ADOPT |
| RP-RDB-019 | rocksdb.md:426-446 | shared atomic-flush; collect all; install as one logical op or roll back | ADOPT |
| RP-RDB-020 | rocksdb.md:449-469 | retryable error rolls back ALL affected pending flushes | ADOPT |
| RP-RDB-021 | rocksdb.md:472-492 | every wait predicate includes background-error escape | ADOPT |
| TKV-CODE-005 | tikv.md:98-117 | transactional registration of mailbox+bootstrap; rollback on partial failure | ADAPT |
| TKV-CODE-012 | tikv.md:252-271 | coalesce only adjacent payloads; flush before control boundary | ADOPT |
| TKV-CODE-013 | tikv.md:274-293 | yield on count/bytes/time; YieldState retains continuation | ADAPT |
| TKV-CODE-017 | tikv.md:362-381 | on destroy drain receiver, answer callbacks with explicit errors | ADOPT |
| TKV-CODE-018 | tikv.md:384-403 | async results route back to lifecycle owner | ADOPT |

## F. Anti-patterns + bug-derived hazards (prohibited)

| id | anchor | prohibited shape | boundary |
|---|---|---|---|
| RP-RDB-003 | rocksdb.md:56-76 | silently close with unreleased snapshots/borrowed views | borrowed sidecar view outlives owner |
| RP-RDB-008 | rocksdb.md:171-191 | blocking I/O (fsync/close/unbounded wait) holding global logical-state lock | deadlock/latency amplification |
| RP-RDB-016 | rocksdb.md:357-377 | accept `sync && disableWAL` (promise durability with no path) | durability contract violation |
| RP-RDB-045 | rocksdb.md:1038-1058 | treat throughput/latency as correctness oracle | benchmark-only restart claims |
| TKV-ANTI-034 | tikv.md:736-755 | shutdown by magic-number sentinel instead of explicit close | missed wakeup/hang |
| TKV-ANTI-035 | tikv.md:758-777 | effectively unbounded apply inbox under bounded polling | bounded turn != bounded memory |
| TKV-ANTI-036 | tikv.md:780-799 | silent terminal success after shutdown discards work | accepted-vs-discarded violation |
| FAIL-ANTI-037 | tikv.md:802-821 | busy-wait spin while updating failpoint list | must not enter write path |
| RP-RDB-013 | rocksdb.md:288-308 | wake a writer before removing its node (wake-before-unlink) | list cycle / reuse |
| RP-RDB-018 | rocksdb.md:403-423 | false "fully synced" when writes/rollover inside sync window | reopen treats dropped bytes durable |

## G. Harness/test patterns (methodology)

| id | anchor | purpose | hint |
|---|---|---|---|
| FDB-TST-01..09 | foundationdb.md:532-709 | buggify determinism, perturbation vs bug provenance, deterministic RNG/event loop, kill/fault/disk/reboot modelled separately, explicit registration, serial shuffle, lifecycle matrix | ADOPT/ADAPT |
| RP-RDB-033 | rocksdb.md:757-777 | fault env drops bytes after last modeled sync; exposes exact durable prefix | ADOPT |
| RP-RDB-034 | rocksdb.md:780-800 | inject I/O error + checksum corruption at FS boundary | ADOPT |
| RP-RDB-036 | rocksdb.md:826-846 | sync points as dependency DAG | ADOPT |
| RP-RDB-039 | rocksdb.md:895-915 | persist stress oracle across crash/restart | ADOPT |
| RP-RDB-041 | rocksdb.md:941-961 | separate correctness and performance results | ADOPT |
| FAIL-CODE-030..033 | tikv.md:648-733 | scenario mutex+RAII guard; counted actions; pause/unpause sync; faults at semantic boundaries | ADOPT/ADAPT |
| TKV-HARNESS-044 | tikv.md:958-977 | write-barrier grouping with held leader | ADOPT |
| TKV-HARNESS-045 | tikv.md:980-999 | fault matrix with restart + post-recovery index assertions | ADOPT |
| TKV-HARNESS-048 | tikv.md:1046-1065 | asserted input-immutability after failed batch op | ADOPT |

Testing corpus (canonical reports under `.memory/storage-test-corpus/`,
`testing/mining/`): relevant restart/reopen/corruption rows include
FDB-C08/C09/C10/C11/C12/C13/C20/C22, RDB-C01/C03/C11/C13/C14/C15/C34/**C39
(MANIFEST rotation/verify/reuse; kill during open/close; CRC/decode corruption
rejected)**, TIKV-004/C11/C12/C13/C16/C23/C33/C34/C39, RE-046..RE-061
(especially RE-049 consistency/corruption, RE-050 incomplete purge reopen,
RE-051 tail/header corruption policy, RE-054 rotate header error, RE-056
non-atomic partial write visible-prefix, RE-059 partial rewrite recover,
RE-061 empty sync reaches fsync path), FAIL-041..045.
Correctness vs benchmark separated: BENCH-062/063, `nerun-benchmark-catalog.md:6-19`.

## H. Deferred / missing (consequences for a restart-safety claim)

| ids/range | reason | consequence |
|---|---|---|
| FDB-C11/C16/C18, FDB-C13/C23/C34 | DISTRIBUTED-LATER / P2C | negative corruption, data-loss semantics, dual-restore deferred |
| FDB-C05,C18-C23; CRDB-1..3 | distributed phase | no cluster-level restart claim |
| RDB-C10 best-efforts salvage | unresolved | fail-closed vs salvage for corrupt manifest undecided locally |
| TIKV-009/017/018/025/026/027/033/040 | timing-dependent; need barriers | not deterministic crash/reopen oracles yet |
| TiKV split-race / snapshot-install restart | upstream TODO | restart during snapshot install is an upstream gap |
| C5 exact corpus coverage | `MISSING exact corpus coverage` (`nerun-test-catalog.md:13`) | no exact closed-prefix reconstruction corpus row |
| all canonical C2/C3/C4/C5 mappings | PARTIAL/MISSING | no local coverage may be inferred |
| `"sidecar"` term | absent from `pattern/*.md` | sidecar atomic-group must be composed -> Novel-mechanism-relevant gap |
| named phased-shutdown API / fail-rs parked-ack | absent (CORPUS-02-FAILPOINT-SHUTDOWN.md:126-135) | crash-only restart assertions lack a first-class primitive |

`FACT`: FDB paired-restart "allowed post-crash prefix" and RDB reopen
"matches an allowed logical prefix" are **open design decisions**, not corpus
answers (`testing/foundationdb/restart-recovery.md:8-9`, `testing/rocksdb/crash-matrix.md:5-6`).
