import struct,os,collections
p="/data/l3/fleet-forensics-v2-20260916/hicache.meta_-data-models-qwen35-9b-w4a16_0_1.wal.7"
fd=os.open(p,os.O_RDONLY); size=os.path.getsize(p); off=28
ents=[]; setbytes=0; nset=0; klens=[]
while off<size:
    r=os.pread(fd,26,off); m,v,ft,fl,res,plen,seq=struct.unpack_from("<IHBBHIQ",r,0)
    if ft==1:
        pl=os.pread(fd,plen,off+26); o=40; n=0
        while o+21<=len(pl):
            kl=struct.unpack_from("<H",pl,o)[0]; o+=2
            if o+kl+21>len(pl): break
            o+=kl+21; n+=1; klens.append(kl)
        ents.append((seq,plen,n)); setbytes+=plen; nset+=1
    off+=26+plen
print("SET frames=%d SET bytes=%d (%.1f MB)"%(nset,setbytes,setbytes/1e6))
print("entries/SET min=%d max=%d mean=%.1f total=%d"%(min(e for _,_,e in ents),max(e for _,_,e in ents),sum(e for _,_,e in ents)/len(ents),sum(e for _,_,e in ents)))
print("keylen min/max/mean=%d/%d/%.1f"%(min(klens),max(klens),sum(klens)/len(klens)))
print("sample (seq,plen,entries):",ents[:6], ents[-3:])
