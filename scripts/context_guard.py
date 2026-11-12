#!/usr/bin/env python3
"""Claude Code hook (UserPromptSubmit): avisa cuando el contexto de la sesión se agranda.

Cada turno re-lee todo el contexto acumulado (cacheado, pero se paga): en este workspace eso es ~70% del
costo, y dos sesiones de 400+ turnos explicaron la mitad del consumo de 40. Este hook lee el tamaño de
contexto del último turno en el transcript y, la primera vez que cruza cada umbral, muestra un aviso al
usuario y le pide al agente que proponga cortar: checkpoint del ticket + /clear (+ /m-dev-resume), o
/compact si la tarea sigue y el historial viejo ya no aporta.

Umbrales: CONTEXT_GUARD_STEPS (tokens, default "120000,180000,250000"). Nunca bloquea: ante cualquier
error sale 0 sin output.
"""
import json
import os
import sys
import tempfile

STEPS = [int(x) for x in os.environ.get("CONTEXT_GUARD_STEPS", "120000,180000,250000").split(",")]
TAIL_BYTES = 400_000


def last_context(transcript):
    with open(transcript, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - TAIL_BYTES))
        lines = f.read().decode("utf-8", "replace").splitlines()
    for line in reversed(lines):
        if '"usage"' not in line:
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        u = (e.get("message") or {}).get("usage") if isinstance(e.get("message"), dict) else None
        if e.get("type") == "assistant" and u:
            return u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
    return 0


def main():
    data = json.load(sys.stdin)
    transcript, sid = data.get("transcript_path"), data.get("session_id") or "nosession"
    if not transcript or not os.path.exists(transcript):
        return
    ctx = last_context(transcript)
    crossed = [s for s in STEPS if ctx >= s]
    if not crossed:
        return
    d = os.path.join(tempfile.gettempdir(), f"skill-charly-dev-hooks-{os.getuid()}")
    os.makedirs(d, mode=0o700, exist_ok=True)
    sp = os.path.join(d, f"{sid}.guard.json")
    try:
        warned = json.load(open(sp))
    except Exception:
        warned = []
    step = crossed[-1]
    if step in warned:
        return
    json.dump(warned + [step], open(sp, "w"))
    k = ctx // 1000
    print(json.dumps({
        "systemMessage": f"Contexto en ~{k}k tokens: cada turno lo relee entero. Si cambiaste de tarea, /clear; "
                         f"si es el mismo ticket, checkpoint (/m-dev-reflect) + /clear + /m-dev-resume.",
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                f"[context_guard] El contexto de esta sesión está en ~{k}k tokens. Al final de tu respuesta, en UNA "
                "línea, proponé cortar: si el pedido actual es otra tarea, /clear; si sigue el mismo ticket, guardar "
                "checkpoint (/m-dev-reflect <ID> checkpoint) y /clear + /m-dev-resume <ID>; si no hay ticket, /compact. "
                "No repitas este aviso hasta el próximo umbral."),
        },
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
