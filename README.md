# skill-charly-dev

**From Jira ticket to merged PR — one command, full workflow. Works from Claude Code and Codex.**

A set of skills that act as a senior engineer pair: reads your ticket, explores the codebase, implements the changes, runs the tests, opens the PR, handles review comments, and remembers every decision along the way. Installs *inside* your project, not your home directory, so it travels with the repo and works the same from either agent.

---

## The problem

Every ticket follows the same ritual: read the ticket, find the files, remember the architecture, create the branch, write code, run tests, write the PR description, handle review comments, transition Jira... It's slow, repetitive, and full of context switching.

These skills automate all of it. You stay in charge — the agent does the groundwork.

---

## How it works

```
you                    agent
─────────────────────────────────────────────────────
/dev-create "add booking cancellation"
                       drafts the spec with you
                       resolves the epic (cached — no re-asking)
                       files the Jira ticket
─────────────────────────────────────────────────────
/dev PROJ-42
                       reads ticket from Jira
                       explores codebase (grep, git log, file reads)
                       loads past decisions from .ai/memory/
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
/dev-pr PROJ-42
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

/dev-reflect PROJ-42 closing
                       saves learnings to .ai/memory/
                       transitions Jira to Done
                       posts closing comment
```

The longer you use it, the better it gets — `.ai/memory/` accumulates your project's decisions, recurring mistakes, and patterns across tickets.

---

## Skills

`/dev` is the orchestrator — it runs the core loop (branch → code → tests → commit → push) itself and
routes everything else to these siblings:

| Skill | What it does |
|-------|--------------|
| [`/dev`](dev/SKILL.md) | Orchestrator. Full core loop for a ticket ID; routes freeform ideas, PR URLs, and subcommands to the skills below. |
| [`/dev-create`](dev-create/SKILL.md) | Turns a freeform idea into a filed Jira ticket — drafts the spec with you, resolves the epic from a cached list. |
| [`/dev-assess`](dev-assess/SKILL.md) | Technical deep dive before writing any code. Produces a structured assessment with confidence score and waits for your go-ahead. |
| [`/dev-pr`](dev-pr/SKILL.md) | Creates the PR or handles incoming review comments. Builds the body, posts to Jira, runs automated review. |
| [`/dev-reflect`](dev-reflect/SKILL.md) | Saves a snapshot at any point (checkpoint) or runs a full closing reflection when the PR merges. Feeds learnings back into memory. |
| [`/dev-resume`](dev-resume/SKILL.md) | Reconstructs full context for a ticket already in progress, with a standup blurb. |
| [`/dev-review`](dev-review/SKILL.md) | Reviews a teammate's PR against your architecture and conventions. |
| [`/dev-migration`](dev-migration/SKILL.md) | DB migration workflow (check pending, create, review, run, commit). |
| [`/dev-status`](dev-status/SKILL.md) | Read-only ticket or workspace-wide state — no side effects. |
| [`/dev-db-sync`](dev-db-sync/SKILL.md) | Pulls a production DB snapshot over SSH for local development. |

---

## Cross-tool: Claude Code + Codex

Installing writes into your project, not `~/.claude/skills`:

```
<project>/
├── AGENTS.md                    # Codex-native root pointer
├── CLAUDE.md                    # your existing Claude-native file, untouched
├── .ai/
│   ├── agent-context.md         # shared adapter: prefs, memory locations, skill map
│   └── skills/<name>/SKILL.md   # canonical skill sources
└── .claude/skills/<name>        # symlinks → ../../.ai/skills/<name>, for Claude discovery
```

Claude Code auto-discovers the symlinked skills the moment you're in the project — no extra config.
Codex has no reliable cross-version skills-directory auto-discovery, so `AGENTS.md` (which Codex always
reads) points to `.ai/agent-context.md`, which tells it exactly which `.ai/skills/<name>/SKILL.md` to
read for a given request.

---

## Quick start

```bash
# 1. clone the skill repo anywhere (it's a template, not your project)
git clone https://github.com/jorgeemilianom/skill-charly-dev.git ~/skills/charly-dev
cd ~/skills/charly-dev

# 2. configure (your Jira, your repos)
cp config.example.sh config.sh
$EDITOR config.sh

# 3. install — run FROM INSIDE your target project (needs a CLAUDE.md there)
cd /path/to/your/project
~/skills/charly-dev/install.sh
```

Then, in Claude Code or Codex, from inside that project:

```
/dev-create "short description of what you want to build"
```

or, for an existing ticket:

```
/dev PROJ-42
```

---

## Common commands

| Situation | Command |
|-----------|---------|
| Spec + file a new ticket | `/dev-create "<idea>"` |
| Start a new ticket | `/dev PROJ-42` |
| Resume after a break | `/dev-resume PROJ-42` |
| Check ticket state | `/dev-status PROJ-42` |
| Create the PR | `/dev-pr PROJ-42` |
| Fix review comments | `/dev https://github.com/.../pull/42` |
| Review a teammate's PR | `/dev-review https://github.com/.../pull/42` |
| Close the ticket | `/dev-reflect PROJ-42 closing` |
| See all active work | `/dev-status` |
| Pull a fresh prod DB snapshot | `/dev-db-sync <project>` |

---

## Configuration

Everything project-specific lives in `config.sh` (gitignored — never committed).

```bash
cp config.example.sh config.sh
```

| Variable | Description | Example |
|----------|-------------|---------|
| `JIRA_SCRIPTS` | Path to Jira CLI scripts. Leave empty to use the copy vendored in this repo | `/path/to/your-own/jira-communication/scripts` |
| `PROJECT_KEY` | Jira project key (uppercase) | `PROJ` |
| `PROJECT_KEY_LOWER` | Same, lowercase (branch names) | `proj` |
| `JIRA_BASE_URL` | Your Jira instance URL | `https://your-org.atlassian.net` |
| `REPOS` | Repo directories, space-separated | `backend-api frontend-app` |
| `SPECIAL_REPO_PATTERNS` | Repos (glob patterns) with a non-standard base branch | `frontend-app legacy-*` |
| `SPECIAL_REPO_BASE` | Their base branch | `develop` |
| `DB_SYNC_REPOS` | Repos supporting `/dev-db-sync` — leave empty to disable | `backend-api` |
| `CLAUDE_MEMORY_INDEX` | Path to this project's Claude auto-memory `MEMORY.md`, surfaced to Codex as a legacy fallback | `~/.claude/projects/<escaped-path>/memory/MEMORY.md` |

The skills also contain **architecture rules** and **keyword-to-repo mappings** tailored as examples — look for `> CUSTOMIZE` comments in `dev-review/SKILL.md` and `dev-assess/SKILL.md` and replace them with your stack's conventions.

After editing config or skill templates, regenerate from inside your project:

```bash
cd ~/skills/charly-dev && git pull
(cd /path/to/your/project && ~/skills/charly-dev/install.sh)
```

---

## Requirements

| Tool | Install |
|------|---------|
| [Claude Code](https://claude.ai/code) and/or [Codex CLI](https://developers.openai.com/codex) | see docs |
| [`gh`](https://cli.github.com/) | `brew install gh` / `apt install gh` |
| [`uv`](https://github.com/astral-sh/uv) | `curl -Ls https://astral.sh/uv/install.sh \| sh` |
| `envsubst` | `brew install gettext` / `apt install gettext` |
| `JIRA_TOKEN` env var | Personal Access Token from your Jira instance |
