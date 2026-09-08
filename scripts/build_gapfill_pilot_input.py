#!/usr/bin/env python3
"""Deterministically build the historical 30-record Phase 2B fact input.

Do not use candidate availability to select senses for a future milestone.
The future contract is: learner-priority sense selection (independent
editorial judgment) -> candidate lookup -> structural and semantic filtering.
``sense_mapped_candidate`` is a structural DBnary mapping, not an approved
learner gloss.  Lexeme-level CEFR is only a discovery signal.
"""
import hashlib,json,sqlite3
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; DB=ROOT/"data/processed/wordcloud.sqlite"
CAND=ROOT/"data/processed/dbnary-zh-translation-candidates.json"; OUT=ROOT/"data/learner-content-gapfill-pilot-input.json"
DEFAULT="default_learner_chinese"
def canon(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def senses(conn,lid):
 return conn.execute("SELECT s.entry_id,s.id,s.sense_number,s.definition_fr,s.examples_json FROM lexeme_senses s WHERE s.lexeme_id=? ORDER BY s.entry_id,CAST(s.sense_number AS REAL),s.sense_number",(lid,)).fetchall()
def build():
 cands=json.load(open(CAND))["items"]; by=defaultdict(list)
 for x in cands:
  if x["learner_language_eligibility"]==DEFAULT and x["runtime_lexeme_id"]: by[x["runtime_lexeme_id"]].append(x)
 con=sqlite3.connect(DB); con.row_factory=sqlite3.Row
 # A: exact mapped sense candidates, one per sense, deterministic lexical ordering.
 A=[]; seen=set()
 for x in sorted(cands,key=lambda x:x["translation_stable_ref"]):
  k=(x.get("runtime_lexeme_id"),x.get("mapped_sense_id"))
  if x["candidate_class"]=="sense_mapped_candidate" and x["learner_language_eligibility"]==DEFAULT and k not in seen:
   seen.add(k); A.append((x["runtime_lexeme_id"],x["entry_id"],x["mapped_sense_id"],"A","exact_structural_sense_mapping")); 
   if len(A)==10: break
 # B: required ambiguity cases then deterministic ambiguous fill.
 required=[14232,5081,6194,5859]; B=[]; used=set()
 for lid in required:
  x=next((q for q in by[lid] if q["candidate_class"]=="entry_ambiguous_candidate"),None)
  if x: B.append((lid,x["entry_id"],None,"B","entry_level_or_multi_candidate_ambiguity")); used.add(lid)
 for x in sorted(cands,key=lambda x:x["translation_stable_ref"]):
  if len(B)==10: break
  if x["candidate_class"]=="entry_ambiguous_candidate" and x["learner_language_eligibility"]==DEFAULT and x["runtime_lexeme_id"] not in used:
   B.append((x["runtime_lexeme_id"],x["entry_id"],None,"B","entry_level_or_multi_candidate_ambiguity")); used.add(x["runtime_lexeme_id"])
 # C: A1/A2 lexemes with no default candidate, distinct lexemes.
 has=set(by); C=[] 
 rows=con.execute("SELECT id FROM lexemes WHERE status='eligible' AND cefr_level IN ('A1','A2') ORDER BY COALESCE(flelex_frequency,0) DESC,id").fetchall()
 for r in rows:
  lid=r[0]
  if lid in has: continue
  available=senses(con,lid)
  if not available: continue
  s=available[0]; C.append((lid,s[0],s[1],"C","no_default_chinese_candidate"))
  if len(C)==10: break
 selections=A+B+C; items=[]
 for lid,entry,sid,group,reason in selections:
  lex=con.execute("SELECT id,lemma,normalized,pos,cefr_level FROM lexemes WHERE id=?",(lid,)).fetchone()
  all_s=senses(con,lid)
  if sid is None or not any(q[0]==entry and q[1]==sid for q in all_s):
   entry,sid=all_s[0][0],all_s[0][1]
  s=next(q for q in all_s if q[0]==entry and q[1]==sid)
  matching=[x for x in by[lid] if x["entry_id"]==entry and (group!="A" or x["mapped_sense_id"]==sid)]
  fact={"group":group,"stable_lexeme_key":f"{lex['normalized']}|{lex['pos']}","runtime_lexeme_id":lid,"entry_id":entry,"sense_id":sid,"lemma":lex["lemma"],"pos":lex["pos"],"cefr":lex["cefr_level"],"definition_fr":s[3],"sourced_examples":json.loads(s[4]),"learner_sense_selection":{"selection_status":"ai_draft","selection_rationale":reason,"uncertainty":"semantic_editorial_review_required"},"matching_chinese_candidates":[{"candidate_class":x["candidate_class"],"candidate_stable_ref":x["translation_stable_ref"],"chinese_written_form":x["chinese_written_form"],"target_language_code":x["target_language_code"],"learner_language_eligibility":x["learner_language_eligibility"],"translation_gloss":x["translation_gloss"],"mapped_sense_id":x["mapped_sense_id"]} for x in matching],"relevant_sourced_family_relations":[]}
  fact["input_hash"]=hashlib.sha256(canon(fact).encode()).hexdigest();items.append(fact)
 con.close(); payload={"schema_version":1,"scope":"Phase 2B fact input only; no learner draft or semantic judgment.","items":items}; payload["artifact_hash"]=hashlib.sha256(canon(payload).encode()).hexdigest();return payload
if __name__=="__main__":
 p=build();OUT.write_text(json.dumps(p,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"groups":{g:sum(x["group"]==g for x in p["items"]) for g in "ABC"}}))
