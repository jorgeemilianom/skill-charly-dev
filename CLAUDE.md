# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workspace Overview

This is the MSoftIA workspace — three independent git repositories, cloned under `projects/`:

| Project | Stack | Purpose |
|---|---|---|
| `projects/QuintaApp-Api/` | Go 1.22 + Gin + MySQL | REST API for QuintaApp (hexagonal architecture) |
| `projects/QuintaApp-Frontend/` | React 19 + Vite + JSX | Web client for QuintaApp |
| `projects/CloudHubCorp/` | PHP 8.2 + Astro 5 + React | Multi-tenant SaaS framework (separate product) |

Each sub-project has its own `CLAUDE.md` with detailed commands, architecture, and rules. **Always read the sub-project CLAUDE.md before working in that directory.**

## Project Relationships

**QuintaApp** is a rental marketplace for "quintas" (vacation properties) in San Luis, Argentina. The two QuintaApp repos are tightly coupled:

- `QuintaApp-Api` is the authoritative backend — hexagonal architecture, JWT auth, MySQL.
- `QuintaApp-Frontend` calls the API via `VITE_API_URL`; all fetches go through `src/services/apiClient.js`.
- Auth flow: frontend stores `access_token` + `refresh_token` in `localStorage`; API uses Bearer JWT with two token types (`"access"` / `"refresh"`).

**CloudHubCorp** is a separate SaaS product (multi-tenant PHP monolith). It is **not** connected to QuintaApp — they share no code or infrastructure.

## Jira

All three projects track work in Jira at `https://msoftia.atlassian.net`, project key `MSOF`. Setup instructions are in `projects/QuintaApp-Api/CLAUDE.md` under "Jira Integration".

## Sub-project entry points

- **QuintaApp-Api:** `projects/QuintaApp-Api/CLAUDE.md` — commands (`make test`, `make build`, migrations), hexagonal architecture map, coverage gate (≥80%), SDD workflow.
- **QuintaApp-Frontend:** `projects/QuintaApp-Frontend/CLAUDE.md` — scripts (`npm run dev/build/test/lint`), folder conventions, API client details, route table.
- **CloudHubCorp:** `projects/CloudHubCorp/CLAUDE.md` — `make` / `npm run` commands, multi-tenant rules, module scaffold, middleware pipeline, RepositoryAbstract reserved names, DatabaseService WHERE convention.
