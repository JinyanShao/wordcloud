#!/usr/bin/env python3
"""Structural validator only; it does not judge Chinese semantic correctness."""
import hashlib, json
from build_dbnary_zh_translation_candidates import OUT
def main():
 raw=OUT.read_bytes(); actual=json.loads(raw)
 if actual.get("schema_version")!=1: raise SystemExit("invalid candidate artifact schema")
 for x in actual["items"]:
  if x["candidate_class"]=="sense_mapped_candidate" and not (x["entry_id"] and x["mapped_sense_id"]): raise SystemExit("invalid sense-mapped candidate")
  if x["enhanced_sense_links"] or x["enhanced_source_version"] is not None: raise SystemExit("unexpected enhanced data")
  if x["learner_language_eligibility"] not in {"default_learner_chinese","nondefault_chinese_variant"}: raise SystemExit("invalid learner language policy")
 print(json.dumps({"ok":True,"candidates":len(actual["items"]),"artifact_sha256":hashlib.sha256(raw).hexdigest(),"semantic_review":"required"}))
if __name__=="__main__": main()
