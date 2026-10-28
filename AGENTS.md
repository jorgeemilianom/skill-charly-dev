# AGENTS.md

Este workspace usa un adaptador compartido para que Codex y Claude Code carguen el mismo contexto de
proyecto.

## Contexto de arranque obligatorio

Antes de hacer trabajo de proyecto, leer:

1. `agent-context.md`
2. `CLAUDE.md`, y `CLAUDE.local.md` si existe (Claude lo importa vía `@CLAUDE.local.md`; Codex no
   resuelve esa sintaxis, así que hay que leerlo explícitamente — tiene el mapa real de repos).
3. La salida de `python3 scripts/session_context.py` — el mismo digest de `memory/` (preferencias,
   notas de workflow, puntos ciegos, reglas universales) que Claude recibe por su hook `SessionStart`.
4. El `AGENTS.md` y/o `CLAUDE.md` local dentro de la subcarpeta del repo afectado, si existe.

El adaptador mapea las memorias de Claude, las skills de Claude, y las convenciones del proyecto a
instrucciones legibles por Codex sin copiar secretos.

## Alcance

Este archivo aplica en la raíz del workspace. Los `AGENTS.md` locales de cada repo sobreescriben o
extienden estas reglas dentro de sus propios subárboles.

## Seguridad

No duplicar credenciales de `~/.claude` o `~/.codex`. Usar scripts helper por path cuando haga falta.
Preservar los cambios del usuario en worktrees sucios, y preguntar antes de comandos destructivos,
pushes, o cambios de estado externo salvo que ya estén autorizados en la conversación actual.
