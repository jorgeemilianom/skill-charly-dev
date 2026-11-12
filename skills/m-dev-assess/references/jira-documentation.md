# Section H — Jira Documentation

Referencia de `m-dev-assess` — se carga solo cuando el paso corre.

## Section H — Jira Documentation (after confirmation, no extra auth needed)

Run only if the user confirmed documentation in Section D.

### H.1 — Generate technical comment

Build the comment in **Jira wiki markup** (no Markdown: use `*bold*`, `_italic_`, `{code}`, `h2.`, `h3.`, `-` for lists):

```
h2. Análisis técnico — <TICKET_ID>

h3. Enfoque confirmado
<one paragraph: what will be implemented and how>

h3. Repos y capas afectadas
<one line per repo/layer: backend-api: handler → service → repository / frontend-app: feature X → apiClient / internal-platform: módulo Y → DB>

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

_Generado por /m-dev-assess — <ISO date>_
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
