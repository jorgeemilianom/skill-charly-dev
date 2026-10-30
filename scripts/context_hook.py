#!/usr/bin/env python3
"""Claude Code hook: inject the compiled memory digest of a repo/client the first time a session
touches it.

Wired in .claude/settings.json for UserPromptSubmit (the prompt names a repo or client — e.g.
"manager AcmeCorp …") and PostToolUse (a Read/Edit/Write/Bash/Grep/Glob call touches
projects/<repo>/… or worktrees/<repo>-…/…). Each scope is injected once per session; the
per-session state lives in the system temp dir and is reset by scripts/session_context.py when the
context is cleared or compacted, so the digest comes back after a /compact.

The digests themselves are memory/compiled/*.md (scripts/memory_compile.py). Never fails or blocks
the session: any error exits 0 with no output.
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MAX_CHARS = 9000  # per hook call, across all newly-touched scopes
PATH_KEYS = ("file_path", "path", "notebook_path", "command")
TOOLS = {"Read", "Edit", "Write", "MultiEdit", "Bash", "Grep", "Glob", "NotebookEdit"}


def state_path(session_id):
    d = os.path.join(tempfile.gettempdir(), f"skill-charly-dev-hooks-{os.getuid()}")
    os.makedirs(d, mode=0o700, exist_ok=True)
    return os.path.join(d, f"{session_id or 'nosession'}.json")


def load_state(sid):
    try:
        return json.load(open(state_path(sid)))
    except Exception:
        return {"injected": []}


def save_state(sid, st):
    p = state_path(sid)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f)
    os.replace(tmp, p)


def reset_state(sid):
    try:
        os.unlink(state_path(sid))
    except OSError:
        pass
    # opportunistic cleanup of week-old session files
    d = os.path.dirname(state_path(sid))
    for f in os.listdir(d):
        p = os.path.join(d, f)
        if time.time() - os.path.getmtime(p) > 7 * 86400:
            try:
                os.unlink(p)
            except OSError:
                pass


def digests_for(text, sid, paths_only=False):
    import memory_compile as mc
    import memory_query as mq

    repos, clients = mq.detect(text, paths_only=paths_only)
    if not repos and not clients:
        return None
    aliases = mq.load_aliases()
    st = load_state(sid)
    done = set(st["injected"])
    scopes = []
    for c in clients:
        if c in repos:  # client named exactly like its repo: the repo digest covers it
            continue
        if f"client:{c}" not in done:
            scopes.append(("client", c))
            done.update(f"repo:{r}" for r in aliases["clients"].get(c, []))  # client digest includes them
            done.add(f"client:{c}")
    for r in repos:
        if f"repo:{r}" not in done:
            scopes.append(("repo", r))
            done.add(f"repo:{r}")
    if not scopes:
        return None
    parts, used = [], 0
    for kind, name in scopes:
        f = os.path.join(mc.OUT, f"{kind}-{mc.safe_name(name)}.md")
        try:
            content = open(f, encoding="utf-8").read().strip()
        except OSError:
            continue
        if used + len(content) > MAX_CHARS:
            content = content[: max(0, MAX_CHARS - used)].rsplit("\n", 1)[0] + "\n_(recortado)_"
        parts.append(content)
        used += len(content)
        if used >= MAX_CHARS:
            break
    st["injected"] = sorted(done)
    save_state(sid, st)
    try:  # the agent's own experiences/goals/predictions for the same scope (memory/cognition.json)
        import cognition
        new_repos = [n for k, n in scopes if k == "repo"]
        new_clients = [n for k, n in scopes if k == "client"]
        cog = cognition.scoped_digest(new_repos, new_clients, budget=max(0, min(1800, MAX_CHARS + 1800 - used)))
        if cog:
            parts.append("### Estado propio de Charly en este alcance\n" + cog)
    except Exception:
        pass
    if not parts:
        return None
    return ("[harness skill-charly-dev] Primera vez que esta sesión toca este alcance — memoria "
            "relevante (aplicar las reglas; las de conf ≥ 0.8 son el enfoque por defecto):\n\n"
            + "\n\n".join(parts))


def main():
    data = json.load(sys.stdin)
    event = data.get("hook_event_name")
    sid = data.get("session_id")
    if event == "UserPromptSubmit":
        text = data.get("prompt") or ""
    elif event == "PostToolUse":
        if data.get("tool_name") not in TOOLS:
            return
        ti = data.get("tool_input") or {}
        # only paths and commands count — not edited content (old_string/new_string/content) nor a
        # Grep pattern, where mentioning a repo or client name is not "touching" it
        text = "\n".join(str(ti[k]) for k in PATH_KEYS if ti.get(k))
        if "projects/" not in text and "worktrees/" not in text and "Business/" not in text:
            return
    else:
        return
    ctx = digests_for(text, sid, paths_only=(event == "PostToolUse"))
    if ctx:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": ctx}},
                         ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
