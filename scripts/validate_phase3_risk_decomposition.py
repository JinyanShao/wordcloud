#!/usr/bin/env python3
"""Structural validation and separated Phase 2C calibration for Phase 3B."""
from __future__ import annotations
import json, sqlite3, sys
from collections import Counter
from pathlib import Path
import build_phase3_risk_decomposition as d
import build_phase3_scale_prep as base
import validate_phase3_scale_prep as legacy

ROOT=d.ROOT; CAL=ROOT/'data/phase3/phase2c-risk-axis-calibration.json'; INPUT=Path('/tmp/wordcloud-phase2c-input.json')

def phase2_records():
    candidates=base.candidate_index(); rows=json.loads(base.REVIEWED.read_text())['items']; rows=[x for x in rows if x['content_status']=='reviewed']
    conn=sqlite3.connect(base.DB);conn.row_factory=sqlite3.Row
    try:
        result=[]
        for reviewed in rows:
            item=legacy.reviewed_item(conn,candidates,reviewed)
            item['pos']=reviewed['stable_lexeme_key'].rsplit('|',1)[1]
            item['proposal_policy_flags']=[]
            result.append(item)
        return result
    finally: conn.close()

def calibration():
    if not INPUT.exists(): raise SystemExit(f'missing frozen Phase 2C input: {INPUT}')
    original={x['stable_lexeme_key']:(x['proposed_primary_learner_sense']['entry_id'],x['proposed_primary_learner_sense']['sense_id']) for x in json.loads(INPUT.read_text())['items']}
    reviewed={x['stable_lexeme_key']:(x['entry_id'],x['sense_id']) for x in json.loads(base.REVIEWED.read_text())['items'] if x['content_status']=='reviewed'}
    corrected={key for key,value in reviewed.items() if original[key]!=value}
    rows=[]
    for item in phase2_records():
        sf,st,ordinary=d.sense_axis(item); tf,tt=d.translation_axis(item); cf,ct=d.content_axis(item,st,ordinary)
        rows.append({'stable_lexeme_key':item['stable_lexeme_key'],'sense_selection_tier':st,'content_authoring_tier':ct,'sense_selection_flags':sf,'content_authoring_flags':cf})
    by={x['stable_lexeme_key']:x for x in rows}
    for key in ('antenne|NOM','chef|NOM'):
        if by[key]['sense_selection_tier']!='high': raise SystemExit(f'{key} must be high sense risk')
    if by['devoir|VER']['sense_selection_tier']=='low': raise SystemExit('devoir must not be low sense risk')
    if by['personne|NOM']['content_authoring_tier']!='high': raise SystemExit('personne must remain content-risk high')
    false_negatives=sorted(key for key in corrected if by[key]['sense_selection_tier']=='low')
    if false_negatives: raise SystemExit(f'dangerous low sense false negatives: {false_negatives}')
    content_rows=[x for x in rows if x['stable_lexeme_key'] in d.CONTENT_DRIFT]
    content_low=sorted(x['stable_lexeme_key'] for x in content_rows if x['content_authoring_tier']=='low')
    if content_low: raise SystemExit(f'content drift set unexpectedly low: {content_low}')
    report={'schema_version':1,'scope':'Phase 2C calibration split by sense-selection versus content-authoring risk; neither tier is semantic approval.','sense_selection_corrected_records':len(corrected),'sense_selection_corrected_by_tier':dict(Counter(x['sense_selection_tier'] for x in rows if x['stable_lexeme_key'] in corrected)),'dangerous_low_sense_false_negatives':false_negatives,'content_drift_regression_records':len(content_rows),'content_drift_by_tier':dict(Counter(x['content_authoring_tier'] for x in content_rows)),'content_drift_low_false_negatives':content_low,'records':sorted(rows,key=lambda x:x['stable_lexeme_key'])}
    report['artifact_hash']=d.digest(report); return report

def main():
    payload=json.loads(d.OUT.read_text()); rebuilt=d.build()
    if payload!=rebuilt: raise SystemExit('risk decomposition is not deterministic')
    parent=json.loads(d.PARENT.read_text())
    if payload['parent_artifact_hash']!=parent['artifact_hash'] or len(payload['items'])!=500: raise SystemExit('bad parent or item count')
    parent_by={x['stable_lexeme_key']:x for x in parent['items']}
    joined=[]
    for route in d.ROUTES:
        projection=json.loads((d.OUT.parent/d.ROUTE_FILES[route]).read_text())
        expected=[x for x in payload['items'] if x['review_route']==route]
        if projection.get('parent_artifact_hash')!=payload['artifact_hash'] or projection.get('items')!=expected: raise SystemExit(f'bad route projection: {route}')
        joined.extend(projection['items'])
    order={x['stable_lexeme_key']:index for index,x in enumerate(payload['items'])}
    if sorted(joined,key=lambda x:order[x['stable_lexeme_key']])!=payload['items']: raise SystemExit('route projections do not reconstruct payload')
    forbidden={'no_default_chinese_candidate','multiple_chinese_candidates','candidate_not_sense_mapped','structural_mapping_only','nondefault_language_variant_present','candidate_gloss_domain_mismatch_possible'}
    for record in payload['items']:
        source=parent_by.get(record['stable_lexeme_key'])
        if not source or record['parent_input_hash']!=source['input_hash'] or record['proposed_primary_learner_sense']!={k:source['proposed_primary_learner_sense'][k] for k in ('entry_id','sense_id')}: raise SystemExit('identity or proposal changed')
        if forbidden & set(record['sense_selection_flags']): raise SystemExit('translation signal contaminated sense risk')
        if record['review_route']!={'low':'auto_sense_candidate','medium':'ai_sense_adjudication','high':'human_sense_review'}[record['sense_selection_tier']]: raise SystemExit('bad sense route')
    report=calibration()
    if '--write-calibration' in sys.argv: CAL.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    elif not CAL.exists() or json.loads(CAL.read_text())!=report: raise SystemExit('calibration report drift')
    print(json.dumps({'ok':True,'items':500,'sense':Counter(x['sense_selection_tier'] for x in payload['items']),'translation':Counter(x['translation_tier'] for x in payload['items']),'content':Counter(x['content_authoring_tier'] for x in payload['items'])}))
if __name__=='__main__': main()
