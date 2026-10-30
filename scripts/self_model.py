#!/usr/bin/env python3
"""Recompute this project's self-model: the recurring blind spots worth acting on proactively,
not just recording. Prints a JSON list to stdout; the caller merges it into
memory/user_profile.json under "self_model" (see dev-reflect Step 2.5).

Why this exists: memory/global_rules.json, patterns.json, and decisions.json each record
learnings independently, keyed to whichever ticket produced them. Nothing cross-references them,
so the same underlying lesson gets rediscovered from scratch in a later ticket instead of being
recognized as "this again" — e.g. two unrelated tickets (PROJ-171 and PROJ-134) both independently
landing on "type dynamic backend data as `any`, not `unknown`" as if for the first time.

This clusters entries across the three files by word overlap (the same technique as the live
rule-dedup pre-check in dev-reflect Step 7.2 — kept deliberately simple, not real semantic
matching) and keeps only clusters backed by 2+ *distinct* tickets. Same-ticket duplicates (a rule
and a pattern written from the same closing session) do NOT count as recurrence on their own —
patterns.json doesn't record which ticket(s) produced an entry (see origin_tickets below), so
single-ticket clusters are common and are deliberately excluded to avoid inflating the signal.

Usage:
  python3 scripts/self_model.py <path-to-memory-dir>   # historic query: print the list, write nothing
  python3 scripts/self_model.py --refresh              # recompute and store it as the agent's own
                                                       # blind spots in memory/cognition.json
--refresh reads strictly: if any source file exists but doesn't parse, it exits 2 and writes nothing
— a read failure must never replace the stored model with an empty list. The legacy copy in
user_profile.json's self_model is left as it was (read-only history).
"""
import json
import os
import sys
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from text_similarity import words, overlap as word_overlap  # noqa: E402

CLUSTER_THRESHOLD = 0.20  # looser than the live dedup pre-check's 0.25 — retrospective, not a
                          # live accept/reject decision, so a few false groupings are cheap to
                          # eyeball and discard; false negatives (missing a real recurrence)
                          # are the costlier failure mode here.
MIN_DISTINCT_TICKETS = 2  # only surface clusters with real cross-ticket recurrence
TOP_N = 3


STRICT = False


def load(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        if STRICT:
            raise
        return default


def main(mem=None):
    mem = mem or (sys.argv[1] if len(sys.argv) > 1 else 'memory')
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
        if word_overlap(word_sets[i], word_sets[j]) >= CLUSTER_THRESHOLD:
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


def refresh():
    global STRICT
    import datetime
    import memory_store as ms
    STRICT = True
    try:
        spots = main(ms.MEM)
    except Exception as e:
        print(json.dumps({"ok": False, "kind": "read_error",
                          "error": f"no se pudo leer la memoria ({e}); el modelo guardado no se toca"}, ensure_ascii=False))
        sys.exit(2)
    computed_at = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    try:
        result = ms.cognitive("set-blind-spots", {"blind_spots": spots, "computed_at": computed_at})
    except (ms.MemoryCorrupt, ms.cm.IncompatibleSchema) as e:
        print(json.dumps({"ok": False, "kind": "corrupt", "error": str(e)}, ensure_ascii=False))
        sys.exit(2)
    print(json.dumps({"ok": True, "result": result, "blind_spots": spots}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    if '--refresh' in sys.argv[1:]:
        refresh()
    else:
        print(json.dumps(main(), indent=2, ensure_ascii=False))
