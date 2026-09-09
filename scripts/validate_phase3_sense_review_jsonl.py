#!/usr/bin/env python3
"""Structural validation for the compact Phase 3 reviewer JSONL."""
from __future__ import annotations
import json
import build_phase3_sense_review_jsonl as b

def main():
    expected_lines,expected_index=b.build(); actual_lines=b.JSONL.read_bytes(); actual_index=json.loads(b.INDEX.read_text())
    if actual_lines!=expected_lines or actual_index!=expected_index: raise SystemExit('JSONL or index is not deterministic')
    rows=[json.loads(line) for line in actual_lines.splitlines()]
    manifest=json.loads(b.MANIFEST.read_text()); packet_rows=[]
    for packet_ref in manifest['packets']:
        packet_rows.extend(json.loads((b.DIR/packet_ref['filename']).read_text())['items'])
    if len(rows)!=500 or len({row['key'] for row in rows})!=500: raise SystemExit('must contain exactly 500 unique lines')
    if [row['key'] for row in rows] != [row['stable_lexeme_key'] for row in packet_rows]: raise SystemExit('JSONL order or packet union changed')
    if actual_index['total']!=500 or actual_index['line_to_stable_key']!={str(index+1):row['key'] for index,row in enumerate(rows)}: raise SystemExit('index mapping mismatch')
    for compact,source in zip(rows,packet_rows):
        if compact['tier']!=source['sense_selection_tier']: raise SystemExit('tier changed')
        proposal=source['current_proposed_sense']
        if compact['proposed']!={'entry_id':proposal['entry_id'],'sense_id':proposal['sense_id'],'definition':proposal['definition_fr']}: raise SystemExit('proposal changed')
        senses=[{'entry_id':s['entry_id'],'sense_id':s['sense_id'],'definition':s['definition_fr'],'labels':s['leading_labels']} for s in source['all_source_senses']]
        if compact['senses']!=senses: raise SystemExit('source senses changed')
    print(json.dumps({'ok':True,'lines':500,'ranges':{'low':actual_index['low_range'],'medium':actual_index['medium_range'],'high':actual_index['high_range']}}))
if __name__=='__main__': main()
