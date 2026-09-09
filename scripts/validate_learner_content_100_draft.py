#!/usr/bin/env python3
"""Structural validator for 100 reviewed selections and AI-draft content only."""
from __future__ import annotations
import json,sqlite3
from pathlib import Path
from validate_learner_content_pilot import attested_forms,tokens
from build_learner_content_100_draft import OUT,SEL,FACTS,build
from build_learner_content_100_reviewed_selection import BLOCKED,OVERRIDES
ROOT=Path(__file__).resolve().parents[1]; DB=ROOT/'data/processed/wordcloud.sqlite'; CAND=ROOT/'data/processed/dbnary-zh-translation-candidates.json'
def main():
 draft=json.loads(OUT.read_text()); selection=json.loads(SEL.read_text()); facts={x['stable_lexeme_key']:x for x in json.loads(FACTS.read_text())['items']}; choices={x['stable_lexeme_key']:x for x in selection['items']}; candidates={x['translation_stable_ref']:x for x in json.loads(CAND.read_text())['items']}
 if draft!=build(): raise SystemExit('draft is not deterministic from reviewed selection and fixed authoring map')
 if len(draft['items'])!=100 or set(x['identity']['stable_lexeme_key'] for x in draft['items'])!=set(facts): raise SystemExit('draft must preserve exactly the frozen 100 keys')
 conn=sqlite3.connect(DB); errors=[]
 try:
  for item in draft['items']:
   ident=item['identity']; key=ident['stable_lexeme_key']; choice=choices[key]; fact=facts[key]
   if key==BLOCKED:
    if item['content_status']!='blocked' or any(item.get(k) for k in ('gloss_zh_short','example_fr','example_zh')): errors.append('blocked travers contains learner content')
    continue
   if choice['selection_status']!='reviewed' or item['selection_status']!='reviewed' or item['content_status']!='reviewed': errors.append(f'status mismatch {key}')
   if item.get('review_provenance')!={'review_status':'external_semantic_reviewed','review_version':'phase2c-100-semantic-review-v1'}: errors.append(f'missing review provenance {key}')
   selected=choice['primary_learner_sense']
   if ident['entry_id']!=selected['entry_id'] or ident['sense_id']!=selected['sense_id']: errors.append(f'sense binding mismatch {key}')
   row=conn.execute('SELECT 1 FROM lexeme_senses WHERE id=? AND entry_id=? AND lexeme_id=?',(ident['sense_id'],ident['entry_id'],ident['runtime_lexeme_id'])).fetchone()
   if not row: errors.append(f'unknown selected sense {key}')
   if not all(item.get(k) for k in ('gloss_zh_short','example_fr','example_zh')): errors.append(f'missing learner text {key}')
   forms=attested_forms(conn,ident['runtime_lexeme_id'],fact['lemma'],fact['pos'])
   if fact['lemma'].casefold() not in item['example_fr'].casefold() and not (tokens(item['example_fr']) & forms): errors.append(f'example lacks lemma or attested form {key}')
   for ref in item.get('used_candidate_refs',[]):
    candidate=candidates.get(ref)
    if not candidate: errors.append(f'unknown candidate {key}')
    elif candidate['learner_language_eligibility']!='default_learner_chinese': errors.append(f'nondefault candidate used {key}')
   if item.get('relation_explanation_zh') is not None: errors.append(f'unreviewed relation explanation {key}')
  for key,(entry,sense) in OVERRIDES.items():
   if choices[key]['primary_learner_sense']!={'entry_id':entry,'sense_id':sense}: errors.append(f'override missing {key}')
 finally: conn.close()
 if errors: raise SystemExit('\n'.join(errors))
 print(json.dumps({'ok':True,'reviewed':99,'blocked':1,'semantic_review':'external semantic review recorded'}))
if __name__=='__main__': main()
