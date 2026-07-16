---
name: dev-setup
description: "First-run setup and environment health check for this workspace: scaffolds config.sh, checks required tools, Jira credentials, GitHub CLI auth, and that the repos listed in REPOS are actually cloned under projects/. Run once after cloning, or any time /dev reports missing prerequisites. Use 'check' as an argument for a read-only pass with no prompts."
allowed-tools: Bash Read Write
---

# Dev Setup — First-Run Setup & Health Check

Run for: **$ARGUMENTS**

`$ARGUMENTS` is empty (full interactive setup) or `check` (read-only verification only, no prompts —
used by `/dev`'s precondition check).

---

## Step 0 — Locate workspace root

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
```

---

## Step 1 — config.sh

```bash
[ -f "$WS/config.sh" ] && echo EXISTS || echo MISSING
```

**If `MISSING`:**
- In `check` mode: report missing, stop here (don't scaffold interactively during a check).
- Otherwise: `cp "$WS/config.example.sh" "$WS/config.sh"`, then ask the user for each value one at a
  time (none of these are secrets — safe to ask and write directly):
  - `PROJECT_KEY` (Jira project key, uppercase, e.g. `MSOF`)
  - `PROJECT_KEY_LOWER` (same, lowercase, used in branch names)
  - `JIRA_BASE_URL` (e.g. `https://your-org.atlassian.net`)
  - `REPOS` (space-separated repo directory names, implementation order — backend first)
  - `PROJECTS_SUBDIR` (subfolder repos live under, e.g. `projects` — empty for flat layout)
  - `SPECIAL_REPO_PATTERNS` / `SPECIAL_REPO_BASE` (repos with a non-`master` base branch, if any)
  - `DB_SYNC_REPOS` (repos supporting `/dev-db-sync` — empty to disable)
  Write each answer into `$WS/config.sh` (replace the corresponding `export VAR="..."` line). Leave
  `JIRA_SCRIPTS` and `CLAUDE_MEMORY_INDEX` as their defaults unless the user has a reason to override.

**If `EXISTS`:**
```bash
source "$WS/config.sh"
echo "PROJECT_KEY=$PROJECT_KEY REPOS=$REPOS PROJECTS_SUBDIR=$PROJECTS_SUBDIR"
```
Show current values. In interactive mode (not `check`), ask if the user wants to change anything;
otherwise continue.

---

## Step 2 — Required tools

```bash
command -v gh >/dev/null && echo "gh: OK" || echo "gh: MISSING — https://cli.github.com/"
command -v uv >/dev/null && echo "uv: OK" || echo "uv: MISSING — https://github.com/astral-sh/uv"
```

If either is missing, show the install link and stop — nothing else works without them.

---

## Step 3 — Jira credentials

```bash
if [ -f ~/.env.jira ] || [ -f ~/.jira/profiles.json ]; then echo "jira: OK"; else echo "jira: MISSING"; fi
```

**If `MISSING`**: do **not** try to run `jira-setup.py` yourself — its credential prompts (API token /
personal access token) are interactive-only by design (no CLI flag exists for them, so secrets never
land in shell history or process args). Tell the user:

> "Faltan credenciales de Jira. Corré esto vos mismo en una terminal (no acá en el chat, para no pasar
> el token por la conversación):
> `uv run $WS/scripts/jira-communication/scripts/core/jira-setup.py`
> Cuando termine, volvé a correr `/dev-setup` para confirmar."

Stop here in both modes if missing — nothing Jira-related works without this.

---

## Step 4 — GitHub CLI auth

```bash
gh auth status &>/dev/null && echo "gh auth: OK" || echo "gh auth: MISSING"
```

**If `MISSING`**: tell the user to run `gh auth login` themselves (same reasoning as Jira — it's an
interactive/browser flow this agent can't drive), then re-run `/dev-setup` to confirm.

---

## Step 5 — Folder scaffold

Skip this step in `check` mode (read-only).

```bash
mkdir -p "$WS/projects" "$WS/scripts/local" "$WS/memory/tickets" "$WS/memory/assessments" "$WS/memory/snapshots"
MANIFEST="$WS/scripts/local/MANIFEST.json"
[ -f "$MANIFEST" ] || printf '{\n  "scripts": []\n}\n' > "$MANIFEST"
```

---

## Step 6 — Repos check

```bash
source "$WS/config.sh"
PROJECTS_PREFIX="${PROJECTS_SUBDIR:+$PROJECTS_SUBDIR/}"
for REPO in $REPOS; do
  if [ -d "$WS/${PROJECTS_PREFIX}$REPO/.git" ]; then
    echo "$REPO: present"
  else
    echo "$REPO: MISSING — git clone it into $WS/${PROJECTS_PREFIX}$REPO"
  fi
done
```

For each missing repo, remind the user to `git clone <url> "$WS/${PROJECTS_PREFIX}<repo>"` themselves —
this skill has no way to know their private repo URLs.

---

## Step 7 — Summary

Print a short checklist, one line per check from Steps 1–6, ✅ or ❌. If everything is ✅:

> "Todo listo. Corré `/dev <TICKET_ID>` para arrancar, o `/dev-create \"<idea>\"` si todavía no hay
> ticket."

If anything is ❌, list the exact remaining commands the user needs to run themselves (Jira setup, `gh
auth login`, missing `git clone`s) — don't repeat generic advice, be specific to what's actually
missing.
