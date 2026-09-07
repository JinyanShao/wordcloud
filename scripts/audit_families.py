#!/usr/bin/env python3
"""Reproducible coverage audit of source-labelled derivation relations, not human review."""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from runtime_graph import ROOT, load_runtime, UnionFind


def audit(runtime):
    nodes = {n[0]: n for n in runtime['nodes']}
    edges = [e for e in runtime['official_edges'] if e[2] == 'fam' and e[9] == 'sourced' and e[3] == 'derivational_morphology']
    ids = sorted({v for e in edges for v in e[:2]})
    uf = UnionFind(ids)
    for e in edges:
        assert e[0] in nodes and e[1] in nodes
        uf.union(e[0], e[1])
    groups = defaultdict(list)
    has_senses = lambda i: any(g.get('senses') for g in runtime['senses'].get(str(i), []))
    for i in ids:
        groups[uf.find(i)].append(i)
    patterns = Counter()
    for e in edges:
        direction = e[5].split('->')
        if not e[5]:
            patterns[(e[4], e[6], 'undirected', 'undirected')] += 1
            continue
        assert len(direction) == 2 and {int(v) for v in direction} == set(e[:2]), f'Invalid direction: {e}'
        a, b = map(int, direction)
        patterns[(e[4], e[6], nodes[a][2], nodes[b][2])] += 1
    return {
        'basis': 'Committed sourced derivational_morphology edges; connected groups are partial families, not exhaustive linguistic families.',
        'runtime_sha256': hashlib.sha256((ROOT/'graph-data.js').read_bytes()).hexdigest(),
        'rendered_words': len(nodes), 'sourced_derivation_edges': len(edges),
        'family_words': len(ids), 'partial_families': len(groups),
        'family_words_with_french_senses': sum(has_senses(i) for i in ids),
        'family_words_with_chinese_hint': sum(bool(nodes[i][4]) for i in ids),
        'families_with_all_members_defined': sum(all(has_senses(i) for i in g) for g in groups.values()),
        'largest_family': max(map(len, groups.values()), default=0),
        'by_construction': dict(Counter(e[4] for e in edges)),
        'patterns': [dict(construction=k[0],label=k[1],from_pos=k[2],to_pos=k[3],pairs=v) for k,v in sorted(patterns.items(),key=lambda x:(-x[1],x[0]))],
        'missing_basic_words': [w for w in ['école','bonjour','avoir','maison','chat'] if not any(n[1]==w for n in nodes.values())],
    }

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    result=audit(load_runtime());path=ROOT/'data/family-summary.json'
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.check:
        assert path.read_text()==text, 'Family audit is stale; run python3 scripts/audit_families.py'
    else:
        path.write_text(text)
    print(json.dumps({k:v for k,v in result.items() if k!='patterns'},ensure_ascii=False))
