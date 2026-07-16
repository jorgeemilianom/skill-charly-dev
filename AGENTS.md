# AGENTS.md

This workspace uses a shared adapter so Codex and Claude Code load the same project context.

## Required Startup Context

Before doing project work, read:

1. `agent-context.md`
2. `CLAUDE.md`
3. The local `AGENTS.md` and/or `CLAUDE.md` inside the affected repo subfolder, if present.

The adapter maps Claude memories, Claude skills, and project conventions into Codex-readable
instructions without copying secrets.

## Scope

This file applies at the workspace root. Repo-local `AGENTS.md` files override or extend these rules
inside their own subtrees.

## Safety

Do not duplicate credentials from `~/.claude` or `~/.codex`. Use helper scripts by path when needed.
Preserve user changes in dirty worktrees, and ask before destructive commands, pushes, or external
state changes unless already authorized in the current conversation.
