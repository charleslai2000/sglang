import struct,os,collections
p="/data/l3/fleet-forensics-v2-20260916/hicache.meta_-data-models-qwen35-9b-w4a16_0_1.wal.7"
fd=os.open(p,os.O_RDONLY); size=os.path.getsize(p); off=28
eid=collections.Counter(); gens=collections.Counter(); lens=collections.Counter()
while off<size:
    r=os.pread(fd,26,off); m,v,ft,fl,res,plen,seq=struct.unpack_from("<IHBBHIQ",r,0)
    if ft==1:
        pl=os.pread(fd,plen,off+26); o=40
        while o+21<=len(pl):
            kl=struct.unpack_from("<H",pl,o)[0]; o+=2
            if o+kl+21>len(pl): break
            o+=kl
            e,off_,ln,g,c=struct.unpack_from("<IIIQB",pl,o); o+=21
            eid[e]+=1; gens[g]+=1; lens[ln]+=1
    off+=26+plen
print("distinct extent_ids written=%d of 1024 ; total pages=%d"%(len(eid),sum(eid.values())))
print("top extent_id write counts:",eid.most_common(8))
print("extent_id count histogram (writes_per_slot: n_slots):",collections.Counter(eid.values()).most_common(8))
print("distinct generations=%d ; top gens:"%len(gens),gens.most_common(5))
print("page length histogram (bytes: count):",lens.most_common(6))
