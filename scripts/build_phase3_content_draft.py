#!/usr/bin/env python3
"""Deterministically package frozen external semantic authoring for Phase 3C.

This module never creates learner prose.  The overlay is the sole semantic
source; this builder only joins reviewed identities and packages artifacts.
"""
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'data/phase3/content-150-input.json'; OVERLAY=ROOT/'data/phase3/learner-content-150-authored-overlay.json'; OUT=ROOT/'data/phase3/learner-content-150-draft.json'; REVIEW=ROOT/'data/phase3/learner-content-150-review.jsonl'
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def build():
 source=json.loads(INPUT.read_text()); overlay=json.loads(OVERLAY.read_text()); authored={x['key']:x for x in overlay['items']}
 if len(authored)!=150 or len(source['items'])!=150 or set(authored)!={x['stable_lexeme_key'] for x in source['items']}:raise SystemExit('input/overlay identities must match exactly')
 items=[]
 for row in source['items']:
  semantic=authored[row['stable_lexeme_key']]
  if semantic['sense_id']!=row['sense_id']:raise SystemExit(f'sense mismatch: {row["stable_lexeme_key"]}')
  items.append({'stable_lexeme_key':row['stable_lexeme_key'],'lemma':row['lemma'],'pos':row['pos'],'cefr':row['cefr'],'entry_id':row['entry_id'],'sense_id':row['sense_id'],'definition_fr':row['definition_fr'],'content_authoring_risk_tier':row['content_authoring_risk_tier'],'translation_binding_risk_tier':row['translation_binding_risk_tier'],'gloss_zh_short':semantic['gloss_zh_short'],'usage_note_zh':semantic['usage_note_zh'],'example_fr':semantic['example_fr'],'example_zh':semantic['example_zh'],'example_source_type':'ai_generated','gloss_source_strategy':'ai_gap_fill','used_candidate_refs':[],'rejected_candidates':[],'content_status':'ai_draft','provenance':{'authoring_surface':overlay['authoring_provenance']['authoring_surface'],'actual_model':overlay['authoring_provenance']['actual_model'],'authoring_status':overlay['authoring_provenance']['status'],'authoring_policy':overlay['authoring_provenance']['policy'],'input_facts_hash':row['parent_input_hash'],'packaging_builder':'phase3c-overlay-packager-v1'}})
 body={'schema_version':1,'scope':'Phase 3C externally semantic-authored learner prose packaged deterministically; content remains ai_draft pending external content review.','input_artifact_hash':source['artifact_hash'],'overlay_source_commit':overlay['source_commit'],'items':items};body['artifact_hash']=digest(body);return body
def write():
 body=build();OUT.write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n');lines=[]
 for x in body['items']:
  lines.append(canonical({'key':x['stable_lexeme_key'],'lemma':x['lemma'],'pos':x['pos'],'cefr':x['cefr'],'content_authoring_risk':x['content_authoring_risk_tier'],'translation_binding_risk':x['translation_binding_risk_tier'],'entry_id':x['entry_id'],'sense_id':x['sense_id'],'definition_fr':x['definition_fr'],'gloss_zh_short':x['gloss_zh_short'],'usage_note_zh':x['usage_note_zh'],'example_fr':x['example_fr'],'example_zh':x['example_zh'],'gloss_source_strategy':x['gloss_source_strategy'],'example_source_type':x['example_source_type']})+'\n')
 REVIEW.write_text(''.join(lines));return body
if __name__=='__main__':print(json.dumps({'items':len(write()['items'])}))
