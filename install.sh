#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────
#  skill-charly-dev  —  installer
#
#  Run this FROM INSIDE the target project (any directory under the project
#  root that contains CLAUDE.md). Reads config.sh (or config.example.sh as
#  fallback), substitutes project-specific variables into each SKILL.md
#  template plus the shared adapter templates, and writes everything into
#  the project:
#
#    <project>/.ai/skills/<name>/SKILL.md   — canonical skill sources
#    <project>/.ai/agent-context.md         — shared Codex/Claude adapter
#    <project>/AGENTS.md                    — Codex-native root pointer
#    <project>/.claude/skills/<name>        — symlinks for Claude discovery
#
#  To update after a git pull:  git pull && (cd /path/to/project && /path/to/skill-charly-dev/install.sh)
# ─────────────────────────────────────────────

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS=(dev dev-create dev-assess dev-pr dev-reflect dev-resume dev-review dev-migration dev-status dev-db-sync)

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
      echo "Usage: (run from inside your project) /path/to/skill-charly-dev/install.sh"
      echo ""
      echo "  Reads config.sh (copy config.example.sh and fill in your values)."
      echo "  Generates <project>/.ai/skills/<name>/SKILL.md with your config substituted,"
      echo "  plus <project>/.ai/agent-context.md, <project>/AGENTS.md, and"
      echo "  <project>/.claude/skills/<name> symlinks."
      echo "  Run again after 'git pull' to update."
      exit 0
      ;;
    *) error "Unknown flag: $arg"; exit 1 ;;
  esac
done

# ── 1. Locate the target project ──────────────
heading "Locating project root..."

find_project_root() {
  local dir="$PWD"
  while [[ "$dir" != "/" ]]; do
    if [[ -f "$dir/CLAUDE.md" ]]; then
      echo "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

if ! PROJECT_ROOT="$(find_project_root)"; then
  error "No CLAUDE.md found in $PWD or any parent directory."
  error "Run this installer from inside the target project (or create CLAUDE.md first)."
  exit 1
fi
info "Project root: $PROJECT_ROOT"

# ── 2. Check requirements ─────────────────────
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

# ── 3. Load config ────────────────────────────
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

# ── 3b. Vendor third-party scripts ────────────
# The skills call out to the jira-communication CLI scripts. Rather than require
# a separately-installed skill on every machine, a copy ships in this repo
# (vendor/jira-communication/ — see its NOTICE.md for source/license) and gets
# copied into the project on install. JIRA_SCRIPTS in config.sh, if set,
# overrides this with your own installation instead.
heading "Vendoring third-party scripts..."

VENDOR_SRC="$REPO_DIR/vendor/jira-communication"
VENDOR_DEST="$PROJECT_ROOT/.ai/vendor/jira-communication"
if [[ -d "$VENDOR_SRC" ]]; then
  mkdir -p "$(dirname "$VENDOR_DEST")"
  rm -rf "$VENDOR_DEST"
  cp -r "$VENDOR_SRC" "$VENDOR_DEST"
  info "Vendored jira-communication scripts → .ai/vendor/jira-communication/"
else
  warn "No vendor/jira-communication found in $REPO_DIR — skipping"
fi

if [[ -z "${JIRA_SCRIPTS:-}" ]]; then
  export JIRA_SCRIPTS="$VENDOR_DEST/scripts"
  dim "JIRA_SCRIPTS not set in config.sh — defaulting to the vendored copy"
fi

# envsubst only replaces literal ${VAR} references — it doesn't evaluate bash
# parameter expansions. Pre-compute the pipe-joined form here so templates can
# drop it straight into a `case` pattern without needing SPECIAL_REPO_PATTERNS
# to exist as a real env var at skill-execution time.
export SPECIAL_REPO_CASE_PATTERN="${SPECIAL_REPO_PATTERNS// /|}"

# Only these vars are substituted; all other \${...} in bash blocks are preserved.
SUBST_VARS='${JIRA_SCRIPTS}${PROJECT_KEY}${PROJECT_KEY_LOWER}${JIRA_BASE_URL}${REPOS}${SPECIAL_REPO_PATTERNS}${SPECIAL_REPO_BASE}${SPECIAL_REPO_CASE_PATTERN}${DB_SYNC_REPOS}${CLAUDE_MEMORY_INDEX}'

dim "JIRA_SCRIPTS          = ${JIRA_SCRIPTS:-<not set>}"
dim "PROJECT_KEY           = ${PROJECT_KEY:-<not set>}"
dim "JIRA_BASE_URL         = ${JIRA_BASE_URL:-<not set>}"
dim "REPOS                 = ${REPOS:-<not set>}"
dim "SPECIAL_REPO_PATTERNS = ${SPECIAL_REPO_PATTERNS:-(none)} → base: ${SPECIAL_REPO_BASE:-master}"
dim "DB_SYNC_REPOS         = ${DB_SYNC_REPOS:-(none, db-sync disabled)}"
dim "CLAUDE_MEMORY_INDEX   = ${CLAUDE_MEMORY_INDEX:-(none)}"

# ── 4. Generate and install skills ────────────
SKILLS_OUT="$PROJECT_ROOT/.ai/skills"
CLAUDE_SKILLS_DIR="$PROJECT_ROOT/.claude/skills"
heading "Installing skills to $SKILLS_OUT ..."

INSTALLED=()
UPDATED=()
SKIPPED=()

for skill in "${SKILLS[@]}"; do
  template="$REPO_DIR/$skill/SKILL.md"
  dest_dir="$SKILLS_OUT/$skill"
  dest="$dest_dir/SKILL.md"

  if [[ ! -f "$template" ]]; then
    warn "Skipping '$skill' — SKILL.md template not found"
    continue
  fi

  mkdir -p "$dest_dir"

  # Substitute only the listed config vars; other ${...} in bash blocks are left as-is
  generated=$(envsubst "$SUBST_VARS" < "$template")

  if [[ -f "$dest" ]] && [[ "$generated" == "$(cat "$dest")" ]]; then
    SKIPPED+=("$skill")
  elif [[ -f "$dest" ]]; then
    printf '%s\n' "$generated" > "$dest"
    UPDATED+=("$skill")
    info "Updated  .ai/skills/$skill/SKILL.md"
  else
    printf '%s\n' "$generated" > "$dest"
    INSTALLED+=("$skill")
    info "Installed .ai/skills/$skill/SKILL.md"
  fi

  # Claude Code discovery bridge: relative symlink, mirrors the ~/.agents/skills pattern
  mkdir -p "$CLAUDE_SKILLS_DIR"
  link="$CLAUDE_SKILLS_DIR/$skill"
  if [[ -L "$link" || -e "$link" ]]; then
    rm -rf "$link"
  fi
  ln -s "../../.ai/skills/$skill" "$link"
done

for s in "${SKIPPED[@]}"; do
  info "Up to date .ai/skills/$s/SKILL.md"
done

# ── 5. Generate the shared adapter + Codex pointer ──────
heading "Installing shared adapter..."

AGENT_CONTEXT_DEST="$PROJECT_ROOT/.ai/agent-context.md"
generated_ctx=$(envsubst "$SUBST_VARS" < "$REPO_DIR/agent-context.md.template")
if [[ -f "$AGENT_CONTEXT_DEST" ]] && [[ "$generated_ctx" == "$(cat "$AGENT_CONTEXT_DEST")" ]]; then
  info "Up to date .ai/agent-context.md"
else
  printf '%s\n' "$generated_ctx" > "$AGENT_CONTEXT_DEST"
  info "Wrote .ai/agent-context.md"
fi

AGENTS_MD_DEST="$PROJECT_ROOT/AGENTS.md"
generated_agents=$(envsubst "$SUBST_VARS" < "$REPO_DIR/AGENTS.md.template")
if [[ -f "$AGENTS_MD_DEST" ]]; then
  if [[ "$generated_agents" == "$(cat "$AGENTS_MD_DEST")" ]]; then
    info "Up to date AGENTS.md"
  else
    warn "AGENTS.md already exists at $AGENTS_MD_DEST with different content — not overwriting."
    warn "Compare manually against the template: $REPO_DIR/AGENTS.md.template"
  fi
else
  printf '%s\n' "$generated_agents" > "$AGENTS_MD_DEST"
  info "Wrote AGENTS.md"
fi

# ── 6. Summary ────────────────────────────────
heading "Done."
echo ""
echo "  Installed : ${#INSTALLED[@]} skill(s)"
echo "  Updated   : ${#UPDATED[@]} skill(s)"
echo "  Up to date: ${#SKIPPED[@]} skill(s)"
echo ""
echo "  To update after a git pull:"
echo "    cd $REPO_DIR && git pull && (cd $PROJECT_ROOT && $REPO_DIR/install.sh)"
echo ""
echo "  Available in Claude Code (project-scoped, from inside $PROJECT_ROOT):"
for skill in "${SKILLS[@]}"; do
  echo "    /$skill"
done
echo ""
echo "  Codex reads AGENTS.md → .ai/agent-context.md → .ai/skills/<name>/SKILL.md automatically."
echo ""
echo "  Quick start:"
echo "    /dev ${PROJECT_KEY}-XXX      full workflow for a Jira ticket"
echo "    /dev-status                  see all active branches"
echo "    /dev-review <URL>            review a teammate's PR"
echo ""
