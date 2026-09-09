#!/usr/bin/env python3
"""Standalone validation for the clean production Phase 3 semantic source."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SOURCE=ROOT/'data/phase3/learner-content-499-authored.json'
EXPECTED={'combien|ADV':'__ws_1_combien__adv__1','langue|NOM':'__ws_4_langue__nom__1','fait|NOM':'__ws_3_fait__nom__1','histoire|NOM':'__ws_8_histoire__nom__1','classique|ADJ':'__ws_3_classique__adj__1','appeler|VER':'__ws_22_appeler__verb__1','impression|NOM':'__ws_7_impression__nom__1','sang|NOM':'__ws_1_sang__nom__1','peau|NOM':'__ws_1_peau__nom__1','émission|NOM':'__ws_2_émission__nom__1','évoquer|VER':'__ws_4_évoquer__verb__1','animer|VER':'__ws_2_animer__verb__1','illustrer|VER':'__ws_3_illustrer__verb__1','engager|VER':'__ws_6_engager__verb__1'}
def main():
 rows=json.loads(SOURCE.read_text())['items'];by={x['stable_lexeme_key']:x for x in rows};needed={'stable_lexeme_key','runtime_lexeme_id','entry_id','sense_id','entry_rank','sense_number','gloss_zh_short','example_fr','example_zh','content_status','cohort'}
 if len(rows)!=499 or len(by)!=499 or len({x['runtime_lexeme_id'] for x in rows})!=499:raise SystemExit('invalid Phase 3 identities')
 for x in rows:
  if x['stable_lexeme_key'] in {'cesse|NOM','travers|NOM'} or not needed<=set(x) or any(not x[field] for field in needed) or x['content_status']!='external_semantic_authored' or x['cohort']!='phase3' or any(v in (x['gloss_zh_short']+x['example_zh']) for v in ('的的','地地')):raise SystemExit('invalid Phase 3 source record')
 for key,sense in EXPECTED.items():
  if by.get(key,{}).get('sense_id')!=sense:raise SystemExit(f'v2 regression: {key}')
 print(json.dumps({'ok':True,'phase3':499,'v2':14}))
if __name__=='__main__':main()
