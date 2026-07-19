# Shared AI Context

This file is the shared adapter between Claude Code and Codex for this workspace. Treat it as the
stable entry point for user preferences, memory locations, skill mappings, and cross-tool fallbacks.
Claude Code does not read this file automatically (it reads `CLAUDE.md`) — it's Codex's entry point,
reached via the root `AGENTS.md`.

## Load Order

1. Read this file first.
2. Read the workspace `CLAUDE.md` for repo overview and conventions.
3. Read `config.sh` for this workspace's Jira project/repo identity (project key, repos, base branches).
4. If working inside a repo subfolder, read that repo's local `AGENTS.md` and/or `CLAUDE.md`.
5. Read task-specific memory only when the task touches that area.

Do not copy secrets from `~/.claude` or other Claude state into project files. If a helper already
embeds credentials, reference the helper path instead of duplicating the credential.

## User Preferences

- Respond in Spanish by default. Keep technical terms in English when that is the natural term in the codebase.
- Be concise. Do not repeat prior context. Explain only when it changes the decision, risk, or next step.
- Never add a "Co-Authored-By" line to commits — only the user is the author.
- After any change under `CloudHubCorp/Backoffice/`, run `make build` before considering the work done — the Astro Backoffice needs compiling for changes to take effect.

## Workspace Memory

Shared memory for this workspace lives at:

`memory/` (workspace root, next to `CLAUDE.md` — not per-repo)

Files the `/dev-*` skills read and write:

- `memory/user_profile.json` — communication/workflow preferences, loaded by `/dev` at the start of every ticket.
- `memory/epics.json` — cached epic list for the project key in `config.sh`, maintained by `/dev-create` so epics aren't re-queried every session.
- `memory/snapshots/<TICKET>.json` — checkpoints written by `/dev-reflect`, read by `/dev`, `/dev-resume`, `/dev-status`.
- `memory/assessments/<TICKET>.json` — technical assessments written by `/dev-assess`.
- `memory/vps-config.json` — production VPS connection settings for `/dev-db-sync`.
- `memory/review_rounds/<TICKET>.json` — PR review history written by `/dev-pr`.
- `memory/db-backups/` — downloaded DB snapshots from `/dev-db-sync`.
- `memory/patterns.json`, `memory/decisions.json`, `memory/mistakes.json`, `memory/global_rules.json` — cross-ticket learnings written by `/dev-reflect`, retrieved by `/dev-assess` **filtered** by `tags` (repo names + keywords; empty `tags` = universal, always included) so a growing memory doesn't dump irrelevant history into every ticket. `global_rules.json` entries also carry `status` (`active`/`superseded`), `confidence` (`≥0.8` = apply by default, `<0.4` = omit), and `source` (`live_correction` = captured directly from a user correction, confidence `0.9`; `retrospective` = inferred at `/dev-reflect` closing, confidence `0.6`).

Memory writes are part of the shared workflow — both agents may update `memory/` files directly as
local memory persistence, including capturing a live correction into `global_rules.json` the moment the
user corrects an in-progress approach (see "Capture Corrections as They Happen" in `skills/dev/SKILL.md`
— don't wait for `/dev-reflect` to reconstruct it retrospectively). Ask before Jira transitions or Jira
comments unless the user explicitly requested the flow that includes them (e.g. `/dev-reflect` closing
mode, `/dev-assess`).

Imported Claude project memory index (legacy — prefer `memory/` for new learnings unless the user
explicitly asks to update Claude memory): see `CLAUDE_MEMORY_INDEX` in `config.sh`.

## Business Context (`Business/`)

Separate from `memory/` above — `memory/` is ticket-level operational history, `Business/<cliente>/`
is stable, client-level knowledge (business context, scripts, credentials, confidential info) that
doesn't change ticket to ticket. Free-form on purpose: no required schema, the skills just read
whatever files are present. One optional convenience file, `client.md` (front-matter `repos:` /
`jira_key:`), lets `skills/dev-assess/SKILL.md` map `projects/` repos back to a client — it's offered,
never required, and `/dev-assess` never blocks on its absence. Credentials are never asked in chat:
`skills/manager-create/SKILL.md` leaves a blank placeholder file for the user to fill by hand. Only
`Business/README.md` is tracked in git; real client content is gitignored and the skills never assume
a particular VCS layout for it (single repo, one repo per client, or unversioned).

## Shared Skill Adapter

Canonical skill sources live in `skills/`. Claude Code discovers them automatically via symlinks
at `.claude/skills/<name>` → `../../skills/<name>` (committed to git, no generation step needed) — no
extra Claude-side config needed. Codex has no reliable equivalent auto-discovery, so this file is the
resolution path: when the user's intent matches one of the rows below, read the corresponding
`skills/<name>/SKILL.md` directly and execute that workflow with the user's arguments as `$ARGUMENTS`.

| User intent | Skill source |
| --- | --- |
| First-run setup / credentials & environment health check | `skills/dev-setup/SKILL.md` |
| Full ticket workflow (branch, develop, validate, commit, push) | `skills/dev/SKILL.md` |
| New idea/requirement with no ticket yet — spec + file a Jira ticket | `skills/dev-create/SKILL.md` |
| Technical deep dive / assessment before coding | `skills/dev-assess/SKILL.md` |
| Create a PR or handle review comments | `skills/dev-pr/SKILL.md` |
| Snapshot / closing reflection, persist learnings | `skills/dev-reflect/SKILL.md` |
| Resume a ticket already in progress | `skills/dev-resume/SKILL.md` |
| Review a teammate's PR ("review <PR URL>") | `skills/dev-review/SKILL.md` |
| DB migration workflow (QuintaApp-Api) | `skills/dev-migration/SKILL.md` |
| Read-only ticket/workspace status | `skills/dev-status/SKILL.md` |
| Pull a production DB snapshot | `skills/dev-db-sync/SKILL.md` |
| Bootstrap a new client's `Business/<cliente>/` | `skills/manager-create/SKILL.md` |
| Refresh/maintain an existing client's `Business/<cliente>/` | `skills/manager-update/SKILL.md` |
| Read-only client status/catch-up digest, proposals | `skills/manager-status/SKILL.md` |
| Execute a task on a client's remote infra (SSH/VPS), no local repo | `skills/manager-exec/SKILL.md` |
| Talk through a client requirement / list known clients / route to any of the above | `skills/manager/SKILL.md` |

`skills/dev/SKILL.md` is the orchestrator: when a request doesn't clearly match one of the other
rows, start there — it routes to the rest via its own dispatch table (including a precondition check
that routes to `skills/dev-setup/SKILL.md` when credentials/config are missing).

`skills/manager/SKILL.md` is a separate orchestrator for business-layer requests — it never creates or
edits code, Jira tickets, or PRs itself, but its Phase 2 (requirement intake) can delegate a client
requirement outward: to `skills/dev/SKILL.md` (which routes to `dev-create` to file the ticket) when it
needs local development, or to `skills/manager-exec/SKILL.md` when it needs execution on a client's own
remote infrastructure instead of a repo under `projects/`. `skills/dev-assess/SKILL.md` delegates to
`skills/manager-create/SKILL.md` automatically the first time it meets a repo with no client
association under `Business/`.

### Local scripts toolbox

`scripts/local/` is a growing, gitignored, per-project toolbox the `/dev-*` skills write for
themselves — small scripts that replace re-deriving the same multi-step procedure (and re-spending
tokens on it) every session. Before improvising a multi-step shell/git/gh/jq procedure, read
`scripts/local/MANIFEST.json` — a script may already exist for it. When you find yourself deriving a
deterministic, repeatable procedure worth keeping, write it there and register it in the manifest. Full
convention: `skills/dev/references/local-scripting.md`.

### Command Resolution Rules

- Do not treat `/dev-*` as a literal Codex slash command. Resolve it as: read the matching
  `skills/<name>/SKILL.md` and execute that workflow with the given arguments.
- When one skill delegates to another (e.g. `/dev` → `/dev-assess`), stop the current phase and follow
  the delegated skill's file first, exactly as it says.
- `$ARGUMENTS` in a skill file means the arguments supplied by the user or by the parent skill's delegation.
- Claude UI/CLI mechanics that appear across skill files have Codex fallbacks — this list is the
  canonical translation table; don't re-derive it per skill, and extend it here (not locally) when a
  new one turns up:
  - `/rename ...`: no-op in Codex; keep the intended title in the working summary if useful.
  - `/recap`: summarize from available context instead.
  - `/loop`: treat as one iteration unless continuous monitoring was explicitly requested.
  - `Task(...)` / subagent delegation: do the work locally unless the user explicitly asks for parallel delegation.
  - `/code-review ultra` (called after PR creation in `/dev-pr`; `/ultrareview` was the old name for the
    same thing, now deprecated): this launches a billed, Claude-Code-only cloud review that neither
    Codex nor even a plain Claude Code agent can trigger programmatically. Perform a normal Codex
    code-review pass instead, focused on bugs, regressions, security, and tests.
  - `Ctrl+B` (Claude Code's background-execution shortcut, used e.g. in `/dev` Phase 4 for slow test
    suites): no Codex equivalent — run the slow step sequentially, or tell the user it's running so they
    can work elsewhere while waiting.
  - `claude --worktree -C <path>` (used in `/dev` Phase 3 for parallel multi-repo development): no
    direct Codex flag equivalent. If simultaneous work across repos is genuinely needed, either run
    Codex sessions sequentially per repo, or set up the isolated copies yourself first with
    `git worktree add <path> <branch>` before starting Codex in each one.
  - If `jq` is unavailable in the environment (several skills read/write `memory/*.json` via `jq`), use
    Python's `json` module for the same read-modify-write instead of skipping the memory update.

Preserve every safety gate written into the skill files: ask before destructive operations, before
pushes, before Jira transitions/comments, and before any other external state change — unless the user
has already authorized it in the current conversation.

## Jira

Use the scripts instead of duplicating Jira credentials:

`uv run <JIRA_SCRIPTS from config.sh, or scripts/jira-communication/scripts if unset>/<core|workflow>/<script>.py <command> ...`

Common commands:

- `core/jira-issue.py get <ISSUE_KEY> --json`
- `core/jira-search.py query "<JQL>" --json`
- `workflow/jira-comment.py add <ISSUE_KEY> "<text>"`
- `workflow/jira-transition.py do <ISSUE_KEY> "<transition>"`
- `workflow/jira-create.py issue <PROJECT_KEY> "<summary>" -t <type> -d "<description>" --parent <EPIC_KEY>`

Jira base URL and project key: see `config.sh` (`JIRA_BASE_URL`, `PROJECT_KEY`). If Jira credentials
aren't set up yet (`~/.env.jira` missing), run `skills/dev-setup/SKILL.md` first — it needs a live
terminal, not this agent, since the token prompt can't be automated.

## Workspace Working Rules

- This workspace contains multiple repos — see `REPOS` in `config.sh`. Determine the affected repo(s) before editing — see `CLAUDE.md` for the full architecture map.
- Repos matching `SPECIAL_REPO_PATTERNS` (in `config.sh`) use `SPECIAL_REPO_BASE` as their base branch; everything else uses `master`.
- `/dev-db-sync` is only configured for repos listed in `DB_SYNC_REPOS` in `config.sh` (empty means disabled).

## Updating This Adapter

If a future session discovers a new recurring rule that should affect both Claude and Codex, add it
here. Ticket-specific details belong in `memory/tickets/` or `memory/snapshots/`, not here.
