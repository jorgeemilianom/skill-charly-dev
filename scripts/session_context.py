#!/usr/bin/env python3
"""SessionStart hook: injects a compact digest of the harness memory into Claude Code's context.

Claude Code auto-loads CLAUDE.md, but not memory/ — so without this, user preferences and
cross-ticket rules only reach the agent when a /m-dev* skill happens to read them. Prints to stdout
(Claude Code adds it to the session context; Codex runs it by hand, step 3 of agent-context.md):
  - user_profile.json: communication prefs, workflow notes
  - cognition.json (scripts/cognition.py): the agent's identity, blind spots, pending predictions,
    open goals, relevant evaluated experiences and the read-only `tick` proposals
  - global_rules.json: universal active rules with confidence ≥ 0.8
  - the compiled digest of the repo the session starts in, if any (memory/compiled/)
  - warnings: a memory file that no longer parses, a consolidation pass overdue
Side effects, all best-effort: a daily backup of memory/ (memory/.backups/, rotated) and a reset of
scripts/context_hook.py's per-session state on startup/clear/compact, so repo digests get
re-injected after the context is lost. Never fails the session.
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(ROOT, "memory")
MAX_NOTE = 220  # chars per free-text note — the digest must stay small, it loads every session
CONSOLIDATE_EVERY_DAYS = 14


def hook_input():
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def load(name):
    try:
        with open(os.path.join(MEM, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def clip(text):
    text = " ".join(str(text).split())
    return text if len(text) <= MAX_NOTE else text[: MAX_NOTE - 1] + "…"


def side_effects(inp):
    try:
        import context_hook
        if inp.get("source") in (None, "startup", "clear", "compact"):
            context_hook.reset_state(inp.get("session_id"))
    except Exception:
        pass
    try:
        import memory_store
        memory_store.backup(if_older_than_hours=20, quiet=True)
    except Exception:
        pass


def warnings():
    out = []
    for name in ("global_rules.json", "patterns.json", "decisions.json", "mistakes.json", "user_profile.json"):
        p = os.path.join(MEM, name)
        if os.path.exists(p) and load(name) is None and os.access(p, os.R_OK):
            out.append(f"⚠ memory/{name} no parsea — no escribir en él; avisar al usuario y restaurar desde memory/.backups/")
    last = load("consolidation/last.json") or {}
    try:
        age = (datetime.date.today() - datetime.date.fromisoformat(last.get("date", "")[:10])).days
    except ValueError:
        age = None
    if age is None or age > CONSOLIDATE_EVERY_DAYS:
        when = "nunca" if age is None else f"hace {age} días"
        out.append(f"Consolidación de memoria pendiente (última: {when}) — ofrecer `/m-memory consolidate` "
                   f"al usuario si la sesión es de mantenimiento del harness, no interrumpir otra tarea.")
    return out


def cwd_digest(inp):
    cwd = inp.get("cwd") or os.getcwd()
    if "/projects/" not in cwd and "/worktrees/" not in cwd:
        return None
    try:
        import context_hook
        return context_hook.digests_for(cwd, inp.get("session_id"))
    except Exception:
        return None


def main():
    inp = hook_input()
    side_effects(inp)
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

    # The agent's own model (identity, blind spots, pending predictions, open goals, lessons) comes
    # from memory/cognition.json; before it exists, cognition.py falls back to the legacy
    # user_profile.self_model read-only. Once migrated, cognition.json takes precedence.
    try:
        import cognition
        cog = cognition.session_digest(budget=1800)
    except Exception:
        cog = ""

    rules = (load("global_rules.json") or {}).get("rules") or []
    active_universal = [
        r for r in rules
        if isinstance(r, dict) and not r.get("tags") and r.get("status", "active") == "active"
    ]
    strong = [r for r in active_universal if r.get("confidence", 0) >= 0.8]
    if strong:
        out.append("Reglas universales activas (confidence ≥ 0.8, de memory/global_rules.json):")
        out += [f"- {clip(r.get('rule', ''))}" for r in strong]
    rest = len(active_universal) - len(strong)
    out.append(
        "Memoria por repo/cliente: se inyecta sola la primera vez que la sesión toca projects/<repo> o "
        "nombra un cliente (memory/compiled/). Consulta a demanda: "
        "`python3 scripts/memory_query.py --repos <repo> [--clients X] [--text \"<tarea>\"]`"
        + (f"; hay {rest} reglas universales más de menor confianza en memory/compiled/universal.md." if rest else ".")
        + " Escrituras a memory/ solo vía `python3 scripts/memory_store.py` (nunca jq > archivo)."
    )
    out += warnings()

    print("[harness skill-charly-dev] Digest de memory/ (generado por scripts/session_context.py):")
    print("\n".join(out))
    if cog:
        print("\n" + cog)
    d = cwd_digest(inp)
    if d:
        print("\n" + d)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
