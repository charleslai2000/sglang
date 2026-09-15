# P1 SPEC_BUDGET chain -- R118 evidence report

Task: `P1-SPEC-BUDGET-CHAIN-20260911-R118`  (tester / independent verification)
Run id: `run-48806-4187756182262`  Profile: `profile-97ee3d5d3bfdca6237dc746e`
Server: `http://127.0.0.1:30000` (PID 48746, scheduler 48806), read-only.
Source HEAD: `4f41f5bab562b99562f30c67540eb05344d13637` (worktree dirty; hashes in bundle).

Method: public HTTP only (`GET /health`, `POST /v1/tokenize`, `POST /v1/completions`),
temperature 0, top-level `session_id`, `prompt` as `input_ids` (batch path; the
tokenizer is not batch-encode enabled). No product edits, no instrumentation, no
server control. 6 build requests + 1 input_ids batch replay + 1 trigger request per
run. Driver: `/tmp/r118/driver118.py` (copied into the bundle as `driver.out` transcript).

## Result

The SPEC_BUDGET park and the budget-release epoch are **reproducibly captured** for the
same rid. The downstream legs (RH wake / L3->L2 stage / host-ready / admission /
L2->L1 restore+generation) are **not reached** for the parked rid: it is never
re-evaluated by the ready horizon after the park, and host headroom is structurally
insufficient to stage it. Verdict: full chain **not produced**; park + release-epoch
legs verified, downstream legs missing.

### Run R118-n3 (target `r118-n3-R-T`, gen 24, prompt 27461 tokens)

1. Park (verified) -- issuer `r118-n3-R-F2` issues a 43027-token prefetch and exhausts
   the speculative budget; the deferred tail target is parked.
   - issuer `prefetch_issued`: server log line 1576552 (`raw.log` 519950).
   - target park: server log line 1576565 (`raw.log` 519963), `rh_pass_seq=12733744`,
     `fingerprint=(2, 2, 'NONE', None, True, 'SPEC_BUDGET', 43027, (336, 500, 24, 43027,
     ('r118-n3-R-F2', 'r118-n3-R-T')), 500, 0, 65536, 43027, 39321, 43027,
     'exclude', 'negative_cache')`,
     `negative_cache_blocked=True negative_cursor=43027`,
     `decision=exclude reason=negative_cache`,
     `staging_eligible=True restore_potential=True`,
     `speculative_budget_used_tokens=43027 > 39321`,
     `spec_budget_release_epoch=51`, `host_headroom_tokens=500`.
2. Budget-release epoch (verified) -- `prefetch_revoke rid=r118-n3-R-F2 ... miss`
   (server log line 1576609) drops `spec_budget_release_epoch` 51 -> 52 and
   `speculative_budget_used_tokens` -> 0 (first advanced decision at server log line
   1576615, `raw.log` 520013). The target's negative-cache cursor (51) is now stale, so
   the park is causally clearable.
3. Downstream (NOT reached) -- target `r118-n3-R-T` has **0** `rh_preadmission_decision`
   events after the park. A trigger request in the same session
   (`r118-n3-trig-1`, 7 tokens) forced a fresh refill pass (`rh_pass_seq=12808936`) but
   the target was not in the frontier. At that pass `host_headroom_tokens=1652` vs the
   27461 tokens the target must stage.

### Run R118-run1 (target `r118-R-T`, gen 16)

Same shape, independently reproduced.
- Park: server log line 1094814 (`raw.log` 38212), `rh_pass_seq=11227643`,
  `fingerprint=(2, 2, 'NONE', None, True, 'SPEC_BUDGET', 42755, (89, 575, 14, 42755,
  ('r118-R-F1', 'r118-R-T')), 575, 0, 65536, 42755, 39321, 42755,
  'exclude', 'negative_cache')`, `host_headroom_tokens=575`,
  `spec_budget_release_epoch=35`; issuer `r118-R-F1` `prefetch_issued` 42755 at line 1094800.
- Release epoch: 35 -> 36 at server log line 1094873 (`raw.log` 38271).
- Downstream: 0 target `rh_preadmission_decision` events after the park.

## Reachability analysis (evidence, not diagnosis)

- Reproduced invariant across both runs: after a SPEC_BUDGET negative-cache park of a
  deferred batch tail, the parked rid is never re-evaluated by the ready horizon
  (`policy.frontier(self.waiting_queue)`), even though the subscribed
  `spec_budget_release_epoch` advances and other requests continue to produce passes.
- The host headroom needed to stage the parked target is never available: park-time
  `host_headroom_tokens` was 500 (n3) / 575 (run1); the next refill pass showed 1652.
  `_ready_host_headroom` = host pool `available_size()` (+ ready resident); the host
  pool is saturated by the writeback working set created by the eviction fill that the
  park precondition itself requires (issuer must be host-absent to prefetch full length).
  With `--max-running-requests 1` and the batch sub-requests parked, the working set
  does not drain.
- Therefore the observed ordering is: park -> release-epoch advance -> no wake (frontier
  no longer re-probes the parked tail; headroom gate could not pass anyway).

Classification: park leg and release-epoch leg = verified product behavior. Downstream
legs = missing evidence; observed blocking condition reported. Root-cause ownership
(whether the parked tail should have been re-queued, or whether the profile/workload is
the limiting factor) is left to the diagnosis owner; no product defect is asserted here.

## Artifacts (bundle `work/R118-bundle/`)

- `raw.log` sha256 `420ea7f7d2d10c64aae435989ce765525b48172589420edd7a9e5b0b3bda226f`
  (server log lines 1056603.., includes run1 + n2 + n3 windows).
- `probe.log` sha256 `8e91defa6a2c36263a42844c3a586d467ae21ce4df5c88174aa6c4bab563e306`.
- `requests.jsonl` sha256 `2e6721d7e800d017957e29543dfc9c17e532a328b62eea40a69f616500f408a1`
  (build/replay/trigger request records for R118-n3).
- `state.jsonl` sha256 `8f4291d1fb92e61b4f2ad8e528102981fddf673e012e10aa898e7a40ded4a9af`.
- `chain.json` (structured chain + line refs), `manifest.json` (`p0b.raw-bundle.v3`),
  `baseline-offsets.txt`, `source-hashes.txt`, `driver.out`, `watch.log`.

## Open issues / followups

1. Downstream legs for the parked rid remain uncaptured; a scenario that (a) parks the
   tail and (b) leaves >= target tokens of host headroom was not found under the frozen
   R117 profile. A different profile (e.g. larger host pool or a drainable workload)
   would be needed to test the wake path; that is outside this invocation's scope.
2. Whether a parked batch sub-request is intentionally dropped from `waiting_queue`
   should be adjudicated by the mechanism owner (scheduler/ready-horizon).
