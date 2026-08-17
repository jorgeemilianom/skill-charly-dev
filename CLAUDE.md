# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **This is an example template**, not a real workspace map — `skill-charly-dev` is a public repo, so
> this file only shows the shape the `/m-dev-*` and `/m-manager-*` skills expect. Replace the table and
> prose below with your own repos. If a gitignored `CLAUDE.local.md` exists next to this file, it's
> imported automatically (see the bottom of this file) and takes precedence for your real, private
> workspace map — that's where your actual client/project details should live, not here.

## Workspace Overview

This is an example workspace — independent git repositories, cloned under `projects/`:

| Project | Stack | Purpose |
|---|---|---|
| `projects/backend-api/` | e.g. Go + MySQL | REST API, hexagonal architecture, source of truth for business logic |
| `projects/frontend-app/` | e.g. React + Vite | Web client, calls `backend-api` |
| `projects/internal-platform/` | e.g. PHP + Astro | Separate, independent product — no coupling with the other two |

Each sub-project has its own `CLAUDE.md`/`README.md` with detailed commands, architecture, and rules.
**Always read the sub-project docs before working in that directory.**

## Project Relationships

`backend-api` and `frontend-app` are tightly coupled: `frontend-app` calls `backend-api` via an env var
(e.g. `VITE_API_URL`), all fetches go through a single API client module, and auth uses Bearer JWT with
access/refresh tokens.

`internal-platform` is a separate product — it shares no code or infrastructure with the other two.

## Jira

Projects track work in Jira — see `JIRA_BASE_URL` and `PROJECT_KEY` in `config.sh`.

## Sub-project entry points

- **backend-api:** `projects/backend-api/CLAUDE.md` — commands (`make test`, `make build`, migrations), architecture map, coverage gate, SDD workflow.
- **frontend-app:** `projects/frontend-app/CLAUDE.md` — scripts (`npm run dev/build/test/lint`), folder conventions, API client details, route table.
- **internal-platform:** `projects/internal-platform/CLAUDE.md` — build/test commands, module scaffold, project-specific conventions.

---

## Self-hosted usage

Add as many rows/sections above as you have repos, delete what you don't need, and keep this file
generic if you plan to keep this workspace repo public — put anything real (client names, actual
architecture details, internal URLs) in the gitignored `CLAUDE.local.md` instead. See `README.md` for
the full self-hosted setup.

@CLAUDE.local.md
