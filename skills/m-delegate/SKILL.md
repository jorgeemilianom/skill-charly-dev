---
name: m-delegate
description: "Delegate a clear, bounded, verifiable task to another AI agent (Codex by default; Claude when the caller is Codex) running non-interactively in an isolated git worktree, then review its diff and integrate it. Saves the delegating agent's tokens, spreads usage across providers and lets independent subtasks run in parallel. Use when the user says '/m-delegate <task>', 'delegale a codex', 'que lo haga codex', or when — inside /m-dev Phase 3 or any other work — a subtask fits the delegation criteria below (tests for existing code, mechanical multi-file changes, boilerplate, a read-only investigation over a large codebase, a second-opinion review). Also 'delegate stats' to see what delegates well."
allowed-tools: Bash Read Edit
---

# Delegate — una IA le pasa trabajo a otra

Run for: **$ARGUMENTS**

Motor: `python3 $WS/scripts/delegate.py` (`-h` para todo). Corre el otro agente sin interacción, con un
contrato fijo (no commit/push/Jira/SSH/secretos, no salir del directorio, respuesta JSON con schema),
en un **worktree propio** (`worktrees/delegate-<id>`, rama `delegate/<id>`), y devuelve un reporte de
~8 líneas: estado, validación, diffstat. Todo queda en `memory/delegations/<id>/` (brief, eventos,
resultado, `diff.patch`, `meta.json`).

```bash
WS="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
while [ "$WS" != "/" ] && { [ ! -f "$WS/CLAUDE.md" ] || [ ! -f "$WS/config.example.sh" ]; }; do WS="$(dirname "$WS")"; done
```

## Cuándo delegar

Delegar conviene cuando **el brief es mucho más corto que el trabajo** y el resultado **se verifica
barato** (un comando de validación o un diff chico de leer).

| Sí | No |
|---|---|
| Tests para código que ya existe (criterio: pasan + cubren X) | Diseño o decisiones abiertas — eso lo decide el delegante con el usuario |
| Cambios mecánicos en muchos archivos (renombres, migrar una API, tipar) | Prod, infra remota, deploys, DB de dev compartida (`/m-manager-exec`) |
| Boilerplate con patrón existente (endpoint/módulo "como X") | Credenciales, Jira, GitHub, push — nunca, ni en modo read |
| Investigación read-only en un repo grande ("¿dónde se calcula X?, ¿quién llama a Y?") | Tareas que requieren el contexto de la conversación con el usuario |
| Segunda opinión: revisar un diff buscando bugs (`--mode read`) | Algo que tomaría menos tokens hacer que explicar |
| Subtareas independientes de un ticket, en paralelo | Repos con reglas de "trabajar directo en el checkout" (prod/bind-mounts) |

Por defecto: **Codex** (`--agent codex`) — consume la cuota de OpenAI, no la de Claude. Desde Codex,
la dirección inversa es `--agent claude` (útil para una revisión con otro modelo). `--effort low` para
tareas mecánicas; `medium` (default de la config) para el resto.

## Elegir agente y esfuerzo con datos

Antes de delegar, `python3 $WS/scripts/delegate.py stats` y `python3 $WS/scripts/evidence.py calibration`:
- tipo de tarea con veredictos `reworked`/`rejected` repetidos para un agente → no delegarlo (o cambiar de agente);
- tag/repo donde el delegante sobreestima (sesgo > +0.15) → delegar la parte mecánica pero revisar el diff completo;
- sin historial: Codex `--effort low` para lo mecánico, `medium` para el resto; `--agent claude --model haiku`
  para lecturas/resúmenes baratos cuando el delegante es Codex.

## Flujo

1. **Brief** (en un archivo del scratchpad o por stdin). Corto y cerrado — el otro agente no ve esta
   conversación:
   ```
   Objetivo: <una oración>
   Contexto: <archivos/funciones clave con ruta; patrón a imitar ("como src/x/Foo.ts")>
   Criterios de aceptación: <verificables, uno por línea>
   Fuera de alcance: <lo que NO tiene que tocar>
   Validación: <comando exacto que tiene que pasar>
   ```
2. **Predicción** (protocolo cognitivo): una experiencia por delegación —
   `"action":"delegar a codex: <tarea>","prediction":"se acepta sin retrabajo","probability":<honesta>`,
   tags `["delegation","<agente>","<repo>"]` (el veredicto de `review` es la evidencia: evaluarla a mano en el paso 6). Ver `/m-dev-reflect` 7.5 para el formato.
3. **Correr**:
   ```bash
   python3 $WS/scripts/delegate.py run --repo projects/<repo> --base <rama del ticket u origin/<base>> \
     --brief <archivo> [--agent codex] [--effort low] [--ticket <ID>] [--mode read]
   ```
   - `--base` = la rama donde se va a integrar, para que el patch aplique limpio.
   - `--dir <worktree del ticket>` en vez de `--repo` si conviene que edite directo ahí (nunca un
     checkout de `projects/`: el script lo rechaza salvo `--allow-shared`).
   - Tareas largas o varias en paralelo: lanzarlas con `run_in_background` (una por worktree) y seguir
     con otra cosa; avisan al terminar.
4. **Revisar** — esto es lo que el delegante no puede saltear:
   - `status != done`, validación en FALLA o `open_questions`: decidir si alcanza con un `followup`
     (misma sesión del agente, no recarga contexto: `delegate.py followup <id> --brief -`) o si se
     termina a mano.
   - Leer `diff.patch` (si es grande, al menos los archivos fuera del alcance esperado y los tests).
   - Correr la validación uno mismo en el worktree — el reporte del otro agente es un dato, no una prueba.
5. **Integrar** en la rama del ticket: `git -C <worktree-del-ticket> apply $WS/memory/delegations/<id>/diff.patch`
   (o `git merge --squash delegate/<id>`), revisar `git status`, y seguir el flujo normal de `/m-dev`
   (validación, commit con las reglas de siempre).
6. **Cerrar**: `delegate.py review <id> --verdict accepted|reworked|rejected --note "<por qué>"`,
   evaluar la experiencia del paso 2 con esa evidencia, y `delegate.py cleanup <id>`.

Al usuario, una línea por delegación: qué se delegó, a quién, resultado y si se integró.

## `stats`

`python3 $WS/scripts/delegate.py stats` — corridas, aceptadas sin retrabajo, duración y tokens por
agente. Con veredictos acumulados, ajustar el criterio de arriba: si un tipo de tarea se rechaza seguido,
dejar de delegarlo (regla en memoria vía `memory_store.py add-rule --tags delegation`).

## Notas

- Codex corre con sandbox `workspace-write` (escribe solo dentro del worktree, con red para deps/tests),
  habilitado por el perfil AppArmor `/etc/apparmor.d/codex-bwrap` (la VPS tiene
  `kernel.apparmor_restrict_unprivileged_userns=1`). Si un update de Codex cambia la ruta de su `bwrap`
  y la delegación falla con `bwrap: ... Permission denied`, revisar la ruta del perfil;
  `DELEGATE_CODEX_SANDBOX=danger-full-access` es el escape temporal.
- Costo fijo de Codex: ~50-70k tokens de entrada por corrida (la mayoría cacheados) al cargar su
  contexto. Por eso no conviene delegar tareas de un par de líneas.
- `--mode read` verifica al final que el árbol quedó intacto y avisa si no.
