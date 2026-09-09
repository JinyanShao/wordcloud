#!/usr/bin/env python3
"""Create a line-oriented reading view of frozen Phase 3 sense-review packets."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/'data/phase3/sense-review'
MANIFEST=DIR/'manifest.json'; JSONL=DIR/'all-500-review.jsonl'; INDEX=DIR/'all-500-review-index.json'

def canonical(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha256_bytes(value): return hashlib.sha256(value).hexdigest()
def compact(row):
    proposed=row['current_proposed_sense']
    return {'key':row['stable_lexeme_key'],'lemma':row['lemma'],'pos':row['pos'],'cefr':row['cefr'],'tier':row['sense_selection_tier'],'proposed':{'entry_id':proposed['entry_id'],'sense_id':proposed['sense_id'],'definition':proposed['definition_fr']},'senses':[{'entry_id':sense['entry_id'],'sense_id':sense['sense_id'],'definition':sense['definition_fr'],'labels':sense['leading_labels']} for sense in row['all_source_senses']],'flags':row['sense_selection_flags']}

def build():
    manifest=json.loads(MANIFEST.read_text()); rows=[]; ranges={}; line=1
    for packet_ref in manifest['packets']:
        packet=json.loads((DIR/packet_ref['filename']).read_text())
        tier=packet['sense_selection_tier']; start=line
        for item in packet['items']:
            record=compact(item)
            if record['tier']!=tier: raise SystemExit('packet tier mismatch')
            rows.append(record); line+=1
        end=line-1
        if tier not in ranges: ranges[tier]={'start_line':start,'end_line':end}
        else: ranges[tier]['end_line']=end
    lines=''.join(canonical(row)+'\n' for row in rows).encode('utf-8')
    index={'schema_version':1,'scope':'Line index for compact French sense-review reading only; each JSONL line is one unchanged frozen proposal.','total':len(rows),'line_to_stable_key':{str(index+1):row['key'] for index,row in enumerate(rows)},'low_range':ranges.get('low'),'medium_range':ranges.get('medium'),'high_range':ranges.get('high'),'source_manifest_hash':manifest['artifact_hash'],'jsonl_sha256':sha256_bytes(lines)}
    index['artifact_hash']=hashlib.sha256(canonical(index).encode()).hexdigest()
    return lines,index

def write():
    lines,index=build(); JSONL.write_bytes(lines); INDEX.write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n'); return index
if __name__=='__main__': print(json.dumps({'lines':write()['total']}))
