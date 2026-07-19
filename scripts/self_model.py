#!/usr/bin/env python3
"""Recompute this project's self-model: the recurring blind spots worth acting on proactively,
not just recording. Prints a JSON list to stdout; the caller merges it into
memory/user_profile.json under "self_model" (see dev-reflect Step 2.5).

Why this exists: memory/global_rules.json, patterns.json, and decisions.json each record
learnings independently, keyed to whichever ticket produced them. Nothing cross-references them,
so the same underlying lesson gets rediscovered from scratch in a later ticket instead of being
recognized as "this again" — see MSOF-171 and MSOF-134 both independently landing on "type
dynamic backend data as `any`, not `unknown`" as if for the first time.

This clusters entries across the three files by word overlap (the same technique as the live
rule-dedup pre-check in dev-reflect Step 7.2 — kept deliberately simple, not real semantic
matching) and keeps only clusters backed by 2+ *distinct* tickets. Same-ticket duplicates (a rule
and a pattern written from the same closing session) do NOT count as recurrence on their own —
patterns.json doesn't record which ticket(s) produced an entry (see origin_tickets below), so
single-ticket clusters are common and are deliberately excluded to avoid inflating the signal.

Usage: python3 scripts/self_model.py <path-to-memory-dir>
"""
import json
import os
import re
import sys
from itertools import combinations

STOP = {
    'the', 'a', 'an', 'in', 'on', 'of', 'to', 'and', 'or', 'for', 'with', 'is', 'are', 'be',
    'not', 'it', 'this', 'de', 'la', 'el', 'en', 'y', 'o', 'un', 'una', 'que', 'del', 'al',
    'se', 'con', 'para', 'antes', 'los', 'las', 'lo', 'como', 'no',
}

CLUSTER_THRESHOLD = 0.20  # looser than the live dedup pre-check's 0.25 — retrospective, not a
                          # live accept/reject decision, so a few false groupings are cheap to
                          # eyeball and discard; false negatives (missing a real recurrence)
                          # are the costlier failure mode here.
MIN_DISTINCT_TICKETS = 2  # only surface clusters with real cross-ticket recurrence
TOP_N = 3


def words(text):
    return set(re.findall(r'[a-zA-Z0-9_áéíóúñ]+', text.lower())) - STOP


def load(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def main():
    mem = sys.argv[1] if len(sys.argv) > 1 else 'memory'
    entries = []

    rules = load(os.path.join(mem, 'global_rules.json'), {'rules': []})
    for r in rules.get('rules', []):
        if r.get('status') == 'active':
            entries.append({
                'text': r['rule'], 'source': 'rule', 'ref': r.get('id'),
                'tickets': {r['origin_ticket']} if r.get('origin_ticket') else set(),
            })

    patterns = load(os.path.join(mem, 'patterns.json'), {'patterns': []})
    for p in patterns.get('patterns', []):
        # origin_tickets is optional — older entries predate this field (see dev-reflect Step 4)
        entries.append({
            'text': p['pattern'], 'source': 'pattern', 'ref': p.get('type'),
            'tickets': set(p.get('origin_tickets', [])),
        })

    decisions = load(os.path.join(mem, 'decisions.json'), {'decisions': []})
    for d in decisions.get('decisions', []):
        if d.get('outcome') in ('partial', 'failure'):
            entries.append({
                'text': d['decision'], 'source': 'decision', 'ref': d.get('outcome'),
                'tickets': {d['context']} if d.get('context') else set(),
            })

    n = len(entries)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    word_sets = [words(e['text']) for e in entries]
    for i, j in combinations(range(n), 2):
        wi, wj = word_sets[i], word_sets[j]
        if not wi or not wj:
            continue
        overlap = len(wi & wj) / len(wi | wj)
        if overlap >= CLUSTER_THRESHOLD:
            union(i, j)

    clusters = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(entries[i])

    scored = []
    for cluster in clusters.values():
        if len(cluster) < 2:
            continue
        distinct_tickets = set()
        for e in cluster:
            distinct_tickets |= e['tickets']
        if len(distinct_tickets) < MIN_DISTINCT_TICKETS:
            continue
        rep = max(cluster, key=lambda e: len(e['text']))
        scored.append({
            'statement': rep['text'],
            'distinct_tickets': sorted(distinct_tickets),
            'recorded_count': len(cluster),
            'sources': sorted({f"{e['source']}:{e['ref']}" for e in cluster if e['ref']}),
        })

    scored.sort(key=lambda c: (len(c['distinct_tickets']), c['recorded_count']), reverse=True)
    return scored[:TOP_N]


if __name__ == '__main__':
    print(json.dumps(main(), indent=2, ensure_ascii=False))
