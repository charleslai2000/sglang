# T004 Owner10 Nsight timeline analysis — 2026-10-19

## Result

Owner10 (`falcon-t004-owner10-20261019T1000Z`) is a successful high-pressure service run (`nsys_rc=0`, `driver_rc=0`, 107,741,893-byte report), and its same-run RID → Scheduler iteration → FPM/NVTX step identity is valid. It is **not** valid per-RID CUDA Runtime/Kernel timing evidence for the measured B/C/D prefills: all three exact step NVTX windows contain zero CUPTI Runtime API and zero CUDA Kernel events.

| arm | RID | Scheduler iteration | FPM wall (s) | step NVTX (ns) | Runtime APIs in step | Kernels in step |
|---|---|---:|---:|---:|---:|---:|
| B | `51aef825b2af4713b20dd2337ec012cb` | 1050 | 0.314425 | 112138476637–112421961880 | 0 | 0 |
| C | `ea4ccb2921f34e36ab1c670bdc1bad89` | 1051 | 0.321813 | 112474494336–112745295256 | 0 | 0 |
| D | `45b2aafbcea14a5e91b37855cf258258` | 1052 | 0.368603 | 112791070664–113114914645 | 0 | 0 |

The server's same-run request records independently give B/C/D prefill wall times 303.662/310.314/359.801 ms. These are service prefill wall measurements, **not** GPU Kernel execution time. The Scheduler-to-Nsight NVTX time mapping is consistent. In contrast, the TP-worker CUDA activity ends at Nsight timestamp 111,081,191,902 ns (last Kernel 111,096,791,440 ns), before all three step windows; target Nsight timestamp domain is not repaired by choosing an inferred offset. Offset scans produce non-unique sets of unrelated kernels and are rejected.

Exact auxiliary H2D evidence is separately available by the submitted node identity: B node 93 / operation 27 / 370,720,768 bytes / CUDA-event elapsed 40.984 ms; C node 94 / operation 28 / 370,810,880 bytes / 36.947 ms; D node 96 / operation 29 / 370,720,768 bytes / 36.785 ms. These asynchronous transfer/event measurements do not substitute for step GPU compute time and are not added to FPM wall.

## Diagnosis

`falcon.sqlite` has 1,390,067 Kernel events and 168,573 Runtime events overall, with CUDA Runtime/Kernel coverage only through ~111.1 s; B/C/D NVTX ranges run from 112.14 to 113.11 s. The capture ended normally; increasing the post-run Nsight wait did not extend this activity coverage. Nsight diagnostics in this same report explicitly say the installed CUDA driver version 13.0 is unsupported by Nsight Systems 2025.1.3 and collection uses its CUDA 12.9 library. There is also a GPU metrics sampling buffer overflow diagnostic. These are concrete capture-integrity warnings, but do not alone prove the cause of the missing tail activity.

The prior hypothesis that the Nsight runner's 180-second report wait truncated the capture is falsified by this complete `rc=0` report. No evidence supports assigning the gap to application `cudaProfilerStop` either: the capture uses `--capture-range=none`, and no profiler start/stop calls were found among recorded Runtime APIs. Keep the causal mechanism unresolved until a controlled same-run clock/activity calibration tests the new buffer policy.

## Next experiment

`run_nsys_timeline.py` is a pre-existing untracked working file; it remains untracked and was not staged. Its next-run Nsight command and manifest now include `--cuda-flush-interval=1000` and `--flush-on-cudaprofilerstop=false`. This is a candidate capture-strategy change, not a verified solution. A no-GPU re-export of Owner10's saved `.nsys-rep` to `/tmp/falcon-owner10-flush-compare.sqlite` produced byte-identical SQLite size (1,391,718,400 bytes), Kernel count/end (1,390,067 / 111,096,794,896 ns), and Runtime count/end (168,573 / 111,081,191,902 ns) to the existing export. This rules out export settings as a way to restore the missing events; it does not test live buffer flushing. Do not launch another full GPU capture merely on the strength of this hypothesis. First inspect saved report capture-range/process lifecycle and identify a supported profiler/driver combination or a bounded calibration capture that is demonstrably capable of recording a known CUDA synchronization/kernel event across the current gap. Then, if that provides a distinct test, run under the exclusive GPU lock and preserve full B/C/D workload. Keep `NOT_VERIFIED` for per-RID GPU time, L0 utilization, and physical-media attribution.

## Artifacts and checks

- Raw report/export: `falcon-t004-owner10-20261019T1000Z-nsys/falcon.nsys-rep`, `falcon.sqlite`
- Run manifest/status: same directory `run-manifest.json`, `capture-status.json`
- RID mapping/workload: sibling `ab-falcon-t004-owner10-20261019T1000Z.json`, `timeline.jsonl`, `fpm.jsonl`, `requests.jsonl`
- Source audit: TP-worker process PID 182337; exact target `sglang.step` NVTX ranges and zero direct Runtime/Kernel matches confirmed in SQLite.
- `run_nsys_timeline.py` py_compile passed; `git diff --check` passed. The source is untracked (pre-existing state); no staging/commit performed.
- Post-capture GPU: 0% utilization, 1 MiB used; exclusive flock was available. No new GPU run was started during this analysis.
