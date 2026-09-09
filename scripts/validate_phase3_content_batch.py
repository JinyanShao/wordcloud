#!/usr/bin/env python3
"""Structural checks for frozen reviewed selections and the fixed 150 batch."""
from __future__ import annotations
import json
import build_phase3_content_batch as b
def main():
    materialized=json.loads(b.MATERIALIZED.read_text()); batch=json.loads(b.BATCH.read_text()); rebuilt_m=b.materialize(); rebuilt_b=b.choose(rebuilt_m)
    if materialized!=rebuilt_m or batch!=rebuilt_b: raise SystemExit('selection materialization or batch is not deterministic')
    items=materialized['items']; selected=[x for x in items if 'entry_id' in x]; blocked=[x for x in items if x.get('review_status')=='blocked']
    if len(items)!=500 or len(selected)!=499 or len(blocked)!=1 or blocked[0]['stable_lexeme_key']!='cesse|NOM':raise SystemExit('invalid reviewed selection totals')
    if sum(x['selection_decision']=='reviewed_override' for x in selected)!=115:raise SystemExit('invalid override count')
    if len(batch['items'])!=150 or any(x['stable_lexeme_key']=='cesse|NOM' for x in batch['items']):raise SystemExit('invalid batch')
    counts={tier:sum(x['content_authoring_risk_tier']==tier for x in batch['items']) for tier in b.QUOTAS}
    if counts!=b.QUOTAS:raise SystemExit(f'invalid batch quotas: {counts}')
    allowed={(x['stable_lexeme_key'],x['entry_id'],x['sense_id']) for x in selected}
    if any((x['stable_lexeme_key'],x['entry_id'],x['sense_id']) not in allowed for x in batch['items']):raise SystemExit('batch reselection detected')
    print(json.dumps({'ok':True,'selected':499,'blocked':1,'batch':150,'content_risk':counts}))
if __name__=='__main__':main()
