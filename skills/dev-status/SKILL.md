---
name: dev-status
description: "Read-only status check — no workflow started, no side effects. Use for 'PROJ-XXX status' (single ticket: branches, commits, PR state), 'status' (all active tickets across the workspace), 'epic <EPIC_KEY>' (rollup of every ticket under an epic), or 'sprint' (current sprint health). Delegated to by /dev for the 'status' subcommand."
allowed-tools: Bash Read
---

# Dev Status — Read-Only Ticket State

Check status for: **$ARGUMENTS**

If `$ARGUMENTS` contains a ticket ID (`msof-XXX`), run the single-ticket check below. If empty or just
`status`, run the multi-ticket overview. If `epic <EPIC_KEY>`, run the epic health check. If `sprint`,
run the sprint health check.

> Before improvising a multi-step procedure, check `scripts/local/MANIFEST.json` — see `dev/references/local-scripting.md`. If the user corrects an in-progress approach, capture it immediately — see "Capture Corrections as They Happen" in `dev/SKILL.md`.

---

## Single ticket: `<TICKET_ID> status`

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"
cat $WS/memory/snapshots/<TICKET_ID>.json 2>/dev/null

for REPO in $REPOS; do
  BASE="master"; case "$REPO" in ${SPECIAL_REPO_PATTERNS// /|}) BASE="$SPECIAL_REPO_BASE";; esac
  git -C $WS/${PROJECTS_PREFIX}$REPO fetch origin -q 2>/dev/null
  BRANCH=$(git -C $WS/${PROJECTS_PREFIX}$REPO branch -a | grep -i "<TICKET_ID>" | head -1 | xargs)
  [ -n "$BRANCH" ] && echo "$REPO: $BRANCH" && git -C $WS/${PROJECTS_PREFIX}$REPO log $BASE..HEAD --oneline 2>/dev/null | head -3
done

gh pr list --search "<TICKET_ID>" --json state,url,title --state all 2>/dev/null | head -3

[ -f $WS/memory/tickets/<TICKET_ID>.json ] && echo "reflected: yes" || echo "reflected: no"
```

**Only if no snapshot was found above** (title/summary otherwise unknown), fetch it — this also gives
`worklog_total_seconds` for free, worth folding into the output line below, still no separate call for
just the title:
```bash
uv run $JIRA_SKILL/utility/jira-qa-gather.py --json "<TICKET_ID>" | python3 "$WS/scripts/jira_trim.py"
```
Skip this call entirely when a snapshot already has the summary — this check is meant to stay fast.

Output format — exactly 6 lines, no markdown:
```
MSOF-XXX | <summary from snapshot or Jira title>
Repos: <which repos have an active branch>  |  PR: <url or "no creado">  |  Estado PR: <open|changes_requested|approved|merged|none>
Commits: <N commits total>  |  Cambios sin commitear: <yes/no>  |  Tiempo logueado: <from worklog_total_seconds if fetched, omit segment otherwise>
Próximo paso: <next_step from snapshot or inferred>
Última actualización: <snapshot_date or "sin snapshot">
```

**Próximo paso priority rule**: if `Estado PR` is `merged` and `reflected: no`, the next step is always
`cerrar con /dev-reflect <TICKET_ID> closing` — capturing the closing reflection (learnings, mistakes,
patterns) takes priority over branch cleanup, since cleanup can happen as part of that closing flow.
Only fall back to "limpiar branch local" once `reflected: yes`.

---

## Multi-ticket overview: `status` (no ticket ID)

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"

for REPO in $REPOS; do
  git -C $WS/${PROJECTS_PREFIX}$REPO branch -a 2>/dev/null | grep -oiE "(feature|fix)/${PROJECT_KEY_LOWER}-[0-9]+" | sort -u
done | sort -u
```

For each ticket found, check whether it was ever closed out:
```bash
[ -f $WS/memory/tickets/<TICKET_ID>.json ] && echo "reflected: yes" || echo "reflected: no"
```

Collect the rest (PR state, commit count) in parallel and output one line per ticket:
```
MSOF-XXX  <phase>  |  <N> commits  |  PR: <state or "sin PR">  |  <next_step — 5 words max>
```

**Próximo paso priority rule** (same as the single-ticket check): if the PR is merged and
`reflected: no`, `<next_step>` is `cerrar con /dev-reflect closing` — this takes priority over
"limpiar branch local". Sort merged-and-unreflected tickets to the **top** of the list — they're the
ones losing captured learnings the longer they sit, not just stale branches.

If no active branches: `"No hay branches activos de MSOF en este workspace."`

---

## Epic health: `epic <EPIC_KEY>`

Rolls up every ticket under an epic — `/dev-status <TICKET_ID>` only ever shows one ticket at a time,
this is the "is the epic actually on track" view nothing else provides.

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"

uv run $JIRA_SKILL/core/jira-search.py --json query "parent = <EPIC_KEY> ORDER BY status, updated DESC" \
  --fields key,summary,status,updated
```

(`--fields` is required here — without it, `updated` isn't included in the response, and the
staleness check below needs it.)

From the results, compute: total count, breakdown by status category (Done / In Progress / To Do), and
flag any `In Progress` ticket whose `updated` field is more than 3 days old — that's a real signal
("started but stalled"), not a maybe.

```
Épica <EPIC_KEY> | <epic summary, from the epic issue itself if easy to fetch, otherwise omit>
Tickets: <N> total | Done: <X> | In Progress: <Y> | To Do: <Z>
Estancados (In Progress, sin actividad hace 3+ días): <lista de tickets, o "ninguno">
```

## Sprint health: `sprint`

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"

# Discover and cache the board ID for this project — boards essentially never change, no need to
# re-query every time
if [ -f "$WS/memory/board.json" ]; then
  BOARD_ID=$(jq -r '.id' "$WS/memory/board.json")
else
  uv run $JIRA_SKILL/workflow/jira-board.py --json list | python3 -c "
import json, sys
boards = json.load(sys.stdin)
match = next((b for b in boards if b.get('location', {}).get('projectKey') == '$PROJECT_KEY'), None) or (boards[0] if boards else None)
if match:
    json.dump({'id': match['id'], 'name': match['name']}, open('$WS/memory/board.json', 'w'))
    print(match['id'])
"
fi

uv run $JIRA_SKILL/workflow/jira-sprint.py --json current "$BOARD_ID"
```

If no active sprint: report that plainly and stop — not every project runs sprints continuously, this
isn't an error.

If there is one, get its issues and compute the same breakdown as the epic check:
```bash
uv run $JIRA_SKILL/workflow/jira-sprint.py --json issues "<SPRINT_ID from current, above>" \
  --fields key,summary,status,updated
```

```
Sprint <name> | <N> días restantes (termina <end date>)
Tickets: <N> total | Done: <X> | In Progress: <Y> | To Do: <Z>
Sin actividad reciente (In Progress, 3+ días sin update): <lista, o "ninguno">
```
