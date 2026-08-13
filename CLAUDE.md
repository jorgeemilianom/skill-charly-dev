# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workspace Overview

This is the the team workspace — independent git repositories, cloned under `projects/`:

| Project | Stack | Purpose |
|---|---|---|
| `projects/backend-api/` | Go 1.22 + Gin + MySQL | REST API for the-product (hexagonal architecture) |
| `projects/frontend-app/` | React 19 + Vite + JSX | Web client for the-product |
| `projects/internal-platform/` | PHP 8.2 + Astro 5 + React | Multi-tenant SaaS framework (separate product) |
| `projects/Client B/client-b-back/` | Node/TS | Backend for Client B, talent discovery SaaS (client: Client B) |
| `projects/Client B/client-b-front/` | React/Vite | Frontend for Client B |
| `projects/client-sync-tool/` | Node.js (CommonJS) | SAP Business One/HANA ↔ PrestaShop sync tool + web panel (client: Client E) |
| `projects/client-landing/` | Static HTML | Landing page hosted for client Grupo T Seguros (content built by the client, the team only hosts it) |
| `projects/base-prestashop-9.1/` | PrestaShop 9 (empty scaffold) | Internal base/starter template for future PrestaShop 9 work — not tied to a specific client yet |
| `projects/personal-finance-app/` | Node/TS + Express + React/Vite + MySQL (Docker) | Personal finance app (single-tenant, migrated from internal-platform's `m_finances`) |
| `projects/document-saas.example/` | Node/TS monorepo (npm workspaces) + Docker | SaaS MVP: document upload, text extraction, AI-assisted analysis and chat per document |

Each sub-project has its own `CLAUDE.md` with detailed commands, architecture, and rules (document-saas.example currently documents itself via `README.md` and the `*.spec.*.md` files at its root instead). **Always read the sub-project docs before working in that directory.**

## Project Relationships

**the-product** is a rental marketplace for "quintas" (vacation properties) in San Luis, Argentina. The two the-product repos are tightly coupled:

- `backend-api` is the authoritative backend — hexagonal architecture, JWT auth, MySQL.
- `frontend-app` calls the API via `VITE_API_URL`; all fetches go through `src/services/apiClient.js`.
- Auth flow: frontend stores `access_token` + `refresh_token` in `localStorage`; API uses Bearer JWT with two token types (`"access"` / `"refresh"`).

**internal-platform** is a separate SaaS product (multi-tenant PHP monolith). It is **not** connected to the-product — they share no code or infrastructure. It also hosts custom modules for other the team clients (Client C, Grupo T Seguros) that have no repo of their own under `projects/`.

**Client B** is a talent-discovery SaaS client with its own two repos (`client-b-back`, `client-b-front`), plus a backoffice module inside internal-platform — not connected to the-product.

**client-sync-tool** is a standalone sync tool for client Client E (`client-e.example.com`), unrelated to any other project in this workspace.

**personal-finance-app** and **document-saas.example** are independent personal products, unrelated to the-product/internal-platform — they share no code or infrastructure with the rest of the workspace either.

## Jira

the-product, internal-platform, Client B, and Client E track work in Jira at `https://your-org.atlassian.net`, project key `PROJ`. Setup instructions are in `projects/backend-api/CLAUDE.md` under "Jira Integration". personal-finance-app and document-saas.example do not currently track work there.

## Sub-project entry points

- **backend-api:** `projects/backend-api/CLAUDE.md` — commands (`make test`, `make build`, migrations), hexagonal architecture map, coverage gate (≥80%), SDD workflow.
- **frontend-app:** `projects/frontend-app/CLAUDE.md` — scripts (`npm run dev/build/test/lint`), folder conventions, API client details, route table.
- **internal-platform:** `projects/internal-platform/CLAUDE.md` — `make` / `npm run` commands, multi-tenant rules, module scaffold, middleware pipeline, RepositoryAbstract reserved names, DatabaseService WHERE convention.
- **Client B:** `projects/Client B/Agent.md`, `projects/Client B/SpecPlan.md` — backend + frontend architecture, deploy notes.
- **client-sync-tool:** `projects/client-sync-tool/CLAUDE.md` — SAP HANA read, PrestaShop sync domains (`products`/`categories`/`orders`), dry-run vs write mode, web panel.
- **personal-finance-app:** `projects/personal-finance-app/CLAUDE.md` — Docker Compose commands, port architecture, backend/frontend structure, critical business rules (installments, monthly projection), DB tables.
- **document-saas.example:** `projects/document-saas.example/README.md` and `1 - spec.functional.md` / `2 - spec.tecnical.md` / `3 - spec.plan.md` — setup, functional spec, technical spec, roadmap.
