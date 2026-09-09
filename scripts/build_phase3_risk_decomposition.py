#!/usr/bin/env python3
"""Decompose Phase 3A's combined risk without changing its 500 proposals."""
from __future__ import annotations
import hashlib, json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'data/phase3/learner-sense-500-review-input.json'
OUT=ROOT/'data/phase3/learner-sense-500-risk-decomposed.json'
ROUTES=('auto_sense_candidate','ai_sense_adjudication','human_sense_review')
ROUTE_FILES={'auto_sense_candidate':'auto-sense-candidate.json','ai_sense_adjudication':'ai-sense-adjudication.json','human_sense_review':'human-sense-review.json'}
DATED={'vieilli','désuet','archaïque','archaïsme'}
HISTORICAL={'étymologique','etymologique','historique'}
SPECIALIZED={'marine','botanique','zoologie','entomologie','chimie','physique','médecine','medecine','droit','linguistique','technique','histoire','anatomie','religion'}
CONTENT_DRIFT={'bon|ADJ','français|ADJ','personne|NOM','pouvoir|VER','savoir|VER','prendre|VER','passer|VER','trouver|VER','parler|VER','mettre|VER','remettre|VER','élever|VER','vieux|ADJ','sûr|ADJ','maison|NOM','temps|NOM'}

def canonical(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()
def marked(labels): return any(x in DATED or any(token in x for token in HISTORICAL) or x in SPECIALIZED for x in labels)
def ordinary(sense): return not marked(sense['leading_labels'])

def sense_axis(item):
    selected=item['proposed_primary_learner_sense']; senses=item['all_source_senses']; labels=selected['leading_labels']; flags=[]
    entries={x['entry_id'] for x in senses}; ordinary_competing=sum(1 for x in senses if x['sense_id']!=selected['sense_id'] and ordinary(x))
    if len(senses)>=6: flags.append('many_senses')
    if len(senses)>=12: flags.append('extreme_polysemy')
    if len(entries)>1: flags.append('multiple_lexical_entries')
    if item['capitalization_variant']: flags.append('capitalization_variant')
    if any(x in DATED or any(token in x for token in HISTORICAL) for x in labels): flags.append('proposed_dated_or_literary')
    if any(x in SPECIALIZED for x in labels): flags.append('proposed_specialized_domain')
    if item['source_order_only_choice']: flags.append('source_order_only_tie')
    if ordinary_competing: flags.append('competing_unmarked_ordinary_sense')
    if selected['source_order'] > 3 and ordinary_competing: flags.append('late_source_sense_selection')
    if any(x['sense_id'] != selected['sense_id'] and x['source_order'] < selected['source_order'] and marked(x['leading_labels']) for x in senses): flags.append('marked_predecessor_requires_adjudication')
    if len(selected['definition_fr'])>180: flags.append('definition_complex_or_opaque')
    if any(x=='nonmatching_entry_surface' for x in item['proposal_policy_flags']): flags.append('lexical_entry_surface_mismatch')
    high={'extreme_polysemy','multiple_lexical_entries','capitalization_variant','proposed_dated_or_literary','proposed_specialized_domain','lexical_entry_surface_mismatch','late_source_sense_selection'}
    if high & set(flags): tier='high'
    elif flags: tier='medium'
    else: tier='low'
    return sorted(set(flags)),tier,ordinary_competing

def translation_axis(item):
    selected=item['proposed_primary_learner_sense']; candidates=item['selected_sense_chinese_candidates']; flags=[]
    default=[c for c in candidates if c['learner_language_eligibility']=='default_learner_chinese']
    exact=[c for c in default if c['candidate_class']=='sense_mapped_candidate' and c['mapped_sense_id']==selected['sense_id']]
    if not default: flags.append('no_default_chinese_candidate')
    if len({c['chinese_written_form'] for c in default})>1: flags.append('multiple_chinese_candidates')
    if default and not exact: flags.append('candidate_not_sense_mapped')
    if any(c['candidate_class']=='entry_single_candidate' for c in default): flags.append('entry_single_candidate_only')
    if any(c['candidate_class']=='entry_ambiguous_candidate' for c in default): flags.append('entry_level_or_ambiguous_candidate')
    if any(c['candidate_class']=='sense_mapped_candidate' and c['mapped_sense_id']!=selected['sense_id'] and c['translation_gloss'] for c in default): flags.append('candidate_gloss_domain_mismatch_possible')
    if any(c['candidate_class']=='sense_mapped_candidate' for c in candidates): flags.append('structural_mapping_only')
    if any(c['learner_language_eligibility']!='default_learner_chinese' for c in candidates): flags.append('nondefault_language_variant_present')
    if len(exact)==1 and len(default)==1: tier='low'
    elif 'candidate_gloss_domain_mismatch_possible' in flags or len(default)>1 or 'entry_level_or_ambiguous_candidate' in flags: tier='high'
    else: tier='medium'
    return sorted(set(flags)),tier

def content_axis(item, sense_tier, ordinary_competing):
    selected=item['proposed_primary_learner_sense']; senses=item['all_source_senses']; flags=[]
    if len(senses)>=6: flags.append('highly_polysemous_lemma')
    if ordinary_competing: flags.append('sibling_sense_confusion_possible')
    if len(selected['definition_fr'])>150: flags.append('definition_abstract_or_opaque')
    if any(x in SPECIALIZED for x in selected['leading_labels']): flags.append('specialized_usage')
    if item['pos']=='ADV' and len(selected['definition_fr'])<45: flags.append('function_or_discourse_sense_possible')
    if item['stable_lexeme_key'] in CONTENT_DRIFT: flags.append('phase2c_content_drift_regression')
    high={'highly_polysemous_lemma','specialized_usage','phase2c_content_drift_regression'}
    if high & set(flags): tier='high'
    elif flags or sense_tier=='high': tier='medium'
    else: tier='low'
    return sorted(set(flags)),tier

def route(sense, translation, content):
    review={'low':'auto_sense_candidate','medium':'ai_sense_adjudication','high':'human_sense_review'}[sense]
    translation_route=('source_reuse_candidate' if translation=='low' else 'ai_translation_disambiguation' if translation=='high' else 'ai_translation_gap_fill')
    content_route='content_sample_qa' if content=='low' else 'content_semantic_review'
    return review,translation_route,content_route

def build():
    parent=json.loads(PARENT.read_text()); records=[]
    for item in parent['items']:
        sense_flags,sense_tier,ordinary_competing=sense_axis(item)
        trans_flags,trans_tier=translation_axis(item)
        content_flags,content_tier=content_axis(item,sense_tier,ordinary_competing)
        review,translation_route,content_route=route(sense_tier,trans_tier,content_tier)
        record={'stable_lexeme_key':item['stable_lexeme_key'],'runtime_lexeme_id':item['runtime_lexeme_id'],'parent_input_hash':item['input_hash'],'proposed_primary_learner_sense':{k:item['proposed_primary_learner_sense'][k] for k in ('entry_id','sense_id')},'legacy_combined_risk':item['risk_tier'],'sense_selection_flags':sense_flags,'sense_selection_tier':sense_tier,'sense_selection_rationale':'; '.join(sense_flags) or 'one unmarked source sense with no detected competition','translation_flags':trans_flags,'translation_tier':trans_tier,'content_authoring_flags':content_flags,'content_authoring_tier':content_tier,'review_route':review,'translation_route':translation_route,'content_route':content_route}
        record['record_hash']=digest(record); records.append(record)
    body={'schema_version':1,'scope':'Phase 3B risk axes and routing only. French learner-sense proposals are inherited unchanged from the parent artifact; translation data never affects sense-selection tier. No learner prose or semantic approval.','parent_artifact_hash':parent['artifact_hash'],'items':records}
    body['artifact_hash']=digest(body); return body

def write():
    payload=build(); OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    for route_name in ROUTES:
        body={'schema_version':1,'parent_artifact_hash':payload['artifact_hash'],'review_route':route_name,'items':[x for x in payload['items'] if x['review_route']==route_name]};body['artifact_hash']=digest(body)
        (OUT.parent/ROUTE_FILES[route_name]).write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n')
    return payload
if __name__=='__main__':
    x=write(); print(json.dumps({'items':len(x['items']),'sense':Counter(a['sense_selection_tier'] for a in x['items']),'translation':Counter(a['translation_tier'] for a in x['items']),'content':Counter(a['content_authoring_tier'] for a in x['items'])}))
