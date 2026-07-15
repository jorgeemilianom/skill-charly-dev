# skill-charly-dev

**From Jira ticket to merged PR — one command, full workflow.**

A set of [Claude Code](https://claude.ai/code) skills that act as a senior engineer pair: reads your ticket, explores the codebase, implements the changes, runs the tests, opens the PR, handles review comments, and remembers every decision along the way.

---

## The problem

Every ticket follows the same ritual: read the ticket, find the files, remember the architecture, create the branch, write code, run tests, write the PR description, handle review comments, transition Jira... It's slow, repetitive, and full of context switching.

These skills automate all of it. You stay in charge — Claude does the groundwork.

---

## How it works

```
you                    Claude
─────────────────────────────────────────────────────
/dev PROJ-42
                       reads ticket from Jira
                       explores codebase (grep, git log, file reads)
                       loads past decisions from .ai-memory/
                       ─────────────────────────────
                       Technical Assessment
                         · approach proposed
                         · files affected
                         · risks flagged
                         · confidence score
                       ─────────────────────────────
confirm / adjust
                       creates branch
                       implements changes
                       runs tests + linter
                       commits
─────────────────────────────────────────────────────
/pr PROJ-42
                       scans diff for issues
                       builds PR body (summary, test plan, acceptance criteria)
                       opens PR via gh
                       posts link to Jira
                       runs automated review
─────────────────────────────────────────────────────
review comments arrive

/dev https://github.com/.../pull/42
                       reads every review comment
                       implements fixes
                       re-runs validation
                       commits + asks to push
─────────────────────────────────────────────────────
PR merged

/reflect PROJ-42 closing
                       saves learnings to .ai-memory/
                       transitions Jira to Done
                       posts closing comment
```

The longer you use it, the better it gets — `.ai-memory/` accumulates your project's decisions, recurring mistakes, and patterns across tickets.

---

## Skills

| Skill | What it does |
|-------|--------------|
| [`/dev`](dev/SKILL.md) | Main orchestrator. Handles the full lifecycle: assessment → branch → code → tests → commit → push → PR → reviews. Also does code review for teammates' PRs. |
| [`/assess`](assess/SKILL.md) | Technical deep dive before writing any code. Produces a structured assessment with confidence score and waits for your go-ahead. |
| [`/pr`](pr/SKILL.md) | Creates the PR or handles incoming review comments. Builds the body, posts to Jira, runs automated review. |
| [`/reflect`](reflect/SKILL.md) | Saves a snapshot at any point (checkpoint) or runs a full closing reflection when the PR merges. Feeds learnings back into memory. |

---

## Quick start

```bash
# 1. clone
git clone https://github.com/jorgeemilianom/skill-charly-dev.git
cd skill-charly-dev

# 2. configure (your Jira, your repos)
cp config.example.sh config.sh
$EDITOR config.sh

# 3. install
./install.sh
```

Open Claude Code in your workspace and run:

```
/dev PROJ-42
```

---

## Common commands

| Situation | Command |
|-----------|---------|
| Start a new ticket | `/dev PROJ-42` |
| Resume after a break | `/dev PROJ-42 resume` |
| Check ticket state | `/dev PROJ-42 status` |
| Create the PR | `/pr PROJ-42` |
| Fix review comments | `/dev https://github.com/.../pull/42` |
| Review a teammate's PR | `/dev review https://github.com/.../pull/42` |
| Close the ticket | `/reflect PROJ-42 closing` |
| See all active work | `/dev status` |
| Pull a fresh prod DB snapshot | `/dev db-sync <project>` |

---

## Configuration

Everything project-specific lives in `config.sh` (gitignored — never committed).

```bash
cp config.example.sh config.sh
```

| Variable | Description | Example |
|----------|-------------|---------|
| `JIRA_SCRIPTS` | Path to your Jira scripts | `/path/to/jira-communication/scripts` |
| `PROJECT_KEY` | Jira project key (uppercase) | `PROJ` |
| `PROJECT_KEY_LOWER` | Same, lowercase (branch names) | `proj` |
| `JIRA_BASE_URL` | Your Jira instance URL | `https://your-org.atlassian.net` |
| `REPOS` | Repo directories, space-separated | `backend-api frontend-app` |
| `SPECIAL_REPO_PATTERNS` | Repos (glob patterns) with a non-standard base branch | `frontend-app legacy-*` |
| `SPECIAL_REPO_BASE` | Their base branch | `develop` |
| `DB_SYNC_REPOS` | Repos supporting `/dev db-sync` (Phase 15) — leave empty to disable | `backend-api` |

The skills also contain **architecture rules** and **keyword-to-repo mappings** tailored as examples — look for `> CUSTOMIZE` comments in `dev/SKILL.md` and `assess/SKILL.md` and replace them with your stack's conventions.

After editing config or skill templates, regenerate:

```bash
git pull && ./install.sh
```

---

## Requirements

| Tool | Install |
|------|---------|
| [Claude Code](https://claude.ai/code) | see docs |
| [`gh`](https://cli.github.com/) | `brew install gh` / `apt install gh` |
| [`uv`](https://github.com/astral-sh/uv) | `curl -Ls https://astral.sh/uv/install.sh \| sh` |
| `envsubst` | `brew install gettext` / `apt install gettext` |
| `JIRA_TOKEN` env var | Personal Access Token from your Jira instance |
