---
name: dev-review
description: "Reviews a teammate's GitHub pull request against MSoftIA architecture and conventions, then optionally posts the review to GitHub. Use when the user asks to review a PR URL, invokes 'review <PR URL>', or wants a code review of someone else's changes (not their own PR). Delegated to by /dev when the argument starts with 'review '."
allowed-tools: Bash Read Write
---

# Dev Review — External Code Review

Review the pull request at: **$ARGUMENTS**

`$ARGUMENTS` is the PR URL (strip a leading `review ` if present).

> Before improvising a multi-step procedure, check `scripts/local/MANIFEST.json` — see `dev/references/local-scripting.md`.

---

## Step 1 — Fetch PR context

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

## Step 2 — Load project conventions

Read in parallel (from the checked-out branch):
- `CLAUDE.md` of the current repo (architecture rules)
- `Makefile` (build, test, lint targets)
- Full content of each file in the diff (not just changed lines) for surrounding context

## Step 3 — Review analysis

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

## Step 4 — Present the review

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

## Step 5 — Post review (optional)

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

## Step 6 — Restore your branch

```bash
git checkout "$CURRENT_BRANCH"
```
