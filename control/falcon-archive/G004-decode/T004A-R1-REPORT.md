# G004 / T004A-R1 — Privileged Counter Access Qualification

## Verdict

```text
T004A-R1: PASS
T004 remains BLOCKED pending CUDA-graph Marlin qualification
```

The ordinary-user control reproduced the known permission failure. The
privileged qualification then succeeded after authorized sudo access was made
available. No driver, module, sudo, system, SGLang, or production configuration
was changed.

## Normal-user probe

The same standalone CUDA probe was rebuilt with the existing CUDA toolkit:

```text
compiler: /usr/local/cuda-12.9/bin/nvcc
probe result: probe-ok
```

Nsight Compute:

```text
/opt/nvidia/nsight-compute/2025.2.1/ncu
version: 2025.2.1.0
```

Normal-user capture result:

```text
connected: yes
performance counters accessible: no
error: ERR_NVGPUCTRPERM
probe exit: 0
ncu exit: 1
```

Exact profiler behavior:

```text
==PROF== Connected to process ...
==ERROR== ERR_NVGPUCTRPERM - The user does not have permission to access
NVIDIA GPU Performance Counters on the target device 0.
probe-ok
==PROF== Disconnected from process ...
```

This confirms the probe itself runs normally and the failure is specifically
counter access.

## Privileged probe

The same standalone probe was profiled with the existing Nsight Compute binary
under sudo:

```text
sudo /opt/nvidia/nsight-compute/2025.2.1/ncu \
  --target-processes application-only \
  --set basic \
  --export /tmp/g004_t004a-privileged \
  --force-overwrite \
  /tmp/g004_t004a_probe
```

Result:

```text
connected: yes
profiling: 8 passes completed
ERR_NVGPUCTRPERM: absent
probe output: probe-ok
ncu exit: 0
report: /tmp/g004_t004a-privileged.ncu-rep
size: 83K
```

The imported report contains real numeric metrics, including:

```text
gpu__time_duration.avg: 2.62 us
gpu__dram_throughput.avg.pct_of_peak_sustained_elapsed: 0.81%
gpu__compute_memory_throughput.avg.pct_of_peak_sustained_elapsed: 1.79%
sm__inst_executed.avg.pct_of_peak_sustained_elapsed: 0.16%
```

Therefore privileged performance-counter access is confirmed. The report was
only imported/read for qualification; no formal Marlin or serving profile was
run.
## Permission root cause audit

Current loaded-driver state:

```text
GPU: RTX 3090
driver: 580.178.04
loaded module: /lib/modules/6.8.0-139-generic/updates/dkms/nvidia.ko.zst
RmProfilingAdminOnly: 1
```

The module exposes:

```text
NVreg_RestrictProfilingToAdminUsers:int
```

Read-only configuration audit found no current explicit profiling override in:

```text
/etc/modprobe.d
/etc/modules-load.d
/etc/initramfs-tools
/etc/default
/proc/cmdline
```

The only NVIDIA modprobe configuration found was:

```text
/etc/modprobe.d/nvidia-graphics-drivers-kms.conf
options nvidia-drm modeset=1
```

No configuration was written.

The currently loaded value is consistent with the driver default/admin-only
policy. A persistent non-admin path would normally require an authorized
modprobe option such as:

```text
options nvidia NVreg_RestrictProfilingToAdminUsers=0
```

Exact deployment impact was not applied or tested. Depending on module loading
and initramfs state, making such a setting effective may require module reload
or reboot; this task did not perform either. Rollback would be removal of the
added option followed by the corresponding authorized module reload/reboot
procedure. No `update-initramfs` was run.

## Production changes

```text
NONE
```

No SGLang server was started. No benchmark or Nsight Systems capture was run.

## Required next action

T004A-R1 is complete. Do not change driver/module policy based only on this
qualification. The next separate authorization is CUDA-graph compatibility
qualification using the target Marlin kernel; do not start formal T004 until
that qualification passes.