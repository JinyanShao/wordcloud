#!/usr/bin/env python3
"""Structural validator only; it does not judge Chinese semantic correctness."""
import json
from pathlib import Path
from build_dbnary_zh_translation_candidates import OUT, build
def main():
 actual=json.loads(OUT.read_text()); expected=build()
 if actual!=expected: raise SystemExit("candidate artifact is not a deterministic projection of the pinned source")
 for x in actual["items"]:
  if x["candidate_class"]=="sense_mapped_candidate" and not (x["entry_id"] and x["mapped_sense_id"]): raise SystemExit("invalid sense-mapped candidate")
  if x["enhanced_sense_links"] or x["enhanced_source_version"] is not None: raise SystemExit("unexpected enhanced data")
 print(json.dumps({"ok":True,"candidates":len(actual["items"]),"semantic_review":"required"}))
if __name__=="__main__": main()
