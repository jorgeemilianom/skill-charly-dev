---
name: manager-exec
description: "Executes a development or operational task directly on a client's remote infrastructure (SSH/VPS) instead of a local git+Jira flow. Loads Business/<cliente>/Agent.md as the authoritative connection/deploy playbook when present; otherwise bootstraps one collaboratively and generates only the connection script actually needed. Never prints credentials in chat — resolves secrets via session-scoped environment variables the user sets themselves. Read-only checks run freely; anything that mutates remote state (deploy, restart, write) requires explicit authorization first, every time. Delegated to by /manager's Phase 2 when a client requirement needs infra execution, or directly via '<cliente> exec <task>'."
allowed-tools: Bash Read Write
---

# Manager Exec — Remote Task Execution for Infra-Based Clients

Execute the task for: **$ARGUMENTS**

`$ARGUMENTS` is `<cliente> <task description>`.

Distinct from `/dev`: this is for clients whose work doesn't live in a local repo under `projects/`
tracked with Jira branches/PRs — it happens directly on the client's own infrastructure (a VPS, a
shared host, a remote Windows box), reached over SSH/SFTP. If `client.md` has a `repos:` entry pointing
at a local checkout for the task at hand, this is the wrong skill — that's `/dev`. A client can have
both (e.g. a Jira epic for tracking *and* `exec: ssh` for where the actual work happens) — check what
the specific task touches, not just what the client has.

## Non-negotiable rules (from `Business/Agent.md`, apply throughout, no exceptions)

- Identify the client before reading secrets or connecting to anything.
- Never reuse credentials, hosts, or backups across clients.
- Never print passwords, tokens, cookies, private keys, or connection strings in chat, logs, commits, or
  responses — resolve them into session-scoped environment variables instead (e.g.
  `<CLIENTE>_SSH_PASSWORD`, set by the user in their own shell). Never ask them to paste the secret into
  chat, and never write it to a file this skill creates.
- No deploys, uploads, write SQL, service restarts, cache clears, or production changes without
  explicit authorization in the current turn — no matter how small the change looks.
- Read-only checks (status, whoami, diff, logs) run freely, no need to ask before each one.

---

## Step 0 — Preconditions and client resolution

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CLIENTE="<cliente>"
[ -d "$WS/Business/$CLIENTE" ] && echo EXISTS || echo MISSING
```

If `MISSING`: offer `/manager-create <cliente>` first — stop here, there's no context to work from yet.

## Step 1 — Load the operational playbook

```bash
[ -f "$WS/Business/Agent.md" ] && cat "$WS/Business/Agent.md"
[ -f "$WS/Business/$CLIENTE/Agent.md" ] && cat "$WS/Business/$CLIENTE/Agent.md"
cat "$WS/Business/$CLIENTE/client.md" 2>/dev/null
```

**If `Business/<cliente>/Agent.md` exists**: it is the authoritative playbook — connection details,
existing helper scripts, environment quirks, and deployment procedure are already documented there.
Follow it as-is. Do not regenerate scripts it already provides (e.g. an existing
`ssh_<cliente>.py`/`sftp_<cliente>.py`) — reuse them. Read any other files it points to (README,
HANDOFF, INDEX, snapshot) in the order it specifies before doing anything else.

**If no `Agent.md` exists yet for this client** (first time working this way with them): go to Step 2
before attempting the task.

## Step 2 — Bootstrap (first time only, no existing client `Agent.md`)

Ask, in a short back-and-forth:
- Host, port, username for SSH/SFTP access.
- Auth method: SSH key (preferred — ask for the key path) or password. **Never ask the user to paste a
  password into chat.** If password-based, have them set it as a session env var themselves — tell them
  the exact command, don't run it for them.
- Remote path(s) relevant to the work (webroot, app path, etc.).
- Anything environment-specific worth documenting up front (runtime version constraints, multi-site/
  multi-language quirks, non-default ports, a staging vs. production distinction).

Prefer plain `ssh`/`scp`/`rsync` from bash — simplest, no extra script needed. Only generate a dedicated
helper script (e.g. Python+paramiko) when plain `ssh` genuinely can't do the job cleanly from this
session — e.g. password auth with no TTY, a remote shell needing special quoting (Windows `cmd`), or a
command that has to run repeatedly across a longer task.

Write the connection details (non-secret only: host/port/user/paths) to a new
`Business/<cliente>/Agent.md`: how to connect, how to check state safely (read-only commands first), the
deploy workflow (Step 4 below), and any quirks gathered above. If another client folder already has its
own `Agent.md` documenting a similar remote-access setup, skim its shape for inspiration on structure —
but never copy client-specific details (hosts, paths, credentials) across clients. Confirm the draft
with the user before writing, same as any other `Business/` write.

If a helper script was generated, save it under `Business/<cliente>/scripts/` and reference its path
from the new `Agent.md`.

Record `exec: ssh` in `client.md` (create it if missing, preserve any existing `jira_key:` /
`jira_epic:` fields) so `/manager` routes future requests for this client here without asking again:
```yaml
---
jira_epic: <existing value, if any>
exec: ssh
---
```

## Step 3 — Understand the task

Same back-and-forth stance as `/dev-create`'s Step 1: what's actually needed, why, and — critically for
remote work — what it touches (a read-only check, a config/content change, a code change that needs a
deploy, a service operation like a restart). Don't start executing until this is clear.

## Step 4 — Execute, following the deploy workflow

Default workflow when the client's own `Agent.md` doesn't already specify one:

1. Determine which environment the task touches (dev/staging/prod, which host).
2. Check current remote state first — read-only (status, existing config, logs) — before touching
   anything.
3. For any remote file being changed: download a timestamped backup copy before modifying it.
4. Make the minimal change in the correct place — locally, in a cloned/synced copy, not by editing live
   over an interactive SSH session where there's no diff to review afterward.
5. Show the diff, the risk, and the rollback plan to the user.
6. **Ask for explicit authorization before deploying/uploading/restarting anything.** No exceptions,
   regardless of how small the change looks — same rule as `/dev`'s push authorization, applied here.
7. Deploy the single change, verify the remote hash/content matches, and check functional behavior
   (HTTP check, expected output) afterward.
8. Log what was done — date, environment, files touched, backup location, what was verified, rollback
   command — in `Business/<cliente>/` (append to `context.md`, or the client's own log location if
   `Agent.md` specifies one). Never overwrite prior log entries.

## Step 5 — Report

Summarize what changed, where, and how to roll it back if needed. Remind the user to unset any
session-scoped credential env vars now, if they haven't been already.

---

## Related sibling skills

- `/manager` Phase 2 — routes here when a requirement needs infra execution instead of local
  development or a business note
- `/manager-create` — Step 2 also asks whether a new client works this way and records `exec: ssh`
- `/dev` — the other execution path, for clients with a local repo under `projects/` and a Jira ticket
  loop; not used here
