#!/usr/bin/env python3
import sqlite3, json

p = "/data/sglang-hicache/g2-quasar-runs/20261113T-t004-stage-replay.sqlite"
c = sqlite3.connect(p)
c.row_factory = sqlite3.Row


def query(sql, args=()):
    return [dict(r) for r in c.execute(sql, args)]


# List captured GraphExecs and graph kernel launches. Nsight represents graph nodes as
# kernel records with launchType=2; regular direct launches are launchType=1.
print(
    "launch types",
    query(
        "select launchType,count(*) count from CUPTI_ACTIVITY_KIND_KERNEL group by launchType"
    ),
)
print("graph traces", query("select * from CUPTI_ACTIVITY_KIND_GRAPH_TRACE"))
print(
    "graph events",
    query(
        "select e.*,s.value event from CUDA_GRAPH_EVENTS e join StringIds s on s.id=e.nameId where e.eventClass in (94,95)"
    ),
)
print(
    "kernel names",
    query(
        "select k.launchType,s.value name,count(*) count,min(k.gridX) gridX,min(k.gridY) gridY,min(k.gridZ) gridZ,min(k.blockX) blockX,min(k.blockY) blockY,min(k.dynamicSharedMemory) dynsm,min(k.streamId) streamId from CUPTI_ACTIVITY_KIND_KERNEL k join StringIds s on s.id=k.demangledName group by k.launchType,s.value order by count desc"
    ),
)
print(
    "graph id join",
    query(
        "select t.graphId,t.graphExecId,t.streamId,k.launchType,s.value,k.gridX,k.gridY,k.gridZ,k.blockX,k.blockY,k.blockZ,k.dynamicSharedMemory,k.graphNodeId,count(*) cnt from CUPTI_ACTIVITY_KIND_GRAPH_TRACE t join CUPTI_ACTIVITY_KIND_KERNEL k on k.correlationId=t.correlationId join StringIds s on s.id=k.demangledName group by t.graphId,t.graphExecId,t.streamId,k.launchType,s.value,k.gridX,k.gridY,k.gridZ,k.blockX,k.blockY,k.blockZ,k.dynamicSharedMemory,k.graphNodeId"
    ),
)
