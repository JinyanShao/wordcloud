#!/usr/bin/env python3
"""Prepare candidate-independent Phase 3 learner-sense review facts.

The order is deliberate: select useful lexemes, propose a sense from source
metadata, then attach cached DBnary candidates, then classify review risk.
Translation availability never selects or promotes a sense.
"""
from __future__ import annotations

import hashlib, json, re, sqlite3, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data/processed/wordcloud.sqlite"
CANDIDATES = Path("/tmp/wordcloud-phase3-candidates.json")
REVIEWED = ROOT / "data/learner-sense-content-reviewed.json"
OUT = ROOT / "data/phase3/learner-sense-500-review-input.json"
TIERS = ("low_risk", "medium_risk", "high_risk")
QUOTAS = {
    "A1": {"VER": 73, "NOM": 65, "ADJ": 50, "ADV": 30},
    "A2": {"VER": 77, "NOM": 70, "ADJ": 45, "ADV": 10},
    "B1": {"VER": 18, "NOM": 18, "ADJ": 16, "ADV": 8},
    "B2": {"VER": 7, "NOM": 7, "ADJ": 4, "ADV": 2},
}
DATED = {"vieilli", "désuet", "archaïque", "archaïsme"}
HISTORICAL_LABEL_MARKERS = {"étymologique", "etymologique", "historique"}
REGISTER = {"littéraire", "soutenu", "rare"}
SPECIALIZED = {"marine", "botanique", "zoologie", "entomologie", "chimie", "physique", "médecine", "medecine", "droit", "linguistique", "technique", "histoire", "anatomie", "religion"}

def canon(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
def digest(value): return hashlib.sha256(canon(value).encode()).hexdigest()
def norm(value): return unicodedata.normalize("NFC", value.replace("’", "'").strip().lower())
def labels(definition):
    hit = re.match(r"^\s*((?:\([^)]*\)\s*)+)", definition)
    return [] if not hit else [norm(x) for group in re.findall(r"\(([^)]*)\)", hit.group(1)) for x in group.split(",") if x.strip()]

def senses(conn, lexeme_id):
    rows = conn.execute("""SELECT s.entry_id,s.id,s.sense_number,s.definition_fr,s.examples_json,le.entry_rank
      FROM lexeme_senses s JOIN lexical_entries le ON le.id=s.entry_id WHERE s.lexeme_id=?
      ORDER BY le.entry_rank,s.entry_id,CAST(s.sense_number AS REAL),s.sense_number,s.id""", (lexeme_id,)).fetchall()
    return [{"entry_id":r[0],"sense_id":r[1],"sense_number":r[2],"source_order":i+1,"entry_rank":r[5],"definition_fr":r[3],"sourced_examples":json.loads(r[4])[:2],"leading_labels":labels(r[3])} for i,r in enumerate(rows)]

def propose(all_senses, lemma):
    ranked=[]
    for s in all_senses:
        ls=s["leading_labels"]; penalty=0; reasons=[]
        if any(x in DATED or any(marker in x for marker in HISTORICAL_LABEL_MARKERS) for x in ls): penalty+=100; reasons.append("dated_or_literary")
        if any(x in SPECIALIZED for x in ls): penalty+=25; reasons.append("specialized_domain")
        if any(x in REGISTER for x in ls): penalty+=10; reasons.append("marked_register")
        surface=s["entry_id"].split("__",1)[0]
        if lemma == lemma.lower() and norm(surface)!=norm(lemma): penalty+=40; reasons.append("nonmatching_entry_surface")
        ranked.append((penalty,s["source_order"],s,reasons))
    penalty, order, selected, reasons=min(ranked,key=lambda x:(x[0],x[1]))
    tied=sum(1 for score,_,_,_ in ranked if score==penalty)>1
    return selected, reasons, tied

def relations(conn, lexeme_id):
    rows=conn.execute("""SELECT e.subtype,e.direction,e.label,a.normalized,a.pos,b.normalized,b.pos
      FROM official_edges e JOIN official_edge_sources x ON x.edge_id=e.id JOIN lexemes a ON a.id=e.a_id JOIN lexemes b ON b.id=e.b_id
      WHERE e.relation='fam' AND e.dimension='derivational_morphology' AND e.review_status='sourced' AND x.source_id='demonette_2' AND (e.a_id=? OR e.b_id=?)
      ORDER BY a.normalized,a.pos,b.normalized,b.pos,e.subtype""",(lexeme_id,lexeme_id)).fetchall()
    return [{"stable_relation_key":"|".join(sorted((f"{norm(a)}|{ap}",f"{norm(b)}|{bp}")))+f"|{sub}","subtype":sub,"direction":direction,"label":label,"source_boundary":"demonette_2:sourced"} for sub,direction,label,a,ap,b,bp in rows]

def production_keys(): return {x["stable_lexeme_key"] for x in json.loads(REVIEWED.read_text())["items"]}

def select(conn):
    excluded=production_keys(); out=[]; ids=set()
    for level, by_pos in QUOTAS.items():
      for pos, quota in by_pos.items():
        rows=conn.execute("""SELECT id,lemma,normalized,pos,cefr_level,flelex_frequency,lexique_frequency,contextual_diversity
          FROM lexemes WHERE status='eligible' AND cefr_level=? AND pos=? AND EXISTS(SELECT 1 FROM lexeme_senses s WHERE s.lexeme_id=lexemes.id)
          ORDER BY COALESCE(flelex_frequency,0) DESC,COALESCE(lexique_frequency,0) DESC,id""",(level,pos)).fetchall()
        picked=[r for r in rows if f"{norm(r[2])}|{r[3]}" not in excluded and r[0] not in ids][:quota]
        if len(picked)!=quota: raise SystemExit(f"insufficient {level}/{pos}: {len(picked)}/{quota}")
        out.extend(picked); ids.update(r[0] for r in picked)
    return out

def candidate_index():
    if not CANDIDATES.exists(): raise SystemExit(f"missing cached candidate artifact: {CANDIDATES}")
    by_entry=defaultdict(list)
    for c in json.loads(CANDIDATES.read_text())["items"]:
        if c.get("entry_id"): by_entry[c["entry_id"]].append(c)
    return by_entry

def classify(item):
    s=item["proposed_primary_learner_sense"]; all_s=item["all_source_senses"]; candidates=item["selected_sense_chinese_candidates"]; flags=[]
    entries={x["entry_id"] for x in all_s}; ls=s["leading_labels"]; definition=s["definition_fr"]
    if len(all_s)>=6: flags.append("many_senses")
    if len(all_s)>=12: flags.append("extreme_polysemy")
    if len(entries)>1: flags.append("multiple_lexical_entries")
    if item["capitalization_variant"]: flags.append("capitalization_variant")
    if any(x in DATED|REGISTER or any(marker in x for marker in HISTORICAL_LABEL_MARKERS) for x in ls): flags.append("dated_or_literary")
    if any(x in SPECIALIZED for x in ls): flags.append("specialized_domain")
    if any(
        sense["sense_id"] != s["sense_id"] and (
            any(label in DATED or any(marker in label for marker in HISTORICAL_LABEL_MARKERS) for label in sense["leading_labels"])
            or any(label in SPECIALIZED for label in sense["leading_labels"])
        ) for sense in all_s
    ): flags.append("dated_or_specialized_competing_sense")
    if item["source_order_only_choice"]: flags.append("source_order_only_choice")
    if len(definition.strip())<28: flags.append("definition_very_short")
    if len(definition)>180 or any(x in SPECIALIZED for x in ls): flags.append("definition_complex_or_opaque")
    default=[c for c in candidates if c["learner_language_eligibility"]=="default_learner_chinese"]
    exact=[c for c in default if c["candidate_class"]=="sense_mapped_candidate" and c["mapped_sense_id"]==s["sense_id"]]
    if not default: flags.append("no_default_chinese_candidate")
    if len({c["chinese_written_form"] for c in default})>1: flags.append("multiple_chinese_candidates")
    if default and not exact: flags.append("candidate_not_sense_mapped")
    if any(c["candidate_class"]=="sense_mapped_candidate" and c["mapped_sense_id"]!=s["sense_id"] and c["translation_gloss"] for c in default): flags.append("candidate_gloss_domain_mismatch_possible")
    if any(c["candidate_class"]=="sense_mapped_candidate" for c in candidates): flags.append("candidate_mapping_known_structural_only")
    if any(c["learner_language_eligibility"]!="default_learner_chinese" for c in candidates): flags.append("nondefault_language_variant_present")
    if len(all_s)>=3: flags.append("lemma_highly_polysemous")
    flags.append("cefr_lexeme_level_only")
    # Low risk is intentionally strict: no meaningful ambiguity and exactly one structural candidate.
    high={"extreme_polysemy","multiple_lexical_entries","capitalization_variant","dated_or_literary","specialized_domain","definition_complex_or_opaque","candidate_gloss_domain_mismatch_possible"}
    low_allowed={"candidate_mapping_known_structural_only","cefr_lexeme_level_only","no_default_chinese_candidate"}
    if any(x in high for x in flags): tier="high_risk"
    elif set(flags).issubset(low_allowed) and len(all_s)<=2 and len(entries)==1 and (not default or len(exact)==1): tier="low_risk"
    else: tier="medium_risk"
    return sorted(set(flags)), tier

def build():
    by_entry=candidate_index(); conn=sqlite3.connect(DB); conn.row_factory=sqlite3.Row
    try:
      items=[]
      for r in select(conn):
        key=f"{norm(r['normalized'])}|{r['pos']}"; all_s=senses(conn,r['id']); selected, proposal_flags, tied=propose(all_s,r['lemma'])
        attached=[]
        for c in sorted(by_entry.get(selected['entry_id'],[]),key=lambda x:x['translation_stable_ref']):
          attached.append({k:c.get(k) for k in ('translation_stable_ref','candidate_class','chinese_written_form','target_language_code','learner_language_eligibility','translation_gloss','mapped_sense_id','ambiguity_reasons')})
        item={"stable_lexeme_key":key,"runtime_lexeme_id":r['id'],"lemma":r['lemma'],"pos":r['pos'],"cefr":r['cefr_level'],"frequency_signals":{"flelex_frequency":r['flelex_frequency'],"lexique_frequency":r['lexique_frequency'],"contextual_diversity":r['contextual_diversity']},"all_source_senses":all_s,"proposed_primary_learner_sense":selected,"selection_status":"needs_semantic_review","selection_reason":"candidate-independent source-label, entry-surface, then source-order proposal","uncertainty":"mechanical proposal; semantic fitness and real frequency require review","source_order_only_choice":tied,"capitalization_variant":any(norm(x['entry_id'].split('__',1)[0])==norm(r['lemma']) and x['entry_id'].split('__',1)[0]!=r['lemma'] for x in all_s),"proposal_policy_flags":proposal_flags,"competing_source_senses":[x for x in all_s if x['sense_id']!=selected['sense_id']],"selected_sense_chinese_candidates":attached,"relevant_sourced_family_relations":relations(conn,r['id'])}
        item['risk_flags'],item['risk_tier']=classify(item); item['risk_rationale']='; '.join(item['risk_flags']); item['input_hash']=digest(item); items.append(item)
    finally: conn.close()
    items.sort(key=lambda x:(x['cefr'],x['pos'],-(x['frequency_signals']['flelex_frequency'] or 0),x['runtime_lexeme_id']))
    body={"schema_version":1,"scope":"Phase 3A review facts, candidate context, and deterministic risk triage only; no learner prose or semantic approval.","items":items}
    body['artifact_hash']=digest(body); return body

def write():
    payload=build(); OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n")
    for tier in TIERS:
      body={"schema_version":1,"parent_artifact_hash":payload['artifact_hash'],"risk_tier":tier,"items":[x for x in payload['items'] if x['risk_tier']==tier]}; body['artifact_hash']=digest(body)
      (OUT.parent/f"{tier}.json").write_text(json.dumps(body,ensure_ascii=False,indent=2)+"\n")
    return payload
if __name__=='__main__':
    x=write(); print(json.dumps({"items":len(x['items']),"cefr":Counter(i['cefr'] for i in x['items']),"pos":Counter(i['pos'] for i in x['items']),"tiers":Counter(i['risk_tier'] for i in x['items'])},ensure_ascii=False))
