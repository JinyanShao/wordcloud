#!/usr/bin/env python3
"""Build compact, deterministic French-sense review packets for Phase 3B."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'data/phase3/learner-sense-500-review-input.json'
RISK=ROOT/'data/phase3/learner-sense-500-risk-decomposed.json'
OUT=ROOT/'data/phase3/sense-review'
GROUPS=(('low','low-sanity.json',40),('medium','medium',40),('high','high',40))

def canonical(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()
def compact_sense(sense): return {key:sense[key] for key in ('entry_id','sense_id','sense_number','entry_rank','definition_fr','leading_labels')}

def build():
    source=json.loads(INPUT.read_text()); risks=json.loads(RISK.read_text())
    if risks['parent_artifact_hash']!=source['artifact_hash']: raise SystemExit('risk artifact parent mismatch')
    risk_by={x['stable_lexeme_key']:x for x in risks['items']}
    if len(risk_by)!=500: raise SystemExit('expected 500 risk records')
    groups={'low':[],'medium':[],'high':[]}
    for item in source['items']:
        risk=risk_by.get(item['stable_lexeme_key'])
        if not risk: raise SystemExit('missing risk record')
        selected=item['proposed_primary_learner_sense']
        selected_source=next((s for s in item['all_source_senses'] if s['entry_id']==selected['entry_id'] and s['sense_id']==selected['sense_id']),None)
        if not selected_source or risk['parent_input_hash']!=item['input_hash']: raise SystemExit('proposal identity mismatch')
        tier=risk['sense_selection_tier']
        record={'stable_lexeme_key':item['stable_lexeme_key'],'runtime_lexeme_id':item['runtime_lexeme_id'],'lemma':item['lemma'],'pos':item['pos'],'cefr':item['cefr'],'frequency_signals':item['frequency_signals'],'current_proposed_sense':compact_sense(selected_source),'all_source_senses':[compact_sense(s) for s in item['all_source_senses']],'sense_selection_flags':risk['sense_selection_flags'],'sense_selection_tier':tier,'current_proposal_rationale':item['selection_reason'],'parent_input_hash':item['input_hash']}
        record['record_hash']=digest(record); groups[tier].append(record)
    return source,risks,groups

def packet(parent_input_hash,parent_risk_hash,tier,records,filename):
    body={'schema_version':1,'scope':'Compact French learner-primary sense review facts only; no adjudication, Chinese candidates, examples, family relations, or learner prose.','parent_input_artifact_hash':parent_input_hash,'parent_risk_artifact_hash':parent_risk_hash,'sense_selection_tier':tier,'items':records}
    body['artifact_hash']=digest(body); return body

def write():
    source,risks,groups=build(); OUT.mkdir(parents=True,exist_ok=True); manifest=[]
    for tier,stem,size in GROUPS:
        rows=groups[tier]
        chunks=[rows] if tier=='low' else [rows[index:index+size] for index in range(0,len(rows),size)]
        for index,chunk in enumerate(chunks,1):
            filename=stem if tier=='low' else f'{stem}-{index:02}.json'
            payload=packet(source['artifact_hash'],risks['artifact_hash'],tier,chunk,filename)
            (OUT/filename).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
            manifest.append({'filename':filename,'record_count':len(chunk),'canonical_hash':payload['artifact_hash'],'first_stable_lexeme_key':chunk[0]['stable_lexeme_key'],'last_stable_lexeme_key':chunk[-1]['stable_lexeme_key']})
    body={'schema_version':1,'scope':'Manifest for deterministic Phase 3 French sense-review packets; packet content is compact source-sense context only.','parent_phase3a_artifact_hash':source['artifact_hash'],'parent_phase3b_artifact_hash':risks['artifact_hash'],'total_records':sum(len(x) for x in groups.values()),'tier_counts':{key:len(value) for key,value in groups.items()},'packets':manifest}
    body['artifact_hash']=digest(body)
    (OUT/'manifest.json').write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n')
    return body
if __name__=='__main__':
    result=write();print(json.dumps({'total':result['total_records'],'tiers':result['tier_counts'],'packets':len(result['packets'])}))
