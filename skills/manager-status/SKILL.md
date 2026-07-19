---
name: manager-status
description: "Read-only client status/catch-up digest, no side effects. Combines Business/<cliente> context with linked Jira/repo activity (from client.md's manifest, if present) into a summary, then proactively surfaces risks/opportunities and opens the floor for discussion. Use for 'manager <cliente> status' (single client) or 'manager status' (all known clients). Delegated to by /manager for the 'status' subcommand."
allowed-tools: Bash Read
---

# Manager Status — Client Catch-Up and Advisory Digest

Status for: **$ARGUMENTS**

If `$ARGUMENTS` names a client, run the single-client digest. If empty, run the multi-client overview.

Distinct from `/manager`'s Phase 2 (requirement intake): this is read-only — no writes, no delegation
to `/dev`. It exists to get you up to speed and open a conversation. Any resulting action (a note to
save, a ticket to file) still goes back through `/manager`'s Phase 2 or `/manager-update`, not here.

> Before improvising a multi-step procedure, check `scripts/local/MANIFEST.json` — see
> `dev/references/local-scripting.md`.

Apply "Role: Business Advisor" from `manager/SKILL.md` throughout this digest — don't just recite
facts, flag what's stale/at-risk/an opportunity, and propose concretely. This digest is a conversation
opener, not a final report: end by inviting the user to push back, dig into one point, or just talk it
through, without forcing the conversation toward writing something down.

---

## Single client: `<cliente> status`

### Step 1 — Load everything

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CLIENTE="<cliente>"
[ -d "$WS/Business/$CLIENTE" ] && echo EXISTS || echo MISSING
[ -f "$WS/Business/$CLIENTE/Agent.md" ] && cat "$WS/Business/$CLIENTE/Agent.md"
cat "$WS/Business/$CLIENTE/context.md" 2>/dev/null
cat "$WS/Business/$CLIENTE/client.md" 2>/dev/null
```

If `MISSING`: say so and offer `/manager-create <cliente>`. Stop here.

### Step 2 — Pull linked dev/Jira state (only if `client.md` has a manifest)

If `client.md` has `repos:`, check each mapped repo for recent activity:
```bash
source "$WS/scripts/workspace-env.sh"
for REPO in <repos from client.md>; do
  git -C "$WS/${PROJECTS_PREFIX}${REPO}" fetch origin -q 2>/dev/null
  git -C "$WS/${PROJECTS_PREFIX}${REPO}" branch -a 2>/dev/null | grep -oiE "(feature|fix)/[a-z]+-[0-9]+" | sort -u
  git -C "$WS/${PROJECTS_PREFIX}${REPO}" log --oneline -5 2>/dev/null
done
```

If `client.md` has `jira_key` or `jira_epic`, query open work:
```bash
JIRA_SKILL="${JIRA_SCRIPTS:-$WS/scripts/jira-communication/scripts}"
uv run $JIRA_SKILL/core/jira-search.py --json query "<project = jira_key OR parent = jira_epic, whichever is set> AND statusCategory != Done ORDER BY updated DESC"
```

Skip this step silently if `client.md` has no manifest — not every client has code or Jira tracked in
this workspace.

### Step 3 — Present the digest

```
## Estado — <cliente>

### Contexto de negocio
<resumen de las notas mas recientes de context.md, no el archivo completo>

### Desarrollo en curso
<tickets abiertos / branches activos / PRs pendientes, o "sin actividad de desarrollo registrada">

### Propuestas
- <1-3 sugerencias concretas: riesgo, oportunidad, seguimiento pendiente>

---
¿Sobre qué querés profundizar, o hay algo de esto que no cuadra con lo que sabés vos?
```

---

## Multi-client overview: `status` (no client name)

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
[ -f "$WS/CLAUDE.md" ] || WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
find "$WS/Business" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | xargs -n1 basename
```

For each client, read only `context.md`'s most recent dated entry (not the full file) and, if
`client.md` has a manifest, a one-line dev status (open ticket count, or last commit date). Output one
line per client:
```
<cliente>  |  última nota: <date, short summary>  |  dev: <N tickets abiertos, o "sin tracking">
```

Close with the same advisor framing — if any client's last note is old, or has open tickets with no
recent movement, flag it as worth a check-in rather than staying silent about it.

---

## Related sibling skills

- `/manager` Phase 2 — requirement intake, once the conversation turns into an actual ask (a note to
  save, or a ticket to file via `/dev`)
- `/manager-update` — apply a change directly, when you already know what you want to write
