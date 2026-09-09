#!/usr/bin/env python3
"""Structural validation only; semantic authoring remains external evidence."""
from __future__ import annotations
import json
import build_phase3_content_draft as b
WATCH={'personne|NOM','pouvoir|NOM','savoir|VER','prendre|VER','mettre|VER','remettre|VER','élever|VER','vieux|ADJ','sûr|ADJ','maison|NOM','temps|NOM','travailler|VER','père|NOM','mère|NOM','pied|NOM','euro|NOM','dépendre|VER','patron|NOM','or|NOM'}
def main():
 draft=json.loads(b.OUT.read_text());source=json.loads(b.INPUT.read_text());overlay=json.loads(b.OVERLAY.read_text());rebuilt=b.build(); rows=draft['items'];src={x['stable_lexeme_key']:x for x in source['items']}; authored={x['key']:x for x in overlay['items']}
 if draft!=rebuilt or len(rows)!=150 or set(src)!=set(authored)!={x['stable_lexeme_key'] for x in rows}:raise SystemExit('identity or deterministic rebuild mismatch')
 counts={tier:sum(x['content_authoring_risk_tier']==tier for x in rows) for tier in ('low','medium','high')}
 if counts!={'low':23,'medium':50,'high':77}:raise SystemExit(f'bad risk quotas: {counts}')
 for x in rows:
  parent=src[x['stable_lexeme_key']];semantic=authored[x['stable_lexeme_key']]
  if x['stable_lexeme_key']=='cesse|NOM' or (x['entry_id'],x['sense_id'])!=(parent['entry_id'],parent['sense_id']) or x['sense_id']!=semantic['sense_id']:raise SystemExit('French sense reselection')
  if not x['gloss_zh_short'] or not x['example_fr'] or not x['example_zh'] or x['content_status']!='ai_draft':raise SystemExit('missing content')
  if any(bad in x['gloss_zh_short']+x['example_zh'] for bad in ('的的','地地')):raise SystemExit('mechanical Chinese duplication')
  for field in ('gloss_zh_short','usage_note_zh','example_fr','example_zh'):
   if x[field]!=semantic[field]:raise SystemExit(f'overlay prose mismatch: {x["stable_lexeme_key"]}/{field}')
  if x['provenance']['authoring_surface']!='ChatGPT external semantic authoring' or x['provenance']['actual_model']!='GPT-5.6 Sol':raise SystemExit('false authoring provenance')
 review=[json.loads(line) for line in b.REVIEW.read_text().splitlines()]
 if len(review)!=150 or [x['key'] for x in review]!=[x['stable_lexeme_key'] for x in rows]:raise SystemExit('review JSONL mismatch')
 for key in WATCH & set(src):
  if (src[key]['entry_id'],src[key]['sense_id'])!=(next(x for x in rows if x['stable_lexeme_key']==key)['entry_id'],next(x for x in rows if x['stable_lexeme_key']==key)['sense_id']):raise SystemExit('anti-drift binding')
 text=b.Path(b.__file__).read_text()
 if any(token in text for token in ('GLOSS={','SPECIAL={','def article(','def example(','Nous allons {lemma}','Voici {article','Il agit {lemma}')):raise SystemExit('generic prose generator remains')
 print(json.dumps({'ok':True,'items':150,'sense_reselection':0,'semantic_quality':'external_review_required'}))
if __name__=='__main__':main()
