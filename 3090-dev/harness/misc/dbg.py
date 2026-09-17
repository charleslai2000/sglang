import faulthandler, sys, time
faulthandler.dump_traceback_later(15, exit=True)
sys.argv = ["x", "/tmp/opencode/l3-reclaim-20260916/scratch-fleet"]
import repro_wal_discontinuity as r
print("loaded module", flush=True)
m = r.load_metadata_module()
print("metadata module loaded", flush=True)
print(r.run(m, "/tmp/opencode/l3-reclaim-20260916/scratch-fleet"))
