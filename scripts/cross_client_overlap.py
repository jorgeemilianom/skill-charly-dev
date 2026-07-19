#!/usr/bin/env python3
"""Detect candidate cross-client feature reuse: the same kind of ask showing up for 2+ different
clients, worth flagging as "maybe build this once as a shared CloudHubCorp module" instead of
bespoke work per client (several MSoftIA clients — NorteMed, Grupo T Seguros, iBender, QuintaApp
— already run as modules/bots inside the same CloudHubCorp multi-tenant framework).

Reads {"<cliente>": ["<ticket summary>", ...], ...} as JSON on stdin — the caller (manager-status's
multi-client overview) is responsible for fetching each client's recent ticket summaries; this
script only does the pure text comparison, same word-overlap technique as
scripts/self_model.py and the live rule-dedup pre-check (dev-reflect Step 7.2). Only compares
summaries belonging to *different* clients — overlap within one client's own tickets isn't reuse.

Usage: echo '{"ClientA": ["..."], "ClientB": ["..."]}' | python3 scripts/cross_client_overlap.py
"""
import json
import os
import sys
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from text_similarity import words, overlap as word_overlap  # noqa: E402

THRESHOLD = 0.34  # higher than self_model.py's 0.20 — ticket summaries are short (often 3-5
                  # significant words), so a single shared generic word inflates Jaccard fast;
                  # verified against real MSOF data, see text_similarity.py's stopword comment
TOP_N = 3


def main():
    data = json.load(sys.stdin)

    entries = []
    for client, summaries in data.items():
        for text in summaries:
            entries.append({'client': client, 'text': text, 'words': words(text)})

    matches = []
    for a, b in combinations(entries, 2):
        if a['client'] == b['client']:
            continue
        score = word_overlap(a['words'], b['words'])
        if score >= THRESHOLD:
            matches.append({
                'overlap': round(score, 2),
                'clients': sorted([a['client'], b['client']]),
                'tickets': {a['client']: a['text'], b['client']: b['text']},
            })

    matches.sort(key=lambda m: m['overlap'], reverse=True)
    return matches[:TOP_N]


if __name__ == '__main__':
    print(json.dumps(main(), indent=2, ensure_ascii=False))
