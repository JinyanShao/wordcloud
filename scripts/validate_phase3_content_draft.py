#!/usr/bin/env python3
"""Structural validation only; external review owns semantic quality."""
from __future__ import annotations
import json
import build_phase3_content_draft as b
WATCH={'personne|NOM','pouvoir|NOM','savoir|VER','prendre|VER','mettre|VER','remettre|VER','élever|VER','vieux|ADJ','sûr|ADJ','maison|NOM','temps|NOM','travailler|VER','père|NOM','mère|NOM','pied|NOM','euro|NOM','dépendre|VER','patron|NOM','or|NOM'}
def main():
    draft=json.loads(b.OUT.read_text()); source=json.loads(b.INPUT.read_text()); rebuilt=b.build()
    if draft!=rebuilt:raise SystemExit('draft is not deterministic')
    rows=draft['items'];src={x['stable_lexeme_key']:x for x in source['items']}
    if len(rows)!=150 or len({x['stable_lexeme_key'] for x in rows})!=150:raise SystemExit('invalid draft count')
    counts={tier:sum(x['content_authoring_risk_tier']==tier for x in rows) for tier in ('low','medium','high')}
    if counts!={'low':23,'medium':50,'high':77}:raise SystemExit(f'bad risk quotas: {counts}')
    for x in rows:
        parent=src.get(x['stable_lexeme_key'])
        if not parent or x['stable_lexeme_key']=='cesse|NOM' or (x['entry_id'],x['sense_id'])!=(parent['entry_id'],parent['sense_id']):raise SystemExit('sense reselection')
        if x['content_status']!='ai_draft' or not x['gloss_zh_short'] or not x['example_fr'] or not x['example_zh'] or x['example_source_type']!='ai_generated':raise SystemExit('invalid required draft content')
        if x['provenance'].get('actual_model')!='unknown' or not x['provenance'].get('input_facts_hash'):raise SystemExit('invalid provenance')
        if x['used_candidate_refs'] or x['gloss_source_strategy']!='ai_gap_fill':raise SystemExit('unexpected sourced candidate claim')
    review=[json.loads(line) for line in b.REVIEW.read_text().splitlines()]
    if len(review)!=150 or [x['stable_lexeme_key'] for x in review]!=[x['stable_lexeme_key'] for x in rows]:raise SystemExit('review JSONL mismatch')
    for x in rows:
        if x['stable_lexeme_key'] in WATCH and (x['entry_id'],x['sense_id'])!=(src[x['stable_lexeme_key']]['entry_id'],src[x['stable_lexeme_key']]['sense_id']):raise SystemExit('anti-drift binding regression')
    print(json.dumps({'ok':True,'items':150,'content_risk':counts,'semantic_quality':'external_review_required'}))
if __name__=='__main__':main()
