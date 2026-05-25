#!/usr/bin/env bash
# charly-dev — project configuration
# Copy this file to config.sh and fill in your values.
# config.sh is gitignored — never commit it.

# ── Jira ─────────────────────────────────────
# Path to the jira-communication scripts directory
# (clone https://github.com/your-org/jira-communication or equivalent)
export JIRA_SCRIPTS="/path/to/jira-communication/scripts"

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

# If one repo uses a non-standard base branch (e.g. "develop" instead of "master"),
# set it here. Leave SPECIAL_REPO empty if all repos use "master".
export SPECIAL_REPO=""
export SPECIAL_REPO_BASE="develop"

# ── Notes ────────────────────────────────────
# After editing this file, run ./install.sh to regenerate the skills:
#   cd ~/skills/charly-dev && ./install.sh
#
# To update skills after a git pull:
#   git pull && ./install.sh
