#!/usr/bin/env python3
"""SessionStart hook: injects a compact digest of the harness memory into Claude Code's context.

Claude Code auto-loads CLAUDE.md, but not memory/ — so without this, user preferences and
cross-ticket rules only reach the agent when a /m-dev* skill happens to read them. Reads
memory/user_profile.json and memory/global_rules.json (both gitignored, may be absent) and prints a
short summary to stdout, which Claude Code adds to the session context. Never fails the session:
any missing/malformed file is silently skipped.
"""
import json
import os
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(ROOT, "memory")
MAX_NOTE = 220  # chars per free-text note — the digest must stay small, it loads every session


def load(name):
    try:
        with open(os.path.join(MEM, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def clip(text):
    text = " ".join(str(text).split())
    return text if len(text) <= MAX_NOTE else text[: MAX_NOTE - 1] + "…"


def main():
    out = []
    profile = load("user_profile.json") or {}

    comm = profile.get("communication") or {}
    prefs = {k: v for k, v in comm.items() if k != "notable_phrases"}
    if prefs:
        out.append("Preferencias de comunicación: " + ", ".join(f"{k}={v}" for k, v in prefs.items()))

    notes = profile.get("workflow_notes") or {}
    if notes:
        out.append("Notas de workflow del usuario:")
        out += [f"- {k}: {clip(v)}" for k, v in notes.items()]

    spots = (profile.get("self_model") or {}).get("top_blind_spots") or []
    if spots:
        out.append("Puntos ciegos recurrentes del agente (evitarlos):")
        out += [f"- {clip(s.get('statement', ''))}" for s in spots if s.get("statement")]

    rules = (load("global_rules.json") or {}).get("rules") or []
    universal = [
        r for r in rules
        if isinstance(r, dict) and not r.get("tags")
        and r.get("status", "active") == "active" and r.get("confidence", 0) >= 0.8
    ]
    if universal:
        out.append("Reglas universales activas (confidence ≥ 0.8, de memory/global_rules.json):")
        out += [f"- {clip(r.get('rule', ''))}" for r in universal]

    if out:
        print("[harness skill-charly-dev] Digest de memory/ (generado por scripts/session_context.py):")
        print("\n".join(out))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
