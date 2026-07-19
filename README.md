# skill-charly-dev

**From Jira ticket to merged PR — one command, full workflow. Works from Claude Code and Codex.**

A set of skills that act as a senior engineer pair: reads your ticket, explores the codebase, implements the changes, runs the tests, opens the PR, handles review comments, and remembers every decision along the way. Self-hosted — this repo *is* your workspace, not something you install into one.

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
                       loads past decisions from memory/
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
                       saves learnings to memory/
                       transitions Jira to Done
                       posts closing comment
```

The longer you use it, the better it gets — `memory/` accumulates your project's decisions, recurring mistakes, and patterns across tickets.

---

## Skills

`/dev` is the orchestrator — it runs the core loop (branch → code → tests → commit → push) itself and
routes everything else to these siblings:

| Skill | What it does |
|-------|--------------|
| [`/dev-setup`](skills/dev-setup/SKILL.md) | First-run setup and environment health check: config.sh, required tools, Jira credentials, GitHub auth, repos present under `projects/`. |
| [`/dev`](skills/dev/SKILL.md) | Orchestrator. Full core loop for a ticket ID; routes freeform ideas, PR URLs, and subcommands to the skills below. |
| [`/dev-create`](skills/dev-create/SKILL.md) | Turns a freeform idea into a filed Jira ticket — drafts the spec with you, resolves the epic from a cached list. |
| [`/dev-assess`](skills/dev-assess/SKILL.md) | Technical deep dive before writing any code. Produces a structured assessment with confidence score and waits for your go-ahead. |
| [`/dev-pr`](skills/dev-pr/SKILL.md) | Creates the PR or handles incoming review comments. Builds the body, posts to Jira, runs automated review. |
| [`/dev-reflect`](skills/dev-reflect/SKILL.md) | Saves a snapshot at any point (checkpoint) or runs a full closing reflection when the PR merges. Feeds learnings back into memory. |
| [`/dev-resume`](skills/dev-resume/SKILL.md) | Reconstructs full context for a ticket already in progress, with a standup blurb. |
| [`/dev-review`](skills/dev-review/SKILL.md) | Reviews a teammate's PR against your architecture and conventions. |
| [`/dev-migration`](skills/dev-migration/SKILL.md) | DB migration workflow (check pending, create, review, run, commit). |
| [`/dev-status`](skills/dev-status/SKILL.md) | Read-only ticket or workspace-wide state — no side effects. |
| [`/dev-db-sync`](skills/dev-db-sync/SKILL.md) | Pulls a production DB snapshot over SSH for local development. |

Separate family — business-layer only, no code/Jira/PR logic (see [Business context](#business-context-business) below):

| Skill | What it does |
|-------|--------------|
| [`/manager`](skills/manager/SKILL.md) | Orchestrator. Lists known clients, or routes to the skills below. |
| [`/manager-create`](skills/manager-create/SKILL.md) | Interactive bootstrap of a new client's `Business/<cliente>/`. |
| [`/manager-update`](skills/manager-update/SKILL.md) | Refreshes/maintains an existing client's `Business/<cliente>/`. |

---

## Repo layout

This repo doubles as your workspace — clone it and it *is* the folder you work in, no separate install
step. `skills/` is real, tracked source; `.claude/skills/<name>` are committed symlinks into it, so
Claude Code discovers all the skills the moment you `cd` in after `git clone`.

```
skill-charly-dev/               (== your workspace, one folder, one repo)
├── skills/<name>/SKILL.md      ← tracked, public — canonical source for every skill
├── .claude/skills/<name>       ← tracked symlinks → ../../skills/<name>, for Claude discovery
├── scripts/
│   ├── jira-communication/     ← tracked, vendored third-party Jira CLI (see NOTICE.md)
│   └── local/                  ← gitignored — scripts the skills write for themselves over time
├── agent-context.md            ← tracked — shared Codex/Claude adapter (prefs, memory map, skill map)
├── AGENTS.md                   ← tracked — Codex-native root pointer
├── CLAUDE.md                   ← tracked — your project map, no secrets
├── config.example.sh           ← tracked — template, copy to config.sh
├── config.sh                   ← gitignored — your actual values (no secrets either — see Jira below)
├── memory/                     ← gitignored — real ticket/decision/pattern data
├── projects/                   ← only README.md tracked — your actual repo checkouts
│   ├── your-api/
│   └── your-frontend/
└── Business/                   ← only README.md tracked — client context (see below)
    └── your-client/
```

There's no generation step and no `install.sh` — skills read `config.sh` directly at runtime
(`source config.sh` inside the relevant bash blocks), so editing config takes effect immediately.

---

## Business context (`Business/`)

`projects/` holds code; `Business/<cliente>/` holds everything about the client that isn't code —
business context, scripts, credentials, confidential info. It's free-form on purpose: nothing is
required, the skill just reads whatever files are there. One optional convenience file it does know how
to use, `client.md`, maps `projects/` repos back to a client:

```yaml
---
repos: [your-api, your-frontend]
jira_key: PROJ
---
```

`/dev-assess` offers to write it the first time it meets a repo with no client folder — decline and
it just asks again next time, never blocking the ticket. Credentials are never typed into the chat:
`/manager-create` leaves a blank placeholder file for you to fill by hand instead.

| Skill | What it does |
|-------|--------------|
| `/manager-create <cliente>` | Interactive bootstrap of a new client folder. |
| `/manager-update <cliente>` | Refresh/maintain an existing one. |
| `/manager` | Lists known clients, or routes to the two above. |

Like `projects/`, only `Business/README.md` is tracked — the real content is gitignored, and the skill
never assumes a particular VCS layout for it (one shared private repo, one repo per client, or nothing
versioned at all — all work the same way).

---

## Cross-tool: Claude Code + Codex

Claude Code auto-discovers the symlinked skills the moment you're in the repo — no config needed.
Codex has no reliable cross-version skills-directory auto-discovery, so `AGENTS.md` (which Codex always
reads) points to `agent-context.md`, which tells it exactly which `skills/<name>/SKILL.md` to read for a
given request, and where to find `config.sh` for project-specific values.

---

## Quick start

```bash
# 1. clone — this repo becomes your workspace
git clone https://github.com/jorgeemilianom/skill-charly-dev.git ~/skills/charly-dev
cd ~/skills/charly-dev
```

Then, in Claude Code or Codex, from inside the repo:

```
/dev-setup
```

This scaffolds `config.sh` interactively (Jira project key, repos, base branches — no secrets), checks
`gh`/`uv` are installed, checks Jira credentials and GitHub auth (both need a real terminal — it'll tell
you exactly what to run), creates `projects/`, `scripts/local/`, `memory/`, and reports which of your
configured `REPOS` still need `git clone`ing. Re-run it any time — it's idempotent and safe to use as a
health check.

Once it reports everything OK:

```
/dev-create "short description of what you want to build"
```

or, for an existing ticket:

```
/dev PROJ-42
```

`/dev` also runs this same precondition check itself before every ticket, and offers to run
`/dev-setup` if something's missing — you don't have to remember to run it first.

---

## Common commands

| Situation | Command |
|-----------|---------|
| First clone, or credentials/config check | `/dev-setup` |
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
| Bootstrap a new client's business context | `/manager-create <cliente>` |
| Refresh an existing client's business context | `/manager-update <cliente>` |
| List known clients | `/manager` |

---

## Configuration

Everything project-specific lives in `config.sh` (gitignored — never committed, though it holds no
secrets either; Jira/GitHub credentials live outside this repo, see below).

```bash
cp config.example.sh config.sh
```

Skills `source` this file directly at runtime, so there's no regeneration step — edit it and the next
skill invocation picks it up.

| Variable | Description | Example |
|----------|-------------|---------|
| `JIRA_SCRIPTS` | Path to Jira CLI scripts. Leave empty to use the copy vendored in this repo | `/path/to/your-own/jira-communication/scripts` |
| `PROJECT_KEY` | Jira project key (uppercase) | `PROJ` |
| `PROJECT_KEY_LOWER` | Same, lowercase (branch names) | `proj` |
| `JIRA_BASE_URL` | Your Jira instance URL | `https://your-org.atlassian.net` |
| `REPOS` | Repo directories, space-separated | `backend-api frontend-app` |
| `PROJECTS_SUBDIR` | Subfolder repos live under | `projects` |
| `SPECIAL_REPO_PATTERNS` | Repos (glob patterns) with a non-standard base branch | `frontend-app legacy-*` |
| `SPECIAL_REPO_BASE` | Their base branch | `develop` |
| `DB_SYNC_REPOS` | Repos supporting `/dev-db-sync` — leave empty to disable | `backend-api` |
| `CLAUDE_MEMORY_INDEX` | Path to this project's Claude auto-memory `MEMORY.md`, surfaced to Codex as a legacy fallback | `~/.claude/projects/<escaped-path>/memory/MEMORY.md` |

`/dev-setup` scaffolds and asks for all of these interactively — editing by hand is only needed to
change a value later.

Jira and GitHub credentials are **not** in `config.sh` — `/dev-setup` walks you through both, but the
actual secret-entry step always happens in your own terminal, never through the agent:
- Jira: `uv run scripts/jira-communication/scripts/core/jira-setup.py` → writes `~/.env.jira`
- GitHub: `gh auth login`

The skills also contain **architecture rules** and **keyword-to-repo mappings** tailored as examples — look for `> CUSTOMIZE` comments in `skills/dev-review/SKILL.md` and `skills/dev-assess/SKILL.md` and replace them with your stack's conventions.

---

## Requirements

| Tool | Install |
|------|---------|
| [Claude Code](https://claude.ai/code) and/or [Codex CLI](https://developers.openai.com/codex) | see docs |
| [`gh`](https://cli.github.com/) | `brew install gh` / `apt install gh` |
| [`uv`](https://github.com/astral-sh/uv) | `curl -Ls https://astral.sh/uv/install.sh \| sh` |

`/dev-setup` checks both `gh` and `uv` are on `PATH` and tells you if either is missing.
