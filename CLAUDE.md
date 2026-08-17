# CLAUDE.md

Este archivo le da contexto a Claude Code (claude.ai/code) para trabajar en este repositorio.

> **Esto es una plantilla de ejemplo**, no un mapa de workspace real — `skill-charly-dev` es un repo
> público, así que este archivo solo muestra la forma que esperan las skills `/m-dev-*` y
> `/m-manager-*`. Reemplazá la tabla y el texto de abajo con tus propios repos. Si existe un
> `CLAUDE.local.md` gitignored al lado de este archivo, se importa automáticamente (ver el final de
> este archivo) y tiene precedencia para tu mapa de workspace real y privado — ahí es donde deberían
> vivir tus detalles reales de cliente/proyecto, no acá.

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
