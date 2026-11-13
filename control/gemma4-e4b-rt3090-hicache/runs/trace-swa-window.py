#!/usr/bin/env python3
"""Reconstruct expected SWA membership from a captured request identity.

The capture manifest does not expose device req_to_token rows, physical cache slots,
allocator full->SWA mapping, or ForwardMetadata window indices. This script records
the source-derived window contract without claiming these runtime values were seen.
"""
import json,sys,hashlib
from pathlib import Path
root=Path(sys.argv[1]);forward=sys.argv[2];mode=sys.argv[3]
m=json.loads((root/mode/f'forward.{forward}.manifest').read_text());n=len(m['input_ids']);prefix_len=min(n-1,511);start=n-1-prefix_len
result={'forward_id':forward,'rid':m['rid'],'model_identity':m['model_identity'],'input_ids_sha256':hashlib.sha256(json.dumps(m['input_ids'],separators=(',',':')).encode()).hexdigest(),'n':n,'text_positions_first_last':[m['positions'][0],m['positions'][-1]],'HF_window_including_current_query':512,'SGLang_sliding_window_argument':511,'last_query_text_position':n,'expected_prior_cache_token_count':prefix_len,'expected_prior_cache_text_positions':[start+1,n-1] if prefix_len else [],'expected_prior_cache_prompt_offsets_zero_based':[start,n-2] if prefix_len else [],'actual_req_to_token_slots_captured':False,'actual_full_to_swa_mapping_captured':False,'actual_kernel_kv_indices_captured':False,'runtime_proof':'not present in capture manifests','source_basis':'Gemma4 source converts HF inclusive window to 511 exclusive distance; update_sliding_window_buffer prefix lens=min(seq_len,511), start=seq_len-lens; extend kernel handles current query separately.'}
(root/f'window-contract-{mode}-n{n}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
