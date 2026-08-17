---
name: m-dev-migration
description: "Runs the backend-api DB migration workflow: checks pending migrations, creates a new migration file, reviews the up/down SQL for safety, and runs it only after explicit authorization. Use for 'PROJ-XXX migration' or when a ticket requires a schema change. Delegated to by /m-dev when migration is detected or requested."
allowed-tools: Bash Read Write
---

# Dev Migration — DB Migration Workflow (backend-api only)

> CUSTOMIZE: `backend-api` is an example — point every `make -C projects/backend-api ...` call in this
> file at whichever of your repos actually owns the SQL migrations.

Run the migration workflow for: **$ARGUMENTS**

`$ARGUMENTS` is the ticket ID (`proj-XXX`), used for the migration filename and commit message.

> Before improvising a multi-step procedure, check `scripts/local/MANIFEST.json` — see `m-dev/references/local-scripting.md`. If the user corrects an in-progress approach, capture it immediately — see "Capture Corrections as They Happen" in `m-dev/SKILL.md`.

---

## Step 1 — Check pending migrations

```bash
make -C projects/backend-api migrate-check 2>/dev/null || \
  make -C projects/backend-api migrate-status 2>/dev/null
```

## Step 2 — Create migration file (if adding a new one)

```bash
# Asks for migration name interactively
make -C projects/backend-api migrate-create
```
Name format: `<short_description>_<TICKET_ID_LOWERCASE>` (e.g. `add_reviews_table_proj42`)

## Step 3 — Write migration SQL

Write both up and down scripts in the generated files.

## Step 4 — Review before running

- Does the `down` script fully reverse the `up` script?
- Any data-destructive operations (DROP COLUMN, TRUNCATE)?
- Impact on existing rows?

## Step 5 — Ask for authorization before running

> "Voy a correr `make migrate-up` en backend-api. ¿Confirmás? (requiere DB_* env vars)"

```bash
make -C projects/backend-api migrate-up
```

## Step 6 — Verify and commit

```bash
make -C projects/backend-api test
git add projects/backend-api/migrations/
git commit -m "<TICKET_ID> | add migration <migration_name>"
```
