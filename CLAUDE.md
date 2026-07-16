# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workspace Overview

This is the the team workspace — three independent git repositories, cloned under `projects/`:

| Project | Stack | Purpose |
|---|---|---|
| `projects/backend-api/` | Go 1.22 + Gin + MySQL | REST API for the-product (hexagonal architecture) |
| `projects/frontend-app/` | React 19 + Vite + JSX | Web client for the-product |
| `projects/internal-platform/` | PHP 8.2 + Astro 5 + React | Multi-tenant SaaS framework (separate product) |

Each sub-project has its own `CLAUDE.md` with detailed commands, architecture, and rules. **Always read the sub-project CLAUDE.md before working in that directory.**

## Project Relationships

**the-product** is a rental marketplace for "quintas" (vacation properties) in San Luis, Argentina. The two the-product repos are tightly coupled:

- `backend-api` is the authoritative backend — hexagonal architecture, JWT auth, MySQL.
- `frontend-app` calls the API via `VITE_API_URL`; all fetches go through `src/services/apiClient.js`.
- Auth flow: frontend stores `access_token` + `refresh_token` in `localStorage`; API uses Bearer JWT with two token types (`"access"` / `"refresh"`).

**internal-platform** is a separate SaaS product (multi-tenant PHP monolith). It is **not** connected to the-product — they share no code or infrastructure.

## Jira

All three projects track work in Jira at `https://your-org.atlassian.net`, project key `PROJ`. Setup instructions are in `projects/backend-api/CLAUDE.md` under "Jira Integration".

## Sub-project entry points

- **backend-api:** `projects/backend-api/CLAUDE.md` — commands (`make test`, `make build`, migrations), hexagonal architecture map, coverage gate (≥80%), SDD workflow.
- **frontend-app:** `projects/frontend-app/CLAUDE.md` — scripts (`npm run dev/build/test/lint`), folder conventions, API client details, route table.
- **internal-platform:** `projects/internal-platform/CLAUDE.md` — `make` / `npm run` commands, multi-tenant rules, module scaffold, middleware pipeline, RepositoryAbstract reserved names, DatabaseService WHERE convention.
