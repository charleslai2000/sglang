#!/usr/bin/env python3
"""Join existing FPM records to scheduler NVTX iteration ranges and CUDA launches."""
import json, sqlite3, re, statistics, sys
from pathlib import Path

def union_ns(rows):
    merged=[]
    for start,end in sorted(rows):
        if not merged or start>merged[-1][1]: merged.append([start,end])
        else: merged[-1][1]=max(merged[-1][1],end)
    return sum(b-a for a,b in merged)

def main():
    if len(sys.argv)!=4: raise SystemExit("usage: analyze_nsys.py falcon.sqlite scheduler-forward-pass.json out.json")
    db,fpm_path,out=map(Path,sys.argv[1:]); c=sqlite3.connect(db)
    ranges=[]
    for start,end,text,tid in c.execute("select e.start,e.end,s.value,e.globalTid from NVTX_EVENTS e join StringIds s on e.textId=s.id where s.value like 'sglang.step;worker=%' and e.end is not null order by e.start"):
        m=re.fullmatch(r"sglang.step;worker=([^;]+);iter=(\d+);stage=([^;]+);batch=(\d+);prefill_tokens=(\d+);decode_tokens=(\d+)",text)
        if not m: continue
        ranges.append({"start_ns":start,"end_ns":end,"worker":m[1],"iteration_id":int(m[2]),"stage":m[3],"batch":int(m[4]),"prefill_tokens":int(m[5]),"decode_tokens":int(m[6]),"scheduler_tid":tid,"nvtx":text})
    runtime={corr:(start,end,tid,name) for start,end,corr,tid,name in c.execute("select r.start,r.end,r.correlationId,r.globalTid,s.value from CUPTI_ACTIVITY_KIND_RUNTIME r join StringIds s on s.id=r.nameId where r.correlationId is not null")}
    kernels=[]
    for start,end,corr,gridx,gridy,gridz,blockx,blocky,blockz,nameid,globalpid,ctx,stream in c.execute("select k.start,k.end,k.correlationId,k.gridX,k.gridY,k.gridZ,k.blockX,k.blockY,k.blockZ,k.shortName,k.globalPid,k.contextId,k.streamId from CUPTI_ACTIVITY_KIND_KERNEL k"):
        api=runtime.get(corr)
        kernels.append({"start_ns":start,"end_ns":end,"correlation_id":corr,"runtime":api,"name_id":nameid,"global_pid":globalpid,"context_id":ctx,"stream_id":stream,"grid":[gridx,gridy,gridz],"block":[blockx,blocky,blockz]})
    fpm=json.loads(fpm_path.read_text())
    records=fpm.get("records",[])
    metric_defs={mid:name for mid,name in c.execute("select metricId,metricName from TARGET_INFO_GPU_METRICS")}
    metric_rows=list(c.execute("select timestamp,metricId,value from GPU_METRICS"))
    fpm_by_iter={int(r["iteration_id"]):r for r in records if r.get("iteration_id") is not None and int(r["iteration_id"])>=0}
    result=[]
    assigned=set()
    apis=list(runtime.items())
    for step in ranges:
        # Match CUDA launch API starts in the scheduler NVTX window by process
        # and wall timestamp (CUDA API calls may be issued by a worker thread).
        step_api_corrs={corr for corr,(a,b,tid,name) in apis
                        if (tid >> 32) in {step["scheduler_tid"] >> 32}
                        and step["start_ns"] <= a < step["end_ns"]}
        launches=[k for k in kernels if k["correlation_id"] in step_api_corrs]
        assigned.update(k["correlation_id"] for k in launches)
        ints=[(k["start_ns"],k["end_ns"]) for k in launches if k["end_ns"]>k["start_ns"]]
        clipped=[(max(step["start_ns"],a),min(step["end_ns"],b)) for a,b in ints
                 if min(step["end_ns"],b)>max(step["start_ns"],a)]
        ms=[(t,mid,v) for t,mid,v in metric_rows if step["start_ns"]<=t<step["end_ns"]]
        agg={}
        for t,mid,v in ms: agg.setdefault(metric_defs.get(mid,str(mid)),[]).append(v)
        result.append({**step,"scheduler_range_ms":(step["end_ns"]-step["start_ns"])/1e6,"fpm":fpm_by_iter.get(step["iteration_id"]),"kernel_launches":len(launches),"kernel_duration_sum_ms":sum(k["end_ns"]-k["start_ns"] for k in launches)/1e6,"kernel_interval_union_ms":union_ns(ints)/1e6,"kernel_union_overlap_with_step_ms":union_ns(clipped)/1e6,"launch_api_count":len(step_api_corrs),"gpu_metrics_sample_count":len({t for t,_,_ in ms}),"gpu_metrics_mean":{k:statistics.mean(v) for k,v in agg.items()},"gpu_kernel_names":len(set(k["name_id"] for k in launches))})
    fpm_iters=set(fpm_by_iter); step_iters={s["iteration_id"] for s in ranges}
    output={"database":str(db),"fpm_file":str(fpm_path),"step_ranges":len(ranges),"fpm_records":len(records),"fpm_iteration_records":len(fpm_iters),"range_iteration_ids_unique":len(step_iters)==len(ranges),"fpm_step_intersection":len(step_iters&fpm_iters),"fpm_missing_step_ids":sorted(step_iters-fpm_iters),"step_ids_missing_fpm":sorted(fpm_iters-step_iters),"runtime_rows":len(runtime),"kernel_rows":len(kernels),"kernels_with_runtime_parent":sum(k["runtime"] is not None for k in kernels),"kernels_attributed_to_step_by_runtime_start":len(assigned),"step_rows":result}
    out.write_text(json.dumps(output,indent=2)+"\n")
    print(json.dumps({k:v for k,v in output.items() if k!="step_rows"},indent=2))
if __name__=="__main__":main()
