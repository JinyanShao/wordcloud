#!/usr/bin/env python3
"""Materialize v2 reviewed selections and package externally authored Phase 3 content."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'data/phase3/learner-sense-500-review-input.json'; V1=ROOT/'data/phase3/learner-sense-500-selection-reviewed.json'; V2=ROOT/'data/phase3/learner-sense-selection-corrections-v2.json'; FIRST=ROOT/'data/phase3/learner-content-150-authored-overlay.json'; PARTS=[ROOT/f'data/phase3/learner-content-349-authored-part-{i:02}.json' for i in range(1,6)]; CONTENT_V2=ROOT/'data/phase3/learner-content-semantic-corrections-v2.json'; MATERIALIZED=ROOT/'data/phase3/learner-sense-500-selection-materialized.json'; OUT=ROOT/'data/phase3/learner-content-499-authored.json'
def canon(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(canon(x).encode()).hexdigest()
def materialize():
 source=json.loads(SOURCE.read_text());v1=json.loads(V1.read_text());v2=json.loads(V2.read_text());overrides=v1['overrides'];changes={x['key']:x for x in v2['corrections']};items=[]
 if len(changes)!=14:raise SystemExit('expected 14 v2 corrections')
 for row in source['items']:
  key=row['stable_lexeme_key']
  if key in v1['blocked']:
   items.append({'stable_lexeme_key':key,'lemma':row['lemma'],'pos':row['pos'],'cefr':row['cefr'],'review_status':'blocked','block_reason':v1['blocked'][key]['reason_code'],'parent_input_hash':row['input_hash']});continue
  prior=overrides.get(key,row['proposed_primary_learner_sense']['sense_id']);chosen=changes.get(key,{}).get('new_sense_id',prior);sense=next((s for s in row['all_source_senses'] if s['sense_id']==chosen),None)
  if not sense:raise SystemExit(f'unknown selected sense {key}')
  if key in changes and changes[key]['old_sense_id']!=prior:raise SystemExit(f'v2 old sense mismatch {key}')
  items.append({'stable_lexeme_key':key,'runtime_lexeme_id':row['runtime_lexeme_id'],'lemma':row['lemma'],'pos':row['pos'],'cefr':row['cefr'],'entry_id':sense['entry_id'],'sense_id':sense['sense_id'],'entry_rank':sense['entry_rank'],'sense_number':sense['sense_number'],'definition_fr':sense['definition_fr'],'selection_decision':'v2_correction' if key in changes else ('reviewed_override' if key in overrides else 'accepted_current_proposal'),'parent_input_hash':row['input_hash']})
 body={'schema_version':2,'scope':'Final Phase 3 French learner-primary selection: v1 review followed by latest-wins v2 corrections.','v1_selection_hash':v1['artifact_hash'],'v2_corrections_hash':digest(v2),'items':items};body['artifact_hash']=digest(body);return body
def authored():
 selected=materialize(); semantic={}
 for path in [FIRST,*PARTS]:
  data=json.loads(path.read_text())
  for item in data['items']:
   if item['key'] in semantic:raise SystemExit(f'duplicate authored key {item["key"]}')
   semantic[item['key']]=item
 corrections={x['key']:x for x in json.loads(CONTENT_V2.read_text())['items']}
 rows=[]
 for row in selected['items']:
  if 'entry_id' not in row:continue
  authored=corrections.get(row['stable_lexeme_key'],semantic.get(row['stable_lexeme_key']))
  if not authored or authored['sense_id']!=row['sense_id']:raise SystemExit(f'authored sense mismatch {row["stable_lexeme_key"]}')
  rows.append({**{k:row[k] for k in ('stable_lexeme_key','runtime_lexeme_id','lemma','pos','cefr','entry_id','sense_id','entry_rank','sense_number')},**{k:authored[k] for k in ('gloss_zh_short','usage_note_zh','example_fr','example_zh')},'example_source_type':'ai_generated','gloss_source_strategy':'ai_gap_fill','content_status':'external_semantic_authored','cohort':'phase3','provenance':{'authoring_surface':'ChatGPT external semantic authoring','actual_model':'GPT-5.6 Sol','packaging_builder':'phase3-final-v2'}})
 body={'schema_version':1,'scope':'Final externally semantic-authored Phase 3 learner content; not independently reviewed.','final_selection_hash':selected['artifact_hash'],'items':rows};body['artifact_hash']=digest(body);return selected,body
def write():
 selection,content=authored();MATERIALIZED.write_text(json.dumps(selection,ensure_ascii=False,indent=2)+'\n');OUT.write_text(json.dumps(content,ensure_ascii=False,indent=2)+'\n');return selection,content
if __name__=='__main__':
 s,c=write();print(json.dumps({'selected':sum('entry_id'in x for x in s['items']),'authored':len(c['items'])}))
