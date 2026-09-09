#!/usr/bin/env python3
"""Prepare all remaining externally reviewed Phase 3 sense records for authoring."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MATERIALIZED=ROOT/'data/phase3/learner-sense-500-selection-materialized.json'; EXISTING=ROOT/'data/phase3/content-150-input.json'; OUT=ROOT/'data/phase3/content-349-input.json'; PACKETS=ROOT/'data/phase3/content-authoring-349'
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(value):return hashlib.sha256(value).hexdigest()
def record(row):return {key:row[key] for key in ('stable_lexeme_key','lemma','pos','cefr','entry_id','sense_id','definition_fr','content_authoring_risk_tier','translation_binding_risk_tier','selection_decision','parent_input_hash')}
def build():
 materialized=json.loads(MATERIALIZED.read_text()); existing=json.loads(EXISTING.read_text()); excluded={x['stable_lexeme_key'] for x in existing['items']}; rows=[record(x) for x in materialized['items'] if 'entry_id' in x and x['stable_lexeme_key'] not in excluded]
 body={'schema_version':1,'scope':'Remaining Phase 3 externally reviewed French sense inputs for semantic authoring only; no learner prose.','frozen_selection_artifact_hash':materialized['artifact_hash'],'excluded_content_150_input_hash':existing['artifact_hash'],'blocked_key':'cesse|NOM','items':rows};body['artifact_hash']=sha(canonical(body).encode());return body
def line(row):return canonical({'key':row['stable_lexeme_key'],'lemma':row['lemma'],'pos':row['pos'],'cefr':row['cefr'],'content_risk':row['content_authoring_risk_tier'],'translation_risk':row['translation_binding_risk_tier'],'entry_id':row['entry_id'],'sense_id':row['sense_id'],'definition_fr':row['definition_fr']})+'\n'
def build_packets(body):
 entries=[];payloads={};all_bytes=b''
 for index,start in enumerate(range(0,len(body['items']),70),1):
  chunk=body['items'][start:start+70]; raw=''.join(line(x) for x in chunk).encode();name=f'part-{index:02}.jsonl';payloads[name]=raw;all_bytes+=raw
  entries.append({'filename':name,'record_count':len(chunk),'first_stable_lexeme_key':chunk[0]['stable_lexeme_key'],'last_stable_lexeme_key':chunk[-1]['stable_lexeme_key'],'sha256':sha(raw)})
 manifest={'schema_version':1,'scope':'Deterministic compact packets for remaining Phase 3 external semantic authoring; no learner prose.','total':len(body['items']),'frozen_selection_source_hash':body['frozen_selection_artifact_hash'],'excluded_150_input_hash':body['excluded_content_150_input_hash'],'blocked_key':'cesse|NOM','packets':entries,'union_sha256':sha(all_bytes)};manifest['artifact_hash']=sha(canonical(manifest).encode());return manifest,payloads
def write():
 body=build();manifest,payloads=build_packets(body);OUT.write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n');PACKETS.mkdir(parents=True,exist_ok=True)
 for name,raw in payloads.items():(PACKETS/name).write_bytes(raw)
 (PACKETS/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');return body,manifest
if __name__=='__main__':
 body,manifest=write();print(json.dumps({'remaining':len(body['items']),'packets':[x['record_count'] for x in manifest['packets']]}))
