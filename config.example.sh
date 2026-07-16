#!/usr/bin/env bash
# charly-dev — project configuration
# Copy this file to config.sh and fill in your values.
# config.sh is gitignored — never commit it.

# ── Jira ─────────────────────────────────────
# Path to the jira-communication scripts directory.
# Leave empty to use the copy vendored in this repo (scripts/jira-communication) —
# install.sh copies it into your project automatically. Only set this to point
# at your own separate jira-communication installation instead.
export JIRA_SCRIPTS=""

# Jira project key (uppercase). Used in issue IDs and search queries.
export PROJECT_KEY="PROJ"

# Lowercase version (used in branch name patterns like feature/proj-42)
export PROJECT_KEY_LOWER="proj"

# Your Jira base URL (no trailing slash)
export JIRA_BASE_URL="https://your-org.atlassian.net"

# ── Repositories ─────────────────────────────
# Space-separated list of repo directory names, in implementation order
# (first = most foundational / backend, last = most independent)
export REPOS="backend-api frontend-app"

# Subfolder (relative to the workspace root) that repos live under, e.g. "projects"
# if you clone repos into <workspace>/projects/<repo> instead of <workspace>/<repo>
# directly. Leave empty for the flat layout (repos as direct children of the root).
export PROJECTS_SUBDIR=""

# If some repos use a non-standard base branch (e.g. "develop" instead of "master"),
# list them here as space-separated glob patterns (exact names or trailing "*").
# Leave empty if all repos use "master".
export SPECIAL_REPO_PATTERNS=""
export SPECIAL_REPO_BASE="develop"

# ── DB sync (optional) ───────────────────────
# Repos that support the "db-sync" subcommand (dev-db-sync/SKILL.md) —
# i.e. have a Makefile with backup/import targets for pulling a prod DB snapshot.
# Leave empty to disable db-sync entirely.
export DB_SYNC_REPOS=""

# ── Cross-tool adapter (optional) ────────────
# Path to this project's Claude Code auto-memory index (~/.claude/projects/<escaped-path>/memory/MEMORY.md).
# Referenced from agent-context.md as a legacy fallback so Codex can see it too. Leave empty to omit.
export CLAUDE_MEMORY_INDEX=""

# ── Notes ────────────────────────────────────
# Run ./install.sh FROM INSIDE the target project (the directory containing this
# project's CLAUDE.md) — it installs into <project>/.ai/skills, not a global location.
#
# To update after a git pull:
#   cd /path/to/skill-charly-dev && git pull && (cd /path/to/your/project && /path/to/skill-charly-dev/install.sh)
