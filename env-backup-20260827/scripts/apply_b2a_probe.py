#!/usr/bin/env python3
"""B2A-PROBE: minimal read-only instrumentation of UnifiedRadixCache
(cache_unfinished_req / cache_finished_req insert points) for the six-item
records (radix node id, mamba slot/state id, mamba_exist, insert result,
key length, mamba checkpoint position).

Discipline (V2 probe style):
- .bak backup + md5 before/after;
- zero numeric-path changes: the probe only appends JSON lines to
  /tmp/b2a-cache.log, wrapped in try/except pass (cannot affect numerics);
- restore = cp .bak back (md5 must equal pre-probe md5).

Run inside the sglang-b0 container:
  python3 /tmp/apply_b2a_probe.py apply
  python3 /tmp/apply_b2a_probe.py restore
"""
import hashlib, sys, os

F = "/sgl-workspace/sglang/python/sglang/srt/mem_cache/unified_radix_cache.py"
BAK = F + ".bak-b2a"

PROBE_HELPER = '''
# B2A-PROBE (block 2a read-only instrumentation; appends JSON lines to
# /tmp/b2a-cache.log only, zero numeric-path change; removed after experiment)
def _b2a_probe(tag, req, key_len, eff_cache_len, result, insert_params, **extra):
    try:
        import json as _json
        import time as _time
        _node = getattr(result, "last_device_node", None) if result is not None else None
        _mv = getattr(insert_params, "mamba_value", None)
        _slot = None
        if _mv is not None:
            try:
                _slot = int(_mv.reshape(-1)[0].item())
            except Exception:
                _slot = "tensor"
        _rec = {
            "ts": round(_time.time(), 3),
            "tag": tag,
            "rid": getattr(req, "rid", None),
            "key_len": key_len,
            "eff_cache_len": eff_cache_len,
            "mamba_last_track_seqlen": getattr(req, "mamba_last_track_seqlen", None),
            "prefix_len": getattr(result, "prefix_len", None) if result is not None else None,
            "total_len": getattr(result, "total_len", None) if result is not None else None,
            "mamba_exist": getattr(result, "mamba_exist", None) if result is not None else None,
            "node_id": getattr(_node, "id", None),
            "mamba_slot": _slot,
        }
        _rec.update(extra)
        with open("/tmp/b2a-cache.log", "a") as _f:
            _f.write(_json.dumps(_rec) + "\\n")
    except Exception:
        pass

'''

UNFINISHED_ANCHOR = "        result = self.insert(insert_params)\n\n        # Match prefix"
UNFINISHED_REPLACEMENT = (
    "        result = self.insert(insert_params)\n"
    "        _b2a_probe(\"unfinished\", req, page_aligned_len, effective_cache_len, result, insert_params, chunked=chunked)\n"
    "\n"
    "        # Match prefix"
)

FINISHED_ANCHOR = "            result = self.insert(insert_params)\n\n            # Free unaligned tail (+ deferred truncation tail)"
FINISHED_REPLACEMENT = (
    "            result = self.insert(insert_params)\n"
    "            _b2a_probe(\"finished\", req, page_aligned_len, effective_cache_len, result, insert_params, kv_len_to_handle=kv_len_to_handle)\n"
    "\n"
    "            # Free unaligned tail (+ deferred truncation tail)"
)

HELPER_ANCHOR = "from sglang.srt.mem_cache.radix_cache import RadixKey\n"
HELPER_REPLACEMENT = HELPER_ANCHOR + PROBE_HELPER


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "apply"
    if mode == "apply":
        s = open(F).read()
        assert s.count(UNFINISHED_ANCHOR) == 1, "unfinished anchor not unique"
        assert s.count(FINISHED_ANCHOR) == 1, "finished anchor not unique"
        assert s.count(HELPER_ANCHOR) == 1, "helper anchor not unique"
        assert "_b2a_probe" not in s, "probe already applied"
        pre = md5(F)
        open(BAK, "w").write(s)
        s2 = s.replace(UNFINISHED_ANCHOR, UNFINISHED_REPLACEMENT, 1)
        s2 = s2.replace(FINISHED_ANCHOR, FINISHED_REPLACEMENT, 1)
        s2 = s2.replace(HELPER_ANCHOR, HELPER_REPLACEMENT, 1)
        open(F, "w").write(s2)
        print(f"PRE_MD5={pre}")
        print(f"BAK_MD5={md5(BAK)}")
        print(f"POST_MD5={md5(F)}")
        print("PROBE_APPLIED_OK")
    elif mode == "restore":
        pre = md5(F)
        open(F, "w").write(open(BAK).read())
        post = md5(F)
        bak = md5(BAK)
        print(f"PRE_RESTORE_MD5={pre}")
        print(f"POST_RESTORE_MD5={post}")
        print(f"BAK_MD5={bak}")
        assert post == bak, "restore md5 mismatch"
        print("PROBE_RESTORED_OK")
    else:
        print("usage: apply_b2a_probe.py {apply|restore}")
        sys.exit(1)


if __name__ == "__main__":
    main()
