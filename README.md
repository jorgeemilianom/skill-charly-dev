# skill-charly-dev

Autonomous AI software engineer workflow that transforms Jira tickets into production-ready pull requests.

## Skills

| Skill | Description |
|-------|-------------|
| [`/dev`](dev/SKILL.md) | **Main orchestrator.** Accepts a ticket ID, a PR URL, or `review <PR URL>`. Routes to the correct phase: assessment, branch setup, development, validation, commit, push, PR creation, or review handling. |
| [`/assess`](assess/SKILL.md) | Technical deep dive before writing any code. Reads Jira, detects affected repos, explores the codebase with architecture-aware heuristics, loads `.ai-memory` context, and produces a Technical Assessment. |
| [`/pr`](pr/SKILL.md) | Creates a pull request or handles review comments. Builds the PR body from test files and specs, creates the PR via `gh`, posts a Jira comment, and runs `/ultrareview`. |
| [`/reflect`](reflect/SKILL.md) | Snapshot and self-reflection for tickets. Checkpoint mode (snapshot only) or closing mode (full reflection + Jira comment + memory persistence). |

## Workflow

```
/dev PROJ-XXX
    │
    ├── /assess PROJ-XXX      ← technical deep dive + Jira enrichment
    │
    ├── Phase 2: Branch setup
    ├── Phase 3: Development
    ├── Phase 4: Validation
    ├── Phase 5: Commit
    ├── Phase 6: Push
    │
    ├── /pr PROJ-XXX          ← create PR + ultrareview
    └── /reflect PROJ-XXX     ← closing reflection + memory
```

## Subcommands

| Command | Action |
|---------|--------|
| `/dev PROJ-XXX` | Full workflow from scratch |
| `/dev PROJ-XXX resume` | Reconstruct development context + standup summary |
| `/dev PROJ-XXX status` | Quick read-only ticket state (6 lines) |
| `/dev PROJ-XXX migration` | DB migration workflow |
| `/dev PROJ-XXX reflect` | Post-ticket reflection → delegates to `/reflect` |
| `/dev <PR URL>` | Resume own PR / handle review comments |
| `/dev review <PR URL>` | Code review for a teammate's PR |
| `/dev status` | Multi-ticket overview across all repos |

## Installation

```bash
git clone https://github.com/jorgeemilianom/skill-charly-dev.git
cd skill-charly-dev
cp config.example.sh config.sh   # fill in your project values
./install.sh
```

The installer reads `config.sh`, substitutes your project's values into the skill templates, and writes the final files to `~/.claude/skills/`.

To update after a `git pull`:

```bash
git pull && ./install.sh
```

## Configuration

All project-specific values live in `config.sh` (gitignored). Copy the example and edit:

```bash
cp config.example.sh config.sh
```

| Variable | Description | Example |
|----------|-------------|---------|
| `JIRA_SCRIPTS` | Path to jira-communication scripts | `/path/to/jira-communication/scripts` |
| `PROJECT_KEY` | Jira project key (uppercase) | `PROJ` |
| `PROJECT_KEY_LOWER` | Same in lowercase (used in branch names) | `proj` |
| `JIRA_BASE_URL` | Your Jira base URL | `https://your-org.atlassian.net` |
| `REPOS` | Space-separated repo directory names | `backend-api frontend-app` |
| `SPECIAL_REPO` | Repo that uses a non-standard base branch | `frontend-app` |
| `SPECIAL_REPO_BASE` | Its base branch | `develop` |

> The skill files also contain project-specific **architecture rules** and **keyword-to-repo mappings** (marked with `> CUSTOMIZE` comments). Edit those sections in `dev/SKILL.md` and `assess/SKILL.md` to match your stack, then re-run `./install.sh`.

## Requirements

| Tool | Purpose |
|------|---------|
| [Claude Code](https://claude.ai/code) | runs the skills |
| [`gh`](https://cli.github.com/) | create PRs, checkout branches, post reviews |
| [`uv`](https://github.com/astral-sh/uv) | runs the Jira Python scripts |
| [`envsubst`](https://www.gnu.org/software/gettext/) | config substitution at install time (`apt install gettext` / `brew install gettext`) |
| `JIRA_TOKEN` env var | authenticate against your Jira instance |
| `.ai-memory/` at workspace root | auto-created — stores snapshots, assessments, user profile |
