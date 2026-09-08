#!/usr/bin/env python3
import json
from build_gapfill_pilot_input import OUT,build
p=json.load(open(OUT)); q=build()
if p!=q: raise SystemExit("input artifact is not deterministic from SQLite and candidate artifact")
if [sum(x["group"]==g for x in p["items"]) for g in "ABC"]!=[10,10,10]: raise SystemExit("groups must each contain 10")
print(json.dumps({"ok":True,"items":30,"semantic_review":"not performed"}))
