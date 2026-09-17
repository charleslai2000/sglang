import struct,os,collections
p="/data/l3/fleet-forensics-v2-20260916/hicache.meta_-data-models-qwen35-9b-w4a16_0_1.wal.7"
fd=os.open(p,os.O_RDONLY); size=os.path.getsize(p); off=28
seen=collections.Counter(); total=0; entbytes=0; commits=0
comp=collections.Counter(); seqs=[]
while off<size:
    r=os.pread(fd,26,off); m,v,ft,fl,res,plen,seq=struct.unpack_from("<IHBBHIQ",r,0)
    if ft==1:
        pl=os.pread(fd,plen,off+26); o=40; n=0; commits+=1
        while o+21<=len(pl):
            kl=struct.unpack_from("<H",pl,o)[0]; o+=2
            if o+kl+21>len(pl): break
            key=pl[o:o+kl]; o+=kl
            eid,off_,ln,gen,c=struct.unpack_from("<IIIQB",pl,o); o+=21
            key=(key,c)
            seen[key]+=1; total+=1; entbytes+=(ln if ln else 0); comp[c]+=1; n+=1
    off+=26+plen
print("commits(SET)=%d total_entries=%d distinct_keys=%d"%(commits,total,len(seen)))
mult=collections.Counter(seen.values())
print("write multiplicity histogram (times_written: count_of_keys):",sorted(mult.items())[:12], "...max=",max(mult))
print("keys written >1: %d (%.1f%% of total entries) ; distinct = %d"%(total-len(seen),100*(total-len(seen))/total,len(seen)))
print("component histogram:",comp.most_common())
print("sum of entry lengths=%d (%.2f GB)"%(entbytes,entbytes/1e9))
