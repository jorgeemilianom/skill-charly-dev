#!/usr/bin/env python3
"""Shared word-overlap similarity helper — the same lightweight technique used in three places
across this skill family: the live rule-dedup pre-check (dev-reflect Step 7.2), the cross-ticket
self-model clustering (scripts/self_model.py), and cross-client reuse detection
(skills/manager-status). Deliberately not real semantic matching — just Jaccard overlap on
significant words, cheap and dependency-free. Import, don't re-derive.
"""
import re

STOP = {
    'the', 'a', 'an', 'in', 'on', 'of', 'to', 'and', 'or', 'for', 'with', 'is', 'are', 'be',
    'not', 'it', 'this', 'de', 'la', 'el', 'en', 'y', 'o', 'un', 'una', 'que', 'del', 'al',
    'se', 'con', 'para', 'antes', 'los', 'las', 'lo', 'como', 'no',
    # Generic dev-task verbs/nouns — real noise in short text like ticket summaries: two
    # unrelated tickets sharing only "fix" or "agregar" isn't topical overlap, it's just how
    # tickets are titled. Verified against real Jira data (MSOF) — "Fix imagenes" vs.
    # "fix AgenteIA" matched above threshold on "fix" alone before this list was added.
    'fix', 'bug', 'error', 'add', 'agregar', 'crear', 'create', 'actualizar', 'update',
    'cambiar', 'cambio', 'change', 'mejorar', 'improve', 'nuevo', 'nueva', 'new', 'modulo',
    'module', 'ajustar', 'corregir', 'revisar', 'review', 'implementar', 'implement', 'issue',
    'ticket', 'feature',
}


def words(text):
    """Lowercased, stopword-stripped token set for a piece of text."""
    return set(re.findall(r'[a-zA-Z0-9_áéíóúñ]+', text.lower())) - STOP


def overlap(text_a, text_b):
    """Jaccard word overlap between two texts, 0.0-1.0. Accepts pre-computed word sets too."""
    wa = text_a if isinstance(text_a, set) else words(text_a)
    wb = text_b if isinstance(text_b, set) else words(text_b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)
