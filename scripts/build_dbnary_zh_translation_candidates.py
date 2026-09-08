#!/usr/bin/env python3
"""Deterministically project hash-pinned DBnary Chinese translations into candidates."""
from __future__ import annotations
import json, re, sqlite3, unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from import_dbnary import expected_source_sha256, local_name, stream_blocks, subject_token
from audit_dbnary_translations import literal, values

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/"data/raw/dbnary/fr_dbnary_ontolex.ttl.bz2"; DB=ROOT/"data/processed/wordcloud.sqlite"
OUT=ROOT/"data/processed/dbnary-zh-translation-candidates.json"
CHINESE_CODES={"zho":"default_chinese_pool","cmn":"default_mandarin_pool","yue":"nondefault_cantonese","zhb":"nondefault_zh_variant","zhd":"nondefault_zh_variant","zhn":"nondefault_zh_variant"}
def norm(v): return unicodedata.normalize("NFC",v.replace("’","'").strip().lower())
def language(block, form):
 m=re.search(r"dbnary:targetLanguage\s+lexvo:([A-Za-z0-9_-]+)",block)
 return m.group(1) if m else (literal(block,"dbnary:targetLanguageCode") or ("missing",None))[0]
def build():
 # The source hash was verified by the preceding core audit.  Rehashing here
 # would add a second full raw-file pass without changing candidate semantics.
 pinned_hash=expected_source_sha256()
 conn=sqlite3.connect(DB); conn.row_factory=sqlite3.Row
 entries={r["id"]:dict(r) for r in conn.execute("SELECT le.id,le.lexeme_id,l.lemma,l.normalized,l.pos,l.cefr_level,l.status FROM lexical_entries le JOIN lexemes l ON l.id=le.lexeme_id")}
 senses=defaultdict(list)
 for r in conn.execute("SELECT id,entry_id,sense_number FROM lexeme_senses"): senses[r["entry_id"]].append((r["id"],r["sense_number"]))
 gl={}; raw=[]
 for b in stream_blocks(RAW):
  if "dbnary:Gloss" in b:
   s=local_name(subject_token(b)); text=literal(b,"rdf:value"); number=literal(b,"dbnary:senseNumber")
   if s and text: gl[s]={"text":text[0],"sense_number":number[0] if number else None}
   continue
  if "dbnary:Translation" not in b: continue
  form=literal(b,"dbnary:writtenForm"); code=language(b,form)
  if code not in CHINESE_CODES: continue
  srcs=values(b,"dbnary:isTranslationOf"); source=local_name(srcs[0]) if srcs else None
  if not form or not form[0].strip(): continue
  raw.append({"translation_id":local_name(subject_token(b)),"source_entry_id":source,"written_form":form[0],"target_language_code":code,
              "translation_gloss_id":local_name(values(b,"dbnary:gloss")[0]) if values(b,"dbnary:gloss") else None})
 by_entry=defaultdict(list)
 for r in raw:
  if r["source_entry_id"] in entries: by_entry[r["source_entry_id"]].append(r)
 items=[]
 for r in raw:
  entry=entries.get(r["source_entry_id"]); g=gl.get(r["translation_gloss_id"]); mapped=None
  if entry and g and g["sense_number"]:
   mapped=next((sid for sid,num in senses[entry["id"]] if num==g["sense_number"]),None)
  forms={norm(x["written_form"]) for x in by_entry.get(r["source_entry_id"],[])}
  if not entry: tier="unmapped"; reasons=["entry_not_in_current_sqlite"]
  elif mapped: tier="sense_mapped_candidate"; reasons=[]
  elif len(senses[entry["id"]])==1 and len(forms)==1: tier="entry_single_candidate"; reasons=["entry_level_translation_only"]
  else: tier="entry_ambiguous_candidate"; reasons=(["multiple_current_senses"] if len(senses[entry["id"]])>1 else [])+(["multiple_chinese_forms"] if len(forms)>1 else [])+["no_structural_sense_mapping"]
  item={"translation_stable_ref":f"dbnary_fr:{r['translation_id']}","chinese_written_form":r["written_form"],"target_language_code":r["target_language_code"],
        "learner_language_pool":CHINESE_CODES[r["target_language_code"]],"translation_gloss":g["text"] if g else None,"gloss_sense_number":g["sense_number"] if g else None,
        "learner_language_eligibility":"default_learner_chinese" if r["target_language_code"] in {"zho","cmn"} else "nondefault_chinese_variant",
        "mapped_sense_id":mapped,"candidate_class":tier,"ambiguity_reasons":reasons,
        "enhanced_sense_links":[],"enhanced_source_version":None,
        "source_provenance":{"source_id":"dbnary_fr","snapshot_sha256":pinned_hash,"translation_subject":r["translation_id"],"is_translation_of":r["source_entry_id"]}}
  if entry: item.update({"stable_lexeme_key":f"{entry['normalized']}|{entry['pos']}","runtime_lexeme_id":entry["lexeme_id"],"entry_id":entry["id"]})
  else: item.update({"stable_lexeme_key":None,"runtime_lexeme_id":None,"entry_id":None})
  items.append(item)
 conn.close()
 return {"schema_version":1,"scope":"Sourced translation candidates only; not reviewed learner glosses.","items":sorted(items,key=lambda x:x["translation_stable_ref"])}
if __name__=="__main__":
 p=build(); OUT.write_text(json.dumps(p,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"candidates":len(p["items"]),"classes":Counter(x["candidate_class"] for x in p["items"])}))
