#!/usr/bin/env python3
"""Structural checks only for frozen remaining Phase 3 authoring inputs."""
from __future__ import annotations
import json
from collections import Counter
import build_phase3_remaining_content_inputs as b
FORBIDDEN={'gloss_zh_short','usage_note_zh','example_fr','example_zh','sourced_examples','selected_sense_chinese_candidates'}
def main():
 actual=json.loads(b.OUT.read_text());manifest=json.loads((b.PACKETS/'manifest.json').read_text());expected=b.build();expected_manifest,expected_packets=b.build_packets(expected)
 if actual!=expected or manifest!=expected_manifest:raise SystemExit('remaining input or packets are not deterministic')
 materialized=json.loads(b.MATERIALIZED.read_text());existing=json.loads(b.EXISTING.read_text());selected=[x for x in materialized['items'] if 'entry_id' in x];blocked=[x for x in materialized['items'] if x.get('review_status')=='blocked'];rows=actual['items']
 if len(selected)!=499 or len(blocked)!=1 or blocked[0]['stable_lexeme_key']!='cesse|NOM':raise SystemExit('materialized selection invalid')
 if len(existing['items'])!=150 or len(rows)!=349:raise SystemExit('bad remaining total')
 old={x['stable_lexeme_key'] for x in existing['items']};new={x['stable_lexeme_key'] for x in rows};all_keys={x['stable_lexeme_key'] for x in selected}
 if old&new or old|new!=all_keys or 'cesse|NOM' in new or len(new)!=349:raise SystemExit('partition invalid')
 identity={(x['stable_lexeme_key'],x['entry_id'],x['sense_id']) for x in selected}
 if any((x['stable_lexeme_key'],x['entry_id'],x['sense_id']) not in identity or FORBIDDEN&set(x) for x in rows):raise SystemExit('identity or prose boundary invalid')
 combined=[]
 for entry in manifest['packets']:
  raw=(b.PACKETS/entry['filename']).read_bytes()
  if raw!=expected_packets[entry['filename']] or b.sha(raw)!=entry['sha256']:raise SystemExit('packet sha mismatch')
  packet=[json.loads(line) for line in raw.splitlines()];combined.extend(packet)
 if len(combined)!=349 or [x['key'] for x in combined]!=[x['stable_lexeme_key'] for x in rows]:raise SystemExit('packet union mismatch')
 print(json.dumps({'ok':True,'remaining':349,'packets':len(manifest['packets']),'content_risk':Counter(x['content_authoring_risk_tier'] for x in rows),'translation_risk':Counter(x['translation_binding_risk_tier'] for x in rows)}))
if __name__=='__main__':main()
