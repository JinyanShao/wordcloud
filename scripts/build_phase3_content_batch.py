#!/usr/bin/env python3
"""Materialize external Phase 3 sense decisions and select a fixed 150 batch."""
from __future__ import annotations
import hashlib,json
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'data/phase3/learner-sense-500-review-input.json'; RISK=ROOT/'data/phase3/learner-sense-500-risk-decomposed.json'; REVIEW=ROOT/'data/phase3/learner-sense-500-selection-reviewed.json'
MATERIALIZED=ROOT/'data/phase3/learner-sense-500-selection-materialized.json'; BATCH=ROOT/'data/phase3/content-150-input.json'
QUOTAS={'low':23,'medium':50,'high':77}
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def materialize():
    source=json.loads(INPUT.read_text()); risk={x['stable_lexeme_key']:x for x in json.loads(RISK.read_text())['items']}; review=json.loads(REVIEW.read_text()); overrides=review['overrides']; blocked=review['blocked']
    items=[]
    for row in source['items']:
        key=row['stable_lexeme_key']; selected=row['proposed_primary_learner_sense']
        if key in blocked:
            items.append({'stable_lexeme_key':key,'lemma':row['lemma'],'pos':row['pos'],'cefr':row['cefr'],'review_status':'blocked','block_reason':blocked[key]['reason_code'],'parent_input_hash':row['input_hash']});continue
        chosen_id=overrides.get(key,selected['sense_id']); sense=next((s for s in row['all_source_senses'] if s['sense_id']==chosen_id),None)
        if not sense:raise SystemExit(f'override not found for {key}')
        items.append({'stable_lexeme_key':key,'runtime_lexeme_id':row['runtime_lexeme_id'],'lemma':row['lemma'],'pos':row['pos'],'cefr':row['cefr'],'frequency_signals':row['frequency_signals'],'entry_id':sense['entry_id'],'sense_id':sense['sense_id'],'sense_number':sense['sense_number'],'entry_rank':sense['entry_rank'],'definition_fr':sense['definition_fr'],'content_authoring_risk_tier':risk[key]['content_authoring_tier'],'translation_binding_risk_tier':risk[key]['translation_tier'],'selection_decision':'reviewed_override' if key in overrides else 'accepted_current_proposal','parent_input_hash':row['input_hash'],'selected_sense_chinese_candidates':[c for c in row['selected_sense_chinese_candidates'] if c['mapped_sense_id']==sense['sense_id'] or c['candidate_class']!='sense_mapped_candidate'],'sourced_examples':sense['sourced_examples']})
    body={'schema_version':1,'scope':'Deterministic materialization of authoritative external French learner-sense review; no new sense selection.','source_input_hash':source['artifact_hash'],'selection_review_hash':review['artifact_hash'],'items':items};body['artifact_hash']=digest(body);return body
def choose(materialized):
    groups=defaultdict(list)
    for row in materialized['items']:
        if row['review_status'] if 'review_status' in row else False: continue
        groups[row['content_authoring_risk_tier']].append(row)
    chosen=[]
    for tier,quota in QUOTAS.items():
        # Frequency-led deterministic round robin through POS/CEFR strata.
        strata=defaultdict(list)
        for row in groups[tier]:strata[(row['pos'],row['cefr'])].append(row)
        for rows in strata.values():rows.sort(key=lambda x:(-(x['frequency_signals'].get('flelex_frequency') or 0),-(x['frequency_signals'].get('lexique_frequency') or 0),x['stable_lexeme_key']))
        order=sorted(strata); picked=[]; cursor=0
        while len(picked)<quota:
            key=order[cursor%len(order)]; cursor+=1
            if strata[key]: picked.append(strata[key].pop(0))
            if not any(strata.values()):break
        if len(picked)!=quota:raise SystemExit(f'insufficient {tier}')
        chosen.extend(picked)
    body={'schema_version':1,'scope':'Phase 3C production-schema learner-content input facts only; selected senses are authoritative external review and require no reselection.','materialized_selection_hash':materialized['artifact_hash'],'risk_quotas':QUOTAS,'items':chosen};body['artifact_hash']=digest(body);return body
def write():
    m=materialize(); MATERIALIZED.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n'); b=choose(m);BATCH.write_text(json.dumps(b,ensure_ascii=False,indent=2)+'\n');return m,b
if __name__=='__main__':
 m,b=write();print(json.dumps({'materialized':len(m['items']),'selected':sum('entry_id'in x for x in m['items']),'batch':len(b['items'])}))
