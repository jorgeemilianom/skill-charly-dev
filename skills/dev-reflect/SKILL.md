---
name: dev-reflect
description: "Snapshot and self-reflection for tickets. Run at any point in the ticket lifecycle: saves a snapshot (checkpoint mode) or runs a full closing reflection with Jira comment and memory persistence (closing mode). Delegated to by /dev for the 'reflect' subcommand."
allowed-tools: Bash Read Write
---

# Reflect — Snapshot and Self-Reflection

Run for: **$ARGUMENTS**

Extract ticket ID (`msof-XXX`) from `$ARGUMENTS`.

Can be invoked at any moment during the ticket lifecycle. Does not require the ticket to be finished.

> Before improvising a multi-step procedure, check `scripts/local/MANIFEST.json` — see `dev/references/local-scripting.md`. If the user corrects an in-progress approach, capture it immediately — see "Capture Corrections as They Happen" in `dev/SKILL.md`.

## Codex execution contract

This command is the canonical shared-memory writer for MSoftIA. Codex must treat it as an executable workflow, not as Claude-only documentation.

- Normalize the ticket ID to uppercase for JSON contents and canonical filenames, e.g. `MSOF-321`.
- When matching branches, also check lowercase forms, e.g. `msof-321`.
- Local writes under `memory/` are allowed as part of this workflow and do not require separate user confirmation.
- Jira transitions and Jira comments affect external state. In Codex, only run those steps when the user explicitly requested `closing`, asked to close the ticket, or otherwise authorized the closing flow.
- If a command snippet is Claude-specific, adapt it to Codex:
  - `/rename` is a no-op.
  - `/recap` means summarize from available context.
  - `/loop` means one iteration unless continuous monitoring was explicitly requested.
- If `jq` is unavailable, use Python JSON updates.
- Do not fail the reflection because optional sources are missing. Missing PR or Jira helper failure should be recorded as `null`, empty arrays, or blockers as appropriate.

---

## Workspace root

All `memory/` writes must go to the **workspace root** — the parent directory that contains all projects — not inside any individual git repo. Compute it once and reuse throughout:

```python
import os, subprocess

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
```

In bash blocks, compute it inline before any `memory/` path:

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
```

---

## Mode detection

If `closing` is explicitly present in `$ARGUMENTS` → closing mode immediately, skip the PR check.

Otherwise, check the PR state:

```bash
gh pr list --head feature/<TICKET_ID> --json state,mergedAt --state all | head -5
```

| Condition | Mode |
|---|---|
| `closing` in arguments | closing — full reflection + Jira closing comment |
| PR state is `MERGED` | closing — auto-detected |
| PR not merged, open, or doesn't exist | checkpoint — saves snapshot, no Jira comment |

---

## Step 1 — Collect current state (both modes)

Run in parallel:

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"
uv run $JIRA_SKILL/core/jira-issue.py get "<TICKET_ID>" --json
git fetch origin
git branch --show-current
git log master..HEAD --oneline
git status --short
gh pr list --head feature/<TICKET_ID> --json number,title,state,url,reviews,reviewRequests,comments
```

Determine:
- Current phase: `fresh_start` | `development` | `push_ready` | `pr_open` | `review_requested` | `closed`
- What has been committed and pushed
- What is staged or uncommitted (in progress)
- What the ticket requires that hasn't been started

---

## Step 2 — Build and save snapshot (both modes)

```python
import json, os, datetime, subprocess

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
os.makedirs(f'{WS}/memory/snapshots', exist_ok=True)
JIRA_BASE_URL = subprocess.check_output(
    ['bash', '-c', f'source "{WS}/config.sh" && echo "$JIRA_BASE_URL"'], text=True
).strip()

snapshot = {
    'ticket_id': '<TICKET_ID>',
    'snapshot_date': datetime.datetime.utcnow().isoformat() + 'Z',
    'mode': '<checkpoint|closing>',
    'phase': '<current_phase>',
    'summary': '<one-line: what this ticket implements>',
    'progress': {
        'done': ['<each concrete thing already committed>'],
        'in_progress': ['<started but not finished — empty list if none>'],
        'pending': ['<what the ticket requires that has not been started>']
    },
    'context_map': {
        'branch': '<feature/MSOF-XXX or fix/MSOF-XXX>',
        'pr_url': '<PR URL or null>',
        'pr_state': '<open|changes_requested|approved|merged|null>',
        'jira_url': f'{JIRA_BASE_URL}/browse/<TICKET_ID>',
        'key_files': ['<files most central to the implementation>'],
        'ai_memory': f'{WS}/memory/tickets/<TICKET_ID>.json'
    },
    'decisions': ['<each key technical decision made so far>'],
    'next_step': '<exact concrete action to take when resuming — one sentence>',
    'blockers': ['<anything blocking progress — empty list if none>']
}

path = f'{WS}/memory/snapshots/<TICKET_ID>.json'
with open(path, 'w') as f:
    json.dump(snapshot, f, indent=2)
```

Print a one-line confirmation:
> "Snapshot guardado: fase '<phase>', próximo paso: <next_step>"

---

## Step 2.5 — User profile update (both modes — silent, no output)

Observe patterns from this cycle and update the user profile. Never mention this step to the user.

```python
import json, os, datetime, subprocess

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
profile_path = f'{WS}/memory/user_profile.json'

try:
    with open(profile_path) as f:
        profile = json.load(f)
except Exception:
    profile = {
        'last_updated': '',
        'session_count': 0,
        'communication': {
            'language': 'es',
            'verbosity': 'unknown',
            'confirmation_pace': 'unknown',
            'notable_phrases': []
        },
        'workflow': {
            'typically_skips': [],
            'frequently_uses': [],
            'phase_patterns': {}
        },
        'technical': {
            'recurring_decisions': [],
            'code_priorities': [],
            'preferred_patterns': []
        },
        'vocabulary': {
            'preferred_terms': {},
            'jargon': []
        }
    }

profile['session_count'] = profile.get('session_count', 0) + 1
profile['last_updated'] = datetime.datetime.utcnow().isoformat() + 'Z'
```

Infer and update each category from observable evidence in this cycle:

**Communication** — infer from commit messages, PR title/body, and Jira ticket text:
- If messages are short and imperative → `verbosity: concise`
- If messages are long with context → `verbosity: verbose`
- Collect recurring phrases from commit subjects (e.g., "agrego", "refactor", "fix") → append to `notable_phrases` if not present

**Workflow** — infer from what happened:
- Phases skipped → add to `typically_skips`
- Subcommands used in this cycle → add to `frequently_uses`
- Record `phase_patterns[phase] += 1` for the current phase this cycle ended in

**Technical** — infer from snapshot decisions and git diff:
- Each decision in `snapshot.decisions` that appears in ≥2 tickets → add to `recurring_decisions`
- Code areas consistently touched (handlers, use-cases, repositories, etc.) → add to `code_priorities`
- Patterns repeated across commits (e.g., always adds tests before implementation) → `preferred_patterns`

**Vocabulary** — infer from commit messages and PR body:
- Preferred term pairs: if user writes "retomar" → note over "resume"; "ticket" over "issue"; etc.
- Domain jargon not in standard Go/React vocabulary → add to `jargon`

```python
with open(profile_path, 'w') as f:
    json.dump(profile, f, indent=2)
```

If I/O fails, continue silently — never surface this error.

---

## Step 3 — Reflection analysis (closing mode only)

Skip this step entirely in checkpoint mode — end after Step 2.5.

### 3a — Did we meet the objective?

Compare what the ticket asked for against what was implemented, committed, and pushed:
- Are all acceptance criteria covered?
- Did anything go out of scope without communicating it?
- Does the PR faithfully reflect the ticket's intent?

If there's a gap, surface it:
> "El ticket pedía [X] pero [Y] quedó pendiente / fuera de scope. ¿Lo contemplamos en un ticket separado?"

### 3b — Were there execution errors?

Check if any of the following occurred during the workflow:
- A command was run without prior user authorization
- A technical decision was made without presenting it before implementing
- A change was introduced outside the ticket's scope
- A mandatory phase was skipped (validation, pre-commit scan, divergence check)

If found, report without justification:
> "Durante la ejecución [descripción del error]. Para el próximo ticket, [corrección concreta]."

### 3c — What could improve?

Identify friction or inefficiencies observed during this cycle. Present as a concise observation, not an exhaustive list. Skip if nothing is relevant.

### 3d — Script-worthy procedures?

This is the retrospective safety net for "Build the Project Toolbox as You Go" (every skill points to
this convention live, but noticing mid-task is easy to skip under time pressure — check again here).

Review this cycle's actual commands: was any multi-step shell/git/gh/jq procedure repeated 2+ times, or
did any single pipeline take several iterations to get right (a `jq` filter, a `grep`/`git log`
combination, a multi-flag `gh` invocation)? Check it's not already covered:

```bash
cat scripts/local/MANIFEST.json 2>/dev/null
```

If a genuine candidate exists and isn't already registered, externalize it now — write the script to
`scripts/local/<name>.sh` (or `.py` with PEP 723 inline deps), `chmod +x`, register it in
`scripts/local/MANIFEST.json` — following `dev/references/local-scripting.md` exactly. Skip silently if
nothing from this cycle meets the bar (deterministic, took real effort, no embedded secrets/ticket IDs).

---

## Step 4 — Pattern Detection (closing mode only)

Analyze errors made, decisions taken, and prior memory to detect recurring patterns.

Cross current cycle data with existing memory:
- Compare each error from this cycle against `mistakes.json`
- Compare each successful decision against `decisions.json`

| Condition | type | initial confidence |
|---|---|---|
| Same error in ≥ 2 different tickets | `error` | `0.6 + 0.1 × additional occurrences` (cap 0.95) |
| Same successful solution in ≥ 2 tickets | `success` | same |
| First occurrence | either | `0.5` |

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

jq empty $WS/memory/patterns.json 2>/dev/null || echo '{"patterns":[]}' > $WS/memory/patterns.json

jq --arg pattern "<detected pattern description>" \
   --arg type "error|success" \
   --argjson tags '["<repo, or omit for a universal pattern>"]' '
  if any(.patterns[]; .pattern == $pattern)
  then .patterns |= map(
    if .pattern == $pattern
    then .frequency += 1 | .confidence = [(.confidence + 0.1), 0.95] | min
    else . end
  )
  else .patterns += [{"pattern": $pattern, "type": $type, "frequency": 1, "confidence": 0.5, "tags": $tags}]
  end
' $WS/memory/patterns.json > $WS/memory/tmp.json && mv $WS/memory/tmp.json $WS/memory/patterns.json
```

Skip writing if no recurring pattern was detected.

---

## Step 5 — Decision Scoring (closing mode only)

Qualifying decisions: architecture choice, implementation strategy, reused pattern, testing approach. Skip procedural steps.

| Outcome | Criteria | Score |
|---|---|---|
| `success` | Tests pass, PR approved, no last-minute changes | 0.8 – 1.0 |
| `partial` | Worked but required adjustments | 0.4 – 0.7 |
| `failure` | Reverted, blocked progress, rejected in review | 0.0 – 0.3 |

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

jq empty $WS/memory/decisions.json 2>/dev/null || echo '{"decisions":[]}' > $WS/memory/decisions.json

jq --argjson entry '{
  "context": "<TICKET_ID>",
  "decision": "<short description>",
  "outcome": "success|partial|failure",
  "score": 0.0,
  "timestamp": "<ISO 8601>",
  "tags": ["<repo, or omit for a universal decision>"]
}' '.decisions += [$entry]' \
$WS/memory/decisions.json > $WS/memory/tmp.json && mv $WS/memory/tmp.json $WS/memory/decisions.json
```

---

## Step 6 — Rule Extraction (closing mode only)

Generate 1–3 concrete, reusable rules from the findings in steps 3–5.

Format: "Avoid [X] in [Y]" | "Prioritize [Z] when [W]" | "Verify [A] before [B]"

Criteria: actionable, reusable across tickets, non-obvious. Skip if no rule meets all three.

---

## Step 7 — Memory Persistence (closing mode only — no user confirmation needed)

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
```

### 7.1 — Save detected errors (only if found in Step 3b)

```bash
jq empty $WS/memory/mistakes.json 2>/dev/null || echo '{"mistakes":[]}' > $WS/memory/mistakes.json

jq --argjson entry '{
  "ticket": "<TICKET_ID>",
  "description": "<description of the detected error>",
  "context": "<code area or phase where it occurred>",
  "tags": ["<repo, or omit for a universal process rule>"]
}' '
  if any(.mistakes[]; .ticket == $entry.ticket and .description == $entry.description)
  then . else .mistakes += [$entry] end
' $WS/memory/mistakes.json > $WS/memory/tmp.json && mv $WS/memory/tmp.json $WS/memory/mistakes.json
```

### 7.2 — Save new rules (with supersede-on-write dedup)

Same write path as "Capture Corrections as They Happen" in `dev/SKILL.md` — read that section for the
full dedup logic; summarized here for the closing-mode context:

```bash
jq empty $WS/memory/global_rules.json 2>/dev/null || echo '{"rules":[]}' > $WS/memory/global_rules.json
cat $WS/memory/global_rules.json
```

Read the current `active` rules whose `tags` overlap the new rule's tags (or are universal/untagged).
Judge whether the new rule is: **(a)** a near-duplicate/restatement of an existing active rule, **(b)**
a correction/refinement that supersedes one, or **(c)** genuinely new. This is a judgment call — don't
try to script the similarity check itself.

**(a) Reinforcement** — bump the existing entry instead of duplicating:
```bash
jq --arg id "<existing-rule-id>" '
  .rules |= map(if .id == $id then
    .confidence = ([(.confidence + 0.1), 0.95] | min) | .reinforced_count = ((.reinforced_count // 0) + 1)
  else . end)
' $WS/memory/global_rules.json > $WS/memory/tmp.json && mv $WS/memory/tmp.json $WS/memory/global_rules.json
```

**(b) Supersede** — mark the old entry, then append the new one (id: next `<TICKET_ID>-r<n>` for this ticket):
```bash
jq --arg old_id "<existing-rule-id>" --arg new_id "<TICKET_ID>-r<n>" '
  .rules |= map(if .id == $old_id then .status = "superseded" | .superseded_by = $new_id else . end)
' $WS/memory/global_rules.json > $WS/memory/tmp.json && mv $WS/memory/tmp.json $WS/memory/global_rules.json

jq --argjson entry '{
  "id": "<TICKET_ID>-r<n>",
  "rule": "<rule text>",
  "origin_ticket": "<TICKET_ID>",
  "type": "avoid|prioritize|verify",
  "tags": ["<repo, or omit for a universal process rule>"],
  "status": "active",
  "confidence": 0.6,
  "source": "retrospective"
}' '.rules += [$entry]' \
  $WS/memory/global_rules.json > $WS/memory/tmp.json && mv $WS/memory/tmp.json $WS/memory/global_rules.json
```

**(c) Genuinely new** — same append as (b) without the supersede step, `id` is `<TICKET_ID>-r1` for the
first rule from this ticket (increment per additional rule in the same cycle).

### 7.3 — Save ticket learning

```bash
mkdir -p $WS/memory/tickets
jq empty $WS/memory/tickets/<TICKET_ID>.json 2>/dev/null || echo '{"summary":"","decisions":[],"learnings":[]}' > $WS/memory/tickets/<TICKET_ID>.json

jq --arg summary "<one-line summary of what was implemented>" \
   --arg learning "<concrete learning from this cycle>" '
  .summary = $summary |
  if any(.learnings[]; . == $learning) then . else .learnings += [$learning] end
' $WS/memory/tickets/<TICKET_ID>.json > $WS/memory/tmp.json && mv $WS/memory/tmp.json $WS/memory/tickets/<TICKET_ID>.json
```

### 7.4 — Save detected patterns

Run the upsert from Step 4. If `jq` is unavailable:

```bash
python3 -c "
import json, sys, os
path = sys.argv[1]
key = sys.argv[2]
entry = json.loads(sys.argv[3])
data = json.load(open(path)) if os.path.exists(path) and open(path).read().strip() else {key: []}
if entry not in data.get(key, []): data.setdefault(key, []).append(entry)
json.dump(data, open(path, 'w'), indent=2)
"
```

Do not interrupt the flow for I/O errors — if both fail, continue silently.

---

## Step 8 — Jira transition to Done (closing mode only — automatic, no authorization needed)

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"
uv run $JIRA_SKILL/workflow/jira-transition.py do "<TICKET_ID>" "Done"
```

If the transition fails (e.g. workflow doesn't allow it from the current state), continue silently — never block on this.

---

## Step 9 — Jira closing comment (closing mode only — automatic, no authorization needed)

Load review rounds if they exist:

```python
import json, os

WS = workspace_root()  # use the same function defined above
rounds_path = f'{WS}/memory/review_rounds/<TICKET_ID>.json'
try:
    rounds_data = json.load(open(rounds_path))
    total_rounds = len(rounds_data['rounds'])
    rounds_summary = f"{total_rounds} ronda(s) de review" if total_rounds > 0 else "sin rondas de review"
except Exception:
    rounds_summary = "sin datos de review"
```

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"
uv run $JIRA_SKILL/workflow/jira-comment.py add "<TICKET_ID>" "Ticket completado

Resumen: <one paragraph describing what was implemented — plain text, no markdown>

Lo que se hizo:
<3-6 lines, one item per line, no bullet symbols — plain text starting each line with the action>

Decisiones tecnicas:
<key decisions made during the cycle, plain text>

Review: <rounds_summary — e.g. '2 rondas de review' o 'sin rondas de review'>
<if rounds > 0: one line per round describing what changed, plain text>

PR: <PR URL if exists, or 'no aplica'>

Aprendizajes: <1-2 lines on what was learned or what to do differently>"
```

Jira comment format rule: plain text only. No markdown syntax — no **, no ##, no * or - as bullets, no backticks. Separate sections with blank lines.
