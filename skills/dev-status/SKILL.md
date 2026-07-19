---
name: dev-status
description: "Read-only ticket state check — no workflow started, no side effects. Use for 'PROJ-XXX status' (single ticket: branches, commits, PR state) or 'status' (all active tickets across the workspace). Delegated to by /dev for the 'status' subcommand."
allowed-tools: Bash Read
---

# Dev Status — Read-Only Ticket State

Check status for: **$ARGUMENTS**

If `$ARGUMENTS` contains a ticket ID (`msof-XXX`), run the single-ticket check below. If empty or just `status`, run the multi-ticket overview.

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

Output format — exactly 6 lines, no markdown:
```
MSOF-XXX | <summary from snapshot or Jira title>
Repos: <which repos have an active branch>  |  PR: <url or "no creado">  |  Estado PR: <open|changes_requested|approved|merged|none>
Commits: <N commits total>  |  Cambios sin commitear: <yes/no>
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
