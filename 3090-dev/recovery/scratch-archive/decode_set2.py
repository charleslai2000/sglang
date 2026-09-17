import struct,os
p="/data/l3/fleet-forensics-v2-20260916/hicache.meta_-data-models-qwen35-9b-w4a16_0_1.wal.7"
fd=os.open(p,os.O_RDONLY)
def frame(off):
    r=os.pread(fd,26,off)
    m,v,ft,fl,res,plen,seq=struct.unpack_from("<IHBBHIQ",r,0)
    return ft,seq,os.pread(fd,plen,off+26),plen
for off in (28,123012,492072,109775800):
    ft,seq,pl,plen=frame(off)
    o=0; epoch=pl[o:o+16]; o+=16
    batch_id=struct.unpack_from("<Q",pl,o)[0]; o+=8
    member_index=struct.unpack_from("<I",pl,o)[0]; o+=4
    member_count=struct.unpack_from("<I",pl,o)[0]; o+=4
    print("frame off=%d type=%d seq=%d plen=%d batch=%d member_index=%d member_count=%d"%(off,ft,seq,plen,batch_id,member_index,member_count))
    n=0; keylens=[]; firstkeys=[]
    try:
        while o<len(pl):
            kl=struct.unpack_from("<H",pl,o)[0]; o+=2
            key=pl[o:o+kl]; o+=kl
            eid,off_,ln,gen,comp=struct.unpack_from("<IIIQB",pl,o); o+=18
            if n<3: firstkeys.append((key.decode('utf-8','replace')[:70],eid,off_,ln,gen,comp))
            keylens.append(kl); n+=1
    except Exception as e:
        print("  parse stop:",e)
    print("  entries=%d keylen min/max=%d/%d remaining=%d"%(n,min(keylens),max(keylens),len(pl)-o))
    for k in firstkeys: print("   ",k)
