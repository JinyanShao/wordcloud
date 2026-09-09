#!/usr/bin/env python3
from __future__ import annotations
import json
import build_phase3_final_content as b
def main():
 selection=json.loads(b.MATERIALIZED.read_text());content=json.loads(b.OUT.read_text());expected_selection,expected_content=b.authored()
 if selection!=expected_selection or content!=expected_content:raise SystemExit('final Phase 3 artifacts are stale')
 selected=[x for x in selection['items'] if 'entry_id'in x];blocked=[x for x in selection['items'] if x.get('review_status')=='blocked']
 if len(selected)!=499 or len(blocked)!=1 or blocked[0]['stable_lexeme_key']!='cesse|NOM' or len(content['items'])!=499:raise SystemExit('final Phase 3 counts invalid')
 if sum(x['selection_decision']=='v2_correction' for x in selected)!=14:raise SystemExit('v2 correction count invalid')
 if len({x['stable_lexeme_key'] for x in content['items']})!=499 or any(x['content_status']!='external_semantic_authored' for x in content['items']):raise SystemExit('final authored content invalid')
 print(json.dumps({'ok':True,'selected':499,'blocked':1,'v2':14,'authored':499}))
if __name__=='__main__':main()
