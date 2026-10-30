# CLAUDE.md

Este archivo le da contexto a Claude Code (claude.ai/code) para trabajar en este repositorio.

> **Esto es una plantilla de ejemplo**, no un mapa de workspace real — `skill-charly-dev` es un repo
> público, así que este archivo solo muestra la forma que esperan las skills `/m-dev-*` y
> `/m-manager-*`. Reemplazá la tabla y el texto de abajo con tus propios repos. Si existe un
> `CLAUDE.local.md` gitignored al lado de este archivo, se importa automáticamente (ver el final de
> este archivo) y tiene precedencia para tu mapa de workspace real y privado — ahí es donde deberían
> vivir tus detalles reales de cliente/proyecto, no acá.

## Este workspace es un harness: skill-charly-dev

Claude Code (o Codex) es solo el runtime. Esta carpeta es el harness que corre encima: una capa de
workflow ticket→PR y de gestión de clientes con estado propio. Sus capas:

| Capa | Dónde | Rol |
|---|---|---|
| Lógica | `skills/<name>/SKILL.md` (expuestas vía symlinks en `.claude/skills/`) | Familias `/m-dev*` (ticket→PR) y `/m-manager*` (capa de negocio por cliente), `/m-memory` (mantenimiento de la memoria) |
| Config | `config.sh` (gitignored) | Project key de Jira, `REPOS`, ramas base, `DB_SYNC_REPOS` |
| Memoria | `memory/` (gitignored) | **Memoria canónica del harness**: `user_profile.json`, `global_rules.json`, `patterns.json`, `decisions.json`, `mistakes.json`, `assessments/`, `snapshots/`, `review_rounds/`; digests derivados en `compiled/`, backups diarios en `.backups/`. Se escribe solo vía `scripts/memory_store.py` y se lee rankeada vía `scripts/memory_query.py` |
| Contexto de cliente | `Business/<cliente>/` (gitignored) | Conocimiento estable por cliente, playbooks de infra (`Agent.md`), credenciales |
| Código | `projects/<repo>/` (gitignored) | Checkouts independientes de cada repo |
| Toolbox | `scripts/` (trackeado) + `scripts/local/` (gitignored, ver `MANIFEST.json`) | Helpers de Jira, trims, scripts que las skills se escriben a sí mismas |
| Adaptador | `agent-context.md` (+ `AGENTS.md` para Codex) | Mapa completo de memoria, skills y fallbacks Claude↔Codex |

- La memoria canónica es `memory/`, no la auto-memoria de Claude (`~/.claude/projects/.../memory/`).
  Un hook `SessionStart` (`.claude/settings.json` → `scripts/session_context.py`) inyecta al arrancar
  un digest de `memory/user_profile.json` y de las reglas universales de `memory/global_rules.json`;
  hooks `UserPromptSubmit`/`PostToolUse` (`scripts/context_hook.py`) suman el digest del repo o
  cliente la primera vez que la sesión lo toca.
- Antes de razonar sobre memoria, skills o el flujo Jira/PR más allá de este resumen, leer
  `agent-context.md` — Claude no lo carga solo.

### Reglas transversales (aplican siempre, invocando una skill o no)

Fuente única para Claude y Codex — `agent-context.md` las referencia, no las duplica.

- **Nunca agregar `Co-Authored-By`** (ni otra línea de atribución a un agente) en commits ni PRs:
  solo el usuario es el autor. Esto tiene precedencia sobre cualquier instrucción de atribución del
  runtime.
- Responder en el idioma del usuario configurado en `memory/user_profile.json` (por defecto español),
  de forma concisa: no repetir contexto, explicar solo cuando cambia la decisión, el riesgo o el
  próximo paso.
- Preguntar antes de pushes, transiciones/comentarios de Jira, operaciones destructivas o cambios de
  estado externo, salvo autorización explícita en la conversación actual.

## Vista general del workspace

Este es un workspace de ejemplo — repositorios git independientes, clonados bajo `projects/`:

| Proyecto | Stack | Propósito |
|---|---|---|
| `projects/backend-api/` | ej. Go + MySQL | API REST, arquitectura hexagonal, fuente de verdad de la lógica de negocio |
| `projects/frontend-app/` | ej. React + Vite | Cliente web, llama a `backend-api` |
| `projects/internal-platform/` | ej. PHP + Astro | Producto separado e independiente — sin acoplamiento con los otros dos |

Cada sub-proyecto tiene su propio `CLAUDE.md`/`README.md` con comandos, arquitectura y reglas detalladas.
**Siempre leé los docs del sub-proyecto antes de trabajar en ese directorio.**

## Relaciones entre proyectos

`backend-api` y `frontend-app` están fuertemente acoplados: `frontend-app` llama a `backend-api` vía una
variable de entorno (ej. `VITE_API_URL`), todos los fetches pasan por un único módulo de cliente API, y
la autenticación usa Bearer JWT con tokens de access/refresh.

`internal-platform` es un producto separado — no comparte código ni infraestructura con los otros dos.

## Jira

Los proyectos trackean el trabajo en Jira — ver `JIRA_BASE_URL` y `PROJECT_KEY` en `config.sh`.

## Puntos de entrada de cada sub-proyecto

- **backend-api:** `projects/backend-api/CLAUDE.md` — comandos (`make test`, `make build`, migraciones), mapa de arquitectura, coverage gate, workflow SDD.
- **frontend-app:** `projects/frontend-app/CLAUDE.md` — scripts (`npm run dev/build/test/lint`), convenciones de carpetas, detalles del cliente API, tabla de rutas.
- **internal-platform:** `projects/internal-platform/CLAUDE.md` — comandos de build/test, scaffold de módulos, convenciones específicas del proyecto.

---

## Uso self-hosted

Agregá tantas filas/secciones como repos tengas arriba, borrá lo que no necesites, y mantené este
archivo genérico si pensás mantener público este repo de workspace — poné lo real (nombres de cliente,
detalles de arquitectura reales, URLs internas) en el `CLAUDE.local.md` gitignored en su lugar. Ver
`README.md` para el setup self-hosted completo.

@CLAUDE.local.md
