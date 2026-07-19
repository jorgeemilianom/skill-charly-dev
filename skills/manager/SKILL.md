---
name: manager
description: "Business-layer orchestrator and entry point for client requirements. Talks through a client's request grounded in Business/<cliente> context; resolves it directly if it's pure business (notes, process, manifest), delegates to /dev (which files the ticket via /dev-create) when it needs local development, or delegates to /manager-exec when it needs execution on a client's remote infrastructure (SSH/VPS). Also gives a read-only status/catch-up digest with proactive proposals (manager-status), and a consolidated dev+clients digest (manager-digest) for a weekly check-in or a scheduled routine. Never creates/edits Jira tickets, code, or remote state itself. Routes to manager-create, manager-update, manager-status, manager-exec, or manager-digest, or lists known clients on a bare call. Use for 'manager <cliente>', 'manager create <cliente>', 'manager update <cliente>', 'manager <cliente> status', 'manager status', 'manager digest', 'manager <cliente> exec <task>', 'manager <cliente> <requirement text>', or plain 'manager'."
allowed-tools: Bash Read Write
---

# Manager — Business Context Orchestrator

Execute the business-layer request for: **$ARGUMENTS**

Distinct from `/dev`: `/manager` never creates or edits code, branches, Jira tickets, or PRs itself —
it only manages `Business/<cliente>/`, the folder where client context, scripts, credentials and
confidential info live (see `Business/README.md`). When a client requirement turns out to need actual
development, `/manager` doesn't build that logic itself — it delegates to `/dev` (Phase 2 below), same
single owner of Jira/code/PR actions as always. Different people use this skill with different clients,
so nothing in this file (or its siblings) should hardcode a specific client's name or content — only
generic folder-scanning logic.

`$ARGUMENTS` can be:
- empty — lists known clients (read-only, no side effects).
- `<cliente>` alone — resolves to create or update depending on whether the folder already exists.
- `create <cliente>` — routes to `/manager-create`.
- `update <cliente>` — routes to `/manager-update`.
- `status` (no client) or `<cliente> status` — routes to `/manager-status`: read-only catch-up digest,
  see Phase 1.
- `digest` — routes to `/manager-digest`: one consolidated summary of dev tickets, sprint health, and
  all clients — composed from `/dev-status` + `/manager-status`, not reimplemented.
- `<cliente> exec <task>` — routes directly to `/manager-exec <cliente> <task>`, for clients whose work
  happens on remote infrastructure (SSH/VPS) instead of a local repo.
- `<cliente> <free text>`, or any free text describing what a client wants — Phase 2, requirement
  intake: talk it through and resolve it here, or delegate to `/dev` or `/manager-exec` depending on
  what the task actually needs.

---

## Role: Business Advisor

Applies across `/manager` and every sibling skill (`manager-create`, `manager-update`,
`manager-status`) — same cross-reference pattern as `/dev`'s "Technical Advisor, Not Just Executor"
stance in `dev/SKILL.md`, at business altitude instead of technical:

- Don't just execute or recite facts — flag what looks stale, at-risk, or like an opportunity, based on
  what `Business/<cliente>/` and any linked dev/Jira activity actually show.
- Make concrete proposals when relevant (1-3, not a wall of ideas) — grounded, not generic advice.
- Acknowledge uncertainty — if context is thin or contradicts what you infer from other sources, say so
  instead of guessing.
- Defer to the user if they push back after hearing your take.
- A conversation with `/manager` doesn't have to end in a file write — debating a client's situation
  without resolving to an action in the same turn is a legitimate use of this skill, not something to
  rush past.

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
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
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
| `status` (no client) | → `/manager-status` |
| `<cliente> status` | → `/manager-status <cliente>` |
| `digest` | → `/manager-digest` |
| `<cliente> exec <task>` | → `/manager-exec <cliente> <task>` |
| anything else — free text, with or without a leading client name | → Phase 2 (Requirement Intake) |

For routed skills: invoke the target with the client name (and any extra arguments) and follow its
instructions entirely. Do not duplicate their logic here.

---

## Phase 2: Requirement Intake (client requirement conversation)

This is the entry point for "hablar sobre un requerimiento de un cliente" — you (business owner) describe
what a client wants, in your own words, and this phase figures out whether it's something to resolve here
or something that needs `/dev`.

### Step 1 — Identify the client

If a client name from Phase 0's listing appears in `$ARGUMENTS`, use it. Otherwise ask:
> "¿Para qué cliente es esto?" — list the known clients from Phase 0 as a hint if there's more than one.

If the client has no folder yet, offer `/manager-create <cliente>` first (same as the Phase 1 bare-name
case) so there's context to ground the conversation, then continue here once it's created.

### Step 2 — Load context

```bash
CLIENTE="<resolved client name>"
[ -f "$WS/Business/$CLIENTE/Agent.md" ] && cat "$WS/Business/$CLIENTE/Agent.md"
cat "$WS/Business/$CLIENTE/context.md" 2>/dev/null
cat "$WS/Business/$CLIENTE/client.md" 2>/dev/null
```

Respect `Business/Agent.md` / per-client `Agent.md` as usual (see above). `client.md`'s `repos:` /
`jira_key:` (or `jira_epic:`) manifest, if present, is what lets Step 4 hand off to `/dev` without
re-asking which repo or Jira project this client maps to.

### Step 3 — Understand the requirement

Short back-and-forth, same technical-advisor stance as `/dev-create`'s Step 1 but at business altitude:
what does the client actually want, why, how urgent. Don't assume the answer to the question that
decides everything else — if `client.md` already has `exec: ssh` or `repos:`, that's a strong hint of
which path applies; otherwise ask directly:
> "¿Esto implica desarrollo en un repo local (`/dev`), ejecutar algo en la infraestructura del cliente
> (SSH/VPS), o es más de gestión/contenido/proceso?"

### Step 4 — Resolve

- **Pure business** (no code, no infra — a note, a process change, pricing, content, a manual task, a
  question answered): apply it the same way `/manager-update` would. You already have `context.md`
  loaded from Step 2, so apply directly instead of re-invoking that skill from scratch:
  ```
  ## <ISO date>
  <note>
  ```
  appended to `context.md` (never overwrite prior notes), or a `client.md` manifest update if that's
  what changed. Confirm the change with the user before writing, same as `/manager-update` Step 3.

- **Needs local development** (a repo under `projects/`, tracked via Jira/branch/PR): confirm scope
  with the user, then hand off:
  ```
  /dev <resumen del requerimiento, con cliente y repo(s) identificados si el manifiesto los tiene>
  ```
  This routes to `/dev-create`, which drafts the spec together with the user and files the ticket —
  and **stops there**, offering to continue into development on its own (`/dev-create`'s Step 6:
  "¿Arrancamos el desarrollo ahora? (`/dev <TICKET_ID>`)"). `/manager` does not create the ticket
  itself and does not auto-continue into the coding loop — filing the ticket is as far as this flow
  goes unless the user explicitly asks to keep going.

- **Needs execution on the client's own infrastructure** (SSH/VPS, no local repo — e.g. `exec: ssh` in
  `client.md`, or the client has no `repos:` entry at all): confirm scope with the user, then hand off:
  ```
  /manager-exec <cliente> <resumen de la tarea>
  ```
  `/manager-exec` finds or bootstraps the connection details and the client's operational playbook
  (`Business/<cliente>/Agent.md`), generates only the script actually needed, and executes read-only
  checks freely — but asks for explicit authorization before anything that mutates remote state. Same
  "stops and reports" spirit as the `/dev` branch: this hands off fully, `/manager` doesn't duplicate
  any of that execution logic here.

### Step 5 — Log the outcome (development and infra-execution branches only)

Once `/dev-create` or `/manager-exec` reports what it did (ticket created, or task executed), come back
and append the cross-reference to `context.md` — nothing today otherwise links `Business/<cliente>/`
notes back to the Jira tickets or remote changes they originated:
```
## <ISO date>
Ticket <TICKET_ID> abierto a partir de esta conversación: <one-line summary>.
```
or
```
## <ISO date>
Ejecutado en infraestructura del cliente: <one-line summary, ver detalle en manager-exec o context.md>.
```
Same confirm-before-write and commit/push offer as any other `Business/` write (see "Keeping
`Business/` in sync" above). The pure-business branch (Step 4, first case) already writes its own note
inline — no separate log needed there.

---

## Related sibling skills

- `/manager-create` — interactive bootstrap of a new client's `Business/<cliente>/`
- `/manager-update` — refresh/maintain an existing one
- `/manager-status` — read-only status/catch-up digest with proactive proposals, no writes
- `/manager-digest` — consolidated dev+clients summary composed from `/dev-status` + `/manager-status`,
  built to double as a scheduled routine's payload
- `/manager-exec` — executes tasks on a client's remote infrastructure (SSH/VPS), for clients without a
  local repo under `projects/`

Separate command family (not a `manager-*` sibling): `/dev` and its own siblings own all Jira/code/PR
logic for clients with a local repo. Phase 2 above delegates to `/dev` for anything requiring local
development, or to `/manager-exec` for anything requiring remote infra execution — it never duplicates
either's logic locally.
