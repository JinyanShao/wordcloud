#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SOURCE=ROOT/'data/learner-sense-content-reviewed.json'
def main():
 rows=json.loads(SOURCE.read_text())['items']
 if len(rows)!=100 or sum(x['content_status']=='reviewed' for x in rows)!=99: raise SystemExit('expected 99 reviewed records')
 blocked=[x for x in rows if x['content_status']=='blocked']
 if len(blocked)!=1 or blocked[0]['stable_lexeme_key']!='travers|NOM': raise SystemExit('invalid blocked record')
 for x in rows:
  if x['content_status']=='reviewed':
   if not x['entry_id'] or not x['sense_id'] or not x.get('entry_rank') or not x.get('sense_number') or x.get('review_provenance',{}).get('review_status')!='external_semantic_reviewed': raise SystemExit('invalid reviewed identity/provenance')
   if x['gloss_source_strategy'].startswith('sourced_') and not x.get('source_provenance'): raise SystemExit('sourced gloss lacks self-contained provenance')
 print(json.dumps({'ok':True,'reviewed':99,'blocked':1}))
if __name__=='__main__': main()
