#!/usr/bin/env python3
"""Validate Phase 3 compact packets structurally; no semantic adjudication."""
from __future__ import annotations
import json
import build_phase3_sense_review_packets as b

FORBIDDEN=('sourced_examples','selected_sense_chinese_candidates','translation_','family','content_authoring','relevant_sourced')

def main():
    manifest=json.loads((b.OUT/'manifest.json').read_text())
    source,risks,groups=b.build()
    expected_entries=[]; expected_packets={}
    for tier,stem,size in b.GROUPS:
        rows=groups[tier]; chunks=[rows] if tier=='low' else [rows[index:index+size] for index in range(0,len(rows),size)]
        for index,chunk in enumerate(chunks,1):
            filename=stem if tier=='low' else f'{stem}-{index:02}.json'; payload=b.packet(source['artifact_hash'],risks['artifact_hash'],tier,chunk,filename)
            expected_packets[filename]=payload
            expected_entries.append({'filename':filename,'record_count':len(chunk),'canonical_hash':payload['artifact_hash'],'first_stable_lexeme_key':chunk[0]['stable_lexeme_key'],'last_stable_lexeme_key':chunk[-1]['stable_lexeme_key']})
    expected={'schema_version':1,'scope':'Manifest for deterministic Phase 3 French sense-review packets; packet content is compact source-sense context only.','parent_phase3a_artifact_hash':source['artifact_hash'],'parent_phase3b_artifact_hash':risks['artifact_hash'],'total_records':500,'tier_counts':{key:len(value) for key,value in groups.items()},'packets':expected_entries}
    expected['artifact_hash']=b.digest(expected)
    if manifest!=expected: raise SystemExit('manifest is not deterministic')
    if manifest['parent_phase3a_artifact_hash']!=source['artifact_hash'] or manifest['parent_phase3b_artifact_hash']!=risks['artifact_hash']: raise SystemExit('parent hash mismatch')
    source_by={x['stable_lexeme_key']:x for x in source['items']}; risk_by={x['stable_lexeme_key']:x for x in risks['items']}; seen=[]; counts={'low':0,'medium':0,'high':0}
    for entry in manifest['packets']:
        packet=json.loads((b.OUT/entry['filename']).read_text())
        if packet!=expected_packets[entry['filename']]: raise SystemExit('packet is not deterministic')
        if packet['artifact_hash']!=entry['canonical_hash'] or len(packet['items'])!=entry['record_count']: raise SystemExit('packet hash or count mismatch')
        rows=packet['items']; tier=packet['sense_selection_tier']; counts[tier]+=len(rows); seen.extend(x['stable_lexeme_key'] for x in rows)
        if rows[0]['stable_lexeme_key']!=entry['first_stable_lexeme_key'] or rows[-1]['stable_lexeme_key']!=entry['last_stable_lexeme_key']: raise SystemExit('manifest boundary mismatch')
        for row in rows:
            if any(any(key.startswith(prefix) for prefix in FORBIDDEN) for key in row): raise SystemExit('compact packet has forbidden field')
            parent=source_by.get(row['stable_lexeme_key']); risk=risk_by.get(row['stable_lexeme_key'])
            if not parent or not risk or row['parent_input_hash']!=parent['input_hash'] or row['sense_selection_tier']!=risk['sense_selection_tier']: raise SystemExit('parent linkage mismatch')
            selected=parent['proposed_primary_learner_sense']; current=row['current_proposed_sense']
            if current['entry_id']!=selected['entry_id'] or current['sense_id']!=selected['sense_id']: raise SystemExit('proposal changed')
            compact=[b.compact_sense(s) for s in parent['all_source_senses']]
            if row['all_source_senses']!=compact or row['current_proposed_sense'] not in compact: raise SystemExit('sense facts changed')
    if len(seen)!=500 or len(set(seen))!=500 or set(seen)!=set(source_by): raise SystemExit('packet union mismatch')
    if counts!={'low':34,'medium':318,'high':148}: raise SystemExit(f'bad tier counts: {counts}')
    print(json.dumps({'ok':True,'records':500,'packets':len(manifest['packets']),'tier_counts':counts}))
if __name__=='__main__': main()
