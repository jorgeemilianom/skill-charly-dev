---
name: dev-migration
description: "Runs the QuintaApp-Api DB migration workflow: checks pending migrations, creates a new migration file, reviews the up/down SQL for safety, and runs it only after explicit authorization. Use for 'PROJ-XXX migration' or when a ticket requires a schema change. Delegated to by /dev when migration is detected or requested."
allowed-tools: Bash Read Write
---

# Dev Migration — DB Migration Workflow (QuintaApp-Api only)

Run the migration workflow for: **$ARGUMENTS**

`$ARGUMENTS` is the ticket ID (`msof-XXX`), used for the migration filename and commit message.

> Before improvising a multi-step procedure, check `.ai/vendor/local/MANIFEST.json` — see `dev/references/local-scripting.md`.

---

## Step 1 — Check pending migrations

```bash
make -C QuintaApp-Api migrate-check 2>/dev/null || \
  make -C QuintaApp-Api migrate-status 2>/dev/null
```

## Step 2 — Create migration file (if adding a new one)

```bash
# Asks for migration name interactively
make -C QuintaApp-Api migrate-create
```
Name format: `<short_description>_<TICKET_ID_LOWERCASE>` (e.g. `add_reviews_table_msof42`)

## Step 3 — Write migration SQL

Write both up and down scripts in the generated files.

## Step 4 — Review before running

- Does the `down` script fully reverse the `up` script?
- Any data-destructive operations (DROP COLUMN, TRUNCATE)?
- Impact on existing rows?

## Step 5 — Ask for authorization before running

> "Voy a correr `make migrate-up` en QuintaApp-Api. ¿Confirmás? (requiere DB_* env vars)"

```bash
make -C QuintaApp-Api migrate-up
```

## Step 6 — Verify and commit

```bash
make -C QuintaApp-Api test
git add QuintaApp-Api/migrations/
git commit -m "<TICKET_ID> | add migration <migration_name>"
```
