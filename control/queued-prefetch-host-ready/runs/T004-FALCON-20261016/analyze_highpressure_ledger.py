#!/usr/bin/env python3
"""Summarize exact-run stage intervals without manufacturing GPU attribution."""
import json, statistics
from pathlib import Path
P=Path(__file__).parent/'highpressure-stage-ledger-20261018.json'
d=json.loads(P.read_text())
for arm in d['runs']:
    print('\n'+arm['mode'],arm['run_id'])
    print('RID label origin queue_s L3_read_event_span_s host_wait_s H2D_wait_s H2D_service_ms postadmit_to_prefillfinish_s decodeplusresponse_s e2e_s new_suffix_tokens')
    for r in arm['requests']:
        if r['label']=='A': continue
        ack=r['h2d_ack_events_matching_node']
        svc=ack[0]['ack_service_ms'] if len(ack)==1 else None
        h2d_wait = f"{(ack[0]['ack_monotonic_ns']-r['admission_monotonic_ns'])/1e9:.3f}" if len(ack)==1 and len(ack[0].get('node_operation_ids', [])) == 1 else 'SHARED_BATCH'
        print(r['rid'],r['label'],r['prefetch_origin'],f"{r['arrival_to_admission_s']:.3f}",f"{r['query_to_host_complete_event_span_s']:.3f}",f"{r['host_ready_to_admission_s']:.3f}",h2d_wait, f"{svc:.2f}" if svc is not None and len(ack[0].get('node_operation_ids', [])) == 1 else 'SHARED_BATCH',f"{r['admission_to_prefill_finished_s']:.3f}",f"{r['prefill_finish_to_request_finish_s']:.3f}",f"{r['e2e_s']:.3f}",r['new_suffix_tokens_not_covered_by_cache'])
    vals=[r['e2e_s'] for r in arm['requests'] if r['label'] in 'BCD']
    print('B/C/D means: E2E %.3f s, E2E min/max %.3f/%.3f s, reports only; no replicated causal inference' % (statistics.mean(vals),min(vals),max(vals)))
