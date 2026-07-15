---
name: dev
description: "Main development orchestrator. Accepts a PROJ-XXX ticket ID, a freeform idea with no ticket yet, a PR URL (own PR), or 'review <PR URL>' (teammate's PR). Runs the core ticket loop (branch setup, development, validation, commit, push) and routes everything else to sibling dev-* skills: dev-create, dev-assess, dev-pr, dev-reflect, dev-resume, dev-review, dev-migration, dev-status, dev-db-sync."
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

## Phase 0: Routing

Parse `$ARGUMENTS` and dispatch immediately.

### Dispatch table

| Argument | Action |
|----------|--------|
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
   JIRA_SKILL=${JIRA_SCRIPTS}
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
        g = subprocess.check_output(['git','rev-parse','--show-toplevel'], text=True).strip()
    except Exception:
        g = os.getcwd()
    p = os.path.dirname(g)
    return p if os.path.exists(os.path.join(p, 'CLAUDE.md')) else g

WS = workspace_root()
try:
    profile = json.load(open(f'{WS}/.ai-memory/user_profile.json'))
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
JIRA_SKILL=${JIRA_SCRIPTS}
uv run $JIRA_SKILL/core/jira-issue.py get "<TICKET_ID>" --json
```

**Step 2 — Rename session:** `/rename MSOF-XXX | <ticket summary>`

**Step 3 — Migration detection:** Scan ticket title and description for "migración", "migration", "DDL", "ALTER", "schema change", "data migration". If found:
> "Este ticket parece requerir un flujo de migración en QuintaApp-Api. ¿Lo proceso con `/dev-migration`?"
If confirmed → invoke `/dev-migration <TICKET_ID>`, stop here.

**Step 4 — Check branch state** across all three repos:
```bash
WS=$(python3 -c "
import os, subprocess
try:
    g = subprocess.check_output(['git','rev-parse','--show-toplevel'], text=True).strip()
except:
    g = os.getcwd()
p = os.path.dirname(g)
print(p if os.path.exists(os.path.join(p,'CLAUDE.md')) else g)
")
git -C $WS/QuintaApp-Api     fetch origin 2>/dev/null; git -C $WS/QuintaApp-Api     branch -a | grep -i "<TICKET_ID>"
git -C $WS/QuintaApp-Frontend fetch origin 2>/dev/null; git -C $WS/QuintaApp-Frontend branch -a | grep -i "<TICKET_ID>"
git -C $WS/CloudHubCorp      fetch origin 2>/dev/null; git -C $WS/CloudHubCorp      branch -a | grep -i "<TICKET_ID>"
```

Also check for a saved snapshot:
```bash
cat $WS/.ai-memory/snapshots/<TICKET_ID>.json 2>/dev/null
```
If snapshot exists, use it to fast-track context. Still run git/PR checks to verify it's not stale.

**Branch(es) exist (resuming):** For each repo with a matching branch, collect independently:
```bash
# Detect base branch for this repo
REPO_NAME=$(basename <repo_path>)
BASE_BRANCH="master"; case "$REPO_NAME" in ${SPECIAL_REPO_CASE_PATTERN}) BASE_BRANCH="${SPECIAL_REPO_BASE}";; esac

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
- Loads `.ai-memory/` context (historical patterns, decisions, mistakes)
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
REPO_NAME=$(basename <repo_path>)
BASE_BRANCH="master"; case "$REPO_NAME" in ${SPECIAL_REPO_CASE_PATTERN}) BASE_BRANCH="${SPECIAL_REPO_BASE}";; esac

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
JIRA_SKILL=${JIRA_SCRIPTS}
uv run $JIRA_SKILL/workflow/jira-transition.py do "<TICKET_ID>" "In Progress"
```

---

## Phase 3: Development

Make focused, minimal changes — only what the ticket asks for.

- No refactoring, no extra comments, no docstrings unless explicitly requested.
- Follow existing patterns in the codebase.
- For Go: ensure `go build ./...` passes after each logical change.
- For CloudHubCorp: run `make build` after any Backoffice change to rebuild static assets.

**QuintaApp-Api architectural rules:**
- New features follow the hexagonal flow: domain entity → port interface → service implementation → handler → MySQL repository
- New domain errors: define in `internal/core/domain/errors.go`, add case in `mapError()` in `response.go`
- Services only depend on port interfaces, never on concrete adapters
- New spec for significant features: create `specs/features/<name>.md` using `specs/TEMPLATE.md`

**QuintaApp-Frontend rules:**
- All fetches go through `src/services/apiClient.js`
- New components need a `.test.jsx` file alongside them
- No hardcoded URLs — use `import.meta.env.VITE_API_URL`

**CloudHubCorp rules:**
- Always scope SQL queries with `business_id`
- Only POST and GET — never PUT or DELETE
- Protected routes need `# useMiddleware` or `middleware:` attribute
- PHP files start with `<?php #Business Hub Corp Framework` + `declare(strict_types=1);`
- `make build` after any Backoffice change

### Multi-project change order

If the ticket affects more than one repo, implement in this order:
1. **QuintaApp-Api** (backend / source of truth) — business logic and API contracts first
2. **QuintaApp-Frontend** — can start once the API contract is defined, even if not deployed yet
3. **CloudHubCorp** — independent product; no coupling with QuintaApp

**API contract check:** If you modify an existing endpoint (path, method, request/response shape), grep the other repos:
```bash
grep -r "<endpoint_path>" QuintaApp-Frontend/src/services/ 2>/dev/null
grep -r "<endpoint_path>" CloudHubCorp/ 2>/dev/null
```
If found, review and update the consumer before closing the backend phase.

### Worktrees for parallel multi-repo development

If the ticket requires simultaneous development in more than one repo, use `--worktree` (`-w`) to open each in an isolated git copy:
```bash
claude --worktree -C QuintaApp-Api/
claude --worktree -C QuintaApp-Frontend/
```
Each worktree operates on an independent copy of the branch. Background agents (Ctrl+B) work normally within each session.

---

## Phase 4: Validation

Before committing, run the full validation suite for each affected repo.

**QuintaApp-Api:**
```bash
make -C QuintaApp-Api check   # fmt + vet + lint + test
```
If `check` target unavailable, fallback:
```bash
cd QuintaApp-Api && go test ./internal/core/... ./internal/adapters/primary/... -race -coverprofile=coverage.out
go tool cover -func=coverage.out
cd QuintaApp-Api && golangci-lint run
```
Coverage gate: **80% minimum** on `./internal/core/...` and `./internal/adapters/primary/...`.
If any package falls below 80%, list exactly which ones and their percentages — do not proceed until fixed.

**QuintaApp-Frontend:**
```bash
cd QuintaApp-Frontend && npm run test && npm run lint
```

**CloudHubCorp:**
```bash
make -C CloudHubCorp test
make -C CloudHubCorp build   # always rebuild after any Backoffice change
```

Fix any failures before moving on. Do not skip or work around failing tests.

Background mode for slow test suites: run with Ctrl+B and continue reviewing other files while tests run.

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
  REPO_NAME=$(basename $(git rev-parse --show-toplevel))
  BASE="master"; case "$REPO_NAME" in ${SPECIAL_REPO_CASE_PATTERN}) BASE="${SPECIAL_REPO_BASE}";; esac
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

`/dev-pr` will: run the pre-PR scan, build the PR body from test files and specs, create the PR against the correct base branch (`master` or `develop`), post a Jira comment, and run `/ultrareview`.

---

## Phase 8: Review Handling

Delegated to `/dev-pr` with the `review` subcommand:

```
/dev-pr <TICKET_ID> review
```

`/dev-pr` will: record the review round in `.ai-memory/`, analyze each comment, implement fixes, re-run validation per repo, commit, and ask for push authorization.

---

## Related sibling skills

Not inlined here — each is independently invokable and has its own SKILL.md:

- `/dev-create` — spec and file a brand-new ticket
- `/dev-assess` — technical deep dive (Phase 0.5)
- `/dev-pr` — create PR / handle review comments (Phases 7–8)
- `/dev-reflect` — snapshot / closing reflection
- `/dev-resume` — reconstruct context for a ticket already in progress
- `/dev-review` — external code review of a teammate's PR (Entry point C)
- `/dev-migration` — QuintaApp-Api DB migration workflow
- `/dev-status` — read-only ticket/workspace state
- `/dev-db-sync` — pull a production DB snapshot
