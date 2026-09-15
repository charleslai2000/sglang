# G1 implementation notes (pinned details)

Authority: USER-RULING-20260912-G1 (D1=b / D3=a / D7=a; D2=a / D4=b / D6=a;
NM-EXTENT-RESTART-REBUILD-01 ACCEPTED). Frozen bundle R5-ruled. `implementation_authorized: true`.

These are IMPLEMENTATION-PINNED details where the frozen design was silent. Per the user's
"no further design expansion" instruction, they were NOT turned into new design rounds; they are
recorded here and guarded by unit tests. They are not D1/D3/D7 semantics and do not change them.

## Format constants (extent_metadata.py)

| detail | value | note |
|---|---|---|
| manifest magic | `0x484D3145` ("HM1E") | pinned in contract §3 |
| manifest CRC range | `header[0..12) || payload` | contract §3 |
| frame magic | `0x484D3146` ("HM1F") | chosen (contract pinned only manifest magic) |
| segment-header magic | `0x484D3153` ("HM1S") | chosen |
| frame CRC | offset 22, covers `header[0..22) || payload` | contract §4.2 (D-11) |
| segment-header CRC | covers `header[0..24)` (bytes before the CRC field) | contract §4.1 silent; mirrors manifest/frame convention |
| `GROUP_STATE_COMPLETE` | `1` | contract gives the symbolic name only |
| `OTHER` component | `255` | contract §3.1 |
| `NUM_COMPONENTS` | `13` | all `PoolName` values, order-verified |
| default `wal_max_record_bytes` | 8 MiB | contract §4.2 proposal; constant `DEFAULT_WAL_MAX_RECORD_BYTES` |
| entry field widths | extent_id/offset/length u32, generation u64, component u8 | same as manifest entry record |
| SET entries delimiter | frame `payload_len` (no explicit entry count) | contract §4.2 |
| segment-header trailing bytes | allowed (frames follow the header) | segment form |
| `data_dev`/`data_ino` == 0 | "unknown" (no mismatch); nonzero must match | contract §3 |
| crc32c | table-driven reflected Castagnoli (poly `0x82F63B78`) | project has NO crc32c lib and `zlib.crc32` is NOT crc32c-compatible; check vector `crc32c(b"123456789")==0xE3069283` |

## Allocator API naming

The contract §4.3/§8 pseudo-API `plan(key_lengths, pending_drops) -> (refs, passed, drop_events)` is
implemented as `plan_split(...)` to preserve backward compatibility. `ExtentAllocator.plan` remains
the legacy 2-tuple `(refs, passed)` used by the current backend and the 77-test file. `plan_split`,
`apply_drops`, and `commit_install` are the new path; the legacy `commit` is retained as the gate-off
composition shim. D-I2 backend integration calls `plan_split`.

## Placement fidelity (D-I1a2)

Contract §4.3 requires placement computed "exactly as if `_drop_slot` had been applied (cursor reset
to 0, slot empty)" for `pending_drops` slots. D-I1a initially used live cursors; D-I1a2 corrects this
so a pending-drop destination is placed at offset 0 and is not double-counted in `passed`. The
generation formula is unchanged (unified form).
