#!/usr/bin/env python3
"""Apply external semantic selection decisions to the frozen Phase 2C input."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'data/learner-content-100-review-input.json'
OUT=ROOT/'data/learner-content-100-selection-reviewed.json'
OVERRIDES={
'monde|NOM':('monde__nom__1','__ws_5_monde__nom__1'),'vie|NOM':('vie__nom__1','__ws_3_vie__nom__1'),'faire|VER':('faire__verb__1','__ws_4_faire__verb__1'),'devoir|VER':('devoir__verb__1','__ws_2_devoir__verb__1'),'économique|ADJ':('économique__adj__1','__ws_3_économique__adj__1'),'inquiet|ADJ':('inquiet__adj__1','__ws_2_inquiet__adj__1'),'cependant|ADV':('cependant__adv__1','__ws_2_cependant__adv__1'),'point|NOM':('point__nom__1','__ws_7_point__nom__1'),'corps|NOM':('corps__nom__1','__ws_2_corps__nom__1'),'emploi|NOM':('emploi__nom__1','__ws_6_emploi__nom__1'),'développer|VER':('développer__verb__1','__ws_3_développer__verb__1'),'étonner|VER':('étonner__verb__1','__ws_2_étonner__verb__1'),'rapport|NOM':('rapport__nom__1','__ws_3_rapport__nom__1'),'chef|NOM':('chef__nom__2','__ws_1_chef__nom__2'),'paraître|VER':('paraître__verb__1','__ws_4_paraître__verb__1'),'assurer|VER':('assurer__verb__1','__ws_3_assurer__verb__1'),'terme|NOM':('terme__nom__2','__ws_1_terme__nom__2'),'antenne|NOM':('antenne__nom__1','__ws_6_antenne__nom__1')}
SECONDARY={'vie|NOM':('vie__nom__1','__ws_7_vie__nom__1'),'faire|VER':('faire__verb__1','__ws_1_faire__verb__1'),'devoir|VER':('devoir__verb__1','__ws_1_devoir__verb__1'),'heure|NOM':('heure__nom__1','__ws_6_heure__nom__1'),'temps|NOM':('temps__nom__1','__ws_16_temps__nom__1'),'maison|NOM':('maison__nom__1','__ws_2_maison__nom__1'),'sûr|ADJ':('sûr__adj__1','__ws_4_sûr__adj__1'),'français|ADJ':('français__adj__1','__ws_2_français__adj__1')}
BLOCKED='travers|NOM'
def canon(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def build():
 p=json.loads(INPUT.read_text()); items=[]
 for record in p['items']:
  key=record['stable_lexeme_key']; senses={(s['entry_id'],s['sense_id']):s for s in record['all_source_senses']}
  if key==BLOCKED:
   items.append({'stable_lexeme_key':key,'runtime_lexeme_id':record['runtime_lexeme_id'],'selection_status':'blocked','selection_reason':'Standalone noun senses do not provide a clean learner-primary sense; the learner-relevant use is mainly multiword à travers.','primary_learner_sense':None,'secondary_learner_senses':[]}); continue
  selected=OVERRIDES.get(key,(record['proposed_primary_learner_sense']['entry_id'],record['proposed_primary_learner_sense']['sense_id']))
  if selected not in senses: raise SystemExit(f'unknown selected sense {key}')
  second=[]
  if key in SECONDARY:
   sec=SECONDARY[key]
   if sec not in senses: raise SystemExit(f'unknown secondary {key}')
   second=[{'entry_id':sec[0],'sense_id':sec[1]}]
  row={'stable_lexeme_key':key,'runtime_lexeme_id':record['runtime_lexeme_id'],'selection_status':'reviewed','selection_reason':'external_semantic_override' if key in OVERRIDES else 'external_review_accepted_phase2c_proposal','primary_learner_sense':{'entry_id':selected[0],'sense_id':selected[1]},'secondary_learner_senses':second}
  if key=='antenne|NOM': row['semantic_translation_binding_note']='External semantic review aligns the sourced DBnary 天线 record to this selected SQLite sense; its structural mapped_sense_id is stale and is not rewritten.'
  items.append(row)
 result={'schema_version':1,'scope':'Authoritative external semantic selection for the frozen Phase 2C 100-lexeme set. Selection review is distinct from learner-text review.','base_input_artifact_hash':p['artifact_hash'],'items':items}; result['artifact_hash']=hashlib.sha256(canon(result).encode()).hexdigest(); return result
if __name__=='__main__': OUT.write_text(json.dumps(build(),ensure_ascii=False,indent=2)+'\n')
