#!/usr/bin/env python3
"""Build V3 fact artifacts for the fixed 20-lexeme learner pilot."""
from __future__ import annotations
import hashlib, json, sqlite3, unicodedata
from pathlib import Path
from build_learner_content import stable_key

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "processed" / "wordcloud.sqlite"
SENSES_PATH = ROOT / "data" / "learner-content-pilot-senses.json"
SELECTION_PATH = ROOT / "data" / "learner-content-pilot-selection.json"
INPUT_PATH = ROOT / "data" / "learner-content-pilot-input.json"
LEXEME_IDS = [14232,1157,9976,1034,2339,406,5859,5866,9495,9504,1515,1533,351,348,5081,5163,13641,13594,6194,6259]

def norm(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("’", "'").strip().lower())

def relations(conn, lexeme_id):
    rows = conn.execute("""SELECT e.subtype,e.direction,e.label,e.review_status,e.dimension,a.lemma,a.pos,b.lemma,b.pos,x.source_id
        FROM official_edges e JOIN official_edge_sources x ON x.edge_id=e.id JOIN lexemes a ON a.id=e.a_id JOIN lexemes b ON b.id=e.b_id
        WHERE e.relation='fam' AND e.dimension='derivational_morphology' AND e.review_status='sourced' AND x.source_id='demonette_2'
        AND (e.a_id=? OR e.b_id=?) ORDER BY a.normalized,a.pos,b.normalized,b.pos,e.subtype""",(lexeme_id,lexeme_id)).fetchall()
    return [{"stable_relation_key":stable_key(f"{norm(a)}|{ap}",f"{norm(b)}|{bp}",sub),"subtype":sub,"direction":direction,"label":label,
             "source_boundary":{"source_id":source,"review_status":review,"relation":"fam","dimension":dim}}
            for sub,direction,label,review,dim,a,ap,b,bp,source in rows]

def sense_rows(conn, lexeme_id):
    rows=conn.execute("""SELECT s.entry_id,s.id,s.sense_number,s.definition_fr,s.examples_json,s.source_id,le.source_url
        FROM lexeme_senses s JOIN lexical_entries le ON le.id=s.entry_id WHERE s.lexeme_id=?
        ORDER BY le.entry_rank,s.entry_id,CAST(s.sense_number AS REAL),s.sense_number,s.id""",(lexeme_id,)).fetchall()
    return [{"entry_id":entry,"sense_id":sid,"source_order":index+1,"sense_number":number,"definition_fr":definition,
             "sourced_examples":json.loads(examples),"sense_source":{"source_id":source,"source_url":url}}
            for index,(entry,sid,number,definition,examples,source,url) in enumerate(rows)]

def all_senses(conn):
    items=[]
    for lexeme_id in LEXEME_IDS:
        lemma,normalized,pos,hint=conn.execute("SELECT lemma,normalized,pos,gloss_zh FROM lexemes WHERE id=?",(lexeme_id,)).fetchone()
        items.append({"identity":{"stable_lexeme_key":f"{norm(normalized)}|{pos}","runtime_lexeme_id":lexeme_id},
                      "lemma":lemma,"pos":pos,"existing_zh_hint":{"value":hint,"status":"hint_only_not_sense_fact"},
                      "all_senses":sense_rows(conn,lexeme_id),"sourced_family_relations":relations(conn,lexeme_id)})
    return {"schema_version":3,"scope":"All available sourced senses for exactly 20 pilot lexemes; no learner priorities or draft text.","items":items}

def selected_input(senses, selection):
    by_key={x["identity"]["stable_lexeme_key"]:x for x in senses["items"]}
    items=[]
    for choice in selection["items"]:
        key=choice["stable_lexeme_key"]; record=by_key.get(key)
        if not record: raise SystemExit(f"selection lexeme missing: {key}")
        primary=choice["primary_learner_sense"]
        source=next((x for x in record["all_senses"] if x["entry_id"]==primary["entry_id"] and x["sense_id"]==primary["sense_id"]),None)
        if not source: raise SystemExit(f"selection sense missing: {key}")
        items.append({"identity":{**record["identity"],**primary},"selection":choice,
                      "lemma":record["lemma"],"pos":record["pos"],"definition_fr":source["definition_fr"],
                      "sourced_examples":source["sourced_examples"],"sense_source":source["sense_source"],
                      "existing_zh_hint":record["existing_zh_hint"],"relevant_sourced_relations":record["sourced_family_relations"]})
    payload={"schema_version":3,"scope":"Selected-sense facts for the 20-record V3 learner draft; priorities are editorial judgment, not sourced facts.","items":items}
    payload["input_facts_sha256"]=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return payload

def build():
    conn=sqlite3.connect(DB_PATH)
    try: senses=all_senses(conn)
    finally: conn.close()
    selection=json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
    if len(selection.get("items",[]))!=20: raise SystemExit("selection must retain exactly 20 lexemes")
    return senses,selected_input(senses,selection)

if __name__=="__main__":
    senses,payload=build()
    SENSES_PATH.write_text(json.dumps(senses,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    INPUT_PATH.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"lexemes":len(senses["items"]),"selected":len(payload["items"]),"input_facts_sha256":payload["input_facts_sha256"]}))
