# SMOKE-DEVOPS-20260917-01 — Release Procedure Design (Design-Only)

Status: DONE

## Task

- task_id: SMOKE-DEVOPS-20260917-01
- role: devops (design-only)
- goal: DESIGN (not execute) a safe, reversible release procedure for a hypothetical simple service, and analyze its failure modes. No infrastructure, service, container, or environment action of any kind.
- inputs: none required, none used.
- dependencies: none.
- Dispatch validation: VALID. The request is a design/analysis deliverable, which is inside the devops role's authority; it explicitly forbids execution and limits the working surface to one `.memory` subtree. The scope restriction and the prohibitions (no execution, no git, no GPU, no services, no network, no package installs, no orchestrator ledger or other-agent artifact writes) are consistent with the global operating rules. No authorization boundary was crossed, and no work outside this invocation was accepted.

## Scope

- Confined entirely to `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/protocol-subagent-smoke-20260917/`.
- Single permitted write: this result artifact at `agents/SMOKE-DEVOPS-20260917-01.md`. No other file was created or modified.
- No reads outside the scope directory; the orchestrator ledger and other agents' artifacts were not read or touched.
- No git, GPU, service, container, network, or package-manager operation was performed. The procedure below was NOT executed.
- The design is ABSTRACT: it uses placeholders only and references no real host, hostname, credential, service endpoint, or infrastructure of this machine. The only real environment detail in this file is the required artifact path in this section, mandated by the dispatch.

## Result

### Side effects

ZERO side effects. Nothing was executed, started, stopped, deployed, or changed. The only write performed in this task is this artifact file; all other operations were read-only existence/list checks inside the scope directory (see Evidence).

### Dispatch validation

See Task section: dispatch is VALID; no reroute, escalation, or extra authority is needed for this design-only deliverable.

### Hypothetical subject (placeholders only)

Service **S**: a simple stateless request-serving service, deployed as a set of identical instances behind a load balancer, running immutable versioned artifacts. Release moves the environment from version **V** (digest **D**) to version **V+1** (digest **D+1**) with configuration revision **C+1**. Environments, stores, tooling, and roles are referred to generically (e.g., "the artifact store", "the deploy tooling", "the operator").

### 1. Preconditions that must hold before the release starts

- **P1 — Authorization:** an approved change record exists for V+1; the release window is open; a named operator and a named rollback decider are on duty.
- **P2 — Artifact readiness:** the V+1 artifact is built by the pipeline, immutable, content-addressed (digest D+1), and its provenance/build record is archived.
- **P3 — Configuration readiness:** configuration revision C+1 is reviewed and versioned; secrets are referenced by name and resolved at runtime from the secret store — never embedded in the artifact, the configuration, or release commands.
- **P4 — Known good current state:** V currently serves 100% of traffic; every instance passes its health check; baseline metrics (error ratio, latency percentiles, saturation, per-route error ratio) are captured and archived.
- **P5 — Rollback readiness:** artifact V (digest D) and configuration revision C are retained and reachable; the rollback path (redeploy V, or re-point traffic to the previous environment in a blue/green topology) has been exercised successfully in a non-production environment; the rollback decision authority is named.
- **P6 — Data compatibility gate:** the release contains no irreversible data or schema migration. Any required migration is backward-compatible, applied separately, and completed and verified before Step 2. If this gate cannot be satisfied, do not start (see A6).
- **P7 — Capacity:** the environment can run V and V+1 concurrently for the transition with headroom above the peak-traffic baseline, so the minimum healthy capacity is never breached.
- **P8 — Observability:** health checks, error/latency metrics, instance inventory, and logs are live and cover both V and V+1, and alerting routes to the on-duty operator. No new observation mechanism is introduced for the release.
- **P9 — Interface compatibility:** no breaking interface change; any change is additive and versioned, and consumers were informed per the change record.
- **P10 — Tooling guarantees:** the deploy/rollback tooling is known to be idempotent (re-running converges to the same state) and to honor the minimum-healthy-capacity and connection-draining constraints.

### 2. Ordered steps

Per-step verification (item 3) and per-step rollback (item 4) are stated inline for each step.

#### Step 0 — Record baseline and announce start
Action: freeze unrelated changes for the window; record current version V (digest D), configuration revision C, instance inventory, and baseline metrics; announce release start on the agreed channel.
- **Verification:** recorded version/config/inventory match live inventory; health checks green; baseline snapshot archived and readable.
- **Rollback:** none required (no state changed). If the baseline cannot be established, abort under A5.

#### Step 1 — Stage the V+1 artifact (no traffic change)
Action: place artifact V+1 (digest D+1) and rendered configuration C+1 into the target environment's artifact store; no serving instance is touched.
- **Verification:** stored artifact digest equals D+1 (checksum match); configuration renders without errors and contains no plaintext secrets; instance inventory unchanged.
- **Rollback:** remove the staged artifact and rendered configuration; V continues serving unaffected.

#### Step 2 — Launch a single canary instance of V+1
Action: start one instance of V+1, receiving only health checks or a minimal canary traffic slice; all other instances remain on V.
- **Verification:** canary passes its health check; startup logs show no fatal errors; canary receives no more than the intended traffic share; the V instances remain healthy.
- **Rollback:** stop and remove the canary instance; confirm the instance set is exactly the pre-release state.

#### Step 3 — Canary observation window
Action: route an agreed small fixed share of production traffic to the canary for an agreed window (at least one full traffic cycle), holding all other instances on V.
- **Verification:** compare canary vs. baseline on error ratio, latency percentiles, saturation, and per-route error ratio against agreed thresholds; scan canary logs for new error classes; confirm dependency capacity is stable.
- **Rollback:** shift the canary traffic share back to V, then stop and remove the canary instance.

#### Step 4 — Rolling expansion in bounded batches
Action: replace instances V → V+1 in bounded batches (one or a small fixed number), draining connections before stop, never dropping below minimum healthy capacity, pausing after each batch for verification.
- **Verification (per batch):** all instances healthy; error ratio and latency within thresholds; healthy instance count never below the minimum; batch completes within its time box.
- **Rollback:** halt the rollout; drain and remove upgraded V+1 instances and start replacements on V until the set is 100% V; if drain-based revert is not possible, redeploy V to the whole set.

#### Step 5 — Full cutover
Action: bring the remaining instances to V+1 so 100% of production traffic is served by V+1.
- **Verification:** version inventory shows 100% V+1; all instances healthy; end-to-end synthetic checks pass; error ratio and latency at or below baseline; no unresolved alerts.
- **Rollback:** redeploy V to 100% via the same mechanism (or re-point traffic to the previous environment in a blue/green topology).

#### Step 6 — Post-release soak
Action: hold the release under observation for the agreed soak period; no further changes to S.
- **Verification:** metrics remain at baseline; alerts silent; correctness and consumer-facing checks pass; capacity stable.
- **Rollback:** execute the Step 5 rollback to V; retain V+1 and all evidence for diagnosis; reopen the change record as failed.

#### Step 7 — Finalize
Action: mark the release complete in the change record; close the window; unfreeze unrelated changes; announce completion; archive digests, configuration revision, and release notes.
- **Verification:** change record closed-complete; version inventory remains 100% V+1; dashboards stable; archived evidence readable.
- **Rollback:** metadata-only reversal of the record plus re-announcement; if a defect appears later, perform the Step 5 rollback and reopen the record.

### 3. Per-step verification

Each step above carries an explicit `Verification:` line; collectively they form the per-step verification set. Summary index: Step 0 → baseline integrity; Step 1 → artifact digest + secret-free rendered config + unchanged inventory; Step 2 → canary health + bounded traffic share + V health; Step 3 → canary-vs-baseline metrics + log scan; Step 4 → per-batch health/capacity/time-box; Step 5 → 100% inventory + end-to-end checks + baseline metrics; Step 6 → soak stability; Step 7 → record/inventory/dashboard consistency.

### 4. Per-step rollback

Each step above carries an explicit `Rollback:` line. Summary index: Step 0 → none needed (abort if baseline unknown); Step 1 → unstage artifact/config, no traffic impact; Step 2 → remove canary; Step 3 → return traffic share to V, remove canary; Step 4 → halt, revert upgraded instances to V (or redeploy V fleet-wide); Step 5 → redeploy V to 100%; Step 6 → revert to V, retain evidence; Step 7 → reverse the metadata record and reopen on defect.

### 5. Explicit abort criteria

Any single condition triggers abort of the whole release:

- **A1:** canary or any upgraded instance fails its health check, crashes, or restarts repeatedly.
- **A2:** error ratio (overall or per route) exceeds the agreed absolute threshold or exceeds baseline by more than the agreed margin.
- **A3:** latency percentiles exceed the agreed threshold, sustained beyond the agreed short-window tolerance.
- **A4:** any data-corruption signal, security signal, or availability/SLO breach.
- **A5:** the current state (version, inventory, configuration, baseline) cannot be established with confidence.
- **A6:** rollback readiness is lost at any point (previous artifact/configuration unreachable, rollback tooling failing, or an irreversible migration not covered by P6 is discovered).
- **A7:** the operator loses access to monitoring or the deploy/rollback control path.
- **A8:** a step exceeds its agreed time box without completing verification.
- **A9:** a concurrent incident or conflicting change is detected in the same environment.

Abort behavior: stop at the current step, execute that step's rollback, return to 100% V, freeze further change, and record the evidence. The rollback decider declares the release failed and the change record is reopened.

### 6. Single most likely failure mode and its detection signal

- **Most likely failure mode:** V+1 passes health checks but contains a silent behavioral regression under the real production traffic mix — an edge-case path, input shape, or dependency interaction not exercised by health checks or smoke tests. Because aggregate health stays green, the rollout continues and the defect silently reaches a large share of traffic.
- **Why most likely:** the health check validates only liveness/readiness on a trivial path, the canary window is short relative to rare traffic shapes, and this defect class produces no crash, no restart, and no infrastructure alarm — so the procedure's structural safeguards do not catch it unaided.
- **Detection signal:** a segmented metric divergence — specifically, the canary slice's per-route (or per-dependency-call) error ratio or latency percentile diverges from the concurrently measured baseline by more than the abort margin while the health check stays green and aggregate instance health is unchanged. Secondary confirmation: a new error/log class appears only in the canary slice.

## Evidence

- **Observed (read-only, inside scope):** `ls -la` on the scope directory shows it exists and contains `agents/` and `ledger.md`; `ls -la` on `agents/` shows the expected artifact directory. Commands run: two directory listings only. No file contents outside this artifact were read.
- **Observed:** no project-local AGENTS.md exists inside the scope subtree; the global AGENTS.md was available in context via the runtime configuration. No out-of-scope file was read.
- **Observed:** this artifact was written to the exact required path and read back; all required section headings (Task / Scope / Result / Evidence / Defects-blockers / Remaining claims-exclusions / Terminal state) and all six required content items (preconditions; ordered steps; per-step verification; per-step rollback; abort criteria; most likely failure mode + detection signal) are present.
- **Observed:** the only write performed was this file; no execution of any kind occurred.
- **Hypotheses / unvalidated content:** the release procedure, thresholds, time boxes, and failure-mode analysis are reasoning artifacts for a hypothetical service, not empirically validated facts. No claim is made that this procedure was executed, tested, or verified against any real system.

## Defects-blockers

- None. The dispatch was valid, the required artifact was produced at the exact path, and no blocker prevented completion.
- Note (not a defect): end-to-end validation of the procedure would require a real non-production environment, which was explicitly out of scope; this is captured as an exclusion below.

## Remaining claims-exclusions

- The procedure was NOT executed; no environment, service, container, or infrastructure was touched, and none is claimed to exist.
- All thresholds, margins, time boxes, canary shares, and batch sizes are placeholders to be set per real service; none were validated against any workload.
- No security review, threat model, or compliance assessment of the hypothetical service was performed.
- The "stateless, no migration" assumption is not verified for any real service; P6 is an explicit gate an operator must satisfy.
- Tooling behavior (idempotency, drain semantics, blue/green mechanics) was not evaluated in any environment; blue/green is mentioned as an alternative but not designed in detail.
- The real path of this artifact is the only environment-specific detail present and is required by the dispatch; the release design itself references no real host, hostname, credential, endpoint, or infrastructure.

## Terminal state

DONE — all acceptance criteria satisfied; design-only deliverable complete; zero side effects.
