---
name: manager-digest
description: "Read-only consolidated digest across everything — dev tickets, sprint health, and all clients — composed from /dev-status and /manager-status rather than duplicating their logic. Built to be the payload of a scheduled weekly routine so status stops being purely pull-based (today nothing surfaces unless explicitly asked), but works identically run on demand. Use for 'manager digest' or 'digest'. Delegated to by /manager for the 'digest' subcommand."
allowed-tools: Bash Read
---

# Manager Digest — Everything, Consolidated

Run the full digest: **$ARGUMENTS** (no arguments expected — always a full sweep)

This composes three existing read-only checks into one summary — it does not reimplement any of
their logic, just runs them and merges the output:

1. `/dev-status` (multi-ticket overview) — active tickets, prioritizing merged-and-unreflected ones.
2. `/dev-status sprint` — current sprint health, if the board has an active one.
3. `/manager-status` (multi-client overview) — all clients, including cross-client reuse proposals.

Apply "Role: Business Advisor" from `manager/SKILL.md` throughout — the point of this digest is
proactive surfacing, not a neutral dump. If everything is genuinely quiet, say that in one line and
stop; don't pad a quiet week to look substantive.

---

## Step 1 — Run the three checks

Invoke each and collect its output — don't re-derive their logic here, follow each skill's own
instructions as written:

```
/dev-status
/dev-status sprint
/manager-status
```

If any one fails (e.g. no active sprint, a client has no Jira tracking), that's an expected, normal
outcome for that section, not a reason to abort the whole digest — continue with the rest.

## Step 2 — Merge into one digest

```
## Digest — <fecha>

### Tickets que necesitan atención
<de /dev-status: priorizar merged-y-sin-reflect primero (misma regla de prioridad que dev-status),
después cualquier otro con next_step accionable. Omitir tickets que simplemente están progresando
bien sin nada que decidir.>

### Sprint actual
<de /dev-status sprint: días restantes, breakdown, estancados. "Sin sprint activo" si no hay.>

### Clientes
<de /manager-status: solo los que tienen algo que decir — nota vieja, ticket estancado, o propuesta
de reuso cross-cliente. No repetir la lista completa de clientes si la mayoría está tranquila.>

### Propuestas
<consolidar cualquier propuesta de negocio (de /manager-status) y cualquier riesgo técnico (de
/dev-status) en una sola lista priorizada — 1-4 items, no una por sección.>
```

Keep it short — this is meant to be read in under a minute, not to replace running the underlying
checks individually when you actually want depth on one item.

---

## Scheduling (optional, not automatic)

This skill only runs when invoked — it does not register itself as a recurring job. If a weekly
cadence is wanted, that's a separate, explicit step: use the `schedule` skill to create a routine
whose prompt is `/manager digest` (or equivalent), on whatever cadence is confirmed with the user.
Setting up a recurring scheduled agent is an ongoing commitment (it keeps running, keeps costing) —
never register one without the user explicitly confirming the cadence first.

---

## Related sibling skills

- `/dev-status` — the ticket/sprint half this composes, unmodified
- `/manager-status` — the client half this composes, unmodified
