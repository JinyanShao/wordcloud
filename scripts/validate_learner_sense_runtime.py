#!/usr/bin/env python3
from __future__ import annotations
import json
from build_learner_sense_runtime import DRAFT,OUT,build,serialize
def main():
 payload=build(); actual=OUT.read_text()
 if actual!=serialize(payload): raise SystemExit('runtime learner projection is stale')
 rows=payload['records']
 if len(rows)!=99 or any(x['content_status']!='reviewed' for x in rows): raise SystemExit('runtime must contain 99 reviewed records')
 if any(x['stable_lexeme_key']=='travers|NOM' for x in rows): raise SystemExit('blocked travers leaked into runtime')
 draft=json.loads(DRAFT.read_text()); reviewed={(x['entry_id'],x['sense_id']) for x in draft['items'] if x['content_status']=='reviewed'}
 if {(x['entry_id'],x['sense_id']) for x in rows}!=reviewed: raise SystemExit('runtime does not exactly match reviewed draft identities')
 if any(not x.get('entry_rank') or not x.get('sense_number') for x in rows): raise SystemExit('runtime binding metadata missing')
 print(json.dumps({'ok':True,'records':99,'blocked_leaks':0}))
if __name__=='__main__': main()
