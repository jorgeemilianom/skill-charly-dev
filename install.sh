#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────
#  skill-charly-dev  —  installer
#
#  Reads config.sh (or config.example.sh as fallback),
#  substitutes project-specific variables into each SKILL.md
#  template, and writes the final files to ~/.claude/skills/.
#
#  To update after a git pull:  git pull && ./install.sh
# ─────────────────────────────────────────────

SKILLS_DIR="$HOME/.claude/skills"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS=(dev assess pr reflect)

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${GREEN}✓${NC} $*"; }
warn()    { echo -e "${YELLOW}!${NC} $*"; }
error()   { echo -e "${RED}✗${NC} $*" >&2; }
heading() { echo -e "\n${YELLOW}$*${NC}"; }
dim()     { echo -e "${CYAN}  $*${NC}"; }

for arg in "$@"; do
  case "$arg" in
    --help|-h)
      echo "Usage: ./install.sh"
      echo ""
      echo "  Reads config.sh (copy config.example.sh and fill in your values)."
      echo "  Generates ~/.claude/skills/<name>/SKILL.md with your config substituted."
      echo "  Run again after 'git pull' to update."
      exit 0
      ;;
    *) error "Unknown flag: $arg"; exit 1 ;;
  esac
done

# ── 1. Check requirements ─────────────────────
heading "Checking requirements..."

if ! command -v claude &>/dev/null; then
  error "Claude Code CLI not found. Install it from https://claude.ai/code"
  exit 1
fi
info "Claude Code: $(claude --version 2>/dev/null || echo 'found')"

check_optional() {
  local cmd=$1 label=$2 url=$3
  if command -v "$cmd" &>/dev/null; then
    info "$label: $(command -v "$cmd")"
  else
    warn "$label not found — some skill features won't work. Install: $url"
  fi
}
check_optional gh       "gh (GitHub CLI)"     "https://cli.github.com/"
check_optional uv       "uv (Python)"         "https://github.com/astral-sh/uv"
check_optional envsubst "envsubst (gettext)"  "sudo apt install gettext  /  brew install gettext"

# ── 2. Load config ────────────────────────────
heading "Loading config..."

CONFIG_FILE="$REPO_DIR/config.sh"
if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
  info "Using $CONFIG_FILE"
else
  source "$REPO_DIR/config.example.sh"
  warn "config.sh not found — using config.example.sh defaults"
  warn "Copy config.example.sh → config.sh and fill in your values."
fi

# envsubst only replaces literal ${VAR} references — it doesn't evaluate bash
# parameter expansions. Pre-compute the pipe-joined form here so templates can
# drop it straight into a `case` pattern without needing SPECIAL_REPO_PATTERNS
# to exist as a real env var at skill-execution time.
export SPECIAL_REPO_CASE_PATTERN="${SPECIAL_REPO_PATTERNS// /|}"

# Only these vars are substituted; all other \${...} in bash blocks are preserved.
SUBST_VARS='${JIRA_SCRIPTS}${PROJECT_KEY}${PROJECT_KEY_LOWER}${JIRA_BASE_URL}${REPOS}${SPECIAL_REPO_PATTERNS}${SPECIAL_REPO_BASE}${SPECIAL_REPO_CASE_PATTERN}${DB_SYNC_REPOS}'

dim "JIRA_SCRIPTS          = ${JIRA_SCRIPTS:-<not set>}"
dim "PROJECT_KEY           = ${PROJECT_KEY:-<not set>}"
dim "JIRA_BASE_URL         = ${JIRA_BASE_URL:-<not set>}"
dim "REPOS                 = ${REPOS:-<not set>}"
dim "SPECIAL_REPO_PATTERNS = ${SPECIAL_REPO_PATTERNS:-(none)} → base: ${SPECIAL_REPO_BASE:-master}"
dim "DB_SYNC_REPOS         = ${DB_SYNC_REPOS:-(none, db-sync disabled)}"

# ── 3. Generate and install ───────────────────
heading "Installing skills to $SKILLS_DIR ..."

INSTALLED=()
UPDATED=()
SKIPPED=()

for skill in "${SKILLS[@]}"; do
  template="$REPO_DIR/$skill/SKILL.md"
  dest_dir="$SKILLS_DIR/$skill"
  dest="$dest_dir/SKILL.md"

  if [[ ! -f "$template" ]]; then
    warn "Skipping '$skill' — SKILL.md template not found"
    continue
  fi

  mkdir -p "$dest_dir"

  # Substitute only the listed config vars; other ${...} in bash blocks are left as-is
  generated=$(envsubst "$SUBST_VARS" < "$template")

  if [[ -L "$dest" ]]; then
    rm "$dest"
    printf '%s\n' "$generated" > "$dest"
    UPDATED+=("$skill")
    info "Replaced symlink with generated: ~/.claude/skills/$skill/SKILL.md"
  elif [[ -f "$dest" ]]; then
    existing=$(cat "$dest")
    if [[ "$generated" == "$existing" ]]; then
      SKIPPED+=("$skill")
      continue
    fi
    printf '%s\n' "$generated" > "$dest"
    UPDATED+=("$skill")
    info "Updated  ~/.claude/skills/$skill/SKILL.md"
  else
    printf '%s\n' "$generated" > "$dest"
    INSTALLED+=("$skill")
    info "Installed ~/.claude/skills/$skill/SKILL.md"
  fi
done

for s in "${SKIPPED[@]}"; do
  info "Up to date ~/.claude/skills/$s/SKILL.md"
done

# ── 4. Summary ────────────────────────────────
heading "Done."
echo ""
echo "  Installed : ${#INSTALLED[@]} skill(s)"
echo "  Updated   : ${#UPDATED[@]} skill(s)"
echo "  Up to date: ${#SKIPPED[@]} skill(s)"
echo ""
echo "  To update after a git pull:"
echo "    cd $REPO_DIR && git pull && ./install.sh"
echo ""
echo "  Available slash commands in Claude Code:"
for skill in "${SKILLS[@]}"; do
  echo "    /$skill"
done
echo ""
echo "  Quick start:"
echo "    /dev ${PROJECT_KEY}-XXX      full workflow for a Jira ticket"
echo "    /dev status          see all active branches"
echo "    /dev review <URL>    review a teammate's PR"
echo ""
