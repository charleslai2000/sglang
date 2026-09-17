import struct,os
p="/data/l3/fleet-forensics-v2-20260916/hicache.meta_-data-models-qwen35-9b-w4a16_0_1.wal.7"
fd=os.open(p,os.O_RDONLY)
def frame(off):
    r=os.pread(fd,26,off)
    m,v,ft,fl,res,plen,seq=struct.unpack_from("<IHBBHIQ",r,0)
    return ft,seq,os.pread(fd,plen,off+26),plen
# first SET
ft,seq,payload,plen=frame(28)
print("SET seq=%d plen=%d hex[:64]=%s"%(seq,plen,payload[:64].hex()))
o=0
# try SetPayload: batch_id u64? member_index u32? member_count u32? entries...
for fmtname in ["<QII"]:
    b,mi,mc=struct.unpack_from("<QII",payload,0); print("guess batch_id=%d member_index=%d member_count=%d"%(b,mi,mc))
o=16
# SetEntry: key_len u16, key, extent_id u32, offset u32, length u32, generation u64, component u8
n=0; firstkeys=[]; total_entry=16
while o < len(payload) and n<5:
    kl=struct.unpack_from("<H",payload,o)[0]
    key=payload[o+2:o+2+kl]
    eid,off_,ln,gen,comp=struct.unpack_from("<IIIQB",payload,o+2+kl)
    print("entry%d keylen=%d key=%r eid=%d off=%d len=%d gen=%d comp=%d"%(n,kl,key[:60],eid,off_,ln,gen,comp))
    o+=2+kl+18
    n+=1
print("after 5 entries o=%d remaining=%d"%(o,len(payload)-o))
# count all entries
o=16;cnt=0;tot=0
try:
    while o<len(payload):
        kl=struct.unpack_from("<H",payload,o)[0]; o+=2+kl+18; cnt+=1
    print("total entries parsed=%d"%cnt)
except Exception as e:
    print("parse stop at %d: %s"%(o,e))
# group_commit frame
ft,seq,payload,plen=frame(245996)
print("GROUP_COMMIT seq=%d plen=%d payload=%s"%(seq,plen,payload.hex()))
ft,seq,payload,plen=frame(122974)
print("BATCH_COMMIT seq=%d plen=%d payload=%s"%(seq,plen,payload.hex()))
