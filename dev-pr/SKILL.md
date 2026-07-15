---
name: dev-pr
description: "Create a pull request or handle review comments for a ticket. Phase 1: pre-PR scan, build PR body, create PR via gh, post Jira comment, run /ultrareview. Phase 2 (subcommand 'review'): record review round, implement fixes, validate, commit, push. Delegated to by /dev for PR creation and review handling."
allowed-tools: Bash Read Write
---

# PR — Pull Request and Review Handling

Create a PR or handle review comments for: **$ARGUMENTS**

Extract ticket ID (`msof-XXX`) from `$ARGUMENTS`. Normalize to uppercase: `MSOF-XXX`.

Optional subcommand: `review` — skip directly to Phase 2 (handle existing review comments).

---

## Repo and branch detection (run first, reuse throughout)

```bash
# Detect which repo we're in
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
REPO_NAME=$(basename "$REPO_ROOT")

# Determine base branch and diff base
BASE_BRANCH="master"
case "$REPO_NAME" in ${SPECIAL_REPO_CASE_PATTERN}) BASE_BRANCH="${SPECIAL_REPO_BASE}";; esac

# Determine PR title prefix from branch name
CURRENT_BRANCH=$(git branch --show-current)
if echo "$CURRENT_BRANCH" | grep -qi "^fix/"; then
  PR_PREFIX="Fix"
elif echo "$CURRENT_BRANCH" | grep -qi "^feature/"; then
  PR_PREFIX="Feature"
else
  PR_PREFIX="Chore"
fi

echo "Repo: $REPO_NAME | Base: $BASE_BRANCH | Prefix: $PR_PREFIX"
```

---

## Phase 1 — Create Pull Request

**Ask for explicit user authorization** before creating the PR.

### Pre-PR scan (blocking)

Read the full diff and fix any issues before writing the PR body:

```bash
git diff $BASE_BRANCH...HEAD
```

Flag and fix each of the following before continuing:

- **Debug logs**: `fmt.Println`, `console.log`, `log.Printf`, `var_dump`, `dd()` added for debugging (not production observability)
- **TODOs without a ticket**: `// TODO: fix this` not linked to a Jira issue
- **Stray files**: `.env`, `*.local`, generated binaries, IDE configs, `vendor/` changes that shouldn't be committed
- **Misnamed identifiers**: function or variable names that contradict what they actually do
- **Hardcoded values**: magic strings or numbers that belong in config or constants
- **CloudHubCorp only**: SQL queries missing `business_id` scope

Report each issue with file and line, fix it, then continue:
> "Encontré [issue] en [file:line]. Lo corrijo antes de crear el PR."

### Build PR body

**1 — List new test files added in this branch:**

```bash
# Go (QuintaApp-Api)
git diff $BASE_BRANCH...HEAD --name-only | grep "_test\.go$"

# React/JS (QuintaApp-Frontend)
git diff $BASE_BRANCH...HEAD --name-only | grep "\.test\.\(jsx\|js\)$"

# PHP (CloudHubCorp)
git diff $BASE_BRANCH...HEAD --name-only | grep "Test\.php$"
```

For each test file, note what scenario it covers (inferred from test function names).

**2 — Check for specs (QuintaApp-Api only):**

If working in `QuintaApp-Api` and a spec file exists for the feature being implemented:
```bash
ls QuintaApp-Api/specs/features/ 2>/dev/null
cat QuintaApp-Api/specs/features/<feature-name>.md 2>/dev/null
```
Extract acceptance criteria from the spec if found.

**3 — Build the body:**

```
## Summary
- <bullet points describing the changes, grounded in actual commits and diff>

## Test plan
- [ ] <one item per new test file, describing what it validates>
- [ ] <any manual verification steps relevant to the ticket>

## Acceptance criteria
<paste acceptance criteria from specs/features/<name>.md — only if spec exists for this feature>
<omit this section entirely if no spec>

## Specs
Specs disponibles en `QuintaApp-Api/specs/features/`
<only if a spec was found and used>
```

Rules:
- Omit **Acceptance criteria** and **Specs** entirely if no spec file applies.
- The test plan must always have at least one item. If no new test files, describe manual steps instead.

### Create the PR

PR title format: `[<Prefix>][<TICKET_ID>] <brief description>`
- Prefix is `Feature`, `Fix`, or `Chore` — detected from branch name above.
- TICKET_ID must be uppercase: `MSOF-123`, never lowercase.
- **NEVER** use the commit format `MSOF-123 | description` as the PR title.
- **NEVER** use the branch name or commit subject verbatim as the PR title.

```bash
gh pr create --base $BASE_BRANCH \
  --title "[$PR_PREFIX][<TICKET_ID>] <description>" \
  --body "$(cat <<'EOF'
<body built above>
EOF
)"
```

After the PR is created, capture the URL from the `gh pr create` output, then post a Jira comment automatically (no authorization needed):

```bash
JIRA_SKILL=${JIRA_SCRIPTS}
uv run $JIRA_SKILL/workflow/jira-comment.py add "<TICKET_ID>" "PR abierto

Titulo: [$PR_PREFIX][<TICKET_ID>] <brief description>
URL: <PR_URL>
Base: $BASE_BRANCH
Repo: $REPO_NAME
Archivos cambiados: N

Cambios principales:
<2-4 lines of plain text describing the changes — no bullet symbols, no markdown>"
```

Jira comment format rule: plain text only. No markdown — no **, no ##, no * or - as bullets, no backticks. Separate sections with blank lines. Use "Label: value" for structured data.

### Post-PR: /ultrareview

After creating the PR, run a multi-agent review in parallel:

```
/ultrareview
```

**Wait for `/ultrareview` to finish before telling the user the PR is ready for human review.** If issues are reported:
1. Fix each issue found.
2. Commit: `<TICKET_ID> | address automated review findings`
3. Ask for authorization before pushing.

**Skip when**: the PR is trivial (one-line change, docs only, config with no logic).

After ultrareview completes (or is skipped), offer proactively:
> "PR listo para revisión humana. ¿Guardo un checkpoint? (`/dev-reflect <TICKET_ID>`)"

If the user confirms, run `/dev-reflect <TICKET_ID>` immediately.

---

## Phase 2 — Review Handling

Triggered when the user shares PR review comments, or via subcommand `review`.

**Before implementing anything**, record this review round:

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
os.makedirs(f'{WS}/.ai-memory/review_rounds', exist_ok=True)
path = f'{WS}/.ai-memory/review_rounds/<TICKET_ID>.json'
try:
    data = json.load(open(path))
except Exception:
    data = {'ticket_id': '<TICKET_ID>', 'rounds': []}

data['rounds'].append({
    'round': len(data['rounds']) + 1,
    'date': datetime.datetime.utcnow().isoformat() + 'Z',
    'comments': ['<each review comment — one string per comment>'],
    'changes': []
})

with open(path, 'w') as f:
    json.dump(data, f, indent=2)
```

1. Analyze each comment and determine the fix.
2. Implement all fixes.
3. **If a spec exists in `QuintaApp-Api/specs/features/` and any fix alters a design decision** (not just a bug fix, but changes approach, interface, or behavior): update the relevant section of the spec before committing. Specs must describe what shipped, not the original plan.
4. Run validation for the current repo:

   **QuintaApp-Api:**
   ```bash
   make check   # fmt + vet + lint + test — gate is ≥80% coverage
   ```

   **QuintaApp-Frontend:**
   ```bash
   npm run test && npm run lint
   ```

   **CloudHubCorp:**
   ```bash
   make test
   ```

5. Commit: `<TICKET_ID> | address PR review comments`
6. **Ask for authorization** before pushing.

After pushing, patch the current round's `changes` field:

```python
data = json.load(open(path))
data['rounds'][-1]['changes'] = ['<each concrete change made — one string per fix>']
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
```
