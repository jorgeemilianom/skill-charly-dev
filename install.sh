#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────
#  skill-charly-dev  —  installer
#
#  Default: symlink mode (skills update on git pull)
#  Use --copy to copy files instead of symlinking
# ─────────────────────────────────────────────

SKILLS_DIR="$HOME/.claude/skills"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS=(dev assess pr reflect)
MODE="link"   # "link" | "copy"

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

# ── Parse flags ───────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --copy) MODE="copy" ;;
    --link) MODE="link" ;;
    --help|-h)
      echo "Usage: ./install.sh [--link|--copy]"
      echo ""
      echo "  --link  (default) symlink SKILL.md files — skills update automatically on git pull"
      echo "  --copy            copy files — skills are independent of the repo after install"
      exit 0
      ;;
    *) error "Unknown flag: $arg"; exit 1 ;;
  esac
done

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
if [[ "$MODE" == "link" ]]; then
  heading "Linking skills → $SKILLS_DIR  (git pull will auto-update)"
  dim "repo: $REPO_DIR"
else
  heading "Copying skills → $SKILLS_DIR"
fi

INSTALLED=()
UPDATED=()
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

  if [[ "$MODE" == "link" ]]; then
    # ── Symlink mode ──────────────────────────
    if [[ -L "$dest" ]]; then
      current_target="$(readlink "$dest")"
      if [[ "$current_target" == "$src" ]]; then
        SKIPPED+=("$skill")
        continue
      fi
      # Pointing somewhere else — update the link
      ln -sf "$src" "$dest"
      UPDATED+=("$skill")
      info "Relinked ~/.claude/skills/$skill/SKILL.md → $src"
    elif [[ -f "$dest" ]]; then
      # Was a plain copy before; replace with symlink
      rm "$dest"
      ln -s "$src" "$dest"
      UPDATED+=("$skill")
      info "Replaced copy with symlink: ~/.claude/skills/$skill/SKILL.md"
    else
      ln -s "$src" "$dest"
      INSTALLED+=("$skill")
      info "Linked   ~/.claude/skills/$skill/SKILL.md → $src"
    fi

  else
    # ── Copy mode ─────────────────────────────
    if [[ -L "$dest" ]]; then
      # Was a symlink; materialise it
      rm "$dest"
      cp "$src" "$dest"
      UPDATED+=("$skill")
      info "Replaced symlink with copy: ~/.claude/skills/$skill/SKILL.md"
    elif [[ -f "$dest" ]]; then
      if cmp -s "$src" "$dest"; then
        SKIPPED+=("$skill")
        continue
      fi
      cp "$src" "$dest"
      UPDATED+=("$skill")
      info "Updated  ~/.claude/skills/$skill/SKILL.md"
    else
      cp "$src" "$dest"
      INSTALLED+=("$skill")
      info "Installed ~/.claude/skills/$skill/SKILL.md"
    fi
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

if [[ "$MODE" == "link" ]]; then
  echo "  Skills are live-linked to this repo."
  echo "  To update: git pull   (no re-install needed)"
  echo ""
fi

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
