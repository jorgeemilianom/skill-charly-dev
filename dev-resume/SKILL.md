---
name: dev-resume
description: "Reconstructs full development context for a ticket already in progress — reads commits, diffs, and PR state across every repo, cross-references against ticket requirements, and produces a resume summary plus a standup blurb. Use for 'PROJ-XXX resume'. Delegated to by /dev for the 'resume' subcommand."
allowed-tools: Bash Read
---

# Dev Resume — Reconstruct Development Context

Resume development context for: **$ARGUMENTS**

`$ARGUMENTS` is the ticket ID (`msof-XXX`).

> Before improvising a multi-step procedure, check `.ai/vendor/local/MANIFEST.json` — see `dev/references/local-scripting.md`.

---

## Step 1 — Load ticket and branch state

Run in parallel:
```bash
JIRA_SKILL=${JIRA_SCRIPTS}
uv run $JIRA_SKILL/core/jira-issue.py get "<TICKET_ID>" --json

WS=$(python3 -c "
import os, subprocess
try:
    g = subprocess.check_output(['git','rev-parse','--show-toplevel'], text=True).strip()
except:
    g = os.getcwd()
p = os.path.dirname(g)
print(p if os.path.exists(os.path.join(p,'CLAUDE.md')) else g)
")
cat $WS/.ai-memory/snapshots/<TICKET_ID>.json 2>/dev/null
cat $WS/.ai-memory/assessments/<TICKET_ID>.json 2>/dev/null

for REPO in ${REPOS}; do
  BASE="master"; case "$REPO" in ${SPECIAL_REPO_CASE_PATTERN}) BASE="${SPECIAL_REPO_BASE}";; esac
  BRANCH=$(git -C $WS/$REPO branch -a | grep -i "<TICKET_ID>" | head -1 | tr -d ' ')
  if [ -n "$BRANCH" ]; then
    echo "=== $REPO ==="
    git -C $WS/$REPO log $BASE..HEAD --oneline
    git -C $WS/$REPO status --short
    gh pr list --head $(echo $BRANCH | sed 's|remotes/origin/||') \
      --json number,title,state,url,reviews,reviewRequests,comments 2>/dev/null
  fi
done
```

Rename session: `/rename MSOF-XXX | <ticket summary>`

## Step 2 — Read the actual changes

For each file in the diff across affected repos, read its content to understand **what was implemented**, not just what changed. Focus on:
- What logic was added or modified
- What is partially done (started but not finished)
- What the code reveals about the next step

## Step 3 — Cross-reference against ticket requirements

Compare what was implemented against what the ticket asks for. Determine:
- What acceptance criteria are already satisfied
- What is partially addressed
- What has not been started yet

## Step 4 — Present the resume summary

```
## Resumen de retomada — <TICKET_ID>

### Qué se implementó
- <bullet por cada cosa concreta ya hecha, basado en commits y código>

### En progreso (incompleto)
- <código que existe pero está a medio hacer, si hay>

### Pendiente
- <lo que el ticket pide y aún no está implementado>

### Repos activos
- <QuintaApp-Api: branch + N commits | QuintaApp-Frontend: idem | CloudHubCorp: idem>

### Estado del PR
- <no creado / abierto / cambios solicitados / aprobado>
- <si hay review comments pendientes: listarlos>

### Próximo paso concreto
<una sola oración describiendo exactamente qué hacer primero al retomar>

---
### Para la daily
> "Estoy trabajando en [TICKET_ID]: [descripción breve].
> [Lo que se hizo: 1-2 oraciones].
> Hoy voy a [próximo paso]."
```

## Step 5 — Propose continuation

> "¿Continuamos desde donde quedó? Puedo arrancar con [próximo paso concreto]."

Proceed to the appropriate `/dev` phase after confirmation (e.g. `/dev <TICKET_ID>` to re-enter branch setup/development, `/dev-pr <TICKET_ID>` if a PR is pending).
