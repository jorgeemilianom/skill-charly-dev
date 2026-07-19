---
name: dev-create
description: "Collaboratively defines a brand-new ticket from a freeform idea or requirement: discusses scope with the user, drafts a structured spec, resolves the epic (using a cached epic list so it's never re-learned from scratch), and files the Jira ticket. Use when the user describes a new feature/bug/idea that has no ticket ID yet, or explicitly asks to create a ticket. Delegated to by /dev when no ticket ID is found in the request."
allowed-tools: Bash Read Write
---

# Dev Create — Spec and File a New Ticket

Turn this idea into a filed Jira ticket: **$ARGUMENTS**

`$ARGUMENTS` is a freeform description — there is no ticket ID yet, that's what this skill produces.

> Before improvising a multi-step procedure, check `scripts/local/MANIFEST.json` — see `dev/references/local-scripting.md`. If the user corrects an in-progress approach, capture it immediately — see "Capture Corrections as They Happen" in `dev/SKILL.md`.

---

## Step 0 — Preconditions

`dev-create` is a common **first entry point** into a fresh clone — a freeform idea routes here directly
without going through `/dev`'s own precondition check first (Claude can match this skill straight from
its description; Codex resolves it the same way via `agent-context.md`). Run the same cheap check `/dev`
does before diving into a multi-step conversation that would otherwise fail deep in, at the Jira step:

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
[ -f "$WS/config.sh" ] && { [ -f ~/.env.jira ] || [ -f ~/.jira/profiles.json ]; } && echo OK || echo MISSING
```

If `MISSING`: "Faltan prerequisitos antes de crear el ticket (config o credenciales de Jira). ¿Corro
`/dev-setup` para revisar qué falta?" If confirmed, invoke `/dev-setup`, then resume with the original
`$ARGUMENTS` once it reports OK. (`gh auth` isn't required here — this skill doesn't touch GitHub — so
it's not part of this check, unlike `/dev`'s.)

## Role

Same technical-advisor stance as `/dev`: challenge vague or questionable scope before drafting the
spec, ask what's missing instead of guessing, and surface existing patterns/tickets that might already
cover this.

## Step 1 — Understand the request

Have a short back-and-forth to nail down:
- The actual problem or need (not just the proposed solution).
- Which repo(s) are affected — QuintaApp-Api, QuintaApp-Frontend, CloudHubCorp, or a combination.
- Rough acceptance criteria.
- Whether it's a Story, Bug, or Task.

Don't proceed to drafting until this is clear enough to write a real spec — ask, don't assume.

## Step 2 — Draft the spec together

Write the description directly in Jira wiki markup (see the `jira-syntax` skill for syntax — this is a
structured description, not a plain-text comment):

```
h2. Resumen
<one paragraph: what this is and why>

h3. Problema / Motivación
<what's broken or missing today>

h3. Alcance
<affected repo(s), what changes>

h3. Criterios de aceptación
* <criterion>
* <criterion>

h3. Fuera de alcance
<omit this section entirely if there's nothing to exclude>
```

Show the draft to the user and iterate until they approve it — do not create the ticket from a first
draft without confirmation.

## Step 3 — Resolve the epic

Read the cached epic list first:
```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cat $WS/memory/epics.json 2>/dev/null
```

If it exists, show the cached epics for `PROJECT_KEY` (from `config.sh`) and ask the user to pick one
(or "ninguna").

If it's missing, or the user wants a refreshed list, or none of the cached epics fit, query Jira and
rewrite the cache:
```bash
source "$WS/scripts/workspace-env.sh"
uv run $JIRA_SKILL/core/jira-search.py --json query "project = $PROJECT_KEY AND issuetype = Epic ORDER BY created DESC"
```

Cache format — `$WS/memory/epics.json`, keyed by project so multiple projects can share the file:
```json
{
  "<PROJECT_KEY>": {
    "MSOF-10": "Epic name",
    "MSOF-24": "Another epic name"
  },
  "updated_at": "<ISO date>"
}
```

## Step 4 — Confirm before creating

Show the final summary — type, project, summary, epic, full description — and get explicit
confirmation before touching Jira.

## Step 5 — Create the ticket

**Do not use `--parent <EPIC_KEY>` directly** — verified against `PROJECT_KEY` (team-managed
project): `--parent` forces the issue type down to the project's subtask type regardless of `-t`,
turning the new issue into a subtask of the epic instead of a top-level Story/Task/Bug linked to it.
Use `--fields-json` instead, which preserves the requested type:

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"
uv run $JIRA_SKILL/workflow/jira-create.py issue $PROJECT_KEY "<summary>" -t <type> -d "<description>" --fields-json '{"parent": {"key": "<EPIC_KEY>"}}' --dry-run
uv run $JIRA_SKILL/workflow/jira-create.py issue $PROJECT_KEY "<summary>" -t <type> -d "<description>" --fields-json '{"parent": {"key": "<EPIC_KEY>"}}'
```

If a future Jira project configured through this template is company-managed instead of team-managed,
the epic-link field is different (classic "Epic Link" custom field, not `parent`) — check an existing
epic-linked issue with `jira-issue.py get <KEY> --json` and look for either `fields.parent` or a
`customfield_*` holding the epic key before assuming `parent` works there too.

## Step 6 — Report and offer to continue

Report the created ticket key and URL, then offer:
> "Ticket creado: `<TICKET_ID>`. ¿Arrancamos el desarrollo ahora? (`/dev <TICKET_ID>`)"
