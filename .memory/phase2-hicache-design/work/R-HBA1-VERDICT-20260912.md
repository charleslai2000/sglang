# R-HBA1 — Ready Horizon Behavioral Acceptance verdict

Date: 2026-09-12. Grading per contract
`work/R-HBA1-ACCEPTANCE-CONTRACT-20260912.md`
sha256 `a3232e02e437e28496bd3a589ec77e0892bdf1448c52569240b199171f509262`
(frozen). Every claim labelled `FACT` / `INFERENCE` / `OPEN` / `DECISION`.
Launcher `launch-rhba1.sh` sha256
`d6d037fa26ee5b8cd420961c68a133c2c7761b18c4f28104fd7594cfd62cd351`.

## Result in one line

`FACT`: the four-part frozen question (§1 a-d) is answered **YES 20/20** for
sufficient-lead RH ON. The overall contract verdict is **NOT_VERIFIED** only
because §10's supplementary "materially better than the L3-only RH-OFF
control" clause is not met — and it is not met because the RH-OFF control is
**degenerate at C1** (it does pre-stage; see below), not because RH failed.

## Data (n = 20 per condition, fresh server + fresh extent dir each)

Raw: `/mnt/data/nerun-dev/rhba1/result-<cond>.json`,
`rhba1-report.json`. TFTT = `B_first_token - A_last_token` (ms).

| condition | TFTT p50 | TFTT p95 | TFTT max | hidden | restored==D_req | avoidable_recompute | mamba | discard |
|---|---|---|---|---|---|---|---|---|
| `l3_hot` (L2-hot control) | 97.127 | 111.803 | 131.257 | n/a | `FACT` device 24576 / host 3072-3200 | 0 | n/a | n/a |
| `l3_off` (RH OFF) | 92.778 | 103.448 | 119.264 | 20/20 | 20/20 | 0 | 20/20 | 20/20 |
| `l3_on_short` (RH ON, insuff.) | 506.333 | 571.417 | 627.218 | 0/20 | 20/20 | 0 | 20/20 | 20/20 |
| `l3_on_long` (RH ON, suff.) | 93.877 | 108.758 | 122.175 | 20/20 | 20/20 | 0 | 20/20 | 20/20 |

RH ON sufficient-lead derived `FACT`: `ordered_rh` 20/20
(`B_enqueue < prefetch_issue < ready_host <= A_last_token`),
`prefetch_slack` p50 = +8.03 s, `stage` p50 = 490 ms. Insufficient-lead
`prefetch_slack` p50 = -400 ms (correctly classified insufficient; TFTT 5.4x
hot — RH does NOT fake readiness). Config `FACT`: the `l3_off` server ran with
`enable_ready_horizon=False` and emitted **0** `rh_preadmission_decision`
marks, yet still staged+restored D 20/20 via the eager path.

## §9 Hard gates — sufficient-lead RH ON

`FACT` **PASS 20/20**:

* `B_enqueue < prefetch_issue < ready_host <= A_last_token` — 20/20
* `ready_host <= B_admission` — 20/20 (`hidden` 20/20)
* `restored_durable == D_req` — 20/20 (`completed_kv_tokens` == measured storage hit)
* KV + Mamba restore complete — 20/20 (`required_aux_pools=['mamba']`,
  `completed_aux_units={'mamba': 1}`, `finalize_result=accepted`)
* `avoidable_recompute_tokens == 0` — 20/20
* no durable-prefix PARTIAL / shortfall, no hybrid discard, HTTP complete — 20/20

## §10 Effectiveness gate

* `FACT`: RH ON sufficient p95 (108.758 ms) is within `max(100 ms, 25%)` of the
  L2-hot control p95 (111.803 ms) → `within_hot_band = true`.
* `FACT`: RH OFF p95 (103.448 ms) is **not** materially worse than RH ON
  sufficient p95 (108.758 ms) → `better_than_off = false`.
* `FACT` (root cause): contract §6 condition 2 assumes "L3-only, RH OFF — **no
  pre-staging**". That premise is false in the frozen profile:
  `scheduler.py:6068-6072`, `_add_request_to_queue` calls
  `self._prefetch_kvcache(req, origin=HiCachePrefetchOrigin.EAGER_RH_OFF)`
  whenever `not self.enable_ready_horizon`. The eager prefetch is issued at
  enqueue (earlier than the RH pass) and stages D L3->L2 with no RH
  involvement. This path is pre-existing upstream (not introduced for R-HBA1).
* `INFERENCE`: with a sufficient lead (long A, ~8 s hidden) and an uncontended
  host, *any* prefetch issued before A's last token hides the ~0.49 s stage.
  Therefore §10's "materially better than RH-OFF" clause is **not evaluable at
  C1** — its discrimination requires a short lead or resource pressure, which
  is the separate RH Pressure Acceptance line (C4/C8), explicitly deferred.

## Verdict

`DECISION` per frozen contract §11 (PASS requires §9 **and** §10):

* **§9 / single question (§1 a-d): PASS** — RH stages D before admission,
  restores D, skips recompute of D, and brings the A->B gap to the L2-hot
  band, 20/20.
* **§10: NOT SATISFIED at C1** — RH-OFF control is non-discriminating; the
  exact missing transition is a *non-prestaging baseline*, which the frozen
  profile cannot produce.
* **Strict overall verdict: NOT_VERIFIED** (a §10 discriminator is absent),
  **not FAIL** (§9 gates are clean) and **not a fabricated PASS**.

`原结论` (contract §6 cond.2 / §10): "RH OFF = no pre-staging; RH ON must be
materially faster." `新证据` (n=20 live + `scheduler.py:6068-6072`): RH OFF
eager-prefetches at enqueue and reaches the same hidden/restored/no-recompute
state with p95 103.4 ms vs RH ON 108.8 ms. `因此修正为`: at C1 the RH-OFF
control validates the *restore path*, not the *predictive staging* value; the
RH-vs-non-RH separation must be judged under pressure, not at C1.

## USER RULING (2026-09-12) — Option A, frozen

`DECISION` (user authority): **R-HBA1 Behavioral Correctness = PASS / CLOSED**.
`§10` RH-vs-OFF discrimination = **NOT EVALUABLE at C1** because the RH-OFF
control carries the upstream `EAGER_RH_OFF` prefetch (a wrong control
definition, not a lowered bar). **RH Incremental Effectiveness = OPEN**, moved
to the independent **RH Pressure Acceptance** line (C4/C5/C6/C8). Option B
(product-code change to manufacture a true no-prefetch control) is explicitly
**rejected**: it would modify product code only to satisfy a control already
proven mis-specified. No re-run of C1.

Ledger status wording (user-specified, binding):

> `R-HBA1: PASS — behavioral correctness proven 20/20.`
> `§10 RH-vs-OFF discrimination: NOT EVALUABLE because RH-OFF contains upstream eager prefetch.`
> `Incremental RH effectiveness moved to RH Pressure Acceptance.`
