# PRODUCTION TAKEOVER — authority capture + Gate A adjudication (2026-09-17 17:20Z)

Single mainline: RTX 3090 / SGLang M1 production go-live. Terminal = `PRODUCTION GREEN` or
`PRODUCTION BLOCKED — <single blocker>`.

## §0 AUTHORITY (recorded first, per directive)

| item | value |
|---|---|
| repo (sole source authority) | `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt` |
| branch | `3090-24g-opt` |
| HEAD | `7d08fb26f89b7c31ed7a6a36587629bd0c10d229` |
| git status | dirty: `M 3090-dev/deploy/bin/supervise.sh`, `M 3090-dev/tools/prod-service/bin/supervise.sh`, `M python/sglang/srt/utils/hf_transformers/gguf_native.py`, `M .memory/.../ledger.md`; untracked: HANDOFF/EPOCH-RESUME/GGUF-provenance docs, `3090-dev/gates/gguf-sampled-smoke/`, `test/registered/unit/utils/test_gguf_native_tokenizer_ids.py` |
| actual imported `sglang.__file__` | **depends on PYTHONPATH**: with `<tree>/src/python` → `<tree>/src/python/sglang/__init__.py`; **without it → the repo working tree** (`.../sglang-3090-24g-opt/python/sglang/__init__.py`) via the venv editable finder `__editable___sglang_0_5_20_dev22_g9c9e7b7c7_finder.py`. Version `0.5.20.dev22+g9c9e7b7c7`. |
| production Rust `.so` (native writer) | `home/ubuntu/.cache/sglang/rust_extensions/artifacts/l3-native-wal/51ca2e73…b0376/_l3wal.cpython-312-x86_64-linux-gnu.so`, 578264 B, sha256 `f1f0c0d3634f3e11891d6632790fc9301167d2e9168b2e441506684846220750`; loads clean via `load_rust_extension(mode="never", cache_dir=None)` under the real venv |

**The editable-install binding is a live hazard**: the venv maps `sglang` to the *repo working
tree*, so any run that forgets `PYTHONPATH` silently executes uncommitted bytes. This is the
trap the production launcher's fail-closed identity gate exists to prevent.

### DECISIVE AUTHORITY GAP (blocks §4/§5 as-is)

The deployed production tree `/opt/sglang/local-prod-v1.1.2-candidate`
(`PROD_TREE_DEFAULT` in `3090-dev/deploy/conf/service.env`) is **stale and NOT the current
authoritative source**:

| file | repo HEAD / worktree | `/opt` candidate | meaning |
|---|---|---|---|
| `.../extent/extent_file_backend.py` | `a5c99fd1cc32b645` (**3** native-writer refs) | `b284ec2a710d2afb` (**0** refs) | candidate **lacks the GIL-free native L3 writer** |
| `python/sglang/srt/models/qwen3_5_text.py` | `d51d5441064c13cb` (`4501e59f88`) | `c140253b8125df0a` | candidate predates the norm-fold fix |
| `.../utils/hf_transformers/gguf_native.py` | `c5f2e9730c88f589` (HEAD) | `c5f2e9730c88f589` | same (GGUF, out of production scope) |

Source-only delta is exactly those 3 files; everything else matches. The candidate froze from
`/tmp/opencode/v1.1.2-optionC-20260917` per its own `manifest/identity.json`, i.e. from scratch,
not from a committed SHA. **No existing `/opt` tree satisfies §4/§5** (§0: `/opt/local-prod-*` is
historical evidence only). A final candidate must be rebuilt deterministically from a committed
commit.

§4 required changes, status at HEAD: WAL/checkpoint fix **committed**; native L3 writer
(`b26bd39ece`, ancestor of HEAD) **committed**; Option-C relocation (`63f7eff612`) **committed**;
`cache_dir=None` **committed**; final gate harness **committed**; **provider lifecycle fix
(`supervise.sh`) is UNCOMMITTED** in the worktree.

## §2 GATE A ADJUDICATION — H-A (HARNESS), with decisive evidence

Method: the harness's **own read-only oracle** `wal_forensics.py --mode membership` run against
the static aborted store `/data/l3/phase9-gates-final-20260916/gateA-gateA-20260917T165123Z-1500213`
with the run's real `prompt_A.json` / `prompt_B.json` ids (not log-string inference).

### Decisive evidence

1. **Zero durable loss.** `drop_slot_frames = {n: 0, slots_dropped: []}` and
   `slot_state_replay.n_drop_slot_frames = 0` (vs `n_set_frames = 93`). The extent store's WAL
   contains **no `DROP_SLOT` frame at all** (`cursor_source: "WAL frame replay (SET advances,
   DROP_SLOT resets)"`). ⇒ **No page that was ever written to L3 was removed.**
2. **Graded target durable refs exist.** prompt A: `n_present = 52672`, `first_present_index = 0`,
   head present, `n_runs = 2` (`[0,51200)` + `[63488,64960)`), spread across **all 52 slots**
   (slot histogram: slot0 523 target refs, slot1 952, slot2 1093, …).
3. **The drop warnings are a different layer.** `write_back: KV subtree dropped without backup`
   comes from `python/sglang/srt/mem_cache/unified_radix_cache.py:3246` — the **device→host backup
   failure** path (`_drop_subtree_no_host`), i.e. an L1 cache-tier eviction decision. It is not the
   extent store and it removed no L3 index entry (see 1).
4. **The relocation refusal is a real, correctly-refused capacity shortfall.**
   `victim = slot 0`, `live_bytes = 61079552`, `target_live_refs = 523`,
   `holds_live_target_refs = true`, `relocation_headroom_bytes = 49201152`,
   `reclaim_relocatable = false`, `fail_closed_reason = "no destination capacity outside victim
   slot 0: relocation headroom 49201152 B < victim live bytes 61079552 B; the circular reclaim must
   refuse the write (ExtentFileBackend fail-closed)"`. The product **behaved correctly**: Option-C
   needs a destination outside the victim, and the harness geometry left none large enough.
5. **Fillers are never persisted** — filler 0 and filler 1 membership = `n_present = 0`.

### Consequence

The aborted INVALID is a **harness artifact**, not a product defect: the drop predicate is
over-broad (collects *any* `without backup due to host memory pressure` line, while the harness's
own README scopes it to the graded prefix), and the geometry consumed the store such that no
relocation destination remained. The gate **never reached the measured L3 / RECOVERED arms**, so
no storage-restore evidence exists yet; the campaign must be re-run after the harness fix.

### Required harness corrections (owner-preauthorized)

* bind the drop predicate to the **graded target** only; mark filler disposable; a filler drop must
  not INVALIDate the target, but **any target page/ref drop must fail closed**;
* reserve an explicit **relocation destination** (Option-C needs capacity outside the victim); do
  not fill the store ~100 % live and then require relocation to succeed; do not dodge the wrap by
  making the store enormous;
* geometry must trigger circular reclaim with a victim slot holding target live refs and a real
  recycle event;
* pre-assert (before any measured request) the §3 preconditions: Gate A = target in Extent index,
  DEVICE miss, HOST miss, STORAGE-hit candidate, host pool sized; F1 = victim slot id known, victim
  holds target live refs, relocation destination capacity exists, actual recycle event, victim
  generation changed, target relocation count > 0. Missing any ⇒ `INVALID` without burning GPU.

_Orchestrator-authored from primary artifacts; no subagent report was used as authority._
