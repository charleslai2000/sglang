import struct,os
p="/data/l3/fleet-forensics-v2-20260916/hicache.meta_-data-models-qwen35-9b-w4a16_0_1.wal.7"
fd=os.open(p,os.O_RDONLY); size=os.path.getsize(p); off=28
out=[]
while off<size and len(out)<6:
    r=os.pread(fd,26,off); m,v,ft,fl,res,plen,seq=struct.unpack_from("<IHBBHIQ",r,0)
    if ft==1:
        pl=os.pread(fd,plen,off+26); o=40
        while o+21<=len(pl):
            kl=struct.unpack_from("<H",pl,o)[0]; o+=2
            if o+kl+21>len(pl): break
            key=pl[o:o+kl]; o+=kl
            e,off_,ln,g,c=struct.unpack_from("<IIIQB",pl,o); o+=21
            out.append((kl,key.decode('utf-8','replace'),ln,c))
    off+=26+plen
for kl,k,ln,c in out: print("keylen=%d len=%d comp=%d key=%r"%(kl,ln,c,k))
