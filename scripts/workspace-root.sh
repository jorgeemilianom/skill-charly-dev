#!/usr/bin/env bash
# Resolve the MSoftIA workspace root and print it.
#
# The workspace root is identified by having BOTH CLAUDE.md and config.example.sh at its
# top level — using CLAUDE.md alone is not enough, since sub-repos under projects/ (and some
# Business/<cliente>/ folders) have their own local CLAUDE.md for repo-specific context.
#
# Walks up from git's toplevel (or cwd, if not inside a git repo) until it finds a directory
# with both markers, so this resolves correctly regardless of nesting depth: invoked from the
# workspace root itself, from a repo directly under it (flat layout), or from a repo nested
# under projects/<repo> or Business/<cliente> (this workspace's actual layout). Falls back to
# git's toplevel (or cwd) if no match is found walking up — better to return something than
# fail outright.
#
# This exact algorithm is also inlined at the top of every skill's bash blocks, because a
# skill can't source this file before it knows where the workspace root is (the chicken-and-egg
# problem this script exists to solve). Keep both in sync if the algorithm ever changes.
set -euo pipefail

dir="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fallback="$dir"

while [ -n "$dir" ] && [ "$dir" != "/" ]; do
  if [ -f "$dir/CLAUDE.md" ] && [ -f "$dir/config.example.sh" ]; then
    echo "$dir"
    exit 0
  fi
  dir="$(dirname "$dir")"
done

echo "$fallback"
