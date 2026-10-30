#!/usr/bin/env python3
"""One-shot, idempotent upgrade of memory/ to the current schema. Safe to re-run.

  - global_rules: unique ids (duplicates renamed to the next free <TICKET>-r<n>, superseded_by
    references re-pointed to the most similar entry), rounded confidences, created_at/last_seen.
  - patterns / mistakes: created_at (+ last_seen) backfilled; legacy `mistake` field -> description.
  - Dates are backfilled from the origin ticket's snapshot (snapshot_date), else the mtime of its
    assessment/ticket file; left out when nothing is known (the ranking treats that as "old-ish").

Takes a backup first. Usage: python3 scripts/memory_migrate.py [--dry-run]
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memory_store as ms  # noqa: E402
from text_similarity import overlap  # noqa: E402


def ticket_date(ticket, cache={}):
    if not ticket:
        return None
    if ticket in cache:
        return cache[ticket]
    date = None
    try:
        snap = json.load(open(os.path.join(ms.MEM, "snapshots", f"{ticket}.json")))
        date = (snap.get("snapshot_date") or "")[:10] or None
    except Exception:
        pass
    if not date:
        for sub in ("assessments", "tickets"):
            p = os.path.join(ms.MEM, sub, f"{ticket}.json")
            if os.path.exists(p):
                date = datetime.date.fromtimestamp(os.path.getmtime(p)).isoformat()
                break
    cache[ticket] = date
    return date


def migrate_rules(d, log):
    rules = d["rules"]
    seen, renamed = set(), {}
    for r in rules:
        if r["id"] in seen:
            ticket = r.get("origin_ticket") or r["id"].rsplit("-r", 1)[0]
            new = ms.next_rule_id(rules + [{"id": x} for x in seen], ticket)
            log.append(f"id duplicado {r['id']} -> {new}")
            renamed.setdefault(r["id"], []).append((new, r))
            r["id"] = new
        seen.add(r["id"])
    # re-point ambiguous superseded_by to whichever same-id candidate reads closest
    for r in rules:
        old = r.get("superseded_by")
        if old in renamed:
            cands = [(old, next(x for x in rules if x["id"] == old))] + renamed[old]
            best = max(cands, key=lambda c: overlap(r["rule"], c[1]["rule"]))
            if best[0] != old:
                log.append(f"superseded_by de {r['id']}: {old} -> {best[0]}")
                r["superseded_by"] = best[0]
    for r in rules:
        r["confidence"] = round(float(r["confidence"]), 2)
        if "created_at" not in r:
            date = ticket_date(r.get("origin_ticket"))
            if date:
                r["created_at"] = date
        if "last_seen" not in r and r.get("created_at"):
            later = [ticket_date(t) for t in r.get("reinforced_by", [])]
            r["last_seen"] = max([x for x in later if x] + [r["created_at"]])


def migrate_patterns(d, log):
    for p in d["patterns"]:
        p["confidence"] = round(float(p["confidence"]), 2)
        if "created_at" not in p:
            dates = sorted(x for x in (ticket_date(t) for t in p.get("origin_tickets", [])) if x)
            if dates:
                p["created_at"], p["last_seen"] = dates[0], dates[-1]


def migrate_mistakes(d, log):
    for m in d["mistakes"]:
        if "description" not in m and "mistake" in m:
            m["description"] = m.pop("mistake")
            log.append(f"mistake {m['ticket']}: campo 'mistake' -> 'description'")
        m.setdefault("context", "")
        if "date" not in m:
            date = ticket_date(m.get("ticket"))
            if date:
                m["date"] = date


def main():
    dry = "--dry-run" in sys.argv
    if not dry:
        print(ms.backup())
    log = []
    for name, fn in (("global_rules.json", migrate_rules), ("patterns.json", migrate_patterns),
                     ("mistakes.json", migrate_mistakes)):
        if dry:
            data = ms.read_json(name)
            fn(data, log)
            ms.validate(name, data)
        else:
            ms.update_json(name, lambda data, fn=fn: fn(data, log), compile_after=False)
    print("\n".join(log) or "sin cambios estructurales")
    if not dry:
        ms.recompile()
    print("dry-run OK" if dry else "migración aplicada")


if __name__ == "__main__":
    main()
