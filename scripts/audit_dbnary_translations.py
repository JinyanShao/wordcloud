#!/usr/bin/env python3
"""Read-only coverage audit for DBnary translations in the registered raw snapshot."""
from __future__ import annotations
import bz2, json, re, sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from import_dbnary import expected_source_sha256, local_name, sha256, stream_blocks, subject_token

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/"data/raw/dbnary/fr_dbnary_ontolex.ttl.bz2"
DB=ROOT/"data/processed/wordcloud.sqlite"
PILOT=ROOT/"data/learner-content-pilot-input.json"
REPORT=ROOT/"data/reports/dbnary-translation-audit.json"

def values(block, predicate):
    match=re.search(rf"{re.escape(predicate)}\s+(.+?)(?=;\s*\n|\s+\.\s*$)",block,re.S)
    return [] if not match else [x.strip() for x in re.split(r"\s*,\s*",match.group(1))]

def literal(block, predicate):
    match=re.search(rf'{re.escape(predicate)}\s+"((?:[^"\\]|\\.)*)"(?:@([\w-]+))?',block)
    return None if not match else (match.group(1),match.group(2))

def run():
    actual_hash=sha256(RAW)
    if actual_hash != expected_source_sha256():
        raise SystemExit("registered DBnary raw snapshot hash mismatch")
    conn=sqlite3.connect(DB)
    conn.row_factory=sqlite3.Row
    entries={r["id"]:dict(r) for r in conn.execute("SELECT le.id,le.lexeme_id,l.lemma,l.pos,l.cefr_level,l.status FROM lexical_entries le JOIN lexemes l ON l.id=le.lexeme_id")}
    sense_pairs={(r["entry_id"],r["sense_number"]) for r in conn.execute("SELECT entry_id,sense_number FROM lexeme_senses")}
    sense_ids={r["id"] for r in conn.execute("SELECT id FROM lexeme_senses")}
    searchable={r[0] for r in conn.execute("SELECT lexeme_id FROM positions")}
    a1a2={r[0] for r in conn.execute("SELECT id FROM lexemes WHERE status='eligible' AND cefr_level IN ('A1','A2')")}
    pilot=json.loads(PILOT.read_text())["items"]
    pilot_by_key={(x["lemma"].lower(),x["pos"]):x for x in pilot}
    total=0; code_counts=Counter(); chinese=[]; raw_sources=set(); glosses={}; target_stats=Counter()
    for block in stream_blocks(RAW):
        if "dbnary:Translation" not in block: 
            if "dbnary:Gloss" in block:
                subject=local_name(subject_token(block))
                text=literal(block,"rdf:value"); number=literal(block,"dbnary:senseNumber")
                if subject and text: glosses[subject]={"text":text[0],"sense_number":number[0] if number else None}
            continue
        total+=1
        code_match=re.search(r"dbnary:targetLanguage\s+lexvo:([A-Za-z0-9_-]+)",block)
        code=code_match.group(1) if code_match else None
        if not code:
            literal_code=literal(block,"dbnary:targetLanguageCode"); code=literal_code[0] if literal_code else "missing"
        code_counts[code]+=1
        form=literal(block,"dbnary:writtenForm")
        source=local_name(values(block,"dbnary:isTranslationOf")[0]) if values(block,"dbnary:isTranslationOf") else None
        gloss=local_name(values(block,"dbnary:gloss")[0]) if values(block,"dbnary:gloss") else None
        if code in {"zho","chi","cmn","yue"} or (form and form[1] and form[1].lower().startswith("zh")):
            if source: raw_sources.add(source)
            chinese.append({"source":source,"gloss":gloss,"form":form[0] if form else None,"form_lang":form[1] if form else None,"code":code})
    by_entry=defaultdict(list)
    chinese_lexemes=set(); searchable_lexemes=set(); a1a2_lexemes=set(); direct_sense=0; entry_only=0; gloss_count=0; gloss_mappable=0
    pilot_result={}
    for t in chinese:
        source=t["source"]; entry=None
        if source in sense_ids:
            direct_sense+=1
            # DBnary sense identifiers include the entry local name as a prefix.
            entry=next((eid for eid in entries if source.startswith(eid)),None)
        elif source in entries:
            entry_only+=1; entry=source
        else: target_stats["unmatched_target"]+=1
        if entry:
            by_entry[entry].append(t); lex=entries[entry]["lexeme_id"]; chinese_lexemes.add(lex)
            if lex in searchable: searchable_lexemes.add(lex)
            if lex in a1a2: a1a2_lexemes.add(lex)
        if t["gloss"]:
            gloss_count+=1
            g=glosses.get(t["gloss"])
            if entry and g and g["sense_number"] and (entry,g["sense_number"]) in sense_pairs: gloss_mappable+=1
    for (lemma,pos), item in pilot_by_key.items():
        hits=[]
        for entry, ts in by_entry.items():
            e=entries[entry]
            if e["lemma"].lower()==lemma and e["pos"]==pos: hits.extend(ts)
        selected=item["identity"]
        primary_number=None
        row=conn.execute("SELECT sense_number FROM lexeme_senses WHERE entry_id=? AND id=?",(selected["entry_id"],selected["sense_id"])).fetchone()
        if row: primary_number=row[0]
        sense_aware=any(glosses.get(x["gloss"],{}).get("sense_number")==primary_number for x in hits if x["gloss"])
        pilot_result[f"{lemma}|{pos}"]={"chinese_translations":len(hits),"target_modes":Counter("sense" if x["source"] in sense_ids else "entry" for x in hits),"selected_sense_gloss_match":sense_aware,
                                       "sample_forms":[x["form"] for x in hits[:5]]}
    result={"snapshot":"fr_dbnary_ontolex_2026-09-01","raw_sha256":actual_hash,"translation_records_total":total,"target_language_codes":code_counts,
            "chinese_target_codes":sorted({x["code"] for x in chinese}),"chinese_translation_records":len(chinese),
            "chinese_distinct_raw_translation_targets":len(raw_sources),"chinese_distinct_french_entries":len(by_entry),"chinese_distinct_french_lexemes":len(chinese_lexemes),
            "searchable_lexemes":len(searchable),"searchable_with_chinese":len(searchable_lexemes),
            "a1a2_eligible_lexemes":len(a1a2),"a1a2_with_chinese":len(a1a2_lexemes),
            "chinese_with_gloss":gloss_count,"gloss_sense_number_mappable":gloss_mappable,
            "direct_sense_targets":direct_sense,"entry_targets":entry_only,
            "entries_with_multiple_chinese":sum(len(v)>1 for v in by_entry.values()),"pilot":pilot_result,
            "semantic_boundary":"Gloss sense-number mapping is a structural candidate only; it does not prove modern sense alignment or learner suitability."}
    REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__": run()
