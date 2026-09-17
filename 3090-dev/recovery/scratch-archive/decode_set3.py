import struct,os,collections
p="/data/l3/fleet-forensics-v2-20260916/hicache.meta_-data-models-qwen35-9b-w4a16_0_1.wal.7"
fd=os.open(p,os.O_RDONLY)
size=os.path.getsize(p)
off=28; setbytes=0; nset=0; ents=[]; memb=[]; plens=collections.Counter()
while off<size:
    r=os.pread(fd,26,off)
    m,v,ft,fl,res,plen,seq=struct.unpack_from("<IHBBHIQ",r,0)
    if ft==1:
        pl=os.pread(fd,plen,off+26)
        o=16; gseq=struct.unpack_from("<Q",pl,o)[0]; o+=8
        bid=struct.unpack_from("<Q",pl,o)[0]; o+=8
        mi=struct.unpack_from("<I",pl,o)[0]; o+=4
        mc=struct.unpack_from("<I",pl,o)[0]; o+=4
        n=0
        while o+21<=len(pl):
            kl=struct.unpack_from("<H",pl,o)[0]; o+=2+kl+18; n+=1
        ents.append(n); memb.append((mi,mc)); setbytes+=plen; nset+=1; plens[plen]+=1
    off+=26+plen
print("SET frames=%d total SET bytes=%d (%.1f MB)"%(nset,setbytes,setbytes/1e6))
print("entries/SET min=%d max=%d mean=%.1f"%(min(ents),max(ents),sum(ents)/len(ents)))
print("member_index range=%d..%d  member_count values=%s"%(min(m for m,_ in memb),max(m for m,_ in memb),collections.Counter(c for _,c in memb).most_common(5)))
print("payload_len distribution top:",plens.most_common(6))
