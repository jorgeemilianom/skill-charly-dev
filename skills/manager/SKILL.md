---
name: manager
description: "Business-layer orchestrator — never touches code, branches, Jira tickets or PRs. Routes requests about Business/<cliente> (client context, scripts, credentials, confidential info) to manager-create or manager-update, or lists known clients on a bare call. Use for 'manager <cliente>', 'manager create <cliente>', 'manager update <cliente>', or plain 'manager'."
allowed-tools: Bash Read Write
---

# Manager — Business Context Orchestrator

Execute the business-layer request for: **$ARGUMENTS**

Distinct from `/dev`: `/manager` never touches code, branches, Jira, or PRs — it only manages
`Business/<cliente>/`, the folder where client context, scripts, credentials and confidential info
live (see `Business/README.md`). Different people use this skill with different clients, so nothing
in this file (or its siblings) should hardcode a specific client's name or content — only generic
folder-scanning logic.

`$ARGUMENTS` can be:
- empty — lists known clients (read-only, no side effects).
- `<cliente>` alone — resolves to create or update depending on whether the folder already exists.
- `create <cliente>` — routes to `/manager-create`.
- `update <cliente>` — routes to `/manager-update`.

---

## Respect `Business/Agent.md` when present

This applies across `/manager` and every sibling skill (`manager-create`, `manager-update`) — same
cross-reference pattern as `/dev`'s shared conventions in `dev/SKILL.md`.

Before doing anything else under `Business/`, check for a root manual:
```bash
[ -f "$WS/Business/Agent.md" ] && cat "$WS/Business/Agent.md"
```

If it exists, it is **authoritative** — its rules override anything generic in this file or its
siblings. At minimum, expect and honor rules like:
- Identify the client before reading secrets, running scripts, or connecting to any infrastructure.
- Never reuse credentials, hosts, databases, or backups across clients.
- Never print passwords, tokens, cookies, private keys, or connection strings in chat, logs, commits,
  or responses.
- No deploys, uploads, write SQL, service restarts, cache clears, or production changes without
  explicit authorization.
- Keep `Business/` (if it's backed by its own repo) up to date: `fetch`/`pull` before relying on its
  content, `commit`/`push` local changes when appropriate. Never mix files from more than one client in
  the same commit. This content must never end up committed to the public `skill-charly-dev` repo
  itself — that's why `Business/*` is in its `.gitignore` — always confirm you're operating inside
  `Business/` (or a client subfolder) before running git, never from the parent workspace root.

If a specific client folder has its own manual (e.g. `Business/<cliente>/Agent.md`), that file is the
authoritative operational manual for that client — read and follow it before applying
`manager-create`'s generic scaffolding or `manager-update`'s generic maintenance steps to that client.
Treat its existing files/conventions as-is; never impose `context.md`/`client.md`/`credentials.md` on
a client that already has its own established structure.

If no `Business/Agent.md` exists yet, none of this applies — proceed with the generic conventions
below, which follow the same git-sync spirit (fetch first, ask before push) without assuming a
specific policy document exists.

---

## Keeping `Business/` in sync (if it's a git repo)

Applies across `/manager` and every sibling skill, same cross-reference pattern as above.

```bash
[ -d "$WS/Business/.git" ] && git -C "$WS/Business" fetch origin 2>/dev/null && git -C "$WS/Business" status --short
```

If this shows the local branch behind `origin`, surface it before relying on possibly-stale content:
> "`Business/` tiene cambios remotos nuevos. ¿Hago `pull` antes de seguir?"

After writing/updating files in a client subfolder, offer to commit (scoped to that one client's
files only — never a blanket `git add .` across multiple clients) and push, same authorization pattern
`/dev` uses for code pushes — never push without the user's explicit go-ahead in this turn:
> "¿Confirmás el commit y push de `Business/<cliente>/` a su repo?"

If `Business/` has no `.git` (not a repo, or the user manages it manually), skip this section silently
— never initialize a repo there uninvited.

---

## Phase 0: Locate workspace + list known clients

```bash
WS=$(python3 -c "
import os, subprocess
try:
    g = subprocess.check_output(['git','rev-parse','--show-toplevel'], text=True).strip()
except:
    g = os.getcwd()
p = os.path.dirname(g)
print(p if os.path.exists(os.path.join(p,'CLAUDE.md')) else g)
")
find "$WS/Business" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | xargs -n1 basename
```

## Phase 1: Routing

| `$ARGUMENTS` | Action |
|---|---|
| empty | List the clients found in Phase 0. If none exist yet, suggest `/manager-create <cliente>`. Stop here — read-only, no delegation. |
| `create <cliente>` | → `/manager-create <cliente>` |
| `update <cliente>` | → `/manager-update <cliente>` |
| `<cliente>` (no subcommand) matching a folder from Phase 0 | → `/manager-update <cliente>` |
| `<cliente>` (no subcommand) not matching any folder | → `/manager-create <cliente>` |

For routed skills: invoke the target with the client name (and any extra arguments) and follow its
instructions entirely. Do not duplicate their logic here.

---

## Related sibling skills

- `/manager-create` — interactive bootstrap of a new client's `Business/<cliente>/`
- `/manager-update` — refresh/maintain an existing one
