#!/usr/bin/env python3
import argparse, collections, hashlib, json, math, struct
from pathlib import Path
import numpy as np
from gguf import GGUFReader

QK = 256
BLOCK_BYTES = 110

def official(path):
    m = {}
    for line in Path(path).read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#'): continue
        name, typ = line.rsplit(':', 1)
        m[name.strip()] = typ.strip()
    return m

def scan(gguf_path, alloc_path):
    r=GGUFReader(gguf_path)
    local={t.name:t.tensor_type.name for t in r.tensors}
    off=official(alloc_path)
    names=sorted(set(local)|set(off))
    diff=[(n,local.get(n),off.get(n)) for n in names if local.get(n)!=off.get(n)]
    hist=collections.Counter(local.values())
    iq=[t for t in r.tensors if t.tensor_type.name=='IQ3_S']
    rows=[]; total_blocks=0; nonfinite_blocks=0; nan=0; inf=0
    for t in iq:
        # GGUF stores tensor shape as [K,N]; ReaderTensor.data is [N, row_bytes].
        shape=tuple(int(x) for x in t.shape)
        data=np.asarray(t.data)
        if shape[0] % QK: raise RuntimeError(f'{t.name}: K={shape[0]} not divisible by {QK}')
        blocks_per_row=shape[0]//QK
        expected=(shape[1], blocks_per_row*BLOCK_BYTES)
        if data.shape != expected: raise RuntimeError(f'{t.name}: data={data.shape} expected={expected}')
        raw=np.ascontiguousarray(data).reshape(shape[1], blocks_per_row, BLOCK_BYTES)
        d=raw[:,:,:2].copy().view('<f2').reshape(shape[1],blocks_per_row)
        nf=~np.isfinite(d)
        n_nan=int(np.isnan(d).sum()); n_inf=int(np.isinf(d).sum())
        count=int(nf.sum()); total=int(d.size)
        total_blocks+=total; nonfinite_blocks+=count; nan+=n_nan; inf+=n_inf
        if count:
            coords=[]
            for row, block in np.argwhere(nf):
                coords.append({'logical_row':int(row),'block':int(block),'row_start':int(block*QK),'row_end':int((block+1)*QK-1),'d_bits':int(raw[row,block,0]) | int(raw[row,block,1])<<8,'value':float(d[row,block])})
            rows.append({'name':t.name,'shape':list(shape),'data_shape':list(data.shape),'blocks':total,'nonfinite_blocks':count,'nan_blocks':n_nan,'inf_blocks':n_inf,'coords':coords})
    # Independent orientation facts from GGUF tensor shape and raw byte layout.
    orientation=[]
    for t in iq[:3]:
        shape=tuple(int(x) for x in t.shape); data=np.asarray(t.data)
        orientation.append({'name':t.name,'gguf_shape_K_N':list(shape),'reader_data_shape_N_rowbytes':list(data.shape),'logical_rows':shape[1],'blocks_per_logical_row':shape[0]//QK,'bytes_per_block':BLOCK_BYTES,'ne0_K':shape[0],'ne1_N':shape[1]})
    return {'gguf':gguf_path,'gguf_sha256':hashlib.sha256(Path(gguf_path).read_bytes()).hexdigest(),'allocation_sha256':hashlib.sha256(Path(alloc_path).read_bytes()).hexdigest(),'tensor_count_local':len(local),'tensor_count_official':len(off),'type_histogram':dict(sorted(hist.items())),'iq3_s_tensor_count':len(iq),'iq3_s_total_blocks':total_blocks,'iq3_s_nonfinite_blocks':nonfinite_blocks,'iq3_s_nan_blocks':nan,'iq3_s_inf_blocks':inf,'affected_tensors':rows,'exact_tensor_qtype_diff':diff,'orientation_samples':orientation}

if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('gguf'); p.add_argument('allocation'); p.add_argument('--json',required=True); a=p.parse_args()
 result=scan(a.gguf,a.allocation); Path(a.json).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 print(json.dumps({k:result[k] for k in ('gguf_sha256','allocation_sha256','tensor_count_local','tensor_count_official','iq3_s_tensor_count','iq3_s_total_blocks','iq3_s_nonfinite_blocks','iq3_s_nan_blocks','iq3_s_inf_blocks','exact_tensor_qtype_diff')},indent=2))
