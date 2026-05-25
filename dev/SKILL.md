---
name: dev
description: "Main development orchestrator. Accepts a PROJ-XXX ticket ID, a PR URL (own PR), or 'review <PR URL>' (teammate's PR). Routes to the correct phase: technical assessment, branch setup, development, validation, commit, push, PR creation, or review handling. Also accepts subcommands: 'PROJ-XXX migration', 'PROJ-XXX resume', 'PROJ-XXX reflect', 'PROJ-XXX status'."
allowed-tools: Bash Read Write
---

# Dev — Development Workflow

Execute the full development workflow for: **$ARGUMENTS**

`$ARGUMENTS` can be:
- A ticket ID: `msof-XXX`
- A PR URL (your own PR): `https://github.com/.../pull/123`
- `review <PR URL>` — code review for a teammate's PR
- A ticket ID with a subcommand:
  - `msof-XXX migration` — run DB migration workflow (QuintaApp-Api)
  - `msof-XXX resume` — reconstruct development context + standup
  - `msof-XXX reflect` — post-ticket reflection + memory persistence (→ `/reflect`)
  - `msof-XXX status` — quick ticket state — no workflow started

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
| starts with `review ` + URL | Entry point C — External code review (reviewer) |
| URL containing `http` or `/pull/` | Entry point B — Own PR (resume/review comments) |
| `msof-XXX migration` | Inline migration workflow — Phase 2b |
| `msof-XXX resume` | Phase 12 — Resume development context |
| `msof-XXX reflect` | → `/reflect <TICKET_ID>` (auto-detects mode by PR state) |
| `msof-XXX status` | Phase 5b — Quick read-only state |
| `status` (no ticket ID) | Phase 5c — Multi-ticket overview |
| `msof-XXX` (no subcommand) | Entry point A — full workflow |

For delegated skills: invoke the target with the ticket ID and follow its instructions. Do not proceed to any other phase.

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
6. Invoke `/pr <TICKET_ID> review` with the detected review comments.

---

### Entry point C — External code review (reviewer)

Triggered when argument starts with `review ` followed by a PR URL.

Extract `<PR_URL>` from arguments (everything after `review `).

#### Step 1 — Fetch PR context

Save the current branch:
```bash
CURRENT_BRANCH=$(git branch --show-current)
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
REPO_NAME=$(basename "$REPO_ROOT")
```

Run in parallel:
```bash
gh pr view "<PR_URL>" --json title,body,headRefName,baseRefName,state,url,author,additions,deletions,changedFiles,reviews,comments
gh pr diff "<PR_URL>"
```

Check out the PR branch for full-file reads:
```bash
gh pr checkout "<PR_URL>"
```

Rename session: `/rename review | <PR title>`

#### Step 2 — Load project conventions

Read in parallel (from the checked-out branch):
- `CLAUDE.md` of the current repo (architecture rules)
- `Makefile` (build, test, lint targets)
- Full content of each file in the diff (not just changed lines) for surrounding context

#### Step 3 — Review analysis

Evaluate across these dimensions in order of severity.

> **CUSTOMIZE** — The blocking rules below are examples for a Go hexagonal API + React frontend + PHP multi-tenant stack. Replace with your project's architecture and conventions.

**Blocking** (must be fixed before merging):

*QuintaApp-Api (Go hexagonal):*
- **Architecture violation**: use-case importing infrastructure; handler containing business logic; service depending on concrete adapter (not interface); domain entity importing from adapters layer
- **Error handling**: domain error not defined in `errors.go`; error not mapped in `mapError()` in `response.go`; wrong HTTP status returned for a domain error type
- **Coverage regression**: new logic added without tests; coverage in `./internal/core/...` or `./internal/adapters/primary/...` drops below 80%
- **JWT misuse**: refresh token used as access token (missing `Type` field validation); token not validated with `middleware.Auth()`
- **Test fixture issues**: `time.Now()` in booking tests (causes float precision drift in TotalPrice — use fixed `time.Date(...)` instead); `bcrypt.DefaultCost` in tests (too slow — use `bcrypt.MinCost`)
- **OpenAPI drift**: handler endpoint changed but `spec_openapi/openapi.yaml` not updated

*QuintaApp-Frontend (React):*
- **Direct fetch**: API call in a component or hook without going through `src/services/apiClient.js`
- **Missing test file**: new component added without a `.test.jsx` file alongside it
- **Hardcoded URL**: API URL not read from `import.meta.env.VITE_API_URL`
- **Auth bypass**: token not read from `localStorage.access_token` or Bearer header missing

*CloudHubCorp (PHP multi-tenant):*
- **Missing `business_id`**: SQL query without `business_id` scope — data leak between tenants
- **Forbidden HTTP methods**: using `PUT` or `DELETE` — only `POST` and `GET` are allowed
- **Missing auth middleware**: route without `# useMiddleware` or `middleware:` attribute on a protected endpoint
- **Wrong file header**: PHP file not starting with `<?php #Business Hub Corp Framework` + `declare(strict_types=1);`
- **Backoffice not rebuilt**: Backoffice-related changes without `make build` in the last commits
- **Module naming violation**: core module using `m_` prefix, or add-on module missing `m_` prefix

**Non-blocking** (improvements/style):

- Debug output left in: `fmt.Println`, `console.log`, `var_dump`, `dd()`
- TODO/FIXME without a linked Jira issue
- Magic strings or numbers that belong in named constants
- Comments explaining WHAT code does (vs. non-obvious WHY/invariant/workaround)
- Commit message not matching `<TICKET_ID> | <description>` format
- 4-space indentation missing in PHP files (tabs are wrong)

**Positive observations** (call out explicitly):

- Good reuse of existing utilities instead of reinventing
- Well-structured error handling with correct domain error type
- Thoughtful test coverage including edge cases
- Clear naming that makes the code self-documenting

#### Step 4 — Present the review

Write it as a peer would — no section headers, no tables, no bot structure.

Format rules:
- Lead with one short line: overall impression + verdict signal (nothing if all good, "un par de cosas" if minor, "hay cosas que bloquean" if blocking).
- List only real findings. Each item: `` `file:line` `` + short explanation in plain language — say the fix inline, no "Fix:" label.
- If something is genuinely good and non-obvious, mention it in one line at the end.
- End with one line: verdict ("LGTM", "LGTM con los cambios", "necesito los cambios antes de aprobar").
- Write in the same language the PR description uses. If mixed, use Spanish.
- No markdown headers (`###`), no `**Blocking**`, no checkboxes.

Example:
```
Luce bien en general, un par de cosas antes de aprobar:

- `internal/adapters/primary/http/handlers/booking.go:87` falta agregar este error en `mapError()` — sin eso devuelve 500 en lugar del status correcto
- `src/features/bookings/BookingForm.jsx:34` el fetch debería ir por `apiClient`, no con `fetch()` directo

El manejo del JWT está bien estructurado.

LGTM con los cambios.
```

#### Step 5 — Post review (optional)

Ask: "¿Publico el review en GitHub?"

If confirmed, post the **same text from Step 4** (no reformatting):
```bash
# Request changes:
gh pr review "<PR_URL>" --request-changes --body "<review text>"

# Approve:
gh pr review "<PR_URL>" --approve --body "<review text>"

# Comment only:
gh pr review "<PR_URL>" --comment --body "<review text>"
```

Pick based on verdict: blocking → `--request-changes`, all good → `--approve`, informational → `--comment`.

#### Step 6 — Restore your branch

```bash
git checkout "$CURRENT_BRANCH"
```

---

### Entry point A — Ticket ID (full workflow)

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
> "Este ticket parece requerir un flujo de migración en QuintaApp-Api. ¿Lo proceso con el flujo de migrations?"
If confirmed → Phase 2b (migration workflow), stop here.

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
BASE_BRANCH=$( [ "$REPO_NAME" = "${SPECIAL_REPO}" ] && echo "${SPECIAL_REPO_BASE}" || echo "master" )

git -C <repo_path> log $BASE_BRANCH..HEAD --oneline
git -C <repo_path> status
gh pr list --head <branch> --json number,title,state,url,reviews,reviewRequests,comments
git -C <repo_path> rev-list HEAD..origin/$BASE_BRANCH --count   # drift check
```

Auto-proceed to the most logical phase based on state:
- Uncommitted changes or staged files → Phase 3 (development)
- Clean tree, no PR yet → Phase 6 (push)
- PR open with `CHANGES_REQUESTED` → Phase 8 (review handling)
- PR open, no pending reviews → already at PR, monitor
- Only when next step is genuinely ambiguous: present state and ask

**No branch found (fresh start):** Proceed to Phase 0.5.

---

## Phase 0.5: Technical Deep Dive

**Applies to**: every fresh start and resumed branches before continuing development.

Delegated entirely to `/assess`. Invoke it and follow its instructions:

```
/assess <TICKET_ID>
```

`/assess` handles everything in **one combined confirmation**:
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
BASE_BRANCH=$( [ "$REPO_NAME" = "${SPECIAL_REPO}" ] && echo "${SPECIAL_REPO_BASE}" || echo "master" )

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

Applied if the user confirmed it in `/assess`. Skip if already In Progress or branch already existed.

```bash
JIRA_SKILL=${JIRA_SCRIPTS}
uv run $JIRA_SKILL/workflow/jira-transition.py do "<TICKET_ID>" "In Progress"
```

---

## Phase 2b: Migration Workflow (QuintaApp-Api only)

Triggered by subcommand `migration` or when migration is detected and confirmed.

**Step 1 — Check pending migrations:**
```bash
make -C QuintaApp-Api migrate-check 2>/dev/null || \
  make -C QuintaApp-Api migrate-status 2>/dev/null
```

**Step 2 — Create migration file** (if adding a new one):
```bash
# Asks for migration name interactively
make -C QuintaApp-Api migrate-create
```
Name format: `<short_description>_<TICKET_ID_LOWERCASE>` (e.g. `add_reviews_table_msof42`)

**Step 3 — Write migration SQL** in the generated files (up and down scripts).

**Step 4 — Review before running:**
- Does the `down` script fully reverse the `up` script?
- Any data-destructive operations (DROP COLUMN, TRUNCATE)?
- Impact on existing rows?

**Step 5 — Ask for authorization** before running:
> "Voy a correr `make migrate-up` en QuintaApp-Api. ¿Confirmás? (requiere DB_* env vars)"

```bash
make -C QuintaApp-Api migrate-up
```

**Step 6 — Verify and commit:**
```bash
make -C QuintaApp-Api test
git add QuintaApp-Api/migrations/
git commit -m "<TICKET_ID> | add migration <migration_name>"
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

## Phase 5b: Status subcommand

Triggered by `msof-XXX status`. Read-only — no workflow started.

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
cat $WS/.ai-memory/snapshots/<TICKET_ID>.json 2>/dev/null

for REPO in ${REPOS}; do
  BASE=$( [ "$REPO" = "${SPECIAL_REPO}" ] && echo "${SPECIAL_REPO_BASE}" || echo "master" )
  git -C $WS/$REPO fetch origin -q 2>/dev/null
  BRANCH=$(git -C $WS/$REPO branch -a | grep -i "<TICKET_ID>" | head -1 | xargs)
  [ -n "$BRANCH" ] && echo "$REPO: $BRANCH" && git -C $WS/$REPO log $BASE..HEAD --oneline 2>/dev/null | head -3
done

gh pr list --search "<TICKET_ID>" --json state,url,title --state all 2>/dev/null | head -3
```

Output format — exactly 6 lines, no markdown:
```
MSOF-XXX | <summary from snapshot or Jira title>
Repos: <which repos have an active branch>  |  PR: <url or "no creado">  |  Estado PR: <open|changes_requested|approved|merged|none>
Commits: <N commits total>  |  Cambios sin commitear: <yes/no>
Próximo paso: <next_step from snapshot or inferred>
Última actualización: <snapshot_date or "sin snapshot">
```

---

## Phase 5c: Multi-ticket status

Triggered by `status` (no ticket ID). Read-only.

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

for REPO in ${REPOS}; do
  git -C $WS/$REPO branch -a 2>/dev/null | grep -oiE "(feature|fix)/${PROJECT_KEY_LOWER}-[0-9]+" | sort -u
done | sort -u
```

For each ticket found, collect in parallel and output one line:
```
MSOF-XXX  <phase>  |  <N> commits  |  PR: <state or "sin PR">  |  <next_step — 5 words max>
```

If no active branches: `"No hay branches activos de MSOF en este workspace."`

---

## Phase 6: Push

- **Ask for explicit user authorization** before running `git push`.
- If branch has diverged from base, rebase (never merge):
  ```bash
  REPO_NAME=$(basename $(git rev-parse --show-toplevel))
  BASE=$( [ "$REPO_NAME" = "CloudHubCorp" ] && echo "develop" || echo "master" )
  git fetch origin && git rebase origin/$BASE
  ```
- If conflicts, resolve and continue the rebase.
- Use `--force-with-lease` **only** after a rebase on top of origin base. Never to push an amended commit.

After push:
> "Push listo. ¿Guardo un checkpoint? (`/dev <TICKET_ID> reflect`)"

---

## Phase 7: Pull Request

Delegated entirely to `/pr`. Invoke it with the ticket ID:

```
/pr <TICKET_ID>
```

`/pr` will: run the pre-PR scan, build the PR body from test files and specs, create the PR against the correct base branch (`master` or `develop`), post a Jira comment, and run `/ultrareview`.

---

## Phase 8: Review Handling

Delegated to `/pr` with the `review` subcommand:

```
/pr <TICKET_ID> review
```

`/pr` will: record the review round in `.ai-memory/`, analyze each comment, implement fixes, re-run validation per repo, commit, and ask for push authorization.

---

## Phase 12: Resume Development Context

Triggered by: `/dev msof-XXX resume`

### Step 1 — Load ticket and branch state

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
  BASE=$( [ "$REPO" = "${SPECIAL_REPO}" ] && echo "${SPECIAL_REPO_BASE}" || echo "master" )
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

### Step 2 — Read the actual changes

For each file in the diff across affected repos, read its content to understand **what was implemented**, not just what changed. Focus on:
- What logic was added or modified
- What is partially done (started but not finished)
- What the code reveals about the next step

### Step 3 — Cross-reference against ticket requirements

Compare what was implemented against what the ticket asks for. Determine:
- What acceptance criteria are already satisfied
- What is partially addressed
- What has not been started yet

### Step 4 — Present the resume summary

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

### Step 5 — Propose continuation

> "¿Continuamos desde donde quedó? Puedo arrancar con [próximo paso concreto]."

Proceed to the appropriate phase after confirmation.

---

## Phase 14: Self-Reflection

Triggered by: `/dev msof-XXX reflect`

Delegated entirely to `/reflect`:

```
/reflect <TICKET_ID>
```

`/reflect` auto-detects the mode: if the PR is merged → closing mode (full reflection + Jira comment + memory persistence); otherwise → checkpoint mode (snapshot only).
