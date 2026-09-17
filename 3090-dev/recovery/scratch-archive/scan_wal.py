import struct, os, sys
p="/data/l3/fleet-forensics-v2-20260916/hicache.meta_-data-models-qwen35-9b-w4a16_0_1.wal.7"
size=os.path.getsize(p)
print("wal.7 size",size)
fd=os.open(p,os.O_RDONLY)
hdr=os.pread(fd,28,0)
magic,ver,flags,gen,base=struct.unpack_from("<IHHQQ",hdr,0)
print("seg magic=%08X ver=%d flags=%d generation=%d base_lsn=%d"%(magic,ver,flags,gen,base))
off=28
seqs=[]
types={}
n=0
first20=[]
last20=[]
discon=[]
prev=None
while off < size:
    off0=off
    if size-off < 26:
        print("TRAILING <26 at",off,"bytes",size-off); break
    r=os.pread(fd,26,off)
    m,v,ftype,fl,res,plen,seq=struct.unpack_from("<IHBBHIQ",r,0)
    if m!=0x484D3146:
        print("BAD FRAME MAGIC at",off,"0x%08X"%m); break
    total=26+plen
    if off+total>size:
        print("TRUNCATED frame at",off,"plen",plen,"need",total,"avail",size-off); break
    n+=1
    if prev is not None and seq!=prev+1:
        discon.append((off0,prev,seq))
    prev=seq
    if len(first20)<20: first20.append((off0,seq,ftype,plen))
    last20.append((off0,seq,ftype,plen))
    if len(last20)>20: last20.pop(0)
    types[ftype]=types.get(ftype,0)+1
    seqs.append(seq)
    off+=total
print("frames",n,"end offset",off,"(size-end)",size-off)
print("first frames (off,seq,type,plen):",first20)
print("last frames:",last20)
print("type counts",types)
print("seq min",min(seqs),"max",max(seqs),"distinct",len(set(seqs)))
print("discontinuities (off,prev,next):",discon[:20],"total",len(discon))
# find where seq wraps down
wraps=[(i,seqs[i-1],seqs[i]) for i in range(1,len(seqs)) if seqs[i] <= seqs[i-1]]
print("wrap points:",wraps[:20],"total",len(wraps))
