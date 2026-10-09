# R76 disposable P0-B driver/reducer

This directory is an out-of-tree, disposable harness for the authorized RTX
3060 experiment. It does not modify product source, tests, gates, storage, or
Git. The driver uses only the public HTTP `/health` and `/generate` vehicles.

## Driver boundary

`p0b_driver.py` runs one `single-positive-hit` scenario, defaults to the local
public server at `http://127.0.0.1:30000`, and enforces a 600-second total
deadline and six-request hard ceiling (the normal path uses two requests).
Redirects are disabled so a server cannot cause hidden follow-up requests.

Public HTTP does not provide deterministic control or observation of a
HOST_ALLOC allocability change. Therefore the driver always terminates with a
structured `status: BLOCKED` result after recording the public response facts;
it never synthesizes allocator, generation, retry, reclaim, or READY events.
An optional `--trace-out` file contains the public-only trace and is
intentionally not accepted by the offline reducer.

Example (the expected result is BLOCKED unless a future public vehicle exposes
the required deterministic control):

```bash
python3 p0b_driver.py \
  --base-url http://127.0.0.1:30000 \
  --trace-out /tmp/p0b-r76-public.json
```

The process exits `2` for a structured BLOCKED result. It does not claim that
HOST_ALLOC was exercised.

## Offline reducer

`p0b_reducer.py` accepts only `p0b.trace.v1` JSON traces with explicit
request/session/node/build identity on every event. It fails closed on missing,
unknown, out-of-order, or conflicting evidence. The accepted trace must prove
all eleven oracle items:

1. one exact RID/session/node/build identity;
2. positive full KV and Mamba hit;
3. genuine non-allocability / terminal allocation failure, not a miss;
4. `WAIT_CAPACITY` + `HOST_ALLOC` park;
5. a real allocability change;
6. a relevant generation advance;
7. exactly one FIFO retry;
8. bounded reclaim and full-span allocation;
9. complete KV+Mamba restore and `READY`;
10. no crop and no genuine miss;
11. no same-generation wake and no repeated retry.

The synthetic trace in `test_reducer.py` is intentionally the only positive
fixture. Negative fixtures cover incomplete evidence, same-generation wake,
crop, and repeated retry. A live public-only driver trace is incomplete and is
rejected as designed.

## Verification

```bash
./run_selftests.sh
```

`manifest.sha256` is generated over the five source/readme/test/runner files,
sorted by relative path. The manifest excludes itself and the invocation report
to avoid a circular digest.
