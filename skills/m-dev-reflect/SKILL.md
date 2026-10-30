---
name: m-dev-reflect
description: "Snapshot and self-reflection for tickets. Run at any point in the ticket lifecycle: saves a snapshot (checkpoint mode) or runs a full closing reflection with Jira comment and memory persistence (closing mode). Delegated to by /m-dev for the 'reflect' subcommand."
allowed-tools: Bash Read Write
---

# Reflect — Snapshot and Self-Reflection

Run for: **$ARGUMENTS**

Extract ticket ID (`proj-XXX`) from `$ARGUMENTS`.

Can be invoked at any moment during the ticket lifecycle. Does not require the ticket to be finished.

> Before improvising a multi-step procedure, check `scripts/local/MANIFEST.json` — see `m-dev/references/local-scripting.md`. If the user corrects an in-progress approach, capture it immediately — see "Capture Corrections as They Happen" in `m-dev/SKILL.md`.

## Codex execution contract

This command is the canonical shared-memory writer for this workspace — Codex must treat it as an executable
workflow, not as Claude-only documentation. Generic Claude→Codex command translations (`/rename`,
`/recap`, `/loop`, `jq` unavailability, etc.) live centrally in `agent-context.md`'s "Command Resolution
Rules" — not repeated here. What's specific to *this* skill:

- Normalize the ticket ID to uppercase for JSON contents and canonical filenames, e.g. `PROJ-321`.
- When matching branches, also check lowercase forms, e.g. `proj-321`.
- Local writes under `memory/` are allowed as part of this workflow and do not require separate user
  confirmation (matches `agent-context.md`'s general memory-write rule).
- Jira transitions and Jira comments affect external state — same general rule as `agent-context.md`'s
  "Workspace Memory" section (ask unless the user explicitly requested the flow that includes them): in
  Codex specifically, only run Steps 8-9 (Done transition, closing comment) when the user explicitly
  requested `closing`, asked to close the ticket, or otherwise authorized the closing flow.
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
uv run $JIRA_SKILL/core/jira-issue.py --json get "<TICKET_ID>" | python3 "$WS/scripts/jira_trim.py"
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
        'branch': '<feature/PROJ-XXX or fix/PROJ-XXX>',
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

import sys
sys.path.insert(0, f'{WS}/scripts')
from memory_store import locked, write_json_atomic  # lock + atomic replace
with locked():
    write_json_atomic('snapshots/<TICKET_ID>.json', snapshot)
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
import sys
sys.path.insert(0, f'{WS}/scripts')
import memory_store as ms

# Missing file -> the default below. Existing but unparseable -> ms.MemoryCorrupt is raised: skip
# this step (and tell the user at the end) instead of resetting a profile built over many sessions.
profile = ms.read_json('user_profile.json', default={
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
    })

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
with ms.locked():
    ms.write_json_atomic('user_profile.json', profile)
```

If I/O fails, continue silently — never surface this error. Exception: `ms.MemoryCorrupt` (the
profile exists but doesn't parse) — skip the write and mention it in one line at the end, so the
user can restore it (`/m-memory restore user_profile.json`).

**Self-model recompute** (cheap, run every cycle — same silent, no-confirmation-needed spirit as
the rest of this step): re-derive the recurring cross-ticket blind spots and store them as the
agent's own model in `memory/cognition.json` (not in the user's profile — the legacy
`user_profile.self_model` stays as read-only history):

```bash
python3 "$WS/scripts/self_model.py" --refresh
```

Exit 2 means a memory file couldn't be read: the stored model is left as it was (never replaced by
an empty list) — mention it in one line at the end.

Empty `top_blind_spots` is a normal, valid result — it means nothing has independently recurred
across 2+ distinct tickets yet, not that the mechanism is broken. Don't force a result to appear
non-empty.

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
`scripts/local/MANIFEST.json` — following `m-dev/references/local-scripting.md` exactly. Skip silently if
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

# Upsert: same text -> frequency += 1, confidence += 0.1 (cap 0.95), ticket added to origin_tickets
python3 $WS/scripts/memory_store.py upsert-pattern --type error|success --ticket "<TICKET_ID>" \
  --tags "<repo,… or empty for a universal pattern>" --pattern "<detected pattern description>"
```

`origin_tickets` (added alongside `frequency`) is what lets `scripts/self_model.py` tell "the same
lesson independently rediscovered across different tickets" apart from "recorded twice in one
closing session" — track it even though nothing reads it directly here. Skip writing if no
recurring pattern was detected.

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

python3 $WS/scripts/memory_store.py add-decision --context "<TICKET_ID>" --outcome success|partial|failure \
  --score 0.0 --tags "<repo,… or empty for a universal decision>" --decision "<short description>"
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
python3 $WS/scripts/memory_store.py add-mistake --ticket "<TICKET_ID>" \
  --context "<code area or phase where it occurred>" --tags "<repo,… or empty for a universal process rule>" \
  --description "<description of the detected error>"
```

### 7.2 — Save new rules (with supersede-on-write dedup)

This section is canonical for the dedup mechanism — `m-dev/SKILL.md`'s "Capture Corrections as They
Happen" points back here rather than restating it, only differing in `confidence`/`source` (0.9 /
`live_correction` there vs. 0.6 / `retrospective` here).

**Run the similarity pre-check before judging — do not skip straight to "genuinely new."** History
shows why: with an open-ended "does this look familiar?" call, 126 of 137 active rules were never
reinforced and almost none ever superseded. Forcing concrete candidates into view gives something
specific to accept or reject instead of an abstract absence to default past. The pre-check scores
`max(Jaccard, containment)` over significant words (Spanish + English stopwords), so a short
restatement of a long rule still surfaces:

```bash
python3 $WS/scripts/memory_store.py similar-rules --tags "<repo,… or empty>" --rule "<rule text derived from this cycle>"
```

For each printed candidate you **must** explicitly decide, for that specific rule (not in the
abstract): is the new observation **(a)** the same thing restated, **(b)** a refinement that should
supersede it, or **(c)** actually different despite the overlap? Word overlap can't see a paraphrase
in another language — if you remember an equivalent rule that wasn't printed, treat it as a candidate
too. Only fall through to "genuinely new" after explicitly ruling them out.

**(a) Reinforcement** — bump the existing entry instead of duplicating (+0.1 confidence, cap 0.95,
`reinforced_count`++, `last_seen` = today; `--tags` widens its scope if this ticket is another repo):
```bash
python3 $WS/scripts/memory_store.py reinforce-rule <existing-rule-id> --ticket "<TICKET_ID>" [--tags "<repo>"]
```

**(b) Supersede** — marks the old entry `superseded` and appends the new one in a single locked write:
```bash
python3 $WS/scripts/memory_store.py add-rule --supersedes <existing-rule-id> --source retrospective \
  --ticket "<TICKET_ID>" --type avoid|prioritize|verify --tags "<repo,… or empty>" --rule "<rule text>"
```

**(c) Genuinely new** — same as (b) without `--supersedes`. The id (`<TICKET_ID>-r<n>`, next free one)
is assigned under the lock and printed — never pick it by hand (that's how duplicate ids appeared).

### 7.3 — Save ticket learning

```bash
python3 $WS/scripts/memory_store.py ticket-learning "<TICKET_ID>" \
  --summary "<one-line summary of what was implemented>" --learning "<concrete learning from this cycle>"
```

### 7.4 — Save detected patterns

Run the upsert from Step 4.

### 7.5 — Contrast experiences, update goals, refresh the self-model (both modes when there's evidence)

Follow the cognitive protocol in `agent-context.md` ("Protocolo cognitivo"). After the learnings above are saved:

1. **Evaluate this ticket's pending predictions** — the ones registered in `/m-dev-assess` or during
   development:
   ```bash
   python3 $WS/scripts/cognition.py status | python3 -c "import json,sys;[print(e) for e in json.load(sys.stdin)['episodes']['pending']]"
   ```
   For each one whose result is now known, record what happened — `observation` (facts), `interpretation`
   (a possible explanation, not a certainty), `adjustment` (what to do differently), `evidence`
   (verifiable refs: CI run, PR, commit, log line, Jira comment) and `outcome` (`true`/`false`, or `null`
   if it can't be determined — never force a verdict):
   ```bash
   echo '{"id":"ep-0007","observation":"...","interpretation":"...","adjustment":"...","evidence":["PR #42","CI run 123"],"outcome":false}' \
     | python3 $WS/scripts/memory_store.py cognitive evaluate
   ```
   Still unknown (e.g. depends on prod traffic) → leave it pending and say so. Evaluations are final;
   to correct one, register a new experience with `"corrects": "<id>"`.
2. **Goals** — close what this ticket fulfilled (`update-goal` with `status: done` + `evidence`), block
   what's waiting on someone (`blocked_reason`), or open a goal for a commitment that outlives the
   session (follow-up, monitoring, a promised check). Never mark done without evidence.
3. **Beliefs** — only when 2+ evaluated episodes support the same claim (or one contradicts an active
   belief): `belief` (with `supersedes` to revise one). Confidence can't exceed what the evidence allows.
4. `python3 "$WS/scripts/self_model.py" --refresh` (after the writes above, so it sees them).

All writes above go through `scripts/memory_store.py` (lock, atomic replace, schema check, compiled
digests regenerated). Exit code 2 means a memory file exists but doesn't parse — the write was
refused on purpose instead of resetting it: mention it in one line at the end (`/m-memory restore`)
and continue the closing. Any other I/O error: continue silently.

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
