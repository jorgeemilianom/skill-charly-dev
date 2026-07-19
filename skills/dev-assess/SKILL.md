---
name: dev-assess
description: "Technical deep dive before writing any code. Reads Jira, detects affected repos, ensures each has an associated Business/<cliente> (bootstrapping via /manager-create if missing), explores the codebase with architecture-aware heuristics, loads memory/ context, produces a Technical Assessment, and — after one user confirmation — enriches the Jira ticket with structured documentation and transitions it to In Progress. Delegated to by /dev before development starts."
allowed-tools: Bash Read Write
---

# Assess — Technical Deep Dive

Run technical assessment for: **$ARGUMENTS**

Extract ticket ID (`msof-XXX`) from `$ARGUMENTS`. Normalize to uppercase: `MSOF-XXX`.

This skill performs the full pre-development analysis before any code is written. It produces a Technical Assessment that the user confirms **once** — that single confirmation also covers Jira documentation and transition to In Progress.

**Triggered by**: before starting development. Can also be invoked directly.

> Before improvising a multi-step procedure, check `scripts/local/MANIFEST.json` — see `dev/references/local-scripting.md`. If the user corrects an in-progress approach, capture it immediately — see "Capture Corrections as They Happen" in `dev/SKILL.md`.

---

## Step 0 — Parallel kickoff

**If the ticket JSON was already fetched earlier in this same session** (e.g. `/dev`'s Entry Point A
Step 1, right before delegating here) **reuse that response — do not call `jira-issue.py get` again.**
This is the single most-repeated avoidable Jira round-trip in the whole skill family: a fresh `/dev
<TICKET_ID>` start used to fetch the same ticket 3 times (once in `/dev`, twice here) before this fix.
Only fetch fresh if this is a standalone invocation (`/dev-assess <TICKET_ID>` called directly) or the
earlier read is no longer in context.

Run the rest of the following **simultaneously** before doing anything else — #1 (or the reused JSON),
#2, and #3 are independent:

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"

# 1 — Read ticket from Jira (skip and reuse if already fetched this session — see above)
TICKET_JSON=$(uv run $JIRA_SKILL/core/jira-issue.py get "<TICKET_ID>" --json)
echo "$TICKET_JSON"

# 2 — Check branch state across all sub-repos
for REPO in $REPOS; do
  git -C $WS/projects/$REPO fetch origin 2>/dev/null; git -C $WS/projects/$REPO branch -a | grep -i "<TICKET_ID>"
done

# 3 — Ensure memory/ files exist, upgrade legacy patterns entries
mkdir -p $WS/memory/tickets $WS/memory/assessments
[ -f $WS/memory/global_rules.json ] || echo '{"rules":[]}' > $WS/memory/global_rules.json
[ -f $WS/memory/patterns.json ]     || echo '{"patterns":[]}' > $WS/memory/patterns.json
jq empty $WS/memory/patterns.json 2>/dev/null || echo '{"patterns":[]}' > $WS/memory/patterns.json
jq '.patterns |= map(. + {type: (.type // "success"), frequency: (.frequency // 1), confidence: (.confidence // 0.5), tags: (.tags // [])})' \
  $WS/memory/patterns.json > $WS/memory/tmp.json && mv $WS/memory/tmp.json $WS/memory/patterns.json
[ -f $WS/memory/decisions.json ] || echo '{"decisions":[]}' > $WS/memory/decisions.json
[ -f $WS/memory/mistakes.json ]  || echo '{"mistakes":[]}' > $WS/memory/mistakes.json
[ -f $WS/memory/tickets/<TICKET_ID>.json ] || echo '{"summary":"","decisions":[],"learnings":[]}' > $WS/memory/tickets/<TICKET_ID>.json
[ -f $WS/memory/assessments/<TICKET_ID>.json ] && cat $WS/memory/assessments/<TICKET_ID>.json
cat $WS/memory/tickets/<TICKET_ID>.json
```

**Then**, once `TICKET_JSON` is in hand — extract the epic key from that **same** blob, no second API
call:

```bash
echo "$TICKET_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
epic = d.get('fields', {}).get('parent', {}).get('key') or d.get('fields', {}).get('customfield_10014')
print(epic or '')
" 2>/dev/null
```

**Detect affected repos now** (from the ticket title/description already in hand), using the keyword
table in Section A.1 below — do this as soon as the ticket JSON is available, don't wait for Section A.
This same detection is reused as-is when execution reaches Section A.1 later; no need to redo it.

**Filtered memory read** — once repos are detected, read `memory/` filtered to what's actually relevant
instead of dumping everything (unfiltered dumps get noisy and expensive as `memory/` grows — see
`memory/global_rules.json`'s `tags` field). Entries with no `tags` (or an empty array) are universal
process/git rules and always included regardless of detected repo:

```bash
# Replace TAGS with the space-separated repos detected above, e.g. TAGS='CloudHubCorp'
TAGS='<detected-repo-1> <detected-repo-2>'
TAG_FILTER=$(printf '%s\n' $TAGS | jq -R . | jq -s '.')

jq --argjson tags "$TAG_FILTER" \
  '[.rules[] | select(.status == "active") | select((.tags // []) == [] or ([.tags[]? | IN($tags[])] | any))]' \
  $WS/memory/global_rules.json

jq --argjson tags "$TAG_FILTER" \
  '[.patterns[] | select((.tags // []) == [] or ([.tags[]? | IN($tags[])] | any))]' \
  $WS/memory/patterns.json

jq --argjson tags "$TAG_FILTER" \
  '[.decisions[] | select((.tags // []) == [] or ([.tags[]? | IN($tags[])] | any))]' \
  $WS/memory/decisions.json

jq --argjson tags "$TAG_FILTER" \
  '[.mistakes[] | select((.tags // []) == [] or ([.tags[]? | IN($tags[])] | any))]' \
  $WS/memory/mistakes.json
```

Once all complete, determine:
- **Branch exists in any repo** → resumed branch. Skip sections E, F, A, B. Go to Section G.
- **No branch found** → fresh start. Continue below.

---

## Section E — Historical Context (passive, from the filtered read above)

Extract from the filtered `memory/` results from Step 0 (already scoped to detected repos + universal
rules — no need to re-filter or second-guess relevance, that filtering already happened):

1. **`memory/`** (primary): decisions, mistakes, patterns, global rules, ticket history.
2. **`~/.claude/projects/`** (secondary): style preferences and authorization rules.

Feed findings into the **Memory context** section of the Technical Assessment, grouped by confidence
(rules only — `patterns`/`decisions` don't carry a directive confidence, present them as-is):
- **`confidence ≥ 0.8`** → present as the default approach to take unless the user says otherwise.
- **`0.5 ≤ confidence < 0.8`** → present as a consideration/suggestion, not a default.
- **`confidence < 0.4`** → omit entirely, too weak a signal to surface.

**`decisions.json` entries with `outcome: "failure"` or `score < 0.4` always go in the 🔴 Errores
previos bucket below, never the optional 📋 one — this isn't discretionary.** `dev-reflect` computes
that score carefully at closing time specifically so a failed approach doesn't get tried again; folding
it into the same catch-all bucket as routine successful decisions (score shown, no distinct treatment)
was silently discarding the one signal most worth surfacing. Higher-scoring decisions stay in 📋 as
before, cited only when relevant.

Cite origin ticket when relevant: `"En MSOF-XXX se adoptó el mismo patrón y funcionó / falló porque [razón]"`. If nothing is applicable after filtering, continue silently — except the failed-decisions rule above, which is never silent when a match exists.

---

## Section F — Epic Context (passive, from Step 0)

Use the epic key extracted in Step 0. If no epic, skip silently.

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"
uv run $JIRA_SKILL/core/jira-search.py query \
  "project = $PROJECT_KEY AND parent = <EPIC_KEY> ORDER BY status, priority" \
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

Already done in Step 0 (needed there to filter the memory read) — reuse that result, don't redetect.
For reference, the table used:

> **CUSTOMIZE** — Replace the table below with your project's repos and their associated keywords.

| Keywords | Repo |
|---|---|
| API, endpoint, handler, use case, dominio, entidad, repositorio, Go, JWT, auth, migración SQL, booking, quinta, imagen | `QuintaApp-Api` |
| Frontend, UI, componente, React, vista, página, formulario, ruta, JSX, Vite, CSS | `QuintaApp-Frontend` |
| CloudHub, módulo, tenant, backoffice, Astro, PHP, m_, negocio, multi-tenant | `CloudHubCorp` |

If ambiguous or the ticket mentions multiple areas → mark all relevant repos as affected.

### A.1b — Business context association (generic — never hardcode a client name here)

For each repo detected in A.1, check whether it already has a client folder under `Business/`. This
is generic folder-scanning, the same regardless of which client/repo it's run for:

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

for REPO in <detected-repos>; do
  # 1. Exact-name convention: Business/<repo>/
  if [ -d "$WS/Business/$REPO" ]; then echo "MAPPED $REPO -> $REPO"; continue; fi
  # 2. Manifest scan: any Business/*/client.md listing this repo under `repos:`
  MATCH=$(grep -l "$REPO" $WS/Business/*/client.md 2>/dev/null | head -1)
  if [ -n "$MATCH" ]; then echo "MAPPED $REPO -> $(basename $(dirname "$MATCH"))"; continue; fi
  echo "UNMAPPED $REPO"
done
```

For each `UNMAPPED` repo (skip ones already mapped):
> "El repo `<REPO>` no tiene un cliente asociado en `Business/`. ¿A qué cliente pertenece? (uno existente o uno nuevo)"

If the user answers, invoke `/manager-create <cliente> <REPO>` and wait for it to finish (it handles
the interactive bootstrap — context, credentials placeholder, optional manifest) before resuming this
assessment. This association is a convenience for future sessions, **never a blocker for the current
ticket** — if the user wants to skip it for now, respect that and continue straight to A.2.

### A.2 — Read project context for each affected repo (in parallel)

> **CUSTOMIZE** — Replace the per-repo blocks below with your project's directory structure and architecture rules.

**For QuintaApp-Api** (if affected):
```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cat $WS/projects/QuintaApp-Api/CLAUDE.md
cat $WS/projects/QuintaApp-Api/Makefile
ls $WS/projects/QuintaApp-Api/internal/core/domain/
ls $WS/projects/QuintaApp-Api/internal/core/ports/repositories/
ls $WS/projects/QuintaApp-Api/internal/core/ports/services/
ls $WS/projects/QuintaApp-Api/internal/core/services/
ls $WS/projects/QuintaApp-Api/internal/adapters/primary/http/handlers/
ls $WS/projects/QuintaApp-Api/internal/adapters/secondary/mysql/
ls $WS/projects/QuintaApp-Api/specs/features/ 2>/dev/null
cat $WS/projects/QuintaApp-Api/spec_openapi/openapi.yaml 2>/dev/null | head -80
```
Architecture layers (dependencies flow inward): Adapters → Ports → Domain.
Coverage gate: 80% minimum on `./internal/core/...` and `./internal/adapters/primary/...`.
New domain errors: define in `errors.go`, add case in `mapError()`.

**For QuintaApp-Frontend** (if affected):
```bash
cat $WS/projects/QuintaApp-Frontend/CLAUDE.md
ls $WS/projects/QuintaApp-Frontend/src/features/
ls $WS/projects/QuintaApp-Frontend/src/services/
ls $WS/projects/QuintaApp-Frontend/src/components/
ls $WS/projects/QuintaApp-Frontend/src/pages/ 2>/dev/null
```
All API calls go through `src/services/apiClient.js` — never fetch directly from components.
Every new component needs a `.test.jsx` file alongside it.

**For CloudHubCorp** (if affected):
```bash
cat $WS/projects/CloudHubCorp/CLAUDE.md
cat $WS/projects/CloudHubCorp/Makefile
ls $WS/projects/CloudHubCorp/src/ 2>/dev/null
ls $WS/projects/CloudHubCorp/api/ 2>/dev/null
ls $WS/projects/CloudHubCorp/Backoffice/src/ 2>/dev/null
```
Quick reminders (not exhaustive — `CLAUDE.md` above is the actual source, read it before trusting this line): always scope SQL with `business_id`; prefer GET/POST, treat existing PUT/DELETE routes as legacy, don't add new ones without updating CORS/proxy/cache/tests together; always run `make build` after Backoffice changes; branch flow is `feature/*` → `develop` → `master` (never push direct to master).

Internalize CLAUDE.md rules for each affected repo before any exploration — they override default patterns.

---

## Section B — Codebase Exploration (passive)

**Check `memory/user_profile.json`'s `self_model.top_blind_spots` first** (loaded by `/dev`'s Step 0
if invoked through the core loop; read it directly here if `/dev-assess` was invoked standalone). Each
entry is a mistake verified across 2+ distinct past tickets, not a one-off — e.g. if a blind spot says
"type dynamic backend data as `any`, not `unknown`," and this ticket touches a store/type receiving
backend data, apply that directly instead of rediscovering it mid-implementation. Empty list is normal
early on — don't fabricate a match that isn't really there.

For each affected repo, run grep and git log in parallel. Use keywords from the ticket title/description.

**QuintaApp-Api:**
```bash
grep -r "<keyword>" $WS/projects/QuintaApp-Api/internal/ --include="*.go" -l
git -C $WS/projects/QuintaApp-Api log --oneline --all --grep="<keyword>"
```
Then read: handler → use case interface (port) → service implementation → repository interface → MySQL implementation → tests.

**QuintaApp-Frontend:**
```bash
grep -r "<keyword>" $WS/projects/QuintaApp-Frontend/src/ --include="*.jsx" --include="*.js" -l
git -C $WS/projects/QuintaApp-Frontend log --oneline --all --grep="<keyword>"
```
Then read: feature component → hook → service call in apiClient.

**CloudHubCorp:**
```bash
grep -r "<keyword>" $WS/projects/CloudHubCorp/src/ --include="*.php" -l
grep -r "<keyword>" $WS/projects/CloudHubCorp/Backoffice/src/ --include="*.jsx" --include="*.astro" -l 2>/dev/null
git -C $WS/projects/CloudHubCorp log --oneline --all --grep="<keyword>"
```
Always check `business_id` scope when reading any DB query. Flag if missing.

**Cross-project check** (always):
```bash
# If Api endpoint changes → check Frontend calls the same path
grep -r "<endpoint_path>" $WS/projects/QuintaApp-Frontend/src/services/ 2>/dev/null
grep -r "<endpoint_path>" $WS/projects/CloudHubCorp/ 2>/dev/null
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
**Memory context** (reglas con `confidence < 0.4` ya fueron excluidas en la lectura filtrada):
  - 🔴 Errores previos aplicables: mistakes.json + patrones `type: error` + decisiones `failure`/`score < 0.4` (omitir solo si ninguna fuente tiene algo aplicable)
  - ⭐ Reglas de alta confianza (≥0.8) — aplicar por defecto: (omitir si no hay)
  - 🟢 Patrones / reglas a considerar (0.5–0.79): (omitir si no hay)
  - 📋 Decisiones previas con score (las de score ≥ 0.4 solamente — las de abajo del umbral ya están en 🔴): (omitir si no hay)
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

### Confidence Score — derived, not a free estimate

Do not pick this number by feel. Across this project's actual history, self-estimated confidence
clustered at 0.85–0.97 regardless of how many open questions or concerns an assessment had — a ticket
with 6 open questions scored *higher* than several with zero. An unanchored self-report doesn't
discriminate risk. Compute it instead, from what Sections C's own **Assessment** and **Open questions**
already contain by the time you reach this point:

```
score = 0.95
      - 0.08 × (number of items in "Open questions")
      - 0.05 × (number of ⚠️ items in "Assessment")
score = max(score, 0.3)          # floor — don't report near-zero
score = round(score to nearest 0.05)
```

This is intentionally mechanical: if a reviewer sees a 0.9, they can recompute it themselves by
counting the two lists above — it's not an unaudited vibe. A clean assessment (no open questions, no
concerns) still lands at 0.95; one with real unresolved unknowns drops fast, exactly where the
escalation path below expects it to.

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
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"
uv run $JIRA_SKILL/workflow/jira-comment.py add "<TICKET_ID>" "<comment text>"
```

### H.2 — Enrich ticket description (only if description is thin — under 150 chars or missing acceptance criteria)

Check ticket description length from Step 0 JSON output. If thin, add labels to flag it and update with a structured description:

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"

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
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"
uv run $JIRA_SKILL/workflow/jira-transition.py do "<TICKET_ID>" "In Progress"
```

If transition fails (workflow constraint), continue silently — never block on this.

---

## Section G — Resumed branches (lighter version)

For branches with existing commits, skip sections E–B and present a concise re-assessment:

- Is the current implementation still the right approach?
- Any new concerns from reading existing code?
- Check if a saved assessment exists in `memory/assessments/<TICKET_ID>.json` and use it as base.
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
        g = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip()
    except Exception:
        g = os.getcwd()
    d = g
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, 'CLAUDE.md')) and os.path.exists(os.path.join(d, 'config.example.sh')):
            return d
        d = os.path.dirname(d)
    return g

WS = workspace_root()
os.makedirs(f'{WS}/memory/assessments', exist_ok=True)

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

with open(f'{WS}/memory/assessments/<TICKET_ID>.json', 'w') as f:
    json.dump(assessment, f, indent=2)
```

Overwrite if a saved assessment already exists — confirmed version is always the most current.

**On future sessions**: if Step 0 finds a saved assessment and the branch exists, skip Sections E, F, A, B — go directly to Section G. Only re-run full analysis if `confidence_score < 0.7` or user explicitly requests it.
