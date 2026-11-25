#!/home/ubuntu/venvs/sglang-3090/bin/python
"""Low-rate NVML sample for an explicitly delimited R17 GPU run window."""
import argparse,csv,json,signal,time
from pathlib import Path
import pynvml
p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--interval',type=float,default=1);p.add_argument('--tag',required=True);a=p.parse_args();stop=False
def end(*_):
 global stop;stop=True
signal.signal(signal.SIGTERM,end);signal.signal(signal.SIGINT,end)
pynvml.nvmlInit();h=pynvml.nvmlDeviceGetHandleByIndex(0);supported=pynvml.nvmlDeviceGetSupportedClocksThrottleReasons(h);reasons={}
for k,v in [('idle',pynvml.nvmlClocksThrottleReasonGpuIdle),('applications',pynvml.nvmlClocksThrottleReasonApplicationsClocksSetting),('sw_power',pynvml.nvmlClocksThrottleReasonSwPowerCap),('hw_slowdown',pynvml.nvmlClocksThrottleReasonHwSlowdown),('hw_thermal',pynvml.nvmlClocksThrottleReasonHwThermalSlowdown),('hw_power_brake',pynvml.nvmlClocksThrottleReasonHwPowerBrakeSlowdown),('sw_thermal',pynvml.nvmlClocksThrottleReasonSwThermalSlowdown)]:
 if supported&v:reasons[str(v)]=k
fields=['wall_time_ns','elapsed_s','gpu_util_pct','memory_util_pct','memory_used_bytes','power_w','temp_c','sm_clock_mhz','mem_clock_mhz','throttle_active_mask','throttle_active_names']
start=time.monotonic();path=Path(a.out)
with path.open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
 while not stop:
  now=time.monotonic();active=pynvml.nvmlDeviceGetCurrentClocksThrottleReasons(h)
  try: names=';'.join(name for k,name in reasons.items() if active&int(k))
  except Exception:names='unavailable'
  x=pynvml.nvmlDeviceGetUtilizationRates(h);mem=pynvml.nvmlDeviceGetMemoryInfo(h)
  w.writerow({'wall_time_ns':time.time_ns(),'elapsed_s':now-start,'gpu_util_pct':x.gpu,'memory_util_pct':x.memory,'memory_used_bytes':mem.used,'power_w':pynvml.nvmlDeviceGetPowerUsage(h)/1000,'temp_c':pynvml.nvmlDeviceGetTemperature(h,pynvml.NVML_TEMPERATURE_GPU),'sm_clock_mhz':pynvml.nvmlDeviceGetClockInfo(h,pynvml.NVML_CLOCK_SM),'mem_clock_mhz':pynvml.nvmlDeviceGetClockInfo(h,pynvml.NVML_CLOCK_MEM),'throttle_active_mask':hex(active),'throttle_active_names':names});f.flush();time.sleep(a.interval)
pynvml.nvmlShutdown()
