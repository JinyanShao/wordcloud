#!/usr/bin/env python3
"""Validate exact runtime identity for Phase 2C + final Phase 3 cohorts."""
from __future__ import annotations
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];P2=ROOT/'data/learner-sense-content-reviewed.json';P3=ROOT/'data/phase3/learner-content-499-authored.json';RUNTIME=ROOT/'learner-sense-content.js'
EXPECTED={'combien|ADV':'__ws_1_combien__adv__1','langue|NOM':'__ws_4_langue__nom__1','fait|NOM':'__ws_3_fait__nom__1','histoire|NOM':'__ws_8_histoire__nom__1','classique|ADJ':'__ws_3_classique__adj__1','appeler|VER':'__ws_22_appeler__verb__1','impression|NOM':'__ws_7_impression__nom__1','sang|NOM':'__ws_1_sang__nom__1','peau|NOM':'__ws_1_peau__nom__1','émission|NOM':'__ws_2_émission__nom__1','évoquer|VER':'__ws_4_évoquer__verb__1','animer|VER':'__ws_2_animer__verb__1','illustrer|VER':'__ws_3_illustrer__verb__1','engager|VER':'__ws_6_engager__verb__1'}
def main():
 raw=RUNTIME.read_text();match=re.search(r'const LEARNER_SENSE_CONTENT=(.*);\n$',raw,re.S)
 if not match:raise SystemExit('missing runtime payload')
 rows=json.loads(match.group(1))['records'];p2=[x for x in rows if x['cohort']=='phase2c'];p3=[x for x in rows if x['cohort']=='phase3']
 if len(rows)!=598 or len(p2)!=99 or len(p3)!=499:raise SystemExit('runtime cohort counts invalid')
 if len({x['lexeme_id'] for x in rows})!=598 or len({x['stable_lexeme_key'] for x in rows})!=598:raise SystemExit('runtime duplicate identity')
 if set(x['stable_lexeme_key'] for x in p2)&set(x['stable_lexeme_key'] for x in p3):raise SystemExit('cohort overlap')
 if any(x['stable_lexeme_key'] in {'cesse|NOM','travers|NOM'} for x in rows):raise SystemExit('blocked key leaked into runtime')
 authored={x['stable_lexeme_key']:x for x in json.loads(P3.read_text())['items']}
 for x in p3:
  source=authored.get(x['stable_lexeme_key'])
  if not source or any(x[k]!=source[k] for k in ('entry_id','sense_id','entry_rank','sense_number')):raise SystemExit('exact Phase 3 binding mismatch')
 for key,sense in EXPECTED.items():
  if authored[key]['sense_id']!=sense or next(x for x in p3 if x['stable_lexeme_key']==key)['sense_id']!=sense:raise SystemExit(f'v2 regression: {key}')
 print(json.dumps({'ok':True,'runtime':598,'phase2c':99,'phase3':499,'v2':14}))
if __name__=='__main__':main()
