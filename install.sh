#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────
#  skill-charly-dev  —  installer
#  Copies Claude Code skills into ~/.claude/skills/
# ─────────────────────────────────────────────

SKILLS_DIR="$HOME/.claude/skills"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS=(dev assess pr reflect)

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # no color

info()    { echo -e "${GREEN}✓${NC} $*"; }
warn()    { echo -e "${YELLOW}!${NC} $*"; }
error()   { echo -e "${RED}✗${NC} $*" >&2; }
heading() { echo -e "\n${YELLOW}$*${NC}"; }

# ── 1. Check for Claude Code ──────────────────
heading "Checking requirements..."

if ! command -v claude &>/dev/null; then
  error "Claude Code CLI not found. Install it from https://claude.ai/code"
  exit 1
fi
info "Claude Code: $(claude --version 2>/dev/null || echo 'found')"

# ── 2. Check optional dependencies ───────────
check_optional() {
  local cmd=$1 label=$2 url=$3
  if command -v "$cmd" &>/dev/null; then
    info "$label: $(command -v "$cmd")"
  else
    warn "$label not found — some skill features won't work. Install: $url"
  fi
}
check_optional gh  "gh (GitHub CLI)" "https://cli.github.com/"
check_optional uv  "uv (Python pkg mgr)" "https://github.com/astral-sh/uv"

# ── 3. Install skills ─────────────────────────
heading "Installing skills to $SKILLS_DIR ..."

INSTALLED=()
SKIPPED=()

for skill in "${SKILLS[@]}"; do
  src="$REPO_DIR/$skill/SKILL.md"
  dest_dir="$SKILLS_DIR/$skill"
  dest="$dest_dir/SKILL.md"

  if [[ ! -f "$src" ]]; then
    warn "Skipping '$skill' — SKILL.md not found in repo"
    continue
  fi

  mkdir -p "$dest_dir"

  if [[ -f "$dest" ]]; then
    # Only overwrite if content differs
    if cmp -s "$src" "$dest"; then
      SKIPPED+=("$skill")
      continue
    fi
    cp "$src" "$dest"
    info "Updated  ~/.claude/skills/$skill/SKILL.md"
  else
    cp "$src" "$dest"
    info "Installed ~/.claude/skills/$skill/SKILL.md"
  fi
  INSTALLED+=("$skill")
done

for s in "${SKIPPED[@]}"; do
  info "Up to date ~/.claude/skills/$s/SKILL.md (no changes)"
done

# ── 4. Summary ────────────────────────────────
heading "Done."
echo ""
echo "  Installed : ${#INSTALLED[@]} skill(s)"
echo "  Up to date: ${#SKIPPED[@]} skill(s)"
echo ""
echo "  Available slash commands in Claude Code:"
for skill in "${SKILLS[@]}"; do
  echo "    /$skill"
done
echo ""
echo "  Quick start:"
echo "    /dev MSOF-XXX       full workflow for a Jira ticket"
echo "    /dev status         see all active branches"
echo "    /dev review <URL>   review a teammate's PR"
echo ""
