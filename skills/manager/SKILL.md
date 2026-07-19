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
- **Never run `git add`, `git commit`, `git push`, or publish anything from within `Business/`** — it
  can hold sensitive data and nested repos for multiple clients. This holds even if a step elsewhere in
  this skill family would otherwise suggest a git operation — none of `/manager`, `/manager-create`, or
  `/manager-update` ever commit or push inside `Business/` themselves, precisely because of this.

If a specific client folder has its own manual (e.g. `Business/<cliente>/Agent.md`), that file is the
authoritative operational manual for that client — read and follow it before applying
`manager-create`'s generic scaffolding or `manager-update`'s generic maintenance steps to that client.
Treat its existing files/conventions as-is; never impose `context.md`/`client.md`/`credentials.md` on
a client that already has its own established structure.

If no `Business/Agent.md` exists yet, none of this applies — proceed with the generic conventions
below.

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
