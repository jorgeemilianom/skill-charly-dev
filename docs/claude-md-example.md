# Ejemplo de mapa de workspace para CLAUDE.md

Plantilla de la sección que describe tus repos. Copiala a tu `CLAUDE.local.md` (gitignored) y reemplazala con tus repos reales; `CLAUDE.md` queda genérico y liviano porque se carga en cada sesión.

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
