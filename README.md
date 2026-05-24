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
/dev MSOF-XXX
    │
    ├── /assess MSOF-XXX      ← technical deep dive + Jira enrichment
    │
    ├── Phase 2: Branch setup
    ├── Phase 3: Development
    ├── Phase 4: Validation
    ├── Phase 5: Commit
    ├── Phase 6: Push
    │
    ├── /pr MSOF-XXX          ← create PR + ultrareview
    └── /reflect MSOF-XXX     ← closing reflection + memory
```

## Subcommands

| Command | Action |
|---------|--------|
| `/dev MSOF-XXX` | Full workflow from scratch |
| `/dev MSOF-XXX resume` | Reconstruct development context + standup summary |
| `/dev MSOF-XXX status` | Quick read-only ticket state (6 lines) |
| `/dev MSOF-XXX migration` | DB migration workflow (QuintaApp-Api) |
| `/dev MSOF-XXX reflect` | Post-ticket reflection → delegates to `/reflect` |
| `/dev <PR URL>` | Resume own PR / handle review comments |
| `/dev review <PR URL>` | Code review for a teammate's PR |
| `/dev status` | Multi-ticket overview across all repos |

## Installation

Copy the skills you want into `~/.claude/skills/`:

```bash
mkdir -p ~/.claude/skills/dev ~/.claude/skills/assess ~/.claude/skills/pr ~/.claude/skills/reflect

curl -o ~/.claude/skills/dev/SKILL.md     https://raw.githubusercontent.com/jorgeemilianom/skill-charly-dev/master/dev/SKILL.md
curl -o ~/.claude/skills/assess/SKILL.md  https://raw.githubusercontent.com/jorgeemilianom/skill-charly-dev/master/assess/SKILL.md
curl -o ~/.claude/skills/pr/SKILL.md      https://raw.githubusercontent.com/jorgeemilianom/skill-charly-dev/master/pr/SKILL.md
curl -o ~/.claude/skills/reflect/SKILL.md https://raw.githubusercontent.com/jorgeemilianom/skill-charly-dev/master/reflect/SKILL.md
```

### Requirements

- [Claude Code](https://claude.ai/code) CLI
- [`gh`](https://cli.github.com/) — GitHub CLI (authenticated)
- [`uv`](https://github.com/astral-sh/uv) — Python package manager
- Jira account at `msoftia.atlassian.net` with `JIRA_TOKEN` env var
- `.ai-memory/` directory at the workspace root (auto-created by the workflow)
