# Business/

Client context for the skill: one subfolder per client, e.g. `Business/QuintaApp/`.

This is separate from `memory/` — `memory/` holds ticket-level operational history (assessments,
snapshots, learnings); `Business/<cliente>/` holds stable, client-level knowledge (business context,
scripts, credentials, confidential info) that doesn't change ticket to ticket.

## Conventions (all optional — nothing here is required)

Content inside each client folder is free-form: notes, scripts, credentials, whatever that client
needs. There's no fixed schema to follow — the skill reads whatever's there.

One convenience file the skill knows how to use if present: `client.md`, a small optional manifest
that maps repos in `projects/` back to this client:

```yaml
---
repos: [QuintaApp-Api, QuintaApp-Frontend]
jira_key: MSOF
---
```

`/dev` offers to write this the first time it needs to ask which client a repo belongs to — decline
and it just asks again next time. It's never required.

Credentials/confidential fields are never filled in through chat — `/manager-create` leaves them as a
placeholder file for you to complete by hand outside the conversation.

## `Agent.md` — if you already have an operational manual

If you drop an `Agent.md` here (root) and/or inside a specific `Business/<cliente>/Agent.md`, it's
treated as **authoritative** by `/manager`, `/manager-create`, and `/manager-update` — its rules
override the generic conventions in this file, and its existing file structure (whatever it is) is
respected as-is rather than overwritten with `context.md`/`client.md`/`credentials.md`. See "Respect
`Business/Agent.md` when present" in `skills/manager/SKILL.md` for exactly what that means (client
isolation, never printing secrets, and — critically — never running `git add`/`commit`/`push` from
inside `Business/`, since it can hold sensitive data and repos for multiple clients at once).

## How folders get here

- `/manager-create <cliente>` — bootstraps a new client folder interactively.
- `/manager-update <cliente>` — refreshes an existing one.
- `/dev` triggers `/manager-create` automatically the first time it works on a repo with no client
  association found under `Business/`.

## Git

This folder's real content is **gitignored** — only this README is tracked, so a fresh clone gets an
empty `Business/` ready to populate. Versioning what you put here (one shared private repo, one repo
per client, or nothing versioned at all) is entirely up to you — the skill never assumes a particular
VCS layout.
