#!/usr/bin/env python3
"""Prepare a memory consolidation pass: the deterministic half of /m-memory consolidate.

Word-overlap dedup (memory_store.py similar-rules) can't see a Spanish paraphrase of an English
rule, and nothing ever retired a stale rule — so memory only grows. This script finds the
candidates; the agent (skills/m-memory/SKILL.md) judges them and applies the outcome through
memory_store.py, which keeps every change reversible (supersede/archive set a status, never delete).

Report sections (JSON on stdout, or --md for a readable version):
  review_groups   active rules grouped by scope (same tag set / universal) — the agent reads each
                  group whole to spot semantic duplicates across languages
  lexical_pairs   pairs above a word-overlap threshold, a head start for the above
  stale           retrospective, never reinforced, confidence < 0.7, older than --stale-days → archive?
  promote         confidence ≥ 0.9, live correction or reinforced, scoped to exactly one repo that has
                  its own CLAUDE.md → propose moving it into that repo's docs (needs the user's OK)
  orphan_tags     tags that match no repo, client, alias or topic → never retrieved by scope

Usage:
  python3 scripts/memory_consolidate.py [--md] [--stale-days 180]
  python3 scripts/memory_consolidate.py --mark-done "<one-line summary>"
"""
import argparse
import collections
import datetime
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memory_compile as mc  # noqa: E402
import memory_query as mq  # noqa: E402
import memory_store as ms  # noqa: E402
from text_similarity import words  # noqa: E402


def pair_score(a, b):
    wa, wb = words(a), words(b)
    inter = len(wa & wb)
    if not inter:
        return 0
    return max(inter / len(wa | wb), 0.8 * inter / min(len(wa), len(wb)))


def build(stale_days):
    rules = ms.read_json("global_rules.json")["rules"]
    active = [r for r in rules if r["status"] == "active"]
    aliases = mq.load_aliases()
    repos = mq.known_repos()

    groups = collections.defaultdict(list)
    for r in active:
        groups[",".join(sorted(r.get("tags") or [])) or "(universal)"].append(
            {"id": r["id"], "conf": r["confidence"], "rule": r["rule"]})

    pairs = []
    for a, b in itertools.combinations(active, 2):
        if a.get("tags") and b.get("tags") and not set(a["tags"]) & set(b["tags"]):
            continue
        s = pair_score(a["rule"], b["rule"])
        if s >= 0.3:
            pairs.append({"score": round(s, 2), "a": a["id"], "b": b["id"]})
    pairs.sort(key=lambda p: -p["score"])

    today = datetime.date.today()
    stale = []
    for r in active:
        if r.get("source") != "retrospective" or r.get("reinforced_count") or r["confidence"] >= 0.7:
            continue
        seen = r.get("last_seen") or r.get("created_at")
        age = (today - datetime.date.fromisoformat(seen[:10])).days if seen else None
        if age is not None and age > stale_days:
            stale.append({"id": r["id"], "age_days": age, "conf": r["confidence"], "rule": r["rule"]})

    promote = []
    for r in active:
        tags = r.get("tags") or []
        if r["confidence"] < 0.9 or not (r.get("source") == "live_correction" or r.get("reinforced_count")):
            continue
        repo_tags = [t for t in tags if t in repos]
        if len(repo_tags) != 1:
            continue
        d = mc.repo_dir(repo_tags[0])
        if d and os.path.isfile(os.path.join(d, "CLAUDE.md")):
            promote.append({"id": r["id"], "repo": repo_tags[0],
                            "target": os.path.relpath(os.path.join(d, "CLAUDE.md"), ms.ROOT), "rule": r["rule"]})

    known = set(repos) | set(aliases["clients"]) | set(aliases["repo_aliases"]) | set(aliases["topics"])
    orphan = collections.Counter()
    for kind, f in mq.FILES.items():
        for e in ms.read_json(f)[kind]:
            for t in e.get("tags") or []:
                if t not in known:
                    orphan[t] += 1

    return {
        "date": today.isoformat(),
        "totals": {"active_rules": len(active), "groups": len(groups)},
        "review_groups": dict(sorted(groups.items(), key=lambda g: -len(g[1]))),
        "lexical_pairs": pairs[:40],
        "stale": stale,
        "promote": promote,
        "orphan_tags": dict(orphan),
    }


def to_md(rep):
    out = [f"# Consolidación de memoria — {rep['date']}",
           f"{rep['totals']['active_rules']} reglas activas en {rep['totals']['groups']} grupos de alcance.", ""]
    out.append("## Pares con solapamiento léxico (revisar primero)")
    out += [f"- {p['score']:.0%}: {p['a']} ↔ {p['b']}" for p in rep["lexical_pairs"]] or ["- (ninguno)"]
    out.append("\n## Candidatas a archivar (retrospectivas, sin refuerzo, viejas)")
    out += [f"- {s['id']} ({s['age_days']} días, conf {s['conf']}): {s['rule'][:160]}" for s in rep["stale"]] or ["- (ninguna)"]
    out.append("\n## Candidatas a promover al CLAUDE.md del repo")
    out += [f"- {p['id']} → {p['target']}: {p['rule'][:160]}" for p in rep["promote"]] or ["- (ninguna)"]
    out.append("\n## Tags huérfanos (ningún repo/cliente/alias/tema los matchea)")
    out += [f"- {t}: {n} entradas" for t, n in rep["orphan_tags"].items()] or ["- (ninguno)"]
    out.append("\n## Grupos para revisión semántica")
    for scope, items in rep["review_groups"].items():
        out.append(f"\n### {scope} ({len(items)})")
        out += [f"- [{i['id']} · {i['conf']}] {i['rule']}" for i in items]
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--md", action="store_true")
    p.add_argument("--stale-days", type=int, default=180)
    p.add_argument("--mark-done", metavar="SUMMARY")
    a = p.parse_args()
    if a.mark_done is not None:
        with ms.locked():
            ms.write_json_atomic("consolidation/last.json", {"date": datetime.date.today().isoformat(), "summary": a.mark_done})
        print("consolidación registrada")
        return
    rep = build(a.stale_days)
    print(to_md(rep) if a.md else json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
