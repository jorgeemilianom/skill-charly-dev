# Commands.md

Referencia operativa rápida de los comandos disponibles en este workspace. Para la explicación
narrativa del sistema y el flujo completo, ver [README.md](README.md); para la relación entre
proyectos y clientes, ver [CLAUDE.md](CLAUDE.md). Este documento es la chuleta de "qué tipeo" —
sintaxis exacta, argumentos, ejemplos.

Dos familias de comandos:

- **`/m-dev*`** — flujo técnico: ticket → código → PR → cierre. Crea/edita código, Jira, PRs.
- **`/m-manager*`** — capa de negocio: contexto de cliente, requerimientos, ejecución remota. Nunca
  toca código, Jira ni PRs directamente — delega a `/m-dev` cuando hace falta desarrollo.

---

## `/m-dev` — orquestador principal

Punto de entrada por defecto. Detecta el tipo de argumento y rutea solo.

| Uso | `$ARGUMENTS` | Qué hace |
|---|---|---|
| `/m-dev PROJ-123` | ticket ID | Loop completo: rama → desarrollo → validación → commit → push |
| `/m-dev arreglar el timeout de login` | idea libre, sin ticket | Rutea a `/m-dev-create` |
| `/m-dev https://github.com/org/repo/pull/42` | URL de PR propia | Retoma el PR: lee comentarios, aplica fixes |
| `/m-dev review https://github.com/org/repo/pull/42` | `review <URL>` | Rutea a `/m-dev-review` (PR ajena) |
| `/m-dev PROJ-123 <subcomando>` | ticket + subcomando | Rutea al skill hermano que corresponda |

Antes de arrancar cualquier flujo, `/m-dev` verifica prerrequisitos (config.sh, credenciales Jira, gh
auth, repos clonados). Si falta algo, dirige a `/m-dev-setup`.

---

## Referencia por comando

### `/m-dev-setup` — setup inicial y health check
```
/m-dev-setup            # setup interactivo completo
/m-dev-setup check      # solo verificación, sin prompts (lo usa /m-dev internamente)
```
Correr una vez después de clonar, o cuando `/m-dev` reporte prerrequisitos faltantes.

### `/m-dev-create` — de idea libre a ticket filed
```
/m-dev-create agregar cancelación de reservas a the-product
```
Discute el alcance, arma el spec, resuelve el epic (lista cacheada) y crea el ticket en Jira.

### `/m-dev-assess` — assessment técnico previo al código
```
/m-dev-assess PROJ-123
```
Explora el codebase, carga `memory/`, produce un Technical Assessment con confidence score.
Una sola confirmación del usuario cubre también la documentación del ticket y su paso a "In Progress".

### `/m-dev-pr` — crear PR / procesar revisión
```
/m-dev-pr PROJ-123           # Fase 1: arma el PR, lo abre con gh, comenta en Jira, corre code-review ultra
/m-dev-pr PROJ-123 review    # Fase 2: registra la ronda de revisión, implementa fixes, valida, commit, push
```

### `/m-dev-reflect` — snapshot / cierre
```
/m-dev-reflect PROJ-123              # checkpoint: guarda snapshot del estado actual
/m-dev-reflect PROJ-123 closing      # cierre: reflexión completa, guarda en memory/, comenta en Jira
```
Se puede invocar en cualquier momento del ciclo de vida del ticket, no solo al cerrar.

### `/m-dev-resume` — reconstruir contexto de un ticket en curso
```
/m-dev-resume PROJ-123
```
Lee commits, diffs y estado de PR en todos los repos afectados; devuelve resumen + blurb para daily.

### `/m-dev-review` — revisar PR de un compañero
```
/m-dev-review https://github.com/org/repo/pull/42
```
Revisión contra arquitectura y convenciones de the team; opcionalmente la postea en GitHub.
(Equivale a `/m-dev review <URL>`.)

### `/m-dev-migration` — migraciones de DB (solo backend-api)
```
/m-dev-migration PROJ-123
```
Chequea pendientes, crea el archivo de migración, revisa el SQL up/down, corre solo con
autorización explícita.

### `/m-dev-status` — estado de solo lectura
```
/m-dev-status                 # overview de todos los tickets activos del workspace
/m-dev-status PROJ-123        # ramas, commits y estado de PR de un ticket puntual
/m-dev-status epic PROJ-100   # rollup de todos los tickets bajo un epic
/m-dev-status sprint          # salud del sprint actual
```

### `/m-dev-db-sync` — snapshot de DB de producción
```
/m-dev-db-sync <proyecto>            # trae un snapshot fresco por SSH
/m-dev-db-sync config <proyecto>     # setup interactivo de conexión para ese proyecto
```
Requiere `DB_SYNC_REPOS` configurado en `config.sh`. `<proyecto>` debe estar en esa lista.

---

### `/m-manager` — orquestador de negocio
```
/m-manager                              # lista los clientes conocidos
/m-manager <cliente>                    # conversa el contexto/requerimiento de ese cliente
/m-manager <cliente> <requerimiento>    # intake: resuelve directo, o delega a /m-dev o /m-manager-exec
/m-manager <cliente> status             # rutea a /m-manager-status
/m-manager status                       # rutea a /m-manager-status (todos los clientes)
/m-manager digest                       # rutea a /m-manager-digest
/m-manager <cliente> exec <tarea>       # rutea a /m-manager-exec
```
Nunca crea/edita código, Jira ni PRs — cuando el requerimiento necesita desarrollo, delega a `/m-dev`
(que a su vez llama a `/m-dev-create` si no hay ticket todavía).

### `/m-manager-create` — bootstrap de un cliente nuevo
```
/m-manager-create NombreCliente
```
Arma `Business/<cliente>/` de forma interactiva; credenciales quedan como placeholder para completar
a mano. También se dispara automáticamente desde `/m-dev-assess` la primera vez que toca un repo sin
cliente asociado.

### `/m-manager-update` — mantener un cliente existente
```
/m-manager-update NombreCliente
```
Muestra el contenido actual y agrega contexto/notas nuevas. No toca `credentials.md`.

### `/m-manager-status` — digest de solo lectura
```
/m-manager-status                # todos los clientes
/m-manager-status NombreCliente  # un cliente puntual
```
Combina contexto de negocio + actividad Jira/repo vinculada; abre la conversación, no ejecuta nada.

### `/m-manager-digest` — todo consolidado
```
/m-manager-digest
```
Junta `/m-dev-status`, `/m-dev-status sprint` y `/m-manager-status` en un solo resumen. Pensado como payload
de una rutina semanal programada, pero funciona igual on-demand.

### `/m-manager-exec` — ejecución remota en infraestructura de cliente
```
/m-manager-exec NombreCliente reiniciar el servicio de sync
```
Para clientes cuyo trabajo no vive en un repo local con Jira/PRs, sino directo sobre su
infraestructura (VPS, hosting compartido) por SSH/SFTP. Lecturas corren libres; todo lo que muta
estado remoto (deploy, restart, escritura) pide autorización explícita cada vez.

---

## Escenarios comunes

| Quiero... | Comando |
|---|---|
| Empezar a trabajar un ticket que ya existe | `/m-dev PROJ-123` |
| Convertir una idea en ticket | `/m-dev-create <idea>` o `/m-dev <idea>` |
| Ver en qué está todo antes de arrancar el día | `/m-manager-digest` |
| Retomar un ticket que dejé a medias ayer | `/m-dev-resume PROJ-123` |
| Responder comentarios de revisión de mi PR | `/m-dev-pr PROJ-123 review` o `/m-dev <URL del PR>` |
| Revisar el PR de un compañero | `/m-dev-review <URL>` |
| Cerrar un ticket ya mergeado | `/m-dev-reflect PROJ-123 closing` |
| Un cliente nuevo pide algo y no tiene carpeta en `Business/` | `/m-manager <cliente> <pedido>` |
| Reiniciar algo en el servidor de un cliente | `/m-manager-exec <cliente> <tarea>` |
| Refrescar un snapshot de DB local | `/m-dev-db-sync <proyecto>` |

---

## Notas

- `$ARGUMENTS` en cada skill acepta el ticket como `proj-XXX` o `PROJ-XXX` indistintamente (se
  normaliza a mayúsculas).
- Todos los skills `/m-dev*` y `/m-manager*` comparten resolución de raíz de workspace y convención de
  scripts locales (`scripts/local/MANIFEST.json`) — ver `skills/m-dev/SKILL.md` para el detalle.
- Antes de scriptear a mano un procedimiento repetitivo, revisar si ya existe en
  `scripts/local/MANIFEST.json`.
