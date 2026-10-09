# EXEC-20260908-P0-BARRIER-VEHICLE

status: blocked
invocation: NEEDS_REASONING

The authorized tooling files were created and made fail-closed: synthetic data is
available only with `--dry-run`, while normal execution requires a supplied live
`p0_durable.v2` event stream. A dry-run reports `NOT_VERIFIED`; it cannot claim a
production PASS.

The requested real integration cannot be completed safely within this invocation.
`3090-dev/gate3_parked.py` owns its build and warm request loop internally. It has
no per-session callback or transport hook between build completion and warm request
issuance where this driver can wait for both `durability_barrier` and
`residency_barrier`. Wrapping it as a subprocess would allow the existing loop to
issue warm requests before those barriers and would violate the acceptance contract.
The driver therefore refuses `--live` with this exact gap rather than weakening the
gate or launching a non-conforming vehicle.

Evidence:

- `python3 -m py_compile 3090-dev/rh_durability_driver.py 3090-dev/rh_durability_analyze.py` passed.
- `python3 3090-dev/rh_durability_driver.py --dry-run ...` reports `NOT_VERIFIED`.
- `rh_durability_analyze.py` reports `FAIL` for the fixture because short suffixes
  are excluded and the fixture is not an acceptance run.
- No remote vehicle was launched and no product files were modified.

Artifacts changed: `3090-dev/rh_durability_driver.py`,
`3090-dev/rh_durability_analyze.py`, and this report. Existing gate3 files were not
changed.

Followup requiring a fresh Task ID: expose an authorized client-level request hook
or implement the S=25 build/warm HTTP client in this vehicle so each session's warm
request is dispatched only after live keyed barriers have been observed.

Open issue: real S=25 execution and real evidence bundle remain outstanding.
