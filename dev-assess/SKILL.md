---
name: dev-assess
description: "Technical deep dive before writing any code. Reads Jira, detects affected repos, explores the codebase with architecture-aware heuristics, loads .ai-memory context, produces a Technical Assessment, and — after one user confirmation — enriches the Jira ticket with structured documentation and transitions it to In Progress. Delegated to by /dev before development starts."
allowed-tools: Bash Read Write
---

# Assess — Technical Deep Dive

Run technical assessment for: **$ARGUMENTS**

Extract ticket ID (`msof-XXX`) from `$ARGUMENTS`. Normalize to uppercase: `MSOF-XXX`.

This skill performs the full pre-development analysis before any code is written. It produces a Technical Assessment that the user confirms **once** — that single confirmation also covers Jira documentation and transition to In Progress.

**Triggered by**: before starting development. Can also be invoked directly.

> Before improvising a multi-step procedure, check `.ai/vendor/local/MANIFEST.json` — see `dev/references/local-scripting.md`.

---

## Step 0 — Parallel kickoff

Run all of the following **simultaneously** before doing anything else.

```bash
JIRA_SKILL=${JIRA_SCRIPTS}
WS=$(python3 -c "
import os, subprocess
try:
    g = subprocess.check_output(['git','rev-parse','--show-toplevel'], text=True).strip()
except:
    g = os.getcwd()
p = os.path.dirname(g)
print(p if os.path.exists(os.path.join(p,'CLAUDE.md')) else g)
")

# 1 — Read ticket from Jira
uv run $JIRA_SKILL/core/jira-issue.py get "<TICKET_ID>" --json

# 2 — Check branch state across all sub-repos
for REPO in ${REPOS}; do
  git -C $WS/$REPO fetch origin 2>/dev/null; git -C $WS/$REPO branch -a | grep -i "<TICKET_ID>"
done

# 3 — Initialize and read .ai-memory/
mkdir -p $WS/.ai-memory/tickets $WS/.ai-memory/assessments
[ -f $WS/.ai-memory/global_rules.json ] || echo '{"rules":[]}' > $WS/.ai-memory/global_rules.json
[ -f $WS/.ai-memory/patterns.json ]     || echo '{"patterns":[]}' > $WS/.ai-memory/patterns.json
jq empty $WS/.ai-memory/patterns.json 2>/dev/null || echo '{"patterns":[]}' > $WS/.ai-memory/patterns.json
jq '.patterns |= map(. + {type: (.type // "success"), frequency: (.frequency // 1), confidence: (.confidence // 0.5)})' \
  $WS/.ai-memory/patterns.json > $WS/.ai-memory/tmp.json && mv $WS/.ai-memory/tmp.json $WS/.ai-memory/patterns.json
[ -f $WS/.ai-memory/decisions.json ] || echo '{"decisions":[]}' > $WS/.ai-memory/decisions.json
[ -f $WS/.ai-memory/mistakes.json ]  || echo '{"mistakes":[]}' > $WS/.ai-memory/mistakes.json
[ -f $WS/.ai-memory/tickets/<TICKET_ID>.json ] || echo '{"summary":"","decisions":[],"learnings":[]}' > $WS/.ai-memory/tickets/<TICKET_ID>.json
[ -f $WS/.ai-memory/assessments/<TICKET_ID>.json ] && cat $WS/.ai-memory/assessments/<TICKET_ID>.json
cat $WS/.ai-memory/global_rules.json $WS/.ai-memory/patterns.json $WS/.ai-memory/decisions.json \
    $WS/.ai-memory/mistakes.json $WS/.ai-memory/tickets/<TICKET_ID>.json

# 4 — Extract epic key from ticket JSON (run in parallel)
uv run $JIRA_SKILL/core/jira-issue.py get "<TICKET_ID>" --json 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
epic = d.get('fields', {}).get('parent', {}).get('key') or d.get('fields', {}).get('customfield_10014')
print(epic or '')
" 2>/dev/null
```

Once all complete, determine:
- **Branch exists in any repo** → resumed branch. Skip sections E, F, A, B. Go to Section G.
- **No branch found** → fresh start. Continue below.

---

## Section E — Historical Context (passive, from Step 0)

Extract from `.ai-memory/` files loaded in Step 0:

1. **`.ai-memory/`** (primary): decisions, mistakes, patterns, global rules, ticket history.
2. **`~/.claude/projects/`** (secondary): style preferences and authorization rules.

Feed findings into the **Memory context** section of the Technical Assessment. Cite origin ticket when relevant: `"En MSOF-XXX se adoptó el mismo patrón y funcionó / falló porque [razón]"`. If nothing is applicable, continue silently.

---

## Section F — Epic Context (passive, from Step 0)

Use the epic key extracted in Step 0. If no epic, skip silently.

```bash
JIRA_SKILL=${JIRA_SCRIPTS}
uv run $JIRA_SKILL/core/jira-search.py query \
  "project = ${PROJECT_KEY} AND parent = <EPIC_KEY> ORDER BY status, priority" \
  --max-results 50 --json
```

| Status | Include when |
|--------|-------------|
| **In Progress** | Always |
| **Done** | Only if closed in the last 60 days |
| **To Do** | Next 3–5 by priority, only if description mentions same module/endpoint/entity |

Cross-reference against Section B findings.

---

## Section A — Repo Detection + Architecture Context

### A.1 — Detect affected repos

Read the ticket title and description. Map keywords to repos:

> **CUSTOMIZE** — Replace the table below with your project's repos and their associated keywords.

| Keywords | Repo |
|---|---|
| API, endpoint, handler, use case, dominio, entidad, repositorio, Go, JWT, auth, migración SQL, booking, quinta, imagen | `QuintaApp-Api` |
| Frontend, UI, componente, React, vista, página, formulario, ruta, JSX, Vite, CSS | `QuintaApp-Frontend` |
| CloudHub, módulo, tenant, backoffice, Astro, PHP, m_, negocio, multi-tenant | `CloudHubCorp` |

If ambiguous or the ticket mentions multiple areas → mark all relevant repos as affected.

### A.2 — Read project context for each affected repo (in parallel)

> **CUSTOMIZE** — Replace the per-repo blocks below with your project's directory structure and architecture rules.

**For QuintaApp-Api** (if affected):
```bash
WS=<workspace_root>
cat $WS/QuintaApp-Api/CLAUDE.md
cat $WS/QuintaApp-Api/Makefile
ls $WS/QuintaApp-Api/internal/core/domain/
ls $WS/QuintaApp-Api/internal/core/ports/repositories/
ls $WS/QuintaApp-Api/internal/core/ports/services/
ls $WS/QuintaApp-Api/internal/core/services/
ls $WS/QuintaApp-Api/internal/adapters/primary/http/handlers/
ls $WS/QuintaApp-Api/internal/adapters/secondary/mysql/
ls $WS/QuintaApp-Api/specs/features/ 2>/dev/null
cat $WS/QuintaApp-Api/spec_openapi/openapi.yaml 2>/dev/null | head -80
```
Architecture layers (dependencies flow inward): Adapters → Ports → Domain.
Coverage gate: 80% minimum on `./internal/core/...` and `./internal/adapters/primary/...`.
New domain errors: define in `errors.go`, add case in `mapError()`.

**For QuintaApp-Frontend** (if affected):
```bash
cat $WS/QuintaApp-Frontend/CLAUDE.md
ls $WS/QuintaApp-Frontend/src/features/
ls $WS/QuintaApp-Frontend/src/services/
ls $WS/QuintaApp-Frontend/src/components/
ls $WS/QuintaApp-Frontend/src/pages/ 2>/dev/null
```
All API calls go through `src/services/apiClient.js` — never fetch directly from components.
Every new component needs a `.test.jsx` file alongside it.

**For CloudHubCorp** (if affected):
```bash
cat $WS/CloudHubCorp/CLAUDE.md
cat $WS/CloudHubCorp/Makefile
ls $WS/CloudHubCorp/src/ 2>/dev/null
ls $WS/CloudHubCorp/api/ 2>/dev/null
ls $WS/CloudHubCorp/Backoffice/src/ 2>/dev/null
```
Critical rules: always scope SQL with `business_id`; never use PUT/DELETE; always run `make build` after Backoffice changes; branch flow is `feature/*` → `develop` → `master` (never push direct to master).

Internalize CLAUDE.md rules for each affected repo before any exploration — they override default patterns.

---

## Section B — Codebase Exploration (passive)

For each affected repo, run grep and git log in parallel. Use keywords from the ticket title/description.

**QuintaApp-Api:**
```bash
grep -r "<keyword>" $WS/QuintaApp-Api/internal/ --include="*.go" -l
git -C $WS/QuintaApp-Api log --oneline --all --grep="<keyword>"
```
Then read: handler → use case interface (port) → service implementation → repository interface → MySQL implementation → tests.

**QuintaApp-Frontend:**
```bash
grep -r "<keyword>" $WS/QuintaApp-Frontend/src/ --include="*.jsx" --include="*.js" -l
git -C $WS/QuintaApp-Frontend log --oneline --all --grep="<keyword>"
```
Then read: feature component → hook → service call in apiClient.

**CloudHubCorp:**
```bash
grep -r "<keyword>" $WS/CloudHubCorp/src/ --include="*.php" -l
grep -r "<keyword>" $WS/CloudHubCorp/Backoffice/src/ --include="*.jsx" --include="*.astro" -l 2>/dev/null
git -C $WS/CloudHubCorp log --oneline --all --grep="<keyword>"
```
Always check `business_id` scope when reading any DB query. Flag if missing.

**Cross-project check** (always):
```bash
# If Api endpoint changes → check Frontend calls the same path
grep -r "<endpoint_path>" $WS/QuintaApp-Frontend/src/services/ 2>/dev/null
grep -r "<endpoint_path>" $WS/CloudHubCorp/ 2>/dev/null
```

Surface cross-project impact if found.

---

## Section C — Technical Assessment

```
## Technical Review — <TICKET_ID>

**Problem being solved**: ...
**Approach requested by ticket**: ...
**Repos affected**: [list of detected repos]
**Codebase findings**: (existing code, patterns, utilities discovered — per repo)
**Architecture impact**:
  - [repo-1]: [layers / areas affected]
  - [repo-2]: [layers / areas affected]
  - [repo-N]: [layers / areas affected — one line per affected repo]
**Memory context**:
  - 🔴 Errores previos aplicables: (omitir si no hay)
  - 🟢 Patrones detectados: (omitir si no hay)
  - 📋 Decisiones previas con score: (omitir si no hay)
**Epic context** (omitir si no hay overlap):
  - 🔵 En curso / ✅ Recientes / 🔜 Próximos
**Assessment**:
  - ✅ What's sound
  - ⚠️ Concerns or risks (if any)
  - 💡 Better alternatives (if applicable)
**Recommended approach**: ...
**Open questions**: ...
**Confidence Score**: [0.0 – 1.0]
```

### Confidence Score

| Range | Meaning |
|-------|---------|
| 0.9 – 1.0 | High certainty — problem and solution completely clear |
| 0.7 – 0.89 | Reasonable certainty — minor unknowns that don't block progress |
| < 0.7 | Low certainty — **dig deeper before continuing** |

If score < 0.7: explore at least one alternative, extend Open questions. Do not proceed until user resolves unknowns.

---

## Section D — Single Confirmation Prompt

Present **one combined prompt**. The user replies once. Build dynamically — include only what applies.

```
## Confirmación para arrancar — <TICKET_ID>

[Technical Assessment shown above]

---
Antes de continuar, confirmá:

**Approach**: ¿el enfoque propuesto es correcto? (o indicá ajustes)

**Documentación en Jira**: ¿Genero el análisis técnico como comentario en el ticket?
(incluye: enfoque, archivos clave, capas afectadas, riesgos, plan de testing)
[omitir si el usuario ya dijo que no quiere docs]

**Ticket en Jira** (solo si descripción incompleta):
- Falta: [qué falta]. ¿Lo completo con: [propuesta]?
[omitir si el ticket está completo]

**Transición a In Progress** (solo fresh start):
- ¿Transiciono el ticket a 'In Progress'?
[omitir si el branch ya existía]
```

Wait for the user's single reply. Apply all confirmed actions in Section H before proceeding.

### Fast path (confidence ≥ 0.9)

```
## ✅ Assessment — <TICKET_ID> [Confidence: 0.9X]

**Approach**: [one sentence]
**No risks or open questions detected.**
**Repos**: [affected repos]

¿Genero el análisis técnico en Jira? (s/n)
[Transition to In Progress si aplica — una línea]

Respondé para arrancar o indicá cambios.
```

---

## Section H — Jira Documentation (after confirmation, no extra auth needed)

Run only if the user confirmed documentation in Section D.

### H.1 — Generate technical comment

Build the comment in **Jira wiki markup** (no Markdown: use `*bold*`, `_italic_`, `{code}`, `h2.`, `h3.`, `-` for lists):

```
h2. Análisis técnico — <TICKET_ID>

h3. Enfoque confirmado
<one paragraph: what will be implemented and how>

h3. Repos y capas afectadas
<one line per repo/layer: QuintaApp-Api: handler → service → repository / QuintaApp-Frontend: feature X → apiClient / CloudHubCorp: módulo Y → DB>

h3. Archivos clave
- <relative path from workspace root>
- <relative path from workspace root>

h3. Riesgos / concerns
<list only ⚠️ items, or "Ninguno" if assessment was clean>

h3. Plan de testing
- <test that must pass — reference Make targets when applicable>
- <edge case to cover>

h3. Preguntas resueltas
<each open question with its confirmed answer, or "Ninguna" if there were none>

_Generado por /dev-assess — <ISO date>_
```

Post it:
```bash
JIRA_SKILL=${JIRA_SCRIPTS}
uv run $JIRA_SKILL/workflow/jira-comment.py add "<TICKET_ID>" "<comment text>"
```

### H.2 — Enrich ticket description (only if description is thin — under 150 chars or missing acceptance criteria)

Check ticket description length from Step 0 JSON output. If thin, add labels to flag it and update with a structured description:

```bash
JIRA_SKILL=${JIRA_SCRIPTS}

# Add label to signal the ticket has been technically assessed
uv run $JIRA_SKILL/core/jira-issue.py update "<TICKET_ID>" --labels "assessed"

# If description is thin, update with structured content via fields-json
# Description must be plain text (Jira Cloud uses ADF internally)
uv run $JIRA_SKILL/core/jira-issue.py update "<TICKET_ID>" \
  --fields-json '{"description": "<enriched description — plain text, no markup>"}'
```

Enriched description format (plain text only):
```
Objetivo: <one sentence — what this ticket achieves>

Contexto: <why this is needed — business or technical reason>

Criterios de aceptación:
<criterion 1>
<criterion 2>
<criterion 3>

Notas técnicas: ver comentario de análisis técnico.
```

### H.3 — Transition to In Progress (if fresh start and user confirmed)

```bash
JIRA_SKILL=${JIRA_SCRIPTS}
uv run $JIRA_SKILL/workflow/jira-transition.py do "<TICKET_ID>" "In Progress"
```

If transition fails (workflow constraint), continue silently — never block on this.

---

## Section G — Resumed branches (lighter version)

For branches with existing commits, skip sections E–B and present a concise re-assessment:

- Is the current implementation still the right approach?
- Any new concerns from reading existing code?
- Check if a saved assessment exists in `.ai-memory/assessments/<TICKET_ID>.json` and use it as base.
- Present condensed assessment and wait for confirmation.

If Jira documentation was never generated for this ticket (no `assessed` label), offer to generate it now.

---

## Decision Gate

After confirmation:

1. Is the approach still valid given the actual code found?
2. Did exploration reveal something new that changes scope or strategy?
3. Did historical context suggest a different direction?

If all "no changes" → proceed to development.

If any answer requires a change: update Assessment, present revised version, wait for confirmation. Max 2 iterations. After 2 cycles with score still < 0.7, escalate with full analysis and unresolved unknowns listed explicitly.

---

## Persist Assessment (always — no user confirmation needed)

After the user confirms direction:

```python
import json, os, subprocess, datetime

def workspace_root():
    try:
        g = subprocess.check_output(['git','rev-parse','--show-toplevel'], text=True).strip()
    except Exception:
        g = os.getcwd()
    p = os.path.dirname(g)
    return p if os.path.exists(os.path.join(p, 'CLAUDE.md')) else g

WS = workspace_root()
os.makedirs(f'{WS}/.ai-memory/assessments', exist_ok=True)

assessment = {
    'ticket_id': '<TICKET_ID>',
    'date': datetime.datetime.utcnow().isoformat() + 'Z',
    'summary': '<problem being solved — one sentence>',
    'repos_affected': ['<detected-repo-name>'],  # list all affected repos
    'recommended_approach': '<confirmed approach>',
    'confidence_score': 0.0,
    'concerns': ['<⚠️ items — empty if none>'],
    'key_files': ['<most relevant files — relative to workspace root>'],
    'architecture_impact': {
        # one key per affected repo, value describes layers/areas touched (or null)
        '<repo-name>': '<layers touched or null>'
    },
    'jira_doc_generated': True,
    'open_questions_resolved': ['<question: answer>'],
    'memory_context_used': '<patterns/mistakes that influenced approach — brief or null>'
}

with open(f'{WS}/.ai-memory/assessments/<TICKET_ID>.json', 'w') as f:
    json.dump(assessment, f, indent=2)
```

Overwrite if a saved assessment already exists — confirmed version is always the most current.

**On future sessions**: if Step 0 finds a saved assessment and the branch exists, skip Sections E, F, A, B — go directly to Section G. Only re-run full analysis if `confidence_score < 0.7` or user explicitly requests it.
