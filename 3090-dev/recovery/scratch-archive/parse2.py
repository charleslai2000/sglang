import struct,os
d="/data/l3/local-prod-v1"
mp=os.path.join(d,"hicache.meta_-data-models-qwen35-9b-w4a16_0_1.manifest")
data=open(mp,"rb").read()
ck,floor,agen=struct.unpack_from("<QQQ",data,16); 
nslots=struct.unpack_from("<I",data,16+40)[0]
o=16+40+4+16+16+16+4
gens=struct.unpack_from("<%dQ"%nslots,data,o); o+=8*nslots
curs=struct.unpack_from("<%dI"%nslots,data,o); o+=4*nslots
sb=struct.unpack_from("<%dQ"%nslots,data,o); o+=8*nslots
ns=struct.unpack_from("<I",data,16+40+4+16+16+16)[0]
print("local-prod-v1 manifest: checkpoint_lsn=%d wal_floor=%d wal_active_gen=%d num_slots=%d next_slot=%d"%(ck,floor,agen,nslots,ns))
print(" slot_bytes_sum=%d nonzero=%d gens_distinct=%s"%(sum(sb),sum(1 for x in sb if x),set(gens)))
ec_off=o+4+struct.unpack_from("<I",data,o)[0]*4
ec=struct.unpack_from("<I",data,ec_off)[0]
print(" entry_count=%d"%ec)
for name in ["hicache.meta_-data-models-qwen35-9b-w4a16_0_1.wal.0"]:
    p=os.path.join(d,name); size=os.path.getsize(p)
    fd=os.open(p,os.O_RDONLY); h=os.pread(fd,28,0)
    m,v,fl,g,b=struct.unpack_from("<IHHQQ",h,0)
    print(" %s size=%d gen=%d base_lsn=%d"%(name,size,g,b))
    off=28; first=None; last=None; n=0; prev=None; disc=0
    while off<size:
        if size-off<26: print("  trailing",size-off); break
        r=os.pread(fd,26,off)
        mm,vv,ft,ff,rr,plen,seq=struct.unpack_from("<IHBBHIQ",r,0)
        if mm!=0x484D3146: print("  bad magic at",off); break
        if off+26+plen>size: print("  truncated at",off); break
        if first is None: first=(off,seq,ft,plen)
        if prev is not None and seq!=prev+1: disc+=1
        prev=seq; last=(off,seq,ft,plen); n+=1; off+=26+plen
    print("  frames=%d first=%s last=%s disc=%d end=%d"%(n,first,last,disc,off))
