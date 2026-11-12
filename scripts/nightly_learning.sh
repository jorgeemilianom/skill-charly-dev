#!/bin/bash
# Ciclo de aprendizaje nocturno (cron): evidencia externa → evaluación de predicciones → calibración,
# y correcciones del usuario en los transcripts → inbox para /m-memory consolidate. Solo escribe en memory/.
WS="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$WS/memory/evidence/nightly.log"
mkdir -p "$WS/memory/evidence"
{
  echo "== $(date -Is)"
  python3 "$WS/scripts/evidence.py" harvest --days 30
  python3 "$WS/scripts/correction_miner.py" --since-days 2
} >>"$LOG" 2>&1
tail -n 400 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
