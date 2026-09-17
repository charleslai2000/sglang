import struct, sys, os
d="/data/l3/fleet-forensics-v2-20260916"
man=os.path.join(d,"hicache.meta_-data-models-qwen35-9b-w4a16_0_1.manifest")
data=open(man,"rb").read()
magic,version,flags,plen=struct.unpack_from("<IHHI",data,0)
print("manifest magic=%08X ver=%d flags=%d payload_len=%d file_len=%d"%(magic,version,flags,plen,len(data)))
o=16
ck,floor,agen,esize,fsize=struct.unpack_from("<QQQQQ",data,o); o+=40
nslots=struct.unpack_from("<I",data,o)[0]; o+=4
dev,ino=struct.unpack_from("<QQ",data,o); o+=16
fuuid=data[o:o+16]; o+=16
nepoch=data[o:o+16]; o+=16
next_slot=struct.unpack_from("<I",data,o)[0]; o+=4
print("checkpoint_lsn=%d wal_floor=%d wal_active_gen=%d extent_size=%d file_size=%d"%(ck,floor,agen,esize,fsize))
print("num_slots=%d data_dev=%d data_ino=%d next_slot=%d"%(nslots,dev,ino,next_slot))
print("file_uuid=%s namespace_epoch=%s"%(fuuid.hex(),nepoch.hex()))
gens=struct.unpack_from("<%dQ"%nslots,data,o); o+=8*nslots
curs=struct.unpack_from("<%dI"%nslots,data,o); o+=4*nslots
sb=struct.unpack_from("<%dQ"%nslots,data,o); o+=8*nslots
ngens=len(set(gens)); print("slot gens: distinct=%d max=%d min=%d"%(ngens,max(gens),min(gens)))
print("slot_bytes sum=%d nonzero_slots=%d"%(sum(sb),sum(1 for x in sb if x)))
rc=struct.unpack_from("<I",data,o)[0]; o+=4
rec=struct.unpack_from("<%dI"%rc,data,o); o+=4*rc
print("recency_count=%d"%rc)
ec=struct.unpack_from("<I",data,o)[0]; o+=4
print("entry_count=%d"%ec)
for _ in range(ec):
    kl=struct.unpack_from("<H",data,o)[0]; o+=2
    key=data[o:o+kl]; o+=kl
    eid,off,ln,gen,comp=struct.unpack_from("<IIIQB",data,o); o+=18
    o+=16+8
gc=struct.unpack_from("<I",data,o)[0]; o+=4
print("group_count=%d"%gc)
print("consumed=%d remaining=%d"%(o,len(data)-o))
