#!/usr/bin/env python3
"""Validate Phase 3A artifacts and replay the Phase 2C risk calibration.

This reads SQLite plus the already-cached processed candidate artifact only;
it never reads or scans raw DBnary.
"""
from __future__ import annotations
import json, sqlite3, sys
from collections import Counter
from pathlib import Path
import build_phase3_scale_prep as b

ROOT=b.ROOT; CAL=ROOT/'data/phase3/phase2c-calibration-report.json'
PHASE2_INPUT=Path('/tmp/wordcloud-phase2c-input.json')
HISTORICAL={f'{x}|{p}' for x,p in [
 ('monde','NOM'),('vie','NOM'),('faire','VER'),('devoir','VER'),('économique','ADJ'),('inquiet','ADJ'),('cependant','ADV'),('point','NOM'),('corps','NOM'),('emploi','NOM'),('développer','VER'),('étonner','VER'),('rapport','NOM'),('chef','NOM'),('paraître','VER'),('assurer','VER'),('terme','NOM'),('antenne','NOM'),('vieux','ADJ'),('sûr','ADJ'),('maison','NOM'),('temps','NOM'),('personne','NOM'),('pouvoir','VER'),('savoir','VER'),('prendre','VER'),('mettre','VER'),('remettre','VER'),('élever','VER') ]}

def reviewed_item(conn, candidate_index, reviewed):
    row=conn.execute('SELECT id,lemma,normalized,pos,cefr_level,flelex_frequency,lexique_frequency,contextual_diversity FROM lexemes WHERE id=?',(reviewed['runtime_lexeme_id'],)).fetchone()
    all_s=b.senses(conn,row['id']); selected=next(s for s in all_s if s['entry_id']==reviewed['entry_id'] and s['sense_id']==reviewed['sense_id'])
    candidates=[{k:c.get(k) for k in ('translation_stable_ref','candidate_class','chinese_written_form','target_language_code','learner_language_eligibility','translation_gloss','mapped_sense_id','ambiguity_reasons')} for c in sorted(candidate_index.get(selected['entry_id'],[]),key=lambda x:x['translation_stable_ref'])]
    item={'stable_lexeme_key':reviewed['stable_lexeme_key'],'all_source_senses':all_s,'proposed_primary_learner_sense':selected,'competing_source_senses':[s for s in all_s if s['sense_id']!=selected['sense_id']], 'selected_sense_chinese_candidates':candidates,'source_order_only_choice':False,'capitalization_variant':any(b.norm(s['entry_id'].split('__',1)[0])==b.norm(row['lemma']) and s['entry_id'].split('__',1)[0]!=row['lemma'] for s in all_s)}
    item['risk_flags'],item['risk_tier']=b.classify(item); return item

def calibration():
    candidates=b.candidate_index(); reviewed=json.loads(b.REVIEWED.read_text())['items']
    conn=sqlite3.connect(b.DB); conn.row_factory=sqlite3.Row
    reviewed=[x for x in reviewed if x['content_status']=='reviewed']
    try: rows=[reviewed_item(conn,candidates,x) for x in reviewed]
    finally: conn.close()
    by={x['stable_lexeme_key']:x for x in rows}
    for key in ('antenne|NOM','chef|NOM'):
        if by[key]['risk_tier']!='high_risk': raise SystemExit(f'{key} must be high risk')
    if by['devoir|VER']['risk_tier']=='low_risk': raise SystemExit('devoir must not be low risk')
    known_low=[key for key in HISTORICAL if by[key]['risk_tier']=='low_risk']
    if known_low: raise SystemExit(f'known Phase 2C risk fixture marked low: {known_low}')
    if not PHASE2_INPUT.exists(): raise SystemExit(f'missing frozen Phase 2C input needed for calibration: {PHASE2_INPUT}')
    original={x['stable_lexeme_key']:(x['proposed_primary_learner_sense']['entry_id'],x['proposed_primary_learner_sense']['sense_id']) for x in json.loads(PHASE2_INPUT.read_text())['items']}
    corrected={x['stable_lexeme_key'] for x in reviewed if original[x['stable_lexeme_key']] != (x['entry_id'],x['sense_id'])}
    dangerous_low=[x['stable_lexeme_key'] for x in rows if x['stable_lexeme_key'] in corrected and x['risk_tier']=='low_risk']
    if dangerous_low: raise SystemExit(f'dangerous historical low-risk false negatives: {dangerous_low}')
    return {'schema_version':1,'scope':'Phase 2C known semantic-risk regression calibration; risk tiers are triage, not semantic approval.','reviewed_records':len(rows),'known_historical_risk_records':len(HISTORICAL),'historical_corrected_records':len(corrected),'historical_corrected_items_by_tier':dict(Counter(x['risk_tier'] for x in rows if x['stable_lexeme_key'] in corrected)),'historical_no_correction_items_by_tier':dict(Counter(x['risk_tier'] for x in rows if x['stable_lexeme_key'] not in corrected)),'dangerous_low_risk_false_negatives':dangerous_low,'records':[{'stable_lexeme_key':x['stable_lexeme_key'],'selection_corrected_in_phase2c':x['stable_lexeme_key'] in corrected,'risk_tier':x['risk_tier'],'risk_flags':x['risk_flags']} for x in sorted(rows,key=lambda x:x['stable_lexeme_key'])]}

def main():
    payload=json.loads(b.OUT.read_text()); rebuilt=b.build()
    if payload!=rebuilt: raise SystemExit('main artifact is not deterministic')
    if payload['artifact_hash']!=b.digest({k:v for k,v in payload.items() if k!='artifact_hash'}): raise SystemExit('main artifact hash mismatch')
    items=payload['items']; production=b.production_keys()
    if len(items)!=500 or len({x['stable_lexeme_key'] for x in items})!=500: raise SystemExit('must be exactly 500 distinct lexemes')
    if production & {x['stable_lexeme_key'] for x in items}: raise SystemExit('production overlap')
    for tier in b.TIERS:
        projection=json.loads((b.OUT.parent/f'{tier}.json').read_text())
        expected=[x for x in items if x['risk_tier']==tier]
        if projection.get('items')!=expected or projection.get('parent_artifact_hash')!=payload['artifact_hash']: raise SystemExit(f'bad {tier} projection')
        if projection.get('artifact_hash')!=b.digest({k:v for k,v in projection.items() if k!='artifact_hash'}): raise SystemExit(f'bad {tier} hash')
    for item in items:
        selected=item['proposed_primary_learner_sense']
        if (selected['entry_id'],selected['sense_id']) not in {(s['entry_id'],s['sense_id']) for s in item['all_source_senses']}: raise SystemExit('orphan sense')
        flags,tier=b.classify(item)
        if flags!=item['risk_flags'] or tier!=item['risk_tier']: raise SystemExit('non-deterministic risk tier')
        if item['selection_status']!='needs_semantic_review' or 'candidate-independent' not in item['selection_reason']: raise SystemExit('candidate availability may have selected a sense')
    report=calibration(); body={**report}; body['artifact_hash']=b.digest(body)
    if '--write-calibration' in sys.argv:
        CAL.write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n')
    elif CAL.exists() and json.loads(CAL.read_text())!=body: raise SystemExit('calibration report drift')
    print(json.dumps({'ok':True,'items':500,'tiers':Counter(x['risk_tier'] for x in items),'calibration':report['historical_corrected_items_by_tier']},ensure_ascii=False))

if __name__=='__main__': main()
