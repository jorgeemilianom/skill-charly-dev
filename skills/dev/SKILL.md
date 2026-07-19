---
name: dev
description: "Main development orchestrator. Accepts a PROJ-XXX ticket ID, a freeform idea with no ticket yet, a PR URL (own PR), or 'review <PR URL>' (teammate's PR). Checks setup prerequisites first, then runs the core ticket loop (branch setup, development, validation, commit, push) and routes everything else to sibling dev-* skills: dev-setup, dev-create, dev-assess, dev-pr, dev-reflect, dev-resume, dev-review, dev-migration, dev-status, dev-db-sync."
allowed-tools: Bash Read Write
---

# Dev — Development Workflow Orchestrator

Execute the development workflow for: **$ARGUMENTS**

`$ARGUMENTS` can be:
- A ticket ID: `msof-XXX` — runs the full core loop (Entry point A)
- A freeform idea/requirement with no ticket ID yet — routes to `/dev-create`
- A PR URL (your own PR): `https://github.com/.../pull/123` — Entry point B
- `review <PR URL>` — routes to `/dev-review`
- A ticket ID with a subcommand — routes to the matching sibling skill

---

## Role: Technical Advisor, Not Just Executor

Throughout this workflow, act as a **senior engineer** familiar with the three MSoftIA codebases. This means:

- **Challenge questionable approaches**: If the ticket or the user requests something suboptimal, say so — with reasoning — before implementing.
- **Surface existing patterns**: Search the codebase for reusable utilities before writing new code.
- **Acknowledge uncertainty**: When entering an unfamiliar area, explore deeply before proposing solutions. If still uncertain, say so explicitly.
- **Defer to the user**: If the user insists after hearing the concerns, proceed with their approach.

---

## Workspace Root Resolution

This applies across `/dev`, `/manager`, and every sibling skill — the exact same 3-line `WS="..."`
snippet opens nearly every bash block in this skill family. It's inlined rather than sourced from
`scripts/workspace-root.sh` on purpose: a skill can't source that script before it knows where the
workspace root is, which is exactly the problem the snippet solves. Keep the inline copies and
`scripts/workspace-root.sh` in sync if the algorithm ever changes — it walks up looking for a directory
with **both** `CLAUDE.md` and `config.example.sh`, not `CLAUDE.md` alone, because sub-repos under
`projects/` and some `Business/<cliente>/` folders have their own local `CLAUDE.md` that would
otherwise false-match. Once `$WS` is known, `source "$WS/scripts/workspace-env.sh"` loads `config.sh`
plus the `JIRA_SKILL`/`PROJECTS_PREFIX` vars most steps need — that part has no bootstrap problem, so
it's a real shared script, not a duplicated snippet.

---

## Build the Project Toolbox as You Go

This applies across `/dev` and every sibling skill. Before improvising a multi-step shell/git/gh/jq
procedure, check `scripts/local/MANIFEST.json` — a script may already exist for it. When you notice
a deterministic, repeatable procedure that took real effort to get right, externalize it there instead
of re-deriving it next session. See [references/local-scripting.md](references/local-scripting.md) for
the full convention (when to script, how to register it, naming).

---

## Capture Corrections as They Happen

This applies across `/dev` and every sibling skill, same as the toolbox convention above — it's a local,
reversible write, so it doesn't need user confirmation (matches `agent-context.md`'s "local writes...
do not require confirmation").

When the user directly corrects an in-progress approach ("no, hacelo así", "eso no, mejor..."), that's
the strongest possible learning signal — stronger than anything reconstructed retrospectively at
`/dev-reflect` closing, because it's a direct, explicit statement instead of an inference. Capture it
immediately, don't wait for closing:

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
jq empty $WS/memory/global_rules.json 2>/dev/null || echo '{"rules":[]}' > $WS/memory/global_rules.json
cat $WS/memory/global_rules.json
```

Same dedup logic as `dev-reflect` Step 7.2 applies here — read the current `active` rules whose `tags`
overlap the current repo(s)/topic (or are universal), and judge: **reinforcement** (bump `confidence`
+`reinforced_count` on the existing entry), **supersede** (mark the old entry `status: "superseded"`
+`superseded_by`, append the new one), or **genuinely new** (just append). The only difference from the
closing-mode write: `confidence` starts at **`0.9`** (not `0.6`) and `source` is `"live_correction"` (not
`"retrospective"`) — a direct correction deserves more weight than a retrospective inference from the
first mention.

```bash
jq --argjson entry '{
  "id": "<TICKET_ID>-r<n>",
  "rule": "<rule text derived from the correction>",
  "origin_ticket": "<TICKET_ID>",
  "type": "avoid|prioritize|verify",
  "tags": ["<repo, or omit for a universal process rule>"],
  "status": "active",
  "confidence": 0.9,
  "source": "live_correction"
}' '.rules += [$entry]' \
  $WS/memory/global_rules.json > $WS/memory/tmp.json && mv $WS/memory/tmp.json $WS/memory/global_rules.json
```

One line, no ceremony: *"Guardé esto como regla en memoria para no repetirlo."* — same tone as the local
scripting convention's confirmation line.

---

## Phase -1: Preconditions

Run before anything else, every invocation — cheap, no prompts:

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
[ -f "$WS/config.sh" ] && { [ -f ~/.env.jira ] || [ -f ~/.jira/profiles.json ]; } && gh auth status &>/dev/null && echo OK || echo MISSING
```

If `MISSING`: "Faltan prerequisitos antes de arrancar (credenciales o config). ¿Corro `/dev-setup` para
revisar qué falta?" If confirmed, invoke `/dev-setup` and, once it reports everything OK, resume with
the original `$ARGUMENTS`. If the user declines, proceed anyway but expect the affected step to fail.

---

## Phase 0: Routing

Parse `$ARGUMENTS` and dispatch immediately.

### Dispatch table

| Argument | Action |
|----------|--------|
| `setup` | → `/dev-setup` |
| freeform idea/description, no ticket ID | → `/dev-create` |
| starts with `review ` + URL | → `/dev-review` |
| URL containing `http` or `/pull/` | Entry point B (below) — Own PR |
| `msof-XXX migration` | → `/dev-migration <TICKET_ID>` |
| `msof-XXX resume` | → `/dev-resume <TICKET_ID>` |
| `msof-XXX reflect` | → `/dev-reflect <TICKET_ID>` |
| `msof-XXX status` | → `/dev-status <TICKET_ID>` |
| `status` (no ticket ID) | → `/dev-status` |
| `msof-XXX` (no subcommand) | Entry point A (below) — full core loop |
| `db-sync <project>` | → `/dev-db-sync <project>` |
| `msof-XXX db-sync <project>` | → `/dev-db-sync <project>` (ticket ID for context only) |
| `db-sync config <project>` | → `/dev-db-sync config <project>` |

For routed sibling skills: invoke the target with the arguments and follow its instructions entirely. Do not proceed to any other phase in this file.

---

### Entry point B — Own PR (resume / review comments)

Use when the argument is a GitHub PR URL you authored.

```bash
gh pr view "$ARGUMENTS" --json title,body,headRefName,baseRefName,state,url,reviews,comments,reviewRequests
```

1. Extract ticket ID from the branch name (e.g. `feature/msof-42` → `MSOF-42`).
2. Read the Jira ticket:
   ```bash
   WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
   while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
   [ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
   source "$WS/scripts/workspace-env.sh"
   uv run $JIRA_SKILL/core/jira-issue.py get "<TICKET_ID>" --json
   ```
3. Rename session: `/rename MSOF-XXX | <ticket summary>`
4. Check out the branch: `git fetch origin && git checkout <branch>`
5. Show state: `git log master..HEAD --oneline && git status`
6. Invoke `/dev-pr <TICKET_ID> review` with the detected review comments.

---

### Entry point A — Ticket ID (full core loop)

**Step 0 — Load user profile (silent — adapt behavior, no output):**

```python
import json, os, subprocess

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
try:
    profile = json.load(open(f'{WS}/memory/user_profile.json'))
except Exception:
    profile = {}
```

Apply the profile throughout this session:
- `communication.verbosity == concise` → keep responses tight, skip preamble
- `communication.confirmation_pace == fast` → don't over-explain before each action
- `workflow.typically_skips` → auto-proceed through those steps without asking
- `workflow.frequently_uses` → proactively suggest those subcommands when relevant
- `vocabulary.preferred_terms` → use the user's own words
- `technical.recurring_decisions` → surface them as the default option when the same choice arises

**Step 1 — Read Jira ticket:**
```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"
uv run $JIRA_SKILL/core/jira-issue.py get "<TICKET_ID>" --json
```

**Step 2 — Rename session:** `/rename MSOF-XXX | <ticket summary>`

**Step 3 — Migration detection:** Scan ticket title and description for "migración", "migration", "DDL", "ALTER", "schema change", "data migration". If found:
> "Este ticket parece requerir un flujo de migración en QuintaApp-Api. ¿Lo proceso con `/dev-migration`?"
If confirmed → invoke `/dev-migration <TICKET_ID>`, stop here.

**Step 4 — Check branch state** across all three repos:
```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
git -C $WS/projects/QuintaApp-Api      fetch origin 2>/dev/null; git -C $WS/projects/QuintaApp-Api      branch -a | grep -i "<TICKET_ID>"
git -C $WS/projects/QuintaApp-Frontend fetch origin 2>/dev/null; git -C $WS/projects/QuintaApp-Frontend branch -a | grep -i "<TICKET_ID>"
git -C $WS/projects/CloudHubCorp       fetch origin 2>/dev/null; git -C $WS/projects/CloudHubCorp       branch -a | grep -i "<TICKET_ID>"
```

Also check for a saved snapshot:
```bash
cat $WS/memory/snapshots/<TICKET_ID>.json 2>/dev/null
```
If snapshot exists, use it to fast-track context. Still run git/PR checks to verify it's not stale.

**Branch(es) exist (resuming):** For each repo with a matching branch, collect independently.
`<repo_path>` resolves to `$WS/projects/<repo-name>` (or `$WS/<repo-name>` if `PROJECTS_SUBDIR` is
empty in `config.sh`):
```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"

# Detect base branch for this repo
REPO_NAME=$(basename <repo_path>)
BASE_BRANCH="master"; case "$REPO_NAME" in ${SPECIAL_REPO_PATTERNS// /|}) BASE_BRANCH="$SPECIAL_REPO_BASE";; esac

git -C <repo_path> log $BASE_BRANCH..HEAD --oneline
git -C <repo_path> status
gh pr list --head <branch> --json number,title,state,url,reviews,reviewRequests,comments
git -C <repo_path> rev-list HEAD..origin/$BASE_BRANCH --count   # drift check
```

Auto-proceed to the most logical phase based on state:
- Uncommitted changes or staged files → Phase 3 (development)
- Clean tree, no PR yet → Phase 6 (push)
- PR open with `CHANGES_REQUESTED` → `/dev-pr <TICKET_ID> review`
- PR open, no pending reviews → already at PR, monitor
- Only when next step is genuinely ambiguous: present state and ask

**No branch found (fresh start):** Proceed to Phase 0.5.

---

## Phase 0.5: Technical Deep Dive

**Applies to**: every fresh start and resumed branches before continuing development.

Delegated entirely to `/dev-assess`. Invoke it and follow its instructions:

```
/dev-assess <TICKET_ID>
```

`/dev-assess` handles everything in **one combined confirmation**:
- Detects affected repos and does architecture-aware codebase exploration
- Loads `memory/` context (historical patterns, decisions, mistakes)
- Queries the Jira epic in parallel
- Presents the **Technical Assessment** with confidence score and repo/layer breakdown
- **Fast path**: if confidence ≥ 0.9 and no open questions, presents a condensed confirmation
- In the same prompt: ticket completeness (if incomplete), Jira documentation, Jira transition to In Progress

After the user replies once, proceed to Phase 2.

---

## Phase 1: Opportunistic Enrichment (applies throughout phases 0–8)

At any point, if relevant information is discovered that is **not already in the ticket** (root cause of a bug, impacted files, a design decision, a risk identified during testing), propose adding it:

> "Encontré información relevante que no está en el ticket: [description]. ¿La agrego?"

- **Always require explicit user confirmation** before updating Jira.
- Use `jira-comment.py add` for findings discovered after development starts; use `jira-issue.py update --fields-json` for enriching the description before development.
- Jira comment format: plain text only. No markdown syntax — no **, no ##, no * or - as bullets, no backticks. Write in paragraphs or "Label: value" lines. Separate sections with blank lines.

---

## Phase 2: Branch Setup

Detect the repo(s) affected by the ticket (from Phase 0.5). For each affected repo:

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"

REPO_NAME=$(basename <repo_path>)
BASE_BRANCH="master"; case "$REPO_NAME" in ${SPECIAL_REPO_PATTERNS// /|}) BASE_BRANCH="$SPECIAL_REPO_BASE";; esac

# Branch prefix from ticket context:
# feature/msof-XXX for new features
# fix/msof-XXX for bug fixes
BRANCH_NAME="feature/<TICKET_ID_LOWERCASE>"

git -C <repo_path> fetch origin
git -C <repo_path> checkout $BASE_BRANCH
git -C <repo_path> pull origin $BASE_BRANCH
git -C <repo_path> checkout -b $BRANCH_NAME
```

### Divergence check (always run before touching any code)

```bash
git -C <repo_path> fetch origin
git -C <repo_path> rev-list --count $BRANCH_NAME..origin/$BASE_BRANCH   # how far behind
git -C <repo_path> rev-list --count origin/$BASE_BRANCH..$BRANCH_NAME   # how far ahead
```

- If base is **> 10 commits ahead**: warn before proceeding.
  > "[Repo] tiene N commits adelante del branch. ¿Hacemos rebase antes de continuar?"
- If **≤ 10 commits ahead**: continue silently.

### Jira transition to "In Progress"

Applied if the user confirmed it in `/dev-assess`. Skip if already In Progress or branch already existed.

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "$WS/scripts/workspace-env.sh"
uv run $JIRA_SKILL/workflow/jira-transition.py do "<TICKET_ID>" "In Progress"
```

---

## Phase 3: Development

Make focused, minimal changes — only what the ticket asks for.

- No refactoring, no extra comments, no docstrings unless explicitly requested.
- Follow existing patterns in the codebase.

**Architecture rules**: each affected repo's own `CLAUDE.md` (`projects/<repo>/CLAUDE.md`) is the
source of truth for its architecture, conventions, and gates — not a copy here. If Phase 0.5
(`/dev-assess`) ran this session, it's already loaded (its Section A.2 reads it explicitly and says to
internalize it before exploring). If this phase was reached directly — e.g. resuming with uncommitted
changes, which skips 0.5 — read the affected repo's `CLAUDE.md` now, don't rely on memory of it from a
prior session. A stale copy here has already drifted from the real rule once (`CloudHubCorp/CLAUDE.md`
treats `PUT`/`DELETE` as legacy exceptions to avoid extending, not an absolute prohibition) — that's
exactly the failure mode duplicating it here produces.

Two build habits worth calling out explicitly, since they're easy to skip mid-edit rather than because
they're missing from each repo's own `CLAUDE.md`:
- Go (`QuintaApp-Api`): run `go build ./...` after each logical change.
- CloudHubCorp: run `make build` after any Backoffice change to rebuild static assets.

### Multi-project change order

If the ticket affects more than one repo, implement in this order:
1. **QuintaApp-Api** (backend / source of truth) — business logic and API contracts first
2. **QuintaApp-Frontend** — can start once the API contract is defined, even if not deployed yet
3. **CloudHubCorp** — independent product; no coupling with QuintaApp

**API contract check:** If you modify an existing endpoint (path, method, request/response shape), grep the other repos:
```bash
grep -r "<endpoint_path>" projects/QuintaApp-Frontend/src/services/ 2>/dev/null
grep -r "<endpoint_path>" projects/CloudHubCorp/ 2>/dev/null
```
If found, review and update the consumer before closing the backend phase.

### Worktrees for parallel multi-repo development

If the ticket requires simultaneous development in more than one repo, use `--worktree` (`-w`) to open each in an isolated git copy:
```bash
claude --worktree -C projects/QuintaApp-Api/
claude --worktree -C projects/QuintaApp-Frontend/
```
Each worktree operates on an independent copy of the branch. Background agents (Ctrl+B) work normally within each session. (Codex: no direct equivalent for either — see `agent-context.md`'s Command Resolution Rules for the fallback.)

---

## Phase 4: Validation

Before committing, run the full validation suite for each affected repo.

**QuintaApp-Api:**
```bash
make -C projects/QuintaApp-Api check   # fmt + vet + lint + test
```
If `check` target unavailable, fallback:
```bash
cd projects/QuintaApp-Api && go test ./internal/core/... ./internal/adapters/primary/... -race -coverprofile=coverage.out
go tool cover -func=coverage.out
cd projects/QuintaApp-Api && golangci-lint run
```
Coverage gate: **80% minimum** on `./internal/core/...` and `./internal/adapters/primary/...`.
If any package falls below 80%, list exactly which ones and their percentages — do not proceed until fixed.

**QuintaApp-Frontend:**
```bash
cd projects/QuintaApp-Frontend && npm run test && npm run lint
```

**CloudHubCorp:**
```bash
make -C projects/CloudHubCorp test
make -C projects/CloudHubCorp build   # always rebuild after any Backoffice change
```

Fix any failures before moving on. Do not skip or work around failing tests.

Background mode for slow test suites: run with Ctrl+B and continue reviewing other files while tests run. (Codex: run sequentially instead — see `agent-context.md`.)

---

## Phase 5: Commit

### Step 1 — Pre-commit scan (blocking)

```bash
git diff --cached --unified=0   # if already staged
```

Flag and fix before proceeding:
- **Debug output**: `fmt.Println`, `console.log`, `var_dump`, `dd()`
- **TODO/FIXME without ticket**: not referencing a Jira issue
- **Dead code**: commented-out blocks of 3+ lines with no documentation purpose
- **Secrets or local config**: `.env` values, hardcoded tokens, local paths
- **CloudHubCorp**: SQL without `business_id` scope

### Step 2 — Commit granularity check

Does the diff represent **one logical change**, or multiple concerns mixed?

If mixed (e.g. unrelated production files changed together, refactor mixed with feature), split and proceed immediately:
> "El diff mezcla [concern A] y [concern B] — voy a splitear en dos commits."

### Step 3 — Commit

Format: `<TICKET_ID> | <short description>`

Example: `msof-42 | add booking cancellation endpoint`

Rules:
- **NEVER** add `Co-Authored-By` lines.
- **NEVER** use conventional commit prefixes (`feat:`, `fix:`, `refactor:`).
- **NEVER amend a commit already pushed** — if correction needed after push, create a new commit.

---

## Phase 6: Push

- **Ask for explicit user authorization** before running `git push`.
- If branch has diverged from base, rebase (never merge):
  ```bash
  WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
  [ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  source "$WS/scripts/workspace-env.sh"
  REPO_NAME=$(basename $(git rev-parse --show-toplevel))
  BASE="master"; case "$REPO_NAME" in ${SPECIAL_REPO_PATTERNS// /|}) BASE="$SPECIAL_REPO_BASE";; esac
  git fetch origin && git rebase origin/$BASE
  ```
- If conflicts, resolve and continue the rebase.
- Use `--force-with-lease` **only** after a rebase on top of origin base. Never to push an amended commit.

After push:
> "Push listo. ¿Guardo un checkpoint? (`/dev-reflect <TICKET_ID>`)"

---

## Phase 7: Pull Request

Delegated entirely to `/dev-pr`. Invoke it with the ticket ID:

```
/dev-pr <TICKET_ID>
```

`/dev-pr` will: run the pre-PR scan, build the PR body from test files and specs, create the PR against the correct base branch (`master` or `develop`), post a Jira comment, and run `/code-review ultra`.

---

## Phase 8: Review Handling

Delegated to `/dev-pr` with the `review` subcommand:

```
/dev-pr <TICKET_ID> review
```

`/dev-pr` will: record the review round in `memory/`, analyze each comment, implement fixes, re-run validation per repo, commit, and ask for push authorization.

---

## Related sibling skills

Not inlined here — each is independently invokable and has its own SKILL.md:

- `/dev-setup` — first-run setup / credentials & environment health check (Phase -1)
- `/dev-create` — spec and file a brand-new ticket
- `/dev-assess` — technical deep dive (Phase 0.5)
- `/dev-pr` — create PR / handle review comments (Phases 7–8)
- `/dev-reflect` — snapshot / closing reflection
- `/dev-resume` — reconstruct context for a ticket already in progress
- `/dev-review` — external code review of a teammate's PR (Entry point C)
- `/dev-migration` — QuintaApp-Api DB migration workflow
- `/dev-status` — read-only ticket/workspace state
- `/dev-db-sync` — pull a production DB snapshot

Separate command family (not a `dev-*` sibling, no code/Jira/PR logic): `/manager`, `/manager-create`,
`/manager-update` — manage `Business/<cliente>/` context. `/dev-assess` (Phase 0.5) delegates to
`/manager-create` automatically the first time it meets a repo with no client association. The relation
also runs the other way: `/manager`'s Phase 2 (requirement intake) delegates *into* `/dev` — which
routes to `/dev-create` — whenever a client requirement turns out to need development; `/manager` never
files the ticket itself.
