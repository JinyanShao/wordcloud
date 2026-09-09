#!/usr/bin/env python3
from __future__ import annotations
import json
from build_learner_content_100_reviewed_selection import INPUT,OUT,OVERRIDES,BLOCKED,build
def main():
 a=json.loads(OUT.read_text()); b=build()
 if a!=b: raise SystemExit('reviewed selection is not deterministic')
 if len(a['items'])!=100 or len({x['stable_lexeme_key'] for x in a['items']})!=100: raise SystemExit('must retain 100 distinct lexemes')
 if sum(x['selection_status']=='reviewed' for x in a['items'])!=99 or sum(x['selection_status']=='blocked' for x in a['items'])!=1: raise SystemExit('must contain 99 reviewed and 1 blocked')
 by={x['stable_lexeme_key']:x for x in a['items']}
 if by[BLOCKED]['selection_status']!='blocked' or by[BLOCKED]['primary_learner_sense'] is not None: raise SystemExit('travers must be blocked without a primary sense')
 for key,(entry,sense) in OVERRIDES.items():
  if by[key]['primary_learner_sense']!={'entry_id':entry,'sense_id':sense}: raise SystemExit(f'override mismatch {key}')
 print(json.dumps({'ok':True,'reviewed':99,'blocked':1,'overrides':18}))
if __name__=='__main__': main()
